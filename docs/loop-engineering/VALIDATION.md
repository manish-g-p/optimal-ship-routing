# Validation

Definition-of-done checklists, adapted from `docs/Source_Of_Truth.md` §42.
A task is not complete merely because code was written or a command ran
once without error.

---

## General principle

A completed loop has: Change + Validation + Measurements (where
applicable) + Analysis + Decision + Updated project state (Source of
Truth §40). "It runs" is necessary but not sufficient.

---

## Definition of done — Routing algorithm work

```text
Implementation
+ Correctness validation
+ Comparison against baseline
+ Relevant metrics
+ Scenario testing
+ Documentation
```

Not yet applicable this loop — no routing algorithm work was done.

## Definition of done — Deployment work (applies to TASK-001)

```text
Build
+ Run
+ Reproducibility
+ Remote validation
+ Failure testing
```

Checklist for TASK-001 specifically:

- [ ] Docker image builds from a clean checkout with no manual
      intervention.
- [ ] Container starts and the existing evaluation entry point runs to
      completion.
- [ ] Rebuilding the image from scratch on the same machine produces the
      same successful result (reproducibility, not just "worked once").
- [ ] No host-level Python environment or system dependency is required
      beyond Docker itself.
- [ ] Failure modes are checked, not just the happy path — e.g. what
      happens if `data/processed/` is missing, what happens if the
      container is given no raw `.nc` files (expected: still works,
      since processed data is committed).
- [ ] Remote-server validation is explicitly **not** part of TASK-001's
      done criteria — that is TASK-004, once TASK-002/003 exist.

## Definition of done — Offline deployment work (future, Phase 7)

```text
Package
+ Install
+ Disconnect internet
+ Run
+ Route
+ Compare
+ Verify functionality
```

Not applicable yet — recorded here only so Phase 7 work starts from the
same definition of done, rather than inventing one later.

---

## Validation performed for this initialization loop

Since this loop is documentation-only, validation means a consistency
check rather than a functional test:

- [x] Every claim in `PROJECT_STATE.md` about "implemented" functionality
      was checked against the actual source file, not assumed from the
      README or Source of Truth alone.
- [x] The ETA claim in Source of Truth §25–26 was checked against
      `src/routing.py` directly rather than taken at face value; the
      discrepancy is recorded rather than silently repeated as fact.
- [x] No document in `docs/loop-engineering/` states or implies that
      RL/PPO is an active implementation priority (see `CHANGE_LOG.md`
      for the explicit check).
- [x] Exactly one task (TASK-001) is marked `READY`.
- [x] No source code, UI, dependencies, or existing routing
      implementation were modified.
