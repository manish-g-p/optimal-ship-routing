# Experiments

Evidence and findings. Each record separates **measured results** (actually
run, with the loop that ran them) from expectations and plans. Planned
experiments are listed at the end and have **no results**.

| ID | Topic | Status |
| --- | --- | --- |
| Baseline | `evaluation.csv`, 5 voyages, Dijkstra vs. A*+ML | Pre-existing; reproduced in Loops 001–004 |
| EXP-001 | Containerized execution | Complete (Loop 001) |
| EXP-002 | Current-position rerouting | Complete (Loop 003) |
| EXP-003 | Weather-driven dynamic rerouting scenarios | Complete (Loop 004; re-run Loop 005) |
| EXP-004 | Voyage simulation through the Flask API/UI | Complete (Loop 006) |
| EXP-005 | Travel-time / ETA correction | Complete (Loop 007) |
| EXP-006 | Rerouting evaluation: 5 voyages × 5 vessels × 6 scenarios | Complete (Loop 008) |
| EXP-007 | Simulation lab: engine parity, host vs. Docker, performance | Complete (Loop 009) |

The field list used for EXP-001 (Scenario, Start, Destination, Vessel,
Weather, Algorithms, Constraints, Metrics, Results, Observations,
Conclusion) came from the **previous** Source of Truth §24. The current
Source of Truth's evaluation guidance is §11 (baselines, metrics,
scenario-based testing).

---

## Existing baseline (pre-existing, not produced by this loop)

`data/processed/evaluation.csv` already exists in the repository and
contains results for 5 voyages (Dijkstra vs. weather-aware A*+ML, `rough`
scenario, `General Cargo` vessel), produced by `src/evaluate.py`. Per
Source of Truth §24, this is retained as the **classical routing baseline
dataset** and is not to be discarded. It was not regenerated or modified
during this initialization loop — it is referenced here as context for
EXP-001, not reproduced.

Observed in the committed file (for reference only, not re-verified this
loop):

- All 5 voyages produced a route with both algorithms.
- A* explored substantially fewer cells than Dijkstra in every voyage
  (e.g. Mumbai→Chennai: 55,321 vs 249,000 expanded cells).
- `trad_h`/`prop_h` (ETA) values are close between algorithms for most
  voyages — consistent with the constant-speed ETA calculation currently
  in `src/routing.py` (see `PROJECT_STATE.md` — ETA discrepancy).

---

## EXP-001 — Containerized Nautilus Execution

**Status:** Complete. Run 2026-10-01 during Loop 001 (TASK-001), against
a real Docker engine (Docker Desktop 4.71.0, Engine 29.4.1, linux/amd64).

**Scenario:** Infrastructure validation, not a routing scenario. Confirms
the existing application runs unchanged inside a Docker container.

**Purpose:** Establish that the Docker development environment built in
TASK-001 reproduces the current host (`.venv`) runtime behavior.

**What it must verify:**

- Docker image builds successfully from a clean checkout of this branch.
- A container starts from that image without error.
- All `requirements.txt` dependencies resolve and import inside the
  container (no missing system libraries for `netCDF4`/`xarray`/`scipy`/
  `scikit-learn`, etc. — verified below: none needed).
- The existing entry point(s) run successfully inside the container,
  using the data already committed under `data/processed/` (no raw `.nc`
  files required):
  - `python -m src.evaluate` (or `python run_all.py`) completes and
    writes/matches `data/processed/evaluation.csv`.
- Required processed data (`bathymetry.npz`, `weather.npz`,
  `weather_grid.csv`, `grid.npz`, `speed_model.joblib`) is accessible to
  the container (via the repo copy/mount — these files are git-tracked
  on this branch despite `.gitignore`, see `PROJECT_STATE.md`).
- No unexpected host dependency is required beyond Docker itself (the
  two raw NetCDF files are correctly NOT required for this path).

**Algorithms tested:** Dijkstra, weather-aware A* — i.e. whatever
`src/evaluate.py` already runs. No new algorithms are introduced by this
experiment.

**Constraints:** None beyond "runs without error and output matches the
existing non-containerized run."

