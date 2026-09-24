---
name: card-coverage-campaign
description: Use to run the next batch(es) of TDD development against docs/card_coverage/plan.md and its status.md files - turning silent/notice/unaudited cards into fully handled, tested engine coverage, one round at a time. Encodes the proven planner -> worktrees -> plan-execute -> integration cycle. Requires plan.md and every status.md to already be up to date (card-coverage-refresh first if in doubt).
---

# Card coverage: campaign

## Before you start

This skill **consumes** `docs/card_coverage/plan.md` and its `status.md`
files; it does not produce them. If either might be stale (a round landed
since the last regenerate, or you're not sure), run `card-coverage-refresh`
first. Planning a round against stale numbers wastes a planner dispatch and
can re-plan work that already landed.

**Prerequisites**: `mise run install` in
`/Users/szymonri/Documents/magic-trainer/code/magic-cards-model`; the
`workbench:plan-execute` and `workbench:worktree-create` skills available
(this skill dispatches both); `mise run rules:pull` run at least once
somewhere the engine repo can find `.rules/` (each task worktree needs its
own, per `CLAUDE.md`).

This skill is self-contained: `planner-prompt.md` and `integration-prompt.md`
in this same directory hold the full prompt templates. It does not read or
depend on anything under a scratchpad from a prior session.

## The cycle, one round at a time

```
pick next round -> planner (opus) -> worktrees per task
  -> workbench:plan-execute (this round's tasks) -> integration (opus)
  -> update status.md/plan.md -> report -> pick next round
```

### 1. Pick the next round

Read `docs/card_coverage/plan.md`'s Campaign order table.

- **Round 0 (metagame decks) first**, if its row is not `done` - these are
  the cards currently played in real decks (`code/magic-cards-model-api/decks/*.txt`,
  `/Users/szymonri/Documents/mtg-decks`), so they're the highest-value
  targets regardless of chronological order.
- Otherwise, the **newest-dated row that is `todo` or `in-progress`** (the
  table is already newest-to-oldest; take the first non-`done` row from the
  top). Chronological order is deliberate - see `plan.md`'s own header.
- The human may override and name a specific set or round; that always wins.

A "round" for this skill is one `plan.md` row: one expansion's `status.md`
(or Round 0's deck-derived card list). If a row's non-full card count is
very large (hundreds), it is still one round - the planner's own 8-task cap
and clustering-by-template is what keeps a large row tractable, not
splitting the row.

### 2. Dispatch the planner

Fill `planner-prompt.md` (this directory) with this round's id/label and
`status.md` path(s), a scratch output path for its plan
(`<scratchpad>/card-coverage-<ROUND_ID>-plan.md`) and plantext
(`<scratchpad>/card-coverage-<ROUND_ID>-plantext.md`). Dispatch with the
**Agent tool**, fresh agent (not `subagent_type: "fork"` - the planner needs
a clean-context read of current engine state, not this orchestrator's
history), `model: "opus"`.

It returns `TASKS=<path> PLANTEXT=<path>` plus a dropped-card count. Read
the plan file's JSON block yourself (`silent-plan.md`'s schema, reproduced
in `planner-prompt.md`) - do not skip reading it; the integration step later
depends on you already knowing every task's file ownership.

### 3. One worktree per task

For every task in the plan:

```sh
python3 /Users/szymonri/Documents/claude-infra-plugin/skills/worktree-create/scripts/create.py \
  --name <round-id-lower>-<task-id-lower>-<short-slug> --repo magic-cards-model
```

run from `/Users/szymonri/Documents/magic-trainer`. Collect
`<task-id>=<worktree-path>` for every task - `workbench:plan-execute` needs
this mapping.

### 4. Run `workbench:plan-execute`

Invoke the `workbench:plan-execute` skill with:

- `tasks`: the plan's JSON array, each task's `notes` field appended with
  the worktree rule (work only in `<worktree>` by absolute path, every Bash
  command starts with `cd <worktree>`, never call `EnterWorktree`, commit on
  the worktree branch) and the engine hard rules (real Scryfall printings,
  no mocks, scenario tests, every CR number looked up with `mise run
  rules:find <n>`, mise for everything, target the mechanic never the card,
  Modern/Pioneer/Standard only and every legal card must be fully
  supported - never silent, never left failing closed with a notice), and
  each task's `worktree` field set from step 3.
- `planText`: the plantext file's contents, **scoped to this round only**
  ("Already done: <earlier rounds>. Deferred: <later rounds>." - this is
  what keeps an implementer from wandering into a different round's cards).
- `contextPack`: a short pointer to this round's `status.md` path(s) and
  `docs/engine-coverage.md`.
- `lenses`: `["correctness", "requirements-coverage"]`.

This runs the implement -> review -> fix loop (max 3 rounds, then escalate)
per task, then one scope audit across the round. Let it run to completion or
escalation before moving on - do not hand-roll a parallel implement/review
loop yourself; that discipline (round caps, model pinning, targeted tests,
single scope audit) is exactly what this workflow exists to hold.

If it escalates on a task: read why, judge it (the workflow's escalation
reason is not automatically correct), and either resolve it yourself,
narrow that one task's scope, or drop the offending card(s) back into a
follow-up round with a `MEMORY.md` line explaining why - never silently fold
an escalated, unresolved task into the round as if it landed clean.

### 5. Integration

Once every task in the round has a committed, reviewed worktree, fill
`integration-prompt.md` (this directory) with the round id/label and every
`<task-id>=<worktree-path>` pair, and dispatch it with the **Agent tool**,
fresh agent, `model: "opus"`.

It merges every task worktree into one integration worktree, runs the full
gate (engine lint + `test:full`, API lint + `test` + `test:pg`, each wrapped
in `suite-lock.sh`), confirms every card of the round reads `handled` via
`scripts/sweep_pool.py --card`, fast-forwards local `main` (does not push),
and regenerates + commits the coverage docs. Read its report; if it names
any card that did not land fully handled, that card goes back into a
follow-up round rather than being counted as done.

### 6. Update the campaign docs and report

If the integration agent didn't already (step 6 of its own prompt), run
`card-coverage-refresh` now so `plan.md`'s round state actually reflects
what just landed.

Report to the human, a few lines: which round landed, the new `main` sha,
cards closed (count, and names if the round was small), anything deferred
and why, and the next round you'd pick.

## Pipelining (optional)

While a round's `workbench:plan-execute` is running (it can take a while),
you may dispatch **a second, independent planner** for the *next* round in
parallel - planning is read-only and cheap, and having the next round's
plan ready the moment this one's integration lands avoids an idle gap. Do
not start the next round's worktrees or `plan-execute` until this round has
actually landed (main must be stable and green for the next round's
implementers to branch from). This is an optimization, not a requirement -
skip it under token pressure.

## Token discipline

- The planner and integration prompts already say this, but as the
  orchestrator: do not read the full bulk Scryfall snapshot, do not read
  `effects.py`/`layers.py`/etc. whole - targeted lookups only
  (`sweep_pool.py --card`, `grep`, specific function reads).
- Prefer forking yourself (`subagent_type: "fork"`) for anything that is
  pure orchestration bookkeeping you'll want to remember; use a fresh agent
  (as specified above) for the planner and integrator, since they benefit
  from a clean-context read of engine state rather than this skill's own
  running history.
- One round at a time by default. Round size is already bounded by the
  planner's 8-task cap; do not widen scope to "finish the whole expansion's
  remaining tail" if the planner judged 8 tasks insufficient - let it defer
  the rest to a follow-up round instead.

## Common failure modes (from the prior ad hoc runs of this same process)

- **A task claims done with an uncommitted worktree.** The integration
  agent's step 4 (confirm every card handled) and its merge-base check
  catch this - never skip them, and never trust a task's self-report of
  "done" without the integration agent's own verification.
- **Two tasks both bump `Game.CURRENT_SCHEMA_VERSION`.** Renumber at
  integration time, never at plan time (the plan is written before either
  task's actual diff exists).
- **A shared helper function gets edited by two tasks in the same round.**
  The planner is responsible for disjoint file ownership; if integration
  finds an overlap anyway, that's a planner defect to note for next time,
  not something to silently paper over in the merge.
- **"Unsupported card" example hardcoded in a test.** Breaks the moment
  that exact card becomes supported (which is the whole point of the
  campaign). Must be picked dynamically - see the integration prompt's
  step 3.
