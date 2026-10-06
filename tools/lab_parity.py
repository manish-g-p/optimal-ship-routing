"""Deterministic Simulation-lab API run, for comparing two environments
(e.g. host vs. Docker). Usage:
    python tools/lab_parity.py http://localhost:8000 out.json
Run against each server, then compare the two JSON files (they must be
identical; session ids are excluded)."""
import json
import sys
import time

import requests

BASE, OUT = sys.argv[1], sys.argv[2]
STORM = {"lat": 18.0, "lon": 66.5, "radius_km": 150, "delta_m": 6}


def call(method, path, body=None):
    r = requests.request(method, BASE + path, json=body, timeout=120)
    r.raise_for_status()
    return r.json()


def strip(st):
    """Drop per-session identifiers; keep every simulation output."""
    st = json.loads(json.dumps(st))
    st.pop("id", None)
    st["weather"].pop("overlay", None)
    return st


def run(preset, manual_at=None, enabled=True):
    st = call("POST", "/api/sim/sessions", {
        "origin": "Cochin (Kerala)", "dest": "Dubai / Jebel Ali (UAE)",
        "vessel": "General Cargo", "base_weather": "typical", "preset": preset,
        "rerouting_enabled": enabled})
    sid, t0, steps = st["id"], time.time(), 0
    while st["status"] != "completed":
        if manual_at is not None and st["step"] == manual_at:
            call("POST", f"/api/sim/sessions/{sid}/weather", {"disturbances": [STORM]})
            call("POST", f"/api/sim/sessions/{sid}/weather/apply")
        st = call("POST", f"/api/sim/sessions/{sid}/step", {"expected_step": st["step"]})
        steps += 1
    call("DELETE", f"/api/sim/sessions/{sid}")
    return strip(st), round(time.time() - t0, 1), steps


out, timing = {}, {}
for name, args in {"manual_storm": ("none", 2), "moving_storm_preset": ("moving_storm", None),
                   "manual_storm_rerouting_off": ("none", 2, False)}.items():
    out[name], timing[name], n = run(*args)
    s = out[name]
    print(f"{name}: {n} steps in {timing[name]} s | reroutes {s['metrics']['reroutes']} | "
          f"{s['metrics']['sailed_hours']} h vs {s['comparison_no_rerouting']['sailed_hours']} h "
          f"without rerouting | timeline {len(s['timeline'])} entries")
json.dump(out, open(OUT, "w"), indent=1, sort_keys=True)
