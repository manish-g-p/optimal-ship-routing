# Nautilus — Project Source of Truth

**Project:** Nautilus
**Category:** ML-Assisted Dynamic Ship Routing System
**Primary Focus:** Weather-Aware Rerouting and Machine Learning
**Status (2026-10-06):** Routing foundation, current-position rerouting and threshold-based dynamic rerouting (simulation) are implemented, and the simulation can be run and inspected in the Flask UI, including an interactive Simulation lab with manual weather control (§12.1). Route cost, distance and travel time now have defined, tested semantics (§10.1). The threshold-based controller has been evaluated across all voyages, vessels and weather scenarios (§11.5). Routes enforce vessel-specific depth (draft + under-keel margin) and coastal clearance, and reroutes record their geometry (§5.3). Next: to be decided (see `docs/loop-engineering/TASKS.md`). Detailed state: `docs/loop-engineering/PROJECT_STATE.md`.

---

## 1. Project Overview

Nautilus is a ship-routing and decision-support system designed to generate efficient maritime routes and adapt them when weather conditions change.

The project focuses on combining traditional pathfinding algorithms with machine learning to improve route estimation and support dynamic rerouting.

Unlike a conventional static routing engine, Nautilus should be able to respond to changing environmental conditions during a simulated voyage. When the existing route becomes less efficient due to changing weather, the system should evaluate alternatives and recommend an updated route.

The goal is to build a functional, demonstrable system that combines:

* Graph-based pathfinding.
* Weather-aware route cost estimation.
* Machine learning for vessel speed prediction.
* Dynamic route recalculation.
* Route comparison and visualization.
* A reproducible, containerized execution environment.

The project is primarily a software engineering and applied ML project. It is not intended to become an autonomous vessel navigation system or a comprehensive maritime safety platform.

---

## 2. Core Problem Statement

Traditional static routing generates a route using the environmental conditions available at planning time. However, weather conditions can change during a voyage.

A route that was initially efficient may become less desirable because of:

* Increased wind or wave severity.
* Adverse weather along the planned path.
* Changes in estimated vessel speed.
* Better alternative paths becoming available.

A static route planner does not inherently respond to these changes.

Nautilus addresses this problem by introducing a dynamic rerouting mechanism that periodically or conditionally evaluates the current route and determines whether recalculation is beneficial.

Machine learning will support this process by estimating vessel speed under different weather conditions and, where justified, assisting rerouting decisions.

---

## 3. Project Goals

### 3.1 Primary Goals

1. **Dynamic rerouting**

   * Recalculate routes from a vessel's current position.
   * Respond to changing weather conditions.
   * Avoid restarting route generation from the original departure port.
   * Compare existing and alternative routes before recommending a change.

2. **Weather-aware routing**

   * Use environmental data to influence route costs.
   * Account for the effect of weather on estimated vessel speed.
   * Support simulated weather updates and, where practical, external weather data.

3. **ML-assisted route estimation**

   * Retain and improve the existing Random Forest speed prediction model.
   * Integrate ML-based speed estimation into route cost calculations.
   * Evaluate whether an ML-based rerouting decision model provides measurable benefits over rule-based thresholds.

4. **Route evaluation and visualization**

   * Compare the original and updated routes.
   * Display relevant metrics such as estimated travel time, distance, and weather-related cost.
   * Explain why a rerouting decision was made.

5. **Reproducible execution**

   * Preserve Docker-based execution.
   * Maintain support for offline evaluation using locally available data.
   * Keep configuration and secrets externalized.

### 3.2 Secondary Goals

* Improve the existing routing and evaluation code.
* Make rerouting behavior configurable.
* Build a repeatable simulation process for testing changing weather.
* Improve the consistency of route cost and ETA calculations.
* Keep the architecture modular enough to support future experiments.

---

## 4. Scope and Non-Goals

### In Scope

* Static initial route generation.
* Dynamic route recalculation.
* Weather-aware pathfinding.
* Machine learning for vessel speed prediction.
* Threshold-based rerouting.
* Experimental ML-based rerouting decisions.
* Simulated environmental changes.
* Route comparison and visualization.
* Performance and behavior evaluation.
* Docker-based deployment and offline testing.

### Out of Scope

The following are not required for the current project:

