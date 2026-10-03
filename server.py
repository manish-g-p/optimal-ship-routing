"""
Nautilus backend - Flask API + static server for the polished web app.

Loads the routing engine ONCE at startup and exposes:
  GET  /                 -> the web app (Google Maps key injected)
  GET  /api/meta         -> ports + vessels
  GET  /api/weather      -> wave heatmap points for a scenario
  POST /api/route        -> compute Dijkstra + weather-aware A* routes
  POST /api/simulate     -> simulated voyage with weather-driven rerouting
                            (vs. the same voyage without rerouting)

Run:  python server.py   (then open http://localhost:8000)
"""
import io
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import colormaps, image as mpimg
from flask import (Flask, jsonify, request, send_from_directory, Response,
                   send_file)

import config as C
from dataclasses import asdict

from src import (grid as G, weather as W, routing as R, ports as P,
                 vessel as V, ml_model as ML, live_weather as LW,
                 rerouting as RR, weather_sim as WS)

WEB = Path(__file__).resolve().parent / "web"
app = Flask(__name__)

if not C.GOOGLE_MAPS_API_KEY:
    # Non-fatal: the JSON API and every routing feature work without a
    # Maps key, only the map tiles won't render. Never log the key value
    # itself, set or not.
    print("[server] WARNING: GOOGLE_MAPS_API_KEY is not set - the map "
          "will not load. Set it in .env (see .env.example) or export it "
          "in your shell before running.")

# ----------------------------------------------------------------------
# Load heavy objects once, then cache derived fields.
# ----------------------------------------------------------------------
print("[server] loading grid + ML model...")
GRID = G.load_grid()
MODEL = ML.load()
DIST_COAST = np.load(C.GRID_FILE)["dist_to_coast_km"]
_weather_cache = {}
_mult_cache = {}
print("[server] ready.")


def get_weather(scenario):
    if scenario == "live":
        return LW.build_live_weather(GRID)          # module-cached ~5 min
    if scenario not in _weather_cache:
        _weather_cache[scenario] = W.load_weather(GRID, scenario)
    return _weather_cache[scenario]


def get_multiplier(scenario, vessel_name, weather):
    if scenario == "live":                          # live changes -> no cache
        return ML.build_multiplier_grid(GRID, weather, V.get(vessel_name), MODEL)
    key = (scenario, vessel_name)
    if key not in _mult_cache:
        _mult_cache[key] = ML.build_multiplier_grid(
            GRID, weather, V.get(vessel_name), MODEL)
    return _mult_cache[key]


def route_waves(weather, res):
    swh = [float(weather.swh[r, c]) for r, c in res.cells]
    return round(max(swh), 2), round(float(np.mean(swh)), 2)


def waypoints(weather, res, every=12):
    mwd = weather.mwd_deg()
    out = []
    for i in range(0, len(res.cells), every):
        r, c = res.cells[i]
        lat, lon = res.latlon[i]
        out.append({"lat": lat, "lon": lon,
                    "swh": round(float(weather.swh[r, c]), 2),
                    "mwp": round(float(weather.mwp[r, c]), 1),
                    "mwd": round(float(mwd[r, c]))})
    return out


def result_json(weather, res):
    if not res.found:
        return {"found": False}
    mx, mean = route_waves(weather, res)
    min_coast = round(float(min(DIST_COAST[r, c] for r, c in res.cells)), 1)
    return {
        "found": True,
        "path": [[la, lo] for la, lo in res.latlon],
        "distance_km": res.distance_km,
        "time_hours": res.time_hours,
        "max_wave_m": mx,
        "mean_wave_m": mean,
        "min_coast_km": min_coast,
        "expanded": res.expanded,
        "waypoints": waypoints(weather, res),
    }


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@app.route("/")
def index():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    html = html.replace("__MAPS_KEY__", C.GOOGLE_MAPS_API_KEY)
    return Response(html, mimetype="text/html")


@app.route("/<path:fname>")
def static_files(fname):
    return send_from_directory(WEB, fname)


@app.route("/api/meta")
def meta():
    return jsonify({
        "ports": [{"name": n, "lat": P.PORTS[n][0], "lon": P.PORTS[n][1]}
                  for n in P.port_list()],
        "vessels": [{"name": v.name, "speed": v.service_speed_kn,
                     "draft": v.draft_m, "length": v.length_m}
                    for v in V.VESSELS.values()],
        "region": {"lat_min": C.LAT_MIN, "lat_max": C.LAT_MAX,
                   "lon_min": C.LON_MIN, "lon_max": C.LON_MAX},
        "simulation": {"scenarios": list(WS.SCENARIOS),
                       "base_weather": list(SIM_BASE_WEATHER),
                       "defaults": asdict(RR.RerouteConfig())},
    })


