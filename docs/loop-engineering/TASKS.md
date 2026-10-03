# Tasks

Current goal, next goal, and roadmap status. Roadmap phases are those of
[`docs/Source_Of_Truth.md`](../Source_Of_Truth.md) §16 (current version,
2026-10-03). Work one goal at a time; don't split goals into microtasks.

Status values: `DONE`, `NEXT` (proposed or confirmed), `BACKLOG`,
`DEFERRED`, `SUPERSEDED`.

---

## Current goal

None in progress. The last implementation goal (weather-driven dynamic
rerouting, Loop 004) is `DONE`.

## Next goal — `NEXT` (proposed, needs user confirmation)

**Route cost / ETA consistency and ML speed integration** — Source of
Truth Phase 3, plus the one open Phase 1 item ("Verify ETA and cost
consistency").

Why this one: it is the next phase in the roadmap order, and the main
open correctness issue (Source of Truth §10) sits here — `time_hours` is
distance at a constant 18 kn while routes are chosen by an ML/weather
cost. Proposed scope, to be confirmed:

- Report travel time from the same speed assumptions used for routing
  (with the ML cost model, cost ÷ (service speed × 1.852) is hours).
- Make the ML-vs-analytic cost model choice explicit for initial
  routing, alternatives and remaining-route evaluation.
- Check behavior across all five vessel profiles.
- Document model limitations (synthetic training data, pickle skew).

This was **not** decided by the user; it is the roadmap's next step. If
the user prefers Phase 4 (evaluation and UI visualization of rerouting)
first, that is equally consistent with the Source of Truth.

---

## Completed goals

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

### Current-position rerouting (Source of Truth Phase 1) — `DONE` (ETA item open)

Loop 003, 2026-10-03, commit `6fdfd91`. Arbitrary navigable start
supported by `Router.search`; added start/goal validation,
`RouteResult.cost`, `Router.path_cost`, `tests/test_routing.py`.
Evidence: `VALIDATION.md` (Loop 003), `EXPERIMENTS.md` EXP-002. The
Phase 1 item "verify ETA and cost consistency" is **not** done — moved
into the next goal.

---

## Roadmap status (Source of Truth §16)

| Phase | Status |
| --- | --- |
| 1 — Rerouting foundation | `DONE` except ETA/cost consistency |
| 2 — Weather updates and rerouting triggers | `DONE` (simulation) |
| 3 — ML speed prediction integration | `NEXT` (proposed) |
| 4 — Evaluation and visualization | `BACKLOG` |
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
