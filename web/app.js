/* Nautilus front-end logic */
let map, waveOverlay = null, info = null;
let routeLines = [], routeMarkers = [], wpMarkers = [], flowTimer = null;
let META = null, scenario = "typical";

const DARK_STYLE = [
  { elementType: "geometry", stylers: [{ color: "#0b1a2b" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#7d93b0" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#0b1a2b" }] },
  { featureType: "water", elementType: "geometry",
    stylers: [{ color: "#08243d" }] },
  { featureType: "landscape", elementType: "geometry",
    stylers: [{ color: "#0f2033" }] },
  { featureType: "administrative", elementType: "geometry.stroke",
    stylers: [{ color: "#1c3350" }] },
  { featureType: "road", stylers: [{ visibility: "off" }] },
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  { featureType: "transit", stylers: [{ visibility: "off" }] },
];

const $ = (id) => document.getElementById(id);

/* Google Maps calls this if the API key is rejected (bad key, referrer
   restriction, or billing not enabled). */
window.__gmAuthFailed = false;
window.gm_authFailure = function () {
  window.__gmAuthFailed = true;
  toast("Google Maps auth failed — check the key's website restriction " +
        "(add http://localhost:8000/*) and that billing is enabled.");
};

let toastTimer = null;
function toast(msg) {
  const t = $("toast");
  t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toastTimer);                 // an older timer must not hide this one
  toastTimer = setTimeout(() => t.classList.add("hidden"), 5000);
}
function loading(on, text) {
  $("loading-text").textContent = text || "Computing optimal route…";
  $("loading").classList.toggle("hidden", !on);
}

/* Google Maps entry point */
window.initApp = async function () {
  const c = { lat: 13.5, lng: 80 };
  map = new google.maps.Map($("map"), {
    center: c, zoom: 5, styles: DARK_STYLE,
    mapTypeControl: true, streetViewControl: false, fullscreenControl: false,
    mapTypeControlOptions: {
      style: google.maps.MapTypeControlStyle.HORIZONTAL_BAR,
      mapTypeIds: ["roadmap", "hybrid"],
      position: google.maps.ControlPosition.TOP_RIGHT,
    },
    zoomControl: true,
    zoomControlOptions: { position: google.maps.ControlPosition.RIGHT_CENTER },
  });
  info = new google.maps.InfoWindow();
  await loadMeta();
  bindUI();
  loadWeather();
};

async function loadMeta() {
  const r = await fetch("/api/meta");
  META = await r.json();
  const vsel = $("vessel"), osel = $("origin"), dsel = $("dest");
  META.vessels.forEach((v) => vsel.add(new Option(v.name, v.name)));
  META.ports.forEach((p) => {
    osel.add(new Option(p.name, p.name));
    dsel.add(new Option(p.name, p.name));
  });
  vsel.value = "Container Ship";
  osel.value = "Cochin (Kerala)";
  dsel.value = "Dubai / Jebel Ali (UAE)";
  updateVesselInfo();
  initSimControls();
}

function updateVesselInfo() {
  const v = META.vessels.find((x) => x.name === $("vessel").value);
  $("vessel-info").textContent =
    `Service ${v.speed} kn · draft ${v.draft} m · length ${v.length} m`;
}

function bindUI() {
  $("vessel").addEventListener("change", updateVesselInfo);
  document.querySelectorAll("#scenario button").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#scenario button")
        .forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      scenario = b.dataset.val;
      loadWeather();
    });
  });
  $("use-waves").addEventListener("change", () => {
    if (waveOverlay) waveOverlay.setMap($("use-waves").checked ? map : null);
  });
  $("go").addEventListener("click", findRoute);
  document.querySelectorAll("#mode button").forEach((b) => {
    b.addEventListener("click", () => setMode(b.dataset.val));
  });
  $("simulate").addEventListener("click", runSimulation);
  bindLab();
}

async function loadWeather() {
  if (waveOverlay) { waveOverlay.setMap(null); waveOverlay = null; }
  $("legend").classList.add("hidden");
  const live = scenario === "live";
  if (live) loading(true, "Fetching live marine weather…");
  try {
    const r = await fetch(`/api/weather?scenario=${scenario}`);
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    const b = d.bounds;
    const bounds = { north: b.north, south: b.south, east: b.east, west: b.west };
    const url = `/api/weather_image?scenario=${scenario}&t=${Date.now()}`;
    waveOverlay = new google.maps.GroundOverlay(url, bounds, { opacity: 0.6 });
    waveOverlay.setMap($("use-waves").checked ? map : null);
    $("legend-max").textContent = d.max + " m";
    $("legend").classList.remove("hidden");
    if (mode === "lab") labSyncOverlay();    // lab shows its own weather field
  } catch (e) {
    toast("Weather: " + e.message);
  } finally {
    if (live) loading(false);
  }
}

function clearRoutes() {
  routeLines.forEach((l) => l.setMap(null)); routeLines = [];
  routeMarkers.forEach((m) => m.setMap(null)); routeMarkers = [];
  wpMarkers.forEach((m) => m.setMap(null)); wpMarkers = [];
  if (flowTimer) { clearInterval(flowTimer); flowTimer = null; }
}

async function findRoute() {
  const algorithms = [];
  if ($("use-dijkstra").checked) algorithms.push("dijkstra");
  if ($("use-astar").checked) algorithms.push("astar");
  if (!algorithms.length) return toast("Pick at least one algorithm.");
  if ($("origin").value === $("dest").value)
    return toast("Origin and destination are the same.");

  loading(true, scenario === "live"
    ? "Fetching live weather + routing…" : "Computing optimal route…");
  $("status").textContent = "";
  try {
    const r = await fetch("/api/route", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin: $("origin").value, dest: $("dest").value,
        vessel: $("vessel").value, scenario,
        use_ml: $("use-ml").checked, algorithms,
      }),
    });
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    drawResults(d);
  } catch (e) {
    toast("Routing failed: " + e.message);
  } finally {
    loading(false);
  }
}

/* Chaikin corner-cutting: turns the blocky grid path into a smooth,
   realistic-looking ship track (purely visual; stats use the real path). */
function smoothPath(pts, iterations) {
  let p = pts;
  for (let it = 0; it < iterations; it++) {
    if (p.length < 3) break;
    const out = [p[0]];
    for (let i = 0; i < p.length - 1; i++) {
      const a = p[i], b = p[i + 1];
      out.push({ lat: a.lat * 0.75 + b.lat * 0.25, lng: a.lng * 0.75 + b.lng * 0.25 });
      out.push({ lat: a.lat * 0.25 + b.lat * 0.75, lng: a.lng * 0.25 + b.lng * 0.75 });
    }
    out.push(p[p.length - 1]);
    p = out;
  }
  return p;
}

