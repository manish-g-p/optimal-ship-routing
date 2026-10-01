# Nautilus — Project Source of Truth

**Project:** Nautilus
**Project Type:** Marine Routing and Decision-Support System
**Primary Scope:** Waters around India / Indian Ocean region
**Document Status:** Authoritative
**Last Updated:** October 2026

---

# 1. Purpose of This Document

This document is the **primary reference for the entire Nautilus project**.

It defines:

* What Nautilus is
* What problem it solves
* What the current project goals are
* What functionality must be implemented
* How routing algorithms should be structured
* How algorithms should be compared
* How the system should determine which algorithm is appropriate for a scenario
* How the project should be evaluated
* How the project should be deployed
* How Docker and remote development fit into the architecture
* How offline operation should work
* What is currently in scope and out of scope
* How future development should proceed

If another document, old implementation plan, or previous discussion conflicts with this document, **this document takes precedence unless explicitly superseded by a newer source-of-truth document**.

---

# 2. Current Project Definition

Nautilus is a **marine route-planning and decision-support system** designed to evaluate and compare different routing algorithms under varying marine conditions.

The system operates over a predefined geographical region around India and uses:

* Bathymetry
* Navigable-water constraints
* Weather/wave information
* Vessel characteristics
* Port locations
* Routing algorithms
* Safety constraints
* Evaluation metrics

The core purpose is not simply to find one route.

The system must be able to answer:

> **Given a particular marine routing scenario, which routing algorithm is most appropriate, and what measurable evidence supports that choice?**

Therefore, Nautilus has two related functions:

### Route Generation

Generate a feasible route between two locations.

### Algorithm Decision Support

Run and compare multiple routing algorithms and determine which algorithm is most suitable for the characteristics and objectives of the current scenario.

The second function is a major part of the project's research contribution.

---

# 3. Project Goals

The current project has five primary goals.

## Goal 1 — Multiple Routing Algorithms

Nautilus must support multiple routing algorithms rather than relying on a single routing strategy.

The algorithms should represent meaningfully different approaches to pathfinding, such as:

* Distance-based routing
* Heuristic-guided routing
* Bidirectional search
* Weather-aware routing
* Risk-constrained or multi-objective routing

The exact final algorithm set will be determined during implementation and experimentation.

The purpose is not to maximize the number of algorithms.

The purpose is to provide **meaningfully different routing strategies that can be experimentally compared**.

---

## Goal 2 — Scenario-Based Routing

A routing algorithm cannot be judged independently of the situation in which it is used.

Therefore, Nautilus must support different routing scenarios involving combinations of:

* Weather conditions
* Geographic characteristics
* Voyage distance
* Vessel characteristics
* Safety constraints
* Optimization objectives

Examples include:

* Calm-weather routing
* Rough-weather routing
* Safety-critical routing
* Long-distance routing
* Constrained coastal routing
* Different vessel profiles

The scenario determines what properties of a route are important.

---

## Goal 3 — Evidence-Based Algorithm Selection

Nautilus must provide measurable evidence explaining why an algorithm is appropriate for a given scenario.

The system must not simply display:

> "Algorithm X is the best."

Instead, it should establish:

1. What the scenario requires.
2. Which metrics matter for that scenario.
3. Which constraints must be satisfied.
4. How each algorithm performs.
5. Which algorithms produce feasible routes.
6. How the feasible algorithms compare against the scenario objectives.
7. Why the selected algorithm is appropriate according to those predefined criteria.

The recommendation must therefore be **derived from experimental evidence and explicit criteria**, not hardcoded preference.

---

## Goal 4 — Remote and Containerized Development

Nautilus must be capable of being developed and executed on a remote server where the developer may not have permission to install system-wide development tools.

Docker is therefore a core infrastructure requirement.

The intended development model is:

```text
Developer Laptop
       |
       | Git / SSH
       v
Remote Server
       |
       v
Docker Container
       |
       +-- Python
       +-- Dependencies
       +-- Nautilus source
       +-- Development tools
       +-- Test environment
```

The remote server becomes the primary development/runtime environment.

The local laptop should not need to contain the complete Nautilus development stack.

---

## Goal 5 — Offline-Capable Marine Deployment

Nautilus is intended for a marine-industry context where continuous internet connectivity cannot be assumed.

The final system therefore must minimize its dependence on internet connectivity.

Normal route planning should work using locally available:

