# Running Nautilus in Docker

Status: **TASK-001 validated** (see
`docs/loop-engineering/TASKS.md` / `EXPERIMENTS.md` EXP-001). This is a
**development** image — source + full dependency set — not yet the
minimal production/distribution image described in
`docs/Source_Of_Truth.md` (that split is a later decision). It is **not**
yet published anywhere (no Docker Hub push, no remote-server deployment —
that's TASK-002/003/004).

## What this gives you

- A reproducible Python 3.12 environment with every pinned dependency
  from `requirements.txt`, built the same way every time.
- No need to install Python, NetCDF/HDF5 libraries, or any of the
  scientific-Python stack on the host — only Docker itself.
- The existing evaluation workflow (`python -m src.evaluate`,
  `python run_all.py`) runs **fully offline** — no raw datasets, no
  internet access required — using the processed data already committed
  to the repo under `data/processed/`.

## Build

```bash
docker build -t nautilus-dev .
```

Build time: roughly 50–85s on a clean cache (dependency install is the
only slow layer; verified with both a cached and a `--no-cache` from-
scratch build — see EXP-001). Final image: ~1.3 GB.

## Run the existing evaluation (the main validation target)

```bash
docker run --rm nautilus-dev python -m src.evaluate
# or, the documented full pipeline:
docker run --rm nautilus-dev python run_all.py
```

Both were verified to run with **no network access at all**
(`docker run --rm --network none nautilus-dev ...`) and to produce
output numerically identical to the host-committed
`data/processed/evaluation.csv` (distance, ETA, expanded-cell counts,
min-coast distance, and wave-exposure columns match exactly; only the
wall-clock `*_sec` runtime columns differ, as expected on different
hardware).

## Configuration and secrets

Nautilus reads its configuration (Google Maps API key, Flask port/host)
from environment variables, optionally populated from a local `.env`
file via `python-dotenv` (see `config.py`). Nothing is hardcoded in
source, and `.env` is never part of the Docker build context (see
`.dockerignore`) so a real key can never end up baked into an image.

```bash
cp .env.example .env   # then edit .env and fill in your real key
```

`.env` is gitignored - it stays local to your machine. See
`.env.example` for every variable and what it does.

## Run the web UIs

Flask (Google Maps UI + JSON API; API endpoints and all routing features
work without a key, only the map tiles need one):

```bash
docker run --rm -p 8000:8000 --env-file .env nautilus-dev python server.py
# or, without a .env file:
docker run --rm -p 8000:8000 -e GOOGLE_MAPS_API_KEY=your-key nautilus-dev python server.py
```

Streamlit (no API key needed):

```bash
docker run --rm -p 8501:8501 nautilus-dev \
    streamlit run app.py --server.address=0.0.0.0 --server.headless=true
```

Or, using the included `docker-compose.yml`:

```bash
docker compose run --rm nautilus python -m src.evaluate
docker compose up nautilus-flask        # http://localhost:8000
docker compose up nautilus-streamlit    # http://localhost:8501
```

`docker-compose.yml`'s `nautilus` service bind-mounts the repo into
`/app` for live code editing during development; the plain `docker run`
commands above do not (they use exactly what was baked into the image at
build time). It also declares `env_file: [{path: .env, required: false}]`,
so if you have a local `.env` it's picked up automatically - no
`--env-file` flag needed with `docker compose`.

## What was actually verified (not assumed)

All of the below were run against a real Docker Desktop engine during
TASK-001, including one full `--no-cache` rebuild from zero cached
layers to rule out "worked by cache luck":

- [x] `docker build` succeeds, including from a completely clean build
      cache.
- [x] All 16 pinned dependencies import successfully inside the
      container with `--network none` (no internet access at all).
- [x] `python -m src.evaluate` and `python run_all.py` both complete
      successfully offline and reproduce the committed
      `data/processed/evaluation.csv` exactly, aside from wall-clock
      timing columns.
- [x] `python server.py` is reachable from the host via `-p 8000:8000`
      and both `/api/meta` and `POST /api/route` return correct JSON.
- [x] `streamlit run app.py --server.address=0.0.0.0` is reachable via
      `-p 8501:8501` (`/_stcore/health` returns `200`).
- [x] `docker compose run --rm nautilus python -m src.evaluate` works
      end-to-end through the compose file, not just plain `docker run`.
- [x] No raw `.nc` files and no host Python environment are required at
      any point in the above.

## Known, investigated limitations

### scikit-learn version skew on the shipped ML model (pre-existing, not caused by containerization)

`data/processed/speed_model.joblib` was pickled with **scikit-learn
1.8.0**. The pinned `requirements.txt` (matching the host `.venv` this
image was derived from) installs **scikit-learn 1.9.0**. Loading the
model prints:

```text
InconsistentVersionWarning: Trying to unpickle estimator ... from
version 1.8.0 when using version 1.9.0. This might lead to breaking
code or invalid results.
```

This is **not** something Docker introduced — the same skew exists in
the host `.venv` the pins were captured from (confirmed: host `.venv`
also has scikit-learn 1.9.0). It predates this task. It was investigated
by diffing the container's generated `evaluation.csv` against the
host-committed baseline byte-for-byte on every non-timing column: the
results are identical, so the skew has **not** changed model behavior
today. It is flagged, not fixed, here — fixing it means either retraining
the model under 1.9.0 or pinning scikit-learn back to 1.8.0, and both are
routing/ML changes out of scope for a containerization task. Recorded as
an open item in `docs/loop-engineering/BLOCKERS.md` for Phase 2.

### ETA calculation (pre-existing, unrelated to this task)

Already documented in `docs/loop-engineering/PROJECT_STATE.md` before
this task started: `src/routing.py` computes ETA from distance at a
constant speed rather than the accumulated weather-aware cost. Verified
unchanged by this task (routing logic was not touched). Still open for
Phase 2.

### Production/offline-distribution image not yet built

This image includes development dependencies and the full source tree.
A minimal, distribution-focused image (Source of Truth §30, Phase 7
offline packaging) is intentionally not attempted here — it's a
different, later goal.

### Docker Hub / remote server

Not in scope for TASK-001. See TASK-002/003/004 in
`docs/loop-engineering/TASKS.md`.

## Files added/changed

| File | What / why |
| --- | --- |
| `Dockerfile` | Builds the dev image described above. |
| `.dockerignore` | Keeps raw datasets, `.git`, `.venv`, and any local `.env` out of the build context (`.env.example` is explicitly un-excluded since it has no secret). |
| `docker-compose.yml` | Convenience wrapper for local dev (bind-mounted source, port mapping, optional `.env` loading). Not required - everything it does can be done with plain `docker` commands above. |
| `requirements.txt` | Pinned to the exact versions verified working on the host `.venv`, plus `python-dotenv` for loading `.env`. |
| `config.py` | Single configuration module. Loads `.env` via `python-dotenv` (if installed) and reads `GOOGLE_MAPS_API_KEY` / `PORT` / `HOST` from the environment, same as every other setting in the file. |
| `.env` / `.env.example` | `.env` is your real local config (gitignored, never committed, never part of the Docker build context). `.env.example` documents every variable with safe placeholders and is safe to commit. |
| `server.py` | Reads `C.GOOGLE_MAPS_API_KEY`/`C.PORT`/`C.HOST` from `config.py` instead of the removed `web_config.py`; logs a non-fatal startup warning (never the key value) when no Maps key is configured. |

## Secret management

Nautilus has exactly one genuine secret: the Google Maps JavaScript API
key, used only by `server.py`'s web UI. It is loaded from the
environment (`config.py`, optionally via a local `.env` - see above) and
is never hardcoded in source, never baked into a Docker image layer, and
`.env` is gitignored so it's never committed.

The legacy `web_config.py` file (which previously held this value, with
an empty-string default in git) has been removed; `config.py` is now the
single configuration module for the whole application, app config
included.

**Frontend exposure note:** a Google Maps **JavaScript** API key is sent
to and used by the browser (it's injected into `web/index.html` and
visible in page source/devtools to anyone who loads the page) - that is
normal for this type of key and is not a leak by itself. What actually
keeps it safe to use client-side is restricting it in [Google Cloud
Console](https://console.cloud.google.com/google/maps-apis) to the HTTP
referrers (and/or the specific Maps JavaScript API) you actually serve
this app from, not keeping it out of `.env`/the browser.

**Historical finding (resolved):** during the earlier Docker
containerization task, a real-looking key was found as a local,
uncommitted default in `web_config.py`. It was confirmed via `git
diff`/`git log`/`git show origin/main` to never have been committed or
pushed anywhere (see `docs/loop-engineering/BLOCKERS.md` Q7 for the
original investigation). As part of this configuration-centralization
work, that local value was migrated into `.env` (not printed or
re-committed anywhere) and `web_config.py` was deleted. If that key is a
real, live key and has ever been copied/synced/shared outside this
machine, rotating it in Google Cloud Console is still a decision for
you, not something this change made or assumed.