function drawResults(d) {
  clearRoutes();
  const bounds = new google.maps.LatLngBounds();

  const drawLine = (res, color, glow, animate) => {
    if (!res || !res.found) return;
    const raw = res.path.map((p) => ({ lat: p[0], lng: p[1] }));
    const path = smoothPath(raw, 3);
    if (glow) {
      routeLines.push(new google.maps.Polyline({
        path, map, geodesic: true, strokeColor: color,
        strokeOpacity: 0.25, strokeWeight: 11,
      }));
    }
    const line = new google.maps.Polyline({
      path, map, geodesic: true, strokeColor: color,
      strokeOpacity: 0.95, strokeWeight: 4,
    });
    routeLines.push(line);
    path.forEach((p) => bounds.extend(p));
    if (animate) animateFlow(line, color);
  };

  drawLine(d.dijkstra, "#38bdf8", false, false);
  drawLine(d.astar, "#f43f5e", true, true);

  // Weather tooltips along the proposed (or available) route.
  const wpSrc = (d.astar && d.astar.found) ? d.astar
    : (d.dijkstra && d.dijkstra.found ? d.dijkstra : null);
  if (wpSrc) drawWaypoints(wpSrc.waypoints);

  // Endpoint markers.
  const vname = d.vessel || "";
  addMarker(d.origin.lat, d.origin.lon,
    "Origin: " + d.origin.name, "#34d399", SHIP_PATH, vname);
  addMarker(d.dest.lat, d.dest.lon,
    "Destination: " + d.dest.name, "#f43f5e", ANCHOR_PATH, vname);
  bounds.extend({ lat: d.origin.lat, lng: d.origin.lon });
  bounds.extend({ lat: d.dest.lat, lng: d.dest.lon });
  map.fitBounds(bounds, 80);

  renderCards(d);
}

/* A circular badge with a white ship glyph, as an SVG marker icon. */
const SHIP_PATH = "M20 21c-1.39 0-2.78-.47-4-1.32-2.44 1.71-5.56 1.71-8 0C6.78 " +
  "20.53 5.39 21 4 21H2v2h2c1.38 0 2.74-.35 4-.99 2.52 1.29 5.48 1.29 8 0 " +
  "1.26.65 2.62.99 4 .99h2v-2h-2zM3.95 19H4c1.6 0 3.02-.88 4-2 .98 1.12 2.4 " +
  "2 4 2s3.02-.88 4-2c.98 1.12 2.4 2 4 2h.05l1.89-6.68c.08-.26.06-.54-.06-.78" +
  "s-.34-.42-.6-.5L20 10.62V6c0-1.1-.9-2-2-2h-3V1H9v3H6c-1.1 0-2 .9-2 2v4.62l" +
  "-1.29.42c-.26.08-.48.26-.6.5s-.15.52-.06.78L3.95 19zM6 6h12v3.97L12 8 6 " +
  "9.97V6z";

const ANCHOR_PATH = "M17 15l1.55 1.55c-.96 1.69-3.66 3.61-6.55 3.94V10.9c1.16" +
  "-.41 2-1.52 2-2.82 0-1.65-1.35-3-3-3S8 6.43 8 8.08c0 1.3.84 2.4 2 2.82v9.59" +
  "c-2.89-.33-5.59-2.25-6.55-3.94L5 15l-4-3v9l1.24-1.24C4.01 21.11 7.24 23 12 " +
  "23s7.99-1.89 9.76-3.24L23 21v-9l-4 3zM12 6.5c.83 0 1.5.67 1.5 1.5s-.67 1.5" +
  "-1.5 1.5-1.5-.67-1.5-1.5.67-1.5 1.5-1.5z";

function badgeIcon(pathData, color) {
  const svg =
    "<svg xmlns='http://www.w3.org/2000/svg' width='48' height='48' " +
    "viewBox='0 0 48 48'><defs><filter id='sh' x='-40%' y='-40%' " +
    "width='180%' height='180%'><feDropShadow dx='0' dy='1.5' " +
    "stdDeviation='1.6' flood-color='#000' flood-opacity='0.5'/></filter>" +
    "</defs><circle cx='24' cy='24' r='17' fill='" + color +
    "' stroke='#ffffff' stroke-width='3' filter='url(#sh)'/>" +
    "<g transform='translate(11,11)' fill='#ffffff'><path d='" + pathData +
    "'/></g></svg>";
  return {
    url: "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(svg),
    scaledSize: new google.maps.Size(48, 48),
    anchor: new google.maps.Point(24, 24),
    labelOrigin: new google.maps.Point(24, 61),   // label sits under badge
  };
}

function addMarker(lat, lng, title, color, pathData, labelText) {
  const m = new google.maps.Marker({
    position: { lat, lng }, map, title, zIndex: 999,
    icon: badgeIcon(pathData, color),
    label: labelText ? {
      text: labelText, className: "map-label", color: "#ffffff",
      fontSize: "11px", fontWeight: "600",
    } : undefined,
  });
  routeMarkers.push(m);
}

function drawWaypoints(wps) {
  wps.forEach((w) => {
    const color = w.swh < 1.5 ? "#34d399" : w.swh < 3 ? "#fbbf24" : "#f43f5e";
    const m = new google.maps.Marker({
      position: { lat: w.lat, lng: w.lon }, map,
      icon: { path: google.maps.SymbolPath.CIRCLE, scale: 4.5,
        fillColor: color, fillOpacity: 0.95, strokeColor: "#0b1220",
        strokeWeight: 1 },
    });
    m.addListener("click", () => {
      info.setContent(
        `<div class="wx-pop"><b>Wave conditions</b>` +
        `Height: ${w.swh} m<br>Period: ${w.mwp} s<br>From: ${w.mwd}°</div>`);
      info.open(map, m);
    });
    wpMarkers.push(m);
  });
}

function animateFlow(line, color) {
  const icons = [{
    icon: { path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW, scale: 3,
      strokeColor: "#fff", fillColor: color, fillOpacity: 1 },
    offset: "0%",
  }];
  line.set("icons", icons);
  let off = 0;
  flowTimer = setInterval(() => {
    off = (off + 1) % 200;
    icons[0].offset = (off / 2) + "%";
    line.set("icons", icons);
  }, 60);
}

