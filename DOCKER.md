# Running Nautilus in Docker

This is a **development** image — source + full dependency set. A
minimal production/distribution image is not on the current roadmap. It
is **not** published anywhere (no Docker Hub push, no remote-server
deployment).

**All commands below are run from the project root** (the directory this
file is in), even though the Docker files themselves live in `docker/`.
Don't `cd` into `docker/` first.

```text
OptimalShipRouting/            <- run every command from here
├── DOCKER.md                  <- this file
├── .dockerignore               <- stays here, NOT in docker/ (see why below)
├── .env / .env.example
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
└── ... (application source, data/processed/, etc.)
```

## What this gives you

- A reproducible Python 3.12 environment with every pinned dependency
  from `requirements.txt`, built the same way every time.
- No need to install Python, NetCDF/HDF5 libraries, or any of the
  scientific-Python stack on the host — only Docker itself.
- The existing evaluation workflow (`python -m src.evaluate`,
  `python run_all.py`) runs **fully offline** — no raw datasets, no
  internet access required — using the processed data already committed
  to the repo under `data/processed/`.

## Configuration and secrets

Nautilus reads its configuration (Google Maps API key, Flask port/host)
from environment variables, optionally populated from a local `.env`
file via `python-dotenv` (see `config.py`). Nothing is hardcoded in
source, and `.env` is never part of the Docker build context (see
`.dockerignore`) so a real key can never end up baked into an image.

```bash
cp .env.example .env   # then edit .env and fill in your real key
```

`.env` is gitignored — it stays local to your machine. See
`.env.example` for every variable and what it does. Both options below
show how to load it.

---

## Option A — Manual Docker commands

**Build** the image (`-f` points at the relocated Dockerfile; the build
context is still the project root — required so `COPY . .` inside the
Dockerfile sees the whole application):

```bash
docker build -f docker/Dockerfile -t nautilus-dev .
```

**Run the existing evaluation workflow:**

```bash
docker run --rm nautilus-dev python -m src.evaluate
# or, the documented full pipeline:
docker run --rm nautilus-dev python run_all.py
```

Both run fully offline — add `--network none` yourself to confirm no
network access is used at all.

**Run the tests and the dynamic-rerouting scenarios** (verified offline;
see `docs/loop-engineering/VALIDATION.md`). The voyage simulation is also in
the Flask UI (`python server.py`, "Voyage simulation" mode):

```bash
docker run --rm --network none nautilus-dev python -m unittest discover -s tests
docker run --rm --network none nautilus-dev python -m src.rerouting
```

**Run the Flask UI** (Google Maps key optional — map tiles won't render
without one, everything else works):

```bash
docker run --rm -p 8000:8000 --env-file .env nautilus-dev python server.py
# or, without a .env file:
docker run --rm -p 8000:8000 -e GOOGLE_MAPS_API_KEY=your-key nautilus-dev python server.py
```

Open http://localhost:8000.

**Run the Streamlit UI** (no API key needed):

```bash
docker run --rm -p 8501:8501 nautilus-dev \
    streamlit run app.py --server.address=0.0.0.0 --server.headless=true
```

Open http://localhost:8501.

**Stop and remove a container** started without `--rm` (the Flask/
Streamlit examples above use `--rm`, so this is only needed if you ran
one with `-d`/without `--rm`, or want to stop a running one by name):

```bash
docker ps                     # find the container ID/name
docker stop <container>       # graceful stop
docker rm <container>         # remove it (skip if you used --rm)
```

---

## Option B — Docker Compose

The compose file lives at `docker/docker-compose.yml`, but its paths
(build context, the bind-mounted volume, `.env`) are all written
relative to the **project root**, not to `docker/`. That only works if
you pass `--project-directory .` — always include it:

```bash
docker compose -f docker/docker-compose.yml --project-directory . <command>
```

That prefix is the same for every command below — define it once as a
shell alias or variable if you'll be running these often, e.g.:

```bash
alias nc='docker compose -f docker/docker-compose.yml --project-directory .'
```

(The examples below spell it out in full so they're copy-paste correct
on their own.)

**Start the application** (Flask, in the background):

```bash
docker compose -f docker/docker-compose.yml --project-directory . up -d nautilus-flask
```

Or Streamlit:

```bash
docker compose -f docker/docker-compose.yml --project-directory . up -d nautilus-streamlit
```

**Run the evaluation workflow:**

```bash
docker compose -f docker/docker-compose.yml --project-directory . run --rm nautilus python -m src.evaluate
```

**View logs:**

```bash
docker compose -f docker/docker-compose.yml --project-directory . logs -f nautilus-flask
```

**Stop the services:**

```bash
docker compose -f docker/docker-compose.yml --project-directory . down
```

### How environment variables differ between the two options

| | Option A (`docker run`) | Option B (`docker compose`) |
| --- | --- | --- |
| Google Maps key | Pass `--env-file .env` or `-e GOOGLE_MAPS_API_KEY=...` explicitly | Loaded automatically — the compose file declares `env_file: [{path: .env, required: false}]`, resolved against the project root via `--project-directory` |
| Flask bind address | The image's `ENV HOST=0.0.0.0` (baked in at build time) | Set explicitly in `docker-compose.yml`'s `nautilus-flask` service, so it can't be silently overridden by `.env` (see the comment in that file — an earlier draft of `.env` once broke this, see `docs/loop-engineering/PROJECT_STATE.md`) |
| Source code | Baked into the image at build time — rebuild (`docker build ...`) to pick up changes | Bind-mounted (`.:/app`) — edits on the host are reflected immediately, no rebuild needed |