* Application code
* Processed geographic data
* Weather datasets/scenarios
* Port data
* Vessel data
* Routing algorithms
* Configuration

The internet may be used for optional data updates or future functionality, but **basic route planning must not depend on an active internet connection**.

---

# 4. Project Research Question

The current research direction is:

> **How do different pathfinding and weather-aware routing algorithms perform under varying marine operating conditions, and which algorithm provides the most appropriate trade-off between route efficiency, environmental exposure, computational cost, and safety constraints for each scenario?**

This research question drives the algorithm design and evaluation framework.

The project is therefore not simply a software implementation.

It is also an **experimental comparison of routing strategies**.

---

# 5. Geographic Scope

Nautilus currently targets waters around India.

The existing geographical configuration is:

```text
Latitude:
0°N → 27°N

Longitude:
50°E → 100°E
```

This covers a large portion of the Indian Ocean and surrounding waters relevant to the project's intended use cases.

Nautilus is **not currently intended to be a global marine routing system**.

---

# 6. Existing Geographic Grid

The routing system operates on a discrete geographic grid.

The current grid resolution is:

```text
0.05°
```

The grid is generated from bathymetry data.

The system identifies navigable cells using:

* Water depth
* Minimum required depth
* Distance from land/coastline
* Connected-component analysis

The current minimum depth threshold is approximately:

```text
10 metres
```

The current coast/boundary safety buffer is approximately:

```text
22 km
```

These values remain configuration parameters rather than universal maritime safety rules.

They are project-level modelling assumptions and must not be presented as actual maritime regulations.

---

# 7. Data Pipeline

The general data pipeline is:

```text
Raw Data
   |
   v
Preprocessing
   |
   v
Processed Geographic / Weather Data
   |
   v
In-Memory Grid and Weather Objects
   |
   v
Routing Engine
   |
   v
Route Result
   |
   v
Evaluation / Visualization
```

The system should prefer processed datasets during normal operation.

Large raw datasets should not need to be loaded every time a route is calculated.

---

# 8. Existing Geographic Data

Bathymetry is derived from GEBCO data.

The preprocessing stage:

1. Loads the bathymetry dataset.
2. Restricts it to the project region.
3. Resamples/coarsens it to the routing resolution.
4. Determines navigable cells.
5. Applies the coast/boundary buffer.
6. Determines connected navigable regions.
7. Generates the processed grid.

The resulting processed grid is used by the routing algorithms.

---

# 9. Weather Data

The current project uses wave-related weather information.

Important variables include:

* Significant wave height (`swh`)
* Mean wave period (`mwp`)
* Mean wave direction (`mwd`)

Weather information can influence route cost.

The current system supports static weather scenarios such as:

* Typical conditions
* Rough conditions

The system currently does not require live weather access for its core routing functionality.

This is important for offline operation.

---

# 10. Vessel Model

Nautilus contains predefined vessel profiles.

Current examples include:

* Bulk Carrier
* Container Ship
* Crude Oil Tanker
* General Cargo
* LNG Carrier

A vessel profile can contain properties such as:

* Service speed
* Length
* Draft
* Wave sensitivity

Not every vessel property is currently used by every routing calculation.

Any property that is not currently used must not be presented as if it affects routing.

Future work may improve vessel-specific routing models.

---

# 11. Routing Engine

The routing engine is the central computational component of Nautilus.

Its responsibility is to:

1. Receive a routing problem.
2. Determine the start and destination cells.
3. Traverse the navigable grid.
4. Calculate movement costs.
5. Apply relevant environmental/safety constraints.
6. Search for a route.
7. Produce a standardized route result.

The routing engine should remain independent from:

* Web UI
* Flask
* Streamlit
* Docker
* Presentation logic

This separation allows the routing algorithms to be tested independently.

---

# 12. Common Routing Interface

All routing algorithms should eventually conform to a common interface.

Conceptually:

```text
RoutingProblem
    |
    +-- Start
    +-- Goal
    +-- Grid
    +-- Weather
    +-- Vessel
    +-- Scenario
    +-- Constraints
    |
    v
RoutingAlgorithm
    |
    +-- Dijkstra
    +-- A*
    +-- Bidirectional Dijkstra
    +-- Bidirectional A*
    +-- Weather-aware algorithms
    +-- Risk-constrained algorithms
    |
    v
RouteResult
```

This is important because the evaluation framework should not need separate logic for every algorithm.

Every algorithm should produce comparable output.

---

# 13. Standard Route Result

Every routing algorithm should return a common result structure.

