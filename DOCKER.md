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

## Run the web UIs

Flask (Google Maps UI + JSON API; API endpoints work without a key, the
map tiles need one):

```bash
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
build time).

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

## Files added/changed for this task

| File | What / why |
| --- | --- |
| `Dockerfile` | New. Builds the dev image described above. |
| `.dockerignore` | New. Keeps raw datasets, `.git`, `.venv`, and the developer's local `web_config.py` (which may hold a real API key - see below) out of the build context. |
| `docker-compose.yml` | New. Convenience wrapper for local dev (bind-mounted source, port mapping). Not required to satisfy TASK-001. |
| `requirements.txt` | Pinned to the exact versions already verified working on the host `.venv` (previously unpinned - see `docs/loop-engineering/BLOCKERS.md` Q1). No package was added, removed, or version-upgraded beyond what was already installed. |
| `web_config.py` | **Not modified on the host.** Excluded from the Docker build context; the image generates its own safe, secret-free version at build time (empty-default `GOOGLE_MAPS_API_KEY`, env-configurable `HOST`/`PORT`). See "Security note" below. |
| `server.py` | One-line, env-driven change: `app.run(host=...)` now reads `WC.HOST` (default `"127.0.0.1"`, unchanged for bare-metal runs) instead of hardcoding `"127.0.0.1"`. The Docker image sets `HOST=0.0.0.0` so the Flask dev server is reachable from outside its container via `-p`. Without this, `docker run -p 8000:8000` silently could not reach the server at all (verified before and after: curl to `/api/meta` returned nothing before the fix, correct JSON after). |

## Security note: local `web_config.py`

While inspecting the repository for this task, the on-disk (uncommitted,
unstaged) `web_config.py` was found to contain what appears to be a real
Google Maps API key as its fallback default value. This was checked
against git history and the remote:

- `git diff` shows it as a **local, uncommitted** change only.
- `git log --follow -- web_config.py` and `git show origin/main:web_config.py`
  confirm the key is **not** in any commit, on this branch, `main`, or
  `origin/main` — it has not been pushed anywhere.

Nothing in this task modified that file or its contents. To make sure it
is never baked into an image (which would make it shareable the moment
this image is pushed anywhere), it was added to `.dockerignore` and the
Dockerfile now generates its own safe, empty-default copy at build time.
If you run `docker compose` (which bind-mounts the whole repo into the
container for live editing), the container will see your actual local
`web_config.py` at runtime, same as running `python server.py` directly
on the host — that is expected and is no different from the non-Docker
workflow. If this key is real and has ever been copied/synced/shared
anywhere outside this machine, it should be rotated in the Google Cloud
Console; that decision belongs to you, not this task.
