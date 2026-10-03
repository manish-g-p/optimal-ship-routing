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

## Planned experiments (not run — no results)

- **Static vs. dynamic across the fixed voyage set** (`evaluate.VOYAGES`)
  and several vessel profiles, including `rough` base weather (Phase 4).
  Should measure missed beneficial and unnecessary reroutes (Source of
  Truth §11.2) and threshold sensitivity.
- **ETA consistency check** once the next goal changes ETA: reported time
  vs. ML-cost-derived time per route (Phase 3).
- **A* heuristic admissibility** on northern east–west voyages, e.g.
  Kandla ↔ Dubai: A* cost vs. weather-aware Dijkstra cost with the same
  multiplier (BLOCKERS C3).
- **ML rerouting-decision model vs. threshold baseline** on held-out
  scenarios (Phase 5, optional).