The result should contain, where applicable:

```text
Algorithm
Route found
Route cells
Latitude/longitude path
Distance
Estimated travel time
Maximum wave exposure
Mean wave exposure
Minimum coast clearance
Expanded/search states
Runtime
Safety validity
Constraint violations
```

Additional metrics may be added later.

The important principle is:

> **The same metrics must be collected for every algorithm whenever they are applicable.**

This makes comparison meaningful.

---

# 14. Current and Planned Routing Algorithms

The project already contains:

## Dijkstra

Dijkstra acts as the classical baseline.

It searches for the minimum accumulated routing cost without using a destination-directed heuristic.

Its importance is that it provides a reference against which other search algorithms can be evaluated.

---

## A*

A* extends the search using a heuristic that estimates remaining cost to the destination.

Its primary expected benefit is reduced search effort compared with Dijkstra while preserving the intended route objective under appropriate cost/heuristic assumptions.

The current implementation already provides a weather-aware A* variant.

---

## Bidirectional Dijkstra

This algorithm searches from both:

```text
Start → Goal
Goal → Start
```

The searches meet somewhere between the endpoints.

The purpose of including it is to determine whether bidirectional search can reduce computational effort relative to conventional Dijkstra.

---

## Bidirectional A*

This combines:

* Bidirectional search
* Heuristic guidance

It provides another meaningful algorithmic comparison rather than simply being another implementation of the same search strategy.

---

## Weather-Aware Dijkstra

A weather-aware Dijkstra implementation can use environmental conditions as part of the edge cost.

Conceptually:

```text
Cost =
Distance × Weather Multiplier
```

This allows the system to compare:

```text
Shortest-distance routing
vs.
Weather-aware routing
```

---

## Weather-Aware A*

Weather-aware A* combines:

* Environmental routing cost
* Heuristic-guided search

The existing Nautilus implementation already provides this general approach.

---

## Risk-Constrained / Multi-Objective Routing

A future routing strategy may explicitly treat safety conditions as constraints.

For example:

```text
Maximum wave <= threshold
Minimum coast clearance >= threshold
```

Among routes satisfying the constraints, the system can optimize a chosen objective such as travel time.

This is potentially one of the most important higher-level routing strategies because it changes the problem from:

> "Find the cheapest route."

to:

> "Find a feasible safe route and optimize within the feasible set."

The exact mathematical formulation must be established before implementation.

---

# 15. Algorithm Development Rule

New algorithms must not be added simply to increase the algorithm count.

Every new algorithm should have a reason for existing.

Before implementing an algorithm, define:

1. What search strategy does it introduce?
2. What problem is it expected to solve?
3. What scenario might benefit from it?
4. What metric should demonstrate its advantage?
5. What baseline should it be compared against?

This prevents the project from becoming a collection of unrelated algorithms.

---

# 16. Routing Cost vs Algorithm

An important distinction must be maintained.

There are two different concepts:

### Search Algorithm

Examples:

```text
Dijkstra
A*
Bidirectional Dijkstra
Bidirectional A*
```

These determine **how the search space is explored**.

### Routing Cost Model

Examples:

```text
Distance
Weather-adjusted distance
Risk-aware cost
```

These determine **what makes one route more desirable than another**.

These should be kept conceptually separate.

For example:

```text
A*
 +
Weather Cost Model
```

is different from:

```text
Dijkstra
 +
Weather Cost Model
```

This separation is essential for meaningful experiments.

---

# 17. Scenario Framework

A scenario represents a specific routing situation.

A scenario should define:

```text
Scenario
├── Start
├── Destination
├── Vessel
├── Weather condition
├── Geographic context
├── Safety constraints
├── Primary objective
└── Secondary metrics
```

For example:

```text
Scenario:
Rough Weather / Long Voyage

Start:
Cochin

Destination:
Dubai

Vessel:
General Cargo

Weather:
Rough

Constraint:
Maximum allowable wave exposure

Primary objective:
Minimize travel time among feasible routes

Secondary:
Search efficiency
Distance
Environmental exposure
```

This makes experiments reproducible.

---

# 18. Scenario Categories

The initial scenario library should cover several distinct conditions.

## Scenario A — Calm Weather

Weather exposure is relatively low.

The main objective may be:

* Travel time
* Distance
* Computational efficiency

This provides a baseline where weather-aware routing may have less influence.

---

## Scenario B — Rough Weather

Weather exposure becomes significant.

