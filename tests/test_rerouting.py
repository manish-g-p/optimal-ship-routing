"""
Dynamic rerouting tests: simulated voyages with scheduled weather updates.

Uses the committed data/processed/ artifacts and the ML speed-based cost
model (as in evaluate.py). Deterministic - no randomness, no network.
Run from the repo root:  python -m unittest discover -s tests -v
"""
import copy
import unittest
import warnings

from src import (grid as G, weather as W, routing as R, ports as P,
                 vessel as V, ml_model as ML, weather_sim as WS,
                 rerouting as RR)

ORIGIN, DEST = "Cochin (Kerala)", "Dubai / Jebel Ali (UAE)"


def setUpModule():
    global grid, base, make, start, goal, initial
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # sklearn pickle version skew
        model = ML.load()
    grid = G.load_grid()
    base = W.load_weather(grid, "typical")
    factory = RR.router_factory(grid, V.get("General Cargo"), model)
    routers = {}                             # id(weather) -> (weather, Router)

    def make(weather):
        # Router.search/path_cost do not mutate the router, so routers can
        # be shared between simulations (keeps the suite fast).
        if id(weather) not in routers:
            routers[id(weather)] = (weather, factory(weather))
        return routers[id(weather)][1]

    start = grid.nearest_cell(*P.coord(ORIGIN))
    goal = grid.nearest_cell(*P.coord(DEST))
    initial = make(base).search(start, goal, True, True)


_scenarios = {}


def run(name, config=None, make_router=None):
    if name not in _scenarios:
        _scenarios[name] = WS.scenario(name, grid, base, initial)
    depart, updates = _scenarios[name]
    return RR.simulate(grid, start, goal, depart, make_router or make,
                       updates, config)


class VoyageChecks(unittest.TestCase):
    def assertValidVoyage(self, res):
        self.assertTrue(res.arrived)
        self.assertEqual(res.track[0], start)
        self.assertEqual(res.track[-1], goal)
        for r, c in res.track:
            self.assertTrue(grid.navigable[r, c], (r, c))
        for (r1, c1), (r2, c2) in zip(res.track, res.track[1:]):
            self.assertIn((r2 - r1, c2 - c1), R._OFF)       # no jumps
        self.assertEqual(tuple(res.active_route.cells[-1]), goal)

    def assertNoReroute(self, res):
        self.assertEqual(res.reroutes, [])
        self.assertIs(res.active_route, res.initial_route)
        self.assertEqual(res.track, [tuple(c) for c in res.initial_route.cells])


