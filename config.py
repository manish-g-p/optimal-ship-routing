"""
Central configuration for the Optimal Ship Routing system.

Everything tunable lives here so the rest of the code stays clean.
Edit BBOX / GRID_RES if you ever want a different region or resolution.

Secrets and per-environment values (the Google Maps API key, the Flask
port/host) are NOT hardcoded here - they are read from the process
environment, optionally populated from a local .env file (see
.env.example). Never commit .env; it is excluded in .gitignore.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Does not overwrite a variable that's already set in the real shell
    # environment (override=False, the default) - so `export
    # GOOGLE_MAPS_API_KEY=...` before running still takes precedence over
    # .env, matching the project's prior documented behavior.
    load_dotenv()
except ImportError:
    # python-dotenv is in requirements.txt, but routing/evaluation code
    # that imports this module should not break if it's somehow missing -
    # only the Flask web settings below would be unavailable without it.
    pass

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent

# Raw NetCDF files (the giant ones). These are read ONCE by preprocess.py
# and then never touched again. You can move/delete them after that.
GEBCO_NC = ROOT / "GEBCO_2024_sub_ice_topo.nc"          # 7.4 GB bathymetry
WAVE_NC  = ROOT / "data_stream-wave_stepType-instant.nc"  # 4.1 GB ERA5 waves

# Small processed outputs live here (a few MB total).
PROCESSED = ROOT / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

BATHY_FILE   = PROCESSED / "bathymetry.npz"   # depth grid + lat/lon
WEATHER_FILE = PROCESSED / "weather.npz"      # swh/mwd/mwp on wave grid
WEATHER_CSV  = PROCESSED / "weather_grid.csv" # normalized weather (PDF: CSV)
GRID_FILE    = PROCESSED / "grid.npz"         # navigable mask + costs
ML_MODEL_FILE = PROCESSED / "speed_model.joblib"  # trained speed predictor
EVAL_CSV     = PROCESSED / "evaluation.csv"   # proposed-vs-traditional metrics

# ----------------------------------------------------------------------
# Region of interest: the seas around India (all Indian ports).
# lat 0 -> 27 N, lon 60 -> 100 E covers the Arabian Sea, the Bay of
# Bengal and the approaches used by Indian incoming/outgoing traffic.
# ----------------------------------------------------------------------
LAT_MIN, LAT_MAX = 0.0, 27.0
# West edge is 50E so Oman/UAE ports (Salalah 54E, Dubai 54.9E) and the
# Gulf of Oman are inside the map - otherwise routes to them stop short
# at the boundary, leaving a visible gap.
LON_MIN, LON_MAX = 50.0, 100.0
BBOX = (LON_MIN, LAT_MIN, LON_MAX, LAT_MAX)

# Routing grid resolution in degrees. 0.05 deg is about 5.5 km per cell.
# Bigger number  -> fewer cells -> faster + lighter (safer for laptops).
# Smaller number -> finer routes -> heavier. 0.05 is a good balance.
GRID_RES = 0.05

# ----------------------------------------------------------------------
# Navigability / safety constraints
# ----------------------------------------------------------------------
# A cell counts as open water only if the seafloor is deeper than this
# (elevation more negative than -MIN_DEPTH_M). Keeps ships off shoals.
MIN_DEPTH_M = 10.0

# Exclude any sea cell within this distance of land (synopsis: 22 km).
COAST_BUFFER_KM = 22.0

# ----------------------------------------------------------------------
# Ship / cost-function parameters (used by the weather-aware A*)
# ----------------------------------------------------------------------
SHIP_SPEED_KN = 18.0   # nominal calm-water speed in knots

# How strongly waves penalise a leg. These are simple, explainable
# weights - tune them and the route visibly changes.
W_WAVE_HEIGHT = 0.6    # penalty per metre of significant wave height
W_HEAD_SEAS   = 0.4    # extra penalty for sailing INTO the waves
W_PERIOD      = 0.1    # short, choppy periods are slightly worse

# Cap so a single stormy cell can't make cost explode to infinity.
MAX_WEATHER_MULT = 4.0

KM_PER_DEG = 111.195   # mean km per degree of latitude

# ----------------------------------------------------------------------
# Dynamic rerouting (src/rerouting.py). Defaults for RerouteConfig.
# "Cost" is the routing search cost (Router.path_cost): km x weather
# multiplier, i.e. km-equivalent at service speed with the ML cost model.
# ----------------------------------------------------------------------
REROUTE_CELLS_PER_STEP = 10       # cells the vessel advances per step (~55 km)
REROUTE_EVAL_INTERVAL = 1         # evaluate the active route every N steps
REROUTE_COOLDOWN_STEPS = 3        # min steps between two route changes
REROUTE_SWH_TRIGGER_M = 4.0       # trigger: max wave height on remaining route
REROUTE_COST_TRIGGER = 0.05       # trigger: remaining cost up >= 5% vs plan
REROUTE_RECHECK_STEPS = 4         # trigger: periodic re-check (0 = off), only
                                  # searches if the weather has changed
REROUTE_MIN_GAIN = 0.03           # adopt only if alternative >= 3% cheaper
REROUTE_MIN_GAIN_ABS = 20.0       # ... and at least this many cost units

# ----------------------------------------------------------------------
# Flask web UI settings (formerly web_config.py - merged in here so there
# is a single configuration module, with secrets/per-environment values
# coming from the environment / .env rather than being hardcoded).
# ----------------------------------------------------------------------
# Google Maps JavaScript API key for server.py's web UI. Empty by default
# so the app starts and the JSON API still works with no key configured;
# server.py logs a non-fatal warning (not an error, and never the key
# value itself) when this is empty. Set it in .env - see .env.example.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# Port the Flask app (server.py) listens on.
PORT = int(os.environ.get("PORT", "8000"))

# Interface the Flask dev server binds to. 127.0.0.1 (localhost only) is
# the safe default outside Docker; the Docker image sets HOST=0.0.0.0 so
# `docker run -p` can reach it (see docker/Dockerfile).
HOST = os.environ.get("HOST", "127.0.0.1")
