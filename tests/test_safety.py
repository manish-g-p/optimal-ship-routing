"""
Navigational safety and rerouting-geometry tests: vessel depth
feasibility, coastal clearance, soft coastal preference, infeasible
outcomes, safe alternatives, reroute continuity and the route-change
penalty. Committed data, no network.
Run from the repo root:  python -m unittest discover -s tests -v
"""
import copy
import unittest
import warnings

import numpy as np

import config as C
from src import (grid as G, weather as W, ports as P, vessel as V,
                 ml_model as ML, routing as R, rerouting as RR, weather_sim as WS)

SHALLOW = ("Kandla (Gujarat)", "Cochin (Kerala)")      # start cell 16 m deep
DEEP = ("Visakhapatnam (AP)", "Colombo (Sri Lanka)")   # endpoints 60 / 625 m
LONG = ("Cochin (Kerala)", "Dubai / Jebel Ali (UAE)")


def setUpModule():
    global grid, base, model, cells
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # sklearn pickle version skew
        model = ML.load()
    grid = G.load_grid()
    base = W.load_weather(grid, "typical")
    cells = lambda v: tuple(grid.nearest_cell(*P.coord(x)) for x in v)


def depth(c):
    return float(-grid.elevation[c[0], c[1]])


class DepthFeasibilityTests(unittest.TestCase):
    def test_required_depth(self):
        vlcc = V.get("Crude Oil Tanker (VLCC)")
        self.assertAlmostEqual(V.required_depth_m(vlcc), vlcc.draft_m * (1 + C.UKC_FRACTION))

    def test_infeasible_endpoint_gives_reason(self):
        for name in ("Crude Oil Tanker (VLCC)", "Container Ship"):
            need = V.required_depth_m(V.get(name))
            res = R.Router(grid, min_depth_m=need).search(*cells(SHALLOW), False, False)
            self.assertFalse(res.found)
            self.assertIn("start water depth 16 m", res.reason)
            self.assertIn(f"{need:.1f} m", res.reason)
        ok = R.Router(grid, min_depth_m=V.required_depth_m(V.get("General Cargo")))
        self.assertTrue(ok.search(*cells(SHALLOW), False, False).found)

    def test_depth_constraint_forces_deeper_route(self):
        s, g = cells(DEEP)
        free = R.Router(grid).search(s, g, False, False)
        self.assertLess(min(depth(c) for c in free.cells), 59.5)
        safe = R.Router(grid, min_depth_m=59.5).search(s, g, False, False)
        self.assertTrue(safe.found)
        self.assertGreaterEqual(min(depth(c) for c in safe.cells), 59.5)
        self.assertGreater(safe.distance_km, free.distance_km)       # a real detour

    def test_no_path_gives_reason(self):
        s, g = cells(DEEP)
        r = R.Router(grid, min_depth_m=50.0)
        nav = np.zeros_like(r.nav)                                    # wall everything
        nav[s[0] * r.nlon + s[1]] = nav[g[0] * r.nlon + g[1]] = True
        r.nav = nav
        res = r.search(s, g, False, False)
        self.assertFalse(res.found)
        self.assertIn("no route stays", res.reason)

    def test_grid_errors_still_raise(self):
        with self.assertRaises(ValueError):
            R.Router(grid, min_depth_m=10).search((-1, 5), cells(DEEP)[1], False, False)


class CoastalClearanceTests(unittest.TestCase):
    def test_routes_respect_clearance(self):
        for v in (DEEP, LONG):
            res = R.Router(grid).search(*cells(v), False, False)
            self.assertGreaterEqual(min(grid.dist_to_barrier_km[c] for c in res.cells),
                                    C.COAST_BUFFER_KM)

    def test_clearance_is_configurable_at_load(self):
        stored = np.load(C.GRID_FILE)["navigable"]
        self.assertTrue(np.array_equal(G.load_grid().navigable, stored))
        old = C.COAST_BUFFER_KM
        try:
            C.COAST_BUFFER_KM = 40.0
            wider = G.load_grid()
        finally:
            C.COAST_BUFFER_KM = old
        self.assertTrue(np.all(wider.dist_to_barrier_km[wider.navigable] >= 40.0))
        self.assertLess(wider.navigable.sum(), stored.sum())
        self.assertFalse(np.any(wider.navigable & ~stored))

    def test_soft_penalty_changes_choice_not_time(self):
        mult = ML.build_multiplier_grid(grid, base, V.get("General Cargo"), model)
        kw = dict(weather=base, mult_dir=mult, speed_kn=16.0, time_mult=mult)
        plain, soft = R.Router(grid, **kw), R.Router(grid, coast_penalty=0.10, **kw)
        s, g = cells(("Mumbai (JNPT)", "Chennai (Tamil Nadu)"))
        a, b = plain.search(s, g, True, True), soft.search(s, g, True, True)
        edge = lambda res: np.mean([grid.dist_to_barrier_km[c] < 30 for c in res.cells])
        self.assertLess(edge(b), edge(a))                             # less hugging
        for path in (a.cells, b.cells):                               # time model unchanged
            self.assertAlmostEqual(plain.path_hours(path), soft.path_hours(path), places=9)
            self.assertGreaterEqual(soft.path_cost(path, True), plain.path_cost(path, True))
        self.assertAlmostEqual(b.cost, soft.path_cost(b.cells, True), delta=1e-6 * b.cost)


