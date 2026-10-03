"""
Interactive voyage simulation sessions (the web "Simulation lab").

A SimSession wraps two rerouting.Voyage steppers that always see the same
weather: the voyage as configured (rerouting on or off) and a no-rerouting
twin for comparison. Weather is the base field plus a list of
disturbances (weather_sim.apply_disturbances); it never modifies the base
grid or any dataset.

Weather update semantics
  * set_draft(list)  - the user's proposed disturbance list becomes
                       PENDING. Routing does not see it yet.
  * apply_pending()  - pending becomes APPLIED immediately (between
                       steps). The next step's evaluation uses it.
  * step()           - 1. apply pending changes (if any) and any preset
                          update scheduled for this step;
                       2. evaluate the active route and maybe reroute
                          (rerouting.RerouteController, unchanged);
                       3. advance the vessel cells_per_step cells.
  Preset updates replace only the preset's own disturbances; manual ones
  are kept.

Sessions are in memory, in one process (the Flask dev server is a single
process). They are not shared between processes, are capped at
MAX_SESSIONS, and expire after SESSION_TTL_S without use.
"""
import itertools
import math
import re
import threading
import time
import uuid
from dataclasses import asdict, replace

import numpy as np

import config as C
from src import geo, rerouting as RR, weather_sim as WS

MAX_SESSIONS = 8
SESSION_TTL_S = 30 * 60
MAX_DISTURBANCES = 12
MAX_TIMELINE = 2000
LIMITS = {"lat": (C.LAT_MIN, C.LAT_MAX), "lon": (C.LON_MIN, C.LON_MAX),
          "radius_km": (10.0, 3000.0), "delta_m": (-6.0, 8.0)}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,16}$")


class SessionError(Exception):
    status = 400


class NotFound(SessionError):
    status = 404


class Conflict(SessionError):
    status = 409


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------
def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise SessionError(f"{name} must be a finite number")
    lo, hi = LIMITS[name]
    if not lo <= value <= hi:
        raise SessionError(f"{name} must be between {lo:g} and {hi:g}")
    return float(value)


def validate_disturbances(items):
    """Normalized copy of a disturbance list; SessionError if invalid.
    Items: {lat, lon, radius_km, delta_m, id?, origin?}."""
    if not isinstance(items, list):
        raise SessionError("disturbances must be a list")
    if len(items) > MAX_DISTURBANCES:
        raise SessionError(f"at most {MAX_DISTURBANCES} disturbances")
    out, seen = [], set()
    for i, d in enumerate(items):
        if not isinstance(d, dict):
            raise SessionError(f"disturbance {i + 1} must be an object")
        try:
            norm = {k: _number(d.get(k), k) for k in LIMITS}
        except SessionError as e:
            raise SessionError(f"disturbance {i + 1}: {e}") from None
        if norm["delta_m"] == 0:
            raise SessionError(f"disturbance {i + 1}: delta_m must not be 0")
        did = d.get("id")
        if did is not None and (not isinstance(did, str) or not _ID_RE.match(did)):
            raise SessionError(f"disturbance {i + 1}: invalid id")
        if did is not None and did in seen:
            raise SessionError(f"duplicate disturbance id {did!r}")
        origin = d.get("origin", "manual")
        if origin not in ("manual", "preset"):
            raise SessionError(f"disturbance {i + 1}: invalid origin")
        norm.update(id=did, origin=origin)
        seen.add(did)
        out.append(norm)
    return out


def _signature(disturbances):
    return tuple(sorted((d["lat"], d["lon"], d["radius_km"], d["delta_m"])
                        for d in disturbances))


def _describe(d):
    kind = "storm" if d["delta_m"] > 0 else "calm patch"
    return (f"{d['id']} {kind} {d['delta_m']:+.1f} m, σ {d['radius_km']:.0f} km "
            f"at {d['lat']:.2f}°N {d['lon']:.2f}°E")


