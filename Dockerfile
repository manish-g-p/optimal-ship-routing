# Nautilus development image.
#
# Goal (docs/loop-engineering/TASKS.md TASK-001): run the existing Nautilus
# application/evaluation reproducibly in a container, without requiring the
# Python/scientific stack to be installed on the host. This is a
# DEVELOPMENT image (source + full dependency set), not yet the minimal
# production/distribution image described in Source_Of_Truth.md Decision
# "Development Image vs Deployment Image" - that split is deferred.
#
# Build:
#   docker build -t nautilus-dev .
#
# Run the existing evaluation (no GPU, no API key, no raw datasets needed -
# data/processed/ is already committed to the repo):
#   docker run --rm nautilus-dev python -m src.evaluate
#
# Run the Streamlit UI (no API key required):
#   docker run --rm -p 8501:8501 nautilus-dev \
#       streamlit run app.py --server.address=0.0.0.0
#
# Run the Flask UI (requires a Google Maps API key):
#   docker run --rm -p 8000:8000 -e GOOGLE_MAPS_API_KEY=your-key nautilus-dev \
#       python server.py
#
# See DOCKER.md for full details, including what was verified and what was
# not.

FROM python:3.12-slim

# Keep Python output unbuffered so logs/prints appear immediately, and
# don't let pip/apt write bytecode or cache files into the image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first (separate layer) so a source-only change does
# not invalidate the dependency-install layer on rebuild.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now bring in the rest of the project. .dockerignore keeps the raw
# multi-gigabyte NetCDF datasets, the host venv, .git, and the developer's
# local web_config.py (which may hold a real Maps API key) out of the image.
COPY . .

# web_config.py is intentionally NOT copied in (see .dockerignore) so a
# developer's local API key can never end up in an image layer. Generate a
# safe, secret-free stand-in with the same shape server.py expects - real
# values are supplied at `docker run` time via environment variables.
RUN printf '%s\n' \
    'import os' \
    '' \
    'GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")' \
    'PORT = int(os.environ.get("PORT", "8000"))' \
    'HOST = os.environ.get("HOST", "127.0.0.1")' \
    > web_config.py

# Flask's dev server binds host="127.0.0.1" by default (see server.py),
# which is unreachable from outside its own container even with `-p`.
# Default to 0.0.0.0 inside the image so `docker run -p 8000:8000` works
# out of the box; a bare-metal `python server.py` run outside Docker still
# defaults to 127.0.0.1 since this only overrides the image's environment.
ENV HOST=0.0.0.0

# Flask (server.py) and Streamlit (app.py) default ports, documented here
# for `docker run -p`; EXPOSE itself does not publish anything.
EXPOSE 8000 8501

# Default to an interactive shell: this is a development container meant
# to run whichever Nautilus entry point (src.evaluate, server.py, app.py,
# src.preprocess, etc.) the developer needs, via `docker run ... <command>`.
CMD ["bash"]