* Autonomous ship navigation or control.
* Reinforcement learning as a mandatory routing mechanism.
* Deep learning-based weather forecasting.
* Complex multi-agent architectures.
* Advanced maritime risk prediction.
* Formal uncertainty quantification.
* Maritime safety certification.
* Large-scale real-time weather infrastructure.
* Complex distributed event-processing systems.
* Adding routing algorithms solely to increase the number of algorithms supported.

These areas may be revisited only if they become necessary to address a demonstrated limitation of the core system.

---

## 5. Existing System and Technical Foundation

Nautilus already contains several components that should be reused and improved rather than rebuilt without a clear reason.

### 5.1 Geographic Scope

The current data coverage focuses on waters around India and the surrounding Indian Ocean region.

Approximate geographic bounds:

* Latitude: 0°N to 27°N.
* Longitude: 50°E to 100°E.

### 5.2 Data Processing

The existing data pipeline uses:

* GEBCO bathymetric data.
* ERA5 weather data.
* Processed environmental grids.
* Navigability information.

The pipeline converts raw geographical and environmental information into data structures that can be consumed by the routing engine.

Existing data processing should remain the foundation for route generation and evaluation.

### 5.3 Navigable Grid

The routing engine operates on a grid that represents navigable and non-navigable regions.

The grid is used to:

* Represent possible vessel movement.
* Restrict routes to navigable cells.
* Calculate movement costs.
* Support graph-based search.

Dynamic rerouting must preserve navigability constraints when calculating alternative routes.

**Implemented constraints (2026-10-06):**

* **Grid.** 0.05° cells (≈ 5.6 × 5.4 km). Depth is GEBCO elevation relative to **mean sea level** (not chart datum). Downsampling keeps the **shallowest** point of each block, so cell depths are conservative.
* **Coastal clearance (hard, all vessels).** A cell is navigable if it is ≥ `MIN_DEPTH_M` (10 m) deep and ≥ `COAST_BUFFER_KM` (22 km) from any land or water shallower than 10 m. The mask is recomputed when the grid loads, so the clearance is configurable without a rebuild. At 22 km it closes narrow passages: the Strait of Hormuz (Dubai uses the Fujairah approach), the Palk Strait, and parts of the Gulf of Kutch. Some ports therefore snap far offshore (Kandla 141 km, Mundra 100 km).
* **Depth feasibility (hard, per vessel).** Every route cell needs depth ≥ draft × (1 + `UKC_FRACTION`), with `UKC_FRACTION` 0.20 (`vessel.required_depth_m`). This applies identically to initial routes, alternatives (the controller rejects candidates crossing water too shallow for the vessel), evaluation and both UIs. When no route qualifies, the result is an explicit infeasible outcome with a reason, never an unsafe fallback. Example: Kandla → Cochin is infeasible for the Container Ship and the VLCC (start cell 16 m vs. 17.4 / 24.6 m required).
* **Coastal preference (soft, optional).** `COAST_PENALTY` raises cost near the clearance edge, for weather-aware A* only. It is **off by default**: in rough weather it pushes routes into rougher open water (EXP-008).

### 5.4 Existing Routing Algorithms

The existing routing foundation includes:

**Dijkstra's algorithm**

* Finds paths using accumulated movement costs.
* Provides a conventional graph-search baseline.
* Can be used for distance-based or configured cost-based routing.

**Weather-aware A***

* Uses a heuristic to guide route search.
* Incorporates weather-dependent movement costs.
* Uses the existing ML speed prediction component in the current design.

Both algorithms should be evaluated for suitability in the dynamic rerouting workflow. There is no requirement to introduce additional algorithms unless an actual limitation is identified.

### 5.5 Vessel Profiles

The project contains five vessel profiles.

Vessel characteristics should influence speed estimation and route cost calculations where the required information is available.

The existing profiles should be retained and validated rather than introducing an unnecessarily detailed vessel dynamics model.

### 5.6 Ports and Route Evaluation

The existing dataset contains approximately 20 ports and an evaluation script for a fixed set of five voyages.

These can serve as the initial evaluation cases for static and dynamic routing.

The current evaluation process should be extended to include changing weather and rerouting behavior.

### 5.7 Implemented Rerouting Capabilities

As of 2026-10-03:

