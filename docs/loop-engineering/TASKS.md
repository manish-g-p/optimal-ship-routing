# Tasks

Roadmap and task queue, derived from `docs/Source_Of_Truth.md` §39
(Project Implementation Order) and §49 (Priority Order).

Rule: **only Phase 1 has detailed, actionable tasks right now.** Later
phases list goals and candidate work only — they are not yet broken into
tasks, per the current loop's scope (avoid over-planning future phases).

Status values: `READY`, `BLOCKED`, `BACKLOG` (not yet actionable),
`DONE`.

There must be exactly one `READY` task at a time.

---

## Phase 1 — Reproducible Remote Environment

**Goal:** Make Nautilus reproducibly executable on the remote server
through Docker.

### TASK-001 — Establish reproducible Docker development environment — `READY`

**Purpose:** Determine and containerize the existing Nautilus
development/runtime environment so the current application can run
reproducibly inside Docker. This is a local/container validation step —
**not** Docker Hub publishing and **not** remote-server deployment.

Target flow:

```text
Repository
    ↓
Docker build
    ↓
Nautilus container
    ↓
Existing application/evaluation runs
    ↓
Reproducible environment
```

Scope for this task:

1. Inspect the current runtime (Python 3.12.3 in `.venv`) and determine
   actual installed dependency versions (`requirements.txt` is currently
   unpinned).
2. Create a Docker development image: base image, dependency install,
   source copy/mount, working directory, entrypoint.
3. Build the image and run a container from it.
4. Verify the existing evaluation command (`python -m src.evaluate`, or
   `run_all.py`) runs successfully inside the container, using the
   already-committed `data/processed/` artifacts (no raw `.nc` files
   required for this).
5. Confirm no unexpected host dependency is required (i.e. the container
   is self-sufficient once the repo is copied/mounted in).

Explicitly out of scope for TASK-001 (deferred to later tasks in this
phase): Docker Hub image publishing, pulling/running on the actual remote
server, production/distribution image, Docker Compose (only if it turns
out to be useful — not assumed up front).

**Depends on:** nothing (first task).
**Blocks:** TASK-002, TASK-003, TASK-004 below.

### TASK-002 — Docker Hub image workflow — `BACKLOG`

Push the validated development image (or a derived build) to Docker Hub
so it can be pulled elsewhere. Depends on TASK-001 succeeding.

### TASK-003 — Pull and run on the remote server — `BACKLOG`

Pull the published image on the actual remote server and start the
container there. Depends on TASK-002.

### TASK-004 — Validate remote execution — `BACKLOG`

On the remote server, inside the container: run the existing routing
system and the existing evaluation, confirm results match the local
container run (TASK-001). This is the "Remote Development Milestone"
from Source of Truth §31, and should be demonstrated before major
routing development (Phase 2+) continues in earnest.

---

## Phase 2 — Routing Foundation — `BACKLOG` (not yet broken into tasks)

Goal: a reliable foundation for algorithm comparison, before adding more
algorithms.

Candidate work (from Source of Truth §39 Phase 3, §13):

- Investigate and resolve the ETA discrepancy noted in
  [`PROJECT_STATE.md`](PROJECT_STATE.md) (Source of Truth claims a fix
  that is not present in this branch's `src/routing.py`).
- Establish a common `RouteResult` that every algorithm populates
  identically (algorithm, found, route cells/latlon, distance, ETA, max
  wave, mean wave, min coast clearance, expanded states, runtime, safety
  validity, constraint violations).
- Establish common routing metrics collection.
- Establish safety/constraint validation as a first-class step.
- Separate routing logic from evaluation/presentation where it is
  currently intermixed (e.g. `evaluate.py` computing min-coast distance
  itself rather than the router/result doing so).

## Phase 3 — Routing Algorithm Expansion — `BACKLOG`

Candidate algorithms (not yet committed to an implementation order; each
must get its own justification before it becomes a task, per Source of
Truth §15):

| Algorithm | Reason to include | Measurable property |
| --- | --- | --- |
| Dijkstra | Classical baseline, already implemented | Reference distance/time/expansions |
| A* | Heuristic-guided reduction in search effort | Expanded-cell count vs. Dijkstra |
| Bidirectional Dijkstra | Tests whether meeting-in-the-middle reduces search effort over single-direction Dijkstra | Expanded-cell count, runtime |
| Bidirectional A* | Combines heuristic + bidirectional search | Expanded-cell count, runtime, vs. both Dijkstra variants and plain A* |
| Weather-aware Dijkstra | Isolates the effect of the weather cost model from the effect of the heuristic (today only A* is weather-aware, confounding the two) | Route distance/ETA/wave exposure vs. weather-aware A* with the same cost model |
| Weather-aware A* | Already implemented; baseline for comparison | — |
| Risk-constrained / multi-objective | Changes the problem from "cheapest route" to "feasible-safe route optimized within the feasible set" | Constraint-violation rate, feasible-route quality vs. unconstrained algorithms |

No implementation tasks exist yet for any of these except the two already
built (Dijkstra, weather-aware A*). Each future algorithm becomes a task
only once it has a documented reason, scenario, and baseline (Source of
Truth §15).

## Phase 4 — Scenario Framework — `BACKLOG`

Goal: reproducible scenarios combining start/destination, vessel,
weather, geographic conditions, safety constraints, and optimization
objective (Source of Truth §17–18). Not yet designed.

## Phase 5 — Evaluation and Evidence — `BACKLOG`

Goal: automated framework that runs multiple algorithms, collects common
metrics, checks constraints, compares feasible routes, determines
suitability per scenario criteria, and produces evidence (Source of Truth
§19–23). Explicitly avoid an arbitrary weighted scoring formula unless
defensible. Not yet designed.

## Phase 6 — Comparison UI — `BACKLOG`

Goal: expose algorithm selection, comparison, route visualization,
metrics, safety status, scenario info, and evidence/recommendation
(Source of Truth §36). Not yet designed.

## Phase 7 — Offline Deployment — `BACKLOG`

Goal: local execution, local processed datasets, no unnecessary network
dependency, downloadable/distributable application, offline validation
(Source of Truth §32–35). Packaging mechanism to be selected after the
core application is stable — not chosen yet.

---

## Current READY task

**TASK-001 — Establish reproducible Docker development environment**

(See Phase 1 above for full scope.)