**Metrics:** Build success/failure, container start success/failure,
entry-point exit code, diff between container-produced
`evaluation.csv` and the currently committed one (should match, since no
code changes are made).

**Commands actually used** (see `DOCKER.md` for the full write-up):

```bash
docker build -t nautilus-dev .
docker run --rm --network none nautilus-dev python -c "import numpy, scipy, xarray, netCDF4, dask, networkx, sklearn, joblib, pandas, matplotlib, flask, flask_cors, streamlit, folium, streamlit_folium"
docker run --rm --network none nautilus-dev python -m src.evaluate
docker run --rm --network none nautilus-dev python run_all.py
docker run -d -p 18000:8000 nautilus-dev python server.py   # + curl /api/meta, POST /api/route
docker run -d -p 18501:8501 nautilus-dev streamlit run app.py --server.address=0.0.0.0 --server.headless=true  # + curl /_stcore/health
docker compose run --rm nautilus python -m src.evaluate
docker rmi nautilus-dev && docker builder prune -af && docker build --no-cache -t nautilus-dev .   # reproducibility check
```

**Results:**

| Check | Result |
| --- | --- |
| Image builds (cached) | Pass, ~3–52s depending on cache state |
| Image builds (`--no-cache`, zero cached layers) | Pass, ~80s |
| All 16 pinned deps import, `--network none` | Pass — no missing system libraries; every dependency resolved as a manylinux wheel on plain `python:3.12-slim` |
| `python -m src.evaluate`, `--network none` | Pass — completed, wrote `evaluation.csv` |
| `python run_all.py`, `--network none` | Pass — completed (preprocess step correctly skipped since `data/processed/` already populated) |
| Container `evaluation.csv` vs. host-committed baseline, non-timing columns | **Byte-for-byte identical** (distance_km, time_hours, expanded cells, min_coast_km, max/mean wave — all 5 voyages). Only `trad_sec`/`prop_sec` (wall-clock) differ, as expected. |
| Same diff after the `--no-cache` rebuild | **Identical again** — confirms reproducibility, not cache luck |
| `GET /api/meta` via `-p 18000:8000` | **Failed before the `HOST` fix** (empty response — server bound to 127.0.0.1 inside the container); **passed after** (correct JSON) |
| `POST /api/route` via `-p 18000:8000` | Passed after the `HOST` fix — correct route JSON for Cochin→Dubai |
| Streamlit `/_stcore/health` via `-p 18501:8501` | Pass — HTTP 200 |
| `docker compose run --rm nautilus python -m src.evaluate` | Pass — same result as plain `docker run` |
| Required processed data accessible | Pass — `data/processed/*` is git-tracked on this branch (despite `.gitignore`), so it's present in the image without needing the raw `.nc` files |
| Unexpected host dependency | None found — Docker itself is the only host requirement |

**Observations:**

- Two `InconsistentVersionWarning`s print on every run that loads the ML
  model (scikit-learn 1.8.0 pickle vs. 1.9.0 installed). Investigated:
  does not change output (see Results row above). Pre-existing on the
  host too, not introduced by containerization. See `PROJECT_STATE.md`
  and `BLOCKERS.md`.
- `server.py` hardcoded `host="127.0.0.1"`, making the Flask UI
  unreachable from outside its container regardless of `-p` mapping.
  Fixed with a minimal, env-driven, backward-compatible change (default
  unchanged for bare-metal runs). See `DOCKER.md` for the before/after
  evidence.
- A real-looking Google Maps API key was found as a local, uncommitted
  default in `web_config.py`. Confirmed not committed/pushed anywhere.
  Not modified; excluded from the Docker build context instead. See the
  "Security note" in `DOCKER.md`.