* **Current-position rerouting:** `Router.search` routes from any navigable grid cell; invalid or non-navigable start/goal cells raise an error; `RouteResult.cost` and `Router.path_cost` expose the routing cost for comparisons.
* **Threshold-based dynamic rerouting (simulation):** `src/weather_sim.py` (deterministic simulated weather updates) and `src/rerouting.py` (vessel progress along the active route, remaining-route evaluation, configurable triggers, cooldown, improvement thresholds, rerouting event log). Defaults are the `REROUTE_*` settings in `config.py`. Run it with `python -m src.rerouting`.
* **Flask UI integration:** "Voyage replay" mode and `POST /api/simulate` run a voyage with and without rerouting. They show the initial plan, the sailed track, reroute points, weather changes, a progress slider, and each rerouting evaluation with its reason. The Streamlit app does not include it.
* **Consistent travel time:** routes report travel time from the ML speed model for the selected vessel and weather, the same model the weather-aware cost uses (§10.1).
* **Simulation lab:** `src/sim_session.py` + `/api/sim/sessions…` let a user step, pause, reset and edit weather during a voyage in the browser. The same `rerouting.Voyage` stepper used by `simulate()` makes every decision (§12.1).
* **Rerouting evaluation:** `python -m src.evaluate_rerouting` compares rerouting-enabled and rerouting-disabled voyages across the fixed voyage set, all vessel profiles and all simulated weather scenarios (§11.5).
* **Navigational safety and reroute geometry (2026-10-06):** vessel depth feasibility and configurable clearance (§5.3). An optional route-change penalty is used only when a nearby alternative is about as good as the best one. Each reroute records its corridor shift, length change, heading change and cause.
* Not yet implemented: ML rerouting decisions (§8.2).

---

## 6. Target System Architecture

The target architecture is intentionally simple. The primary objective is to create a reliable rerouting loop without introducing unnecessary infrastructure.

### 6.1 High-Level Workflow

```text
User selects departure and destination
                  |
                  v
          Initial Route Planner
                  |
                  v
           Initial Route
                  |
                  v
           Weather Updates
                  |
                  v
       Evaluate Current Route
                  |
                  v
        Rerouting Decision
                  |
           +------+------+
           |             |
           v             v
       No Change      Rerouting
           |             |
           |             v
           |       Generate Alternative
           |             |
           |             v
           |       Estimate Route Costs
           |             |
           |             v
           |       Compare Routes
           |             |
           |             v
           |       Recommend Route
           |             |
           +------+------+
                  |
                  v
          Update Route Display
                  |
                  v
           Continue Monitoring
```

The workflow should be implemented as a manageable application-level loop. A distributed streaming platform or complex orchestration framework is not necessary.

### 6.2 Core Components

**Route Planner**

* Generates the initial route.
* Supports routing from arbitrary valid grid positions.
* Accepts route cost configurations.
* Returns route geometry and relevant cost information.

**Weather Data Provider**

* Supplies environmental data to the routing engine.
* Supports locally stored weather data.
* Supports simulated weather changes for repeatable tests.
* Can later be extended to use live data.

**Route Evaluator**

* Evaluates the current route under updated weather conditions.
* Estimates travel time and route cost.
* Identifies weather conditions that may justify recalculation.

**Rerouting Controller**

* Determines when a new route should be calculated.
* Initially uses configurable thresholds.
* Prevents unnecessary route changes.
* Coordinates alternative route generation and comparison.

**ML Speed Predictor**

* Estimates vessel speed under environmental conditions.
* Supplies speed estimates to route cost calculations.
* Provides a consistent prediction interface for the routing engine.

**Route Comparator**

* Compares the current route with candidate alternatives.
* Uses consistent metrics and cost assumptions.
* Supports the final rerouting decision.

**Visualization Layer**

* Displays route geometry and changes.
* Presents route metrics.
* Shows the reason for rerouting.
* Helps users understand the effects of updated weather conditions.

---

## 7. Dynamic Rerouting Design

Dynamic rerouting is the central feature of Nautilus.

### 7.1 Rerouting from the Current Position

The routing engine must support generating a route from the vessel's current simulated position rather than always using the original departure port.

The rerouting process should:

1. Maintain the vessel's progress along the active route.
2. Identify its current position in the routing grid.
3. Update the environmental conditions.
4. Evaluate the remaining part of the existing route.
5. Generate an alternative route to the original destination when required.
6. Compare the alternative with the remaining existing route.
7. Decide whether to retain or replace the active route.