function fmt(n) { return n.toLocaleString(undefined, { maximumFractionDigits: 0 }); }

function card(name, tag, cls, res) {
  if (!res || !res.found)
    return `<div class="card ${cls}"><div class="card-title"><b>${name}</b>
      <span>${tag}</span></div><div class="metric"><div class="v">—</div>
      <div class="k">no safe route</div></div></div>`;
  return `<div class="card ${cls}">
    <div class="card-title"><b>${name}</b><span>${tag}</span></div>
    <div class="metrics">
      <div class="metric"><div class="v">${fmt(res.distance_km)}</div><div class="k">km</div></div>
      <div class="metric"><div class="v">${fmt(res.time_hours)}</div><div class="k">${res.time_basis === "ml_speed" ? "est. hours (ML)" : "est. hours"}</div></div>
      <div class="metric"><div class="v">${res.max_wave_m}</div><div class="k">max wave m</div></div>
      <div class="metric"><div class="v">${res.min_coast_km}</div><div class="k">min coast km</div></div>
      <div class="metric"><div class="v">${fmt(res.expanded)}</div><div class="k">cells explored</div></div>
      <div class="metric"><div class="v">${(res.time_hours/24).toFixed(1)}</div><div class="k">days</div></div>
    </div></div>`;
}

function renderCards(d) {
  $("results-title").textContent = "Route comparison";
  $("sim-extra").classList.add("hidden");
  let html = "";
  if (d.dijkstra) html += card("Dijkstra", "traditional", "dijkstra", d.dijkstra);
  if (d.astar) html += card("Weather-aware A*", "proposed", "astar", d.astar);
  $("cards").innerHTML = html;

  let verdict = "";
  if (d.dijkstra && d.astar && d.dijkstra.found && d.astar.found) {
    const dd = d.astar.distance_km - d.dijkstra.distance_km;
    const wd = d.dijkstra.max_wave_m - d.astar.max_wave_m;
    const eff = Math.round(100 * (1 - d.astar.expanded / d.dijkstra.expanded));
    if (Math.abs(dd) < 1 && Math.abs(wd) < 0.05) {
      verdict = `For this vessel and sea state, the shortest route is already ` +
        `the safest. A* reached the same route while exploring ${eff}% fewer cells.`;
    } else {
      verdict = `A* trades ${dd >= 0 ? "+" : ""}${fmt(dd)} km to cut peak waves ` +
        `by ${wd.toFixed(2)} m — calmer, safer water — and explored ${eff}% ` +
        `fewer cells than Dijkstra.`;
    }
  }
  $("verdict").textContent = verdict;
  $("results").classList.remove("hidden");
}


/* ------------------------------------------------------------------ */
/* Voyage simulation mode (POST /api/simulate)                         */
/* All rerouting logic runs on the server (src/rerouting.py); this     */
/* code only collects inputs and draws the returned voyage.            */
/* ------------------------------------------------------------------ */
let mode = "route", vesselMarker = null, simData = null;

const SIM_SCENARIOS = {
  stable: "No weather change (control)",
  adverse: "Severe storm appears on the route ahead",
  worsening: "Storm on the route ahead intensifies",
  improving_alt: "Storm blocking the direct path clears",
  minor: "Small, weak disturbance on the route",
  shifting: "Storm moves every step (tests cooldown)",
};

const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function initSimControls() {
  const sim = META.simulation;
  const sel = $("sim-scenario");
  sim.scenarios.forEach((n) => sel.add(new Option(SIM_SCENARIOS[n] || n, n)));
  sel.value = "adverse";
  const d = sim.defaults;
  $("cfg-cooldown").value = d.cooldown_steps;
  $("cfg-gain").value = +(100 * d.min_gain).toFixed(2);
  $("cfg-swh").value = d.swh_trigger_m;
  $("cfg-hint").textContent =
    `1 step = ${d.cells_per_step} grid cells (≈${Math.round(d.cells_per_step * 5.5)} km). ` +
    `Also requires ≥ ${d.min_gain_abs} cost units of gain.`;
}

function setMode(m) {
  if (mode === "lab" && m !== "lab") labLeave();
  mode = m;
  document.querySelectorAll("#mode button").forEach((x) =>
    x.classList.toggle("active", x.dataset.val === m));
  // An element is shown if it carries the class of the current mode.
  document.querySelectorAll(".mode-route, .mode-sim, .mode-lab").forEach((e) =>
    e.classList.toggle("hidden", !e.classList.contains("mode-" + m)));
  clearRoutes();
  $("results").classList.add("hidden");
  if (m === "lab") labEnter();
}

async function runSimulation() {
  if (scenario === "live")
    return toast("Voyage simulation uses offline weather: pick Typical or Rough.");
  if ($("origin").value === $("dest").value)
    return toast("Origin and destination are the same.");
  const num = (id) => Number($(id).value);
  loading(true, "Simulating voyage (with and without rerouting)…");
  try {
    const r = await fetch("/api/simulate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin: $("origin").value, dest: $("dest").value,
        vessel: $("vessel").value, base_weather: scenario,
        scenario: $("sim-scenario").value,
        config: { cooldown_steps: num("cfg-cooldown"),
                  min_gain: num("cfg-gain") / 100,
                  swh_trigger_m: num("cfg-swh") },
      }),
    });
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    simData = d;
    drawSimulation(d);
  } catch (e) {
    toast("Simulation failed: " + e.message);
  } finally {
    loading(false);
  }
}

