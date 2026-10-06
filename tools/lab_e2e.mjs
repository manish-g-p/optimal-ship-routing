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
  check("lab mode: lab panel + control bar visible, route controls hidden",
    await ev("return !$('lab-panel').classList.contains('hidden') && !$('lab-bar').classList.contains('hidden') && $('go').classList.contains('hidden') && $('results').classList.contains('hidden');"));
  check("controls before a voyage: Step/Pause/Reset disabled",
    await ev("return $('lab-step').disabled && $('lab-pause').disabled && $('lab-reset').disabled;"));
  await ev(`$('vessel').value='General Cargo'; $('lab-preset').value='none'; $('lab-speed').value='150';`);

  // start -> runs automatically
  await ev(`$('lab-start').click();`);
  await waitFor("lab.state && lab.state.step >= 3", 60000, "auto steps");
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

  // ---- 3. manual storm by map click ----
  await ev(`$('dist-delta').value='6'; $('dist-radius').value='150'; $('dist-place').click();`);
  const target = await ev("const a=lab.state.routes.active; return a[Math.floor(a.length*0.5)];");
  await ev(`google.maps.event.trigger(map, 'click', { latLng: new google.maps.LatLng(${target[0]}, ${target[1]}) });`);
  await waitFor("lab.state.weather.pending && lab.state.weather.pending.length === 1 && !lab.busy", 15000, "pending storm");
  check("map click creates a PENDING storm (routing not yet aware)",
    await ev("return lab.state.weather.applied.length === 0 && lab.state.weather.version === 0 && !$('lab-weather-badge').classList.contains('hidden') && !$('weather-apply').disabled;"),
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
  await ev(`[...document.querySelectorAll('.tl.adopted')].pop().click();`);
  await sleep(500);
  check("timeline R1 entry opens decision detail (cost, alternative, gain, triggers)",
    await ev("const t=document.querySelector('.tl.adopted.open .detail'); return !!t && /gain/.test(t.innerText) && /alternative/.test(t.innerText);"),
    (await ev("const t=document.querySelector('.tl.adopted.open'); return t ? t.innerText.replace(/\\n+/g,' ').slice(0,200) : '';")));
  await shot("3-reroute-R1");

  // edit: select disturbance, move via form -> pending; discard
  await ev(`document.querySelector('#lab-dist-list .dist[data-id]').click();`);
  await ev(`$('dist-lat').value = String(Number($('dist-lat').value) + 1); $('dist-update').click();`);
  await waitFor("lab.state.weather.pending && !lab.busy", 15000, "moved pending");
  check("moving a disturbance creates a pending change (timeline: moved)",
    await ev("return /moved to/.test(lab.state.timeline[lab.state.timeline.length-1].message);"));
  await ev(`$('weather-discard').click();`);
  await waitFor("lab.state.weather.pending === null && !lab.busy", 15000, "discard");
  check("discard pending restores the applied weather list", await ev("return lab.state.weather.applied.length === 1;"));

  // invalid input
  await ev(`$('dist-delta').value='0'; $('dist-lat').value='12'; $('dist-lon').value='66'; $('dist-add').click();`);
  await sleep(300);
  check("invalid Δ=0 rejected in the browser with a message", await ev("return !$('toast').classList.contains('hidden') && /must not be 0/.test($('toast').textContent);"), await ev("return $('toast').textContent + ' | hidden=' + $('toast').classList.contains('hidden');"));
  await ev(`$('dist-delta').value='5'; $('dist-lat').value='45'; $('dist-add').click();`);
  await sleep(300);
  check("out-of-region latitude rejected", await ev("return /lat must be/.test($('toast').textContent);"), await ev("return $('toast').textContent"));
  const httpBefore = httpErrors.length;
  await ev(`lab.limits.lat = [-90, 90]; $('dist-add').click();`);   // bypass client check -> server must reject
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

  // ---- 4. preset to completion ----
  await ev(`$('lab-preset').value='storm_ahead'; $('lab-preset').dispatchEvent(new Event('change')); $('lab-create').click();`);
  await waitFor("lab.state && lab.state.setup.preset === 'storm_ahead' && lab.state.step === 0 && !lab.busy", 30000, "preset voyage");
  await ev(`$('lab-start').click();`);
  await waitFor("lab.state.status === 'completed' && !lab.loop", 240000, "completion");
  const fin = await ev(`const s=lab.state; return {r:s.metrics.reroutes, h:s.metrics.sailed_hours, nh:s.comparison_no_rerouting.sailed_hours, last:s.timeline[s.timeline.length-1].message, start:$('lab-start').disabled, step:$('lab-step').disabled};`);
  check("preset 'storm_ahead' runs to completion; controls disabled at the end",
    fin.r >= 1 && fin.start && fin.step, `${fin.r} reroute(s), ${fin.h} h vs ${fin.nh} h without rerouting | ${fin.last.slice(0, 100)}`);
  await shot("4-preset-complete");

  // ---- 5. layout ----
  const ov0 = await ev(`const r=(id)=>document.querySelector(id).getBoundingClientRect();
    const hit=(p,q)=>!(p.right<=q.left||q.right<=p.left||p.bottom<=q.top||q.bottom<=p.top);
    const a=r('.panel-left'), b=r('#lab-panel'), c=r('#lab-bar'), l=r('#legend');
    return !hit(a,b)&&!hit(a,c)&&!hit(b,c)&&!hit(l,c)&&!hit(l,b);`);
  check("1500x950: panels, control bar and legend do not overlap", ov0);
  await send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
  await sleep(800);
  const overlap = await ev(`const r=(id)=>document.querySelector(id).getBoundingClientRect();
    const a=r('.panel-left'), b=r('#lab-panel'), c=r('#lab-bar'), l=r('#legend');
    const hit=(p,q)=>!(p.right<=q.left||q.right<=p.left||p.bottom<=q.top||q.bottom<=p.top);
    return {lb:hit(a,b), lc:hit(a,c), bc:hit(b,c), legBar:hit(l,c), legPanel:hit(l,b), barVisible: c.bottom <= innerHeight && c.top >= 0, mapFree: b.left - a.right};`);
  check("1280x800: panels, control bar and legend do not overlap; bar on screen", !overlap.lb && !overlap.lc && !overlap.bc && !overlap.legBar && !overlap.legPanel && overlap.barVisible, JSON.stringify(overlap));
  check("no stale info window from an earlier voyage", await ev("return !document.querySelector('.gm-style-iw');"));
  await shot("5-layout-1280");
  await send("Emulation.clearDeviceMetricsOverride");

  // ---- 6. back to route planning ----
  await ev(`document.querySelector('#mode button[data-val=route]').click();`);
  check("leaving lab clears its map objects and hides lab UI",
    await ev("return lab.objs.track === null && lab.objs.circles.length === 0 && $('lab-panel').classList.contains('hidden') && $('lab-bar').classList.contains('hidden');"));
  await ev(`$('go').click();`);
  await waitFor("!$('results').classList.contains('hidden') && document.querySelectorAll('#cards .card').length === 2", 60000, "route again");
  check("route planning works again after the lab", true);
  await ev(`document.querySelector('#mode button[data-val=lab]').click();`);
  check("re-entering lab restores the session", await ev("return lab.state && lab.objs.track && lab.objs.track.getPath().getLength() > 10;"));
  await shot("6-reenter-lab");
} catch (e) {
  check("script error", false, e.message);
  try { await shot("failure"); } catch {}
} finally {
  const deliberate = httpErrors.filter((h) => !h.startsWith("400 /api/sim/sessions/") && !h.includes("favicon"));
  console.log(`\nHTTP >= 400: ${httpErrors.length ? httpErrors.join(" | ") : "none"}`);
  console.log(`unexpected HTTP errors: ${deliberate.length ? deliberate.join(" | ") : "none"}`);
  console.log(`failed loads: ${failed.length ? failed.join(" | ") : "none"}`);
  console.log(`console errors / exceptions: ${consoleIssues.length ? "\n  " + consoleIssues.join("\n  ") : "none"}`);
  const nf = results.filter((x) => x[0] === "FAIL").length;
  console.log(`\n${results.length - nf}/${results.length} checks passed`);
  chrome.kill(); process.exit(0);
}