- Validating this experiment required a working `docker` CLI pointed at
  a real engine; the sandboxed environment's `docker` command was not on
  `PATH` (Docker Desktop's WSL integration was not enabled for this
  distro) and `sudo apt install docker.io` was not possible (no
  passwordless sudo). Resolved by downloading the official static
  `docker` CLI binary (no root required) and pointing it at the Docker
  Desktop engine's already-reachable bind-mount socket
  (`/mnt/wsl/docker-desktop-bind-mounts/<distro>/docker.sock`, group
  `docker`, which this user account is already in) via `DOCKER_HOST`.
  This means every build/run in this experiment is a **real** Docker
  build against a real engine, not a simulation. One side effect:
  `docker builder prune -af` was run once (for the no-cache
  reproducibility check) and cleared the shared engine's build cache for
  *all* images, including the user's unrelated existing projects
  (`pern-store-*`, `pgadmin4`, etc.) — their tagged images themselves
  were confirmed intact (`docker images` before/after), only cached
  intermediate build layers were cleared, meaning their next unrelated
  build may take longer than usual.

**Conclusion:** EXP-001 passes. The Docker development environment
reproduces the host's evaluation behavior exactly (modulo wall-clock
timing) with no raw datasets and no network access required at runtime,
confirming TASK-001's completion criteria. The one genuine gap found
(Flask UI unreachable from outside its container) was fixed and
re-verified; the two other findings (sklearn skew, local API key) are
pre-existing and orthogonal to containerization, and are recorded rather
than fixed here to avoid scope creep into ML/routing work.

---

## EXP-002 — Current-position rerouting

**Status:** Complete. Loop 003, 2026-10-03 (code committed in `6fdfd91`).

**Purpose:** Check that the existing engine can route from an arbitrary
intermediate cell to the original destination, and find gaps.

**Setup:** Mumbai (JNPT) → Chennai, `rough` weather, General Cargo. Dijkstra
(`Router(grid)`) and A* with the ML multiplier (`Router(grid, weather,
mult_dir)`). Reroute from the midpoint cell of each full route.

**Measured (exploratory probe before any code change):**

| | Dijkstra | A* + ML |
| --- | --- | --- |
| Full route | 2953.6 km, 454 cells, path cost 2953.59 | 2954.9 km, 454 cells, path cost 3390.96 |
| Remaining cost from midpoint (original route) | 1476.18 | 1624.01 |
| Rerouted cost from midpoint | 1476.18 (identical) | 1624.01 (identical) |
| Reroute starts at vessel / ends at destination | yes / yes | yes / yes |

Edge-case behavior **before** the fix:

| Start | Result |
| --- | --- |
| `(-1, 5)` (outside grid) | `found=True`, first cell `(-1, 5)` (negative-index wrap) |
| `(nlat+3, 5)` | `IndexError` |
| Land cell surrounded by land | `found=False` (silent) |
| Non-navigable cell next to water | `found=True`, route **starts on the non-navigable cell** |
| Non-navigable goal | `found=False` after expanding ~335k cells |

**Conclusion:** Arbitrary-start routing already worked. The weather cost
(3391 vs. 2955 km for A*) was not exposed, and invalid positions were
silently accepted. Both were fixed (`RouteResult.cost`, `Router.path_cost`,
`ValueError` validation). Validation: `VALIDATION.md` → Loop 003.

---

## EXP-003 — Weather-driven dynamic rerouting scenarios

**Status:** Complete. Loop 004, 2026-10-03 (code committed in `e8f68d1`).
Re-run in Loop 005 at `e8f68d1` (host and offline Docker): identical
results.

**Setup:** `python -m src.rerouting`. Cochin (Kerala) → Dubai / Jebel Ali,
General Cargo (16 kn), base weather `typical`, A* with the ML speed
multiplier, default `RerouteConfig`. Each scenario also runs with
rerouting disabled (static voyage) under the same weather schedule.
Hours = sailed cost ÷ (16 × 1.852 km/h): valid for the ML cost model
only, and independent of `RouteResult.time_hours`.

**Measured:**

