# Project State

**Last updated:** 2026-10-01 (initialization loop, branch
`refactor/docker-containerization`)

This document is rebuilt/updated at the end of every loop. It describes what
is actually true of the repository right now — not what is planned, and not
what any other document claims. Where repository inspection and
`docs/Source_Of_Truth.md` disagree, that is flagged explicitly below rather
than silently resolved.

---

## Current project

Nautilus is a weather-aware marine routing and decision-support system for
waters around India (lat 0–27°N, lon 50–100°E, 0.05° grid ≈ 5.5 km/cell). It
combines GEBCO bathymetry, ERA5 wave data, a navigable-ocean grid, Dijkstra
and weather-aware A* search, and a machine-learning vessel-speed model. See
[`docs/Source_Of_Truth.md`](../Source_Of_Truth.md) for the full target
definition — multi-algorithm, scenario-based, evidence-driven comparison.

## Current primary goals

- Multiple routing algorithms (currently: 2 implemented)
- Scenario-based routing
- Quantitative algorithm comparison
- Evidence-based algorithm selection
- Dockerized remote development
- Offline-capable deployment

## Current repository state

### Implemented and working

- **Data pipeline** (`src/preprocess.py`): extracts the India region from
  raw GEBCO/ERA5 NetCDF files, downsamples to the configured grid, writes
  `bathymetry.npz`, `weather.npz`, `weather_grid.csv` to `data/processed/`.
- **Navigable grid** (`src/grid.py`): builds a navigable-water mask from
  bathymetry (min depth 10 m, coast buffer 22 km), connected-component
  analysis to keep the main ocean basin, KD-tree nearest-cell lookup.
  Cached as `data/processed/grid.npz`.
- **Weather layer** (`src/weather.py`): resamples wave fields (`swh`,
  `mwp`, `mwd`) onto the routing grid for `typical` and `rough` static
  scenarios; computes an explainable wave-cost multiplier.
- **ML speed model** (`src/ml_model.py`): a RandomForestRegressor trained
  on a **synthetic, physics-inspired** dataset (not real AIS/telemetry data)
  predicts attainable vessel speed given sea state and vessel. Used to
  build a per-cell, per-direction cost multiplier for weather-aware A*.
  Cached as `data/processed/speed_model.joblib`.
- **Routing engine** (`src/routing.py`): two algorithms exist —
  - `dijkstra`: shortest great-circle distance, 8-connected grid search.
  - `astar`: same search with an admissible equirectangular heuristic,
    weather/ML cost multiplier applied per edge.
  Both share one `Router` class and return a `RouteResult` dataclass
  (`algorithm`, `found`, `cells`, `latlon`, `distance_km`, `time_hours`,
  `max_wave_m`, `mean_wave_m`, `expanded`).
- **Vessel profiles** (`src/vessel.py`): 5 fixed vessel types with service
  speed, length, draft, wave sensitivity. Not all properties are consumed
  by routing today (e.g. length/draft do not currently affect the search).
- **Ports** (`src/ports.py`): ~20 fixed India + nearby-foreign ports.
- **Evaluation script** (`src/evaluate.py`): runs a hardcoded list of 5
  voyages through both algorithms under the `rough` scenario, computes
  route optimality, computational efficiency, safety compliance (min
  coast distance), and adaptability (wave exposure) metrics, prints a
  table, and writes `data/processed/evaluation.csv`. This file and its
  output **already exist and are committed** — it is the "existing
  five-voyage evaluation baseline" referenced throughout the Source of
  Truth (§24–25).
- **Two UIs**: a Flask app (`server.py` + `web/`) with a Google-Maps
  frontend and a JSON API (`/api/meta`, `/api/weather`,
  `/api/weather_image`, `/api/route`), and a Streamlit app (`app.py`)
  that needs no API key. Both call the same `src/` routing code.
- **Pipeline runner** (`run_all.py`): preprocess (if needed) → train ML
  model (if needed) → run `evaluate.run(scenario="rough", ...)`.
- **Processed data is committed to git.** Despite `.gitignore` listing
  `data/processed/`, the six files under `data/processed/` (including
  `evaluation.csv` and `speed_model.joblib`) are tracked in the repo
  (force-added). A fresh clone can run routing/evaluation **without**
  the two raw NetCDF files, which are correctly excluded by `.gitignore`
  (`*.nc`) and are present locally but not tracked (7.4 GB GEBCO, 4.1 GB
  ERA5 wave).

### Partially implemented

