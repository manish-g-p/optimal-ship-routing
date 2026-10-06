# Nautilus: Optimal Ship Routing System

Nautilus is a weather-aware ship-routing system for vessels travelling around
India. It combines GEBCO bathymetry, ERA5 wave data, a navigable ocean grid,
Dijkstra's shortest-distance algorithm, weather-aware A* search, and a
machine-learning vessel-speed model.

The project provides two interfaces: a Streamlit application for local use
without a Google Maps API key, and a Flask application with a Google Maps web
interface and JSON API.

## What the system does

1. Extracts the region around India from the large NetCDF source files.
2. Downsamples the data to a practical routing grid.
3. Removes shallow water and cells close to the coast.
4. Builds typical and rough wave scenarios.
5. Trains or loads a vessel-speed model.
6. Compares a traditional Dijkstra route with the proposed weather-aware A*
	route.

The default region is latitude `0` to `27` N and longitude `50` to `100` E.
The default grid resolution is `0.05` degrees, approximately 5.5 km per cell.

## Features

- Safe routing based on bathymetry, minimum depth, and coast-buffer rules.
- Traditional shortest-distance routing using Dijkstra's algorithm.
- Weather-aware travel-time routing using A* and predicted vessel speed.
- Typical, rough, and live marine-weather scenarios.
- Flask web application with Google Maps visualization.
- Streamlit interface that does not require a Google Maps API key.
- Evaluation of proposed and traditional routes.
- Simulated dynamic rerouting: a vessel advances along its route, weather
  changes, and a threshold-based controller reroutes from the current
  position when the alternative is sufficiently better. Available in the
  Flask app ("Voyage replay" mode: whole voyage at once; "Simulation lab"
  mode: step by step with manual weather) and from the console.

## Requirements

- Python 3.10 or newer
- Several GB of free disk space for the raw datasets
- Several GB of available memory for one-time weather extraction
- A Google Maps JavaScript API key only for the Flask map interface

Create and activate a virtual environment, then install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On macOS or Linux, activate the environment with:

```bash
source .venv/bin/activate
```

## Datasets

The raw datasets are too large for GitHub and must be downloaded separately.
The project expects these files in the repository root:

