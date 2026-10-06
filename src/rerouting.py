"""
Threshold-based dynamic rerouting during a simulated voyage.

  simulate()        : advances a vessel along its active route, applies
                      scheduled weather updates (see weather_sim.py) and
                      asks the controller whether to reroute.
  RerouteController : evaluates the remaining active route and decides,
                      with a few explicit rules, whether to adopt an
                      alternative from the vessel's current cell.

Route search itself is routing.Router.search(); both the remaining route
and the alternative are scored with the same Router (Router.path_cost /
RouteResult.cost), so they are always compared in the same units.

Decision per evaluation (every `eval_interval` steps):
  1. Score the remaining route under the latest weather.
  2. Triggers: max wave height on it >= swh_trigger_m, or its cost rose
     >= cost_trigger (relative) vs. the weather it was planned under, or
     the weather changed and recheck_steps have passed since the last
     search (periodic re-check, catches alternatives that became cheaper).
     No trigger -> keep the route.
  3. Within `cooldown_steps` of the last route change -> keep the route.
  4. Weather and route unchanged since the last alternative search ->
     keep the route (the search would give the same answer).
  5. Search an alternative from the current cell to the destination.
     Search failure or an invalid result -> keep the route ("failed").
  6. Adopt it only if it is >= min_gain cheaper (relative) AND
     >= min_gain_abs cheaper (absolute); otherwise keep the route.

Units: decisions compare routing COST (Router.path_cost). Reported hours
come from the Router's travel-time model (Router.path_hours) and never
feed into a decision. With the ML cost model the two are proportional
(hours = cost / (service kn x 1.852)).

compare_voyage() runs one scenario twice - with rerouting and with it
disabled (static voyage) - and is what the CLI and the Flask API use.

Run the scenario evaluation:  python -m src.rerouting
"""
import math
from dataclasses import dataclass, field, fields

import numpy as np
from scipy import ndimage

import config as C
from src import geo, routing as R

ALGORITHMS = {"astar": (True, True), "dijkstra": (False, False)}


@dataclass
class RerouteConfig:
    algorithm: str = "astar"
    enabled: bool = True                     # False -> static voyage baseline
    cells_per_step: int = C.REROUTE_CELLS_PER_STEP
    eval_interval: int = C.REROUTE_EVAL_INTERVAL
    cooldown_steps: int = C.REROUTE_COOLDOWN_STEPS
    swh_trigger_m: float = C.REROUTE_SWH_TRIGGER_M
    cost_trigger: float = C.REROUTE_COST_TRIGGER
    recheck_steps: int = C.REROUTE_RECHECK_STEPS
    min_gain: float = C.REROUTE_MIN_GAIN
    min_gain_abs: float = C.REROUTE_MIN_GAIN_ABS
    deviation_penalty: float = C.REROUTE_DEVIATION_PENALTY
    deviation_scale_km: float = C.REROUTE_DEVIATION_KM
    deviation_tol: float = C.REROUTE_DEVIATION_TOL


# RerouteConfig fields a caller (e.g. the web API) may override, with the
# smallest allowed value. Floats unless the default is an int.
_TUNABLE = {"cells_per_step": 1, "eval_interval": 1, "cooldown_steps": 0,
            "swh_trigger_m": 0.0, "cost_trigger": 0.0, "recheck_steps": 0,
            "min_gain": 0.0, "min_gain_abs": 0.0,
            "deviation_penalty": 0.0, "deviation_scale_km": 10.0,
            "deviation_tol": 0.0}


def config_from_dict(overrides=None):
    """RerouteConfig with validated overrides; ValueError on unknown keys,
    wrong types or out-of-range values."""
    cfg = RerouteConfig()
    for key, val in (overrides or {}).items():
        if key not in _TUNABLE:
            raise ValueError(f"unknown rerouting setting {key!r}")
        want_int = isinstance(getattr(cfg, key), int)
        if isinstance(val, bool) or not isinstance(val, (int, float)) \
                or not math.isfinite(val) \
                or (want_int and not float(val).is_integer()):
            raise ValueError(f"{key} must be {'an integer' if want_int else 'a number'}")
        if val < _TUNABLE[key]:
            raise ValueError(f"{key} must be >= {_TUNABLE[key]}")
        setattr(cfg, key, int(val) if want_int else float(val))
    return cfg


