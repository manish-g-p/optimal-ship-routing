"""
Tests for interactive simulation sessions (src/sim_session.py) and the
/api/sim/... endpoints. Committed data, no network.
Run from the repo root:  python -m unittest discover -s tests -v
"""
import copy
import unittest
import warnings

import numpy as np

from src import (grid as G, weather as W, ports as P, vessel as V,
                 ml_model as ML, routing as R, rerouting as RR,
                 weather_sim as WS, sim_session as SS)

SHORT = ("Chennai (Tamil Nadu)", "Port Blair (Andaman)")
LONG = ("Cochin (Kerala)", "Dubai / Jebel Ali (UAE)")
VESSEL = "General Cargo"


def setUpModule():
    global grid, base, make, base_router, server, client
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # sklearn pickle version skew
        model = ML.load()
        import server as S
    server, client = S, S.app.test_client()
    grid = G.load_grid()
    base = W.load_weather(grid, "typical")
    make = RR.router_factory(grid, V.get(VESSEL), model)
    base_router = make(base)


def new_session(voyage=SHORT, preset="none", enabled=True, maker=None, config=None):
    setup = {"origin": voyage[0], "dest": voyage[1], "vessel": VESSEL,
             "base_weather": "typical", "preset": preset, "rerouting_enabled": enabled,
             "start": grid.nearest_cell(*P.coord(voyage[0])),
             "goal": grid.nearest_cell(*P.coord(voyage[1]))}
    return SS.SimSession("a" * 32, grid, base, base_router, maker or make, setup,
                         config or RR.RerouteConfig())


def run_to_end(s):
    while s.state()["status"] != "completed":
        s.advance(s.step)
    return s.state()


def storm_ahead_of(s, frac=0.5, delta=6.0, radius=150.0):
    lat, lon = s.dyn.active.latlon[int(len(s.dyn.active.cells) * frac)]
    return {"lat": float(lat), "lon": float(lon), "radius_km": radius, "delta_m": delta}


class LifecycleTests(unittest.TestCase):
    def test_create(self):
        st = new_session().state()
        self.assertEqual((st["status"], st["step"]), ("ready", 0))
        self.assertEqual(st["routes"]["initial"], st["routes"]["active"])
        self.assertEqual(st["track"], [st["origin"]])
        self.assertEqual(st["timeline"][0]["kind"], "voyage_initialized")
        self.assertIsNone(st["weather"]["pending"])
        self.assertEqual(st["metrics"]["time_basis"], "ml_speed")

    def test_stable_voyage_no_reroute(self):
        st = run_to_end(new_session())
        self.assertEqual(st["metrics"]["reroutes"], 0)
        self.assertEqual(st["track"][-1], st["dest"])
        decisions = {e["detail"]["decision"] for e in st["timeline"] if e["kind"] == "evaluation"}
        self.assertEqual(decisions, {"no_trigger"})
        self.assertEqual(st["metrics"]["sailed_hours"],
                         st["comparison_no_rerouting"]["sailed_hours"])
        self.assertEqual(st["timeline"][-1]["kind"], "voyage_completed")

    def test_matches_batch_engine(self):
        # preset storm_ahead == scenario "adverse": identical voyages
        s = new_session(LONG, "storm_ahead")
        run_to_end(s)
        cmp = RR.compare_voyage(grid, s.setup["start"], s.setup["goal"], base, make, "adverse")
        self.assertEqual(s.dyn.result.track, cmp.dynamic.track)
        self.assertEqual(s.static.result.track, cmp.static.track)
        self.assertAlmostEqual(s.dyn.result.sailed_hours, cmp.dynamic.sailed_hours, places=9)
        self.assertAlmostEqual(s.static.result.sailed_hours, cmp.static.sailed_hours, places=9)
        self.assertEqual([e.step for e in s.dyn.result.reroutes],
                         [e.step for e in cmp.dynamic.reroutes])

    def test_step_conflicts(self):
        s = new_session()
        s.advance(0)
        with self.assertRaises(SS.Conflict):
            s.advance(0)                      # stale / duplicate request
        self.assertEqual(s.step, 1)
        run_to_end(s)
        with self.assertRaises(SS.Conflict):
            s.advance(s.step)
        with self.assertRaises(SS.Conflict):
            s.set_draft([storm_ahead_of(s)])

    def test_reset(self):
        s = new_session(preset="storm_clears")
        s.set_draft([storm_ahead_of(s)])
        for _ in range(4):
            s.advance(s.step)
        s.reset()
        st = s.state()
        self.assertEqual(st["step"], 0)
        self.assertIsNone(st["weather"]["pending"])
        self.assertEqual([d["origin"] for d in st["weather"]["applied"]], ["preset"])
        self.assertEqual(st["routes"]["active"], st["routes"]["initial"])
        self.assertEqual([e["kind"] for e in st["timeline"]][-1], "reset")
        self.assertEqual(st["metrics"]["reroutes"], 0)