class SafeReroutingTests(unittest.TestCase):
    def make(self, vessel):
        return RR.router_factory(grid, V.get(vessel), model)

    def test_initial_and_rerouted_paths_obey_depth(self):
        vessel = "Crude Oil Tanker (VLCC)"
        need = V.required_depth_m(V.get(vessel))
        s, g = cells(("Mumbai (JNPT)", "Chennai (Tamil Nadu)"))
        cmp = RR.compare_voyage(grid, s, g, base, self.make(vessel), "adverse")
        self.assertTrue(cmp.dynamic.reroutes)
        for track in (cmp.dynamic.track, cmp.static.track, cmp.dynamic.active_route.cells):
            self.assertGreaterEqual(min(depth(c) for c in track), need)

    def test_unsafe_candidate_rejected(self):
        make = self.make("Crude Oil Tanker (VLCC)")
        s, g = cells(LONG)
        v = RR.Voyage(grid, s, g, make(base))
        storm = WS.perturb_waves(base, grid, v.active.latlon[len(v.active.cells) // 2], 150, 6)
        router = copy.copy(make(storm))
        unsafe = R.Router(grid).search(v.position, g, False, False)   # ignores draft
        shallow = [c for c in unsafe.cells if depth(c) < router.min_depth_m]
        if not shallow:                                               # force a shallow cell
            r0, c0 = unsafe.cells[len(unsafe.cells) // 2]
            router.nav = router.nav.copy(); router.nav[r0 * router.nlon + c0] = False
        router.search = lambda *a, **k: unsafe
        v.set_router(router)
        ev, adopted = v.step()
        self.assertFalse(adopted)
        self.assertEqual(ev.decision, "failed")
        self.assertIn("not navigable for this vessel", ev.reason)

    def test_infeasible_voyage_raises_explicitly(self):
        with self.assertRaises(RR.InfeasibleRoute) as cm:
            RR.compare_voyage(grid, *cells(SHALLOW), base,
                              self.make("Crude Oil Tanker (VLCC)"), "stable")
        self.assertIn("required", str(cm.exception))


class RerouteGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.make = staticmethod(RR.router_factory(grid, V.get("General Cargo"), model))
        cls.s, cls.g = cells(LONG)
        plan = cls.make(base).search(cls.s, cls.g, True, True)
        mid = WS._point_on(plan, 0.5)
        cls.small = WS.perturb_waves(base, grid, mid, 60.0, 4.0)
        cls.large = WS.perturb_waves(base, grid, mid, 300.0, 6.0)

    def run_voyage(self, weather, cfg=None):
        v = RR.Voyage(grid, self.s, self.g, self.make(base), cfg)
        positions = []
        while not v.done:
            if v.step_no == 2:
                v.set_router(self.make(weather))
            before = v.position
            ev, adopted = v.step()
            positions.append((before, adopted, ev))
        return v, positions

    def test_reroute_continuity(self):
        v, steps = self.run_voyage(self.large)
        adopted = [(pos, ev) for pos, a, ev in steps if a]
        self.assertEqual(len(adopted), 1)
        pos, ev = adopted[0]
        self.assertEqual(tuple(v.previous_plan[0]), pos)              # replaced plan from there
        track = v.result.track
        self.assertIn(pos, track)
        self.assertEqual(v.result.active_route.cells[0], pos)         # new plan starts at vessel
        for (r1, c1), (r2, c2) in zip(track, track[1:]):              # no jumps in movement
            self.assertIn((r2 - r1, c2 - c1), R._OFF)
        self.assertGreater(ev.corridor_shift_km, 50)
        self.assertIsNotNone(ev.heading_change_deg)

    def test_deviation_penalty_uses_true_costs(self):
        cfg = RR.RerouteConfig(deviation_penalty=0.5)
        v, steps = self.run_voyage(self.large, cfg)
        ev = [e for _, a, e in steps if a][0]
        router = v.router
        self.assertAlmostEqual(ev.alternative_cost,
                               router.path_cost(v.result.active_route.cells, True), places=6)
        self.assertAlmostEqual(v.result.active_route.cost, ev.alternative_cost, places=6)

    def test_nearby_alternative_only_when_similar(self):
        # tolerance huge -> the nearby (penalised) route is taken; tolerance 0
        # -> it is taken only if it is no worse than the best route.
        _, loose = self.run_voyage(self.large, RR.RerouteConfig(deviation_penalty=0.5,
                                                                 deviation_tol=1e9))
        _, strict = self.run_voyage(self.large, RR.RerouteConfig(deviation_penalty=0.5,
                                                                  deviation_tol=0.0))
        lo = [e for _, a, e in loose if a][0]
        st = [e for _, a, e in strict if a][0]
        self.assertEqual(lo.alternative_kind, "nearby")
        self.assertEqual(st.alternative_kind, "best")
        self.assertLess(lo.corridor_shift_km, st.corridor_shift_km)
        self.assertLess(lo.gain_rel, st.gain_rel)              # the trade-off is real

    def test_deviation_penalty_keeps_useful_reroute_and_limits_shift(self):
        for storm in (self.small, self.large):
            _, plain = self.run_voyage(storm)
            _, damped = self.run_voyage(storm, RR.RerouteConfig(deviation_penalty=0.5))
            p = [e for _, a, e in plain if a]
            d = [e for _, a, e in damped if a]
            self.assertTrue(p and d)                                   # still reroutes
            self.assertLessEqual(d[0].corridor_shift_km, p[0].corridor_shift_km)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import server
        cls.client = server.app.test_client()

    def test_route_infeasible_reason(self):
        d = self.client.post("/api/route", json={"origin": SHALLOW[0], "dest": SHALLOW[1],
                                                 "vessel": "Crude Oil Tanker (VLCC)"}).get_json()
        for k in ("dijkstra", "astar"):
            self.assertFalse(d[k]["found"])
            self.assertIn("24.6 m", d[k]["reason"])

    def test_lab_and_replay_infeasible(self):
        body = {"origin": SHALLOW[0], "dest": SHALLOW[1], "vessel": "Crude Oil Tanker (VLCC)"}
        r = self.client.post("/api/sim/sessions", json=body)
        self.assertEqual(r.status_code, 422)
        self.assertIn("No safe route for this vessel", r.get_json()["error"])
        r = self.client.post("/api/simulate", json={**body, "scenario": "stable"})
        self.assertEqual(r.status_code, 422)

    def test_safety_image(self):
        r = self.client.get("/api/safety_image?vessel=Crude%20Oil%20Tanker%20(VLCC)")
        self.assertEqual((r.status_code, r.mimetype), (200, "image/png"))
        self.assertGreater(int(r.headers["X-Restricted-Cells"]), 0)
        self.assertEqual(self.client.get("/api/safety_image?vessel=Raft").status_code, 400)

    def test_lab_reports_constraints_and_previous_plan(self):
        st = self.client.post("/api/sim/sessions", json={
            "origin": LONG[0], "dest": LONG[1], "vessel": "General Cargo",
            "preset": "storm_ahead"}).get_json()
        sid = st["id"]
        self.assertEqual(st["constraints"]["min_depth_m"], 10.8)
        self.assertIsNone(st["routes"]["previous"])
        for n in range(3):
            st = self.client.post(f"/api/sim/sessions/{sid}/step",
                                  json={"expected_step": n}).get_json()
        ev = [e for e in st["timeline"] if e["kind"] == "evaluation" and e["detail"]["adopted"]][0]
        self.assertIn("severe waves", ev["detail"]["cause"])
        self.assertIsNotNone(ev["detail"]["corridor_shift_km"])
        self.assertEqual(st["routes"]["previous"][0], st["reroutes"][0]["position"])
        self.assertEqual(st["routes"]["active"][0], st["reroutes"][0]["position"])


if __name__ == "__main__":
    unittest.main()