Important metrics include:

* Maximum wave
* Mean wave
* Travel time
* Distance

This scenario tests whether weather-aware algorithms meaningfully alter route selection.

---

## Scenario C — Safety-Critical Routing

Safety constraints become dominant.

For example:

```text
Maximum wave <= defined threshold
```

Algorithms producing invalid routes should be marked infeasible.

The comparison should then focus on feasible solutions.

---

## Scenario D — Long-Distance Routing

The route is sufficiently long that computational search efficiency becomes important.

Metrics such as:

* Runtime
* Expanded cells
* Route quality

become particularly relevant.

---

## Scenario E — Geographically Constrained Routing

The navigable region is narrow or contains obstacles/coastal restrictions.

This tests how algorithms behave when the search space is constrained.

---

## Scenario F — Vessel-Specific Routing

Different vessel profiles are tested under the same environmental conditions.

This allows the project to investigate whether the appropriate routing strategy changes with vessel characteristics.

---

# 19. Evaluation Framework

The evaluation framework is one of the most important components of the new project.

The basic process is:

```text
Scenario
   |
   v
Run every eligible algorithm
   |
   v
Collect identical metrics
   |
   v
Check safety constraints
   |
   v
Separate feasible/infeasible routes
   |
   v
Compare feasible algorithms
   |
   v
Generate evidence
   |
   v
Determine suitable algorithm
```

The evaluation system should be automated.

A developer should be able to run an experiment without manually collecting results from the UI.

---

# 20. Evaluation Metrics

The initial metrics should include:

## Route Efficiency

### Distance

Total route length in kilometres.

### Estimated Travel Time

Predicted route travel time under the project's current speed/weather assumptions.

ETA calculations must be consistent across algorithms.

---

## Environmental Exposure

### Maximum Wave

Highest wave exposure encountered on the route.

### Mean Wave

Average wave exposure across the route.

Additional weather metrics may be added later.

---

## Computational Performance

### Runtime

Time required to calculate the route.

### Expanded Cells / Search States

Number of grid states explored during routing.

This is particularly useful for comparing Dijkstra, A*, and bidirectional algorithms.

---

## Safety

### Minimum Coast Distance

Minimum distance from the route to the restricted coastal boundary.

### Constraint Violations

Whether the route violates any scenario-specific safety constraints.

---

## Reliability

### Route Found

Whether a valid route exists.

### Safety Validity

Whether the resulting route satisfies all required constraints.

---

# 21. What Does "Best Algorithm" Mean?

The project must never define "best" as a universal property.

There is no single algorithm that must be considered best for every scenario.

Instead:

> **Best means most suitable according to the predefined objectives and constraints of the scenario.**

For example:

### Scenario objective

Minimize computational effort while maintaining the same route quality.

Relevant evidence:

```text
Runtime
Expanded cells
Distance
ETA
```

Another scenario might be:

### Scenario objective

Minimize environmental exposure while remaining feasible.

Relevant evidence:

```text
Maximum wave
Mean wave
ETA
Distance
Constraint validity
```

The evaluation framework must define these priorities **before** examining the results where possible.

This reduces the risk of selecting criteria after seeing which algorithm performs well.

---

# 22. Evidence-Based Recommendation

The recommendation system should work conceptually as follows:

```text
Scenario Definition
        |
        v
Define objective + constraints
        |
        v
Run algorithms
        |
        v
Reject infeasible routes
        |
        v
Compare feasible routes
        |
        v
Generate recommendation
        |
        v
Explain using measured metrics
```

The system should produce explanations such as:

> Algorithm A produced a feasible route with lower environmental exposure while maintaining comparable travel time. It also required fewer search expansions than the baseline.

The explanation must reference measured results.

It must not simply state that the algorithm is better without evidence.

---

# 23. Avoid Arbitrary Universal Scores

The system should not initially combine every metric into one arbitrary weighted score.

For example, avoid an unexplained formula such as:

```text
Score =
0.4 × ETA
+ 0.3 × Safety
+ 0.2 × Runtime
+ 0.1 × Distance
```

unless those weights have a defensible research justification.

Instead, use:

1. Hard constraints
2. Primary objective
3. Secondary metrics

This makes the experimental conclusions easier to defend.

---

# 24. Experimental Design

Each experiment should be reproducible.

An experiment should record:

```text
Experiment ID
Scenario
Start
Destination
Vessel
Weather
Algorithms tested
Constraints
Metrics
Results
Observations
Conclusion
```

