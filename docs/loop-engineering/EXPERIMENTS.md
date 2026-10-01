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

**Status:** Not yet run. Defined now so TASK-001 has a concrete
validation target; to be executed as part of TASK-001.

**Scenario:** Infrastructure validation, not a routing scenario. Confirms
the existing application runs unchanged inside a Docker container.

**Purpose:** Establish that the Docker development environment built in
TASK-001 reproduces the current host (`.venv`) runtime behavior.

**What it must verify:**

- Docker image builds successfully from a clean checkout of this branch.
- A container starts from that image without error.
- All `requirements.txt` dependencies resolve and import inside the
  container (no missing system libraries for `netCDF4`/`xarray`/`scipy`/
  `scikit-learn`, etc. — currently unverified, see `PROJECT_STATE.md`
  "Unknowns").
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

**Commands:** Not recorded yet. Per task instructions, commands are to be
determined from the actual Dockerfile/compose setup once TASK-001
produces it, not invented in advance. This experiment definition will be
filled in with the real `docker build` / `docker run` commands as part of
executing TASK-001.

**Results / Observations / Conclusion:** Pending — to be filled in when
TASK-001 is executed. Do not begin TASK-001 as part of this
initialization loop.