class WeatherTests(unittest.TestCase):
    def test_pending_is_not_seen_until_applied(self):
        s = new_session(LONG)
        s.advance(0)
        s.set_draft([storm_ahead_of(s)])
        st = s.state()
        self.assertEqual(st["weather"]["applied"], [])
        self.assertEqual(len(st["weather"]["pending"]), 1)
        self.assertIs(s.dyn.router, base_router)            # routing unaware
        self.assertEqual(st["weather"]["version"], 0)
        s.advance(1)                                        # applied at step 1
        st = s.state()
        self.assertIsNone(st["weather"]["pending"])
        self.assertEqual(st["weather"]["version"], 1)
        self.assertEqual(st["weather"]["last_update_step"], 1)
        kinds = [(e["step"], e["kind"]) for e in st["timeline"]]
        self.assertLess(kinds.index((1, "weather_applied")), kinds.index((1, "evaluation")))
        ev = [e for e in st["timeline"] if e["kind"] == "evaluation" and e["step"] == 1][0]
        self.assertTrue(ev["detail"]["triggers"])

    def test_manual_storm_triggers_real_reroute(self):
        s = new_session(LONG)
        s.advance(0)
        s.set_draft([storm_ahead_of(s)])
        s.apply_pending()                                   # immediately
        self.assertEqual(s.step, 1)                         # no step taken
        s.advance(1)
        st = s.state()
        self.assertEqual(st["metrics"]["reroutes"], 1)
        r1 = st["reroutes"][0]
        ev = [e for e in st["timeline"] if e["seq"] == r1["seq"]][0]
        self.assertTrue(ev["detail"]["adopted"] and ev["detail"]["searched"])
        self.assertGreaterEqual(ev["detail"]["gain_pct"], 3.0)
        # the map's active route starts where the vessel rerouted
        self.assertEqual(st["routes"]["active"][0], r1["position"])
        self.assertEqual(st["track"][1 * s.dyn.cfg.cells_per_step], r1["position"])
        self.assertEqual(st["routes"]["active"][-1], st["dest"])
        self.assertEqual(st["routes"]["route_version"], 1)

    def test_discard_and_withdraw(self):
        s = new_session()
        s.set_draft([storm_ahead_of(s)])
        s.discard_pending()
        self.assertIsNone(s.pending)
        with self.assertRaises(SS.Conflict):
            s.discard_pending()
        with self.assertRaises(SS.Conflict):
            s.apply_pending()
        s.set_draft([storm_ahead_of(s)]); s.apply_pending()
        applied = copy.deepcopy(s.applied)
        s.set_draft(applied)                                # same as applied -> no pending
        self.assertIsNone(s.pending)

    def test_preset_updates_keep_manual_disturbances(self):
        s = new_session(LONG, "storm_ahead")                # preset storm at step 2
        manual = {"lat": 12.0, "lon": 66.0, "radius_km": 100.0, "delta_m": -1.0}
        s.set_draft([manual]); s.apply_pending()
        s.advance(0); s.advance(1); s.advance(2)
        origins = sorted(d["origin"] for d in s.applied)
        self.assertEqual(origins, ["manual", "preset"])

    def test_edit_preset_disturbance_becomes_manual(self):
        s = new_session(preset="storm_clears")
        d = copy.deepcopy(s.applied)
        d[0]["delta_m"] = 3.0
        s.set_draft(d); s.apply_pending()
        self.assertEqual(s.applied[0]["origin"], "manual")
        s.advance(0); s.advance(1); s.advance(2)            # preset clears only its own
        self.assertEqual(len(s.applied), 1)

    def test_base_weather_never_modified(self):
        before = base.swh.copy()
        s = new_session()
        s.set_draft([storm_ahead_of(s, delta=8.0)]); s.apply_pending()
        self.assertTrue(np.array_equal(base.swh, before))
        self.assertGreater(float(s.dyn.router.weather.swh.max()), float(before.max()))

    def test_validation(self):
        ok = {"lat": 10.0, "lon": 80.0, "radius_km": 100.0, "delta_m": 2.0}
        bad = [
            "not a list", [1], [{**ok, "lat": float("nan")}], [{**ok, "lon": float("inf")}],
            [{**ok, "lat": 40.0}], [{**ok, "radius_km": 1.0}], [{**ok, "delta_m": 0}],
            [{**ok, "delta_m": 50}], [{**ok, "lat": True}], [{**ok, "lat": "10"}],
            [{**ok, "id": "bad id!"}], [{**ok, "id": "A"}, {**ok, "id": "A"}],
            [{**ok, "origin": "alien"}], [ok] * (SS.MAX_DISTURBANCES + 1),
        ]
        s = new_session()
        for items in bad:
            with self.subTest(items=str(items)[:60]):
                with self.assertRaises(SS.SessionError):
                    s.set_draft(items)
        self.assertIsNone(s.pending)                         # nothing changed
        s.set_draft([ok, {**ok, "id": "M7"}])
        self.assertEqual(sorted(d["id"] for d in s.pending), ["M7", "M8"])

    def test_presets_match_evaluated_scenarios(self):
        plan = base_router.search(grid.nearest_cell(*P.coord(LONG[0])),
                                  grid.nearest_cell(*P.coord(LONG[1])), True, True)
        pairs = {"storm_ahead": "adverse", "worsening": "worsening", "minor": "minor",
                 "moving_storm": "shifting", "storm_clears": "improving_alt"}
        for preset, scen in pairs.items():
            with self.subTest(preset=preset):
                depart, updates = WS.scenario(scen, grid, base, plan)
                sched = WS.preset(preset, plan)
                d0 = WS.apply_disturbances(base, grid, sched.get(0, []))
                self.assertTrue(np.array_equal(d0.swh, depart.swh))
                self.assertEqual(sorted(k for k in sched if k > 0), sorted(updates))
                for k, w in updates.items():
                    self.assertTrue(np.array_equal(
                        WS.apply_disturbances(base, grid, sched[k]).swh, w.swh), (preset, k))


