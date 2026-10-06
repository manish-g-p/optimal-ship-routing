# Tasks

Current goal, next goal, and roadmap status. Roadmap phases are those of
[`docs/Source_Of_Truth.md`](../Source_Of_Truth.md) §16 (current version,
2026-10-03). Work one goal at a time; don't split goals into microtasks.

Status values: `DONE`, `NEXT` (proposed or confirmed), `BACKLOG`,
`DEFERRED`, `SUPERSEDED`.

---

## Current goal

None in progress. The last implementation goal (navigational safety and
reroute realism, Loop 010) is `DONE`.

## Next goal — `NEXT` (proposed, needs user confirmation)

All Source of Truth roadmap phases except optional Phase 5 are now done.
Candidates, in suggested order. None is decided by the user.

1. **Address the two defects the evaluation exposed** (correctness, small):
   - draft-aware navigability, so deep-draft vessels are not routed through
     water shallower than their draft (`BLOCKERS.md` C10);
   - the scikit-learn model-artifact skew (C5).
2. **Complete the rule-based baseline before Phase 5:** run the evaluation
   on `rough` base weather and with a small threshold/cooldown sensitivity
   grid, as separate, labelled experiments. Measure counterfactual missed
   reroutes. This makes the baseline that Phase 5 must beat explicit.
3. **Phase 5 (optional):** an experimental ML rerouting-decision model,
   compared with the EXP-006 baseline on held-out scenarios.

---

## Completed goals

### Navigational safety and dynamic-rerouting realism — `DONE`

Loop 010, 2026-10-06 (uncommitted when written).

- Diagnosis: EXP-008 A/B.
- Vessel depth feasibility (draft + 20% UKC), configurable coastal
  clearance and explicit infeasible outcomes, used everywhere
  (Decision 014). The soft coastal preference is implemented but off,
  with evidence.
- Similar-benefit route-change preference and reroute geometry recording
  (Decision 015); no turn-rate model (not justified).
- Lab: replaced plan, safety overlay, vessel moving only along sailed
  cells, constraint and cause display, infeasible messages.

Evidence: `tests/test_safety.py`, `tools/lab_e2e.mjs` (36 checks),
EXP-008, EXP-009, `VALIDATION.md` → Loop 010.

### Interactive weather and rerouting Simulation lab (Phase 4 extension) — `DONE`

Loop 009, 2026-10-03 (uncommitted when written). The Flask app has a
"Simulation lab" mode backed by stateful sessions (`src/sim_session.py`,
`/api/sim/sessions…`). Users can start, pause, step and reset a voyage,
add, move or edit storms and calm patches (pending until applied), and
watch the backend controller's real decisions on the map and in a
timeline. The engine was refactored into `rerouting.Voyage`, with the
evaluation unchanged. Evidence: `tests/test_sim_session.py`,
`tools/lab_e2e.mjs` (28/28 on host and in Docker),
`tools/lab_parity.py` (host == Docker), `VALIDATION.md` → Loop 009,
EXP-007.

### Rerouting evaluation across voyages, vessels and scenarios (Phase 4) — `DONE`

Loop 008, 2026-10-03 (uncommitted when written). `src/evaluate_rerouting.py`
runs 150 rerouting-on/off pairs (5 voyages × 5 vessels × 6 scenarios,
`typical` base, default thresholds, not tuned). Results: 144 ok, 6
draft-infeasible, 0 failed; 88 improved, 50 unchanged, 6 worsened (all
`shifting`). Outputs: `data/rerouting_eval/`. Evidence: EXP-006,
`tests/test_evaluate_rerouting.py`, `VALIDATION.md` → Loop 008.

### Route cost, travel time and ETA consistency (Phase 3 + Phase 1 ETA item) — `DONE`

Loop 007, 2026-10-03 (uncommitted when written). `Router` now has a travel-time model (`speed_kn`,
`time_mult`, `path_hours`, `RouteResult.time_basis`) separate from the
cost model. All application paths estimate travel time with the vessel's
ML speed model; route selection is unchanged. Definitions are in Source of
Truth §10.1 and Decision 011. Evidence: `TravelTimeTests`,
`test_decisions_ignore_travel_time_model`, `VALIDATION.md` → Loop 007,
EXP-005.

### Dynamic rerouting in the application interface (part of Phase 4) — `DONE`

Loop 006, 2026-10-03 (uncommitted when written). The Flask app has a
"Voyage simulation" mode (renamed "Voyage replay" in Loop 009) and
`POST /api/simulate`. The user picks ports,
vessel, base weather, weather change and rerouting settings. They see the
initial plan, the sailed track, reroute points, weather-change locations
and vessel progress (slider). They can inspect each rerouting evaluation's
triggers and reason, and compare with the same voyage without rerouting.
The logic stays in `src/rerouting.py` (`compare_voyage`,
`config_from_dict`; `cost_hours`, later removed in Loop 007) and `src/weather_sim.py` (`peak_change`).
Flask only validates input and shapes JSON. Evidence:
`tests/test_server.py`, `VALIDATION.md` → Loop 006 (including a headless
browser check), `EXPERIMENTS.md` EXP-004. Not done: Streamlit
integration (`DECISIONS.md` D010).

