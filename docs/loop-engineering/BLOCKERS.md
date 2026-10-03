# Blockers and Open Concerns

**Last reviewed:** 2026-10-03 (Loop 006), working tree on top of `095bd0b`.

- **Blocker:** prevents the current/next goal from being done or validated.
- **Open concern:** a known correctness issue, risk or limitation that
  future work must account for, but that does not block it.
- **Resolved / historical:** kept so earlier references stay traceable.

---

## Active blockers

None. The proposed next goal (`TASKS.md`) only needs user confirmation.

---

## Open concerns

### C1 — ETA is not derived from the routing cost (correctness issue)

`Router._finalize` sets `time_hours = distance_km / (SHIP_SPEED_KN × 1.852)`
with `SHIP_SPEED_KN = 18` (`src/routing.py`, `config.py`). It ignores
weather, the ML speed model and the vessel's service speed, so A* routes
chosen for travel time report constant-speed ETAs. Source of Truth §10
treats this as a correctness issue. **Does not block rerouting**:
decisions use `cost` (Decision 006). It is the core of the proposed next
goal. (Formerly Q2, which described the same code against a previous
Source of Truth claim that the ETA had been fixed. That claim no longer
exists; the code is unchanged.)

### C2 — Cost units depend on the cost model

`RouteResult.cost` / `Router.path_cost` are in km (Dijkstra), km × analytic
wave multiplier (`Router(grid, weather)`), or km at service speed (ML
multiplier; ÷ (service kn × 1.852) gives hours). Comparing costs from
different routers is meaningless. The rerouting controller always uses
one router per comparison. Risk for future evaluation code.

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

### C9 — Pre-existing web UI warnings (seen in Loop 006 browser check)

The browser console shows a 404 for `/favicon.ico` and Google's deprecation
notice for `google.maps.Marker` (used by the existing UI, and reused by the
simulation view). Google says `Marker` is not scheduled for removal. Not
fixed: unrelated to rerouting.

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
| Q2 — ETA discrepancy vs. previous Source of Truth claim | Reframed as **C1** (the claim is gone; the issue remains). |
| Q3 — Container base-image system dependencies | Resolved in Loop 001 (plain `python:3.12-slim` suffices). |
| Q4 — `networkx` usage | Still open as **C7**. |
| Q5 — Remote server specifics (OS, Docker version, limits) | **Deferred**: remote deployment (old TASK-003/004) is not on the current roadmap. |
| Q6 — scikit-learn pickle skew | Still open as **C5**. |
| Q7 — Local Google Maps key | Migrated to `.env` (Loop 002); rotation decision open as **C6**. |
| Silent navigability violation for invalid start positions | Found and fixed in Loop 003 (`Router.search` validation). |
