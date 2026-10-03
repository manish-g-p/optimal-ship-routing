# Decisions

Durable decisions that constrain future work, plus unresolved choices.
Status per decision: **Confirmed** (in force), **Superseded** (kept for
history), or listed under *Unresolved*.

Decisions 001–003 were recorded in Loop 000 under the **previous** Source
of Truth; their "§" references point to that version
(`git show 79f130b:docs/Source_Of_Truth.md`). Decisions 004+ refer to the
current Source of Truth (2026-10-03).

## Summary

| ID | Decision | Status |
| --- | --- | --- |
| 001 | Direction: algorithm expansion / evidence-based selection / remote Docker / offline | **Superseded** by 004 |
| 002 | Docker as the development environment | **Confirmed** (remote-server motivation no longer on the roadmap) |
| 003 | Offline-first core operation | **Confirmed** |
| 004 | Direction: ML-assisted dynamic rerouting | **Confirmed** |
| 005 | Rerouting reuses `Router.search`; explicit invalid-position errors | **Confirmed** |
| 006 | Route comparison uses routing cost from one `Router`, not `time_hours` | **Confirmed** |
| 007 | Threshold-based rerouting controller rules | **Confirmed** (baseline) |
| 008 | Simulation model: route-cell position, deterministic `swh` perturbations, ML cost by default | **Confirmed** (prototype) |
| 009 | Tests use stdlib `unittest` and committed data | **Confirmed** |
| 010 | Rerouting UI: Flask only, via `/api/simulate`; logic stays in `src/` | **Confirmed** (hours source amended by 011) |
| 011 | Metric semantics: distance / cost / travel time; ML time model for all routes | **Confirmed** |

---

## Decision 001 — Current project direction — SUPERSEDED

> **Superseded on 2026-10-03 by Decision 004** (Source of Truth rewrite).
> Kept as history. The RL exclusion below still holds under 004; the
> algorithm-expansion, evidence-based-selection and remote-deployment
> goals do not.

**Decision (historical):** Nautilus's active development direction, as of this branch,
is:

- Routing algorithm expansion
- Scenario-based evaluation
- Evidence-based algorithm selection
- Remote Docker development
- Offline deployment

**Why:** This is what `docs/Source_Of_Truth.md` defines as the current,
authoritative project scope (§2–3, §50).

**Implication:** Reinforcement learning (RL/PPO) is **not** part of the
active roadmap. No RL implementation tasks, no RL architecture, and no RL
migration plan are to be created under this direction. The existing
Random-Forest speed model is a separate, already-existing component (not
RL) and may remain where the current routing implementation depends on
it, per Source of Truth §45 — but it is not the research focus and should
not become a mandatory dependency for future algorithms.

---

## Decision 002 — Docker as the development environment — CONFIRMED

> Still in force: the current Source of Truth §13 keeps Docker-based,
> reproducible execution. The remote-server motivation and Docker Hub
> publishing are no longer on the roadmap (see `TASKS.md`).

**Decision:** Docker will be used to provide a reproducible Nautilus
development/runtime environment, primarily for the remote server where
the developer may not have permission to install a system-wide
development stack (Source of Truth §27–31).

**Why:** Matches the stated Goal 4 (Remote and Containerized Development)
and Priority 1 (Reliable Infrastructure) in the Source of Truth.

**Implication:** TASK-001 targets a **development container** first
(source/workspace mounted, dependencies installed, able to run the
existing evaluation). A separate, minimal production/distribution image
(Source of Truth §30) is a later decision — not made now. Docker Compose
is adopted only if/when it proves useful during TASK-001, not decided
up front.

---

## Decision 003 — Offline-first core operation — CONFIRMED

> Still in force (current Source of Truth §13: offline evaluation with
> local data; external weather degrades gracefully). The rerouting
> simulation uses only local data. "Phase 7" below refers to the old
> roadmap; offline packaging is currently deferred.

**Decision:** Core routing and algorithm-comparison functionality must
not require continuous internet access. Normal route planning must work
from locally available application code, processed geographic/weather
data, port data, vessel data, and configuration (Source of Truth §32–33).

