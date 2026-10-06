"""
Integrity tests for the dynamic-rerouting evaluation (src/evaluate_rerouting).
Runs a small real subset of the matrix; the full matrix is run by
`python -m src.evaluate_rerouting`. No files are written.
Run from the repo root:  python -m unittest discover -s tests -v
"""
import math
import unittest
import warnings
from types import SimpleNamespace

import numpy as np
import pandas as pd

from src import (grid as G, weather as W, ports as P, vessel as V,
                 ml_model as ML, rerouting as RR, evaluate as E,
                 weather_sim as WS, evaluate_rerouting as ER)

SHORT = ("Chennai (Tamil Nadu)", "Port Blair (Andaman)")
SHALLOW = ("Kandla (Gujarat)", "Cochin (Kerala)")     # 16 m on the planned route


def setUpModule():
    global grid, base, factories, subset, runs, events
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # sklearn pickle version skew
        model = ML.load()
    grid = G.load_grid()
    base = W.load_weather(grid, ER.BASE_WEATHER)
    factories = {v: RR.router_factory(grid, V.get(v), model)
                 for v in ("General Cargo", "Crude Oil Tanker (VLCC)")}
    subset = (ER.build_matrix([SHORT], ["General Cargo"], ["stable", "adverse"])
              + ER.build_matrix([SHALLOW], ["Crude Oil Tanker (VLCC)"], ["stable"]))
    runs, events = ER.run_matrix(subset, grid, base, factories)


class MatrixTests(unittest.TestCase):
    def test_full_matrix_coverage(self):
        specs = ER.build_matrix()
        keys = {(s["origin"], s["dest"], s["vessel"], s["scenario"]) for s in specs}
        self.assertEqual(len(specs), 5 * 5 * 6)
        self.assertEqual(keys, {(o, d, v, sc) for o, d in E.VOYAGES
                                for v in V.VESSELS for sc in ER.SCENARIOS})

    def test_every_run_has_a_status(self):
        self.assertEqual(len(runs), len(subset))
        self.assertTrue(set(runs.status) <= {"ok", "infeasible", "draft_infeasible",
                                             "incomplete", "failed"})
        self.assertEqual(list(runs.run_id), list(range(len(subset))))


class MetricTests(unittest.TestCase):
    def test_relative_change(self):
        self.assertAlmostEqual(ER.relative_change(90.0, 100.0), -0.1)
        self.assertAlmostEqual(ER.relative_change(110.0, 100.0), 0.1)
        self.assertEqual(ER.relative_change(100.0, 100.0), 0.0)
        for new, base_ in ((1.0, 0.0), (1.0, -5.0), (math.nan, 1.0),
                           (1.0, math.inf), (None, 1.0), (1.0, None)):
            self.assertIsNone(ER.relative_change(new, base_), (new, base_))

    def test_classify_outcome(self):
        self.assertEqual(ER.classify_outcome(-0.1), "improved")
        self.assertEqual(ER.classify_outcome(-0.05), "unchanged")
        self.assertEqual(ER.classify_outcome(0.0), "unchanged")
        self.assertEqual(ER.classify_outcome(0.1), "worsened")
        self.assertIsNone(ER.classify_outcome(math.nan))
        self.assertIsNone(ER.classify_outcome(None))

    def test_run_status(self):
        fake_grid = SimpleNamespace(elevation=np.array([[-30.0, -12.0]]))
        deep, shallow = [(0, 0)], [(0, 0), (0, 1)]
        v = lambda track, arrived=True: SimpleNamespace(track=track, arrived=arrived)
        self.assertEqual(ER.run_status(v(deep), v(deep), 20, fake_grid)[0], "ok")
        self.assertEqual(ER.run_status(v(shallow), v(deep), 20, fake_grid),
                         ("draft_infeasible", 12.0, 30.0))
        self.assertEqual(ER.run_status(v(deep), v(deep, False), 9, fake_grid)[0],
                         "incomplete")

    def test_paired_metrics_are_consistent(self):
        for _, r in runs[~runs.status.isin(["failed", "infeasible"])].iterrows():
            self.assertAlmostEqual(r.delta_hours, r.dynamic_hours - r.static_hours)
            self.assertAlmostEqual(r.rel_change, r.delta_hours / r.static_hours)
            self.assertEqual(r.outcome, ER.classify_outcome(r.delta_hours))
            self.assertEqual(r.reroutes, len(r.reroute_steps.split()) if r.reroute_steps else 0)
            self.assertEqual(r.evaluations, sum(r[f"n_{d}"] for d in ER.DECISIONS
                                                if d != "adopted") + r.reroutes)