Compose is not required — everything it does can be done with the plain
`docker` commands in Option A. It exists purely to save retyping volume/
port flags during day-to-day development.

---

## Why the Docker files are organized this way

- **`docker/Dockerfile` and `docker/docker-compose.yml`** are grouped
  together out of the project root to keep the root less cluttered,
  without changing how either one is used — `-f docker/<file>` plus
  (for compose) `--project-directory .` is all that's needed.
- **`.dockerignore` deliberately stayed at the project root**, not moved
  into `docker/`. Docker looks for `<dockerfile-path>.dockerignore`
  first (which would be `docker/Dockerfile.dockerignore`) and only falls
  back to `<build-context-root>/.dockerignore` if that doesn't exist.
  Since the build context is the project root, keeping `.dockerignore`
  there is the simplest way to guarantee — not hope — that `.env` and
  the raw datasets stay excluded after this reorganization. This was
  verified, not assumed: see "What was actually verified" below.
- **The build context stays the project root** in both options (`docker
  build -f docker/Dockerfile .` and compose's `--project-directory .`),
  so `COPY . .` in the Dockerfile and the `.:/app` bind mount in compose
  are completely unchanged from before this reorganization — same files,
  same destinations, same behavior.

## What was actually verified (not assumed)

All of the below were re-run against a real Docker engine after this
file reorganization, in addition to the original verification from the
earlier containerization and secrets-management work:

- [x] `docker build -f docker/Dockerfile -t nautilus-dev .` succeeds from
      the project root.
- [x] `.env` and `web_config.py` remain absent from the built image, and
      a filesystem scan plus `docker history --no-trunc | grep` for the
      Maps key found zero matches — confirms `.dockerignore` staying at
      the project root is still correctly honored.
- [x] `python -m src.evaluate` inside the relocated-Dockerfile image
      reproduces the committed `data/processed/evaluation.csv` exactly
      (diffed column-by-column, excluding wall-clock timing).
- [x] `docker run --env-file .env -p 8000:8000 ... python server.py` is
      reachable on the host, binds to `0.0.0.0`, serves correct JSON
      from `/api/meta`, and injects the Maps key into the page (checked
      by length only — the value itself was never printed).
- [x] `docker compose -f docker/docker-compose.yml --project-directory .
      config` resolves `build.context` to the project root,
      `build.dockerfile` to `docker/Dockerfile`, the volume to
      `<project-root>:/app`, and `GOOGLE_MAPS_API_KEY` from `.env` — all
      identical to the pre-reorganization behavior (checked with the
      secret value redacted before it ever reached visible output).
- [x] `docker compose ... run --rm nautilus python -m src.evaluate` and
      `docker compose ... up -d nautilus-flask` (with a live
      `/api/meta` check and `down` afterward) both work end-to-end.
- [x] No raw `.nc` files and no host Python environment are required at
      any point in the above.

## Known, investigated limitations

### scikit-learn version skew on the shipped ML model (pre-existing, unrelated to this reorganization)

`data/processed/speed_model.joblib` was pickled with **scikit-learn
1.8.0**; the pinned `requirements.txt` installs **scikit-learn 1.9.0**,
producing a non-fatal `InconsistentVersionWarning` at load time.
Confirmed (again, after this reorganization) to not change any output —
diffed byte-for-byte against the baseline. Pre-existing, not introduced
by Docker or this file move. See `docs/loop-engineering/BLOCKERS.md`.

### ETA calculation — resolved (2026-10-03)

Formerly computed from distance at a constant 18 kn. Travel time now comes
from the ML speed model (`docs/Source_Of_Truth.md` §10.1); verified in the
container (`docs/loop-engineering/VALIDATION.md`, Loop 007).

### Production/offline-distribution image not yet built

This image includes development dependencies and the full source tree.
A minimal, distribution-focused image is a separate, later goal.

### Docker Hub / remote server

Not on the current roadmap (deferred). See
`docs/loop-engineering/TASKS.md` → Historical tasks.

## Secret management

Nautilus has exactly one genuine secret: the Google Maps JavaScript API
key, used only by `server.py`'s web UI. It is loaded from the
environment (`config.py`, optionally via a local `.env`) and is never
hardcoded in source, never baked into a Docker image layer, and `.env`
is gitignored so it's never committed. `config.py` is the single
configuration module for the whole application (the legacy
`web_config.py` has been removed).

**Frontend exposure note:** a Google Maps **JavaScript** API key is sent
to and used by the browser (injected into `web/index.html`, visible in
page source/devtools to anyone who loads the page) — that is normal for
this type of key and is not a leak by itself. What actually keeps it
safe to use client-side is restricting it in [Google Cloud
Console](https://console.cloud.google.com/google/maps-apis) to the HTTP
referrers (and/or the specific Maps JavaScript API) you actually serve
this app from, not keeping it out of `.env`/the browser.

## Files in `docker/` and what references them

| File | What / why |
| --- | --- |
| `docker/Dockerfile` | Builds the dev image. Referenced via `docker build -f docker/Dockerfile .` and, in compose, `build.dockerfile: docker/Dockerfile`. |
| `docker/docker-compose.yml` | Convenience wrapper for local dev (bind-mounted source, port mapping, optional `.env` loading). Referenced via `docker compose -f docker/docker-compose.yml --project-directory .`. Not required — everything it does can be done with Option A. |
| `.dockerignore` (project root) | Excludes raw datasets, `.git`, `.venv`, and `.env` from the build context. Stays at the root deliberately — see "Why the Docker files are organized this way" above. |
| `.env` / `.env.example` (project root) | `.env` is your real local config (gitignored, never committed, never part of the build context). `.env.example` documents every variable with safe placeholders and is committed. |