- **Common `RouteResult`.** A `RouteResult` dataclass already exists in
  `src/routing.py`, but it does not yet carry every field the Source of
  Truth's standard result calls for (§13) — e.g. no explicit `runtime`,
  `safety_validity`, `constraint_violations`, or `min_coast_clearance`
  fields on the object itself (min-coast is computed separately, in
  `evaluate.py`, by indexing a grid field with the route's cells).
- **ETA correctness.** `docs/Source_Of_Truth.md` §25–26 states that the
  ETA implementation was previously constant-speed, was identified as
  incorrect, and was **subsequently corrected to use the accumulated
  routing cost**. Repository inspection on this branch does not support
  that claim: `Router._finalize` in `src/routing.py` currently computes
  `time_hours = distance_km / (SHIP_SPEED_KN * 1.852)` — a constant-speed
  calculation identical in form for both Dijkstra and A*, independent of
  the weather/ML cost actually used to select the A* route. This is
  flagged as an **open discrepancy between the Source of Truth narrative
  and the actual code on this branch**, not asserted as fixed. See
  [`BLOCKERS.md`](BLOCKERS.md). No source code was changed to investigate
  or fix this during initialization, per task scope.
- **Safety validation.** Minimum coast-distance is computed and reported
  in `evaluate.py`, but there is no general constraint-checking/validity
  flag attached to a route result, and no scenario-defined constraint
  framework yet.

### Planned (not yet started)

- Docker development environment (Dockerfile, compose, dev workflow).
- Docker Hub image build/publish workflow; remote-server pull/run.
- Common routing-algorithm interface (`RoutingProblem` → `RoutingAlgorithm`
  → `RouteResult`) decoupled from the two existing hardcoded functions.
- Additional algorithms: Bidirectional Dijkstra, Bidirectional A*,
  weather-aware Dijkstra (a weather-aware algorithm that is *not*
  heuristic-guided — today only the heuristic-guided A* is weather-aware),
  risk-constrained/multi-objective routing.
- Scenario framework (reusable scenario definitions beyond the two
  hardcoded weather scenarios and the hardcoded voyage list in
  `evaluate.py`).
- Automated evaluation engine (scenario → run algorithms → metrics →
  constraints → feasibility → comparison → evidence), generalized beyond
  the current single hardcoded script.
- Evidence-based recommendation engine.
- Algorithm-comparison UI (current UI shows one route per request type;
  it does not yet expose multi-algorithm comparison or recommendation
  evidence).
- Offline packaging/distribution mechanism.

### Unknowns requiring investigation

- **Dependency versions.** `requirements.txt` lists package names with no
  version pins. The exact versions currently installed in `.venv`
  (Python 3.12.3) are not yet captured anywhere reproducible. This is
  directly relevant to TASK-001 (a Docker image needs pinned versions to
  be reproducible) and should be determined by inspecting `.venv`, not
  assumed.
- **Host-level system dependencies**, if any, that `netCDF4`/`xarray`/
  `scipy`/`scikit-learn` wheels might implicitly rely on (e.g. HDF5/NetCDF
  shared libraries) when installed in a minimal container base image —
  not yet verified.
- **No automated tests exist in the repository** (no `test_*.py`,
  `tests/`, or test runner configuration were found). "Validation" today
  means manually running `run_all.py` / `src/evaluate.py` and inspecting
  output. This has no bearing on the current direction (not an RL
  artifact) but is a real gap worth noting for Phase 2/3 work.
- **`tools/generate_demo_guide.py`** exists but was not inspected in
  detail; purpose inferred from filename (generates `docs/*Demo_Guide*`
  materials) and is not part of the routing/evaluation runtime path.
- **Deployment assumptions.** Nothing in the repo currently assumes a
  specific deployment target beyond "run locally with `.venv`"; there is
  no existing Docker, systemd, or cloud-deployment configuration to
  reconcile with the new containerization work.

## Entry points (as they exist today)

| Command | What it does |
| --- | --- |
| `python -m src.preprocess` | One-time: raw NetCDF → `data/processed/*.npz`, `*.csv` (requires the two raw `.nc` files locally; **not required** if `data/processed/` is already populated, which it is on this branch). |
| `python -m src.ml_model` | Trains/saves `speed_model.joblib`. |
| `python -m src.grid` | (Re)builds `grid.npz` from `bathymetry.npz`. |
| `python -m src.evaluate` | Runs the 5-voyage Dijkstra-vs-A* evaluation, writes `data/processed/evaluation.csv`. |
| `python run_all.py` | preprocess (if needed) → train model (if needed) → evaluate. |
| `python server.py` | Flask + Google Maps UI on port 8000 (needs `GOOGLE_MAPS_API_KEY`). |
| `streamlit run app.py` | Streamlit UI on port 8501, no API key required. |

## Dependencies (from `requirements.txt`, unpinned)

numpy, scipy, xarray, netCDF4, dask, networkx, scikit-learn, joblib,
pandas, matplotlib, requests, flask, flask-cors, streamlit, folium,
streamlit-folium.

`networkx` is listed but was not seen imported by any file inspected so
far — unconfirmed whether it is actually used.

## Geographic / modeling configuration (`config.py`)

Region 0–27°N, 50–100°E · grid 0.05° · min depth 10 m · coast buffer 22 km ·
nominal ship speed 18 kn · wave-cost weights `W_WAVE_HEIGHT=0.6`,
`W_HEAD_SEAS=0.4`, `W_PERIOD=0.1` · `MAX_WEATHER_MULT=4.0`. These are
project modeling assumptions, not maritime regulations (Source of Truth §6).
