"""
Routing tests: initial routes, re-routing from a vessel's current position,
and route metric consistency (distance, cost, travel time).

Uses the committed data/processed/ artifacts (grid, weather, speed model).
Run from the repo root:  python -m unittest discover -s tests -v
"""
import unittest
import warnings

import numpy as np

import config as C
from src import (grid as G, weather as W, routing as R, ports as P,
                 vessel as V, ml_model as ML, geo)
from src.evaluate import VOYAGES

# Route distances (km) and ML travel-time estimates (h) for the evaluation
# voyages, (Dijkstra, A* + ML), as in data/processed/evaluation.csv
# (scenario "rough", General Cargo). Distances guard that route selection
# is unchanged; hours were corrected in Loop 007 (ML speed model instead
# of a constant 18 kn).
BASELINE_KM = {
    ("Mumbai (JNPT)", "Chennai (Tamil Nadu)"): (2953.6, 2954.9),
    ("Kandla (Gujarat)", "Cochin (Kerala)"): (1780.2, 1780.3),
    ("Cochin (Kerala)", "Dubai / Jebel Ali (UAE)"): (2771.2, 3068.9),
    ("Visakhapatnam (AP)", "Colombo (Sri Lanka)"): (1697.0, 1701.4),
    ("Chennai (Tamil Nadu)", "Port Blair (Andaman)"): (1612.2, 1621.7),
}
BASELINE_H = {
    ("Mumbai (JNPT)", "Chennai (Tamil Nadu)"): (114.5, 114.4),
    ("Kandla (Gujarat)", "Cochin (Kerala)"): (70.9, 70.9),
    ("Cochin (Kerala)", "Dubai / Jebel Ali (UAE)"): (135.0, 128.9),
    ("Visakhapatnam (AP)", "Colombo (Sri Lanka)"): (68.6, 68.6),
    ("Chennai (Tamil Nadu)", "Port Blair (Andaman)"): (68.7, 66.6),
}

ORIGIN, DEST = "Mumbai (JNPT)", "Chennai (Tamil Nadu)"


def setUpModule():
    global grid, weather, model, cargo, mult, dijkstra_router, astar_router
    with warnings.catch_warnings():
        # speed_model.joblib was pickled with an older scikit-learn
        # (known, see docs/loop-engineering/BLOCKERS.md C5).
        warnings.simplefilter("ignore")
        model = ML.load()
    grid = G.load_grid()
    weather = W.load_weather(grid, "rough")
    cargo = V.get("General Cargo")
    mult = ML.build_multiplier_grid(grid, weather, cargo, model)
    # Same set-up as evaluate.py: both routers estimate travel time with
    # the ML speed model; only the search objective differs.
    timing = {"speed_kn": cargo.service_speed_kn, "time_mult": mult}
    dijkstra_router = R.Router(grid, **timing)
    astar_router = R.Router(grid, weather=weather, mult_dir=mult, **timing)


# (name, router getter, use_weather, use_heuristic)
ALGORITHMS = [
    ("Dijkstra", lambda: dijkstra_router, False, False),
    ("A*", lambda: astar_router, True, True),
]


class RouteChecks(unittest.TestCase):
    def assertValidRoute(self, res, start, goal):
        self.assertTrue(res.found)
        self.assertEqual(tuple(res.cells[0]), tuple(start))
        self.assertEqual(tuple(res.cells[-1]), tuple(goal))
        self.assertEqual(len(res.cells), len(res.latlon))
        for r, c in res.cells:
            self.assertTrue(grid.in_bounds(r, c), (r, c))
            self.assertTrue(grid.navigable[r, c], f"non-navigable cell {(r, c)}")
        for (r1, c1), (r2, c2) in zip(res.cells, res.cells[1:]):
            step = (r2 - r1, c2 - c1)
            self.assertIn(step, R._OFF, f"non-adjacent step {(r1, c1)}->{(r2, c2)}")

    def independent_cost(self, router, cells, use_weather):
        """Step-by-step cost recomputed from first principles (haversine x
        multiplier), not via Router.path_cost."""
        total = 0.0
        for (r1, c1), (r2, c2) in zip(cells, cells[1:]):
            km = float(geo.haversine_km(grid.lats[r1], grid.lons[c1],
                                        grid.lats[r2], grid.lons[c2]))
            if use_weather:
                km *= float(router.mult_dir[r1, c1, R._OFF.index((r2 - r1, c2 - c1))])
            total += km
        return total