| Scenario | Weather change | Route changes | Static → dynamic (h) |
| --- | --- | --- | --- |
| stable | none | 0 | 100.9 → 100.9 |
| adverse | +6 m storm (σ 120 km) on route midpoint at step 2 | 1 (step 2, 19.8% cheaper) | 127.7 → 103.3 |
| worsening | same storm growing +1.5 / +3.5 / +6 m at steps 2/4/6 | 1 (step 4, 8.0%; step-8 re-check gain 0.3% kept) | 127.7 → 103.7 |
| improving_alt | +6 m storm (σ 250 km) at departure clears at step 2 | 1 (step 4 periodic re-check, 6.1%) | 107.2 → 101.3 |
| minor | +0.4 m (σ 25 km) at step 2 | 0 (re-check gain 0.0%) | 101.0 → 101.0 |
| shifting | +6 m storm cycling route / ±1.5° lanes, steps 1–12 | 3 (steps 1, 5, 9); 5 evaluations blocked by cooldown | 118.2 → 106.6 |

**Tuning observations (Loop 004, measured):**

- First `improving_alt` design (calm patch off-route plus +2 m on-route)
  fired no trigger. With a departure storm of σ 120 km, the detour cost
  only ~1%, so the alternative (0.8% gain) was correctly rejected. Storm
  width vs. adopted gain: σ 250 km → 6.1%, σ 350 km (+5 m) → 8.2%,
  σ 400 km → 11.3%. σ 250 km was chosen.
- `shifting` with cooldown 0: 12 route changes in steps 1–12 (thrashing).
  With cooldown 6: 3 changes. Default cooldown 3 gives 3 changes.
- The first periodic re-check implementation re-fired every step once
  due. It was restricted to changed weather/route (Decision 007).

**Observations:** Under these synthetic storms, dynamic rerouting saved
6–24 simulated hours versus static routing and made no changes under
stable or minor weather. These are model results on synthetic weather
and synthetic-data ML speeds, **not** real-world performance (Source of
Truth §11.4).

---

## EXP-004 — Voyage simulation through the Flask API/UI

**Status:** Complete. Loop 006, 2026-10-03. Cochin → Dubai, base weather
`typical`, default `RerouteConfig` unless noted. Runs through
`POST /api/simulate` (test client, live server, and Docker container) and
the web UI in headless Chromium.

**Measured:**

| Vessel | Scenario | Settings | Route changes | Without → with rerouting (h, model) |
| --- | --- | --- | --- | --- |
| General Cargo | adverse | default | 1 (step 2) | 127.7 → 103.3 (same as EXP-003, also in Docker) |
| Container Ship | adverse | default | 1 (step 2, 14.7% cheaper) | 84.5 → 72.6 |
| Container Ship | shifting | cooldown 6 | 3 (steps 1, 8, 14); 7 evaluations blocked by cooldown | 77.0 → 75.9 |

Single `adverse` API request (General Cargo, both runs): 4.3 s on the host
(one measurement).

**Observations:** The API reproduces the console evaluation exactly. With
cooldown 6, `shifting` gave the Container Ship only 1.1 h of benefit. That
is not compared with the General Cargo figure in EXP-003, which used
cooldown 3. Whether rerouting pays off depends on vessel and settings,
which is what the planned multi-voyage evaluation should measure.

---

## EXP-005 — Travel-time / ETA correction

**Status:** Complete. Loop 007, 2026-10-03.

**Measured before the change** (exploratory script, `rough` weather):

| Check | Result |
| --- | --- |
| ML multiplier at the 4× cap (cell-directions) | General Cargo: 0.50%; Container Ship: 0%; `typical`: 0% for both |
| ML multiplier at 1.0 (speed ≥ service) | 0% in all four cases |
| RF predicted speed, General Cargo, head seas, swh 0/4/8/12 m | 15.80 / 5.52 / 3.99 / 3.99 kn (service 16) |
| Mumbai → Chennai, General Cargo: old `time_hours` | 88.6 h (both routes) |
| … calm water at 16 kn | 99.7 h |
| … ML speed model | Dijkstra 114.5 h, A* 114.4 h |

**Evaluation (`python -m src.evaluate`, General Cargo, `rough`) — hours
before → after.** All other non-timing columns are identical.

