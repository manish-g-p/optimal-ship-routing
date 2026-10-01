# Loop Log

Chronological record of each development loop. Newest entry on top.

---

## Loop 001 — TASK-001: Establish reproducible Docker development environment

**Date:** 2026-10-01
**Branch:** `refactor/docker-containerization`
**Task:** TASK-001 (the single `READY` task left by Loop 000).

**Context:** Goal was to make Nautilus build and run reproducibly in
Docker without host-installed dependencies, working autonomously through
inspect → implement → validate → analyze → decide, stopping only at a
genuine blocker or full completion. Constraints: preserve existing
routing behavior/architecture unless a change is essential to the goal;
no new algorithms/features; no Docker Hub push; no remote-server
configuration; no unnecessary dependencies; validate with real evidence.

**What was done:**

1. Re-read `docs/Source_Of_Truth.md` and `docs/loop-engineering/PROJECT_STATE.md`;
   confirmed no `AGENTS.md` exists.
2. Captured exact dependency versions from the host `.venv` (`pip
   freeze`) and pinned all 16 direct dependencies in `requirements.txt`
   (resolves BLOCKERS.md Q1).
3. Wrote `Dockerfile` (`python:3.12-slim`, pinned deps,
   `.dockerignore`), `docker-compose.yml` (turned out useful for the
   documented dev workflow).
