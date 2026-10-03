# Validation

What was verified, how, and with what result. Newest records first. Each
record states whether checks were **run in that loop** or are **reported
from an earlier loop**. A goal is not complete merely because code was
written or a command ran once without error.

Standard checks for routing/rerouting changes:

```bash
python -m unittest discover -s tests -v          # 75 tests (Loop 009), ~3.5 min
python -m src.rerouting                          # scenario table (EXP-003)
python -m src.evaluate_rerouting                 # 150-pair matrix, ~9 min (EXP-006); to check
                                                 # reproducibility, copy data/rerouting_eval/ first,
                                                 # re-run, compare all files (runs.csv excl. wall_s)
python -m src.evaluate                           # then diff evaluation.csv vs. the committed
                                                 # file excluding trad_sec/prop_sec; restore it
docker build -f docker/Dockerfile -t nautilus-dev .
docker run --rm --network none nautilus-dev python -m unittest discover -s tests
# web UI (server running on :8000, Maps key in .env):
CHROME=/path/to/chrome node tools/lab_e2e.mjs <outdir>         # 28 browser checks
python tools/lab_parity.py http://localhost:8000 host.json      # repeat against Docker, compare
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

## Validation slot — next goal (not yet chosen; see `TASKS.md`)

Not started. Record here the checks run and their actual outcomes. If the
change could affect routes or rerouting, re-run
`python -m src.evaluate_rerouting` and compare with the committed
`data/rerouting_eval/` (EXP-006 baseline), not only the unit tests.

---

## Loop 009 — interactive Simulation lab (checks run in this loop)

All on the working tree on top of `c307fe5`.

- [x] **Engine refactor non-regression:** `python -m src.rerouting` gave an
      identical scenario table. The full 150-pair evaluation re-run had
      `runs.csv` identical to the committed baseline excluding `wall_s`,
      and events and all summaries byte-identical. `test_rerouting.py`:
      16 OK.
- [x] **Host tests:** `python -m unittest discover -s tests` → **Ran 75 tests
      in 204.2 s — OK** (run concurrently with the Docker build). New
      `test_sim_session.py`: **20 OK**, covering:
      - lifecycle and batch-engine parity;
      - pending weather not seen by routing until applied;
      - a manual storm causing a real reroute, with the map route starting
        at the R1 position;
      - preset/manual merging and edited preset → manual;
      - base data untouched;
      - validation (NaN, inf, ranges, bools, strings, ids, count);
      - failed search keeps the route; failed weather build changes nothing;
      - store eviction/TTL;
      - API flow, invalid requests, busy 409, and a generic 500 without
        internals;
      - existing endpoints unchanged.
- [x] **Browser, host** (`tools/lab_e2e.mjs`, headless Chromium, real Maps
      key, `python server.py` on :8000): **28/28 PASS**. Covers route
      planning before and after; lab controls enabled/disabled correctly;
      start → auto-run, pause holds the step for 2 s, resume continues the
      same voyage; Step advances exactly one step on a double click and moves
      the vessel; no duplicate timeline entries; map click → pending storm
      (routing unaware); Apply now → overlay re-rendered (v=1); next step →
      backend R1 adopted (24.7–25.3% cheaper across runs; depends on where the vessel was when the storm was placed); R1 marker and the active route
      starting there; initial route and track kept; timeline detail opens;
      move → pending; discard; client-side and server-side (400) validation
      with state intact; two-click reset clears everything; preset
      `storm_ahead` runs to completion; no overlap of panels, control bar and
      legend at 1500×950 and 1280×800; no stale popup; leaving and
      re-entering the lab. HTTP errors: only `404 /favicon.ico`
      (pre-existing) and the deliberate 400. Console errors: none (apart
      from Google's `Marker` deprecation notice, a warning).
- [x] **Defects found by the browser runs and fixed before the final run:**
      - the overlay image held the session lock, so auto-run steps hit 409
        "busy" and stopped;
      - `toast()` timers hid newer messages early;
      - a fast double click on Step sent two requests (the server rejected
        the second with 409, but the user saw an error);
      - a stale info window survived reset or a new voyage;
      - the control bar covered the legend at 1280 px.

      Each was re-verified in the next run.
- [x] **Docker:** image rebuilt. `--network none` test suite: **Ran 75 tests
      in 218.5 s — OK**. Container server (`-p 8000:8000 --env-file .env`;
      `.env` confirmed *not* in the image): `tools/lab_e2e.mjs` **28/28
      PASS**, no unexpected HTTP errors, no console errors.
- [x] **Host vs. Docker parity:** `tools/lab_parity.py` sequences (manual
      storm, `moving_storm` preset, rerouting off): **identical full JSON
      states** (EXP-007).
- [x] Route-planning baseline unaffected: `test_evaluation_voyages_unchanged`
      and `/api/route` checks pass; `data/processed/` untouched.
- [ ] Not verified: browsers other than Chromium; viewports narrower than
      1280 px; the "Live" sea state in the lab (deliberately rejected);
      running the server with several workers (unsupported, see C13).

## Loop 008 — rerouting evaluation (checks run in this loop)

All on the working tree on top of `e7597a1`; thresholds and rerouting
code unchanged.

- [x] `python -m unittest discover -s tests` (host): **Ran 55 tests in
      139.4 s — OK** (41 existing + 14 new in `test_evaluate_rerouting.py`;
      run concurrently with evaluation run 1, so slower than usual). The
      new tests alone: **Ran 14 tests in 26.2 s — OK**. They cover:
      - full 150-combination coverage;
      - run statuses, including a real `draft_infeasible` case
        (VLCC, Kandla → Cochin);
      - relative-change edge cases (zero, negative, NaN, inf, None
        baselines);
      - outcome classification and paired-metric consistency;
      - matched initial conditions of the paired runs;
      - no reroute ⇒ identical voyages;
      - deterministic weather scenarios;
      - a failed run recorded and excluded from `ok`;
      - summaries matching the detail rows;
      - event rows tied to runs;
      - a repeated subset run identical except `wall_s`.
- [x] `python -m src.evaluate_rerouting`, run 1: **150 pairs in 533 s; 144
      `ok`, 6 `draft_infeasible`, 0 incomplete, 0 failed** (EXP-006).
- [x] Run 2 (same command, same code): 150 pairs in 494 s. Compared with
      run 1: `runs.csv` identical except `wall_s`; `events.csv`, all four
      `summary_*.csv` and `config.json` **byte-identical**.
- [x] The heatmap code was changed after the runs (labels, n, worsened
      count, title); the PNG was regenerated from run 2's `runs.csv`. This
      does not affect any CSV.
- [x] Route-planning baseline: `python -m src.evaluate` output identical
      to the committed `data/processed/evaluation.csv` except timing
      columns. The committed file was restored; `data/processed/` is
      unchanged in git.
- [x] Docker: image rebuilt; `--network none` **Ran 55 tests in 106.7 s —
      OK**. The full matrix in the container (`--network none`): **150
      pairs in 546 s, 144 ok / 6 draft_infeasible**. Its `runs.csv` (copied
      out with `docker cp`) is identical to the host's except `wall_s`, and
      `summary_overall.csv` is byte-identical.
- [x] Docs audit: every headline number in EXP-006 matched against
      `summary_overall.csv`; event statistics recomputed on ok runs only
      (the first draft had used all runs, now corrected); no broken links;
      all referenced identifiers exist.
- [ ] Not done: `rough` base weather, threshold sensitivity,
      counterfactual missed-reroute measurement (out of scope; `BLOCKERS.md`
      C12).

---

## Loop 007 — route cost / travel time consistency (checks run in this loop)

- [x] `python -m unittest discover -s tests -v` (host): **Ran 41 tests in
      78.9 s — OK**: 15 routing (7 new `TravelTimeTests`; hours baseline
      added to the evaluation-voyage test), 16 rerouting (1 new: decisions
      ignore the time model; hour checks added), 10 API (2 new: route time
      without ML cost, unknown vessel; `/api/route` hours and
      `time_basis` checked).
- [x] Independent check: per-segment RF predictions (`ml_model.predict_speed`,
      same speed bounds), not via the multiplier grid, agree with
      `Router.path_hours` within 1e-5 relative for Dijkstra and A* routes,
      all 5 vessels, and `typical`/`rough`/storm weather.
- [x] `python -m src.evaluate`: all non-time columns identical to the
      committed CSV (route selection unchanged). `trad_h`/`prop_h` changed
      as intended (EXP-005). The regenerated `evaluation.csv` is kept as the
      new baseline; its timing columns also changed (wall-clock).
- [x] `python -m src.rerouting`: scenario table identical to EXP-003.
- [x] Headless Chromium UI script (as in Loop 006): all flows pass.
      Route cards now read "est. hours (ML)" (Container Ship, Cochin →
      Dubai, `typical`: 71 h for both routes); simulation numbers unchanged.
      Console: only the known favicon 404 and the deliberate 400.
- [x] Streamlit: `streamlit.testing.v1.AppTest` ran `app.py` and clicked
      "Find route": no exceptions; metrics "Est. time (ML speed model)"
      71 h for both routes.
- [x] Docker: image rebuilt; `--network none` **Ran 41 tests in 81.6 s —
      OK**. `python -m src.evaluate` in the container: Mumbai → Chennai
      114 h / 114 h. Container `POST /api/route`: 2953.6 km / 114.5 h and
      2954.9 km / 114.4 h, `time_basis` `ml_speed`.
- [x] Before the change, the exploratory script showed the discrepancy
      (EXP-005). On the old code the new hours baseline and the
      independent-calculation test would fail (88.6 ≠ 114.4); I did not
      run them against the old code.

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
