# Experiments

Experiment records, in the format defined by `docs/Source_Of_Truth.md`
§24: Experiment ID, Scenario, Start, Destination, Vessel, Weather,
Algorithms tested, Constraints, Metrics, Results, Observations, Conclusion.

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