The existing five-voyage evaluation can remain as a **classical routing baseline dataset**.

It should not be discarded simply because the project direction changed.

---

# 25. Existing Baseline

The completed baseline experiment established that:

* All five existing evaluation voyages successfully produced routes.
* A* expanded substantially fewer cells than Dijkstra in those tests.
* The previous ETA implementation was incorrect because it used a constant-speed distance calculation.
* The ETA implementation was subsequently corrected to use the accumulated routing cost.
* The corrected ETA did not change route selection or other core route metrics.

These results form the historical baseline for the routing system.

Future experiments should preserve this baseline where appropriate.

---

# 26. ETA Principle

ETA must correspond to the actual cost assumptions used to evaluate the route.

The routing system should not:

```text
Select route using weather-aware cost
        ↓
Report ETA using unrelated constant-speed distance
```

Instead, the route evaluation and ETA calculation must use consistent assumptions.

Future vessel-specific improvements may refine this further.

---

# 27. Remote Development Architecture

The development environment must support remote execution.

The intended workflow is:

```text
Developer Laptop
      |
      | Git / SSH
      v
Remote Server
      |
      v
Docker
      |
      v
Nautilus Development Container
```

The remote server does not need a global installation of:

* Python
* Project libraries
* Numerical libraries
* Development dependencies

provided the required container runtime is available.

---

# 28. Docker Objectives

Docker must provide:

### Reproducible Environment

The same Python/dependency environment can be recreated on another machine.

### Dependency Isolation

Nautilus dependencies remain inside the container.

### Remote Development

The project can be executed on the remote server without installing the development stack globally.

### Deployment Consistency

The environment used for development can be related to the environment used for testing/deployment.

---

# 29. Docker Development Workflow

The intended workflow is:

```text
Developer changes code
        |
        v
Git commit
        |
        v
GitHub
        |
        v
Remote server
        |
        v
Build / pull Docker image
        |
        v
Run Nautilus container
        |
        v
Test / develop
```

Docker images should eventually be pushed to a container registry such as Docker Hub.

Example:

```text
Nautilus Source
      ↓
Docker Build
      ↓
Nautilus Image
      ↓
Docker Hub
      ↓
Remote Server
      ↓
docker pull
      ↓
Run
```

---

# 30. Development Image vs Deployment Image

The project should distinguish between:

### Development Container

Contains:

* Development dependencies
* Debugging tools
* Test tools
* Source code/workspace support

### Production/Distribution Container

Contains only what is necessary to run Nautilus.

This prevents the final deployment artifact from unnecessarily containing development tooling.

---

# 31. Remote Development Milestone

Docker setup should be considered successful when the following works:

```text
Remote Server
   ↓
Pull Nautilus image
   ↓
Start container
   ↓
Enter development/runtime environment
   ↓
Run existing evaluation
   ↓
Run routing system
   ↓
Modify/test code
```

This should be demonstrated before major routing development continues.

---

# 32. Offline Deployment Architecture

The final application should not require an internet connection for normal routing.

Conceptually:

```text
                 NAUTILUS
                    |
          ┌─────────┴─────────┐
          |                   |
       Local UI          Local Engine
                              |
                     ┌────────┼────────┐
                     |        |        |
                   Grid    Weather   Port/Vessel
                   Data     Data       Data
```

All essential routing data should be available locally.

---

# 33. Internet Dependency Policy

Internet access should be considered **optional** for core functionality.

The following should work offline:

* Opening Nautilus
* Selecting ports
* Selecting a vessel
* Selecting a scenario
* Running routing algorithms
* Comparing algorithms
* Viewing routes
* Viewing evaluation metrics
* Viewing algorithm recommendations

Future online features such as:

* Live weather
* Dataset updates
* Software updates

may exist, but they must not make the core application unusable when connectivity is lost.

---

# 34. Live Weather

Live weather is not a requirement for the first offline-capable version.

The existing live weather functionality should not become a mandatory dependency.

Static/preprocessed weather scenarios are preferred for:

* Reproducible experiments
* Offline operation
* Algorithm comparison
* Academic evaluation

Live weather can be considered a future enhancement.

---

# 35. Offline Distribution

The final user-facing application should eventually be distributed in a form that does not require the user to understand the development environment.

The target experience is approximately:

```text
Download Nautilus
       ↓
Install / Extract
       ↓
Launch
       ↓
Use routing system
```

The exact packaging mechanism should be selected after the core application is stable.

