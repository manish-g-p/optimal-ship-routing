# Blockers

Open blockers and unresolved questions. A "blocker" here means something
that prevents a task from being completed or validated — not every open
question is a blocker.

---

## Active blockers

None. TASK-002 (current READY task — Docker Hub image workflow) is not
blocked technically; it is simply not started yet because the loop that
completed TASK-001 was explicitly scoped to stop short of Docker Hub
publishing and remote-server configuration.

---

## Open questions (not blocking, but need an answer during relevant work)

### Q1 — Unpinned dependency versions — RESOLVED (Loop 001)

`requirements.txt` now pins all 16 direct dependencies to the versions
captured from the host `.venv` and verified working inside the Docker
image (see `DOCKER.md`, EXP-001 in `EXPERIMENTS.md`).

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

### Q3 — Container base-image system dependencies — RESOLVED (Loop 001)

Verified: `netCDF4`, `xarray`, `scipy`, `scikit-learn`, and every other
pinned dependency install and import cleanly on a plain
`python:3.12-slim` base image, with no extra `apt` packages. Confirmed
with `--network none` at both build-cached and full `--no-cache` rebuild.

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
become active; it was not needed for TASK-001 and is not needed for
TASK-002 (Docker Hub publishing doesn't require knowing the pull target).

### Q6 — scikit-learn version skew in the shipped ML model artifact (new, Loop 001)

`data/processed/speed_model.joblib` was pickled with scikit-learn 1.8.0;
the host `.venv` and the now-pinned `requirements.txt` both have 1.9.0.
Loading the model prints an `InconsistentVersionWarning`. Investigated in
Loop 001 (EXP-001): container output matched the host-committed baseline
byte-for-byte on every non-timing column, so behavior is unaffected
today. This is pre-existing (same skew exists on the host, outside
Docker) and not a containerization problem, so it was not fixed as part
of TASK-001 — fixing it means either retraining the model under 1.9.0 or
pinning scikit-learn to 1.8.0, both of which are ML/dependency decisions
for whoever picks up Phase 2 routing-foundation work, not a Docker task.

### Q7 — Real-looking Google Maps API key found locally in `web_config.py` (new, Loop 001) — needs a human decision

While inspecting the repo for TASK-001, the on-disk `web_config.py`
(uncommitted, unstaged) was found to default `GOOGLE_MAPS_API_KEY` to
what looks like a real key rather than the empty string its own
docstring describes. Checked and confirmed:

- `git diff` — local, uncommitted change only.
- `git log --follow -- web_config.py` and
  `git show origin/main:web_config.py` — the key is in **no commit**, on
  this branch, `main`, or `origin/main`. It has never been pushed.

This task did **not** modify the file (it's the developer's own local
config, not something this task should silently alter) and did **not**
include it in the Docker build context (added to `.dockerignore`; the
image generates its own safe, empty-default version at build time — see
`DOCKER.md`). This is flagged, not resolved, because the right action —
whether to rotate the key, whether it's actually a live/billable key,
whether it's been shared anywhere outside this machine — is a judgment
call only the developer can make. No further action was taken here.
