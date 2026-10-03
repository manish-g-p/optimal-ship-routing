# Validation

What was verified, how, and with what result. Newest records first. Each
record states whether checks were **run in that loop** or are **reported
from an earlier loop**. A goal is not complete merely because code was
written or a command ran once without error.

Standard checks for routing/rerouting changes:

```bash
python -m unittest discover -s tests -v          # 31 tests (Loop 006), ~60 s
python -m src.rerouting                          # scenario table (EXP-003)
python -m src.evaluate                           # then diff evaluation.csv vs. the committed
                                                 # file excluding trad_sec/prop_sec; restore it
docker build -f docker/Dockerfile -t nautilus-dev .
docker run --rm --network none nautilus-dev python -m unittest discover -s tests
```

---

## Definition of done — rerouting / routing work (current)

- [ ] Existing tests pass (`tests/`), run in this loop.
- [ ] New behavior has deterministic tests, including failure/invalid cases.
- [ ] Initial routes unchanged: `test_evaluation_voyages_unchanged` passes
      and `src.evaluate` output matches the committed CSV (non-timing
      columns), unless a change is intended and recorded.
- [ ] Route comparisons use one cost model (Decision 006).
- [ ] Routes are navigable, 8-connected, start at the vessel/origin and
      end at the destination.
- [ ] Offline/Docker still works when dependencies or entry points change.
- [ ] Results recorded in `EXPERIMENTS.md`; docs updated per
      `README.md` → Maintenance convention.

## Validation slot — next goal (ETA / cost consistency, ML integration)

Not started. Record here: the checks run, their actual outcomes, and the
before/after `time_hours` vs. cost-derived time on the fixed voyages.

---

## Loop 006 — rerouting in the Flask UI (checks run in this loop)

- [x] `python -m unittest discover -s tests -v` (host): **Ran 31 tests in
      60.3 s — OK** (8 routing, 15 rerouting, 8 new API tests in
      `test_server.py`). A first full run (61.6 s, 31 OK) happened before
      the non-finite-value check and the `peak_change` refinement; the
      60.3 s run is on the final code.
- [x] `python -m src.rerouting` after moving the CLI onto
      `compare_voyage`: scenario table identical to EXP-003.
- [x] API checks in `test_server.py`: `/api/route` output unchanged
      (2953.6 / 2954.9 km, same keys); `/api/simulate` success, stable (no
      events, dynamic = static), reroute (adopted at step 2, track position
      = event position = start of final route), config applied, injected
      failed search (`failed` event, route kept), 12 invalid-input cases
      → HTTP 400.
- [x] Headless Chromium (Playwright's cached build; NSS libraries
      unpacked into the scratchpad with `apt-get download`, nothing
      installed system-wide) against `python server.py` on port 8000 with
      the real Maps key. The script drove the UI: simulation mode,
      `adverse` run, cards/verdict/events rendered, slider step 2 put the
      vessel exactly on the reroute position, last step "arrived";
      `shifting` with cooldown 6 → 3 reroutes; negative min-gain → error
      toast; switching back to route planning cleared the map, and
      **Find optimal route** rendered the usual Dijkstra/A* cards.
      Screenshots reviewed. Console: only a pre-existing favicon 404, the
      deliberate 400, and Google's `Marker` deprecation notice (C9). The
      run was repeated after the final CSS/`peak_change` changes, with the
      same results.
- [x] Docker: image rebuilt from the working tree; `--network none` test
      run **Ran 31 tests in 68.3 s — OK**; container started with
      `-p 18000:8000`, and `POST /api/simulate` (General Cargo, adverse)
      returned 103.3 h vs 127.7 h, 1 reroute; `POST /api/route` returned
      2953.6 / 2954.9 km.
- [x] `node --check web/app.js`: syntax OK.

## Loop 005 — documentation synchronization (checks run in this loop)

At commit `e8f68d1`, before editing any documentation:

- [x] `python -m unittest discover -s tests -v` (host `.venv`): **Ran 23
      tests in 42.3 s — OK** (8 in `test_routing`, 15 in
      `test_rerouting`).
- [x] `python -m src.rerouting` (host): scenario table identical to
      EXP-003.
- [x] Offline Docker: `docker build -f docker/Dockerfile -t nautilus-dev .`,
      then `docker run --rm --network none nautilus-dev python -m unittest
      discover -s tests` → **Ran 23 tests in 50.1 s — OK**, and
      `... python -m src.rerouting` → identical scenario table. Built from
      the working tree, where only documentation differed from `e8f68d1`.
      This closes the gap noted for Loop 004 below.
- [x] scikit-learn pickle warning still present (C5); `networkx` still
      unimported (C7); `docs/*.pdf`/`.pptx` tracked in git (C8).
- [x] No application code, tests, configuration or dependencies changed
      (`git status` shows only `.md` files modified).

## Loop 004 — weather-driven dynamic rerouting (reported from Loop 004)

- [x] `python -m unittest discover -s tests -v`: 23 tests OK (~46 s),
      after the final code change. During development, 3 failures were
      test-design issues (a wave threshold the calm Gulf never reached;
      storms placed on the initial route that missed the rerouted path)
      and were fixed in the tests.
- [x] `python -m src.rerouting`: results as in EXP-003.
- [x] `python -m src.evaluate`: identical to committed `evaluation.csv`
      excluding timing columns (CSV restored afterwards).
- [x] Docker image rebuilt and run with `--network none`: 23 tests OK, same
      scenario results. Run **before** a final behavior-neutral refactor
      of `RerouteController._done`; re-run at HEAD in Loop 005 (above).

## Loop 003 — current-position rerouting (reported from Loop 003)

- [x] `python -m unittest discover -s tests -v`: **8 tests OK** (~15 s).
- [x] Same tests against the original `src/routing.py`
      (`git show HEAD:src/routing.py`): 13 failures, 14 errors. The
      invalid-position tests failed, and the cost tests errored because
      `cost`/`path_cost` did not exist. The initial-route regression test
      passed on both versions.
- [x] `python -m src.evaluate`: identical to committed `evaluation.csv`
      excluding timing columns (CSV restored afterwards).
- [x] Flask `POST /api/route` (test client, Mumbai → Chennai, rough,
      General Cargo): HTTP 200, Dijkstra 2953.6 km, A* 2954.9 km
      (unchanged).

---

## Historical — definitions of done under the previous Source of Truth

The checklists below were adapted from the **previous** Source of Truth
(§40–42) in Loops 000–001. They are kept as history. "Remote validation"
and "Offline deployment" refer to goals now deferred (`TASKS.md`).

### Definition of done — Routing algorithm work (historical)

```text
Implementation
+ Correctness validation
+ Comparison against baseline
+ Relevant metrics
+ Scenario testing
+ Documentation
```

Superseded by "rerouting / routing work (current)" above.

### Definition of done — Deployment work (applies to TASK-001)

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

### Definition of done — Offline deployment work (old Phase 7, deferred)

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

### Validation performed for Loop 001 (TASK-001)

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

### Validation performed for Loop 000 (initialization)

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
