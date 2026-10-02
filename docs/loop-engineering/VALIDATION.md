# Validation

Definition-of-done checklists, adapted from `docs/Source_Of_Truth.md` §42.
A task is not complete merely because code was written or a command ran
once without error.

---

## General principle

A completed loop has: Change + Validation + Measurements (where
applicable) + Analysis + Decision + Updated project state (Source of
Truth §40). "It runs" is necessary but not sufficient.

---

## Definition of done — Routing algorithm work

```text
Implementation
+ Correctness validation
+ Comparison against baseline
+ Relevant metrics
+ Scenario testing
+ Documentation
```

Not yet applicable this loop — no routing algorithm work was done.

## Definition of done — Deployment work (applies to TASK-001)

```text
Build
+ Run
+ Reproducibility
+ Remote validation
+ Failure testing
```

Checklist for TASK-001 — all verified against a real Docker engine,
2026-10-01 (Loop 001). Evidence: `DOCKER.md`, `EXPERIMENTS.md` EXP-001.

- [x] Docker image builds from a clean checkout with no manual
      intervention. (Verified, including a full `--no-cache` rebuild
      after pruning the build cache — not just a cached re-build.)
- [x] Container starts and the existing evaluation entry point runs to
      completion. (`python -m src.evaluate` and `python run_all.py`,
      both with `--network none`.)
- [x] Rebuilding the image from scratch on the same machine produces the
      same successful result (reproducibility, not just "worked once").
      (Diffed container output against the host-committed baseline after
      both the cached build and the `--no-cache` rebuild — identical
      both times, aside from wall-clock timing columns.)
- [x] No host-level Python environment or system dependency is required
      beyond Docker itself. (All pinned deps import under `--network
      none` on plain `python:3.12-slim`; no `apt` packages were added.)
- [x] Failure modes are checked, not just the happy path. Tested: a
      container with `data/processed/` deliberately emptied fails with a
      clear `FileNotFoundError` naming the missing file
      (`bathymetry.npz`) rather than silently producing wrong output —
      i.e. the existing code's own error handling, unchanged and
      verified under containerization. Raw `.nc`-file absence was not
      separately tested as a distinct failure mode since `.dockerignore`
      guarantees they are never in the image in the first place (not a
      runtime failure mode to trigger).
- [x] Remote-server validation is explicitly **not** part of TASK-001's
      done criteria — that is TASK-004, once TASK-002/003 exist. Not
      attempted here, consistent with that scoping.

## Definition of done — Offline deployment work (future, Phase 7)

```text
Package
+ Install
+ Disconnect internet
+ Run
+ Route
+ Compare
+ Verify functionality
```

Not applicable yet — recorded here only so Phase 7 work starts from the
same definition of done, rather than inventing one later.

---

## Validation performed for Loop 001 (TASK-001)

Unlike Loop 000, this loop produced real, executable changes, so
validation means actual builds and runs against a live Docker engine, not
a consistency check:

- [x] Real `docker build`, `docker run`, and `docker compose` commands
      were executed against a genuine Docker Desktop engine (not
      simulated/assumed) — see `EXPERIMENTS.md` EXP-001 for the exact
      commands and every result.
- [x] A full `--no-cache` rebuild from zero cached build layers was
      performed specifically to rule out "it only worked because of
      cached state."
- [x] Container output was diffed byte-for-byte against the pre-existing
      host-committed baseline (`data/processed/evaluation.csv`), twice
      (cached build and `--no-cache` rebuild), rather than just checking
      for a zero exit code.
- [x] The `HOST` fix was verified both ways — confirmed broken
      (`curl` returned nothing) before the change, confirmed working
      (correct JSON from two endpoints) after.
- [x] A failure mode (missing processed data) was deliberately triggered
      to confirm the container fails loudly and correctly rather than
      silently misbehaving.
- [x] Every change that touched tracked files (`requirements.txt`,
      `server.py`) is a minimal, explained, goal-essential diff — not a
      broader refactor. `git diff` was reviewed for unintended changes
      before finishing (and one piece of test residue —
      `data/processed/evaluation.csv` regenerated with different
      wall-clock timing by a bind-mounted compose test run — was found
      and reverted rather than left in).
- [x] The two non-Docker findings (scikit-learn version skew, local API
      key) were investigated enough to state their actual impact (none,
      confirmed by diff; not committed, confirmed by `git log`/`git
      show`) rather than left as vague flags.

---

## Validation performed for Loop 000 (initialization)

Since this loop is documentation-only, validation means a consistency
check rather than a functional test:

- [x] Every claim in `PROJECT_STATE.md` about "implemented" functionality
      was checked against the actual source file, not assumed from the
      README or Source of Truth alone.
- [x] The ETA claim in Source of Truth §25–26 was checked against
      `src/routing.py` directly rather than taken at face value; the
      discrepancy is recorded rather than silently repeated as fact.
- [x] No document in `docs/loop-engineering/` states or implies that
      RL/PPO is an active implementation priority (see `CHANGE_LOG.md`
      for the explicit check).
- [x] Exactly one task (TASK-001) is marked `READY`.
- [x] No source code, UI, dependencies, or existing routing
      implementation were modified.