class PairEquivalenceTests(unittest.TestCase):
    def test_baseline_and_rerouting_runs_start_identically(self):
        s, g = (grid.nearest_cell(*P.coord(x)) for x in SHORT)
        cmp = RR.compare_voyage(grid, s, g, base, factories["General Cargo"], "adverse")
        self.assertEqual(cmp.dynamic.initial_route.cells, cmp.static.initial_route.cells)
        self.assertEqual(cmp.dynamic.initial_route.cost, cmp.static.initial_route.cost)
        self.assertFalse(cmp.static.events)               # controller disabled
        self.assertTrue(cmp.dynamic.events)

    def test_no_reroute_means_identical_voyages(self):
        quiet = runs[(runs.status == "ok") & (runs.reroutes == 0)]
        self.assertTrue(len(quiet))
        for _, r in quiet.iterrows():
            self.assertEqual(r.delta_hours, 0.0)
            self.assertEqual(r.delta_km, 0.0)
            self.assertEqual(r.outcome, "unchanged")

    def test_weather_scenarios_are_deterministic(self):
        s, g = (grid.nearest_cell(*P.coord(x)) for x in SHORT)
        plan = factories["General Cargo"](base).search(s, g, True, True)
        for name in ER.SCENARIOS:
            d1, u1 = WS.scenario(name, grid, base, plan)
            d2, u2 = WS.scenario(name, grid, base, plan)
            self.assertTrue(np.array_equal(d1.swh, d2.swh), name)
            self.assertEqual(sorted(u1), sorted(u2), name)
            for k in u1:
                self.assertTrue(np.array_equal(u1[k].swh, u2[k].swh), (name, k))


class StatusTests(unittest.TestCase):
    def test_draft_unsafe_combination_is_infeasible(self):
        # Since Loop 010 routing enforces draft + under-keel margin, so the
        # VLCC is not routed through 16 m water at all (formerly sailed and
        # flagged "draft_infeasible" afterwards).
        r = runs[(runs.origin == SHALLOW[0]) & (runs.vessel == "Crude Oil Tanker (VLCC)")].iloc[0]
        self.assertEqual(r.status, "infeasible")
        self.assertIn("required 24.6 m", r.error)
        self.assertTrue(np.isnan(r.dynamic_hours))          # no fabricated metrics
        summ = ER.summarize(runs).iloc[0]
        self.assertEqual(summ.infeasible, 1)

    def test_failed_run_is_recorded_not_dropped(self):
        def broken(weather):
            raise RuntimeError("cost model unavailable")
        spec = ER.build_matrix([SHORT], ["General Cargo"], ["stable"])
        out, ev = ER.run_matrix(spec, grid, base, {"General Cargo": broken})
        self.assertEqual(list(out.status), ["failed"])
        self.assertIn("cost model unavailable", out.error.iloc[0])
        self.assertTrue(ev.empty)
        both = pd.concat([runs, out], ignore_index=True)
        summ = ER.summarize(both).iloc[0]
        self.assertEqual(summ.failed, 1)
        self.assertEqual(summ.runs, len(runs) + 1)
        self.assertEqual(summ.ok, ER.summarize(runs).iloc[0].ok)   # not counted as ok


class SummaryTests(unittest.TestCase):
    def test_summary_matches_detail(self):
        ok = runs[runs.status == "ok"]
        overall = ER.summarize(runs).iloc[0]
        self.assertEqual(overall.runs, len(runs))
        self.assertEqual(overall.ok, len(ok))
        self.assertEqual(overall.draft_infeasible, (runs.status == "draft_infeasible").sum())
        self.assertEqual(overall.reroutes, ok.reroutes.sum())
        self.assertEqual(overall.improved + overall.unchanged + overall.worsened, len(ok))
        self.assertAlmostEqual(overall.mean_delta_hours, ok.delta_hours.mean())
        self.assertAlmostEqual(overall.mean_rel_change_pct, 100 * ok.rel_change.mean())
        for by in ("voyage", "vessel", "scenario"):
            grouped = ER.summarize(runs, by)
            self.assertEqual(grouped.runs.sum(), len(runs), by)
            self.assertEqual(grouped.ok.sum(), len(ok), by)
            self.assertEqual(grouped.reroutes.sum(), ok.reroutes.sum(), by)

    def test_events_belong_to_runs(self):
        self.assertTrue(set(events.run_id) <= set(runs.run_id))
        adopted = events[events.decision == "adopted"].groupby("run_id").size()
        for run_id, n in adopted.items():
            self.assertEqual(runs.set_index("run_id").loc[run_id].reroutes, n)


class ReproducibilityTests(unittest.TestCase):
    def test_repeated_run_identical_except_timing(self):
        again, events_again = ER.run_matrix(subset, grid, base, factories)
        cols = [c for c in runs.columns if c not in ER.TIMING_COLUMNS]
        pd.testing.assert_frame_equal(runs[cols], again[cols])
        pd.testing.assert_frame_equal(events, events_again)


if __name__ == "__main__":
    unittest.main()
