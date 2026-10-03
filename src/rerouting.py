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

Run the scenario evaluation:  python -m src.rerouting
"""
from dataclasses import dataclass, field

import config as C
from src import routing as R

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
                          max_swh_m=swh)

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
        try:
            alt = router.search(ev.cell, goal, self.use_weather, self.use_heuristic)
            problem = self._invalid(alt, ev.cell, goal, router)
        except ValueError as e:
            alt, problem = None, f"route search failed: {e}"
        if problem:
            return self._done(ev, "failed", problem)

        ev.alternative_cost = alt.cost
        ev.gain = cost - alt.cost
        ev.gain_rel = ev.gain / cost if cost > 0 else 0.0
        if ev.gain_rel >= cfg.min_gain and ev.gain >= cfg.min_gain_abs:
            self.last_change_step = step
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
        if not all(self.grid.navigable[r, c] for r, c in alt.cells):
            return "alternative crosses non-navigable cells"
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
    steps: int = 0
    arrived: bool = False

    @property
    def reroutes(self):
        return [e for e in self.events if e.decision == "adopted"]


def router_factory(grid, vessel=None, model=None):
    """weather -> Router. With an ML speed model the cost is the ML
    speed-based multiplier (as in evaluate.py / server.py), otherwise the
    analytic wave multiplier."""
    def make(weather):
        if model is None:
            return R.Router(grid, weather=weather)
        from src import ml_model as ML
        mult = ML.build_multiplier_grid(grid, weather, vessel, model)
        return R.Router(grid, weather=weather, mult_dir=mult)
    return make


def simulate(grid, start, goal, weather, make_router, updates=None,
             config=None, max_steps=100_000):
    """Simulate a voyage from cell `start` to cell `goal`.

    weather     : Weather in force at departure.
    make_router : weather -> Router (see router_factory).
    updates     : {step: Weather} schedule (see weather_sim.scenario).

    Each step: apply that step's weather update, evaluate the active route
    (every eval_interval steps), then advance cells_per_step cells.
    """
    cfg = config or RerouteConfig()
    updates = updates or {}
    ctl = RerouteController(cfg, grid)
    router = plan_router = make_router(weather)
    active = router.search(start, goal, ctl.use_weather, ctl.use_heuristic)
    if not active.found:
        raise ValueError(f"no initial route from {start} to {goal}")

    ctl.searched(0, (0, 0))
    res = VoyageResult(initial_route=active, active_route=active,
                       track=[tuple(start)])
    idx = 0                                  # vessel = active.cells[idx]
    weather_v = route_v = 0
    last = len(active.cells) - 1
    for step in range(max_steps):
        if step in updates:
            router = make_router(updates[step])
            weather_v += 1
        if cfg.enabled and step % cfg.eval_interval == 0 and idx < last:
            ev, new = ctl.evaluate(step, active.cells[idx:], router,
                                   plan_router, (weather_v, route_v))
            res.events.append(ev)
            if new is not None:
                active, idx, last = new, 0, len(new.cells) - 1
                plan_router = router
                route_v += 1
                ctl.searched(step, (weather_v, route_v))
        nxt = min(idx + cfg.cells_per_step, last)
        res.sailed_cost += router.path_cost(active.cells[idx:nxt + 1], ctl.use_weather)
        res.track.extend(tuple(c) for c in active.cells[idx + 1:nxt + 1])
        idx = nxt
        res.steps = step + 1
        if idx == last:
            res.arrived = True
            break
    res.active_route = active
    return res


# ----------------------------------------------------------------------
# Scenario evaluation: dynamic vs static voyage under the same weather
# ----------------------------------------------------------------------
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
    initial = make(base).search(s, g, True, True)
    kmh = vessel.service_speed_kn * 1.852    # ML cost / kmh = hours

    print(f"\n=== Dynamic rerouting: {origin} -> {dest} ===")
    print(f"Base weather: {base_scenario} | Vessel: {vessel_name} | "
          f"cost = km x ML speed multiplier (hours = cost / {kmh:.1f} km/h)\n")
    for name in WS.SCENARIOS:
        depart, updates = WS.scenario(name, grid, base, initial)
        dyn = simulate(grid, s, g, depart, make, updates)
        sta = simulate(grid, s, g, depart, make, updates, RerouteConfig(enabled=False))
        saved = sta.sailed_cost - dyn.sailed_cost
        print(f"[{name}] reroutes={len(dyn.reroutes)} arrived={dyn.arrived} | "
              f"static {sta.sailed_cost / kmh:.1f} h -> dynamic "
              f"{dyn.sailed_cost / kmh:.1f} h (saved {saved / kmh:.1f} h)")
        for e in dyn.events:
            if e.decision != "no_trigger":
                print(f"   step {e.step:>3} {e.decision:<9} {e.reason}"
                      f"  [{'; '.join(e.triggers)}]")


if __name__ == "__main__":
    run()