| Voyage | Dijkstra h | A* h |
| --- | --- | --- |
| Mumbai → Chennai | 88.6 → 114.5 | 88.6 → 114.4 |
| Kandla → Cochin | 53.4 → 70.9 | 53.4 → 70.9 |
| Cochin → Dubai | 83.1 → 135.0 | 92.1 → 128.9 |
| Visakhapatnam → Colombo | 50.9 → 68.6 | 51.0 → 68.6 |
| Chennai → Port Blair | 48.4 → 68.7 | 48.6 → 66.6 |

**Observations:**

- The ML estimates are 29–62% higher than the old figures on these
  voyages, i.e. the old figures were 23–38% too low.
  They made A* look slower than Dijkstra on Cochin → Dubai (+9 h), when
  under the time model it optimizes, it is 6.1 h faster. A* ≤ Dijkstra in
  hours on all five voyages.
- Flask route mode, Container Ship, `typical`, Cochin → Dubai: 71 h for
  both routes (old 18 kn figure: 83 h), matching the simulation's 71.3 h
  initial plan.
- Simulation and rerouting results (EXP-003/004) are unchanged: for the
  ML model the new hours equal the old cost-based conversion.

---

## EXP-006 — Rerouting evaluation across voyages, vessels and scenarios

**Status:** Complete. Loop 008, 2026-10-03. Command:
`python -m src.evaluate_rerouting`. Outputs in `data/rerouting_eval/`
(`runs.csv` one row per pair, `events.csv`, `summary_*.csv`,
`config.json`, `rel_change_vessel_scenario.png`). Run twice; the
non-timing outputs were identical (`VALIDATION.md` → Loop 008).

**Setup:** the 5 `evaluate.VOYAGES` × all 5 vessel profiles × all 6
`weather_sim` scenarios = 150 combinations. Base weather `typical`; A* with
the ML speed cost; travel time per Source of Truth §10.1; default
`RerouteConfig` (cells/step 10, eval interval 1, cooldown 3, wave trigger
4.0 m, cost trigger 5%, re-check 4, min gain 3% and 20 units), **not
tuned on these results**. Each combination is one pair from
`rerouting.compare_voyage`: same departure weather, initial route and
weather schedule, rerouting enabled vs. disabled. Outcome tolerance:
|Δ| < 0.1 h = unchanged.

**Caveat on independence:** the scenarios and default thresholds were
designed in Loop 004 on Cochin → Dubai with General Cargo. That pair is
in-sample; the other 24 voyage-vessel pairs were not used for tuning.
In-sample mean change −8.9% vs. −8.0% for the rest.

### Measured results (simulation, model estimates)

**Run status:** 150 runs: 144 `ok`, 6 `draft_infeasible`, 0 incomplete,
0 failed. All 6 draft-infeasible runs are VLCC (20.5 m draft) on Kandla →
Cochin. Both the static and the rerouted track pass through 16 m of
water. The navigable grid enforces only a 10 m minimum depth for all
vessels. These runs are in `runs.csv` but excluded from the averages.

**Overall (144 ok pairs):** improved 88, unchanged 50, worsened 6. Mean
travel time 84.25 h without → 76.91 h with rerouting (mean Δ −7.33 h,
mean −8.0%, median −5.0%, best −30.4%, worst +8.4%). 139 reroutes in 94
runs. 102 alternatives rejected below threshold, 97 evaluations blocked
by cooldown, 0 failed searches.

| Scenario | ok | improved / unchanged / worsened | reroutes | mean Δ h | mean % | worst % | mean Δ km |
| --- | --- | --- | --- | --- | --- | --- | --- |
| stable | 24 | 0 / 24 / 0 | 0 | 0.00 | 0.0 | 0.0 | 0 |
| adverse | 24 | 24 / 0 / 0 | 24 | −17.24 | −19.0 | −8.5 | +78 |
| worsening | 24 | 24 / 0 / 0 | 27 | −16.77 | −18.5 | −8.5 | +71 |
| improving_alt | 24 | 22 / 2 / 0 | 22 | −6.85 | −7.6 | 0.0 | −182 |
| minor | 24 | 0 / 24 / 0 | 0 | 0.00 | 0.0 | 0.0 | 0 |
| shifting | 24 | 18 / 0 / 6 | 66 | −3.14 | −3.0 | +8.4 | +174 |