**Why:** Matches Goal 5 (Offline-Capable Marine Deployment) — the
marine-industry context cannot assume continuous connectivity.

**Implication:** Live weather (`src/live_weather.py`) remains optional
and non-mandatory; static `typical`/`rough` scenarios remain the
preferred basis for reproducible experiments and comparison (Source of
Truth §34). The exact offline packaging mechanism is **not** decided here
— deferred to Phase 7, after the core application is stable.

---

## Decision 004 — Project direction: ML-assisted dynamic rerouting — CONFIRMED

**Decision:** Nautilus is a weather-aware dynamic ship-rerouting system
enhanced by ML. Priorities: rerouting functionality, ML integration (speed
prediction; optional ML rerouting decisions), evaluation/demonstration,
practical engineering (Source of Truth §18).

**Source:** The user's rewrite of `docs/Source_Of_Truth.md`, present in
the working tree at the start of Loop 003 and committed in `6fdfd91`
(2026-10-03).

**Implication:** RL remains out of scope (§8.4). Adding routing
algorithms solely to increase their number is out of scope (§4). Work
follows the §16 phase order.

## Decision 005 — Rerouting reuses `Router.search` — CONFIRMED

**Decision (Loop 003):** Rerouting from the current position is
`Router.search(current_cell, destination_cell, ...)`; no new search
function or algorithm. `search` raises `ValueError` for a start/goal
outside the grid or on a non-navigable cell; `found=False` is reserved
for "no navigable path".

**Why (as recorded in Loop 003):** `search` already accepted any
`(row, col)`. Without validation, a non-navigable start next to water
returned a route starting on that cell, and a negative row index wrapped
around and returned `found=True` — silent navigability violations.

## Decision 006 — Compare routes by routing cost from one Router — CONFIRMED

**Decision (Loops 003–004):** Route comparison uses the search objective:
`RouteResult.cost` for a new route and `Router.path_cost(cells)` for an
existing (remaining) path, both from the **same** `Router` instance.
`time_hours` is not used for decisions.

**Why:** At the time, `time_hours` was distance at a constant 18 kn and
did not reflect the weather/ML cost the route was optimized for (Source
of Truth §10). Cost units differ between cost models (km; km × wave
multiplier; km at service speed with the ML model), so costs from
different routers are not comparable.

> **Still in force after Loop 007.** `time_hours` is now a meaningful
> travel-time estimate (Decision 011), but decisions still use cost only.
> `test_decisions_ignore_travel_time_model` verifies this.

## Decision 007 — Threshold-based rerouting controller — CONFIRMED (baseline)

**Decision (Loop 004):** `src/rerouting.RerouteController`, defaults in
`config.REROUTE_*`:

1. Score the remaining route under the latest weather.
2. Triggers (any): max `swh` on remaining route ≥ 4.0 m; remaining cost
   ≥ 5% above its cost under the weather it was planned with; periodic
   re-check every 4 steps **only if weather or route changed** since the
   last search.
3. No search within a 3-step cooldown after a route change, or if
   weather and route are unchanged since the last search.
4. Reject failed searches or invalid candidates ("failed"; route kept).
5. Adopt only if ≥ 3% **and** ≥ 20 cost units cheaper.

**Why (as recorded in Loop 004):** the periodic re-check was added
because the other two triggers only react to the active route getting
worse, so an alternative becoming cheaper (Source of Truth §9.1
"improving along an alternative") was never noticed; restricting it to
changed weather stopped it from re-firing every step. This is the
transparent baseline that any ML decision model (Phase 5) must beat.

## Decision 008 — Voyage simulation model — CONFIRMED (prototype)

**Decision (Loop 004):**

- Vessel position = index into the active route's cells; no lat/lon
  snapping during a voyage. On adoption the new route starts at the
  vessel's cell.
- Weather updates = deterministic Gaussian perturbations of significant
  wave height on an existing `Weather` (`src/weather_sim.py`); period and
  direction unchanged.
- One `Router` (cost model) is built per weather update; in the
  simulation the ML speed-based multiplier is the default cost model.