This behavior is fundamental to the project and should be implemented before adding sophisticated ML decision-making.

### 7.2 Rerouting Triggers

The initial system should use simple, interpretable triggers.

Potential triggers include:

* Weather severity exceeding a configured threshold.
* A significant increase in estimated remaining travel time.
* An alternative route offering sufficient estimated cost reduction.
* A periodic route reevaluation interval.

These triggers should be configurable rather than embedded as unexplained constants throughout the codebase.

### 7.3 Avoiding Unnecessary Rerouting

Repeated route changes can cause unstable behavior and make evaluation difficult.

The rerouting controller should support:

* A minimum improvement threshold.
* A minimum time or distance between route changes.
* Avoiding repeated calculations when the environment has not changed meaningfully.
* Comparing only feasible alternative routes.

These mechanisms should remain simple and transparent.

### 7.4 Route Continuity

A new route should begin from the current vessel position and connect to the existing destination.

The system should preserve route continuity and avoid unnecessary backtracking where possible.

For the initial implementation, the vessel's position can be advanced using a simplified movement simulation along the active route.

Accurate physical vessel simulation is not a requirement.

---

## 8. Machine Learning Integration

ML should improve the existing routing workflow rather than make the project dependent on complex learning algorithms.

### 8.1 Random Forest Speed Prediction

The existing Random Forest model estimates vessel speed based on environmental conditions and vessel-related inputs.

Its purpose is to improve the estimation of movement costs in weather-aware routing.

The model should be integrated consistently into:

* Initial route generation.
* Alternative route generation.
* Remaining-route evaluation.
* Estimated travel-time calculations.

The model currently relies on synthetic, physics-inspired training data. Its predictions must therefore be treated as experimental estimates rather than validated real-world vessel performance.

### 8.2 ML-Based Rerouting Decision

An additional ML model may be introduced to estimate whether a rerouting decision is beneficial.

Potential input features include:

* Estimated remaining travel time on the current route.
* Estimated travel time on an alternative route.
* Weather severity on both routes.
* Remaining route distance.
* Estimated difference in route cost.
* Vessel-related parameters, where available.

The output may be a binary reroute/no-reroute recommendation.

This model is experimental and should only be implemented after a functional threshold-based baseline exists.

Training data can initially be generated from repeatable simulations. Labels should be defined using a clear comparison objective, such as whether rerouting produces a sufficiently lower total cost under the simulated conditions.

The model should be compared against the rule-based baseline using held-out scenarios. It should not be assumed to provide better decisions simply because it uses ML.

### 8.3 ML Design Principles

* Prefer interpretable and manageable models.
* Avoid unnecessary model complexity.
* Keep prediction separate from hard navigability constraints.
* Use consistent features and cost definitions across route planning and evaluation.
* Track model versions and training assumptions.
* Report model limitations clearly.
* Retain rule-based fallbacks when predictions are unavailable or invalid.

### 8.4 Reinforcement Learning

Reinforcement learning is not part of the core implementation plan.

It may be considered as a future experiment only if simpler rerouting policies demonstrate a meaningful limitation that RL could reasonably address.

The project should be considered successful without RL.

---

## 9. Weather Data and Simulation

Weather changes are required to demonstrate dynamic rerouting.

However, building a full live weather platform is not necessary for the current scope.

### 9.1 Initial Approach

Use existing weather datasets and controlled simulated updates.

The simulation should support scenarios such as:

* Weather conditions worsening along the active route.
* Adverse weather appearing near the current route.
* Weather conditions improving along an alternative route.
* Conditions remaining unchanged, where no rerouting should occur.

These scenarios make it possible to evaluate rerouting behavior consistently.

### 9.2 Live Weather Integration

Live weather integration is a secondary feature.

If implemented, it should use an available weather source and fit into the existing weather provider interface.

The routing engine should not be tightly coupled to one external provider.

### 9.3 Missing or Unavailable Data

The initial system should handle basic data availability problems:

* Missing weather values.
* Invalid values.
* Unavailable updates.
* Stale weather data.

A simple validation and fallback strategy is sufficient for the prototype. Advanced uncertainty estimation is not required.

---

## 10. Route Cost and ETA Consistency

Route cost and travel-time calculations must use consistent assumptions.

A route planner that uses weather-dependent speed estimates should not report an ETA based on an unrelated constant-speed calculation without clearly identifying the difference.

The system should distinguish:

* Geographical distance.
* Weather-adjusted movement cost.
* Estimated travel time.
* Any additional configured penalties.

For the core implementation, estimated travel time should be derived from the same speed assumptions used by the route evaluator.

Any discrepancy between accumulated routing cost and reported ETA should be treated as a correctness issue.

The objective is not to build a perfect vessel performance model, but to make route comparisons internally consistent and meaningful.

### 10.1 Implemented Metric Definitions (2026-10-03)

| Metric | Unit | Definition |
| --- | --- | --- |
| Distance (`distance_km`) | km | Great-circle length of the route's cell path (sum of segment lengths). |
| Route cost (`cost`) | depends on cost model | The search objective. Dijkstra: km. Weather-aware A* with the ML model: Σ segment km × (service speed ÷ ML-predicted speed), i.e. km-equivalent at service speed. A* with the analytic wave multiplier: a weighted penalty, **not** time. Costs are compared only within one cost model and weather state. |
| Travel time (`time_hours`, "est. hours") | h | Σ segment km ÷ (segment speed × 1.852). Segment speed is the ML-predicted speed for the vessel, sea state and heading ("ml_speed" basis), bounded to [service ÷ 4, service]. Without an ML model it is the calm-water service speed ("calm_water" basis). A route reports its basis in `time_basis`. |

* Travel time is a property of the path and the time model, not of the algorithm that chose the path. The Flask API, Streamlit app and evaluation estimate Dijkstra and A* routes with the same ML model, so their hours are comparable.
* With the ML cost model, cost ÷ (service speed × 1.852) equals travel time exactly; this relation is tested. If the optional coastal preference is enabled (§5.3), cost also includes that soft penalty and is no longer exactly time. Travel time itself never includes penalties.
* In voyage simulation, voyage time is the sum over sailed legs of each leg's travel time under the weather in force when it was sailed. Rerouting decisions use cost only; reported hours never feed a decision.
* "ETA" in Nautilus means estimated time en route from departure, in hours. It is a model estimate (synthetic-data speed model), not a predicted real-world arrival time.

---

## 11. Evaluation Strategy

The system must be evaluated using repeatable scenarios rather than relying only on visual demonstrations.

### 11.1 Baselines

At minimum, compare:

**Static routing**

* Generates a route using initial weather information.
* Does not respond to later weather changes.

**Threshold-based dynamic rerouting**

* Re-evaluates the current route when configured conditions are met.
* Generates and compares alternatives when required.

**ML-assisted rerouting**

* Uses the speed prediction model.
* May additionally use the experimental ML decision model.
* Is evaluated against the corresponding rule-based configuration.

Comparisons should use equivalent weather scenarios and cost assumptions.

### 11.2 Evaluation Metrics

| Metric                      | Purpose                                                         |
| --------------------------- | --------------------------------------------------------------- |
| Estimated total travel time | Compare voyage efficiency                                       |
| Total route distance        | Measure route length                                            |
| Weather-related route cost  | Compare environmental exposure under the model                  |
| Number of reroutes          | Measure route stability                                         |
| Rerouting computation time  | Measure responsiveness                                          |
| Missed beneficial reroutes  | Identify cases where the policy failed to react                 |
| Unnecessary reroutes        | Identify changes that did not produce meaningful benefits       |
| ML prediction error         | Evaluate speed prediction accuracy where reference labels exist |

The project should report actual measured results and document simulation assumptions.

### 11.3 Scenario-Based Testing

Use a small but varied collection of test cases:

* Stable weather with no rerouting expected.
* Deteriorating weather along the current route.
* An alternative route becoming more efficient.
* Weather changes that do not justify rerouting.
* Different vessel profiles.
* Different departure and destination pairs.

The existing fixed voyage evaluation set can be reused as a starting point.

### 11.4 Evaluation Principles

* Do not claim real-world fuel savings without appropriate validation.
* Do not treat synthetic simulation results as real maritime performance.
* Compare ML with a transparent baseline.
* Record the conditions under which each result was obtained.
* Separate algorithm correctness from model quality.

### 11.5 Threshold-Based Rerouting Baseline (measured 2026-10-03)

`python -m src.evaluate_rerouting` runs 5 voyages × 5 vessel profiles × 6 simulated weather scenarios (`typical` base weather, default thresholds). Each combination runs as a pair: the same voyage with rerouting enabled and disabled. Outputs: `data/rerouting_eval/`. Full analysis: `docs/loop-engineering/EXPERIMENTS.md` EXP-006.

