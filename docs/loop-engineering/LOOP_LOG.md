# Loop Log

Development-session history. Newest entry on top. File-level detail lives
in `CHANGE_LOG.md`, evidence in `VALIDATION.md` / `EXPERIMENTS.md`.

Loops 000–002 ran under the **previous** Source of Truth (branch
`refactor/docker-containerization`). Their "§" references and "next
task: TASK-002" are historical; see `README.md`.

---

## Loop 007 — Route cost, travel time and ETA consistency

**Date:** 2026-10-03
**Branch / commit:** `feature/dynamic-routing`, on top of `1fd131d`
(uncommitted when written)
**Task:** User-directed: make route cost, travel time and ETA consistent
(Source of Truth §10, Phase 3, Phase 1 ETA item).

**What was done:** Traced cost and time through `routing.py`,
`ml_model.py`, `rerouting.py`, `evaluate.py`, `server.py`, `app.py` and
`web/app.js`. Measured the discrepancy and the ML multiplier bounds
(EXP-005). Added a travel-time model to `Router` (`speed_kn`, `time_mult`,
`path_hours`, `time_basis`) separate from the cost model. Wired the
vessel's ML time model into evaluation, `/api/route`, Streamlit and the
simulation (`sailed_hours`; event hours for reporting only). Removed
`rerouting.cost_hours`. `/api/route` now rejects unknown vessels with 400
(the ML grid it now always builds would otherwise give a 500). Regenerated
`evaluation.csv`. Added tests. Updated the Source of Truth (§10.1 and
status), README, DOCKER.md and these records. Also fixed a stale Source of
Truth §15 bullet that still said rerouting was not in the UI (missed in
Loop 006).

**Validation:** `VALIDATION.md` → Loop 007.

**Decision:** Done (Decision 011). Route selection and rerouting policy
unchanged.

**Next:** Awaiting user confirmation. Proposed: multi-voyage
static-vs-dynamic evaluation (Phase 4 remainder).

---

## Loop 006 — Dynamic rerouting in the application interface

**Date:** 2026-10-03
**Branch / commit:** `feature/dynamic-routing`, on top of `095bd0b`
(uncommitted when written)
**Task:** User-directed: make the voyage simulation usable through the
existing interface (part of Source of Truth Phase 4).

**What was done:** Inspected `server.py`, `web/` and `app.py`. Chose
Flask only (Decision 010). Added `compare_voyage`, `config_from_dict`,
`cost_hours` and `VoyageResult.sailed_km` to `src/rerouting.py`, and moved
the CLI onto `compare_voyage`. Added `peak_change` to `src/weather_sim.py`.
Added `POST /api/simulate` plus a `simulation` key in `/api/meta`. Added a
mode switch, simulation controls and a simulation map/panel to `web/`.
Added `tests/test_server.py`. During validation: rejected non-finite
config values (JSON `NaN` would have disabled adoption silently); made
weather-change markers prefer the largest increase (otherwise `shifting`
showed some updates as "clearing"); capped the results panel above the
wave legend.

**Validation:** `VALIDATION.md` → Loop 006; measurements in EXP-004.

**Decision:** Goal done. Phase 4 is partly done (UI); the multi-voyage
static-vs-dynamic evaluation remains.

**Next:** Still awaiting user confirmation. Phase 3 (ETA/cost
consistency) is proposed; the Phase 4 remainder is the alternative.

---

## Loop 005 — Documentation synchronization

**Date:** 2026-10-03
**Branch / commit:** `feature/dynamic-routing` @ `e8f68d1` (changes uncommitted at time of writing)
**Task:** User-directed: bring the Source of Truth and all
loop-engineering records in line with the current direction and code.
Documentation only.

**What was done:**

1. Read the Source of Truth and every file in `docs/loop-engineering/`,
   plus `README.md` and `DOCKER.md`. Checked the code (`src/routing.py`,
   `src/rerouting.py`, `src/weather_sim.py`, `config.py`, tests) and git
   history.
2. Found that the brief's premise was out of date: it described
   weather-driven dynamic rerouting as the *next, unimplemented* goal,
   but it was already committed (`e8f68d1`, Loop 004) and passing tests.
   Documented it as implemented (with point-by-point evidence in
   `TASKS.md`) instead of planned. Recorded the roadmap's next phase
   (Phase 3, ETA/cost + ML integration) as **proposed**, pending user
   confirmation.