@dataclass
class RerouteEvent:
    """One evaluation of the active route (kept whether or not it changed)."""
    step: int
    cell: tuple                              # vessel position
    decision: str      # no_trigger | cooldown | unchanged | failed | retained | adopted
    reason: str
    triggers: tuple = ()
    remaining_cost: float = 0.0              # remaining active route, latest weather
    planned_cost: float = 0.0                # same cells, weather at planning time
    max_swh_m: float = 0.0                   # on the remaining route
    alternative_cost: float = None
    gain: float = None                       # remaining_cost - alternative_cost
    gain_rel: float = None
    # travel-time estimates (h) - reporting only, not used for decisions
    remaining_hours: float = 0.0
    alternative_hours: float = None
    # geometry of an adopted alternative (reporting only)
    alternative_kind: str = None             # "best" or "nearby" (similar benefit)
    corridor_shift_km: float = None          # max distance of new route from old plan
    length_change_km: float = None           # new route km - remaining old route km
    heading_change_deg: float = None         # vessel heading in vs. new route heading


class InfeasibleRoute(ValueError):
    """No route satisfies the safety constraints (depth, coastal clearance)."""


def distance_to_cells(cells, router):
    """(nlat, nlon) field: km from each grid cell to the nearest of `cells`."""
    mask = np.ones((router.nlat, router.nlon), dtype=bool)
    rows, cols = zip(*cells)
    mask[list(rows), list(cols)] = False
    res_km = C.GRID_RES * C.KM_PER_DEG
    return ndimage.distance_transform_edt(
        mask, sampling=[res_km, res_km * router._coslat0])


def _bearing(grid, a, b):
    return float(geo.bearing_deg(*grid.cell_latlon(*a), *grid.cell_latlon(*b)))