class StableWeatherTests(VoyageChecks):           # Scenario A
    def test_stable_weather_keeps_route(self):
        res = run("stable")
        self.assertValidVoyage(res)
        self.assertNoReroute(res)
        self.assertEqual({e.decision for e in res.events}, {"no_trigger"})
        self.assertAlmostEqual(res.sailed_cost, initial.cost, delta=1e-6 * initial.cost)

    def test_vessel_progress(self):
        cfg = RR.RerouteConfig()
        res = run("stable", cfg)
        # evaluated at every step, from the cell reached by then
        for e in res.events:
            self.assertEqual(e.cell, res.track[e.step * cfg.cells_per_step])
        n = len(initial.cells) - 1
        self.assertEqual(res.steps, -(-n // cfg.cells_per_step))
        # remaining cost shrinks as the voyage progresses
        costs = [e.remaining_cost for e in res.events]
        self.assertEqual(costs, sorted(costs, reverse=True))

    def test_persistent_trigger_does_not_repeat_searches(self):
        # threshold below the calm sea state -> trigger at every step, but
        # nothing changes, so no alternative search is ever repeated
        res = run("stable", RR.RerouteConfig(swh_trigger_m=0.0))
        self.assertNoReroute(res)
        self.assertEqual({e.decision for e in res.events}, {"unchanged"})


class AdverseWeatherTests(VoyageChecks):          # Scenario B
    def test_adverse_storm_adopts_alternative(self):
        cfg = RR.RerouteConfig()
        res = run("adverse", cfg)
        self.assertValidVoyage(res)
        self.assertEqual(len(res.reroutes), 1)
        ev = res.reroutes[0]
        self.assertEqual(ev.step, 2)
        self.assertTrue(ev.triggers)
        # rerouted from the vessel's current position, not the origin
        i = ev.step * cfg.cells_per_step
        self.assertEqual(ev.cell, tuple(initial.cells[i]))
        self.assertEqual(tuple(res.active_route.cells[0]), ev.cell)
        # remaining route = completed cells excluded, same cost model as
        # the alternative (router built from the updated weather)
        storm_router = make(_scenarios["adverse"][1][2])
        self.assertAlmostEqual(ev.remaining_cost,
                               storm_router.path_cost(initial.cells[i:], True), places=6)
        self.assertAlmostEqual(ev.planned_cost,
                               make(base).path_cost(initial.cells[i:], True), places=6)
        self.assertAlmostEqual(ev.alternative_cost, res.active_route.cost, places=6)
        self.assertAlmostEqual(ev.alternative_cost,
                               storm_router.path_cost(res.active_route.cells, True), places=6)
        self.assertGreaterEqual(ev.gain_rel, cfg.min_gain)
        # after adoption the vessel follows the new route
        self.assertEqual(res.track[i:], [tuple(c) for c in res.active_route.cells])

    def test_adverse_storm_beats_static_voyage(self):
        dyn = run("adverse")
        sta = run("adverse", RR.RerouteConfig(enabled=False))
        self.assertNoReroute(sta)
        self.assertLess(dyn.sailed_cost, sta.sailed_cost)

    def test_alternative_below_threshold_is_not_adopted(self):
        res = run("adverse", RR.RerouteConfig(min_gain=0.5))
        self.assertNoReroute(res)
        ev = next(e for e in res.events if e.decision == "retained")
        self.assertGreater(ev.gain, 0)
        self.assertLess(ev.gain_rel, 0.5)

    def test_worsening_storm(self):
        res = run("worsening")
        self.assertValidVoyage(res)
        self.assertEqual(len(res.reroutes), 1)

    def test_improving_alternative_is_adopted(self):
        res = run("improving_alt")
        self.assertValidVoyage(res)
        self.assertEqual(len(res.reroutes), 1)
        self.assertIn("periodic re-check", "; ".join(res.reroutes[0].triggers))
        self.assertLess(res.active_route.distance_km, res.initial_route.distance_km)


class InsufficientImprovementTests(VoyageChecks):  # Scenario C
    def test_minor_change_keeps_route(self):
        cfg = RR.RerouteConfig()
        res = run("minor", cfg)
        self.assertValidVoyage(res)
        self.assertNoReroute(res)
        searched = [e for e in res.events if e.decision == "retained"]
        self.assertTrue(searched)                 # it did look ...
        for e in searched:                        # ... but the gain was negligible
            self.assertLess(e.gain_rel, cfg.min_gain)


class RepeatedWeatherChangeTests(VoyageChecks):    # Scenario D
    def test_cooldown_and_interval(self):
        cfg = RR.RerouteConfig(eval_interval=2, cooldown_steps=4)
        res = run("shifting", cfg)
        self.assertValidVoyage(res)
        self.assertTrue(all(e.step % 2 == 0 for e in res.events))
        steps = [e.step for e in res.reroutes]
        self.assertTrue(steps)
        for a, b in zip(steps, steps[1:]):
            self.assertGreaterEqual(b - a, 4)
        self.assertIn("cooldown", {e.decision for e in res.events})

    def test_cooldown_reduces_route_changes(self):
        loose = run("shifting", RR.RerouteConfig(cooldown_steps=0))
        strict = run("shifting", RR.RerouteConfig(cooldown_steps=6))
        self.assertValidVoyage(loose)
        self.assertValidVoyage(strict)
        self.assertGreater(len(loose.reroutes), 6)       # thrashing ...
        self.assertLessEqual(len(strict.reroutes), 3)    # ... is damped


class FailedAlternativeTests(VoyageChecks):       # Scenario E
    def failing_factory(self, fake_search):
        """Routers for updated weather whose search misbehaves."""
        def factory(weather):
            router = make(weather)
            if weather is base:
                return router
            fake = copy.copy(router)             # don't touch the shared one
            fake.search = fake_search
            return fake
        return factory

    def check_failure(self, fake_search):
        res = run("adverse", make_router=self.failing_factory(fake_search))
        self.assertValidVoyage(res)
        self.assertNoReroute(res)
        failed = [e for e in res.events if e.decision == "failed"]
        self.assertEqual(len(failed), 1)          # not retried: nothing changed
        return failed[0]

    def test_no_route_found(self):
        ev = self.check_failure(lambda *a: R.RouteResult("A*", found=False))
        self.assertIn("no navigable route", ev.reason)

    def test_search_raises(self):
        def boom(*a):
            raise ValueError("start cell (0, 0) is not navigable")
        ev = self.check_failure(boom)
        self.assertIn("route search failed", ev.reason)

    def test_invalid_alternative_rejected(self):
        # a "route" that restarts from the origin instead of the vessel
        ev = self.check_failure(lambda *a: initial)
        self.assertIn("does not run from the vessel", ev.reason)

    def test_invalid_departure(self):
        with self.assertRaises(ValueError):
            RR.simulate(grid, (-1, 5), goal, base, make)


if __name__ == "__main__":
    unittest.main()
