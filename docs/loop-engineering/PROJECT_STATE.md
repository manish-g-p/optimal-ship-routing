# Project State

**Last updated:** 2026-10-06 (Loop 010 — navigational safety and reroute geometry)
**Branch / commit verified:** `feature/dynamic-routing`, working tree on
top of `ee4da2b` (Loop 010 changes not yet committed when written)

What is actually true in the repository now — verified against the code
and test runs, not taken from other documents. Project direction and
scope are defined in [`docs/Source_Of_Truth.md`](../Source_Of_Truth.md).
The previous version of this file (written for the pre-2026-10-03 Source
of Truth) is in git at commit `79f130b`.

---

## Project direction (from the Source of Truth)

Nautilus is an **ML-assisted dynamic ship-rerouting system** for the
waters around India (0–27°N, 50–100°E, 0.05° grid ≈ 5.5 km/cell): route a
voyage, track simulated progress, react to weather changes by
recalculating from the vessel's current position, compare routes under
consistent costs, and use the Random Forest speed model for weather-aware
costs. Reinforcement learning and adding routing algorithms for their own
sake are out of scope.

## Roadmap status (Source of Truth §16)

| Phase | Status |
| --- | --- |
| 1 — Rerouting foundation | **Done** (ETA/cost consistency completed in Loop 007) |
| 2 — Weather updates and rerouting triggers | **Done (simulation only)** — Loop 004 |
| 3 — ML speed prediction integration | **Mostly done** (Loop 007) — ML speed drives costs and all travel times; model artifact skew (C5) open |
| 4 — Evaluation and visualization | **Done** — Flask UI (Loop 006); static-vs-dynamic evaluation of 150 voyage/vessel/scenario pairs (Loop 008, EXP-006) |
| 5 — Experimental ML rerouting decisions | Not started; optional |

## Implemented and verified

**Data and grid (pre-existing)**

- `src/preprocess.py`: raw GEBCO/ERA5 NetCDF → `data/processed/`
  (`bathymetry.npz`, `weather.npz`, `weather_grid.csv`). Raw `.nc` files
  are not tracked and are not needed when `data/processed/` is present.
- `src/grid.py`: navigable mask (depth ≥ 10 m, ≥ 22 km from barrier),
  main-basin restriction for port snapping, KD-tree `nearest_cell`.
- `data/processed/*` is git-tracked (force-added despite `.gitignore`).

**Weather (pre-existing)** — `src/weather.py`: `typical`/`rough` static
scenarios resampled onto the grid (`swh`, `mwp`, `mwd`); analytic wave
multiplier. `src/live_weather.py`: optional Open-Meteo source used by the
Flask app's `live` scenario (not used by rerouting).

**ML speed model (pre-existing)** — `src/ml_model.py`: RandomForest
predicting attainable speed from sea state and vessel, trained on
**synthetic** physics-inspired data. `build_multiplier_grid` turns it into
a per-cell, per-direction cost multiplier (`service_speed / predicted`),
used by weather-aware A* in `evaluate.py`, `server.py` and the rerouting
simulation.

**Routing** — `src/routing.py`:

- `Router.search(start, goal, use_weather, use_heuristic)`: Dijkstra
  (distance) or weather-aware A* on the 8-connected grid. Accepts **any
  navigable `(row, col)` start**, which is how rerouting from the current
  position works.
- Invalid start/goal (outside grid or non-navigable) raises `ValueError`;
  `found=False` means no navigable path (Loop 003).
- `RouteResult`: `algorithm, found, cells, latlon, distance_km,
  time_hours, max_wave_m, mean_wave_m, expanded, cost, time_basis`.
  `cost` is the accumulated search cost (Loop 003).
- `Router.path_cost(cells, use_weather)`: scores any path with the same
  step costs as the search (Loop 003).
- **Safety constraints (Loop 010, Decision 014):**
  - `Router(min_depth_m=…)` makes cells shallower than the vessel's
    requirement impassable: `vessel.required_depth_m` = draft × 1.2.
  - Infeasible routes return `found=False` with a `reason`;
    `rerouting.InfeasibleRoute` is raised for voyages. Clearance
    (`COAST_BUFFER_KM`) is applied at `grid.load_grid()`;
    `grid.dist_to_barrier_km` is exposed.
  - Optional soft `coast_penalty` (default 0). Callers opt in: A* uses
    `config.COAST_PENALTY`, Dijkstra stays pure distance.
  - `search(extra_cost=…)` takes a per-search cost multiplier (used by the
    route-change preference).
- **Travel time (Loop 007):** `Router(..., speed_kn=, time_mult=)` holds a
  time model separate from the cost model. `Router.path_hours(cells)` =
  Σ segment km ÷ (speed × 1.852), with the per-segment speed taken from the
  ML multiplier (`time_basis="ml_speed"`) or calm water
  (`"calm_water"`). `time_hours` = `path_hours` rounded to 0.1 h. A bare
  `Router(grid)` keeps the old calm-water 18 kn behaviour. `evaluate.py`,
  `/api/route`, Streamlit and the rerouting simulation all pass the
  vessel's ML time model. Definitions: Source of Truth §10.1.

