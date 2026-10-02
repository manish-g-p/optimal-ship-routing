# Loop Engineering — Nautilus

This directory is the working memory for Nautilus development under the
loop-engineering methodology described in
[`docs/Source_Of_Truth.md`](../Source_Of_Truth.md) (§40–42).

**Branch:** `refactor/docker-containerization`
**Status as of this writing:** Clean start. This directory was created fresh
on this branch — it contains no RL/PPO history and no prior loop-engineering
artifacts. Nothing here was migrated or reconstructed from another branch.

## Authoritative references

Only two documents govern project direction:

1. [`README.md`](../../README.md) — what the repository contains and how to
   run it today.
2. [`docs/Source_Of_Truth.md`](../Source_Of_Truth.md) — the authoritative
   statement of project goals, architecture direction, phases, and scope.
   If anything in this directory conflicts with it, the Source of Truth wins.

The previous reinforcement-learning direction is explicitly out of scope
(Source of Truth §43–44) and is not referenced by any file in this
directory.

## File index

| File | Purpose |
| --- | --- |
| [`PROJECT_STATE.md`](PROJECT_STATE.md) | What actually exists in the repo right now, vs. planned/unknown. |
| [`TASKS.md`](TASKS.md) | The phased roadmap and the current task queue. |
| [`DECISIONS.md`](DECISIONS.md) | Standing decisions that constrain future work. |
| [`EXPERIMENTS.md`](EXPERIMENTS.md) | Experiment definitions and results. |
| [`LOOP_LOG.md`](LOOP_LOG.md) | Chronological log of each development loop. |
| [`BLOCKERS.md`](BLOCKERS.md) | Open blockers and unresolved questions. |
| [`VALIDATION.md`](VALIDATION.md) | Definition-of-done checklists used to validate a task before closing it. |
| [`CHANGE_LOG.md`](CHANGE_LOG.md) | Human-readable summary of what changed, loop by loop. |

## How to use this during a loop

```text
Read TASKS.md -> pick the one READY task
    |
    v
Read PROJECT_STATE.md -> confirm assumptions still hold
    |
    v
Implement
    |
    v
Validate against VALIDATION.md
    |
    v
Record results in EXPERIMENTS.md (if measurable)
    |
    v
Append an entry to LOOP_LOG.md and CHANGE_LOG.md
    |
    v
Update PROJECT_STATE.md and TASKS.md to reflect the new state
    |
    v
Promote exactly one new task to READY
```

Rules (from Source of Truth §41):

- Work on one task at a time.
- Avoid unrelated refactoring.
- Avoid implementing future phases early.
- Never silently expand scope.
- If an unrelated issue is discovered, record it (in `BLOCKERS.md` or a
  task note) rather than fixing it inline unless it blocks the current task.