3. Re-ran tests and the scenario evaluation on the host and offline in
   Docker (`VALIDATION.md` → Loop 005). Re-checked old open questions
   (sklearn skew, `networkx`, tracked PDFs).
4. Rewrote `README.md` (navigation, reading order, maintenance
   convention), `PROJECT_STATE.md` and `TASKS.md` for the current state.
   Restructured `BLOCKERS.md`. Added decisions 004–009 to `DECISIONS.md`
   and marked 001 superseded. Added EXP-002/003 and planned experiments.
   Added Loop 003–005 records here and in `VALIDATION.md` /
   `CHANGE_LOG.md`. Updated the Source of Truth status line, roadmap
   status, §5 implemented capabilities and §14 maintenance pointer.
   Updated stale references in `DOCKER.md` and the feature list in root
   `README.md`.

**Validation:** see `VALIDATION.md` → Loop 005.

**Decision:** Documentation reflects `e8f68d1`. Next goal proposed, not
started.

**Next:** User to confirm the next goal (Phase 3 proposed; Phase 4 is the
alternative).

---

## Loop 004 — Weather-driven dynamic rerouting

**Date:** 2026-10-03 (committed as `e8f68d1`, "feat: weather driven
re-routing added and simulations passed")
**Branch:** `feature/dynamic-routing`
**Task:** User-directed: Source of Truth Phase 2 — simulated weather
updates, vessel progress, remaining-route evaluation, threshold-based
controller, scenario tests.

**What was done:** Added `src/weather_sim.py` (deterministic wave-height
perturbations, named scenarios), `src/rerouting.py` (controller, voyage
simulation, event log, console evaluation), `REROUTE_*` defaults in
`config.py`, `tests/test_rerouting.py` (15 tests, scenarios A–E), and a
README section. Updated Source of Truth §15. No change to
`src/routing.py`. During development: added a periodic re-check trigger
(an improving alternative was otherwise never noticed); fixed it
re-firing every step; recorded the search after adoption to avoid a
wasted re-search; widened the `improving_alt` storm so the scenario
exercises an adoption; replaced a Scenario D design whose storms missed
the rerouted path.

**Validation:** `VALIDATION.md` → Loop 004; results in EXP-003.

**Decision:** Phase 2 done at simulation level (Decisions 006–008). The
loop stopped without starting ML decision work, as instructed.

**Next (as stated then):** not assigned; limitations listed (now
`BLOCKERS.md` C1–C4).

---

## Loop 003 — Current-position rerouting

**Date:** 2026-10-03 (committed as `6fdfd91`, "fix: minor failures and
bugs in routing fixed", together with the user's Source of Truth rewrite,
which was already in the working tree when the loop started)
**Branch:** `feature/dynamic-routing`
**Task:** User-directed: Source of Truth Phase 1 — implement and validate
rerouting from an arbitrary valid intermediate position.

**What was done:** Inspected routing, grid, ports, evaluation, server and
ML code. Probed behavior (EXP-002): arbitrary starts already worked, but
the search cost was not exposed and invalid starts were silently
accepted. Added start/goal validation (`ValueError`), `RouteResult.cost`
and `Router.path_cost` to `src/routing.py`. Created `tests/` (stdlib
`unittest`, 8 tests). Added a tests section to the README.

**Validation:** `VALIDATION.md` → Loop 003.

**Decision:** Phase 1 done except ETA/cost consistency (Decision 005).
Loop-engineering documents were **not** updated in this loop. That gap
was closed in Loop 005.

**Next (as stated then):** stop; await the next milestone.

---

## Note — 2026-10-02 Docker file reorganization (no loop entry)

Commit `79f130b` moved the Docker files into `docker/` and updated
`DOCKER.md`, `CHANGE_LOG.md` and `PROJECT_STATE.md`. No `LOOP_LOG.md` entry
was written at the time. Whether it was run as a numbered loop is
unknown. Details: `CHANGE_LOG.md` (2026-10-02).

---

## Loop 002 — Centralize and secure Nautilus configuration and secrets

**Date:** 2026-10-01
**Branch:** `refactor/docker-containerization`
**Task:** User-directed (not a pre-existing TASKS.md item): remove
hardcoded secrets, centralize config in `.env`, eliminate redundant
`web_config.py` references, keep Docker working.

**What was done:**

1. Re-read `docs/Source_Of_Truth.md`, `PROJECT_STATE.md`, `DOCKER.md`;
   confirmed no `AGENTS.md`. Inspected `config.py`, the (now-removed)
   `web_config.py`, every `WC.*`/`web_config` reference (`server.py`,
   `Dockerfile`, `docker-compose.yml`, `DOCKER.md`, `README.md`,
   `tools/generate_demo_guide.py`).
2. Ran a repo-wide search for additional secrets: keyword patterns
   (api_key/secret/password/token/credential/etc.), long opaque-string
   scan, AWS-key patterns, DB connection-string patterns, existing
   `.env`/credential files. Found exactly one genuine secret in the
   entire repository: the Google Maps API key already known from Loop
   001 (as a local, uncommitted default in `web_config.py`). Confirmed
   `src/live_weather.py`'s Open-Meteo API needs no key.
3. Migrated that local key value into a new `.env` (gitignored, never
   printed in full in any output/doc/log) and `.env.example` (safe
   placeholder, committed). Added `python-dotenv==1.2.4` to
   `requirements.txt` (version captured from a real `pip install` on the
   host, consistent with the existing pinning convention).
4. Merged the settings `web_config.py` used to hold
   (`GOOGLE_MAPS_API_KEY`, `PORT`, `HOST`) into `config.py`, which now
   calls `load_dotenv()` (guarded by `try/except ImportError` so routing/
   evaluation code doesn't break if `python-dotenv` is somehow absent).
5. Updated `server.py`: removed `import web_config as WC`; replaced all
   `WC.*` with `C.*`; added one non-fatal startup warning (never the key
   value) when `GOOGLE_MAPS_API_KEY` is unset.
6. Deleted `web_config.py` with `git rm -f` (force needed — it still
   carried the uncommitted real-key value, which had already been
   migrated to `.env` first, so nothing was lost).
7. Updated `Dockerfile` (removed the now-obsolete generated-`web_config.py`
   step), `.dockerignore` (excludes `.env`/`.env.*`, un-excludes
   `.env.example`), `docker-compose.yml`, `DOCKER.md`, and `README.md` to
   remove `web_config.py` references and document the `.env` workflow.
8. **Found and fixed a real bug introduced by my own first draft:**
   `.env`/`.env.example` initially included `PORT`/`HOST` alongside the
   real secret. Testing `docker run --env-file .env` (not just reading
   the diff) showed this silently overrode the Dockerfile's
   `ENV HOST=0.0.0.0` back to `127.0.0.1`, reintroducing the exact
   container-unreachability bug Loop 001 had fixed. Fixed by removing
   `PORT`/`HOST` from the `.env` template (correctly recognizing them as
   ordinary deployment config, not secrets — matching the task's
   instruction not to indiscriminately move ordinary config into `.env`)
   and adding an explicit `HOST=0.0.0.0` in `docker-compose.yml`'s
   `nautilus-flask` service as a second safety net.
9. Validated with real `docker build`/`run`/`compose` commands throughout
   (see `DOCKER.md` and the Validation section of the final report for
   this loop) — not just inspection. Every check that could have printed
   the secret was redacted or value-length-checked instead (e.g.
   `docker compose config` piped through `sed` to redact before it ever
   reached visible output).
10. Updated `PROJECT_STATE.md`, `BLOCKERS.md` (Q7 marked migrated, not
    fully resolved — rotation is still a human decision), and this log.

**Validation:** Real `docker build` (cached and `--no-cache`), `docker
run` with and without `--env-file .env`, `docker compose config`/`run`,
image-filesystem and `docker history` scans confirming the secret is
never baked into any layer, and a byte-for-byte diff of
`data/processed/evaluation.csv` against the pre-change baseline
confirming routing/evaluation behavior is unchanged. Full detail in the
final report delivered for this task (not duplicated here — see
`CHANGE_LOG.md` for the file-level summary).

**Analysis:** The codebase had exactly one real secret, and it is now
correctly sourced from the environment with no hardcoded fallback
anywhere. The `web_config.py` → `config.py` consolidation removed a
redundant configuration module without touching routing, ML, or UI
behavior. The `PORT`/`HOST`-in-`.env` bug is a useful reminder that
"centralize config in `.env`" and "these are secrets" are not the same
claim — conflating them broke Docker reachability, caught only by
actually running the container, not by reasoning about the diff.

**Decision:** Done. No further `.env`/secret-management work is pending
from this loop. Whether the discovered key should be rotated remains the
developer's decision (see `BLOCKERS.md` Q7).

**Next task:** None assigned by this loop — it was a standalone
configuration/security cleanup, not a `TASKS.md` roadmap item. TASK-002
(Docker Hub image workflow) remains the roadmap's `READY` task.

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