* 150 combinations: 144 valid, 6 draft-infeasible (VLCC on Kandla → Cochin passes through 16 m of water; draft 20.5 m), 0 failed.
* Of 144 valid pairs: 88 faster with rerouting, 50 unchanged (all stable and minor-change runs, plus 2 near-threshold cases), 6 slower. Mean simulated travel-time change −8.0% (median −5.0%; range −30.4% to +8.4%).
* All 6 slower cases occur with a storm that moves every step: decisions that were cheaper under the weather at decision time turned out worse once the storm moved.

This is the baseline that any ML-based rerouting decision (§8.2) must be compared against. The results are model-based simulations, not real-world performance.

---

## 12. Application and Visualization

The existing user interface should be extended to demonstrate the dynamic behavior of the routing system.

### Expected functionality

* Select departure and destination ports.
* Choose a vessel profile.
* Generate an initial route.
* Start a simulated voyage.
* Apply or advance weather updates.
* Show the current vessel position.
* Display when a rerouting condition is triggered.
* Show the original and alternative routes.
* Present route metrics before and after rerouting.
* Explain the reason for a route change.

The UI is intended for demonstration and analysis. It does not need to provide sophisticated operational control or real-time vessel tracking.

### 12.1 Implemented: Simulation Lab (2026-10-03)

The Flask app has three modes: **Route planning**, **Voyage replay** (whole voyage in one request, `/api/simulate`) and **Simulation lab** (interactive).

* **Engine:** `rerouting.Voyage` is a step-by-step voyage. `simulate()` and the lab both use it, so lab decisions are the batch engine's decisions; this is tested, and a lab preset reproduces the evaluated scenario exactly. A lab session runs the configured voyage and a no-rerouting twin under identical weather.
* **Weather:** the applied weather is the base sea state plus a list of disturbances (Gaussian change of significant wave height: peak Δ, radius σ). Users add, move, resize, re-intensify or remove disturbances. Edits are **pending** until **Apply now** or the next step; only applied weather reaches routing, and the map shows the two differently. Base data are never modified. Wave period and direction are not changed.
* **Step order:** apply pending and scheduled weather, then evaluate the active route and maybe reroute (unchanged controller), then advance the vessel.
* **Traceability:** each evaluation is logged with its triggers, active-route cost and hours, whether a search ran, the alternative and its gain, and the decision and reason. Every reroute marker comes from a logged adoption.
* **Sessions:** in memory, in one server process; up to 8, expiring after 30 minutes idle. Steps carry `expected_step`, so a repeated request cannot advance twice.
* **Safety and reroute visibility (2026-10-06):**
  - **Lab:** a red overlay can show water too shallow for the selected vessel. When the route changes, the replaced plan stays visible (dashed amber) from the reroute point, and the vessel marker advances along the backend's sailed cells between steps, so it never jumps off its track.
  - **Timeline:** each reroute's cause, corridor shift, length change and heading change.
  - **Infeasible voyages:** reported with their reason in the lab, in route planning and in replay.
  - **Not modelled:** turning and manoeuvring. Adoption turns are a decision property, not a ship-dynamics one (median 19°, occasional > 90° in moving-storm cases; EXP-008).
* **Demonstration scenarios:** deterministic disturbance schedules (`weather_sim.PRESETS`). Five reuse the evaluated scenarios' parameters; two are added: "storm over route" and "no useful alternative".

---

## 13. Technology and Infrastructure

Nautilus should preserve its existing technology stack and infrastructure wherever practical.

### Existing foundations

* Python-based routing and data-processing components.
* Existing Flask API.
* Existing Streamlit interface.
* Existing geospatial and weather-processing pipeline.
* Docker-based execution.
* Environment-based configuration.

The implementation should avoid unnecessary rewrites or additional services.

### Docker and Offline Operation

Docker is an established part of the project.

The current organization includes:

* `docker/Dockerfile`
* `docker/docker-compose.yml`
* Root-level `.dockerignore`
* `DOCKER.md`
* `.env.example`
* Centralized configuration in `config.py`

The system should continue to support reproducible builds and local evaluation.

Offline operation should be preserved for workflows that rely on locally available data. Features requiring external weather services should degrade gracefully when those services are unavailable.

