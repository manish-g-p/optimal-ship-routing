# Project State

**Last updated:** 2026-10-01 (Loop 002 — secret management, branch
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

### Implemented and working (added by Loop 001 — TASK-001)

- **Docker development environment.** `Dockerfile` (python:3.12-slim base,
  pinned dependencies), `.dockerignore`, and an optional `docker-compose.yml`
  for bind-mounted local dev. Full details, exact commands, and what was
  verified vs. assumed are in `DOCKER.md` at the repo root — not duplicated
  here. (Loop 001 originally had the Dockerfile generate a secret-free
  `web_config.py` stand-in at build time; **superseded by Loop 002** below —
  `web_config.py` no longer exists at all, so there's nothing to generate.)
- **Pinned dependencies.** `requirements.txt` now pins all direct
  dependencies to the exact versions already verified working on the host
  `.venv` (resolves the "Unpinned dependency versions" unknown previously
  listed below). No package was added, removed, or upgraded beyond what
  Loop 002 added (`python-dotenv`, see below).
- Verified, with real `docker build`/`docker run`/`docker compose` against
  a live Docker engine (including multiple full `--no-cache` rebuilds from
  zero cached layers, across both loops): the image builds reproducibly,
  all dependencies import with `--network none`, and `python -m
  src.evaluate` / `python run_all.py` run fully offline and reproduce the
  committed `data/processed/evaluation.csv` exactly except for wall-clock
  timing columns.
- Fixed `server.py`'s Flask binding to be env-configurable (default
  unchanged at `"127.0.0.1"`) instead of a hardcoded `"127.0.0.1"`, so the
  Flask UI is reachable from outside its container via `docker run -p`
  (verified broken before, working after). The Docker image sets
  `HOST=0.0.0.0`; bare-metal runs are unaffected. (Originally read via the
  now-removed `WC.HOST`; reads `C.HOST` from `config.py` as of Loop 002.)

### Implemented and working (added by Loop 002 — secret management)

- **Single configuration module.** `config.py` is now the only
  configuration module in the application. It loads a local `.env` (via
  `python-dotenv`, pinned `python-dotenv==1.2.4`) if one exists, then reads
  `GOOGLE_MAPS_API_KEY`, `PORT`, and `HOST` from the environment — exactly
  the settings `web_config.py` used to hold, plus every routing/data
  setting already there. `web_config.py` has been deleted
  (`git rm -f`) and no longer exists.
- **No hardcoded secrets remain in source.** A repo-wide search (secret-
  pattern keywords, long opaque-string scan, AWS-key patterns, DB
  connection-string patterns) found exactly one genuine secret in the
  whole repository: the Google Maps API key. It is the only one that
  existed, and it is now sourced from the environment, never hardcoded.
  See `DOCKER.md` → "Secret management" for the full write-up and
  `BLOCKERS.md` Q7 for how the pre-existing local key value was handled.
- **`.env` / `.env.example`.** `.env` holds real local values (gitignored,
  never committed, excluded from the Docker build context).
  `.env.example` documents every variable with safe placeholders and is
  committed. Deliberately contains only `GOOGLE_MAPS_API_KEY` — `PORT` and
  `HOST` are ordinary deployment config, not secrets, and were kept out of
  the template after a real bug was found and fixed during this loop (see
  below).
- **Missing-key handling.** `server.py` logs one clear, non-fatal
  console warning at startup when `GOOGLE_MAPS_API_KEY` is unset
  (`"GOOGLE_MAPS_API_KEY is not set - the map will not load..."`), never
  the key value itself. The app still starts and every non-map feature
  (JSON API, routing, Streamlit) works with no key configured — verified,
  not assumed.
- **Docker compatibility verified**, including a bug found and fixed in
  this loop: an earlier draft of `.env`/`.env.example` included `PORT`
  and `HOST` alongside the real secret. Loading that `.env` via `docker
  run --env-file` silently overrode the Dockerfile's `ENV HOST=0.0.0.0`
  back to `127.0.0.1`, breaking container reachability again (the exact
  problem Loop 001 had fixed). Caught by actually testing the
  `--env-file` path, not just reading the diff. Fixed by removing
  `PORT`/`HOST` from the `.env` template (they're not secrets and don't
  belong there) and, as a second safety net, pinning `HOST=0.0.0.0`
  explicitly in `docker-compose.yml`'s `nautilus-flask` service so it
  wins over `env_file` even if someone re-adds `HOST` to their own `.env`.

### Planned (not yet started)

- Docker Hub image build/publish workflow; remote-server pull/run
  (TASK-002/003/004 — explicitly deferred, see `TASKS.md`).
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

- ~~**Dependency versions.**~~ **Resolved by Loop 001.** `requirements.txt`
  is now pinned to the exact versions verified working both on the host
  `.venv` and inside the Docker image.
- ~~**Host-level system dependencies**~~ **Resolved by Loop 001.**
  Verified: `netCDF4`, `xarray`, `scipy`, `scikit-learn`, and every other
  pinned dependency install cleanly as manylinux wheels on a plain
  `python:3.12-slim` base image — no extra `apt` packages were needed.
- **New: scikit-learn version skew in the shipped ML model artifact.**
  `data/processed/speed_model.joblib` was pickled under scikit-learn
  1.8.0; the host `.venv` (and now the pinned `requirements.txt`) has
  1.9.0. Loading it prints an `InconsistentVersionWarning`. Investigated
  in Loop 001: container output was diffed byte-for-byte against the
  host-committed `evaluation.csv` and found identical on every column
  except wall-clock runtime, so this has not changed behavior today —
  but it is a real, pre-existing fragility (not introduced by
  containerization) worth resolving in Phase 2 by either retraining the
  model under 1.9.0 or pinning scikit-learn to 1.8.0. See `BLOCKERS.md`
  and `DOCKER.md`.
- ~~**A real-looking Google Maps API key as a local, uncommitted default
  in `web_config.py`.**~~ **Migrated by Loop 002**, not fully resolved.
  Found during Loop 001; confirmed never committed/pushed anywhere. Loop
  002 moved that local value into `.env` (gitignored) and deleted
  `web_config.py`. Still open: whether the key is real/live and whether
  it needs rotation is a human decision neither loop made. See
  `BLOCKERS.md` Q7 and `DOCKER.md` → "Secret management".
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
| `python server.py` | Flask + Google Maps UI on port 8000 (`GOOGLE_MAPS_API_KEY` optional — set via `.env` or the environment; everything but map tiles works without it). |
| `streamlit run app.py` | Streamlit UI on port 8501, no API key required. |

## Running in Docker

As of Loop 001, all entry points above also run inside the
`nautilus-dev` Docker image without any host Python installation — see
`DOCKER.md` for exact commands and what was verified. As of Loop 002,
pass `--env-file .env` (or `-e GOOGLE_MAPS_API_KEY=...`) to `docker run`
to supply the Maps key; `docker compose` picks up `.env` automatically.

## Dependencies (from `requirements.txt`, pinned as of Loop 001/002)

numpy, scipy, xarray, netCDF4, dask, networkx, scikit-learn, joblib,
pandas, matplotlib, requests, flask, flask-cors, python-dotenv,
streamlit, folium, streamlit-folium.

`networkx` is listed but was not seen imported by any file inspected so
far — unconfirmed whether it is actually used.

## Geographic / modeling configuration (`config.py`)

Region 0–27°N, 50–100°E · grid 0.05° · min depth 10 m · coast buffer 22 km ·
nominal ship speed 18 kn · wave-cost weights `W_WAVE_HEIGHT=0.6`,
`W_HEAD_SEAS=0.4`, `W_PERIOD=0.1` · `MAX_WEATHER_MULT=4.0`. These are
project modeling assumptions, not maritime regulations (Source of Truth §6).
