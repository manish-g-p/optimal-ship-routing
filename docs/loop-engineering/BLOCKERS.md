# Blockers

Open blockers and unresolved questions. A "blocker" here means something
that prevents a task from being completed or validated — not every open
question is a blocker.

---

## Active blockers

None. TASK-001 (current READY task) is not blocked on anything — it can
begin with the information already gathered in `PROJECT_STATE.md`.

---

## Open questions (not blocking, but need an answer during relevant work)

### Q1 — Unpinned dependency versions

`requirements.txt` lists package names with no version pins, and the
exact versions currently resolved in the local `.venv` (Python 3.12.3)
have not been captured. This must be resolved as part of TASK-001 itself
(it is the task's first listed step: "inspect current runtime/dependencies"),
so it is not a separate blocker — just flagged so it isn't skipped.

### Q2 — ETA calculation discrepancy

`docs/Source_Of_Truth.md` §25–26 states the ETA implementation was
corrected to use the accumulated routing cost instead of a constant-speed
distance calculation. Repository inspection shows `src/routing.py` on
this branch still computes ETA as `distance_km / constant_speed` for both
Dijkstra and A*. This does not block TASK-001 (Docker containerization
does not require routing-logic changes), but it should be the first item
examined in Phase 2 ("Stabilize the Existing Routing System") rather than
assumed already resolved. No code was changed to investigate this further
during this initialization loop — investigation only, no fix attempted,
per task scope.

### Q3 — Container base-image system dependencies

`netCDF4`, `xarray`, `scipy`, and `scikit-learn` sometimes need system
libraries (e.g. HDF5) beyond what `pip install` provides on a minimal
base image. Not yet verified whether the chosen Docker base image will
need extra `apt` packages. To be determined during TASK-001, not
assumed in advance.

### Q4 — `networkx` usage

`networkx` is listed in `requirements.txt` but no import of it was found
during inspection of `src/*.py`, `server.py`, `app.py`, `run_all.py`.
Unconfirmed whether it is actually required. Not resolved in this loop
(no dependency changes were made, per task scope) — noted for whoever
next touches `requirements.txt`.

### Q5 — Deployment target specifics for the remote server

The remote server's OS, available Docker version, and resource limits
are not described in any repository document. TASK-003/TASK-004
(pull-and-run on the remote server) will need this information when they
become active; it is not needed for TASK-001 (local/container build and
validation only).
