"""
Nautilus backend - Flask API + static server for the polished web app.

Loads the routing engine ONCE at startup and exposes:
  GET  /                 -> the web app (Google Maps key injected)
  GET  /api/meta         -> ports + vessels
  GET  /api/weather      -> wave heatmap points for a scenario
  POST /api/route        -> compute Dijkstra + weather-aware A* routes
  POST /api/simulate     -> simulated voyage with weather-driven rerouting
                            (vs. the same voyage without rerouting)
  /api/sim/sessions...   -> interactive "Simulation lab" sessions (see the
                            section below and src/sim_session.py)

Run:  python server.py   (then open http://localhost:8000)
"""
import functools
import io
import logging
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
                 rerouting as RR, weather_sim as WS, sim_session as SS)

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
        "time_hours": res.time_hours,           # estimated travel time
        "time_basis": res.time_basis,           # "ml_speed" | "calm_water"
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
    vmax = max(0.5, float(np.nanpercentile(w.swh, 99)))
    return send_file(io.BytesIO(_swh_png(w.swh, vmax)), mimetype="image/png")


def _swh_png(swh, vmax):
    """Wave-height field -> semi-transparent PNG bytes (north at top)."""
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
    return buf.getvalue()


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
    if vessel_name not in V.VESSELS:
        return jsonify({"error": "Unknown vessel."}), 400

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

    # Travel time of every route is estimated with the ML speed model for
    # this vessel and weather, whatever objective selected the route.
    mult = get_multiplier(scenario, vessel_name, weather)
    timing = {"speed_kn": V.get(vessel_name).service_speed_kn, "time_mult": mult}
    if "dijkstra" in algos:
        rd = R.Router(GRID, **timing).search(start, goal, False, False)
        out["dijkstra"] = result_json(weather, rd)
    if "astar" in algos:
        if use_ml:
            router = R.Router(GRID, weather=weather, mult_dir=mult, **timing)
        else:
            router = R.Router(GRID, weather=weather, **timing)
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


def _route_json(res):
    return {"path": [[la, lo] for la, lo in res.latlon],
            "distance_km": res.distance_km,
            "cost": round(res.cost, 1),
            "hours": res.time_hours}


def _voyage_json(res):
    return {"hours": round(res.sailed_hours, 1),
            "distance_km": round(res.sailed_km, 1),
            "cost": round(res.sailed_cost, 1),
            "reroutes": len(res.reroutes),
            "evaluations": len(res.events),
            "steps": res.steps, "arrived": res.arrived}


def _event_json(e):
    def h(hours):
        return None if hours is None else round(hours, 1)
    return {"step": e.step, "position": _latlon(e.cell),
            "decision": e.decision, "reason": e.reason,
            "triggers": list(e.triggers),
            "max_wave_m": round(e.max_swh_m, 2),
            "remaining_hours": h(e.remaining_hours),
            "alternative_hours": h(e.alternative_hours),
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
        "initial_route": _route_json(dyn.initial_route),
        "final_route": _route_json(dyn.active_route),
        "track": [_latlon(c) for c in dyn.track],
        "dynamic": _voyage_json(dyn),
        "static": _voyage_json(sta),
        "events": [_event_json(e) for e in dyn.events
                   if e.decision != "no_trigger"],
        "departure_change": (_change_json(base, cmp.departure)
                             if cmp.departure is not base else None),
        "weather_updates": changes,
    })


# ----------------------------------------------------------------------
# Interactive simulation sessions ("Simulation lab"). All simulation and
# rerouting logic is in src/sim_session.py / src/rerouting.py; these
# handlers only validate requests and shape responses.
# ----------------------------------------------------------------------
SESSIONS = SS.SessionStore()
_log = logging.getLogger("nautilus")


