# Loop Engineering — Nautilus

Working memory for Nautilus development sessions ("loops"). It records
what is true in the repository, what comes next, and the evidence behind
both — so an agent can start a session without relying on stale
assumptions.

**Last synchronized:** 2026-10-03 (Loop 008), branch
`feature/dynamic-routing`, working tree on top of `e7597a1`.

## Authoritative references

1. [`docs/Source_Of_Truth.md`](../Source_Of_Truth.md) — project scope,
   architecture direction and roadmap. **If anything here conflicts with
   it, the Source of Truth wins** (and the conflict should be fixed).
2. [`PROJECT_STATE.md`](PROJECT_STATE.md) — what is actually implemented
   in the repository now, verified against code and test runs.
3. The code and tests themselves. A document claim that the code does not
   support is a documentation bug.

### Important: the Source of Truth was rewritten on 2026-10-03

The current Source of Truth defines Nautilus as an **ML-assisted dynamic
ship-rerouting system**. The previous version (multi-algorithm
comparison, evidence-based algorithm selection, remote Docker
development, offline packaging) is superseded.

Entries written before that rewrite (Loops 000–002 and the 2026-10-02
Docker reorganization) cite section numbers such as "§25–26", "§39" or
"§40–42". **Those refer to the previous Source of Truth**, not the
current one. The previous version can be read with
`git show 79f130b:docs/Source_Of_Truth.md`. Such entries are kept as
history and labeled where they matter.

## File index

| File | Role |
| --- | --- |
| [`PROJECT_STATE.md`](PROJECT_STATE.md) | What is true in the repository now: implemented / planned / deferred, entry points, limitations. |
| [`TASKS.md`](TASKS.md) | Current and next goal with status; roadmap phase status; historical tasks (labeled). |
| [`DECISIONS.md`](DECISIONS.md) | Durable decisions (confirmed vs. superseded) and unresolved choices. |
| [`BLOCKERS.md`](BLOCKERS.md) | Active blockers, open technical concerns/risks, resolved items. |
| [`EXPERIMENTS.md`](EXPERIMENTS.md) | Measured evidence and findings; planned experiments marked as such. |
| [`VALIDATION.md`](VALIDATION.md) | What was verified, how, and with what result; definition-of-done checklists. |
| [`LOOP_LOG.md`](LOOP_LOG.md) | Session-by-session development history (newest first). |
| [`CHANGE_LOG.md`](CHANGE_LOG.md) | Concise record of meaningful file-level changes (newest first). |

Other active references outside this directory: [`README.md`](../../README.md)
(how to run things) and [`DOCKER.md`](../../DOCKER.md) (container workflow).

## Reading order for a new session

1. `docs/Source_Of_Truth.md` — at least §1–7 and §16 (roadmap).
2. `PROJECT_STATE.md` — current implementation state.
3. `TASKS.md` — the current/next goal and its status.
4. `BLOCKERS.md` — open concerns that may affect the goal.
5. `DECISIONS.md` — constraints already decided.
6. As needed: the latest `LOOP_LOG.md` entry, `VALIDATION.md`,
   `EXPERIMENTS.md`.

Then verify any claim you depend on against the code (and run
`python -m unittest discover -s tests` — 55 tests, about 2–2.5 min).

## Maintenance convention

After completing a **meaningful** implementation goal (new capability,
behavior change, architectural decision, changed project status):

1. Update `PROJECT_STATE.md` to match the repository.
2. Update `TASKS.md`: mark the goal done (with evidence pointer) and
   record the next goal — as *proposed* unless the user confirmed it.
3. Add durable decisions to `DECISIONS.md`; mark any it supersedes.
4. Record measured results in `EXPERIMENTS.md` and the checks actually
   run, with outcomes, in `VALIDATION.md`.
5. Add a concise `LOOP_LOG.md` entry (date, commit if known, what was
   done, validation, decision, next).
6. Update `BLOCKERS.md` and `CHANGE_LOG.md` when something was found,
   resolved or changed.
7. Check the Source of Truth still matches the direction and status;
   update its status markers if a roadmap phase changed.

Rules:

- Trivial edits (typos, refactors without behavior change, test tweaks)
  need no documentation update, or at most a `CHANGE_LOG.md` line.
- Never record a result that was not actually produced; say "not run" or
  "unknown" instead. Mark prior results as prior when not re-run.
- Keep facts in one place and point to it; don't copy details across
  files.
- Historical entries are not rewritten to look cleaner — label them
  superseded/historical instead.
- One goal at a time; record unrelated issues in `BLOCKERS.md` rather
  than fixing them inline.