_TURBO = colormaps["turbo"]


@app.route("/api/weather")
def weather_layer():
    """Return legend max + region bounds for the wave overlay image."""
    scenario = request.args.get("scenario", "typical")
    try:
        w = get_weather(scenario)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    vmax = max(0.5, float(np.nanpercentile(w.swh, 99)))
    return jsonify({
        "max": round(vmax, 2),
        "bounds": {"north": C.LAT_MAX, "south": C.LAT_MIN,
                   "east": C.LON_MAX, "west": C.LON_MIN},
    })


@app.route("/api/weather_image")
def weather_image():
    """Render the wave field as a semi-transparent PNG (GroundOverlay)."""
    scenario = request.args.get("scenario", "typical")
    try:
        w = get_weather(scenario)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    swh = w.swh
    vmax = max(0.5, float(np.nanpercentile(swh, 99)))
    t = np.clip(swh / vmax, 0, 1)
    rgba = _TURBO(t)                                  # (nlat, nlon, 4)
    alpha = np.where((swh > 0.05) & GRID.navigable, 0.58, 0.0)

    # Feather the outer cells so the data-box edges fade out smoothly
    # instead of showing a hard rectangle over open ocean.
    ny, nx = swh.shape
    b = 22
    ramp = np.linspace(0.0, 1.0, b)
    fade = np.ones((ny, nx), dtype=np.float32)
    fade[:b, :] *= ramp[:, None];  fade[-b:, :] *= ramp[::-1, None]
    fade[:, :b] *= ramp[None, :];  fade[:, -b:] *= ramp[None, ::-1]
    rgba[..., 3] = alpha * fade
    rgba = np.flipud(rgba)                            # north at top
    buf = io.BytesIO()
    mpimg.imsave(buf, rgba, format="png")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/api/route", methods=["POST"])
def api_route():
    body = request.get_json(force=True)
    origin = body["origin"]
    dest = body["dest"]
    vessel_name = body.get("vessel", V.DEFAULT_VESSEL)
    scenario = body.get("scenario", "typical")
    use_ml = bool(body.get("use_ml", True))
    algos = body.get("algorithms", ["dijkstra", "astar"])

    if origin == dest:
        return jsonify({"error": "Origin and destination are the same."}), 400
    if origin not in P.PORTS or dest not in P.PORTS:
        return jsonify({"error": "Unknown port."}), 400

    try:
        weather = get_weather(scenario)
    except Exception as e:
        return jsonify({"error": f"Live weather unavailable: {e}"}), 502

    start = GRID.nearest_cell(*P.coord(origin))
    goal = GRID.nearest_cell(*P.coord(dest))

    out = {
        "origin": {"name": origin, "lat": GRID.cell_latlon(*start)[0],
                   "lon": GRID.cell_latlon(*start)[1]},
        "dest": {"name": dest, "lat": GRID.cell_latlon(*goal)[0],
                 "lon": GRID.cell_latlon(*goal)[1]},
        "scenario": scenario, "vessel": vessel_name,
    }

    if "dijkstra" in algos:
        rd = R.Router(GRID).search(start, goal, False, False)
        out["dijkstra"] = result_json(weather, rd)
    if "astar" in algos:
        if use_ml:
            mult = get_multiplier(scenario, vessel_name, weather)
            router = R.Router(GRID, weather=weather, mult_dir=mult)
        else:
            router = R.Router(GRID, weather=weather)
        ra = router.search(start, goal, True, True)
        out["astar"] = result_json(weather, ra)

    return jsonify(out)


# ----------------------------------------------------------------------
# Dynamic voyage simulation (logic lives in src/rerouting.py and
# src/weather_sim.py; this only validates input and shapes the JSON)
# ----------------------------------------------------------------------
SIM_BASE_WEATHER = ("typical", "rough")    # offline only - no live weather


def sim_router_factory(vessel_name):
    """weather -> Router using the ML speed cost (as A* in /api/route)."""
    return RR.router_factory(GRID, V.get(vessel_name), MODEL)


def _latlon(cell):
    return list(GRID.cell_latlon(*cell))