def sim_endpoint(fn):
    """Map SessionError to its HTTP status; never expose internal errors."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SS.SessionError as e:
            return jsonify({"error": str(e)}), e.status
        except Exception:
            _log.exception("simulation lab request failed")
            return jsonify({"error": "Internal simulation error - the session "
                                     "may need a reset."}), 500
    return wrapper


def _json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise SS.SessionError("Expected a JSON object.")
    return body


def _session_state(session):
    st = session.state()
    w = session.dyn.router.weather
    base_p99 = float(np.nanpercentile(session.base.swh, 99))
    st["weather"]["overlay"] = {
        "url": f"/api/sim/sessions/{session.id}/weather_image?v={session.weather_version}",
        "legend_max_m": round(max(0.5, base_p99,
                                  float(w.swh[GRID.navigable].max())), 2),
        "note": "Overlay shows the applied weather field (base + applied "
                "disturbances); only wave height changes."}
    st["simulated"] = True
    return st


@app.route("/api/sim/presets")
def sim_presets():
    return jsonify({"presets": [{"name": k, "description": v}
                                for k, v in WS.PRESETS.items()],
                    "limits": SS.LIMITS, "max_disturbances": SS.MAX_DISTURBANCES,
                    "defaults": asdict(RR.RerouteConfig())})


@app.route("/api/sim/sessions", methods=["POST"])
@sim_endpoint
def sim_create():
    body = _json_body()
    origin, dest = body.get("origin"), body.get("dest")
    vessel_name = body.get("vessel", V.DEFAULT_VESSEL)
    base_name = body.get("base_weather", "typical")
    preset = body.get("preset", "none")
    enabled = body.get("rerouting_enabled", True)
    if origin not in P.PORTS or dest not in P.PORTS:
        raise SS.SessionError("Unknown port.")
    if origin == dest:
        raise SS.SessionError("Origin and destination are the same.")
    if vessel_name not in V.VESSELS:
        raise SS.SessionError("Unknown vessel.")
    if base_name not in SIM_BASE_WEATHER:
        raise SS.SessionError("Initial sea state must be one of "
                              f"{', '.join(SIM_BASE_WEATHER)} (live weather is not "
                              "used in simulations).")
    if preset not in WS.PRESETS:
        raise SS.SessionError(f"Unknown demonstration scenario {preset!r}.")
    if not isinstance(enabled, bool):
        raise SS.SessionError("rerouting_enabled must be true or false.")
    try:
        cfg = RR.config_from_dict(body.get("config"))
    except (ValueError, AttributeError) as e:
        raise SS.SessionError(f"Invalid rerouting settings: {e}") from None

    ves = V.get(vessel_name)
    base = get_weather(base_name)
    mult = get_multiplier(base_name, vessel_name, base)          # cached
    base_router = R.Router(GRID, weather=base, mult_dir=mult,
                           speed_kn=ves.service_speed_kn, time_mult=mult)
    setup = {"origin": origin, "dest": dest, "vessel": vessel_name,
             "base_weather": base_name, "preset": preset,
             "rerouting_enabled": enabled,
             "start": GRID.nearest_cell(*P.coord(origin)),
             "goal": GRID.nearest_cell(*P.coord(dest))}
    session = SESSIONS.create(lambda sid: SS.SimSession(
        sid, GRID, base, base_router, sim_router_factory(vessel_name), setup, cfg))
    return jsonify(_session_state(session)), 201


def _with_session(sid, action):
    session = SESSIONS.get(sid)
    if not session.lock.acquire(blocking=False):
        raise SS.Conflict("Session is busy with another operation - try again.")
    try:
        action(session)
        return jsonify(_session_state(session))
    finally:
        session.lock.release()


@app.route("/api/sim/sessions/<sid>", methods=["GET"])
@sim_endpoint
def sim_get(sid):
    return _with_session(sid, lambda s: None)


@app.route("/api/sim/sessions/<sid>", methods=["DELETE"])
@sim_endpoint
def sim_delete(sid):
    SESSIONS.delete(sid)
    return jsonify({"deleted": sid})


@app.route("/api/sim/sessions/<sid>/step", methods=["POST"])
@sim_endpoint
def sim_step(sid):
    expected = _json_body().get("expected_step")
    if isinstance(expected, bool) or not isinstance(expected, int):
        raise SS.SessionError("expected_step (integer) is required.")
    return _with_session(sid, lambda s: s.advance(expected))


@app.route("/api/sim/sessions/<sid>/weather", methods=["POST"])
@sim_endpoint
def sim_weather(sid):
    items = _json_body().get("disturbances")
    return _with_session(sid, lambda s: s.set_draft(items))


@app.route("/api/sim/sessions/<sid>/weather/apply", methods=["POST"])
@sim_endpoint
def sim_weather_apply(sid):
    return _with_session(sid, lambda s: s.apply_pending())


@app.route("/api/sim/sessions/<sid>/weather/discard", methods=["POST"])
@sim_endpoint
def sim_weather_discard(sid):
    return _with_session(sid, lambda s: s.discard_pending())


@app.route("/api/sim/sessions/<sid>/schedule/cancel", methods=["POST"])
@sim_endpoint
def sim_cancel_schedule(sid):
    return _with_session(sid, lambda s: s.cancel_schedule())


@app.route("/api/sim/sessions/<sid>/reset", methods=["POST"])
@sim_endpoint
def sim_reset(sid):
    return _with_session(sid, lambda s: s.reset())


@app.route("/api/sim/sessions/<sid>/weather_image")
@sim_endpoint
def sim_weather_image(sid):
    session = SESSIONS.get(sid)
    version, w = session.weather_snapshot          # no session lock: steps go on
    with session.image_lock:
        if session._png is None or session._png[0] != version:
            vmax = max(0.5, float(np.nanpercentile(session.base.swh, 99)),
                       float(w.swh[GRID.navigable].max()))
            session._png = (version, _swh_png(w.swh, vmax))
        png = session._png[1]
    resp = send_file(io.BytesIO(png), mimetype="image/png")
    resp.headers["Cache-Control"] = "private, max-age=3600"   # URL is versioned
    return resp


if __name__ == "__main__":
    # HOST defaults to 127.0.0.1 (unchanged local-run behavior). The Docker
    # image sets HOST=0.0.0.0 so the Flask dev server is reachable from
    # outside its container via `docker run -p` - see docker/Dockerfile.
    print(f"[server] http://localhost:{C.PORT}  (bound to {C.HOST})")
    app.run(host=C.HOST, port=C.PORT, debug=False, threaded=True)