**Dynamic rerouting (simulation)** — Loop 004:

- `src/weather_sim.py`: deterministic weather updates as Gaussian
  wave-height perturbations of an existing `Weather`; named scenarios
  `stable, adverse, worsening, improving_alt, minor, shifting`.
- `src/rerouting.py`: `RerouteConfig`, `RerouteController`, `simulate()`,
  `VoyageResult`, `router_factory()`, and a console scenario evaluation
  (`python -m src.rerouting`). Vessel position is an index into the
  active route's cells; each weather update rebuilds the cost model;
  every evaluation is logged as a `RerouteEvent` (triggers, decision,
  reason, costs). Decision rules and defaults: see `DECISIONS.md` D007
  and the `REROUTE_*` settings in `config.py`.

**Route-planning evaluation (pre-existing)** — `src/evaluate.py`: 5
fixed voyages, Dijkstra vs. A*+ML under `rough` weather, writes
`data/processed/evaluation.csv` (committed baseline; route columns
unchanged since Loop 000; hour columns corrected in Loop 007; unchanged by
Loop 008).

**Rerouting evaluation (Loop 008)** — `src/evaluate_rerouting.py`: every
`evaluate.VOYAGES` voyage × all 5 vessels × all 6 `weather_sim` scenarios
(`typical` base, default `RerouteConfig`). Each combination runs as a
`compare_voyage` pair (rerouting on/off). Every run gets a status (`ok`,
`draft_infeasible`, `incomplete`, `failed`) and an outcome (improved /
unchanged / worsened, tolerance 0.1 h). Writes `data/rerouting_eval/`
(runs, events, summaries by voyage/vessel/scenario/overall, config.json,
heatmap), kept separate from `data/processed/`. Current results: 144 ok,
6 draft-infeasible; 88 improved, 50 unchanged, 6 worsened (EXP-006).

**Interfaces** — Flask (`server.py` + `web/`, Google Maps, JSON API) and
Streamlit (`app.py`), both pre-existing. Since Loop 006 the Flask app
has a **"Voyage replay" mode** (called "Voyage simulation" before Loop 009), backed by `POST /api/simulate`, which calls
`rerouting.compare_voyage`. It takes ports, vessel, Typical/Rough base
weather, a `weather_sim` scenario and optional `RerouteConfig` overrides
(validated by `rerouting.config_from_dict`). It returns the initial plan, the
sailed track, the final route, dynamic and static voyage metrics, the
rerouting evaluations that had a trigger, and the simulated weather-change
locations. The UI draws these with a step slider. It always uses the ML speed
cost model, and live weather is rejected. `/api/meta` gained a `simulation`
key; `/api/route` is unchanged. Streamlit does not expose rerouting.

**Simulation lab (Loop 009)** — third Flask mode for interactive
voyages:

- **Engine:** `rerouting.Voyage` is a step-by-step voyage; `simulate()`
  is now a loop over it (150-pair evaluation re-run byte-identical).
  `src/sim_session.py` holds `SimSession`: a configured voyage plus a
  no-rerouting twin under the same weather; applied and pending
  disturbance lists; preset schedule; timeline; locks. `SessionStore`
  keeps sessions in memory (≤ 8, 30 min idle TTL).
- **Weather:** `weather_sim.apply_disturbances` (base + Gaussian swh
  bumps, base untouched) and `weather_sim.PRESETS`, 8 deterministic
  demonstration schedules.
- **API:** `/api/sim/presets` and `/api/sim/sessions[/<id>[/step|/weather|
  /weather/apply|/weather/discard|/schedule/cancel|/reset|/weather_image]]`.
  `expected_step` makes steps idempotent. A busy session returns 409;
  internal errors return a generic 500.
- **UI** (`web/`): control bar (start/pause/resume/step/reset, speed,
  progress); weather panel (place by map click, drag to move, edit or
  remove, pending vs applied, apply/discard, cancel schedule); live
  metrics with a no-rerouting comparison; decision timeline linked to
  map markers. The overlay is rendered from the applied weather field.

**Infrastructure (pre-existing)** — `docker/Dockerfile`,
`docker/docker-compose.yml`, root `.dockerignore`, `DOCKER.md`; pinned
`requirements.txt`; `config.py` as the single configuration module,
secrets from `.env` (template `.env.example`). Offline: evaluation, tests
and the rerouting simulation run with `--network none` (verified, see
`VALIDATION.md`).

