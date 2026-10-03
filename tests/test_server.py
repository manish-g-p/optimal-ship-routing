"""
Flask API tests: the existing static route endpoints and the voyage
simulation endpoint (POST /api/simulate). Uses Flask's test client, the
committed data/processed/ artifacts and no network.
Run from the repo root:  python -m unittest discover -s tests -v
"""
import copy
import unittest
import warnings

from src import routing as R

ORIGIN, DEST = "Cochin (Kerala)", "Dubai / Jebel Ali (UAE)"


def setUpModule():
    global server, client
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # sklearn pickle version skew
        import server as S
    server, client = S, S.app.test_client()


def simulate(**body):
    req = {"origin": ORIGIN, "dest": DEST, "vessel": "General Cargo"}
    req.update(body)
    return client.post("/api/simulate", json=req)


class StaticEndpointTests(unittest.TestCase):
    def test_meta(self):
        d = client.get("/api/meta").get_json()
        self.assertEqual(len(d["ports"]), 19)
        self.assertEqual(len(d["vessels"]), 5)
        self.assertIn("region", d)
        self.assertIn("adverse", d["simulation"]["scenarios"])
        self.assertNotIn("live", d["simulation"]["base_weather"])

    def test_route_unchanged(self):
        # distances as in the committed data/processed/evaluation.csv
        r = client.post("/api/route", json={
            "origin": "Mumbai (JNPT)", "dest": "Chennai (Tamil Nadu)",
            "vessel": "General Cargo", "scenario": "rough"})
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["dijkstra"]["distance_km"], 2953.6)
        self.assertEqual(d["astar"]["distance_km"], 2954.9)
        # travel time from the ML speed model for both routes (Loop 007;
        # previously distance / 18 kn = 88.6 h for both)
        self.assertEqual(d["dijkstra"]["time_hours"], 114.5)
        self.assertEqual(d["astar"]["time_hours"], 114.4)
        self.assertEqual(d["astar"]["time_basis"], "ml_speed")
        self.assertEqual(d["dijkstra"]["time_basis"], "ml_speed")
        # same keys as before plus time_basis
        self.assertEqual(set(d["astar"]), {
            "found", "path", "distance_km", "time_hours", "time_basis",
            "max_wave_m", "mean_wave_m", "min_coast_km", "expanded",
            "waypoints"})

    def test_route_time_without_ml_cost(self):
        # A* on the analytic wave cost still reports ML-estimated time
        d = client.post("/api/route", json={
            "origin": "Mumbai (JNPT)", "dest": "Chennai (Tamil Nadu)",
            "vessel": "General Cargo", "scenario": "rough", "use_ml": False,
            "algorithms": ["astar"]}).get_json()
        self.assertEqual(d["astar"]["time_basis"], "ml_speed")
        self.assertNotIn("dijkstra", d)

    def test_route_rejects_unknown_vessel(self):
        r = client.post("/api/route", json={"origin": ORIGIN, "dest": DEST,
                                            "vessel": "Submarine"})
        self.assertEqual(r.status_code, 400)

    def test_route_rejects_same_port(self):
        r = client.post("/api/route", json={"origin": ORIGIN, "dest": ORIGIN})
        self.assertEqual(r.status_code, 400)