### Configuration and Secrets

* Keep secrets outside source control.
* Use `.env` for local secret configuration.
* Maintain `.env.example` with safe placeholders.
* Avoid hardcoding external API keys.
* Preserve the Docker-specific host and port configuration required for container reachability.

---

## 14. Development Principles

The project should use a goal-oriented, iterative engineering workflow.

### Working Principles

* Use the source of truth as project memory and architectural guidance.
* Avoid creating unnecessary layers of task-management documentation.
* Define clear goals and constraints before implementation.
* Allow coding agents to inspect the repository and determine appropriate implementation details.
* Validate changes with relevant tests and actual execution.
* Update project documentation when significant behavior or architecture changes.
* Avoid large rewrites without demonstrated need.
* Prefer simple solutions that satisfy the current requirements.

### Engineering Guardrails

* Preserve existing functionality unless a change is justified.
* Do not introduce unnecessary dependencies.
* Keep routing, weather evaluation, ML prediction, and rerouting decisions logically separated.
* Maintain a transparent rule-based baseline.
* Keep ML outputs from bypassing navigability checks.
* Do not claim a feature is implemented until it has been verified.
* Document known limitations and failed experiments honestly.

### Project Records

`docs/loop-engineering/` holds the working records: current state, tasks, decisions, blockers, experiments, validation and session history. Its `README.md` gives the reading order and a short maintenance convention. Update these records after meaningful implementation goals, not after trivial edits.

---

## 15. Known Limitations and Technical Risks

The following limitations should be considered during implementation.

### Dynamic Routing

* Current-position route generation is implemented and tested (`Router.search` from any navigable cell, `RouteResult.cost`, `Router.path_cost`).
* A threshold-based rerouting loop runs in simulation only (`src/rerouting.py`, `src/weather_sim.py`, `python -m src.rerouting`): weather updates are synthetic wave-height perturbations, and vessel progress is a fixed number of grid cells per step, not time-based.
* Rerouting decisions compare routing cost (km × weather/ML speed multiplier). Reported travel time follows §10.1 and is not used for decisions.
* Rerouting is exposed in the Flask interface ("Voyage replay" and "Simulation lab" modes), not in Streamlit.

### Machine Learning

* The current speed model is trained using synthetic data.
* Real-world generalization has not been established.
* The quality of an ML rerouting decision model will depend on simulation design and label quality.

### Weather Data

* Existing weather processing does not automatically provide a complete live update mechanism.
* Weather updates may be simulated in the initial implementation.
* Missing and stale data require basic handling.

### Route Evaluation

* ETA and route cost were inconsistent until 2026-10-03 (constant 18 kn ETA); now defined in §10.1. Travel time is only as good as the synthetic-data speed model.
* Depth feasibility uses GEBCO depths relative to mean sea level at 0.05° resolution, plus a 20% under-keel margin. It ignores tides and chart datum, local surveys and squat, and it is not a navigational chart. Port approaches are represented by the nearest navigable cell, which can be far offshore (§5.3).
* Routes tend to follow the 22 km clearance edge on coastal voyages (cost-optimal paths ride the constraint). This is legitimate under the constraint. The soft coastal preference that would reduce it is off by default because of its rough-weather wave-exposure cost (EXP-008).
* Rerouting decisions assume the current weather persists. Under moving weather they can make a voyage slower (§11.5). Large corridor changes are mostly genuinely beneficial: a naive route-change penalty reduced them only by giving up time savings (EXP-008).
* Simulation-lab sessions are held in one server process's memory; they are lost on restart and are not shared across workers or replicas. The lab's "remaining" and "projected" hours assume the current weather persists.
* Dynamic and static routes must be compared under equivalent assumptions.
* Simulation results may not reflect actual maritime operations.

### Operational Limitations

Nautilus is a prototype decision-support system. Its route recommendations are not certified for real-world vessel operation and must not be treated as a substitute for professional navigation, official maritime information, or established safety procedures.

---

## 16. Implementation Roadmap

Development should proceed in the following order.

### Phase 1 — Rerouting Foundation

**Status:** Done (2026-10-03). "Verify ETA and cost consistency" was completed together with Phase 3's ETA alignment (§10.1).

**Objective:** Make the existing routing engine capable of recalculating routes during a voyage.

Tasks:

* Verify arbitrary start-position routing.
* Support routing from the current simulated position.
* Preserve destination and navigability constraints.
* Ensure route results expose the information needed for comparison.
* Verify ETA and cost consistency.

**Completion condition:** The system can generate and compare a new route from an intermediate position on an existing voyage.

### Phase 2 — Weather Updates and Rerouting Triggers

**Status:** Done in simulation (2026-10-03).

**Objective:** Make rerouting respond to changing environmental conditions.

Tasks:

* Introduce controlled weather updates.
* Evaluate the remaining current route.
* Implement configurable weather and cost thresholds.
* Generate alternatives when triggers are met.
* Avoid unnecessary repeated rerouting.

**Completion condition:** A controlled weather scenario can trigger a reroute, while a stable scenario does not cause unnecessary route changes.

### Phase 3 — ML Speed Prediction Integration

**Status:** Mostly done (2026-10-03). The ML model drives weather-aware costs and all reported travel times. Behaviour across vessel profiles is tested, and the metric semantics are documented (§10.1). Open: retraining or re-pinning the model artifact (scikit-learn version mismatch).

**Objective:** Use the existing ML model consistently across route planning and evaluation.

Tasks:

* Inspect and validate the current prediction interface.
* Integrate predicted speed into route cost calculations.
* Align initial routing, alternative routing, and ETA evaluation.
* Test behavior across available vessel profiles.
* Document model limitations.

**Completion condition:** Route evaluation consistently uses the configured ML speed model and produces reproducible results.

### Phase 4 — Evaluation and Visualization

**Status:** Done (2026-10-03). Simulated voyages and route changes can be shown in the Flask UI. Static-vs-dynamic evaluation runs across all voyages, vessels and scenarios (§11.5). Not covered: `rough` base weather and threshold sensitivity.

**Objective:** Demonstrate and measure the rerouting workflow.

Tasks:

* Extend the existing voyage evaluation.
* Add weather-change scenarios.
* Compare static and dynamic routing.
* Record route metrics and rerouting decisions.
* Display route changes in the existing UI.

**Completion condition:** A user can observe a complete simulated voyage with at least one weather-driven rerouting scenario and inspect the resulting metrics.

### Phase 5 — Experimental ML Rerouting Decisions

**Status:** Not started (optional).

**Objective:** Determine whether ML can improve rerouting decisions beyond simple thresholds.

Tasks:

* Establish a rule-based baseline.
* Generate training examples from simulated scenarios.
* Define a clear rerouting objective.
* Train a manageable classifier or other suitable model.
* Compare the model against the baseline on held-out scenarios.
* Retain the ML decision component only if it offers a measurable benefit.

**Completion condition:** The experiment produces a documented comparison. The ML decision model is optional and is not required for the project to be considered complete.

---

## 17. Definition of Success

Nautilus will be considered successful when it demonstrates the following capabilities:

* Generates an initial route between supported ports.
* Tracks progress through a simulated voyage.
* Responds to changing weather conditions.
* Recalculates routes from the current position.
* Compares alternative routes using consistent cost assumptions.
* Uses ML-based vessel speed estimation as part of route evaluation.
* Avoids unnecessary rerouting under stable conditions.
* Demonstrates improved or otherwise clearly characterized behavior relative to static routing.
* Provides a visual explanation of route changes.
* Runs reproducibly using the established containerized environment.

An experimental ML rerouting decision model may provide additional value, but its absence does not invalidate the core project.

Success should be demonstrated through actual execution and recorded evaluation results rather than assumptions or intended behavior.

---

## 18. Final Project Direction

Nautilus is a **weather-aware dynamic ship rerouting system enhanced by machine learning**.

The project should prioritize:

1. **Rerouting functionality** — The ability to react to weather changes and recalculate routes from the vessel's current position.
2. **ML integration** — Using vessel speed prediction to improve route estimation and optionally experimenting with ML-based rerouting decisions.
3. **Evaluation and demonstration** — Showing when rerouting helps, when it does not, and how the system behaves across controlled scenarios.
4. **Practical engineering** — Preserving the existing routing foundation, Docker infrastructure, and manageable development workflow.

The guiding principle is to build a complete and understandable dynamic rerouting system before expanding into advanced algorithms or complex ML research.

The primary objective is not to make Nautilus as complex as possible. It is to make its core rerouting and ML features functional, measurable, and technically sound.