def _route_json(res, ves):
    return {"path": [[la, lo] for la, lo in res.latlon],
            "distance_km": res.distance_km,
            "cost": round(res.cost, 1),
            "hours": round(RR.cost_hours(res.cost, ves), 1)}


def _voyage_json(res, ves):
    return {"hours": round(RR.cost_hours(res.sailed_cost, ves), 1),
            "distance_km": round(res.sailed_km, 1),
            "cost": round(res.sailed_cost, 1),
            "reroutes": len(res.reroutes),
            "evaluations": len(res.events),
            "steps": res.steps, "arrived": res.arrived}


def _event_json(e, ves):
    def h(cost):
        return None if cost is None else round(RR.cost_hours(cost, ves), 1)
    return {"step": e.step, "position": _latlon(e.cell),
            "decision": e.decision, "reason": e.reason,
            "triggers": list(e.triggers),
            "max_wave_m": round(e.max_swh_m, 2),
            "remaining_hours": h(e.remaining_cost),
            "alternative_hours": h(e.alternative_cost),
            "gain_pct": None if e.gain_rel is None else round(100 * e.gain_rel, 1)}


def _change_json(before, after):
    lat, lon, delta = WS.peak_change(before, after, GRID)
    return {"lat": lat, "lon": lon, "delta_m": round(delta, 2)}


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Expected a JSON object."}), 400
    origin, dest = body.get("origin"), body.get("dest")
    vessel_name = body.get("vessel", V.DEFAULT_VESSEL)
    base_name = body.get("base_weather", "typical")
    scenario = body.get("scenario", "adverse")

    if origin not in P.PORTS or dest not in P.PORTS:
        return jsonify({"error": "Unknown port."}), 400
    if origin == dest:
        return jsonify({"error": "Origin and destination are the same."}), 400
    if vessel_name not in V.VESSELS:
        return jsonify({"error": "Unknown vessel."}), 400
    if base_name not in SIM_BASE_WEATHER:
        return jsonify({"error": "Base weather must be one of "
                                 f"{', '.join(SIM_BASE_WEATHER)}."}), 400
    if scenario not in WS.SCENARIOS:
        return jsonify({"error": f"Unknown weather scenario {scenario!r}."}), 400
    try:
        cfg = RR.config_from_dict(body.get("config"))
    except (ValueError, AttributeError) as e:
        return jsonify({"error": f"Invalid rerouting settings: {e}"}), 400

    ves = V.get(vessel_name)
    base = get_weather(base_name)
    start = GRID.nearest_cell(*P.coord(origin))
    goal = GRID.nearest_cell(*P.coord(dest))
    try:
        cmp = RR.compare_voyage(GRID, start, goal, base,
                                sim_router_factory(vessel_name), scenario, cfg)
    except ValueError as e:
        return jsonify({"error": f"Simulation failed: {e}"}), 422

    dyn, sta = cmp.dynamic, cmp.static
    changes, before = [], cmp.departure
    for step in sorted(cmp.updates):
        changes.append({"step": step, **_change_json(before, cmp.updates[step])})
        before = cmp.updates[step]

    return jsonify({
        "simulated": True,
        "note": "Simulated voyage: synthetic weather changes and an ML speed "
                "model trained on synthetic data. Hours are model estimates, "
                "not real-world performance.",
        "origin": {"name": origin, "lat": _latlon(start)[0], "lon": _latlon(start)[1]},
        "dest": {"name": dest, "lat": _latlon(goal)[0], "lon": _latlon(goal)[1]},
        "vessel": vessel_name, "base_weather": base_name, "scenario": scenario,
        "config": asdict(cfg),
        "initial_route": _route_json(dyn.initial_route, ves),
        "final_route": _route_json(dyn.active_route, ves),
        "track": [_latlon(c) for c in dyn.track],
        "dynamic": _voyage_json(dyn, ves),
        "static": _voyage_json(sta, ves),
        "events": [_event_json(e, ves) for e in dyn.events
                   if e.decision != "no_trigger"],
        "departure_change": (_change_json(base, cmp.departure)
                             if cmp.departure is not base else None),
        "weather_updates": changes,
    })


if __name__ == "__main__":
    # HOST defaults to 127.0.0.1 (unchanged local-run behavior). The Docker
    # image sets HOST=0.0.0.0 so the Flask dev server is reachable from
    # outside its container via `docker run -p` - see docker/Dockerfile.
    print(f"[server] http://localhost:{C.PORT}  (bound to {C.HOST})")
    app.run(host=C.HOST, port=C.PORT, debug=False, threaded=True)