class RerouteController:
    def __init__(self, config, grid):
        self.cfg = config
        self.grid = grid
        self.use_weather, self.use_heuristic = ALGORITHMS[config.algorithm]
        self.last_change_step = None
        self._last_search = None             # (weather_version, route_version)
        self._last_search_step = None

    def searched(self, step, versions):
        """Record that a route was searched under `versions` at `step`."""
        self._last_search, self._last_search_step = versions, step

    def evaluate(self, step, remaining, router, plan_router, versions):
        """Decide for the remaining active route `remaining` (list of cells,
        starting at the vessel). Returns (RerouteEvent, new RouteResult|None)."""
        cfg = self.cfg
        cost = router.path_cost(remaining, self.use_weather)
        planned = plan_router.path_cost(remaining, self.use_weather)
        swh = (max(float(router.weather.swh[c]) for c in remaining)
               if router.weather is not None else 0.0)
        ev = RerouteEvent(step=step, cell=tuple(remaining[0]), decision="",
                          reason="", remaining_cost=cost, planned_cost=planned,
                          max_swh_m=swh,
                          remaining_hours=router.path_hours(remaining))

        triggers = []
        if swh >= cfg.swh_trigger_m:
            triggers.append(f"max wave {swh:.2f} m >= {cfg.swh_trigger_m} m")
        if planned > 0 and (cost - planned) / planned >= cfg.cost_trigger:
            triggers.append(f"remaining cost +{100 * (cost - planned) / planned:.1f}%"
                            f" >= {100 * cfg.cost_trigger:.1f}%")
        if (cfg.recheck_steps and versions != self._last_search
                and step - (self._last_search_step or 0) >= cfg.recheck_steps):
            triggers.append(f"periodic re-check ({cfg.recheck_steps} steps)")
        ev.triggers = tuple(triggers)
        if not triggers:
            return self._done(ev, "no_trigger", "no trigger reached")
        if (self.last_change_step is not None
                and step - self.last_change_step < cfg.cooldown_steps):
            return self._done(ev, "cooldown",
                              f"last change at step {self.last_change_step}")
        if versions == self._last_search:
            return self._done(ev, "unchanged", "weather and route unchanged "
                                               "since last alternative search")
        self.searched(step, versions)

        goal = tuple(remaining[-1])
        dist_old, extra = None, None
        if cfg.deviation_penalty > 0:
            dist_old = distance_to_cells(remaining, router)
            extra = (1.0 + cfg.deviation_penalty * np.clip(
                dist_old / cfg.deviation_scale_km, 0.0, 1.0)).ravel()
        try:
            alt = router.search(ev.cell, goal, self.use_weather, self.use_heuristic)
            problem = self._invalid(alt, ev.cell, goal, router)
            ev.alternative_kind = "best"
            if not problem and extra is not None:
                # Prefer a route closer to the current plan only when it is
                # about as good as the best one (true, unpenalised costs).
                near = router.search(ev.cell, goal, self.use_weather,
                                     self.use_heuristic, extra_cost=extra)
                if near.found and not self._invalid(near, ev.cell, goal, router):
                    near.cost = router.path_cost(near.cells, self.use_weather)
                    if near.cost <= alt.cost * (1.0 + cfg.deviation_tol):
                        alt, ev.alternative_kind = near, "nearby"
        except ValueError as e:
            alt, problem = None, f"route search failed: {e}"
        if problem:
            return self._done(ev, "failed", problem)

        ev.alternative_cost = alt.cost
        ev.alternative_hours = router.path_hours(alt.cells)
        ev.gain = cost - alt.cost
        ev.gain_rel = ev.gain / cost if cost > 0 else 0.0
        if ev.gain_rel >= cfg.min_gain and ev.gain >= cfg.min_gain_abs:
            self.last_change_step = step
            if dist_old is None:
                dist_old = distance_to_cells(remaining, router)
            ev.corridor_shift_km = float(max(dist_old[c] for c in alt.cells))
            ev.length_change_km = alt.distance_km - router.path_cost(remaining, False)
            return self._done(ev, "adopted", f"alternative {100 * ev.gain_rel:.1f}% "
                                             f"({ev.gain:.0f}) cheaper", alt)
        return self._done(ev, "retained", f"gain {100 * ev.gain_rel:.1f}% "
                                          f"({ev.gain:.0f}) below threshold")

    @staticmethod
    def _done(ev, decision, reason, alt=None):
        ev.decision, ev.reason = decision, reason
        return ev, alt

    def _invalid(self, alt, start, goal, router):
        """Reason the candidate is unusable, or None if it is valid."""
        if not alt.found:
            return "no navigable route to destination"
        if tuple(alt.cells[0]) != start or tuple(alt.cells[-1]) != goal:
            return "alternative does not run from the vessel to the destination"
        nav, nlon = router.nav, router.nlon            # vessel-specific mask
        if not all(nav[r * nlon + c] for r, c in alt.cells):
            return "alternative crosses water that is not navigable for this vessel"
        try:
            router.path_cost(alt.cells, self.use_weather)   # adjacency check
        except ValueError:
            return "alternative is not a connected path"
        return None


@dataclass
class VoyageResult:
    initial_route: R.RouteResult
    active_route: R.RouteResult              # route in force at the end
    track: list = field(default_factory=list)   # cells actually sailed
    events: list = field(default_factory=list)  # RerouteEvent per evaluation
    sailed_cost: float = 0.0  # cost of the track, each leg under the weather
                              # in force when it was sailed
    sailed_km: float = 0.0    # distance of the track
    sailed_hours: float = 0.0 # travel time of the track, each leg under the
                              # weather in force when it was sailed
    steps: int = 0
    arrived: bool = False

    @property
    def reroutes(self):
        return [e for e in self.events if e.decision == "adopted"]