**Tests** — `tests/` (stdlib `unittest`, committed data, no network):
`test_routing.py` (8 tests: initial-route regression, cost, rerouting
from intermediate/off-route positions, invalid positions) and
`test_rerouting.py` (16 tests: scenarios A–E, decisions independent of
the time model) and `test_server.py` (10 tests: `/api/meta`, `/api/route`
routes unchanged with corrected hours, time without ML cost, unknown
vessel, `/api/simulate` cases). `test_routing.py` also has 7
`TravelTimeTests` (independent per-segment RF calculation, cost↔time
relation, vessel profiles, weather changes, calm-water default).
`test_evaluate_rerouting.py` (14 tests: matrix coverage, pairing, metric
and status calculations, failed-run handling, summary-vs-detail,
determinism on a real subset). `test_sim_session.py` (20 tests: session
lifecycle, batch-engine parity, pending vs applied weather, manual storm →
real reroute, preset/manual merging, validation, failure handling, store
limits, API flow, invalid requests, busy/500 handling, existing endpoints).
`test_safety.py` (19 tests: depth feasibility and reasons, configurable
clearance, soft penalty vs. time, safe alternatives, infeasible voyages,
reroute continuity, route-change penalty and tie selection, API).
94 tests pass (Loop 010). Browser end-to-end: `tools/lab_e2e.mjs` (36
checks); host-vs-Docker parity: `tools/lab_parity.py`.

## Planned (not implemented)

- Phase 3 remainder: resolve the scikit-learn pickle skew (retrain or
  pin) — `BLOCKERS.md` C5.
- Rerouting evaluation extensions: `rough` base weather, threshold
  sensitivity, counterfactual missed-reroute measurement (not started).
- Phase 5 (optional): ML rerouting-decision experiment vs. the
  threshold baseline.

## Deferred / superseded (from the previous Source of Truth)

Docker Hub publishing and remote-server deployment (old TASK-002–004),
additional routing algorithms, a generic scenario/evidence/recommendation
framework, an algorithm-comparison UI, and offline packaging are **not**
in the current roadmap. See `TASKS.md` → Historical tasks.

## Known limitations (details in `BLOCKERS.md`)

- Travel time is an estimate from a speed model trained on synthetic
  data, bounded to [service ÷ 4, service] speed; it is not a real-world
  ETA. Rerouting decisions use `cost`, never hours.
- `cost` units depend on the cost model; compare costs only from the
  same `Router`. The analytic wave cost is not time.
- A* heuristic may overestimate east–west distance north of ~13.5°N
  (up to ~9% at 27°N); its docstring calls it admissible.
- Rerouting is simulation-only: synthetic `swh`-only perturbations,
  movement in fixed cells per step (not time-based), thresholds and
  scenarios designed on one voyage (Cochin → Dubai, General Cargo).
  Evaluated on 5 voyages × 5 vessels (EXP-006): it worsened 6/144 runs,
  all under moving weather; decisions assume the current weather persists.
- Depth uses GEBCO MSL depths at 0.05° plus a 20% margin; this is not a
  navigational chart. Port approach cells can be far offshore and too
  shallow for deep-draft vessels: Kandla → Cochin is infeasible for the
  Container Ship and VLCC (`BLOCKERS.md` C14). Routes follow the 22 km
  clearance edge on coastal legs (C15).
- Voyage replay: the wave overlay shows the base weather, not the
  simulated storms (those are drawn as circles at the peak change); one
  request runs the voyage twice and can take several seconds (≈4 s for
  `adverse`, measured); not in Streamlit.
- Simulation lab: sessions live in one process's memory (lost on restart,
  not shared across workers); each weather change rebuilds the ML cost
  grid (~1.2 s); remaining/projected hours assume the current weather
  persists; only wave height is simulated (`BLOCKERS.md` C13).
- ML model is trained on synthetic data; pickle written with
  scikit-learn 1.8.0 and loaded under 1.9.0 (warning, no observed effect).

## Entry points

| Command | What it does |
| --- | --- |
| `python -m src.preprocess` | Raw NetCDF → `data/processed/` (needs the raw `.nc` files). |
| `python -m src.grid` | (Re)builds `grid.npz`. |
| `python -m src.ml_model` | Trains/saves `speed_model.joblib`. |
| `python -m src.evaluate` | 5-voyage Dijkstra vs. A*+ML evaluation → `evaluation.csv`. |
| `python run_all.py` | preprocess (if needed) → train (if needed) → evaluate. |
| `python -m src.rerouting` | Dynamic-rerouting scenarios, dynamic vs. static voyage (one voyage). |
| `python -m src.evaluate_rerouting` | Full rerouting evaluation matrix (150 pairs, ~9 min) → `data/rerouting_eval/`. |
| `python -m unittest discover -s tests -v` | Test suite (~45 s). |
| `python server.py` | Flask UI/API on port 8000 (Maps key optional, via `.env`); route planning, voyage replay and Simulation lab modes. |
| `streamlit run app.py` | Streamlit UI on port 8501. |

All of these also run in the `nautilus-dev` Docker image; see `DOCKER.md`.

## Configuration (`config.py`)

Region 0–27°N, 50–100°E · grid 0.05° · min depth 10 m · coast buffer
22 km · nominal speed 18 kn · wave weights `W_WAVE_HEIGHT=0.6`,
`W_HEAD_SEAS=0.4`, `W_PERIOD=0.1` · `MAX_WEATHER_MULT=4.0` · rerouting
defaults `REROUTE_*` (cells/step 10, eval interval 1, cooldown 3, wave
trigger 4.0 m, cost trigger 5%, periodic re-check 4 steps, min gain 3% and
20 cost units). These are modeling assumptions, not maritime rules.