Possible approaches can be evaluated later, but the architectural requirement is fixed:

> **Normal operation must be locally executable without continuous internet connectivity.**

---

# 36. User Interface

The UI should eventually expose four major functions.

## Route Planning

User selects:

* Start
* Destination
* Vessel
* Weather/scenario

and generates routes.

---

## Algorithm Selection

The user can explicitly inspect individual algorithms.

For example:

```text
Dijkstra
A*
Bidirectional Dijkstra
Bidirectional A*
Weather-aware Dijkstra
Weather-aware A*
...
```

---

## Algorithm Comparison

The user can compare multiple algorithms for the same scenario.

Example:

```text
Algorithm          Distance    ETA    Max Wave    Expansions
-------------------------------------------------------------
Dijkstra           ...
A*                 ...
Bi-Dijkstra        ...
Bi-A*              ...
Weather Dijkstra   ...
Weather A*         ...
```

---

## Scenario Recommendation

The system can identify the algorithm that best satisfies the predefined scenario criteria.

The UI should also explain the evidence behind the recommendation.

---

# 37. Current Software Architecture

The existing repository contains components such as:

```text
config.py
server.py
app.py

src/
├── evaluate.py
├── geo.py
├── grid.py
├── live_weather.py
├── ml_model.py
├── ports.py
├── preprocess.py
├── routing.py
├── vessel.py
└── weather.py

web/
```

The exact directory structure may evolve as the routing architecture is refactored.

The important architectural boundaries are:

```text
Data
 ↓
Grid / Weather
 ↓
Routing
 ↓
Evaluation
 ↓
Recommendation
 ↓
UI
```

---

# 38. Recommended Future Structure

The project may evolve toward a structure similar to:

```text
src/
│
├── routing/
│   ├── base.py
│   ├── dijkstra.py
│   ├── astar.py
│   ├── bidirectional_dijkstra.py
│   ├── bidirectional_astar.py
│   ├── weather_dijkstra.py
│   ├── weather_astar.py
│   └── constrained.py
│
├── evaluation/
│   ├── scenarios.py
│   ├── runner.py
│   ├── metrics.py
│   ├── comparison.py
│   └── recommendation.py
│
├── data/
│
├── grid.py
├── weather.py
├── vessel.py
├── ports.py
└── geo.py
```

This is a **target architectural direction**, not a requirement to immediately reorganize the entire repository.

Changes should be made incrementally.

---

# 39. Project Implementation Order

The implementation should proceed in the following order.

---

## Phase 1 — Update Project State

First update all planning documents to reflect this source of truth.

Remove RL from the active roadmap.

Keep historical RL documentation only where necessary to preserve project history.

Do not create new RL implementation tasks.

### Completion condition

All active project documentation consistently describes the new routing/evaluation/deployment direction.

---

# Phase 2 — Dockerize the Development Environment

Create:

* Dockerfile
* Development container configuration
* Dependency installation
* Container startup process
* Environment configuration
* Docker Compose if useful
* Docker Hub image workflow

### Goal

Run Nautilus successfully on the remote server entirely through Docker.

### Completion condition

The existing evaluation command can execute inside the remote container.

---

# Phase 3 — Stabilize the Existing Routing System

Before adding many algorithms:

* Validate the corrected ETA.
* Complete TASK-003.
* Establish the common route result.
* Establish common metrics.
* Separate routing logic from presentation.
* Establish safety validation.

### Goal

Create a reliable foundation for algorithm comparison.

---

# Phase 4 — Create the Algorithm Interface

Introduce the common abstraction for routing algorithms.

Every algorithm must:

1. Accept the same routing problem representation.
2. Produce the same route-result representation.
3. Expose comparable metrics.
4. Remain independently testable.

### Goal

Adding a new algorithm should not require rewriting the evaluation framework.

---

# Phase 5 — Implement Additional Algorithms

Implement algorithms incrementally.

Recommended order:

```text
Dijkstra
   ↓
A*
   ↓
Bidirectional Dijkstra
   ↓
Bidirectional A*
   ↓
Weather-aware Dijkstra
   ↓
Weather-aware A*
   ↓
Risk-constrained / multi-objective approach
```

The exact ordering may change based on experimental findings.

Each algorithm should be introduced through its own development loop.

---

# Phase 6 — Build Scenario Framework

Create reusable scenario definitions.

A scenario must specify:

* Start
* Destination
* Vessel
* Weather
* Constraints
* Objective
* Evaluation metrics

### Goal

Make experiments reproducible instead of manually configured.

---

# Phase 7 — Build Evaluation Engine

The evaluation engine should automatically:

1. Load a scenario.
2. Run all selected algorithms.
3. Collect metrics.
4. Validate constraints.
5. Store results.
6. Compare algorithms.
7. Generate an evidence summary.

### Goal

One command should be capable of producing a complete experiment.

---

# Phase 8 — Build Algorithm Recommendation

The recommendation engine should determine the most suitable algorithm according to the scenario definition.

It should:

1. Identify mandatory constraints.
2. Remove infeasible routes.
3. Apply the primary objective.
4. Use secondary metrics to distinguish comparable candidates.
5. Produce an explanation based on actual measurements.

The logic must be transparent.

---

# Phase 9 — Build Comparison UI

Expose:

* Individual route results
* Algorithm comparison
* Scenario information
* Metrics
* Route visualization
* Safety status
* Recommendation
* Evidence explanation

The UI should make it possible to understand **why** an algorithm was selected.

---

# Phase 10 — Offline Packaging

Once the application is stable:

1. Identify all runtime dependencies.
2. Identify all required datasets.
3. Remove unnecessary internet dependencies.
4. Package the local application.
5. Test it with internet disabled.
6. Verify routing still works.
7. Verify comparison and recommendation still work.

### Completion condition

A user can run the core Nautilus system without an internet connection.

---

# 40. Development Methodology

Nautilus should continue using the loop-engineering workflow.

The standard development loop is:

```text
Task
  ↓
Inspect
  ↓
Implement
  ↓
Validate
  ↓
Measure
  ↓
Analyze
  ↓
Decide
  ↓
Next Task
```

A task is not considered complete merely because code was written.

A completed loop should have:

* Change
* Validation
* Measurements where applicable
* Analysis
* Decision
* Updated project state

---

# 41. Rules for AI-Assisted Development

AI coding agents should work incrementally.

They should:

* Read the source of truth before major changes.
* Work on one task at a time.
* Avoid unrelated refactoring.
* Avoid implementing future phases early.
* Run existing tests/evaluations before and after meaningful changes.
* Record measurable results.
* Stop when the assigned task is complete.
* Never silently expand scope.

If an agent discovers an unrelated issue:

1. Record it.
2. Assess whether it blocks the current task.
3. Fix it only if necessary for the current task.
4. Otherwise defer it.

---

# 42. Definition of Done

A feature is not complete merely because it runs.

For routing algorithms, "done" means:

```text
Implementation
+
Correctness validation
+
Comparison against baseline
+
Relevant metrics
+
Scenario testing
+
Documentation
```

For deployment work, "done" means:

```text
Build
+
Run
+
Reproducibility
+
Remote validation
+
Failure testing
```

For offline deployment:

```text
Package
+
Install
+
Disconnect internet
+
Run
+
Route
+
Compare
+
Verify functionality
```

---

# 43. What Is Explicitly Out of Scope

The following are **not priorities in the current project direction**:

### Reinforcement Learning

The previous RL/PPO development plan is no longer part of the active implementation roadmap.

Do not:

* Build a PPO environment
* Train an RL routing agent
* Build RL inference
* Add RL reward functions
* Add RL-specific deployment

unless the project direction is explicitly changed again.

---

### Live/Dynamic RL Routing

Not part of the current scope.

---

### Autonomous Vessel Control

Nautilus is a decision-support system.

It does not directly control ships.

---

### Global Ocean Routing

The project remains focused on the defined geographic region.

---

### Unjustified Fuel Optimization

Fuel optimization should not be introduced unless an appropriate model and supporting data are available.

---

# 44. Historical RL Work

The project previously considered a safety-constrained reinforcement-learning extension.

That work is now **historical context only**.

It must not be treated as part of the current architecture or implementation roadmap.

Existing historical documents may remain in the repository because they represent previous project decisions and development history.

However:

> **The current source of truth supersedes those documents for all active development decisions.**

If future project requirements bring RL back, it must be treated as a new project-direction decision rather than automatically continuing the old RL roadmap.

---

# 45. Existing Machine-Learning Speed Model

The existing Random Forest speed model is different from the previously proposed reinforcement-learning system.

It may currently contribute to weather-aware routing through predicted vessel speed / weather multipliers.

It may therefore remain temporarily where required by the existing routing implementation.

However:

* It is not the central research objective.
* It must not become a mandatory dependency for every routing algorithm.
* Its role should be isolated where practical.
* Its limitations must be documented.
* Future experiments should distinguish algorithmic improvements from changes caused by the cost model.

The existing model is based on synthetic physics-inspired training data and should not be described as validated against real-world vessel telemetry unless such validation is actually performed.

---

# 46. Key Architectural Principle

The most important architectural principle for the new Nautilus is:

> **Separate routing algorithms, routing cost models, scenario definitions, evaluation, and presentation.**

Conceptually:

```text
             SCENARIO
                 |
                 v
          Routing Problem
                 |
        ┌────────┴────────┐
        |                 |
   Cost Model        Constraints
        |                 |
        └────────┬────────┘
                 |
          Routing Algorithm
                 |
                 v
            Route Result
                 |
        ┌────────┴────────┐
        |                 |
     Metrics          Validation
        |                 |
        └────────┬────────┘
                 |
            Comparison
                 |
                 v
          Recommendation
                 |
                 v
                UI
```

This separation is what allows Nautilus to become an actual algorithm-comparison platform rather than a collection of routing implementations.

---

# 47. Final Target System

The long-term target is:

```text
                         NAUTILUS
                            |
             ┌──────────────┴──────────────┐
             |                             |
        Route Planning                Evaluation
             |                             |
     ┌───────┴────────┐            ┌───────┴────────┐
     |                |            |                |
 Algorithms       Constraints   Scenarios       Metrics
     |                |            |                |
     └───────┬────────┘            └───────┬────────┘
             |                             |
             └──────────────┬──────────────┘
                            |
                       Comparison
                            |
                            v
                    Evidence-Based
                     Recommendation
                            |
                            v
                    Marine Decision
                       Support
```

The system should ultimately allow a user to:

1. Select a voyage.
2. Select a vessel.
3. Select or define marine conditions.
4. Select a scenario.
5. Generate routes using multiple algorithms.
6. Compare the resulting routes.
7. View safety and efficiency metrics.
8. Understand computational performance.
9. See which algorithm is most appropriate under the scenario criteria.
10. Understand the evidence behind that recommendation.
11. Perform the entire workflow locally without requiring continuous internet connectivity.

---

# 48. Immediate Development Roadmap

The immediate roadmap is:

```text
CURRENT STATE
     |
     v
Update project documentation
     |
     v
Dockerize remote development
     |
     v
Complete classical routing validation
     |
     v
Create common routing interface
     |
     v
Implement additional algorithms
     |
     v
Create scenario framework
     |
     v
Create automated evaluation framework
     |
     v
Create evidence-based recommendation
     |
     v
Integrate comparison UI
     |
     v
Create offline distribution
     |
     v
Final validation
     |
     v
Final demonstration / research results
```

This is the **active project direction**.

---

# 49. Current Priority Order

When deciding what to work on next, use this priority order:

### Priority 1 — Reliable Infrastructure

Dockerized remote development and reproducible execution.

### Priority 2 — Reliable Routing Foundation

Correct routing, ETA, safety validation, and common result structures.

### Priority 3 — Algorithm Expansion

Meaningfully different routing algorithms.

### Priority 4 — Experimental Framework

Scenarios, metrics, reproducibility, and automated comparison.

### Priority 5 — Evidence-Based Recommendation

Demonstrating why an algorithm is suitable for each scenario.

### Priority 6 — User Interface

Making the comparison and recommendation system understandable.

### Priority 7 — Offline Distribution

Packaging the complete system for disconnected operation.

---

# 50. Final Project Statement

Nautilus is a **locally deployable marine routing decision-support system** that compares multiple routing algorithms under different environmental, geographic, vessel, and safety scenarios.

Its central contribution is not simply generating a route.

Its central contribution is:

> **systematically evaluating different routing strategies and providing evidence for which strategy is most appropriate under a given marine scenario.**

The project combines:

* Marine geographic data
* Weather-aware routing
* Multiple pathfinding algorithms
* Safety constraints
* Scenario-based experimentation
* Quantitative algorithm evaluation
* Evidence-based algorithm selection
* Containerized remote development
* Offline-capable deployment

The system is designed as a **decision-support tool**, not an autonomous navigation or vessel-control system.

All future implementation should preserve this separation between:

```text
Routing
Evaluation
Recommendation
Deployment
```

and should follow the loop-engineering methodology so that every major change is measurable, validated, and documented.