def router_factory(grid, vessel=None, model=None):
    """weather -> Router. With an ML speed model the cost AND the travel
    time use the ML speed-based multiplier (as in evaluate.py / server.py);
    otherwise the cost is the analytic wave multiplier and travel time is
    calm-water time at the vessel's service speed. Every Router enforces
    the vessel's depth constraint and the configured coastal preference,
    so initial routes, alternatives and evaluations share one constraint
    set."""
    from src import vessel as V
    speed = vessel.service_speed_kn if vessel is not None else None
    safety = {"min_depth_m": V.required_depth_m(vessel) if vessel is not None else None,
              "coast_penalty": C.COAST_PENALTY}

    def make(weather):
        if model is None:
            return R.Router(grid, weather=weather, speed_kn=speed, **safety)
        from src import ml_model as ML
        mult = ML.build_multiplier_grid(grid, weather, vessel, model)
        return R.Router(grid, weather=weather, mult_dir=mult,
                        speed_kn=speed, time_mult=mult, **safety)
    return make


class Voyage:
    """A voyage that advances one step at a time (used by simulate() and by
    interactive sessions, see sim_session.py).

    Each step(): evaluate the active route (every eval_interval steps) under
    the current router, maybe adopt an alternative, then advance
    cells_per_step cells. Change the weather between steps with
    set_router(); the next evaluation uses it.
    """

    def __init__(self, grid, start, goal, router, config=None):
        self.cfg = config or RerouteConfig()
        self.grid = grid
        self.previous_plan = None            # old plan's remainder at the last adoption
        self.ctl = RerouteController(self.cfg, grid)
        self.router = self.plan_router = router
        active = router.search(start, goal, self.ctl.use_weather,
                               self.ctl.use_heuristic)
        if not active.found:
            raise InfeasibleRoute(active.reason or f"no route from {start} to {goal}")
        self.ctl.searched(0, (0, 0))
        self.result = VoyageResult(initial_route=active, active_route=active,
                                   track=[tuple(start)])
        self.idx = 0                         # vessel = active.cells[idx]
        self.step_no = 0                     # next step to run
        self.weather_v = self.route_v = 0

    @property
    def active(self):
        return self.result.active_route

    @property
    def position(self):
        return tuple(self.active.cells[self.idx])

    @property
    def done(self):
        return self.result.arrived

    def remaining_cells(self):
        return self.active.cells[self.idx:]

    def set_router(self, router):
        """New weather (cost/time model) from the next evaluation on."""
        self.router = router
        self.weather_v += 1

    def step(self):
        """Run one step. Returns (RerouteEvent or None, adopted: bool)."""
        if self.done:
            raise RuntimeError("voyage already arrived")
        cfg, res, step = self.cfg, self.result, self.step_no
        last = len(self.active.cells) - 1
        ev, adopted = None, False
        if cfg.enabled and step % cfg.eval_interval == 0 and self.idx < last:
            ev, new = self.ctl.evaluate(step, self.active.cells[self.idx:],
                                        self.router, self.plan_router,
                                        (self.weather_v, self.route_v))
            res.events.append(ev)
            if new is not None:
                self.previous_plan = list(self.active.cells[self.idx:])
                track = res.track
                if len(track) > 1:                       # heading in vs. out
                    h_in = _bearing(self.grid, track[max(0, len(track) - 4)], track[-1])
                    h_out = _bearing(self.grid, new.cells[0], new.cells[min(3, len(new.cells) - 1)])
                    ev.heading_change_deg = abs((h_out - h_in + 180.0) % 360.0 - 180.0)
                res.active_route, self.idx = new, 0
                last = len(new.cells) - 1
                self.plan_router = self.router
                self.route_v += 1
                self.ctl.searched(step, (self.weather_v, self.route_v))
                adopted = True
        nxt = min(self.idx + cfg.cells_per_step, last)
        leg = self.active.cells[self.idx:nxt + 1]
        res.sailed_cost += self.router.path_cost(leg, self.ctl.use_weather)
        res.sailed_km += self.router.path_cost(leg, False)
        res.sailed_hours += self.router.path_hours(leg)
        res.track.extend(tuple(c) for c in self.active.cells[self.idx + 1:nxt + 1])
        self.idx = nxt
        self.step_no = res.steps = step + 1
        if self.idx == last:
            res.arrived = True
        return ev, adopted