class FailureTests(unittest.TestCase):
    def test_failed_alternative_keeps_route(self):
        def failing(weather):
            router = copy.copy(make(weather))
            router.search = lambda *a: R.RouteResult("A*", found=False)
            return router
        s = new_session(LONG, maker=failing)
        s.advance(0)
        s.set_draft([storm_ahead_of(s)]); s.apply_pending()
        before = s.state()["routes"]["active"]
        s.advance(1)
        st = s.state()
        ev = [e for e in st["timeline"] if e["kind"] == "evaluation" and e["step"] == 1][0]
        self.assertEqual(ev["detail"]["decision"], "failed")
        self.assertTrue(ev["detail"]["searched"])
        self.assertFalse(ev["detail"]["alternative_found"])
        self.assertEqual(st["routes"]["active"], before)
        self.assertEqual(st["status"], "in_progress")

    def test_failed_weather_build_leaves_state_unchanged(self):
        def broken(weather):
            raise MemoryError("no memory for cost grid")
        s = new_session(maker=broken)
        s.set_draft([storm_ahead_of(s)])
        before = (s.step, s.weather_version, copy.deepcopy(s.applied))
        with self.assertRaises(SS.SessionError):
            s.advance(0)
        self.assertEqual((s.step, s.weather_version, s.applied), before)
        self.assertIsNotNone(s.pending)
        self.assertIsNone(s.error)


class StoreTests(unittest.TestCase):
    def test_store_limits_and_expiry(self):
        store = SS.SessionStore(max_sessions=2, ttl_s=3600)
        sids = [store.create(lambda sid: new_session_with_id(sid)).id for _ in range(3)]
        self.assertEqual(len(store), 2)
        with self.assertRaises(SS.NotFound):
            store.get(sids[0])                               # evicted (oldest)
        store.get(sids[2])
        with self.assertRaises(SS.NotFound):
            store.get("../etc/passwd")
        expiring = SS.SessionStore(ttl_s=0)
        sid = expiring.create(lambda sid: new_session_with_id(sid)).id
        with self.assertRaises(SS.NotFound):
            expiring.get(sid)


def new_session_with_id(sid):
    s = new_session()
    s.id = sid
    return s