4. **Environment obstacle:** this sandbox had no working `docker` CLI
   (Docker Desktop's WSL integration wasn't enabled for this distro; a
   second, independent Docker Engine install via `apt` wasn't possible —
   no passwordless `sudo`). Resolved without installing anything
   system-wide: downloaded the official static `docker` CLI binary and
   pointed it at the Docker Desktop engine's already-reachable bind-mount
   socket (the user's own account is already in the `docker` group).
   This made every subsequent build/run a real Docker operation, not a
   simulation.
5. Built the image, then validated with real commands: dependency
   imports under `--network none`; `python -m src.evaluate` and `python
   run_all.py` offline, diffed byte-for-byte against the host-committed
   `data/processed/evaluation.csv` (identical except wall-clock timing);
   a full `--no-cache` rebuild from zero cached layers, re-diffed
   (identical again — true reproducibility, not cache luck); a
   deliberately broken failure mode (missing processed data) to confirm
   clean error behavior.
6. **Found and fixed one goal-essential gap:** `server.py` hardcoded
   `host="127.0.0.1"`, making the Flask UI unreachable from outside its
   container via `-p` — undermining the Source of Truth's "remote
   Docker development" workflow. Fixed with a minimal, env-driven,
   backward-compatible change (`WC.HOST`, default unchanged); verified
   broken before and working after via `curl` to two live endpoints.
   Also smoke-tested and verified the Streamlit UI reachable the same
   way (no source change needed there — `--server.address` is already a
   CLI flag).
7. **Found two pre-existing, non-Docker issues**, investigated and
   documented but not fixed (out of scope — would be ML/dependency or
   personal-config changes, not containerization):
   - `data/processed/speed_model.joblib` was pickled under scikit-learn
     1.8.0 vs. the now-pinned 1.9.0 (`InconsistentVersionWarning`);
     confirmed via diff that behavior is unaffected today.
   - A real-looking Google Maps API key present as a local, uncommitted
     default in `web_config.py`; confirmed via `git diff`/`git log`/
     `git show origin/main:web_config.py` that it is not committed or
     pushed anywhere. Not modified; excluded from the Docker build
     context instead so it can never be baked into an image.
8. Wrote `DOCKER.md` (build/run instructions, full verification
   checklist, known limitations, security note). Updated
   `PROJECT_STATE.md`, `TASKS.md` (TASK-001 → `DONE`, TASK-002 →
   `READY`), `EXPERIMENTS.md` (EXP-001 filled in with real results),
   `BLOCKERS.md` (Q1/Q3 resolved, Q6/Q7 added), `VALIDATION.md`
   (TASK-001 checklist ticked with evidence).
9. Reviewed `git status`/`git diff` before finishing; found and reverted
   one piece of test residue (`data/processed/evaluation.csv` had been
   regenerated with different wall-clock timing by a bind-mounted
   `docker compose` test run — reverted to the committed baseline since
   the diff was timing noise, not a meaningful change).

**Validation:** See `docs/loop-engineering/VALIDATION.md` ("Loop 001 —
TASK-001" section) and `EXPERIMENTS.md` EXP-001 for the full evidence
trail — every checklist item backed by an actual command and output, not
assumed.

**Analysis:** TASK-001's five scope items are all complete and verified.
The image is reproducible (same result from a cached build and a
from-scratch rebuild), fully offline-capable for the evaluation workflow
(no raw datasets, no network), and self-sufficient (no host system
dependency beyond Docker). One real UX-breaking gap (Flask
unreachability) was found and fixed within scope; two unrelated
pre-existing issues were found, investigated, and documented without
being "fixed" to avoid scope creep into ML/dependency/personal-config
territory that TASK-001 didn't call for.

**Decision:** TASK-001 is `DONE`. TASK-002 (Docker Hub image workflow)
is promoted to the single `READY` task per the roadmap, but is
**explicitly not started** — this loop's instructions excluded Docker
Hub publishing and remote-server configuration.

**Next task:** TASK-002 — Docker Hub image workflow (not started; awaits
a future loop or explicit authorization).

---

## Loop 000 — Project initialization (clean start)

**Date:** 2026-10-01
**Branch:** `refactor/docker-containerization`
**Task:** None (pre-task initialization) — establish
`docs/loop-engineering/` from scratch for the current project direction.

**Context:** This branch was created from `main` before any previous
loop-engineering documentation existed. No prior loop documents, task
documents, project-state documents, experiment logs, or planning
documents were present. This loop creates that structure for the first
time, using only `README.md` and `docs/Source_Of_Truth.md` as references.
No RL-era documentation was recovered, migrated, or reconstructed.

**What was done:**

1. Read `README.md` and `docs/Source_Of_Truth.md` in full.
2. Inspected the repository: `config.py`, `src/*.py` (routing, grid,
   weather, ml_model, evaluate, vessel, ports, preprocess), `server.py`,
   `app.py`, `run_all.py`, `web_config.py`, `requirements.txt`,
   `.gitignore`, `data/processed/` contents, `docs/` contents, git
   history and branches. No source code was modified.
3. Created `docs/loop-engineering/` with: `README.md`, `PROJECT_STATE.md`,
   `TASKS.md`, `DECISIONS.md`, `EXPERIMENTS.md`, `LOOP_LOG.md` (this
   file), `BLOCKERS.md`, `VALIDATION.md`, `CHANGE_LOG.md`.
4. Confirmed via repository inspection that the ETA-correction claim in
   `docs/Source_Of_Truth.md` §25–26 is not reflected in this branch's
   `src/routing.py` (still constant-speed ETA). Recorded as an open
   discrepancy rather than silently assumed true or silently fixed.
5. Confirmed `data/processed/*` files (including `evaluation.csv` and
   `speed_model.joblib`) are git-tracked on this branch despite
   `.gitignore` listing `data/processed/` — relevant to TASK-001 since it
   means the raw 7.4 GB/4.1 GB NetCDF files are not needed to run
   evaluation in a fresh container.
6. Defined TASK-001 (Docker development environment) as the single READY
   task and EXP-001 as its validation experiment, per `TASKS.md` and
   `EXPERIMENTS.md`.

**Validation:** No functional change was made to validate (documentation
only). Checked that no document in `docs/loop-engineering/` contradicts
`docs/Source_Of_Truth.md` and that none references RL/PPO as an active
priority (see `CHANGE_LOG.md` for the explicit consistency check).

**Decision:** Proceed to TASK-001 in a future loop. This loop stops
after initialization, per task instructions — TASK-001 was not started.

**Next task:** TASK-001 — Establish reproducible Docker development
environment.