function drawSimulation(d) {
  clearRoutes();
  const bounds = new google.maps.LatLngBounds();
  const toPath = (pts) => pts.map((p) => ({ lat: p[0], lng: p[1] }));

  // Initial plan: dashed grey.
  const initial = smoothPath(toPath(d.initial_route.path), 3);
  routeLines.push(new google.maps.Polyline({
    path: initial, map, geodesic: true, strokeOpacity: 0,
    icons: [{ icon: { path: "M 0,-1 0,1", strokeOpacity: 0.9, scale: 3,
                      strokeColor: "#94a3b8" }, offset: "0", repeat: "14px" }],
  }));
  // Track actually sailed (ends on the final active route): solid.
  const track = smoothPath(toPath(d.track), 3);
  routeLines.push(new google.maps.Polyline({
    path: track, map, geodesic: true, strokeColor: "#f43f5e",
    strokeOpacity: 0.25, strokeWeight: 11 }));
  routeLines.push(new google.maps.Polyline({
    path: track, map, geodesic: true, strokeColor: "#f43f5e",
    strokeOpacity: 0.95, strokeWeight: 4 }));
  initial.concat(track).forEach((p) => bounds.extend(p));

  // Simulated weather changes: circle at the largest wave-height change.
  const changes = d.weather_updates.slice();
  if (d.departure_change) changes.unshift({ step: 0, departure: true, ...d.departure_change });
  changes.forEach((w) => {
    const worse = w.delta_m > 0;
    const c = new google.maps.Circle({
      map, center: { lat: w.lat, lng: w.lon }, radius: 150000,
      strokeColor: worse ? "#a855f7" : "#34d399", strokeOpacity: 0.8,
      strokeWeight: 1, fillColor: worse ? "#a855f7" : "#34d399",
      fillOpacity: 0.12, clickable: true });
    c.addListener("click", () => {
      info.setPosition({ lat: w.lat, lng: w.lon });
      info.setContent(`<div class="wx-pop"><b>Simulated weather change</b>` +
        `${w.departure ? "At departure" : "Step " + w.step}: ` +
        `${w.delta_m > 0 ? "+" : ""}${w.delta_m} m wave height (peak)</div>`);
      info.open(map);
    });
    routeLines.push(c);
  });

  // Reroute events: amber badges R1, R2, ...; failed searches in red.
  let n = 0;
  d.events.forEach((e) => {
    if (e.decision !== "adopted" && e.decision !== "failed") return;
    const adopted = e.decision === "adopted";
    const m = new google.maps.Marker({
      position: { lat: e.position[0], lng: e.position[1] }, map, zIndex: 1000,
      label: adopted ? { text: "R" + (++n), color: "#0b1220",
                         fontSize: "10px", fontWeight: "700" } : undefined,
      icon: { path: google.maps.SymbolPath.CIRCLE, scale: adopted ? 10 : 6,
        fillColor: adopted ? "#fbbf24" : "#f43f5e", fillOpacity: 1,
        strokeColor: "#0b1220", strokeWeight: 2 },
    });
    m.addListener("click", () => {
      info.setContent(`<div class="wx-pop"><b>Step ${e.step}: ${esc(e.decision)}</b>` +
        `${esc(e.reason)}<br>${esc(e.triggers.join("; "))}</div>`);
      info.open(map, m);
    });
    routeMarkers.push(m);
  });

  addMarker(d.origin.lat, d.origin.lon, "Origin: " + d.origin.name,
    "#34d399", SHIP_PATH, "");
  addMarker(d.dest.lat, d.dest.lon, "Destination: " + d.dest.name,
    "#f43f5e", ANCHOR_PATH, "");
  vesselMarker = new google.maps.Marker({
    position: track[0], map, zIndex: 1001, title: "Simulated vessel position",
    icon: { path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW, scale: 5,
      fillColor: "#ffffff", fillOpacity: 1, strokeColor: "#0b1220", strokeWeight: 1 },
  });
  routeMarkers.push(vesselMarker);
  map.fitBounds(bounds, 80);
  renderSimPanel(d);
}

function simCard(name, cls, v) {
  return `<div class="card ${cls}">
    <div class="card-title"><b>${name}</b><span>simulated</span></div>
    <div class="metrics">
      <div class="metric"><div class="v">${v.hours.toFixed(1)}</div><div class="k">hours (model)</div></div>
      <div class="metric"><div class="v">${fmt(v.distance_km)}</div><div class="k">km sailed</div></div>
      <div class="metric"><div class="v">${v.reroutes}</div><div class="k">reroutes</div></div>
      <div class="metric"><div class="v">${fmt(v.cost)}</div><div class="k">route cost</div></div>
    </div></div>`;
}

function renderSimPanel(d) {
  $("results-title").textContent = "Simulated voyage";
  $("cards").innerHTML = simCard("With rerouting", "astar", d.dynamic) +
    simCard("Without rerouting", "static", d.static);
  const dh = d.dynamic.hours - d.static.hours;
  $("verdict").textContent = d.dynamic.reroutes === 0
    ? "No reroute was adopted: the voyage is the same as without rerouting."
    : `${d.dynamic.reroutes} reroute(s) adopted. Simulated voyage time ` +
      `${dh <= 0 ? "" : "+"}${dh.toFixed(1)} h versus the same voyage ` +
      `without rerouting, under the same simulated weather.`;

  const evs = d.events.map((e) => `<div class="event ${esc(e.decision)}" data-step="${e.step}">
      <span class="badge">Step ${e.step} · ${esc(e.decision)}</span>${esc(e.reason)}
      <small>${esc(e.triggers.join("; ") || "—")}${e.remaining_hours != null
        ? ` · remaining ${e.remaining_hours} h` : ""}${e.alternative_hours != null
        ? ` vs alternative ${e.alternative_hours} h` : ""}</small></div>`).join("");
  const steps = d.dynamic.steps;
  $("sim-extra").innerHTML = `
    <p class="plan-line">Initial plan: ${d.initial_route.hours} h,
      ${fmt(d.initial_route.distance_km)} km (from origin, departure weather).<br>
      Final active route: ${d.final_route.hours} h, ${fmt(d.final_route.distance_km)} km
      (from the last reroute position, weather at that time).</p>
    <h3>Vessel progress</h3>
    <input type="range" id="sim-step" min="0" max="${steps}" value="0" />
    <div id="sim-step-label" class="plan-line"></div>
    <h3>Rerouting evaluations (${d.dynamic.evaluations} total, ` +
      `${d.events.length} with a trigger)</h3>
    <div class="events">${evs || '<div class="plan-line">No trigger was reached.</div>'}</div>
    <p class="sim-note">${esc(d.note)} Cost units: km × ML speed multiplier.</p>`;
  $("sim-extra").classList.remove("hidden");
  $("sim-step").addEventListener("input", (ev) => showStep(+ev.target.value));
  showStep(0);
  $("results").classList.remove("hidden");
}

function showStep(step) {
  const d = simData, cps = d.config.cells_per_step;
  const i = Math.min(step * cps, d.track.length - 1);
  vesselMarker.setPosition({ lat: d.track[i][0], lng: d.track[i][1] });
  const wx = d.weather_updates.filter((w) => w.step === step);
  $("sim-step-label").textContent = `Step ${step} of ${d.dynamic.steps}` +
    (i === d.track.length - 1 ? " · arrived" : "") +
    (wx.length ? ` · weather change ${wx[0].delta_m > 0 ? "+" : ""}${wx[0].delta_m} m` : "");
  document.querySelectorAll(".event").forEach((el) =>
    el.classList.toggle("current", +el.dataset.step === step));
}