class SimulateTests(unittest.TestCase):
    def assertVoyage(self, d):
        o, g = [d["origin"]["lat"], d["origin"]["lon"]], [d["dest"]["lat"], d["dest"]["lon"]]
        self.assertTrue(d["simulated"])
        self.assertIn("not real-world", d["note"])
        self.assertEqual(d["track"][0], o)
        self.assertEqual(d["track"][-1], g)
        self.assertEqual(d["initial_route"]["path"][0], o)
        self.assertEqual(d["final_route"]["path"][-1], g)
        self.assertTrue(d["dynamic"]["arrived"] and d["static"]["arrived"])
        # hours are derived from the reported cost (ML cost model)
        kmh = 16.0 * 1.852                    # General Cargo service speed
        for v in (d["dynamic"], d["static"]):
            self.assertAlmostEqual(v["hours"], v["cost"] / kmh, delta=0.1)

    def test_reroute_scenario(self):
        r = simulate(scenario="adverse")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertVoyage(d)
        self.assertEqual(d["dynamic"]["reroutes"], 1)
        adopted = [e for e in d["events"] if e["decision"] == "adopted"]
        self.assertEqual(len(adopted), 1)
        e = adopted[0]
        self.assertEqual(e["step"], 2)
        self.assertTrue(e["triggers"])
        self.assertGreaterEqual(e["gain_pct"], 3.0)
        self.assertLess(e["alternative_hours"], e["remaining_hours"])
        # the vessel was at the reported position when it rerouted, and
        # sails the final route from there
        i = e["step"] * d["config"]["cells_per_step"]
        self.assertEqual(d["track"][i], e["position"])
        self.assertEqual(d["final_route"]["path"][0], e["position"])
        self.assertLess(d["dynamic"]["hours"], d["static"]["hours"])
        self.assertEqual(d["static"]["reroutes"], 0)
        self.assertEqual([w["step"] for w in d["weather_updates"]], [2])
        self.assertGreater(d["weather_updates"][0]["delta_m"], 5.0)

    def test_stable_weather(self):
        d = simulate(scenario="stable").get_json()
        self.assertVoyage(d)
        self.assertEqual(d["dynamic"]["reroutes"], 0)
        self.assertEqual(d["events"], [])                 # no trigger at all
        self.assertEqual(d["weather_updates"], [])
        self.assertEqual(d["dynamic"]["hours"], d["static"]["hours"])
        self.assertEqual(d["final_route"], d["initial_route"])

    def test_config_is_applied(self):
        d = simulate(scenario="adverse", config={"min_gain": 0.5}).get_json()
        self.assertEqual(d["config"]["min_gain"], 0.5)
        self.assertEqual(d["dynamic"]["reroutes"], 0)
        self.assertIn("retained", {e["decision"] for e in d["events"]})

    def test_failed_alternative(self):
        original = server.sim_router_factory

        def failing(vessel_name):
            make = original(vessel_name)
            base_ids = set()

            def factory(weather):
                router = make(weather)
                if not base_ids:              # first call: departure weather
                    base_ids.add(id(weather))
                if id(weather) in base_ids:
                    return router
                fake = copy.copy(router)
                fake.search = lambda *a: R.RouteResult("A*", found=False)
                return fake
            return factory

        server.sim_router_factory = failing
        try:
            r = simulate(scenario="adverse")
        finally:
            server.sim_router_factory = original
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertVoyage(d)
        self.assertEqual(d["dynamic"]["reroutes"], 0)
        failed = [e for e in d["events"] if e["decision"] == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertIn("no navigable route", failed[0]["reason"])
        self.assertEqual(d["final_route"], d["initial_route"])

    def test_invalid_requests(self):
        cases = {
            "unknown port": {"origin": "Atlantis"},
            "same port": {"dest": ORIGIN},
            "unknown vessel": {"vessel": "Submarine"},
            "live weather": {"base_weather": "live"},
            "unknown scenario": {"scenario": "hurricane"},
            "unknown setting": {"config": {"algorithm": "dijkstra"}},
            "negative value": {"config": {"cooldown_steps": -1}},
            "non-integer steps": {"config": {"cells_per_step": 2.5}},
            "non-numeric": {"config": {"min_gain": "lots"}},
            "config not an object": {"config": [1, 2]},
        }
        r = client.post("/api/simulate", content_type="application/json",
                        data='{"origin": "%s", "dest": "%s", '
                             '"config": {"min_gain": NaN}}' % (ORIGIN, DEST))
        self.assertEqual(r.status_code, 400)
        for name, body in cases.items():
            with self.subTest(name):
                r = simulate(**body)
                self.assertEqual(r.status_code, 400, r.get_json())
                self.assertIn("error", r.get_json())
        r = client.post("/api/simulate", data="not json",
                        content_type="text/plain")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