| Purpose | Dataset | Required filename | Download |
| --- | --- | --- | --- |
| Bathymetry and depth safety mask | GEBCO 2024 sub-ice-topography NetCDF | `GEBCO_2024_sub_ice_topo.nc` | [Google Drive dataset 1](https://drive.google.com/file/d/1hOWit5p4TubLsOrbWnMeq9poyGdt2p24/view?usp=sharing) |
| Significant wave height, direction, and period | ERA5 wave NetCDF | `data_stream-wave_stepType-instant.nc` | [Google Drive dataset 2](https://drive.google.com/file/d/1uE4uSOUD5Bpslm-KvAuxNOCRaqsiXApH/view?usp=sharing) |

Direct download links:

- Dataset 1: https://drive.google.com/file/d/1hOWit5p4TubLsOrbWnMeq9poyGdt2p24/view?usp=sharing
- Dataset 2: https://drive.google.com/file/d/1uE4uSOUD5Bpslm-KvAuxNOCRaqsiXApH/view?usp=sharing

Place them here after downloading and renaming if necessary:

```text
Optimal ship routing system/
	GEBCO_2024_sub_ice_topo.nc
	data_stream-wave_stepType-instant.nc
```

Run the one-time preprocessing step:

```bash
python -m src.preprocess
```

This extracts only the configured region and creates `bathymetry.npz`,
`weather.npz`, and `weather_grid.csv` in `data/processed/`. The raw files are
not needed by the applications after preprocessing. Keep them if you plan to
change the region or grid resolution. The wave subset is loaded while
scenarios are calculated, so preprocessing can require several GB of memory.

## Running the Applications

### Flask and Google Maps interface

The Google Maps key (and the Flask port/host) are read from the
environment, optionally via a local `.env` file. Copy the template and
fill in your key:

```bash
cp .env.example .env
# then edit .env and set GOOGLE_MAPS_API_KEY
python server.py
```

Setting the variable directly in your shell instead of using `.env` also
still works, and takes precedence if both are set. On Windows PowerShell:

```powershell
$env:GOOGLE_MAPS_API_KEY = "your-key"
python server.py
```

Open `http://localhost:8000`. The map, the JSON API, and all routing
features work without a key configured — only the map tiles need one.
Restrict the Google key in Google Cloud Console to the local application
origin and to the Google Maps JavaScript API: a Maps JavaScript key is
sent to and used by the browser, so it is visible in the page source to
anyone who loads the app — those restrictions, not secrecy, are what
keep it safe to use client-side. `.env` is gitignored; never commit a
real key to the repository.

The Flask server exposes:

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/meta` | Available ports, vessels, region bounds, and simulation options |
| `GET` | `/api/weather?scenario=typical` | Weather overlay metadata |
| `GET` | `/api/weather_image?scenario=rough` | Wave overlay PNG |
| `POST` | `/api/route` | Calculate one or both routes |
| `POST` | `/api/simulate` | Simulated voyage with weather-driven rerouting, compared with the same voyage without rerouting |
| `GET` | `/api/sim/presets` | Simulation-lab demonstration scenarios, input limits, default rerouting settings |
| `POST` | `/api/sim/sessions` | Create a Simulation-lab session (`origin`, `dest`, `vessel`, `base_weather`, `preset`, `rerouting_enabled`, `config`) |
| `GET`, `DELETE` | `/api/sim/sessions/<id>` | Current session state / delete the session |
| `POST` | `/api/sim/sessions/<id>/step` | Advance one step; body `{"expected_step": n}` (rejects duplicates with 409) |
| `POST` | `/api/sim/sessions/<id>/weather` | Set the pending disturbance list `{"disturbances": [{lat, lon, radius_km, delta_m}]}` |
| `POST` | `/api/sim/sessions/<id>/weather/apply` · `/weather/discard` | Apply pending weather now / discard it |
| `POST` | `/api/sim/sessions/<id>/schedule/cancel` · `/reset` | Cancel remaining preset updates / reset to step 0 |
| `GET` | `/api/sim/sessions/<id>/weather_image?v=<version>` | PNG of the applied wave field (base + disturbances) |

Example route request in PowerShell:

```powershell
$body = @{
	origin = "Cochin (Kerala)"
	dest = "Dubai / Jebel Ali (UAE)"
	vessel = "General Cargo"
	scenario = "typical"
	algorithms = @("dijkstra", "astar")
	use_ml = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8000/api/route `
	-Method Post -ContentType "application/json" -Body $body
```

### Streamlit interface

```bash
streamlit run app.py
```

Open `http://localhost:8501`.

### Full pipeline and evaluation

```bash
python run_all.py
```

The command preprocesses raw data when processed files are missing, trains the
speed model when needed, and evaluates the rough-weather routes. Results are
written to `data/processed/evaluation.csv`.

Route metrics: `distance_km` is the path length; `cost` is the search objective
(km for Dijkstra; km × weather multiplier for A*); `time_hours` is the
estimated travel time from the ML speed model for the selected vessel and
weather (`time_basis: "ml_speed"`). Dijkstra and A* routes use the same time
model, so their hours are comparable. These are model estimates, not
real-world arrival times. Definitions: `docs/Source_Of_Truth.md` §10.1.

To retrain the speed model independently:

```bash
python -m src.ml_model
```

The trained model is written to `data/processed/speed_model.joblib`.

### Dynamic rerouting simulation

```bash
python -m src.rerouting
```

Simulates a voyage (Cochin to Dubai by default) under several synthetic weather
scenarios. A vessel advances along its route, weather updates are applied, and
a threshold-based controller decides whether to switch to an alternative from
the vessel's current position. Each scenario is compared against a static
voyage with no rerouting. Thresholds are the `REROUTE_*` settings in
`config.py`.

The same simulation is available in the Flask app. Choose **Voyage
simulation** mode, pick ports, a vessel, Typical or Rough base weather and a
weather change, then run it. The map shows the initial plan (dashed), the
track actually sailed, reroute points (R1, R2, ...) and where the weather
changed. A slider moves the vessel through the voyage. The panel lists
every rerouting evaluation with its triggers and reason, and compares the
voyage with and without rerouting. The `simulate` request takes `origin`,
`dest`, `vessel`, `base_weather` (`typical` or `rough`), `scenario`
(`stable`, `adverse`, `worsening`, `improving_alt`, `minor`, `shifting`)
and optional `config` overrides (for example `{"cooldown_steps": 6,
"min_gain": 0.05}`).

All simulation figures are model estimates: the weather changes are synthetic
and the speed model was trained on synthetic data. They are not real-world
voyage performance.

### Simulation lab (interactive)

In the Flask app, choose **Simulation lab**. Pick ports, a vessel, a
Typical/Rough sea state and optionally a demonstration scenario, then
**Start** (automatic stepping), **Pause**, **Step** (one step) or
**Reset**. During the voyage you can add storms or calm patches. Use
**Place on map** and click the map, or type coordinates; set a peak
wave-height change and a radius (1σ of a Gaussian). You can also drag a
circle to move it, or select one to edit or remove it.

Edits are *pending* (white outline, "pending" badge) and the routing
engine does not see them until you click **Apply now** or take the next
step. The backend then evaluates the active route under the new weather
and reroutes only if the existing threshold controller decides to. The
map shows:

- the initial plan (dashed grey);
- the active route (blue);
- the sailed track (green);
- the vessel;
- reroute points R1, R2, …;
- the disturbances;
- an overlay rendered from the applied weather field.

The timeline lists every backend decision with its triggers, costs, the
alternative found and the gain. The metrics compare the voyage with the
same voyage without rerouting under the same weather.

Only significant wave height is simulated; wave period and direction stay
as in the base sea state. Sessions live in the server's memory: up to 8,
expiring after 30 minutes idle, and a server restart discards them. All
values are model estimates, not real-world performance. Browser check:
`node tools/lab_e2e.mjs <outdir>`; environment comparison:
`python tools/lab_parity.py <url> <out.json>`.

### Rerouting evaluation

```bash
python -m src.evaluate_rerouting
```

Runs every evaluation voyage with every vessel profile under each simulated
weather scenario, twice: once with rerouting and once without (150 pairs,
about 9 minutes). It writes per-run results, rerouting events, summaries by
voyage, vessel and scenario, the configuration used, and a heatmap to
`data/rerouting_eval/`. Each run is classified `ok`, `draft_infeasible`,
`incomplete` or `failed`. Only `ok` runs enter the averages. These outputs
are separate from the route-planning baseline in `data/processed/`.
Results are simulated, model-based estimates, not real-world performance.

### Tests

```bash
python -m unittest discover -s tests -v
```

The tests use the committed `data/processed/` artifacts and need no network.
They check the initial evaluation routes, rerouting from a vessel's current
position, the dynamic rerouting scenarios, the Flask API (`/api/route`,
`/api/simulate`) and the integrity of the rerouting evaluation.

## Repository Contents

```text
config.py                 Shared paths, routing parameters, and env/.env-based settings
.env.example              Template for local secrets/config (copy to .env)
server.py                 Flask backend, static server, and JSON API
app.py                    Streamlit interface
run_all.py                End-to-end preprocessing, training, and evaluation
src/preprocess.py         NetCDF extraction and weather aggregation
src/grid.py               Navigable grid construction and loading
src/routing.py            Dijkstra and A* routing
src/weather.py            Processed weather loading
src/live_weather.py       Optional live weather support
src/ml_model.py           Speed-model training and inference
src/evaluate.py           Route comparison and metrics
src/rerouting.py          Rerouting controller and voyage simulation
src/evaluate_rerouting.py Rerouting-on vs. rerouting-off evaluation matrix
src/sim_session.py        Interactive Simulation-lab sessions (step, weather edits, timeline)
src/weather_sim.py        Synthetic weather updates for rerouting scenarios
src/ports.py              Port catalogue and coordinates
src/vessel.py             Vessel profiles
tests/                    Routing and rerouting tests (unittest)
tools/lab_e2e.mjs         Headless-browser end-to-end check of the web app
tools/lab_parity.py       Deterministic Simulation-lab API run (host vs. Docker)
web/                      Flask frontend files
data/processed/           Generated routing and model artifacts (route-planning baseline)
data/rerouting_eval/      Rerouting evaluation outputs (python -m src.evaluate_rerouting)
```

## Configuration

Edit `config.py` to change the geographic bounding box, grid resolution,
minimum water depth, coast buffer, vessel speed, or weather cost weights.
Changing the region or grid resolution requires rerunning preprocessing and
rebuilding the processed grid and model artifacts.

Important settings include `LAT_MIN`, `LAT_MAX`, `LON_MIN`, `LON_MAX`,
`GRID_RES`, `MIN_DEPTH_M`, `COAST_BUFFER_KM`, `SHIP_SPEED_KN`,
`W_WAVE_HEIGHT`, `W_HEAD_SEAS`, `W_PERIOD`, and `MAX_WEATHER_MULT`.

## Troubleshooting

**A raw NetCDF file is not found**

Check that the filename and location exactly match `config.py` and that the
download completed successfully.

**The application cannot load the grid or model**

Run `python -m src.preprocess`, then `python -m src.ml_model`, or run
`python run_all.py` to create the generated files.

**The Flask map is blank**

Set `GOOGLE_MAPS_API_KEY` in the same terminal used to start `server.py` and
confirm that the key enables the Google Maps JavaScript API.

**Preprocessing is slow**

This is expected for multi-gigabyte NetCDF files. The raw files are read only
during preprocessing; normal application startup uses `data/processed/`.

## Files Not Uploaded to GitHub

The following local files and directories are intentionally excluded:

- `GEBCO_2024_sub_ice_topo.nc` (approximately 7.4 GB)
- `data_stream-wave_stepType-instant.nc` (approximately 4.1 GB)
- `.claude/` local tooling configuration
- `__pycache__/` and compiled Python files
- `.env` and Streamlit secret files
- PDF and PowerPoint presentation files

The two NetCDF datasets exceed GitHub's 100 MB per-file limit and must be
stored locally or obtained from their respective data providers. The
processed artifacts in `data/processed/` are included to support normal
application use after cloning.

## Future Improvements

- Use forecast timestamps instead of time-averaged weather scenarios.
- Extend the routing region beyond the seas around India.
- Train the speed model with real AIS vessel data.