/* ------------------------------------------------------------------ */
/* Simulation lab (/api/sim/sessions...)                               */
/* The backend (src/sim_session.py + src/rerouting.py) runs every      */
/* simulation step and rerouting decision. This code only sends user   */
/* actions, one request at a time, and draws the returned state.       */
/* ------------------------------------------------------------------ */
const lab = {
  sid: null, state: null, running: false, loop: false, busy: false,
  queue: Promise.resolve(), selected: null, placing: false,
  drawn: { routeKey: null, weatherKey: null, overlayUrl: null },
  objs: { initial: null, active: null, track: null, vessel: null, ends: [],
          rMarkers: [], circles: [], overlay: null },
  lastSeq: 0, presets: [], limits: null, clickListener: null, resetArmed: null,
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function bindLab() {
  try {
    const d = await (await fetch("/api/sim/presets")).json();
    lab.presets = d.presets; lab.limits = d.limits;
    const sel = $("lab-preset");
    d.presets.forEach((p) => sel.add(new Option(p.name.replace(/_/g, " "), p.name)));
    sel.value = "none";
    const info = () => { $("lab-preset-info").textContent =
      (lab.presets.find((p) => p.name === sel.value) || {}).description || ""; };
    sel.addEventListener("change", info); info();
  } catch (e) { toast("Could not load simulation presets: " + e.message); }
  $("lab-create").addEventListener("click", () => labCreate(false));
  $("lab-start").addEventListener("click", labStart);
  $("lab-pause").addEventListener("click", labPause);
  $("lab-step").addEventListener("click", () => labStepOnce());
  $("lab-reset").addEventListener("click", labReset);
  $("lab-routine").addEventListener("change", () => labRenderTimeline(true));
  $("dist-place").addEventListener("click", () => {
    lab.placing = !lab.placing;
    $("dist-place").classList.toggle("armed", lab.placing);
    $("dist-place").textContent = lab.placing ? "Click the map…" : "＋ Place on map";
  });
  $("dist-add").addEventListener("click", () => {
    const d = labFormDisturbance(true); if (d) labEditWeather([...labWorkList(), d]);
  });
  $("dist-update").addEventListener("click", () => {
    const d = labFormDisturbance(true); if (!d || !lab.selected) return;
    labEditWeather(labWorkList().map((x) => x.id === lab.selected ? { ...x, ...d } : x));
  });
  $("dist-remove").addEventListener("click", () => {
    if (!lab.selected) return;
    labEditWeather(labWorkList().filter((x) => x.id !== lab.selected));
    lab.selected = null;
  });
  $("weather-apply").addEventListener("click", () => labAction("weather/apply"));
  $("weather-discard").addEventListener("click", () => labAction("weather/discard"));
  $("schedule-cancel").addEventListener("click", () => labAction("schedule/cancel"));
  labControls();
}

/* --- requests: strictly one at a time -------------------------------- */
function labApi(method, path, body) {
  const run = async () => {
    lab.busy = true; labControls();
    try {
      let r;
      try {
        r = await fetch(path, { method, headers: { "Content-Type": "application/json" },
                                body: body === undefined ? undefined : JSON.stringify(body) });
      } catch (e) { throw new Error("Network error - is the server running?"); }
      let d = null;
      try { d = await r.json(); } catch (e) { /* non-JSON */ }
      if (!r.ok || !d || d.error) {
        const err = new Error((d && d.error) || `Server returned ${r.status}`);
        err.status = r.status; throw err;
      }
      return d;
    } finally { lab.busy = false; labControls(); }
  };
  const p = lab.queue.then(run, run);
  lab.queue = p.catch(() => {});
  return p;
}

async function labHandleError(e, what) {
  toast(`${what}: ${e.message}`);
  if (e.status === 404) {                  // session expired / unknown
    labPause(); lab.sid = null; lab.state = null; labClearMap(); labRenderPanel();
  } else if (lab.sid && (e.status === 409 || e.status >= 500 || !e.status)) {
    try { labApply(await labApi("GET", `/api/sim/sessions/${lab.sid}`)); }
    catch (e2) { /* keep showing the last good state */ }
  }
}

function labConfig() {
  const num = (id) => Number($(id).value);
  return {
    origin: $("origin").value, dest: $("dest").value, vessel: $("vessel").value,
    base_weather: scenario, preset: $("lab-preset").value,
    rerouting_enabled: $("lab-rerouting").checked,
    config: { cooldown_steps: num("cfg-cooldown"), min_gain: num("cfg-gain") / 100,
              swh_trigger_m: num("cfg-swh") },
  };
}

async function labCreate(thenRun) {
  if (scenario === "live")
    return toast("The simulation uses offline weather: pick Typical or Rough.");
  if ($("origin").value === $("dest").value)
    return toast("Origin and destination are the same.");
  labPause();
  const old = lab.sid;
  loading(true, "Planning the voyage…");
  try {
    const st = await labApi("POST", "/api/sim/sessions", labConfig());
    if (old) labApi("DELETE", `/api/sim/sessions/${old}`).catch(() => {});
    lab.sid = st.id; lab.lastSeq = 0; lab.selected = null;
    lab.drawn = { routeKey: null, weatherKey: null, overlayUrl: null };
    labClearMap();
    labApply(st, true);
    if (thenRun) labStart();
  } catch (e) {
    toast("Could not start voyage: " + e.message);
  } finally { loading(false); }
}

function labStart() {
  if (!lab.sid) return labCreate(true);
  if (lab.loop || !lab.state || ["completed", "error"].includes(lab.state.status)) return;
  lab.running = true; lab.loop = true; labControls();
  (async () => {
    try {
      while (lab.running && lab.state && !["completed", "error"].includes(lab.state.status)) {
        if (!(await labStepOnce(true))) break;
        if (lab.running) await sleep(Number($("lab-speed").value));
      }
    } finally { lab.running = false; lab.loop = false; labControls(); }
  })();
}

function labPause() { lab.running = false; labControls(); }

async function labStepOnce(fromLoop) {
  if (!lab.sid || !lab.state || lab.stepping ||
      (!fromLoop && (lab.running || lab.busy))) return false;
  lab.stepping = true;                      // set synchronously: blocks double clicks
  try { return await labStepRequest(); } finally { lab.stepping = false; labControls(); }
}

async function labStepRequest() {
  for (let attempt = 0; ; attempt++) {
    try {
      labApply(await labApi("POST", `/api/sim/sessions/${lab.sid}/step`,
                            { expected_step: lab.state.step }));
      return true;
    } catch (e) {
      if (e.status === 409 && /busy/.test(e.message) && attempt < 5) {
        await sleep(300); continue;          // another request is finishing
      }
      lab.running = false; await labHandleError(e, "Step failed"); return false;
    }
  }
}

async function labReset() {
  if (!lab.sid) return;
  if (!lab.resetArmed) {                   // two-click confirmation
    $("lab-reset").classList.add("armed");
    $("lab-reset").textContent = "Confirm reset?";
    lab.resetArmed = setTimeout(labDisarmReset, 3000);
    return;
  }
  labDisarmReset(); labPause();
  try {
    const st = await labApi("POST", `/api/sim/sessions/${lab.sid}/reset`);
    lab.lastSeq = 0; lab.selected = null;
    lab.drawn = { routeKey: null, weatherKey: null, overlayUrl: null };
    labClearMap(); labApply(st, true);
  } catch (e) { await labHandleError(e, "Reset failed"); }
}
function labDisarmReset() {
  clearTimeout(lab.resetArmed); lab.resetArmed = null;
  $("lab-reset").classList.remove("armed"); $("lab-reset").textContent = "↺ Reset";
}

async function labAction(path) {
  if (!lab.sid) return;
  try { labApply(await labApi("POST", `/api/sim/sessions/${lab.sid}/${path}`)); }
  catch (e) { await labHandleError(e, "Weather"); }
}

/* --- weather editing ------------------------------------------------- */
function labWorkList() {
  const w = lab.state && lab.state.weather;
  return w ? (w.pending || w.applied).map((d) => ({ ...d })) : [];
}

function labFormDisturbance(needPos) {
  const L = lab.limits || {};
  const v = (id) => Number($(id).value);
  const d = { delta_m: v("dist-delta"), radius_km: v("dist-radius") };
  if (needPos) { d.lat = v("dist-lat"); d.lon = v("dist-lon"); }
  for (const [k, x] of Object.entries(d)) {
    const [lo, hi] = L[k] || [-Infinity, Infinity];
    if ($(`dist-${k === "delta_m" ? "delta" : k === "radius_km" ? "radius" : k}`).value === "" ||
        !Number.isFinite(x) || x < lo || x > hi) {
      toast(`${k} must be a number between ${lo} and ${hi}.`); return null;
    }
  }
  if (d.delta_m === 0) { toast("Δ wave height must not be 0."); return null; }
  return d;
}

async function labEditWeather(list) {
  if (!lab.sid) return toast("Start a voyage first.");
  try {
    labApply(await labApi("POST", `/api/sim/sessions/${lab.sid}/weather`,
                          { disturbances: list }));
  } catch (e) { await labHandleError(e, "Weather change rejected"); }
}

function labMapClick(ev) {
  if (mode !== "lab" || !lab.placing) return;
  lab.placing = false;
  $("dist-place").classList.remove("armed"); $("dist-place").textContent = "＋ Place on map";
  $("dist-lat").value = ev.latLng.lat().toFixed(2);
  $("dist-lon").value = ev.latLng.lng().toFixed(2);
  const d = labFormDisturbance(true);
  if (d) labEditWeather([...labWorkList(), d]);
}

/* --- state -> view ------------------------------------------------------ */
function labApply(st, fit) {
  if (!st || !st.routes || !st.metrics || !st.weather) {
    toast("Malformed response from the server - state not updated."); return;
  }
  lab.state = st;
  if (mode === "lab") { labDraw(fit); }
  labRenderPanel();
}

const toLL = (p) => ({ lat: p[0], lng: p[1] });

function labDraw(fit) {
  const st = lab.state; if (!st) return;
  const o = lab.objs;
  if (!lab.clickListener) lab.clickListener = map.addListener("click", labMapClick);
  const routeKey = `${st.id}:${st.routes.route_version}:${st.timeline[0] && st.timeline[0].seq}`;
  if (lab.drawn.routeKey !== routeKey) {
    lab.drawn.routeKey = routeKey;
    if (!o.initial) {
      o.initial = new google.maps.Polyline({ map, geodesic: true, strokeOpacity: 0, zIndex: 1,
        icons: [{ icon: { path: "M 0,-1 0,1", strokeOpacity: 0.9, scale: 3,
                          strokeColor: "#94a3b8" }, offset: "0", repeat: "14px" }] });
      o.active = new google.maps.Polyline({ map, geodesic: true, strokeColor: "#38bdf8",
        strokeOpacity: 0.95, strokeWeight: 4, zIndex: 2 });
      o.track = new google.maps.Polyline({ map, geodesic: true, strokeColor: "#34d399",
        strokeOpacity: 1, strokeWeight: 5, zIndex: 3 });
    }
    o.initial.setPath(st.routes.initial.map(toLL));
    o.active.setPath(st.routes.active.map(toLL));
    o.ends.forEach((m) => m.setMap(null));
    o.ends = [["Origin", st.origin, "#34d399", SHIP_PATH], ["Destination", st.dest, "#f43f5e", ANCHOR_PATH]]
      .map(([t, p, c, path]) => new google.maps.Marker({ position: toLL(p), map, title: t,
        zIndex: 999, icon: badgeIcon(path, c) }));
  }
  o.track.setPath(st.track.map(toLL));
  const icon = { path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW, scale: 6,
    fillColor: "#ffffff", fillOpacity: 1, strokeColor: "#0b1220", strokeWeight: 1.5,
    rotation: st.vessel.heading_deg };
  if (!o.vessel) o.vessel = new google.maps.Marker({ map, zIndex: 1002,
    title: "Simulated vessel position", icon });
  o.vessel.setPosition(toLL(st.vessel.position)); o.vessel.setIcon(icon);
  if (o.rMarkers.length !== st.reroutes.length) {
    o.rMarkers.forEach((m) => m.setMap(null));
    o.rMarkers = st.reroutes.map((r) => {
      const m = new google.maps.Marker({ position: toLL(r.position), map, zIndex: 1001,
        label: { text: "R" + r.no, color: "#0b1220", fontSize: "10px", fontWeight: "700" },
        icon: { path: google.maps.SymbolPath.CIRCLE, scale: 11, fillColor: "#fbbf24",
                fillOpacity: 1, strokeColor: "#0b1220", strokeWeight: 2 } });
      m.addListener("click", () => labShowEvent(r.seq));
      return m;
    });
  }
  const w = st.weather;
  const weatherKey = JSON.stringify([w.applied, w.pending, lab.selected]);
  if (lab.drawn.weatherKey !== weatherKey) { lab.drawn.weatherKey = weatherKey; labDrawCircles(); }
  labSyncOverlay();
  if (fit) {
    const b = new google.maps.LatLngBounds();
    st.routes.initial.forEach((p) => b.extend(toLL(p)));
    map.fitBounds(b, 80);
  }
}

function labDrawCircles() {
  const o = lab.objs, w = lab.state.weather;
  o.circles.forEach((c) => c.setMap(null)); o.circles = [];
  const add = (d, pending) => {
    const storm = d.delta_m > 0;
    const color = storm ? "#a855f7" : "#34d399";
    const editable = pending || !w.pending;
    const c = new google.maps.Circle({ map, center: { lat: d.lat, lng: d.lon },
      radius: d.radius_km * 1000, clickable: true, draggable: editable,
      zIndex: pending ? 5 : 4,
      strokeColor: pending ? "#ffffff" : color, strokeOpacity: pending ? 0.95 : 0.8,
      strokeWeight: d.id === lab.selected ? 3 : pending ? 2 : 1,
      fillColor: color, fillOpacity: pending ? 0.04 : Math.min(0.35, 0.08 + 0.04 * Math.abs(d.delta_m)) });
    c.addListener("click", () => labSelect(d.id));
    if (editable) c.addListener("dragend", () => {
      const p = c.getCenter();
      labEditWeather(labWorkList().map((x) => x.id === d.id
        ? { ...x, lat: +p.lat().toFixed(3), lon: +p.lng().toFixed(3) } : x));
    });
    o.circles.push(c);
  };
  w.applied.forEach((d) => add(d, false));
  (w.pending || []).forEach((d) => add(d, true));
}

function labSyncOverlay() {
  const st = lab.state;
  if (mode !== "lab" || !st) return;
  if (waveOverlay) waveOverlay.setMap(null);     // base-scenario overlay is not the sim field
  const url = st.weather.overlay.url;
  if (lab.drawn.overlayUrl !== url) {
    if (lab.objs.overlay) lab.objs.overlay.setMap(null);
    lab.objs.overlay = new google.maps.GroundOverlay(url,
      { north: META.region.lat_max, south: META.region.lat_min,
        east: META.region.lon_max, west: META.region.lon_min }, { opacity: 0.6 });
    lab.drawn.overlayUrl = url;
  }
  lab.objs.overlay.setMap($("use-waves").checked ? map : null);
  $("legend-max").textContent = st.weather.overlay.legend_max_m + " m";
  $("legend").classList.remove("hidden");
}

function labClearMap() {
  if (info) info.close();                   // no stale popups from an old voyage
  const o = lab.objs;
  [o.initial, o.active, o.track, o.vessel, o.overlay, ...o.ends, ...o.rMarkers, ...o.circles]
    .forEach((x) => x && x.setMap(null));
  lab.objs = { initial: null, active: null, track: null, vessel: null, ends: [],
               rMarkers: [], circles: [], overlay: null };
  lab.drawn = { routeKey: null, weatherKey: null, overlayUrl: null };
}

function labEnter() {
  $("lab-panel").classList.remove("hidden");
  if (lab.state) labDraw(true);
  labRenderPanel();
}

function labLeave() {
  labPause();
  lab.placing = false;
  labClearMap();
  if (lab.clickListener) { lab.clickListener.remove(); lab.clickListener = null; }
  $("lab-panel").classList.add("hidden");
  if (waveOverlay) waveOverlay.setMap($("use-waves").checked ? map : null);
}

function labSelect(id) {
  lab.selected = lab.selected === id ? null : id;
  const d = labWorkList().find((x) => x.id === lab.selected);
  if (d) {
    $("dist-delta").value = d.delta_m; $("dist-radius").value = d.radius_km;
    $("dist-lat").value = d.lat; $("dist-lon").value = d.lon;
  }
  lab.drawn.weatherKey = null;
  if (lab.state) { labDrawCircles(); labRenderPanel(); }
}

function labShowEvent(seq, fromMap = true) {
  const e = lab.state && lab.state.timeline.find((x) => x.seq === seq);
  if (!e) return;
  if (e.position) {
    map.panTo(toLL(e.position));
    const d = e.detail || {};
    info.setPosition(toLL(e.position));
    info.setContent(`<div class="wx-pop"><b>Step ${e.step}: ${esc(d.decision || e.kind)}</b>` +
      `${esc(e.message)}<br>${d.triggers ? "Triggers: " + esc(d.triggers.join("; ") || "none") : ""}</div>`);
    info.open(map);
  }
  const el = document.querySelector(`.tl[data-seq="${seq}"]`);
  if (el) {
    if (fromMap) { el.classList.add("open"); labRenderTimeline(true); }
    const again = document.querySelector(`.tl[data-seq="${seq}"]`);
    if (again) again.scrollIntoView({ block: "nearest" });
  }
}

/* --- panel ---------------------------------------------------------------- */
function labControls() {
  const st = lab.state, has = !!lab.sid && !!st;
  const done = has && ["completed", "error"].includes(st.status);
  $("lab-start").disabled = lab.running || done;
  $("lab-start").textContent = !has ? "▶ Start" : st.step > 0 ? "▶ Resume" : "▶ Start";
  $("lab-pause").disabled = !lab.running;
  $("lab-step").disabled = !has || lab.running || lab.busy || lab.stepping || done;
  $("lab-reset").disabled = !has;
  const w = has ? st.weather : null;
  const editable = has && !done;
  ["dist-place", "dist-add"].forEach((id) => $(id).disabled = !editable);
  $("dist-update").disabled = !editable || !lab.selected;
  $("dist-remove").disabled = !editable || !lab.selected;
  $("weather-apply").disabled = !editable || !w || !w.pending;
  $("weather-discard").disabled = !has || !w || !w.pending;
  $("schedule-cancel").disabled = !editable || !w || !w.schedule.length;
  let status = "No voyage";
  if (has) status = st.status === "completed" ? "Arrived"
    : st.status === "error" ? "Error - reset" : lab.running ? "Running…"
    : lab.busy ? "Working…" : st.step === 0 ? "Ready" : "Paused";
  $("lab-status").textContent = has
    ? `${status} · step ${st.step} · ${Math.round(100 * st.metrics.progress)}%` : status;
  $("lab-progress-bar").style.width = has ? `${100 * st.metrics.progress}%` : "0";
}

function labRenderPanel() {
  labControls();
  const st = lab.state;
  if (!st) {
    $("lab-metrics").innerHTML = '<div class="plan-line" style="grid-column: span 3">' +
      "Configure the voyage on the left, then <b>Start</b> or <b>New voyage</b>.</div>";
    ["lab-compare", "lab-weather-status", "lab-dist-list", "lab-timeline"]
      .forEach((id) => $(id).innerHTML = "");
    $("lab-weather-badge").classList.add("hidden");
    return;
  }
  const m = st.metrics, c = st.comparison_no_rerouting;
  const cell = (v, k) => `<div><div class="v">${v}</div><div class="k">${k}</div></div>`;
  $("lab-metrics").innerHTML =
    cell(st.step, "step") + cell(Math.round(100 * m.progress) + "%", "progress") +
    cell(m.reroutes, "reroutes") +
    cell(fmt(m.sailed_km), "km sailed") + cell(m.sailed_hours.toFixed(1), "h sailed") +
    cell(m.remaining_hours.toFixed(1), "h remaining") +
    cell(m.projected_total_hours.toFixed(1), "h projected") +
    cell(fmt(m.remaining_route_cost), "route cost left") +
    cell(st.status, "state");
  const dh = m.projected_total_hours - c.projected_total_hours;
  $("lab-compare").textContent = st.setup.rerouting_enabled
    ? `Same voyage without rerouting, same weather: ${c.projected_total_hours.toFixed(1)} h ` +
      `${c.arrived ? "(arrived)" : "projected"} → difference ${dh <= 0 ? "" : "+"}${dh.toFixed(1)} h.`
    : "Rerouting is off for this voyage (the vessel keeps its initial route).";
  const w = st.weather;
  $("lab-weather-badge").classList.toggle("hidden", !w.pending);
  const sched = w.schedule.length
    ? ` · scheduled preset updates at step ${w.schedule.map((x) => x.step).join(", ")}` : "";
  $("lab-weather-status").innerHTML =
    `Base: <b>${esc(w.base_weather)}</b> · ${w.applied.length} applied disturbance(s)` +
    `${w.pending ? `, <b>${w.pending.length} in pending list</b>` : ""}<br>` +
    `Max wave on remaining route ${w.max_wave_on_remaining_route_m} m · field max ` +
    `${w.field_max_wave_m} m<br>Last weather update: ${w.last_update_step == null ? "none"
      : "step " + w.last_update_step} · next route evaluation: ${w.next_evaluation_step == null
      ? "none" : "step " + w.next_evaluation_step}${esc(sched)}`;
  const shown = w.pending || w.applied;
  const appliedIds = new Set(w.applied.map((d) => JSON.stringify([d.id, d.lat, d.lon, d.radius_km, d.delta_m])));
  $("lab-dist-list").innerHTML = shown.length ? shown.map((d) => {
    const isApplied = appliedIds.has(JSON.stringify([d.id, d.lat, d.lon, d.radius_km, d.delta_m]));
    return `<div class="dist ${d.delta_m < 0 ? "calm" : ""} ${d.id === lab.selected ? "selected" : ""}"
      data-id="${esc(d.id)}"><span class="st ${isApplied ? "" : "pending"}">${isApplied ? "applied" : "pending"}
      · ${esc(d.origin)}</span><b>${esc(d.id)}</b> ${d.delta_m > 0 ? "+" : ""}${d.delta_m} m,
      σ ${d.radius_km} km<br>${d.lat.toFixed(2)}°N ${d.lon.toFixed(2)}°E</div>`;
  }).join("") + (w.pending ? w.applied.filter((a) => !w.pending.some((p) => p.id === a.id))
      .map((a) => `<div class="dist"><span class="st pending">removal pending</span>
        <b>${esc(a.id)}</b> ${a.delta_m} m</div>`).join("") : "")
    : '<div class="plan-line">No disturbances. Use “Place on map” to add a storm.</div>';
  document.querySelectorAll("#lab-dist-list .dist[data-id]").forEach((el) =>
    el.addEventListener("click", () => labSelect(el.dataset.id)));
  labRenderTimeline(false);
}

function labRenderTimeline(force) {
  const st = lab.state, box = $("lab-timeline");
  if (!st) return;
  const routine = $("lab-routine").checked;
  const firstSeq = st.timeline.length ? st.timeline[0].seq : 0;
  const lastSeq = st.timeline.length ? st.timeline[st.timeline.length - 1].seq : 0;
  if (!force && box.dataset.first === String(firstSeq) && box.dataset.last === String(lastSeq)) return;
  const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
  const open = new Set([...box.querySelectorAll(".tl.open")].map((e) => e.dataset.seq));
  const items = st.timeline.filter((e) => routine || !(e.kind === "advanced" ||
    (e.kind === "evaluation" && e.detail.decision === "no_trigger")));
  box.innerHTML = items.map((e) => {
    const d = e.detail, adopted = d && d.adopted;
    const cls = ["tl", e.source.split("+")[0], adopted ? "adopted" : "",
                 e.kind === "error" ? "error" : "", e.position ? "clickable" : "",
                 open.has(String(e.seq)) ? "open" : ""].join(" ");
    const det = d && open.has(String(e.seq)) ? `<div class="detail">
      decision ${esc(d.decision)} · searched ${d.searched ? "yes" : "no"} ·
      alternative found ${d.alternative_found ? "yes" : "no"}<br>
      active-route cost ${d.active_route_cost} (${d.remaining_hours} h) ·
      alternative ${d.alternative_cost == null ? "–" : d.alternative_cost + " (" + d.alternative_hours + " h)"} ·
      gain ${d.gain_pct == null ? "–" : d.gain_pct + "%"}<br>
      max wave ${d.max_wave_m} m · triggers: ${esc(d.triggers.join("; ") || "none")}</div>` : "";
    return `<div class="${cls}" data-seq="${e.seq}"><span class="src">s${e.step} · ${esc(e.source)}</span>${esc(e.message)}${det}</div>`;
  }).join("") + (st.timeline_truncated ? `<div class="plan-line">${st.timeline_truncated} older entries dropped</div>` : "");
  box.dataset.first = firstSeq; box.dataset.last = lastSeq;
  box.querySelectorAll(".tl").forEach((el) => el.addEventListener("click", () => {
    const seq = Number(el.dataset.seq);
    const e = st.timeline.find((x) => x.seq === seq);
    if (e && e.detail) el.classList.toggle("open");
    labRenderTimeline(true);
    if (e && e.position) labShowEvent(seq, false);
  }));
  if (atBottom && !force) box.scrollTop = box.scrollHeight;
}