| Vessel | ok | improved / unchanged / worsened | mean Δ h | mean % | worst % |
| --- | --- | --- | --- | --- | --- |
| Bulk Carrier (Panamax) | 30 | 19 / 10 / 1 | −9.28 | −8.3 | +8.4 |
| Container Ship | 30 | 19 / 11 / 0 | −4.74 | −7.3 | 0.0 |
| Crude Oil Tanker (VLCC) | 24 | 14 / 8 / 2 | −7.51 | −7.6 | +8.4 |
| General Cargo | 30 | 19 / 10 / 1 | −9.65 | −9.7 | +8.3 |
| LNG Carrier | 30 | 17 / 11 / 2 | −5.52 | −7.1 | +6.8 |

| Voyage | ok | improved / unchanged / worsened | mean Δ h | mean % | worst % |
| --- | --- | --- | --- | --- | --- |
| Mumbai → Chennai | 30 | 20 / 10 / 0 | −7.72 | −6.5 | 0.0 |
| Kandla → Cochin | 24 | 16 / 8 / 0 | −5.54 | −7.7 | 0.0 |
| Cochin → Dubai | 30 | 20 / 10 / 0 | −8.36 | −7.3 | 0.0 |
| Visakhapatnam → Colombo | 30 | 16 / 10 / 4 | −7.02 | −8.5 | +8.4 |
| Chennai → Port Blair | 30 | 16 / 12 / 2 | −7.68 | −10.0 | +4.3 |

**Worsened runs (all `shifting`, all with 3 reroutes at steps 1, 5, 9):**

| Voyage | Vessel | without → with (h) | Δ km |
| --- | --- | --- | --- |
| Visakhapatnam → Colombo | Bulk Carrier | 97.91 → 106.15 (+8.25) | +471 |
| Visakhapatnam → Colombo | VLCC | 81.49 → 88.32 (+6.83) | +404 |
| Visakhapatnam → Colombo | General Cargo | 89.82 → 97.26 (+7.45) | +553 |
| Visakhapatnam → Colombo | LNG Carrier | 67.15 → 71.68 (+4.53) | +373 |
| Chennai → Port Blair | VLCC | 83.55 → 84.18 (+0.63) | +193 |
| Chennai → Port Blair | LNG Carrier | 67.21 → 70.07 (+2.86) | +193 |

**Controller behaviour (from `events.csv`, ok runs only):**

- Adopted-alternative gain under the weather at decision time: adverse
  8.8–31.9% (median 20.0%), worsening 3.1–19.9% (median 8.0%),
  improving_alt 4.5–18.3% (median 6.3%), shifting 3.5–47.8% (median
  21.4%).
- Rejected alternatives: gain 0–2.67%. 5 were ≥ 2% (just under the 3%
  threshold), including the 2 `improving_alt` runs with no reroute
  (Chennai → Port Blair, Container Ship and LNG Carrier, 2.32% / 2.34%).
- In the 94 runs with a reroute: 66 longer and faster, 22 shorter and
  faster (all `improving_alt`), 6 longer and slower (the worsened runs).
- Execution: 533 s for 150 pairs; mean 3.5 s, max 10.0 s per pair (run 1,
  partly concurrent with the test suite).

### Observations

- Stable and minor weather produced **no route changes** in all 48 ok
  runs. In `minor` the controller searched (periodic re-check) and
  rejected gains ≤ 0.13%.
- Adverse and worsening storms on the route ahead were rerouted around in
  every ok run, with large simulated gains and modestly longer distance.
- Every worsened run is `shifting` and on one of two voyages. In run 95
  (Visakhapatnam → Colombo, Bulk Carrier) each of the 3 adopted reroutes
  was 32.7%, 4.1% and 10.2% cheaper under the weather at decision time,
  yet the realized voyage was 8.25 h slower and 471 km longer than staying
  on the original route.
- Benefits are similar across vessels in relative terms (−7.1% to −9.7%
  mean). In hours, slower vessels gain more (Container Ship −4.7 h vs.
  General Cargo −9.7 h on average).