class InitialRouteTests(RouteChecks):
    def test_evaluation_voyages_unchanged(self):
        for origin, dest in VOYAGES:
            s = grid.nearest_cell(*P.coord(origin))
            g = grid.nearest_cell(*P.coord(dest))
            for i, (name, router, uw, uh) in enumerate(ALGORITHMS):
                with self.subTest(voyage=f"{origin} -> {dest}", algorithm=name):
                    res = router().search(s, g, uw, uh)
                    self.assertValidRoute(res, s, g)
                    self.assertEqual(res.distance_km, BASELINE_KM[(origin, dest)][i])
                    self.assertEqual(res.time_hours, BASELINE_H[(origin, dest)][i])
                    self.assertEqual(res.time_basis, "ml_speed")
            # A* minimises ML travel time, so it is never slower than the
            # distance-optimal Dijkstra route under the same time model.
            h_dij, h_astar = BASELINE_H[(origin, dest)]
            self.assertLessEqual(h_astar, h_dij)

    def test_route_cost(self):
        s = grid.nearest_cell(*P.coord(ORIGIN))
        g = grid.nearest_cell(*P.coord(DEST))
        for name, router, uw, uh in ALGORITHMS:
            with self.subTest(algorithm=name):
                res = router().search(s, g, uw, uh)
                self.assertAlmostEqual(res.cost, router().path_cost(res.cells, uw), places=6)
                self.assertAlmostEqual(res.cost, self.independent_cost(router(), res.cells, uw),
                                       delta=1e-6 * res.cost)
                if uw:
                    # weather multipliers are >= 1
                    self.assertGreaterEqual(res.cost, res.distance_km - 0.05)
                else:
                    # pure-distance search: cost is the route length
                    self.assertAlmostEqual(res.cost, res.distance_km, delta=0.05)


class RerouteTests(RouteChecks):
    def test_reroute_from_intermediate_positions(self):
        s = grid.nearest_cell(*P.coord(ORIGIN))
        g = grid.nearest_cell(*P.coord(DEST))
        for name, router, uw, uh in ALGORITHMS:
            active = router().search(s, g, uw, uh)
            for frac in (0.1, 0.5, 0.9):
                i = int(len(active.cells) * frac)
                pos = active.cells[i]
                with self.subTest(algorithm=name, progress=frac):
                    new = router().search(pos, active.cells[-1], uw, uh)
                    self.assertValidRoute(new, pos, g)
                    self.assertAlmostEqual(new.cost, router().path_cost(new.cells, uw), places=6)
                    self.assertAlmostEqual(new.cost, self.independent_cost(router(), new.cells, uw),
                                           delta=1e-6 * new.cost)
                    # Same weather -> the optimal reroute costs exactly what
                    # the rest of the active route costs.
                    remaining = router().path_cost(active.cells[i:], uw)
                    self.assertAlmostEqual(new.cost, remaining, delta=1e-6 * remaining)
                    self.assertLess(new.distance_km, active.distance_km)

    def test_reroute_from_off_route_position(self):
        # Vessel pushed off its planned track, in the open Arabian Sea.
        pos = grid.nearest_cell(12.0, 68.0)
        g = grid.nearest_cell(*P.coord(DEST))
        for name, router, uw, uh in ALGORITHMS:
            with self.subTest(algorithm=name):
                new = router().search(pos, g, uw, uh)
                self.assertValidRoute(new, pos, g)
                self.assertAlmostEqual(new.cost, router().path_cost(new.cells, uw), places=6)

    def test_reroute_at_destination(self):
        g = grid.nearest_cell(*P.coord(DEST))
        res = dijkstra_router.search(g, g, False, False)
        self.assertValidRoute(res, g, g)
        self.assertEqual(res.cost, 0.0)
        self.assertEqual(res.distance_km, 0.0)


class InvalidPositionTests(unittest.TestCase):
    def setUp(self):
        self.goal = grid.nearest_cell(*P.coord(DEST))
        nav = grid.navigable
        # Non-navigable cell directly next to navigable water (inside the
        # coastal buffer) - previously produced a route starting on it.
        edge = np.argwhere(~nav[1:-1, 1:-1] & (nav[:-2, 1:-1] | nav[2:, 1:-1]))
        self.edge = tuple(int(x) + 1 for x in edge[0])
        self.land = tuple(int(x) for x in np.argwhere(grid.elevation > 0)[0])

    def test_invalid_start(self):
        bad = [(-1, 5), (5, -1), (grid.nlat, 0), (0, grid.nlon), self.land, self.edge]
        for start in bad:
            for name, router, uw, uh in ALGORITHMS:
                with self.subTest(start=start, algorithm=name):
                    with self.assertRaisesRegex(ValueError, "start"):
                        router().search(start, self.goal, uw, uh)

    def test_invalid_goal(self):
        for goal in [(-1, 5), self.land, self.edge]:
            with self.subTest(goal=goal):
                with self.assertRaisesRegex(ValueError, "goal"):
                    dijkstra_router.search(self.goal, goal, False, False)

    def test_path_cost_rejects_non_adjacent_cells(self):
        with self.assertRaises(ValueError):
            dijkstra_router.path_cost([(10, 10), (10, 12)], False)


if __name__ == "__main__":
    unittest.main()


