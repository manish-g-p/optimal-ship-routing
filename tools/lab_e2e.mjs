// Browser end-to-end check of the Nautilus web app (route planning + Simulation lab).
// Drives a real headless Chromium over the DevTools protocol - no npm packages needed (Node >= 22).
// Usage: CHROME=/path/to/chrome node tools/lab_e2e.mjs <output-dir> [http://localhost:8000]
// Needs a running server (python server.py, or the Docker image) and a Maps key in .env.
// Prints PASS/FAIL per check, HTTP errors, failed loads and console errors; saves screenshots.
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";

const OUT = process.argv[2];
const BASE = process.argv[3] || "http://localhost:8000";
const CHROME = process.env.CHROME || process.env.HOME + "/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome";
const chrome = spawn(CHROME, ["--headless=new", "--no-sandbox", "--disable-gpu",
  "--remote-debugging-port=9334", `--user-data-dir=${OUT}/chrome-prof`,
  "--window-size=1500,950", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let ws, id = 0; const pending = new Map();
const consoleIssues = [], httpErrors = [], failed = [];
const apiCalls = new Set();      // "METHOD /api/path {body keys}" - request shapes sent by the UI
const results = [];
const check = (name, ok, info = "") => { results.push([ok ? "PASS" : "FAIL", name, info]);
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${info ? "  -- " + info : ""}`); };

function send(method, params = {}) {
  return new Promise((res) => { const i = ++id; pending.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params })); });
}
async function ev(expr) {
  const r = await send("Runtime.evaluate", { expression: `(async () => { ${expr} })()`,
    awaitPromise: true, returnByValue: true });
  if (r.result.exceptionDetails) throw new Error("page: " + JSON.stringify(r.result.exceptionDetails).slice(0, 300));
  return r.result.result.value;
}
async function waitFor(expr, ms, label) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await ev(`return !!(${expr});`)) return true; await sleep(250); }
  throw new Error("timeout waiting for " + label);
}
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.result.data, "base64"));
}
const state = (field) => ev(`return lab.state ? lab.state.${field} : null;`);
async function mouseDrag(x0, y0, dx, dy) {          // real pointer events (press, move, release)
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x: x0, y: y0, button: "left", clickCount: 1 });
  for (let i = 1; i <= 8; i++)
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: x0 + dx * i / 8, y: y0 + dy * i / 8, button: "left", buttons: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: x0 + dx, y: y0 + dy, button: "left", clickCount: 1 });
  await sleep(250);
}
const rect = (sel) => ev(`const r=document.querySelector("${sel}").getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height};`);
/* every visible floating panel inside the viewport and clear of other panels,
   the top bar and the Google zoom / map-type controls */
const LAYOUT = `const vis=[...document.querySelectorAll('.fpanel')].filter(p=>p.offsetParent!==null);
  const R=vis.map(p=>[p.id,p.getBoundingClientRect()]);
  const hit=(p,q)=>!(p.right<=q.left||q.right<=p.left||p.bottom<=q.top||q.bottom<=p.top);
  const bad=[];
  for(const [i,r] of R){ if(r.left<0||r.top<0||r.right>innerWidth||r.bottom>innerHeight) bad.push(i+' off-screen');
    for(const [j,q] of R) if(i<j && hit(r,q)) bad.push(i+' x '+j);
    for(const k of keepOut()) if(hit(r,k)) bad.push(i+' covers a control/top bar'); }
  return {n:R.length, bad, overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth};`;

try {
  let targets;
  for (let i = 0; i < 40; i++) {
    try { targets = await (await fetch("http://127.0.0.1:9334/json/list")).json(); break; } catch { await sleep(250); }
  }
  ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  ws.addEventListener("message", (m) => {
    const d = JSON.parse(m.data);
    if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); }
    if (d.method === "Runtime.exceptionThrown") consoleIssues.push("EXCEPTION " + (d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text).slice(0, 300));
    if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error")
      consoleIssues.push("console.error " + d.params.args.map((a) => a.value ?? a.description).join(" ").slice(0, 200));
    if (d.method === "Network.responseReceived" && d.params.response.status >= 400)
      httpErrors.push(`${d.params.response.status} ${d.params.response.url.replace(BASE, "")}`);
    if (d.method === "Network.requestWillBeSent" && d.params.request.url.includes("/api/")) {
      const rq = d.params.request, path = new URL(rq.url).pathname.replace(/[0-9a-f]{32}/, "<id>");
      let keys = "";
      try { const b = JSON.parse(rq.postData || "null"); if (b && typeof b === "object") keys = JSON.stringify(Object.keys(b).sort()); } catch {}
      apiCalls.add(`${rq.method} ${path} ${keys}`);
    }
    if (d.method === "Network.loadingFailed" && !d.params.canceled)
      failed.push(`${d.params.errorText} ${d.params.type}`);
  });
  await send("Runtime.enable"); await send("Network.enable"); await send("Page.enable");
  await send("Page.navigate", { url: BASE + "/" });
  await waitFor("typeof META !== 'undefined' && META && lab.presets.length", 30000, "app init");
  check("homepage loads, Maps + metadata + presets", true, `maps auth failed=${await ev("return window.__gmAuthFailed")}`);

  // ---- 1. static route planning (regression) ----
  await ev(`$('go').click();`);
  await waitFor("!$('results').classList.contains('hidden') && $('results-title').textContent==='Route comparison'", 60000, "route result");
  check("static route planning renders two route cards",
    await ev("return document.querySelectorAll('#cards .card').length === 2;"),
    await ev("return $('cards').innerText.replace(/\\n+/g,' ').slice(0,120);"));
  await shot("1-route-planning");

  // ---- 2. lab mode ----
  await ev(`document.querySelector('#mode button[data-val=lab]').click();`);
  await sleep(600);
  check("lab mode: setup, simulation and weather panels visible; route-planning panel hidden",
    await ev("return ['fp-setup','fp-sim','fp-weather'].every(id=>$(id).offsetParent!==null) && $('side-panel').offsetParent===null && $('go').offsetParent===null && $('results').classList.contains('hidden');"));
  const fresh = await ev(`const vis=[...document.querySelectorAll('.fpanel')].filter(p=>p.offsetParent!==null);
    const area=vis.reduce((a,p)=>{const r=p.getBoundingClientRect();return a+r.width*r.height;},0)/(innerWidth*innerHeight);
    const text=vis.map(p=>p.innerText).join(' ');
    return {area:+area.toFixed(3), collapsed:vis.filter(p=>p.classList.contains('collapsed')).map(p=>p.id), clutter:/route cost|projected|km sailed|cells explored|h sailed/i.test(text)};`);
  check("fresh lab: map dominant (panels < 30% of viewport), secondary panels collapsed, no metric clutter",
    fresh.area < 0.30 && fresh.collapsed.includes("fp-events") && fresh.collapsed.includes("fp-key") && !fresh.clutter, JSON.stringify(fresh));
  await shot("0-lab-fresh");
  const heat = `return {base: !!waveOverlay && waveOverlay.getMap() === map, sim: !!lab.objs.overlay && lab.objs.overlay.getMap() === map, legend: $('lab-legend-max').textContent};`;
  const hm0 = await ev(heat);
  await ev("$('lab-waves').click();");
  const hmOff = await ev(heat);
  await ev("$('lab-waves').click();");
  const hmOn = await ev(heat);
  check("wave heatmap shown in the lab before a voyage exists, and the toggle works",
    hm0.base && !hmOff.base && hmOn.base && /\d m/.test(hm0.legend), JSON.stringify([hm0, hmOff, hmOn]));

  // ---- panels: drag, collapse, hide/dock, front, map still interactive ----
  const w0 = await rect("#fp-weather"), h0 = await rect("#fp-weather .fp-title");
  await mouseDrag(h0.x + 10, h0.y + h0.h / 2, -220, 140);
  const w1 = await rect("#fp-weather");
  check("panel drags by its header and stays where dropped",
    Math.abs(w1.x - (w0.x - 220)) < 3 && Math.abs(w1.y - (w0.y + 140)) < 3 &&
    await ev("return pstate($('fp-weather')).x !== undefined;"), `moved (${Math.round(w1.x - w0.x)}, ${Math.round(w1.y - w0.y)})`);
  const b0 = await rect("#fp-weather .fp-collapse");
  await mouseDrag(b0.x + b0.w / 2, b0.y + b0.h / 2, -150, 80);     // press on a header BUTTON
  const w2 = await rect("#fp-weather");
  await ev("if ($('fp-weather').classList.contains('collapsed')) $('fp-weather').querySelector('.fp-collapse').click();");
  const sp = await rect("#lab-speed"), simBefore = await rect("#fp-sim");
  await mouseDrag(sp.x + 10, sp.y + sp.h / 2, 120, -120);           // press on a SELECT in a body
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape" });
  const simAfter = await rect("#fp-sim");
  check("dragging from header buttons or form controls does not move a panel",
    Math.abs(w2.x - w1.x) < 1 && Math.abs(w2.y - w1.y) < 1 && Math.abs(simAfter.x - simBefore.x) < 1 && Math.abs(simAfter.y - simBefore.y) < 1);
  await ev("$('fp-weather').querySelector('.fp-collapse').click();");
  const wc = await rect("#fp-weather");
  await ev("$('fp-weather').querySelector('.fp-collapse').click();");
  const we = await rect("#fp-weather");
  check("panel collapses to its header and expands again", wc.h < 50 && we.h > 100, `collapsed ${Math.round(wc.h)} px, expanded ${Math.round(we.h)} px`);
  await ev("$('fp-events').querySelector('.fp-hide').click();");
  const hidden = await ev("return $('fp-events').offsetParent === null && !document.querySelector('#lab-dock button[data-p=fp-events]').classList.contains('on');");
  await ev("document.querySelector('#lab-dock button[data-p=fp-events]').click();");
  check("panel hides to the dock and comes back from it", hidden &&
    await ev("return $('fp-events').offsetParent !== null && document.querySelector('#lab-dock button[data-p=fp-events]').classList.contains('on');"));
  const st0 = await rect("#fp-setup .fp-title");
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x: st0.x + 5, y: st0.y + 5, button: "left", clickCount: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: st0.x + 5, y: st0.y + 5, button: "left", clickCount: 1 });
  check("clicking a panel brings it to the front",
    await ev("const z=[...document.querySelectorAll('.fpanel')].map(p=>+p.style.zIndex||10); return +$('fp-setup').style.zIndex === Math.max(...z);"));
  const c0 = await ev("return map.getCenter().toJSON();");
  await mouseDrag(700, 450, 160, 60);                                  // empty map area
  const c1 = await ev("return map.getCenter().toJSON();");
  check("map still pans with the mouse (panels do not capture map interaction)",
    Math.abs(c1.lng - c0.lng) > 0.1 || Math.abs(c1.lat - c0.lat) > 0.1, JSON.stringify([c0, c1]));
  await ev("lab.selected = null; ui.panels = {}; uiSave(); layoutPanels();");   // back to default layout
  check("controls before a voyage: Step/Pause/Reset disabled",
    await ev("return $('lab-step').disabled && $('lab-pause').disabled && $('lab-reset').disabled;"));
  await ev(`$('vessel').value='General Cargo'; $('vessel').dispatchEvent(new Event('change')); $('lab-preset').value='none'; $('lab-speed').value='150';`);

  // start -> runs automatically
  await ev(`$('lab-start').click();`);
  await waitFor("lab.state && lab.state.step >= 3", 60000, "auto steps");
  const hmRun = await ev(`return {base: !!waveOverlay && waveOverlay.getMap() === map, sim: !!lab.objs.overlay && lab.objs.overlay.getMap() === map};`);
  check("during a voyage the heatmap shows the voyage's own weather field (one overlay, not two)",
    hmRun.sim && !hmRun.base, JSON.stringify(hmRun));
  await ev(`$('lab-pause').click();`);
  await waitFor("!lab.loop", 15000, "loop stopped");
  const s1 = await state("step"); await sleep(2000); const s2 = await state("step");
  check("start runs automatically; pause stops progress", s1 >= 3 && s1 === s2, `step after pause ${s1} -> ${s2} (2 s later)`);
  await ev(`$('lab-start').click();`);
  await waitFor(`lab.state.step >= ${s2 + 2}`, 30000, "resume");
  await ev(`$('lab-pause').click();`); await waitFor("!lab.loop", 15000, "loop stopped");
  const s3 = await state("step");
  check("resume continues from the same voyage (no restart)", s3 >= s2 + 2 && (await ev("return lab.state.timeline.filter(e=>e.kind==='voyage_initialized').length")) === 1, `step ${s2} -> ${s3}`);

  // manual step + double click guard
  const posA = await ev("return JSON.stringify(lab.objs.vessel.getPosition().toJSON());");
  await ev(`$('lab-step').click(); $('lab-step').click();`);
  await waitFor(`!lab.busy && lab.state.step === ${s3 + 1}`, 15000, "one step");
  await sleep(800);
  const s4 = await state("step");
  const posB = await ev("return JSON.stringify(lab.objs.vessel.getPosition().toJSON());");
  check("Step advances exactly one step (double click ignored) and moves the vessel marker",
    s4 === s3 + 1 && posA !== posB, `step ${s3} -> ${s4}`);
  const seqs = await ev("return lab.state.timeline.map(e=>e.seq);");
  check("timeline has no duplicate entries after pause/resume/step", new Set(seqs).size === seqs.length, `${seqs.length} entries`);

  // ---- 3. manual storm: + Storm, click the map, adjust with the slider ----
  await ev(`$('w-add-storm').click();`);
  check("+ Storm arms map placement", await ev("return lab.placing === 'storm' && !$('w-place-hint').classList.contains('hidden');"));
  const target = await ev("const a=lab.state.routes.active; return a[Math.floor(a.length*0.5)];");
  await ev(`google.maps.event.trigger(map, 'click', { latLng: new google.maps.LatLng(${target[0]}, ${target[1]}) });`);
  await waitFor("lab.state.weather.pending && lab.state.weather.pending.length === 1 && !lab.busy && lab.selected", 15000, "pending storm");
  await ev(`$('w-delta').value = '6'; $('w-delta').dispatchEvent(new Event('input')); $('w-delta').dispatchEvent(new Event('change'));`);
  await waitFor("!lab.busy && lab.state.weather.pending[0].delta_m === 6", 15000, "slider edit");
  check("map click creates a PENDING storm (routing not yet aware); slider edits it",
    await ev("return lab.state.weather.applied.length === 0 && lab.state.weather.version === 0 && !$('lab-weather-badge').classList.contains('hidden') && !$('weather-apply').disabled && !$('w-editor').classList.contains('hidden') && $('w-delta-v').textContent === '+6 m';"),
    `circles on map: ${await ev("return lab.objs.circles.length")}`);
  await shot("2-pending-storm");
  await ev(`$('weather-apply').click();`);
  await waitFor("lab.state.weather.version === 1 && !lab.busy", 30000, "apply");
  check("Apply now: storm applied, overlay re-rendered from applied field",
    await ev("return lab.state.weather.pending === null && lab.state.weather.applied.length === 1 && lab.objs.overlay && lab.objs.overlay.getUrl().endsWith('v=1');"),
    `legend max ${await ev("return lab.state.weather.overlay.legend_max_m")} m`);
  const before = await ev("return lab.state.routes.route_version;");
  await ev(`$('lab-step').click();`);
  await waitFor(`!lab.busy && lab.state.step === ${s4 + 1}`, 60000, "step after storm");
  const r = await ev(`const s=lab.state; const e=s.timeline.filter(x=>x.kind==='evaluation').pop();
    return {rv:s.routes.route_version, reroutes:s.reroutes.length, decision:e.detail.decision, msg:e.message, triggers:e.detail.triggers,
            r1:s.reroutes[0]||null, activeStart:s.routes.active[0], markers:lab.objs.rMarkers.length,
            path0: lab.objs.active.getPath().getAt(0).toJSON()};`);
  check("backend rerouted around the manual storm (R1 adopted)", r.rv === before + 1 && r.reroutes === 1 && r.decision === "adopted", `${r.msg} | triggers: ${r.triggers.join('; ')}`);
  check("map: R1 marker drawn and active route starts at the reroute position",
    r.markers === 1 && r.r1 && r.activeStart[0] === r.r1.position[0] && Math.abs(r.path0.lat - r.r1.position[0]) < 1e-6);
  check("map keeps initial route and sailed track alongside the new active route",
    await ev("return lab.objs.initial.getPath().getLength() > 10 && lab.objs.track.getPath().getLength() > 10 && lab.objs.active.getPath().getLength() > 2;"));
  const geo = await ev(`const s=lab.state; const e=s.timeline.find(x=>x.seq===s.reroutes[0].seq);
    return {prev0: s.routes.previous ? s.routes.previous[0] : null, prevLen: lab.objs.prev.getPath().getLength(),
            pos: s.reroutes[0].position, cause: e.detail.cause, shift: e.detail.corridor_shift_km, turn: e.detail.heading_change_deg};`);
  check("replaced plan drawn (amber) from the reroute point, separate from the new plan",
    !!geo.prev0 && geo.prev0[0] === geo.pos[0] && geo.prev0[1] === geo.pos[1] && geo.prevLen > 2,
    `cause: ${geo.cause}; corridor shift ${geo.shift} km; turn ${geo.turn} deg`);
  check("substantial storm -> substantial detour (corridor shift > 50 km)", geo.shift > 50, `${geo.shift} km`);
  await ev(`window.__samples = []; window.__sampler = setInterval(() => { if (lab.objs.vessel) __samples.push(lab.objs.vessel.getPosition().toJSON()); }, 15);
    $('lab-speed').value = '1500'; $('lab-step').click();`);
  await waitFor(`!lab.busy && !lab.anim && lab.state.step === ${s4 + 2}`, 60000, "animated step");
  const tp = await ev(`clearInterval(__sampler);
    const line = new google.maps.Polyline({ path: lab.state.track.map(p => ({ lat: p[0], lng: p[1] })) });
    const off = __samples.filter(p => !google.maps.geometry.poly.isLocationOnEdge(new google.maps.LatLng(p.lat, p.lng), line, 0.02));
    const last = lab.objs.vessel.getPosition().toJSON(), end = lab.state.vessel.position;
    return { n: __samples.length, off: off.length,
             distinct: new Set(__samples.map(p => p.lat.toFixed(4) + ',' + p.lng.toFixed(4))).size,
             endOk: Math.abs(last.lat - end[0]) < 1e-6 && Math.abs(last.lng - end[1]) < 1e-6 };`);
  check("vessel moves along the sailed track, never off it (no teleport)", tp.off === 0 && tp.distinct > 3 && tp.endOk,
    `${tp.n} samples, ${tp.distinct} distinct positions, ${tp.off} off-track, ends on backend position: ${tp.endOk}`);
  await ev(`$('lab-speed').value = '150'; $('lab-safety').checked = true; $('lab-safety').dispatchEvent(new Event('change'));`);
  await sleep(800);
  check("safety overlay (water too shallow for the vessel) can be shown",
    await ev("return !!lab.objs.safety && lab.objs.safety.getMap() === map && /safety_image\\?vessel=/.test(lab.objs.safety.get('src'));"));
  await shot("3b-after-reroute-safety");
  await ev(`$('lab-safety').checked = false; $('lab-safety').dispatchEvent(new Event('change'));`);
  await ev("if ($('fp-events').classList.contains('collapsed')) $('fp-events').querySelector('.fp-collapse').click();");
  await sleep(300);
  const evp = await ev("return $('lab-ev-current').innerText.replace(/\\n+/g,' | ');");
  await ev("$('ev-details-btn').click();");
  await sleep(300);
  check("Route changes panel: R1 summary with cause; Details reveal triggers and plan comparison",
    /R1 · Route changed/.test(evp) && /waves|costlier|re-check/i.test(evp) &&
    await ev("const t=$('lab-ev-current').innerText; return /Triggers/.test(t) && /better/.test(t) && /Detour/.test(t);"), evp.slice(0, 160));
  await ev("$('ev-log').open = true;");
  await sleep(200);
  check("full decision log still available (collapsed by default) and lists R1",
    await ev("return [...document.querySelectorAll('#lab-timeline .tl.adopted')].some(t => /R1/.test(t.innerText));"));
  await ev("$('ev-log').open = false;");
  await shot("3-reroute-R1");

  // edit: select disturbance, move via the Position section -> pending; discard
  await ev(`lab.selected = null; document.querySelector('#lab-dist-list .dist[data-id]').click();`);
  await ev(`document.querySelector('.w-adv').open = true; $('dist-lat').value = String(Number($('dist-lat').value) + 1); $('w-move').click();`);
  await waitFor("lab.state.weather.pending && !lab.busy", 15000, "moved pending");
  check("moving a disturbance creates a pending change (timeline: moved)",
    await ev("return /moved to/.test(lab.state.timeline[lab.state.timeline.length-1].message);"));
  await ev(`$('weather-discard').click();`);
  await waitFor("lab.state.weather.pending === null && !lab.busy", 15000, "discard");
  check("discard pending restores the applied weather list", await ev("return lab.state.weather.applied.length === 1;"));

  // invalid input
  await ev(`document.querySelector('#lab-dist-list .dist[data-id]').click(); if (!lab.selected) document.querySelector('#lab-dist-list .dist[data-id]').click();`);
  await ev(`$('w-delta').value = '0'; $('w-delta').dispatchEvent(new Event('change'));`);
  await waitFor("!lab.busy && lab.state.weather.pending", 15000, "zero snap");
  check("wave change cannot be set to 0 (snaps to ±0.5 m instead of sending an invalid value)",
    await ev("return Math.abs(lab.state.weather.pending.find(d=>d.id===lab.selected).delta_m) === 0.5;"));
  await ev(`$('weather-discard').click();`);
  await waitFor("lab.state.weather.pending === null && !lab.busy", 15000, "discard 2");
  await ev(`document.querySelector('.w-adv').open = true; $('dist-lat').value='45'; $('w-move').click();`);
  await sleep(300);
  check("out-of-region latitude rejected", await ev("return /Latitude must be/.test($('toast').textContent);"), await ev("return $('toast').textContent"));
  const httpBefore = httpErrors.length;
  await ev(`lab.limits.lat = [-90, 90]; $('dist-lat').value = '45'; $('w-move').click();`);   // bypass client check -> server must reject
  await waitFor(`!lab.busy`, 10000, "server validation");
  await sleep(500);
  check("server rejects invalid disturbance (400) and state stays intact",
    httpErrors.length === httpBefore + 1 && httpErrors[httpErrors.length - 1].startsWith("400") &&
    await ev("return lab.state.weather.pending === null && lab.state.weather.applied.length === 1;"),
    httpErrors[httpErrors.length - 1]);
  await ev(`lab.limits.lat = [0, 27]; $('dist-lat').value='12';`);

  // reset (two-click)
  await ev(`$('lab-reset').click();`);
  check("reset asks for confirmation first", await ev("return $('lab-reset').textContent.includes('Confirm');"));
  await ev(`$('lab-reset').click();`);
  await waitFor("lab.state.step === 0 && !lab.busy", 30000, "reset");
  check("reset: step 0, no reroutes, no weather, map cleared to initial",
    await ev("const s=lab.state; return s.metrics.reroutes===0 && s.weather.applied.length===0 && s.weather.pending===null && lab.objs.rMarkers.length===0 && lab.objs.circles.length===0 && s.timeline[s.timeline.length-1].kind==='reset' && s.track.length===1;"));

  // small disturbance must not cause rerouting / oscillation
  const mid = await ev("const a=lab.state.routes.active; return a[Math.floor(a.length*0.5)];");
  await ev(`labEditWeather([{ lat: ${mid[0]}, lon: ${mid[1]}, radius_km: 25, delta_m: 0.4 }]);`);
  await waitFor("lab.state.weather.pending && !lab.busy", 15000, "small pending");
  await ev(`$('weather-apply').click();`);
  await waitFor("lab.state.weather.version === 1 && !lab.busy", 30000, "small apply");
  for (let i = 0; i < 6; i++) { await ev(`$('lab-step').click();`); await waitFor(`!lab.busy && !lab.stepping && lab.state.step === ${i + 1}`, 30000, "small step"); }
  check("small weather change: no reroute, plan unchanged over 6 steps (no oscillation)",
    await ev("return lab.state.metrics.reroutes === 0 && lab.state.routes.route_version === 0;"),
    await ev("return lab.state.timeline.filter(e=>e.kind==='evaluation' && e.detail.decision!=='no_trigger').map(e=>e.detail.decision+' '+(e.detail.gain_pct??'')).join(', ') || 'no triggered evaluation';"));

  // + Calm and Remove
  await ev(`$('w-add-calm').click();`);
  await ev(`google.maps.event.trigger(map, 'click', { latLng: new google.maps.LatLng(${mid[0] - 2}, ${mid[1] - 2}) });`);
  await waitFor("!lab.busy && lab.state.weather.pending && lab.state.weather.pending.some(d => d.delta_m < 0)", 15000, "calm");
  const calmId = await ev("return lab.state.weather.pending.find(d => d.delta_m < 0).id;");
  check("+ Calm places a calm patch (negative wave change), selected for editing",
    await ev(`return lab.selected === '${calmId}' && /Calm/.test($('lab-dist-list').innerText);`));
  await ev(`$('dist-remove').click();`);
  await waitFor(`!lab.busy && !(lab.state.weather.pending || []).some(d => d.id === '${calmId}')`, 15000, "remove");
  check("Remove deletes the selected disturbance (as a pending change)", true);
  await ev(`$('weather-discard').click();`);
  await waitFor("!lab.busy && lab.state.weather.pending === null", 15000, "discard 3");

  // ---- 4. preset to completion ----
  await ev(`$('lab-preset').value='storm_ahead'; $('lab-preset').dispatchEvent(new Event('change')); $('lab-create').click();`);
  await waitFor("lab.state && lab.state.setup.preset === 'storm_ahead' && lab.state.step === 0 && !lab.busy", 30000, "preset voyage");
  await ev(`$('lab-start').click();`);
  await waitFor("lab.state.status === 'completed' && !lab.loop", 240000, "completion");
  const fin = await ev(`const s=lab.state; return {r:s.metrics.reroutes, h:s.metrics.sailed_hours, nh:s.comparison_no_rerouting.sailed_hours, last:s.timeline[s.timeline.length-1].message, start:$('lab-start').disabled, step:$('lab-step').disabled};`);
  check("preset 'storm_ahead' runs to completion; controls disabled at the end",
    fin.r >= 1 && fin.start && fin.step, `${fin.r} reroute(s), ${fin.h} h vs ${fin.nh} h without rerouting | ${fin.last.slice(0, 100)}`);
  await shot("4-preset-complete");

  // ---- 5. layout (default positions; every panel expanded = worst case) ----
  await ev("ui.panels = {}; uiSave(); FPANELS().forEach(p => setCollapsed(p, false, false)); layoutPanels();");
  await sleep(500);
  for (const [w, h] of [[1500, 950], [1280, 800], [900, 700]]) {
    await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
    await sleep(900);
    const L = await ev(LAYOUT);
    check(`${w}x${h}: all ${L.n} panels on screen, no overlaps, top bar and map controls clear, no page overflow`,
      L.bad.length === 0 && !L.overflow, L.bad.join("; "));
    await shot(`5-layout-${w}`);
  }
  check("no stale info window from an earlier voyage", await ev("return !document.querySelector('.gm-style-iw');"));
  await send("Emulation.clearDeviceMetricsOverride");
  await ev("FPANELS().forEach(p => setCollapsed(p, p.id === 'fp-events' || p.id === 'fp-key', false)); layoutPanels();");

  // ---- 5b. infeasible voyage ----
  const keepSid = await ev("return lab.sid;");
  await ev(`$('vessel').value = 'Crude Oil Tanker (VLCC)'; $('vessel').dispatchEvent(new Event('change'));
    $('origin').value = 'Kandla (Gujarat)'; $('dest').value = 'Cochin (Kerala)'; $('lab-preset').value = 'none'; $('lab-create').click();`);
  await waitFor("!lab.busy && /No safe route/.test($('toast').textContent)", 30000, "infeasible message");
  check("infeasible voyage (VLCC through 16 m water): clear message, previous session kept",
    await ev(`return /required 24.6 m/.test($('toast').textContent) && lab.sid === '${keepSid}';`),
    await ev("return $('toast').textContent;"));

  // ---- 6. back to route planning ----
  await ev(`document.querySelector('#mode button[data-val=route]').click();`);
  check("leaving lab clears its map objects, hides lab panels and returns the shared fields",
    await ev("return lab.objs.track === null && lab.objs.circles.length === 0 && FPANELS().every(p => p.offsetParent === null) && $('voyage-fields').parentNode === $('side-panel');"));
  await ev(`$('go').click();`);
  await waitFor("!$('results').classList.contains('hidden') && document.querySelectorAll('#cards .card').length === 2", 60000, "route infeasible");
  check("route planning shows the infeasibility reason on both cards",
    await ev("return [...document.querySelectorAll('#cards .card')].every(c => /no safe route/i.test(c.innerText) && /24.6 m/.test(c.innerText));"));
  await ev(`$('vessel').value = 'General Cargo'; $('vessel').dispatchEvent(new Event('change'));
    $('origin').value = 'Cochin (Kerala)'; $('dest').value = 'Dubai / Jebel Ali (UAE)'; $('go').click();`);
  await waitFor("!$('results').classList.contains('hidden') && document.querySelectorAll('#cards .card .metrics').length === 2", 60000, "route again");
  check("route planning works again after the lab", true);
  await ev(`document.querySelector('#mode button[data-val=sim]').click(); $('sim-scenario').value = 'adverse'; $('simulate').click();`);
  await waitFor("$('results-title').textContent === 'Simulated voyage' && !$('results').classList.contains('hidden')", 90000, "replay");
  check("voyage replay mode still works", await ev("return simData && simData.dynamic.reroutes >= 1;"),
    await ev("return $('verdict').textContent;"));
  await ev(`document.querySelector('#mode button[data-val=lab]').click();`);
  check("heatmap present after leaving and re-entering the lab",
    await ev("return !!lab.objs.overlay && lab.objs.overlay.getMap() === map && !(waveOverlay && waveOverlay.getMap());"));
  check("re-entering lab restores the session", await ev("return lab.state && lab.objs.track && lab.objs.track.getPath().getLength() > 10;"));
  await shot("6-reenter-lab");
} catch (e) {
  check("script error", false, e.message);
  try { await shot("failure"); } catch {}
} finally {
  const deliberate = httpErrors.filter((h) => !h.startsWith("400 /api/sim/sessions/") && h !== "422 /api/sim/sessions" && !h.includes("favicon"));
  console.log(`\nHTTP >= 400: ${httpErrors.length ? httpErrors.join(" | ") : "none"}`);
  console.log(`unexpected HTTP errors: ${deliberate.length ? deliberate.join(" | ") : "none"}`);
  console.log(`failed loads: ${failed.length ? failed.join(" | ") : "none"}`);
  console.log(`console errors / exceptions: ${consoleIssues.length ? "\n  " + consoleIssues.join("\n  ") : "none"}`);
  writeFileSync(`${OUT}/api_calls.json`, JSON.stringify([...apiCalls].sort(), null, 1));
  const exc = consoleIssues.filter((x) => x.startsWith("EXCEPTION"));
  check("no uncaught JavaScript exceptions", exc.length === 0, exc.length ? exc.join(" | ") : "");
  const nf = results.filter((x) => x[0] === "FAIL").length;
  console.log(`\n${results.length - nf}/${results.length} checks passed`);
  chrome.kill(); process.exit(0);
}