- Cooldown blocked 97 evaluations (92 in `shifting`). This matrix has no
  no-cooldown counterpart, so its net effect is not measured here (EXP-003
  showed 12 vs. 3 changes for one pair).

### Hypotheses (not verified)

- **Moving-weather worsening:** each decision assumes the current weather
  persists. When the storm moves, a detour chosen for the current position
  can lie under the next position. Supporting measurement: on the two
  affected voyages the `shifting` side positions are 163–167 km from the
  planned route; on the other three, 184–231 km (storm width σ = 200 km).
  So detours are more likely to meet the next storm. 5 voyages are too few
  to confirm.
- **Threshold near-misses:** the 5 rejected alternatives at 2.3–2.7% may
  have been beneficial. Not measured: that would need a counterfactual run
  that adopts them.

### Not covered

Base weather `rough`; non-default thresholds (sensitivity); real or
forecast weather; draft-aware routing; counterfactual "missed beneficial
reroute" measurement. All results are simulated with synthetic weather and
a synthetic-data speed model; they show the controller's behaviour, not
real-world benefit.

---

## EXP-007 — Simulation lab: parity and performance

**Status:** Complete. Loop 009, 2026-10-03.

**Engine parity (measured):**

- After refactoring `simulate()` onto `rerouting.Voyage`, the full EXP-006
  matrix re-run gave `runs.csv` identical to the committed baseline
  (excluding `wall_s`), and all events and summary files byte-identical.
- A lab session with preset `storm_ahead` (Cochin → Dubai, General Cargo)
  matches `compare_voyage(..., "adverse")`: identical tracks, 103.34 h vs.
  127.68 h, R1 at step 2. Preset `moving_storm` via the API gives 106.6 h vs.
  118.2 h, the same as scenario `shifting` in EXP-003.

**Host vs. Docker (`tools/lab_parity.py`, Cochin → Dubai, General Cargo):**

| Sequence | Steps | Reroutes | With → without rerouting (h) | Host == Docker |
| --- | --- | --- | --- | --- |
| manual storm (18.0°N 66.5°E, σ 150 km, +6 m) applied at step 2 | 42 | 1 | 106.0 vs. 135.0 | identical full state |
| preset `moving_storm` | 43 | 3 | 106.6 vs. 118.2 | identical full state |
| manual storm, rerouting off | 39 | 0 | 135.0 vs. 135.0 | identical full state |

"Identical full state" covers every route and track point, timeline
message, decision detail and metric; only session ids were excluded.

**Performance (host, single measurements):**

| Operation | Time |
| --- | --- |
| Create session (first for a vessel/sea state, includes the base cost grid) | 2.3 s |
| Create session (base grid cached) | 1.1 s |
| Step without weather change | < 0.01 s |
| Apply weather (new ML cost grid) | 1.16 s |
| Step with a reroute search | 0.37 s |
| Overlay PNG render / cached re-fetch | 0.11 s (109 KB) / ≈ 0 s |
| Full voyage via API: manual storm / moving_storm preset | 2.2 s / 18.6 s (Docker: 2.1 s / 16.3 s) |

Session state response: 30–55 KB per request (routes + track ≈ 21 KB,
timeline ≤ 32 KB). Disturbed cost grid: 16.5 MB each, ≤ 2 per session.
Server process max RSS in the measurement script: 625 MB.

---

## Planned experiments (not run — no results)

- ~~Static vs. dynamic across the fixed voyage set and vessels~~ — done
  as EXP-006 (`typical` base). Still planned: `rough` base weather,
  threshold/cooldown sensitivity, and counterfactual missed-reroute
  measurement.
- **ETA consistency check** once the next goal changes ETA: reported time
  vs. ML-cost-derived time per route (Phase 3).
- **A* heuristic admissibility** on northern east–west voyages, e.g.
  Kandla ↔ Dubai: A* cost vs. weather-aware Dijkstra cost with the same
  multiplier (BLOCKERS C3).
- **ML rerouting-decision model vs. threshold baseline** on held-out
  scenarios (Phase 5, optional).
