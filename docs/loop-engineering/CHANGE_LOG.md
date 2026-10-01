# Change Log

Human-readable summary of what changed, loop by loop. Complements
`LOOP_LOG.md` (which records process/decisions) by summarizing concrete
file-level changes.

---

## 2026-10-01 — Loop 002: centralize and secure configuration/secrets

**Added:**

- `.env` — real local config (gitignored, never committed).
- `.env.example` — documents every variable (`GOOGLE_MAPS_API_KEY` only
  — see below for why `PORT`/`HOST` were deliberately left out) with a
  safe placeholder; committed.

**Removed:**

- `web_config.py` — deleted (`git rm -f`). Its one real setting
  (`GOOGLE_MAPS_API_KEY`) and its two ordinary settings (`PORT`, `HOST`)
  were merged into `config.py`.

**Changed:**

- `config.py` — now loads `.env` via `python-dotenv` (optional import,
  won't break routing/evaluation code if absent) and reads
  `GOOGLE_MAPS_API_KEY`/`PORT`/`HOST` from the environment.
- `server.py` — `import web_config as WC` removed; all `WC.*` replaced
  with `C.*`; added a non-fatal startup warning (never the key value)
  when no Maps key is configured.
- `requirements.txt` — added `python-dotenv==1.2.4`.
- `Dockerfile` — removed the now-obsolete step that generated a
  secret-free `web_config.py` stand-in (nothing to generate anymore).
- `.dockerignore` — excludes `.env`/`.env.*`, explicitly un-excludes
  `.env.example`.
- `docker-compose.yml` — loads `.env` via `env_file: [{path: .env,
  required: false}]`; `nautilus-flask` pins `HOST=0.0.0.0` explicitly
  (see bug note below).
- `DOCKER.md`, `README.md` — updated run instructions and references
  from `web_config.py`/`-e GOOGLE_MAPS_API_KEY=...` to `.env`/
  `--env-file .env`; added a "Secret management" section to `DOCKER.md`.

**Not changed:** routing logic, ML model/behavior, evaluation results,
UI behavior/markup, any dependency's functionality beyond adding one new
pinned package. `src/live_weather.py`'s Open-Meteo API needs no key and
was not touched.

**Bug found and fixed in this loop (not pre-existing):** the first draft
of `.env`/`.env.example` included `PORT`/`HOST` next to the real secret.
Loading that file via `docker run --env-file .env` silently overrode the
Dockerfile's `ENV HOST=0.0.0.0`, making the Flask UI unreachable from
outside its container again — the same class of bug Loop 001 had just
fixed. Caught by actually testing `--env-file`, not by inspection. Fixed
by removing `PORT`/`HOST` from the `.env` template (they are deployment
config, not secrets) and pinning `HOST=0.0.0.0` explicitly in the
`nautilus-flask` compose service as a second safety net.

**Security findings:** exactly one genuine secret in the whole
repository (Google Maps API key), found already flagged from Loop 001 as
a local-only, never-committed value in `web_config.py`. A repo-wide
search (keyword patterns, opaque-string scan, AWS-key patterns, DB
connection-string patterns) found nothing else. That value was migrated
into `.env` (never printed in full anywhere) rather than discarded, and
`web_config.py` was removed. Whether the key should be rotated is a
human decision, not made or assumed here — see
`docs/loop-engineering/BLOCKERS.md` Q7.

**Validated with:** real `docker build` (cached + `--no-cache`),
`docker run` with and without `--env-file .env`, `docker compose
config`/`run` (secret redacted before ever reaching visible output),
image-filesystem and `docker history` scans confirming the secret is
never baked into any image layer, and a byte-for-byte diff of
`data/processed/evaluation.csv` against the pre-change baseline
confirming routing/evaluation output is unchanged.

---

## 2026-10-01 — Loop 001: TASK-001, reproducible Docker development environment

**Added:**

- `Dockerfile` — `python:3.12-slim` dev image, pinned deps, generates a
  safe/secret-free `web_config.py` at build time, `HOST=0.0.0.0`.
- `.dockerignore` — excludes raw `.nc` files, `.git`, `.venv`, and the
  developer's local `web_config.py`.
- `docker-compose.yml` — convenience wrapper for local dev (bind-mounted
  source, port mapping); not required for TASK-001's completion.
- `DOCKER.md` — build/run instructions, full verification checklist,
  known limitations, security note on the local API-key finding.

**Changed:**

- `requirements.txt` — pinned all 16 direct dependencies to the versions
  already verified working on the host (previously unpinned). No
  package added, removed, or upgraded.
- `server.py` — `app.run(host=...)` now reads `WC.HOST` (env-overridable,
  default unchanged at `"127.0.0.1"`) instead of a hardcoded
  `"127.0.0.1"`. One line of application logic changed; justified below.

**Not changed:** routing logic (`src/routing.py`), any algorithm, the
web UI's HTML/JS/CSS, the ETA calculation, the ML model, or any
dependency's functionality beyond pinning its already-installed version.
The user's actual local `web_config.py` file was inspected but never
written to.

**Why the `server.py` change was in scope:** The task constraints said
"preserve existing behavior unless a change is essential to the goal."
Without this change, `docker run -p 8000:8000 ... python server.py`
would start successfully but be completely unreachable from outside its
own container (Flask bound only to the container's loopback interface) —
silently defeating the containerized-remote-development workflow the
Source of Truth describes. Verified broken before the change (`curl`
returned nothing) and working after (correct JSON from two live
endpoints). Default behavior for a bare-metal, non-Docker run is
unchanged.

**Validated with:** real `docker build`/`docker run`/`docker compose`
against a live Docker Desktop engine, including a full `--no-cache`
rebuild from zero cached layers. `python -m src.evaluate` and `python
run_all.py` produce output byte-for-byte identical to the pre-existing
`data/processed/evaluation.csv` (aside from wall-clock timing columns),
with `--network none` (no internet access at all). Full detail in
`DOCKER.md` and `docs/loop-engineering/EXPERIMENTS.md` (EXP-001).

**Found, documented, deliberately not fixed (out of scope for a
containerization task):**

- A scikit-learn 1.8.0-vs-1.9.0 pickle-version warning on the shipped
  `speed_model.joblib` (pre-existing on the host too; confirmed no
  effect on output). See `docs/loop-engineering/BLOCKERS.md` Q6.
- A real-looking Google Maps API key as a local, uncommitted default in
  `web_config.py` (confirmed not committed or pushed anywhere; excluded
  from the Docker build context rather than modified). See
  `docs/loop-engineering/BLOCKERS.md` Q7 and the "Security note" in
  `DOCKER.md`.

**Environment note:** validating this task required a working `docker`
CLI, which this sandbox did not have on `PATH` by default (no WSL
Docker-Desktop integration, no passwordless `sudo` for an `apt` install).
Resolved by downloading the official static `docker` client binary (no
root needed) and connecting it to the already-reachable Docker Desktop
engine socket this user account already has group access to — every
build/run in this loop is real, not simulated. One side effect: a
`docker builder prune -af` (run once, to force a true from-scratch
rebuild) cleared the shared engine's build cache for the user's other,
unrelated Docker images too — their actual tagged images were confirmed
unaffected (`docker images` before/after matched), only cached
intermediate layers were cleared.

---

## 2026-10-01 — Loop 000: Project initialization

**Added:**

- `docs/loop-engineering/README.md`
- `docs/loop-engineering/PROJECT_STATE.md`
- `docs/loop-engineering/TASKS.md`
- `docs/loop-engineering/DECISIONS.md`
- `docs/loop-engineering/EXPERIMENTS.md`
- `docs/loop-engineering/LOOP_LOG.md`
- `docs/loop-engineering/BLOCKERS.md`
- `docs/loop-engineering/VALIDATION.md`
- `docs/loop-engineering/CHANGE_LOG.md` (this file)

**Changed:** Nothing in application source, configuration, dependencies,
or UI. No Docker files were created. No routing algorithms were
implemented or modified.

**Documentation consistency check (Source of Truth §39 Phase 1
completion condition):**

- [x] `PROJECT_STATE.md` reflects the actual repository, distinguishing
      implemented / partial / planned / unknown functionality, and does
      not claim functionality exists where the code does not support it
      (e.g. the ETA-correction claim in the Source of Truth is explicitly
      flagged as unconfirmed/contradicted by the code, not repeated as
      fact).
- [x] `TASKS.md` roadmap mirrors the Source of Truth's phase order
      exactly (Phase 1 Reproducible Remote Environment → Phase 2 Routing
      Foundation → Phase 3 Algorithm Expansion → Phase 4 Scenario
      Framework → Phase 5 Evaluation/Evidence → Phase 6 Comparison UI →
      Phase 7 Offline Deployment).
- [x] Only Phase 1 has detailed tasks; later phases list goals/candidates
      only, per the Source of Truth's own instruction not to over-plan.
- [x] `DECISIONS.md` records only the three decisions required to
      establish the current direction, with no speculative architecture
      or scoring-formula decisions.
- [x] No file in `docs/loop-engineering/` references reinforcement
      learning, PPO, RL training, RL inference, or RL deployment as an
      active or planned priority. The only mention of RL anywhere in this
      directory is in `DECISIONS.md`, stating explicitly that RL is
      **not** part of the active roadmap — consistent with Source of
      Truth §43–44.
- [x] No migration plan from a previous RL-oriented direction was
      created; none exists in this repository state to migrate from on
      this branch.
- [x] TASK-001 is the single `READY` task, matches the Source of Truth's
      Phase 1 definition, and was **not** started during this loop.

**Verified by:** grep-style review of all nine new files for the strings
"RL", "PPO", "reinforcement", "reward", "policy" — only occurrences are
in `DECISIONS.md` explicitly excluding RL from scope.