## Decision 009 — Test framework — CONFIRMED

**Decision (Loop 003):** Tests use stdlib `unittest` in `tests/`, run with
`python -m unittest discover -s tests`, using committed
`data/processed/` artifacts. No pytest dependency was added (none existed
and the brief said to avoid new dependencies).

## Decision 010 — Rerouting in the interface — CONFIRMED

**Decision (Loop 006):**

- Integrate into the **Flask** app only: it is the main interface, and its
  JSON API can be tested with Flask's test client. Streamlit is
  not integrated (the smallest change that fits the brief).
- New endpoint `POST /api/simulate`; existing endpoints unchanged apart
  from an added `simulation` key in `/api/meta`.
- Voyage execution, dynamic/static comparison and config validation live
  in `src/rerouting.py`; the weather-change
  location helper lives in `src/weather_sim.py`. `server.py` only
  validates the request and shapes JSON; `web/app.js` only draws it.
- The simulation always uses the ML speed cost model. Loop 006 converted
  cost to hours (cost ÷ (service kn × 1.852)). **Amended in Loop 007:**
  hours now come from `Router.path_hours` / `VoyageResult.sailed_hours` /
  `RouteResult.time_hours` (same numbers for the ML model, now one
  definition), and `cost_hours` was removed.
- Live weather is rejected for simulations (offline, deterministic).
- Every simulated figure is labeled "simulated"/"model", and the response
  carries a note that it is not real-world performance.

## Decision 011 — Route metric semantics and travel-time model — CONFIRMED

**Decision (Loop 007):** see Source of Truth §10.1.

- **Distance** (km): path length. **Cost**: the search objective, with
  units that depend on the cost model. **Travel time** (h): Σ segment km ÷
  segment speed, from a time model held by the `Router` (`speed_kn`,
  `time_mult`) that is **separate from the cost model**.
- Every application path (evaluation, `/api/route`, Streamlit,
  simulation) uses the vessel's ML speed model for travel time, for
  **all** routes, including Dijkstra and A* on the analytic wave cost. So
  hours are comparable across algorithms; only the objective differs.
- The analytic wave cost is never converted to hours. A `Router` with no
  ML time model reports calm-water time at `speed_kn`, and a bare
  `Router(grid)` keeps the old 18 kn behaviour for backward
  compatibility. Results carry `time_basis`.
- Route selection, rerouting thresholds and decisions are unchanged.

**Why (as recorded in Loop 007):** before this, every route reported
distance ÷ 18 kn regardless of vessel and weather. For General Cargo in
`rough` weather the ML-estimated time was 29% higher than reported
(114.4 h vs 88.6 h, Mumbai → Chennai). It also made A* look slower than Dijkstra on
Cochin → Dubai (92.1 vs 83.1 h), when under the ML model it is faster
(128.9 vs 135.0 h). ML cost was verified to be proportional to time; the
4× multiplier cap binds on 0.5% of moves (`rough`, General Cargo) and
floors speed at service ÷ 4, about the model's own minimum prediction.

---

## Unresolved choices

- **Next goal:** multi-voyage static-vs-dynamic evaluation (Phase 4
  remainder) is proposed in `TASKS.md` but not confirmed by the user.
- **A* heuristic:** whether to correct the latitude scaling (possible
  overestimate north of ~13.5°N). See `BLOCKERS.md` C3.
- **Rejected-alternative re-search:** the controller does not re-search
  while weather and route are unchanged, even though a rejected
  alternative's *relative* gain can grow as the voyage shortens. Kept for
  now; revisit if Phase 4 evaluation shows missed reroutes.
- **ML model artifact:** retrain under scikit-learn 1.9.0 or pin 1.8.0
  (`BLOCKERS.md` C5).

---

## Decisions explicitly NOT made in Loop 000 (historical)

- No final set of routing algorithms beyond what already exists.
- No recommendation-scoring formula or metric weighting.
- No offline-packaging technology choice.
- No production/distribution Docker image design.
- No resolution of the ETA discrepancy noted in `PROJECT_STATE.md` — it
  is recorded as an open item for Phase 2, not decided or fixed now.