def _diff(old, new):
    """Human-readable list of changes between two disturbance lists."""
    before = {d["id"]: d for d in old}
    after = {d["id"]: d for d in new}
    out = [f"added {_describe(d)}" for i, d in after.items() if i not in before]
    out += [f"removed {_describe(d)}" for i, d in before.items() if i not in after]
    for i in before.keys() & after.keys():
        a, b = before[i], after[i]
        what = []
        if (a["lat"], a["lon"]) != (b["lat"], b["lon"]):
            what.append(f"moved to {b['lat']:.2f}°N {b['lon']:.2f}°E")
        if a["delta_m"] != b["delta_m"]:
            verb = "intensified" if abs(b["delta_m"]) > abs(a["delta_m"]) else "weakened"
            what.append(f"{verb} to {b['delta_m']:+.1f} m")
        if a["radius_km"] != b["radius_km"]:
            what.append(f"resized to σ {b['radius_km']:.0f} km")
        if what:
            out.append(f"{i} " + ", ".join(what))
    return sorted(out)


# ----------------------------------------------------------------------
# Session
# ----------------------------------------------------------------------
class SimSession:
    def __init__(self, sid, grid, base, base_router, make_router, setup,
                 config):
        """setup: dict(origin, dest, vessel, base_weather, preset,
        rerouting_enabled, start, goal). config: RerouteConfig."""
        self.id = sid
        self.grid, self.base = grid, base
        self.base_router, self.make_router = base_router, make_router
        self.setup = setup
        self.config = config
        self.lock = threading.Lock()
        self.image_lock = threading.Lock()      # overlay rendering only
        self._png = None                        # (weather version, PNG bytes)
        self.touched = time.monotonic()
        self._routers = {}                     # signature -> Router (bounded)
        uw, uh = RR.ALGORITHMS[config.algorithm]
        self.plan = base_router.search(setup["start"], setup["goal"], uw, uh)
        if not self.plan.found:
            raise SessionError("No navigable route between these ports.")
        self.schedule = WS.preset(setup["preset"], self.plan)
        self._init_voyage()

    # -- lifecycle -------------------------------------------------------
    def _init_voyage(self):
        self.timeline, self._seq = [], itertools.count(1)
        self.truncated = 0
        self.error = None
        self._n_manual = 0
        self.weather_version = 0
        self.pending = None
        self.last_weather_step = None
        self.applied = self._tag_preset(self.schedule.get(0, []), 0)
        router = self._router(self.applied)
        dyn_cfg = replace(self.config, enabled=self.setup["rerouting_enabled"])
        self.dyn = RR.Voyage(self.grid, self.setup["start"], self.setup["goal"],
                             router, dyn_cfg)
        # (version, Weather) replaced as one object, so readers that do not
        # hold the session lock (the overlay image) always see a matching pair.
        self.weather_snapshot = (self.weather_version, router.weather)
        self.static = RR.Voyage(self.grid, self.setup["start"], self.setup["goal"],
                                router, replace(self.config, enabled=False))
        self._log(0, "voyage_initialized", "system",
                  f"Voyage initialised: {self.setup['origin']} → {self.setup['dest']}, "
                  f"{self.setup['vessel']}, rerouting "
                  f"{'on' if self.setup['rerouting_enabled'] else 'off'}; "
                  f"planned {self.dyn.active.distance_km:,.0f} km / "
                  f"{self.dyn.active.time_hours} h (model)")
        if self.applied:
            self.last_weather_step = 0
            self._log(0, "weather_applied", "preset",
                      "Weather at departure: " + "; ".join(map(_describe, self.applied)))

    def reset(self):
        self._init_voyage()
        self._log(0, "reset", "user",
                  "Simulation reset: progress, route changes and manual weather discarded")

    # -- weather ---------------------------------------------------------
    def _tag_preset(self, items, step):
        return [{**d, "id": f"P{step}-{i + 1}", "origin": "preset"}
                for i, d in enumerate(items)]

    def _router(self, disturbances):
        if not disturbances:
            return self.base_router
        sig = _signature(disturbances)
        if sig not in self._routers:
            weather = WS.apply_disturbances(self.base, self.grid, disturbances)
            router = self.make_router(weather)          # may raise: nothing changed yet
            if len(self._routers) >= 2:
                self._routers.pop(next(iter(self._routers)))
            self._routers[sig] = router
        return self._routers[sig]

    def _apply(self, new_list, source, step, note=""):
        router = self._router(new_list)                 # build first, then mutate
        changes = _diff(self.applied, new_list)
        self.applied = new_list
        self.pending = None
        self.weather_version += 1
        self.weather_snapshot = (self.weather_version, router.weather)
        self.dyn.set_router(router)
        if not self.static.done:
            self.static.set_router(router)
        self.last_weather_step = step
        self._log(step, "weather_applied", source,
                  f"Weather applied{note}: " + ("; ".join(changes) or "no change")
                  + ". Used by the next route evaluation.")

    def set_draft(self, items):
        self._require_active()
        draft = validate_disturbances(items)
        for d in draft:                                  # highest M# in use
            if d["id"] and d["id"][0] == "M" and d["id"][1:].isdigit():
                self._n_manual = max(self._n_manual, int(d["id"][1:]))
        for d in draft:
            if d["id"] is None:
                self._n_manual += 1
                d["id"] = f"M{self._n_manual}"
        old = {d["id"]: d for d in self.applied}
        for d in draft:                                  # edited preset -> manual
            o = old.get(d["id"])
            if d["origin"] == "preset" and (o is None or _signature([o]) != _signature([d])):
                d["origin"] = "manual"
        if _signature(draft) == _signature(self.applied) and \
                {d["id"] for d in draft} == {d["id"] for d in self.applied}:
            if self.pending is not None:
                self.pending = None
                self._log(self.step, "weather_discarded", "user",
                          "Pending weather changes withdrawn")
            return
        self.pending = draft
        self._log(self.step, "weather_pending", "user",
                  "Weather change pending (not yet seen by routing): "
                  + ("; ".join(_diff(self.applied, draft)) or "reordered"))

    def apply_pending(self):
        self._require_active()
        if self.pending is None:
            raise Conflict("No pending weather changes to apply.")
        try:
            self._apply(self.pending, "user", self.step, " now by user")
        except Exception as e:                       # nothing was changed
            self._log(self.step, "error", "system",
                      f"Weather update could not be applied ({type(e).__name__}); "
                      "simulation unchanged")
            raise SessionError("Weather update failed; the simulation was not "
                               "changed.") from e

    def discard_pending(self):
        if self.pending is None:
            raise Conflict("No pending weather changes to discard.")
        self.pending = None
        self._log(self.step, "weather_discarded", "user", "Pending weather changes discarded")

    def cancel_schedule(self):
        future = [s for s in self.schedule if s > self.step]
        if not future:
            raise Conflict("No scheduled preset updates remain.")
        self.schedule = {s: v for s, v in self.schedule.items() if s <= self.step}
        self._log(self.step, "schedule_cancelled", "user",
                  f"Cancelled {len(future)} scheduled preset weather update(s)")

    # -- stepping ----------------------------------------------------------
    @property
    def step(self):
        return self.dyn.step_no

    def _require_active(self):
        if self.error:
            raise Conflict("Simulation is in an error state - reset it.")
        if self.dyn.done:
            raise Conflict("Voyage completed - reset to run again.")

    def advance(self, expected_step):
        self._require_active()
        if expected_step != self.step:
            raise Conflict(f"Step mismatch: simulation is at step {self.step}, "
                           f"request was for step {expected_step}.")
        s = self.step
        # 1. weather changes due at this step
        new_list, source = None, None
        if self.pending is not None:
            new_list, source = self.pending, "user"
        if s > 0 and s in self.schedule:
            keep = [d for d in (new_list if new_list is not None else self.applied)
                    if d["origin"] != "preset"]
            new_list = keep + self._tag_preset(self.schedule[s], s)
            source = "preset" if source is None else "user+preset"
        if new_list is not None:
            try:
                self._apply(new_list, source, s, f" at step {s}")
            except Exception as e:                   # nothing was changed
                self._log(s, "error", "system",
                          f"Weather update could not be applied ({type(e).__name__}); "
                          "simulation unchanged")
                raise SessionError("Weather update failed; the simulation was not "
                                   "changed.") from e
        try:
            # 2-3. evaluate / reroute / advance (backend controller)
            ev, adopted = self.dyn.step()
            if not self.static.done:
                self.static.step()
        except Exception as e:                       # keep state inspectable
            self.error = f"{type(e).__name__}: {e}"
            self._log(s, "error", "system", f"Simulation error at step {s}: {self.error}")
            raise
        if ev is not None:
            self._log_evaluation(ev, adopted)
        r = self.dyn.result
        self._log(s, "advanced", "engine",
                  f"Vessel advanced to step {s + 1}: {r.sailed_km:,.0f} km sailed, "
                  f"{r.sailed_hours:.1f} h (model)")
        if self.dyn.done:
            while not self.static.done:              # finish the comparison
                self.static.step()
            self._log(s, "voyage_completed", "engine",
                      f"Voyage completed in {r.sailed_hours:.1f} h, {r.sailed_km:,.0f} km, "
                      f"{len(r.reroutes)} reroute(s). Without rerouting: "
                      f"{self.static.result.sailed_hours:.1f} h (model, same weather)")

    def _log_evaluation(self, ev, adopted):
        searched = ev.decision in ("adopted", "retained", "failed")
        detail = {
            "decision": ev.decision, "reason": ev.reason,
            "triggers": list(ev.triggers),
            "searched": searched,
            "alternative_found": ev.decision in ("adopted", "retained"),
            "adopted": adopted,
            "active_route_cost": round(ev.remaining_cost, 1),
            "planned_cost": round(ev.planned_cost, 1),
            "remaining_hours": round(ev.remaining_hours, 1),
            "alternative_cost": None if ev.alternative_cost is None else round(ev.alternative_cost, 1),
            "alternative_hours": None if ev.alternative_hours is None else round(ev.alternative_hours, 1),
            "gain_pct": None if ev.gain_rel is None else round(100 * ev.gain_rel, 2),
            "max_wave_m": round(ev.max_swh_m, 2),
        }
        if adopted:
            detail["reroute_no"] = len(self.dyn.result.reroutes)
            msg = f"R{detail['reroute_no']}: alternative adopted - {ev.reason}"
        elif ev.decision == "no_trigger":
            msg = f"Route evaluated: no trigger (max wave {ev.max_swh_m:.1f} m)"
        elif ev.decision == "retained":
            msg = f"Alternative found but rejected - {ev.reason}"
        elif ev.decision == "failed":
            msg = f"Alternative search failed - {ev.reason}; current route kept"
        elif ev.decision == "cooldown":
            msg = f"Rerouting blocked by cooldown ({ev.reason})"
        else:
            msg = f"Evaluation skipped - {ev.reason}"
        self._log(ev.step, "evaluation", "engine", msg,
                  position=self._latlon(ev.cell), detail=detail)

    # -- timeline / state --------------------------------------------------
    def _log(self, step, kind, source, message, position=None, detail=None):
        self.timeline.append({"seq": next(self._seq), "step": step, "kind": kind,
                              "source": source, "message": message,
                              "position": position, "detail": detail})
        if len(self.timeline) > MAX_TIMELINE:
            self.timeline.pop(0)
            self.truncated += 1

    def _latlon(self, cell):
        return [round(float(v), 4) for v in self.grid.cell_latlon(*cell)]

    def _path(self, cells):
        return [self._latlon(c) for c in cells]

    def _heading(self):
        cells = self.dyn.remaining_cells()
        if len(cells) < 2:
            cells = self.dyn.result.track[-2:]
        if len(cells) < 2:
            return 0.0
        a, b = self._latlon(cells[0]), self._latlon(cells[1])
        return round(float(geo.bearing_deg(a[0], a[1], b[0], b[1])), 1)

    def next_evaluation_step(self):
        if not self.dyn.cfg.enabled or self.dyn.done:
            return None
        k = self.dyn.cfg.eval_interval
        return -(-self.step // k) * k

    def state(self):
        dyn, sta = self.dyn, self.static
        rem = dyn.remaining_cells()
        router = dyn.router
        r, rs = dyn.result, sta.result
        rem_h = router.path_hours(rem)
        rem_km = router.path_cost(rem, False)
        sta_rem = sta.remaining_cells()
        sta_rem_h = 0.0 if sta.done else sta.router.path_hours(sta_rem)
        swh = router.weather.swh
        nav = self.grid.navigable
        status = ("error" if self.error else "completed" if dyn.done
                  else "ready" if self.step == 0 else "in_progress")
        reroutes = [e for e in self.timeline
                    if e["kind"] == "evaluation" and e["detail"]["adopted"]]
        return {
            "id": self.id,
            "status": status, "error": self.error,
            "step": self.step,
            "setup": {k: v for k, v in self.setup.items() if k not in ("start", "goal")},
            "reroute_config": asdict(dyn.cfg),
            "origin": self._latlon(self.setup["start"]),
            "dest": self._latlon(self.setup["goal"]),
            "routes": {"initial": self._path(r.initial_route.cells),
                       "active": self._path(dyn.active.cells),
                       "route_version": dyn.route_v},
            "track": self._path(r.track),
            "vessel": {"position": self._latlon(dyn.position), "heading_deg": self._heading()},
            "metrics": {
                "progress": round(r.sailed_km / (r.sailed_km + rem_km), 4)
                if (r.sailed_km + rem_km) > 0 else 1.0,
                "sailed_km": round(r.sailed_km, 1),
                "sailed_hours": round(r.sailed_hours, 1),
                "remaining_km": round(rem_km, 1),
                "remaining_hours": round(rem_h, 1),
                "projected_total_hours": round(r.sailed_hours + rem_h, 1),
                "remaining_route_cost": round(router.path_cost(rem, True), 1),
                "reroutes": len(r.reroutes),
                "evaluations": len(r.events),
                "time_basis": router.time_basis,
            },
            "comparison_no_rerouting": {
                "sailed_hours": round(rs.sailed_hours, 1),
                "remaining_hours": round(sta_rem_h, 1),
                "projected_total_hours": round(rs.sailed_hours + sta_rem_h, 1),
                "sailed_km": round(rs.sailed_km, 1),
                "arrived": sta.done,
            },
            "weather": {
                "version": self.weather_version,
                "base_weather": self.setup["base_weather"],
                "applied": self.applied,
                "pending": self.pending,
                "last_update_step": self.last_weather_step,
                "next_evaluation_step": self.next_evaluation_step(),
                "max_wave_on_remaining_route_m": round(max(float(swh[c]) for c in rem), 2),
                "field_max_wave_m": round(float(swh[nav].max()), 2),
                "schedule": [{"step": s, "disturbances": v}
                             for s, v in sorted(self.schedule.items()) if s > self.step],
            },
            "reroutes": [{"no": e["detail"]["reroute_no"], "step": e["step"],
                          "position": e["position"], "seq": e["seq"]} for e in reroutes],
            "timeline": self.timeline,
            "timeline_truncated": self.truncated,
        }


# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------
class SessionStore:
    def __init__(self, max_sessions=MAX_SESSIONS, ttl_s=SESSION_TTL_S):
        self.max_sessions, self.ttl_s = max_sessions, ttl_s
        self._sessions = {}
        self._lock = threading.Lock()

    def _purge(self):
        now = time.monotonic()
        for sid in [s for s, x in self._sessions.items() if now - x.touched > self.ttl_s]:
            del self._sessions[sid]

    def create(self, build):
        """build(sid) -> SimSession (may raise SessionError)."""
        sid = uuid.uuid4().hex
        session = build(sid)
        with self._lock:
            self._purge()
            while len(self._sessions) >= self.max_sessions:
                oldest = min(self._sessions.values(), key=lambda x: x.touched)
                del self._sessions[oldest.id]
            self._sessions[sid] = session
        return session

    def get(self, sid):
        if not isinstance(sid, str) or not re.fullmatch(r"[0-9a-f]{32}", sid):
            raise NotFound("Unknown simulation session.")
        with self._lock:
            self._purge()
            session = self._sessions.get(sid)
        if session is None:
            raise NotFound("Simulation session not found or expired - start a new one.")
        session.touched = time.monotonic()
        return session

    def delete(self, sid):
        self.get(sid)
        with self._lock:
            self._sessions.pop(sid, None)

    def __len__(self):
        return len(self._sessions)
