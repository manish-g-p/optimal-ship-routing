# Blockers and Open Concerns

**Last reviewed:** 2026-10-06 (Loop 010), working tree on top of `ee4da2b`.

- **Blocker:** prevents the current/next goal from being done or validated.
- **Open concern:** a known correctness issue, risk or limitation that
  future work must account for, but that does not block it.
- **Resolved / historical:** kept so earlier references stay traceable.

---

## Active blockers

None. The proposed next goal (`TASKS.md`) only needs user confirmation.

---

## Open concerns

### C1 — ETA not derived from the routing cost — RESOLVED (Loop 007)

Was: `time_hours = distance ÷ 18 kn` for every route. Now travel time comes
from the vessel's ML speed model per segment (Source of Truth §10.1,
Decision 011). It is tested against an independent per-segment
calculation. Kept here because older records refer to C1.

### C2 — Cost units depend on the cost model

`RouteResult.cost` / `Router.path_cost` are in km (Dijkstra), km × analytic
wave multiplier (`Router(grid, weather)`), or km at service speed (ML
multiplier; ÷ (service kn × 1.852) gives hours). Comparing costs from
different routers is meaningless. The rerouting controller always uses
one router per comparison. For cross-route comparison, use `time_hours`
(one time model for all routes since Loop 007) or `distance_km`. Risk for
future evaluation code.

### C3 — A* heuristic may not be admissible (unverified impact)

`Router._heuristic` scales longitude by `cos(mean grid latitude)` ≈
cos 13.5°. North of that, it overstates east–west distance (at 27°N by
about cos 13.5° / cos 27° ≈ 1.09, i.e. ~9%), while the module docstring
claims admissibility/optimality. A* could therefore return slightly
suboptimal routes there. Not observed: rerouted costs matched the
remaining optimal costs exactly in the Loop 003 tests (Mumbai → Chennai).
Not measured on northern east–west voyages. Risk.

### C4 — Rerouting is a simplified simulation

Implemented in Loop 004, with these known limits:

- Weather updates are synthetic Gaussian changes to wave height only
  (period and direction unchanged); no forecast timeline.
- Vessel movement is a fixed number of cells per step, not time- or
  speed-based.
- Scenarios and thresholds were tuned on one voyage (Cochin → Dubai,
  General Cargo, `typical` base weather). On `rough` weather, the 4.0 m
  wave trigger is near the 90th-percentile wave height of navigable cells
  (≈ 4.02 m, measured in Loop 004), so it would fire often.
- A rejected alternative is not re-searched while weather and route are
  unchanged (`DECISIONS.md` → Unresolved).
- Missing/invalid/stale weather handling (Source of Truth §9.3) is not
  implemented for the simulation; live weather is not connected to it.
- Exposed in the Flask UI since Loop 006, not in Streamlit. In the UI,
  the wave overlay shows the base weather; simulated storms appear only
  as circles at the peak change (fixed 150 km display radius). A request
  runs the voyage twice and blocks the request thread for its duration
  (≈4 s for `adverse`; longer scenarios not timed).

### C5 — scikit-learn version skew in the ML model artifact (formerly Q6)

`data/processed/speed_model.joblib` was pickled with scikit-learn 1.8.0;
`requirements.txt` pins 1.9.0. Re-checked in Loop 005: loading still emits
`InconsistentVersionWarning` (62 warnings). Loop 001 found no effect on
`evaluation.csv`, and evaluation output has matched the baseline in every
check since. Fix options (retrain under 1.9.0, or pin 1.8.0) fit the
Phase 3 ML work. Risk.

### C6 — Google Maps API key rotation (formerly Q7) — human decision

A real-looking key existed as a local, uncommitted default in
`web_config.py` (Loop 001; confirmed never committed or pushed). Loop 002
moved it to the gitignored `.env` and deleted `web_config.py`, without
printing it. Whether the key is live, billable or needs rotation is
still the developer's decision; no loop has assumed or acted on it.

### C7 — `networkx` dependency appears unused (formerly Q4)

Pinned in `requirements.txt`; still not imported anywhere (re-checked in
Loop 005 with a repo-wide grep). Remove only as part of a deliberate
dependency change.

### C10 — Vessel draft is not used by routing — RESOLVED (Loop 010)

Resolved by Decision 014: depth ≥ draft × 1.2 is enforced everywhere, and
Kandla → Cochin is now *infeasible* for the Container Ship and VLCC with an
explicit reason. Original finding kept below.


The navigable grid applies one minimum depth (`config.MIN_DEPTH_M = 10 m`)
to every vessel. Drafts are 9.0–20.5 m, so deep-draft vessels can be
routed through water shallower than their draft. Measured: the Kandla →
Cochin planned route reaches 16 m depth, so the VLCC (20.5 m) is
infeasible there. Other planned routes reach ≥ 23 m (≥ 25 m for all but
General Cargo on Cochin → Dubai), enough for every draft. No under-keel
clearance is modelled. The rerouting evaluation flags these runs
(`draft_infeasible`), but the Flask/Streamlit apps and route planning do
not check draft.