class ApiTests(unittest.TestCase):
    def create(self, **kw):
        body = {"origin": SHORT[0], "dest": SHORT[1], "vessel": VESSEL}
        body.update(kw)
        return client.post("/api/sim/sessions", json=body)

    def test_full_api_flow(self):
        r = self.create(preset="none")
        self.assertEqual(r.status_code, 201)
        st = r.get_json()
        sid = st["id"]
        self.assertTrue(st["simulated"])
        self.assertIn("weather_image", st["weather"]["overlay"]["url"])
        self.assertEqual(client.get(f"/api/sim/sessions/{sid}").get_json()["step"], 0)
        st = client.post(f"/api/sim/sessions/{sid}/step", json={"expected_step": 0}).get_json()
        self.assertEqual(st["step"], 1)
        lat, lon = st["routes"]["active"][len(st["routes"]["active"]) // 2]
        st = client.post(f"/api/sim/sessions/{sid}/weather", json={"disturbances": [
            {"lat": lat, "lon": lon, "radius_km": 150, "delta_m": 6}]}).get_json()
        self.assertEqual(len(st["weather"]["pending"]), 1)
        st = client.post(f"/api/sim/sessions/{sid}/weather/apply").get_json()
        self.assertEqual(st["weather"]["version"], 1)
        img = client.get(st["weather"]["overlay"]["url"])
        self.assertEqual((img.status_code, img.mimetype), (200, "image/png"))
        st = client.post(f"/api/sim/sessions/{sid}/step", json={"expected_step": 1}).get_json()
        ev = [e for e in st["timeline"] if e["kind"] == "evaluation" and e["step"] == 1][0]
        self.assertTrue(ev["detail"]["triggers"])
        st = client.post(f"/api/sim/sessions/{sid}/reset").get_json()
        self.assertEqual((st["step"], st["weather"]["applied"]), (0, []))
        self.assertEqual(client.delete(f"/api/sim/sessions/{sid}").status_code, 200)
        self.assertEqual(client.get(f"/api/sim/sessions/{sid}").status_code, 404)

    def test_invalid_requests(self):
        cases = [({"origin": "Atlantis"}, 400), ({"dest": SHORT[0]}, 400),
                 ({"vessel": "Submarine"}, 400), ({"base_weather": "live"}, 400),
                 ({"preset": "hurricane"}, 400), ({"rerouting_enabled": "yes"}, 400),
                 ({"config": {"cooldown_steps": -1}}, 400)]
        for body, code in cases:
            with self.subTest(body=body):
                r = self.create(**body)
                self.assertEqual(r.status_code, code)
                self.assertIn("error", r.get_json())
        sid = self.create().get_json()["id"]
        for body in ({}, {"expected_step": "0"}, {"expected_step": True}):
            self.assertEqual(client.post(f"/api/sim/sessions/{sid}/step", json=body).status_code, 400)
        self.assertEqual(client.post(f"/api/sim/sessions/{sid}/step",
                                     data="x", content_type="text/plain").status_code, 400)
        self.assertEqual(client.post(f"/api/sim/sessions/{sid}/step",
                                     json={"expected_step": 5}).status_code, 409)
        r = client.post(f"/api/sim/sessions/{sid}/weather", content_type="application/json",
                        data='{"disturbances": [{"lat": NaN, "lon": 80, "radius_km": 100, "delta_m": 2}]}')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(client.post(f"/api/sim/sessions/{sid}/weather/apply").status_code, 409)
        self.assertEqual(client.get("/api/sim/sessions/" + "f" * 32).status_code, 404)

    def test_busy_session_and_internal_errors(self):
        sid = self.create().get_json()["id"]
        session = server.SESSIONS.get(sid)
        with session.lock:                                   # another request running
            r = client.post(f"/api/sim/sessions/{sid}/step", json={"expected_step": 0})
        self.assertEqual(r.status_code, 409)
        original = session.advance
        session.advance = lambda *a: (_ for _ in ()).throw(RuntimeError("secret detail"))
        try:
            r = client.post(f"/api/sim/sessions/{sid}/step", json={"expected_step": 0})
        finally:
            session.advance = original
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("secret detail", r.get_data(as_text=True))
        self.assertNotIn("Traceback", r.get_data(as_text=True))

    def test_existing_endpoints_unchanged(self):
        self.assertEqual(client.get("/api/meta").status_code, 200)
        d = client.post("/api/route", json={"origin": "Mumbai (JNPT)", "dest": "Chennai (Tamil Nadu)",
                                            "vessel": VESSEL, "scenario": "rough"}).get_json()
        self.assertEqual((d["dijkstra"]["distance_km"], d["astar"]["time_hours"]), (2953.6, 114.4))
        self.assertEqual(client.post("/api/simulate", json={
            "origin": SHORT[0], "dest": SHORT[1], "vessel": VESSEL, "scenario": "stable"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