### Weather-driven dynamic rerouting (Source of Truth Phase 2) — `DONE`

Loop 004, 2026-10-03, commit `e8f68d1`. Simulation-level only (no UI).
Goal definition and where each point is implemented/tested:

| # | Goal requirement | Implementation | Test evidence (`tests/test_rerouting.py`) |
| --- | --- | --- | --- |
| 1 | Advance a vessel along an active route | `rerouting.simulate()` — index into active route cells, `cells_per_step` | `test_vessel_progress` |
| 2 | Deterministic weather updates | `weather_sim.perturb_waves`, `weather_sim.scenario` | all scenario tests (no randomness) |
| 3 | Evaluate the remaining route under new weather | `RerouteController.evaluate` → `Router.path_cost(remaining)` | `test_adverse_storm_adopts_alternative` |
| 4 | Transparent, configurable triggers | wave-height, cost-increase, periodic re-check; `RerouteConfig` / `config.REROUTE_*` | `test_adverse_storm_adopts_alternative`, `test_improving_alternative_is_adopted` |
| 5 | Alternative from current position to original destination | `Router.search(vessel_cell, goal)` | `test_adverse_storm_adopts_alternative` |
| 6 | Consistent cost comparison | remaining and alternative scored by the same `Router` | `test_adverse_storm_adopts_alternative` |
| 7 | Adopt only if valid and sufficiently beneficial | validation + `min_gain` / `min_gain_abs` | `test_alternative_below_threshold_is_not_adopted` |
| 8 | Record decisions and reasons | `RerouteEvent` list in `VoyageResult.events` | all scenario tests |
| 9 | Prevent unnecessary/repeated rerouting | cooldown, unchanged-skip, thresholds | `test_cooldown_and_interval`, `test_cooldown_reduces_route_changes`, `test_persistent_trigger_does_not_repeat_searches` |
| 10 | Scenarios: stable, worsening, insignificant change, cooldown, failed alternative | `stable`, `adverse`/`worsening`, `minor`, `shifting`, injected failures | `StableWeatherTests`, `AdverseWeatherTests`, `InsufficientImprovementTests`, `RepeatedWeatherChangeTests`, `FailedAlternativeTests` |

Evidence: `VALIDATION.md` (Loops 004, 005), `EXPERIMENTS.md` EXP-003.
Limitations carried forward: `BLOCKERS.md` C4.

### Current-position rerouting (Source of Truth Phase 1) — `DONE`

Loop 003, 2026-10-03, commit `6fdfd91`. Arbitrary navigable start
supported by `Router.search`; added start/goal validation,
`RouteResult.cost`, `Router.path_cost`, `tests/test_routing.py`.
Evidence: `VALIDATION.md` (Loop 003), `EXPERIMENTS.md` EXP-002. The
Phase 1 item "verify ETA and cost consistency" was completed later, in
Loop 007.

---

## Roadmap status (Source of Truth §16)

| Phase | Status |
| --- | --- |
| 1 — Rerouting foundation | `DONE` (ETA/cost item in Loop 007) |
| 2 — Weather updates and rerouting triggers | `DONE` (simulation) |
| 3 — ML speed prediction integration | `DONE` except model artifact skew (C5) |
| 4 — Evaluation and visualization | `DONE` (UI Loop 006; evaluation Loop 008) |
| 5 — Experimental ML rerouting decisions | `BACKLOG` (optional) |

---

## Historical tasks (previous Source of Truth roadmap)

Defined in Loops 000–001 under the pre-2026-10-03 Source of Truth
(multi-algorithm comparison direction). Section references in those
entries point to that version (`git show 79f130b:docs/Source_Of_Truth.md`).
The full previous text of this file is at commit `79f130b`.

| Task / phase | Status | Note |
| --- | --- | --- |
| TASK-001 — Reproducible Docker development environment | `DONE` (Loop 001, 2026-10-01) | Still valid and in use. Evidence: `DOCKER.md`, EXP-001. |
| TASK-002 — Docker Hub image workflow | `DEFERRED` | Was the `READY` task; never started. Not in the current roadmap. |
| TASK-003 — Pull and run on the remote server | `DEFERRED` | Never started. Not in the current roadmap. |
| TASK-004 — Validate remote execution | `DEFERRED` | Never started. Not in the current roadmap. |
| Old Phase 2 — Routing foundation (common `RouteResult`, metrics, safety validation) | `SUPERSEDED` | Partly overlaps current Phase 1/3 (cost exposure, ETA). |
| Old Phase 3 — Routing algorithm expansion (bidirectional, weather-aware Dijkstra, risk-constrained) | `SUPERSEDED` | Current Source of Truth §4 puts adding algorithms for their own sake out of scope. |
| Old Phases 4–5 — Scenario framework, evaluation/evidence engine | `SUPERSEDED` | Replaced by current §11 evaluation strategy / Phase 4. |
| Old Phase 6 — Algorithm-comparison UI | `SUPERSEDED` | Replaced by current §12 rerouting visualization / Phase 4. |
| Old Phase 7 — Offline packaging | `DEFERRED` | Current §13 keeps offline evaluation but no packaging goal. |

Remote deployment or offline packaging can be revived only if the user
adds them back to the Source of Truth.