### C11 — Rerouting can make voyages slower under moving weather (found in Loop 008)

In EXP-006, 6 of 144 valid pairs were slower with rerouting (+0.6 to
+8.3 h), all in the `shifting` scenario, on Visakhapatnam → Colombo (4
vessels) and Chennai → Port Blair (2). Each adopted reroute was cheaper
under the weather at decision time. The controller assumes current
weather persists, so a storm that moves can invalidate a decision.
Hypothesis (not verified): more likely when the storm's alternate
positions are close to the route (163–167 km on these voyages vs.
184–231 km elsewhere). This is a property of the baseline policy, to be
reported, not tuned away.

### C12 — Evaluation gaps

Not measured in EXP-006: `rough` base weather; threshold and cooldown
sensitivity; missed beneficial reroutes (5 rejected alternatives had
2.3–2.7% gain, just under the 3% threshold, but would need a
counterfactual run). The scenarios and thresholds were designed on one of
the 25 voyage-vessel pairs (Cochin → Dubai, General Cargo), so that pair
is in-sample.

### C14 — Port approach cells far offshore (Loop 010)

Ports are represented by the nearest cell that is navigable on the grid:
Kandla 141 km, Mundra 100 km, Haldia 83 km and Mumbai 44 km away. That cell
may also be too shallow for deep-draft vessels (Kandla: 16 m), which makes
the voyage infeasible rather than finding a deeper approach. Narrow
passages are closed by the 22 km clearance (Hormuz, Palk Strait). A
vessel-aware approach model or a smaller clearance in designated channels
would be a separate design decision.

### C15 — Coastal-proximity trade-off (Loop 010)

Cost-optimal routes follow the 22 km clearance edge on coastal voyages
(38–51% of cells within 22–30 km). The soft coastal preference reduces this
but increases rough-weather wave exposure (EXP-008), so it is off. Choosing
a weight is a policy decision between coastal proximity and sea state.

### C13 — Simulation-lab limitations (Loop 009)

- Sessions are in one process's memory: lost on server restart, not shared
  across Flask workers or containers. Running several workers or replicas
  would break sessions (requests could reach a process without the
  session). Capped at 8 sessions (oldest idle evicted) and 30 min idle TTL.
- Each weather change rebuilds the ML cost grid (≈ 1.2 s); a preset that
  changes weather every step (`moving_storm`) takes ≈ 16–19 s per voyage.
- Only significant wave height is simulated; wave period and direction
  stay as in the base sea state. "Remaining" and "projected" hours assume
  the current weather persists.
- Circle radius on the map is 1σ of the Gaussian; the storm's effect
  extends beyond it (visible in the overlay).
- Browser coverage: verified in headless Chromium only (no Firefox/Safari),
  at 1500×950 and 1280×800. Narrower layouts were not checked.

### C9 — Pre-existing web UI warnings (seen in Loop 006 browser check)

The browser console shows a 404 for `/favicon.ico` and Google's deprecation
notice for `google.maps.Marker` (used by the existing UI, and reused by the
simulation view). Google says `Marker` is not scheduled for removal. Not
fixed: unrelated to rerouting. The Simulation lab also uses `Marker` (same
notice); its own check found no other console errors (Loop 009).

### C8 — Documentation risks

- Pre-2026-10-03 records cite old Source of Truth section numbers
  (explained in `README.md`).
- Root `README.md` says PDF/PowerPoint files are "not uploaded to GitHub",
  but `docs/*.pdf` and `docs/Nautilus_Slides.pptx` are tracked in git
  (verified in Loop 005). Which is intended is unknown; not changed.
- The PDF/PPTX project documents (report, slides, guides) were not
  reviewed and may describe the earlier project direction.

---

## Resolved / historical

| Item | Status |
| --- | --- |
| Q1 — Unpinned dependency versions | Resolved in Loop 001 (pinned `requirements.txt`). |
| Q2 — ETA discrepancy vs. previous Source of Truth claim | Reframed as **C1**; **resolved in Loop 007**. |
| Q3 — Container base-image system dependencies | Resolved in Loop 001 (plain `python:3.12-slim` suffices). |
| Q4 — `networkx` usage | Still open as **C7**. |
| Q5 — Remote server specifics (OS, Docker version, limits) | **Deferred**: remote deployment (old TASK-003/004) is not on the current roadmap. |
| Q6 — scikit-learn pickle skew | Still open as **C5**. |
| Q7 — Local Google Maps key | Migrated to `.env` (Loop 002); rotation decision open as **C6**. |
| Silent navigability violation for invalid start positions | Found and fixed in Loop 003 (`Router.search` validation). |