def ml_hours_independent(cells, w, ves):
    """Travel time (h) of a path computed directly from the RF model, one
    prediction per segment - not via build_multiplier_grid / Router."""
    lats, lons, res = grid.lats, grid.lons, C.GRID_RES
    mwd = w.mwd_deg()
    km, swh, rel, mwp = [], [], [], []
    for (r1, c1), (r2, c2) in zip(cells, cells[1:]):
        km.append(float(geo.haversine_km(lats[r1], lons[c1], lats[r2], lons[c2])))
        heading = geo.bearing_deg(lats[r1], 0.0, lats[r2], (c2 - c1) * res)
        rel.append(abs((heading - mwd[r1, c1] + 180.0) % 360.0 - 180.0))
        swh.append(w.swh[r1, c1])
        mwp.append(w.mwp[r1, c1])
    speed = ML.predict_speed(model, swh, rel, mwp, ves)
    # Same bounds as the cost model: never faster than service speed, never
    # slower than service / MAX_WEATHER_MULT.
    speed = np.clip(speed, ves.service_speed_kn / C.MAX_WEATHER_MULT,
                    ves.service_speed_kn)
    return float(np.sum(np.array(km) / (speed * 1.852)))


class TravelTimeTests(RouteChecks):
    @classmethod
    def setUpClass(cls):
        cls.s = grid.nearest_cell(*P.coord(ORIGIN))
        cls.g = grid.nearest_cell(*P.coord(DEST))
        cls.dij = dijkstra_router.search(cls.s, cls.g, False, False)
        cls.ast = astar_router.search(cls.s, cls.g, True, True)

    def test_distance_matches_segments(self):
        for res in (self.dij, self.ast):
            seg = sum(float(geo.haversine_km(*a, *b))
                      for a, b in zip(res.latlon, res.latlon[1:]))
            self.assertEqual(res.distance_km, round(seg, 1))
            self.assertAlmostEqual(dijkstra_router.path_cost(res.cells, False),
                                   seg, delta=1e-6 * seg)

    def test_ml_time_matches_independent_calculation(self):
        for res in (self.dij, self.ast):
            with self.subTest(algorithm=res.algorithm):
                ref = ml_hours_independent(res.cells, weather, cargo)
                hours = astar_router.path_hours(res.cells)
                self.assertAlmostEqual(hours, ref, delta=1e-5 * ref)
                self.assertEqual(res.time_hours, round(hours, 1))

    def test_ml_cost_is_travel_time(self):
        # ML cost = km x service/predicted speed, so cost / service km/h = h
        kmh = cargo.service_speed_kn * 1.852
        self.assertAlmostEqual(self.ast.cost / kmh,
                               astar_router.path_hours(self.ast.cells), places=9)
        # Dijkstra's cost is distance, not time
        self.assertAlmostEqual(self.dij.cost, self.dij.distance_km, delta=0.05)
        self.assertGreater(self.dij.time_hours, self.dij.cost / kmh)

    def test_analytic_cost_is_not_reported_as_time(self):
        analytic = R.Router(grid, weather=weather, speed_kn=cargo.service_speed_kn)
        res = analytic.search(self.s, self.g, True, True)
        self.assertEqual(res.time_basis, "calm_water")
        calm = analytic.path_hours(res.cells)
        self.assertAlmostEqual(calm * cargo.service_speed_kn * 1.852,
                               analytic.path_cost(res.cells, False), places=6)
        self.assertNotAlmostEqual(res.cost / (cargo.service_speed_kn * 1.852),
                                  calm, places=0)

    def test_default_router_keeps_calm_water_18kn(self):
        res = R.Router(grid).search(self.s, self.g, False, False)
        self.assertEqual(res.time_basis, "calm_water")
        self.assertAlmostEqual(res.time_hours, res.distance_km / (18.0 * 1.852),
                               delta=0.06)

    def test_vessel_profiles(self):
        hours = {}
        for name, ves in V.VESSELS.items():
            m = ML.build_multiplier_grid(grid, weather, ves, model)
            router = R.Router(grid, speed_kn=ves.service_speed_kn, time_mult=m)
            hours[name] = router.path_hours(self.ast.cells)
            calm = self.ast.distance_km / (ves.service_speed_kn * 1.852)
            self.assertGreater(hours[name], calm)          # weather slows
            ref = ml_hours_independent(self.ast.cells, weather, ves)
            self.assertAlmostEqual(hours[name], ref, delta=1e-5 * ref)
        self.assertEqual(len(set(round(h, 3) for h in hours.values())), 5)
        self.assertLess(hours["Container Ship"], hours["General Cargo"])

    def test_weather_changes_travel_time(self):
        from src import weather_sim as WS
        calm_w = W.load_weather(grid, "typical")
        storm_w = WS.perturb_waves(calm_w, grid, self.ast.latlon[len(self.ast.cells) // 2],
                                   120.0, 6.0)
        hours = {}
        for name, w in (("typical", calm_w), ("storm", storm_w), ("rough", weather)):
            m = ML.build_multiplier_grid(grid, w, cargo, model)
            router = R.Router(grid, speed_kn=cargo.service_speed_kn, time_mult=m)
            hours[name] = router.path_hours(self.ast.cells)
            ref = ml_hours_independent(self.ast.cells, w, cargo)
            self.assertAlmostEqual(hours[name], ref, delta=1e-5 * ref)
        self.assertGreater(hours["storm"], hours["typical"])
        self.assertGreater(hours["rough"], hours["typical"])