def simulate(grid, start, goal, weather, make_router, updates=None,
             config=None, max_steps=100_000):
    """Simulate a voyage from cell `start` to cell `goal`.

    weather     : Weather in force at departure.
    make_router : weather -> Router (see router_factory).
    updates     : {step: Weather} schedule (see weather_sim.scenario).

    Each step: apply that step's weather update, evaluate the active route
    (every eval_interval steps), then advance cells_per_step cells.
    """
    updates = updates or {}
    voyage = Voyage(grid, start, goal, make_router(weather), config)
    for step in range(max_steps):
        if step in updates:
            voyage.set_router(make_router(updates[step]))
        voyage.step()
        if voyage.done:
            break
    return voyage.result


# ----------------------------------------------------------------------
# Scenario evaluation: dynamic vs static voyage under the same weather
# ----------------------------------------------------------------------
@dataclass
class VoyageComparison:
    scenario: str
    departure: object         # Weather at departure
    updates: dict             # {step: Weather} applied during the voyage
    dynamic: VoyageResult     # with rerouting (given config)
    static: VoyageResult      # same weather, rerouting disabled


def compare_voyage(grid, start, goal, base, make_router, scenario,
                   config=None):
    """Run weather scenario `scenario` (see weather_sim.SCENARIOS) from
    `base` weather with rerouting, and again with rerouting disabled.
    Cost models are built once per weather field and shared by both runs."""
    from src import weather_sim as WS
    routers = {}                             # id(weather) -> (weather, Router)

    def make(weather):
        if id(weather) not in routers:
            routers[id(weather)] = (weather, make_router(weather))
        return routers[id(weather)][1]

    cfg = config or RerouteConfig()
    plan = make(base).search(start, goal, *ALGORITHMS[cfg.algorithm])
    if not plan.found:
        raise InfeasibleRoute(plan.reason or f"no route from {start} to {goal}")
    depart, updates = WS.scenario(scenario, grid, base, plan)
    static_cfg = RerouteConfig(**{f.name: getattr(cfg, f.name)
                                  for f in fields(cfg)})
    static_cfg.enabled = False
    return VoyageComparison(
        scenario, depart, updates,
        simulate(grid, start, goal, depart, make, updates, cfg),
        simulate(grid, start, goal, depart, make, updates, static_cfg))


def run(origin="Cochin (Kerala)", dest="Dubai / Jebel Ali (UAE)",
        base_scenario="typical", vessel_name="General Cargo"):
    import warnings
    from src import (grid as G, weather as W, ports as P, vessel as V,
                     ml_model as ML, weather_sim as WS)

    grid = G.load_grid()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # sklearn pickle version skew
        model = ML.load()
    vessel = V.get(vessel_name)
    base = W.load_weather(grid, base_scenario)
    make = router_factory(grid, vessel, model)
    s = grid.nearest_cell(*P.coord(origin))
    g = grid.nearest_cell(*P.coord(dest))
    print(f"\n=== Dynamic rerouting: {origin} -> {dest} ===")
    print(f"Base weather: {base_scenario} | Vessel: {vessel_name} | "
          f"cost and hours from the ML speed model (simulated)\n")
    for name in WS.SCENARIOS:
        cmp = compare_voyage(grid, s, g, base, make, name)
        dyn, sta = cmp.dynamic, cmp.static
        saved = sta.sailed_hours - dyn.sailed_hours
        print(f"[{name}] reroutes={len(dyn.reroutes)} arrived={dyn.arrived} | "
              f"static {sta.sailed_hours:.1f} h -> dynamic "
              f"{dyn.sailed_hours:.1f} h (saved {saved:.1f} h)")
        for e in dyn.events:
            if e.decision != "no_trigger":
                print(f"   step {e.step:>3} {e.decision:<9} {e.reason}"
                      f"  [{'; '.join(e.triggers)}]")


if __name__ == "__main__":
    run()
