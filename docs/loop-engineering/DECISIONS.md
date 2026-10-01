# Decisions

Standing decisions that constrain future loops. Only decisions required to
establish the current project direction are recorded here; nothing
speculative about later phases (no metric weights, no final recommendation
formula, no offline packaging mechanism — those are deferred, per
`docs/Source_Of_Truth.md` §23 and the current loop's explicit scope).

---

## Decision 001 — Current project direction

**Decision:** Nautilus's active development direction, as of this branch,
is:

- Routing algorithm expansion
- Scenario-based evaluation
- Evidence-based algorithm selection
- Remote Docker development
- Offline deployment

**Why:** This is what `docs/Source_Of_Truth.md` defines as the current,
authoritative project scope (§2–3, §50).

**Implication:** Reinforcement learning (RL/PPO) is **not** part of the
active roadmap. No RL implementation tasks, no RL architecture, and no RL
migration plan are to be created under this direction. The existing
Random-Forest speed model is a separate, already-existing component (not
RL) and may remain where the current routing implementation depends on
it, per Source of Truth §45 — but it is not the research focus and should
not become a mandatory dependency for future algorithms.

---

## Decision 002 — Docker as the development environment

**Decision:** Docker will be used to provide a reproducible Nautilus
development/runtime environment, primarily for the remote server where
the developer may not have permission to install a system-wide
development stack (Source of Truth §27–31).

**Why:** Matches the stated Goal 4 (Remote and Containerized Development)
and Priority 1 (Reliable Infrastructure) in the Source of Truth.

**Implication:** TASK-001 targets a **development container** first
(source/workspace mounted, dependencies installed, able to run the
existing evaluation). A separate, minimal production/distribution image
(Source of Truth §30) is a later decision — not made now. Docker Compose
is adopted only if/when it proves useful during TASK-001, not decided
up front.

---

## Decision 003 — Offline-first core operation

**Decision:** Core routing and algorithm-comparison functionality must
not require continuous internet access. Normal route planning must work
from locally available application code, processed geographic/weather
data, port data, vessel data, and configuration (Source of Truth §32–33).

**Why:** Matches Goal 5 (Offline-Capable Marine Deployment) — the
marine-industry context cannot assume continuous connectivity.

**Implication:** Live weather (`src/live_weather.py`) remains optional
and non-mandatory; static `typical`/`rough` scenarios remain the
preferred basis for reproducible experiments and comparison (Source of
Truth §34). The exact offline packaging mechanism is **not** decided here
— deferred to Phase 7, after the core application is stable.

---

## Decisions explicitly NOT made in this loop

- No final set of routing algorithms beyond what already exists.
- No recommendation-scoring formula or metric weighting.
- No offline-packaging technology choice.
- No production/distribution Docker image design.
- No resolution of the ETA discrepancy noted in `PROJECT_STATE.md` — it
  is recorded as an open item for Phase 2, not decided or fixed now.
