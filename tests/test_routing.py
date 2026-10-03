"""
Routing tests: initial routes + re-routing from a vessel's current position.

Uses the committed data/processed/ artifacts (grid, weather, speed model).
Run from the repo root:  python -m unittest discover -s tests -v
"""
import unittest
import warnings

import numpy as np

from src import (grid as G, weather as W, routing as R, ports as P,
                 vessel as V, ml_model as ML, geo)
from src.evaluate import VOYAGES

# Route distances (km) for the evaluation voyages as recorded in the
# committed data/processed/evaluation.csv (scenario "rough", General Cargo,
# A* + ML) - guards that initial route generation is unchanged.
BASELINE_KM = {
    ("Mumbai (JNPT)", "Chennai (Tamil Nadu)"): (2953.6, 2954.9),
    ("Kandla (Gujarat)", "Cochin (Kerala)"): (1780.2, 1780.3),
    ("Cochin (Kerala)", "Dubai / Jebel Ali (UAE)"): (2771.2, 3068.9),
    ("Visakhapatnam (AP)", "Colombo (Sri Lanka)"): (1697.0, 1701.4),
    ("Chennai (Tamil Nadu)", "Port Blair (Andaman)"): (1612.2, 1621.7),
}

ORIGIN, DEST = "Mumbai (JNPT)", "Chennai (Tamil Nadu)"


def setUpModule():
    global grid, weather, dijkstra_router, astar_router
    with warnings.catch_warnings():
        # speed_model.joblib was pickled with an older scikit-learn
        # (known, see docs/loop-engineering/BLOCKERS.md Q6).
        warnings.simplefilter("ignore")
        model = ML.load()
    grid = G.load_grid()
    weather = W.load_weather(grid, "rough")
    mult = ML.build_multiplier_grid(grid, weather, V.get("General Cargo"), model)
    dijkstra_router = R.Router(grid)
    astar_router = R.Router(grid, weather=weather, mult_dir=mult)


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
