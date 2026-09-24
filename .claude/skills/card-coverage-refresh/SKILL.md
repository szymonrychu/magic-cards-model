---
name: card-coverage-refresh
description: Use to re-sync docs/card_coverage/plan.md and every docs/card_coverage/<NNN>-<code>/status.md against the engine as it stands on main right now - after a merge landed, periodically between campaign rounds, or whenever the coverage numbers might be stale. Re-runs the generator, folds in known bugs (MEMORY.md, strict-xfail markers, SWEEP_DRIVER_GAPS), and moves round states (todo/in-progress/done).
---

# Card coverage: refresh

## When this fires

- A `card-coverage-campaign` round just merged to `main`.
- Periodically, to keep the campaign plan honest between rounds.
- Before starting a new `card-coverage-campaign` round, so the planner works
  from current numbers rather than a stale snapshot.
- The human asks "where does coverage actually stand".

## What it does that a bare generator run doesn't

`scripts/card_coverage.py` is a pure, deterministic function of (bulk
Scryfall data) x (engine main). It gets the counts right but knows nothing
about *why* a card is stuck, or whether a round is actually done. This skill
is the editorial pass on top: it reads what the generator can't - test
coverage, known bugs, engine maturity - and writes that judgement into the
files the generator otherwise only preserves verbatim (`## Notes`, the
`state` column).

## Procedure

### 1. Orient

Read, in this order: `CLAUDE.md`, `MEMORY.md`, `ROADMAP.md`,
`docs/engine-coverage.md` (all repo root). These are usually short; read
them whole rather than grepping blindly, so genuinely new context (a
mechanic that just got engine-modularized, a policy that changed) isn't
missed.

Read `docs/card_coverage/plan.md`'s existing `## Notes` section and skim
each `status.md`'s own `## Notes` for sets you're about to touch (`git diff`
after the regenerate, below, tells you which those are) - a human may have
already recorded why a set is stuck or what's in flight for it.

### 2. Regenerate

```sh
mise exec -- uv run python scripts/card_coverage.py --workers 8
```

Add `--refresh-bulk` only if the cached snapshot is genuinely stale (check
`.scryfall-cache/oracle-cards.jsonl.gz`'s mtime; if it's more than a day
old, refresh). Otherwise the cache is fine - this skill's job is "sync
against the engine", not "sync against Scryfall's latest print run", and an
unnecessary ~100MB re-download just burns time.

This rewrites every `status.md` and `plan.md` from current main, preserving
every `## Notes` section and every round's `state` verbatim, and folding in
whatever new expansions have appeared in `docs/card_coverage/` numbering
since the last run (new sets always get the next free number - nothing
already assigned moves; see the generator's own docstring).

### 3. Diff and gather bug signal

```sh
git diff --stat docs/card_coverage/
```

names every set whose numbers moved. **This only works when `docs/card_coverage/`
is already tracked.** On the very first run of this skill in a repo (or worktree)
- `git status --short docs/card_coverage/` shows `?? docs/card_coverage/` rather
than a list of modified files - `git diff --stat` sees nothing to diff against
and silently prints empty output, which reads exactly like "nothing changed"
even though every set is brand new. Check `git status --short docs/card_coverage/`
first: an untracked directory means treat *every* generated set as having
"moved" (gather bug signal for all of them, not none) rather than trusting an
empty diff.

For those sets (and any the human named), gather *why*:

- **MEMORY.md** - dated lines naming a card or mechanic as a known dead end
  or deferred decision. Read the whole file; it's small and every line
  matters more than a keyword match would suggest.
- **xfail / strict-xfail markers naming cards**:
  ```sh
  grep -rn "xfail" tests/ | grep -iE "reason=.*[A-Z][a-z]+ [A-Z]"
  ```
  A card named in an `xfail` reason is a known, deliberately-deferred gap,
  not a fresh find - the campaign should not re-discover it as new work.
- **SWEEP_DRIVER_GAPS**:
  ```sh
  grep -n "SWEEP_DRIVER_GAPS" -A 20 tests/test_behavioural_sweep.py
  ```
  Each entry is a case the behavioural harness cannot drive yet (per event
  kind and precondition) - a harness limitation, not a rules gap. A card
  whose only failure traces to one of these is "handled but can't be proven
  by the sweep yet", not "silent" in spirit, even though `card_support`
  still reports it that way; note this distinction in the set's `## Notes`
  rather than treating it as ordinary campaign work.
- **`docs/engine-coverage.md`**'s "Not modelled" table - anything listed
  there explains a cluster of `notice`/`silent` entries across many sets at
  once; cross-reference rather than treating each set's instance as
  independent.

### 4. Move round states

For each set row in `plan.md`'s Campaign order table, using the freshly
regenerated `status.md` counts:

| Evidence | State |
|---|---|
| Full = total (100% coverage) | `done` |
| Full rose from the previous state, or a `card-coverage-campaign` round is actively running for it | `in-progress` |
| Otherwise, no work has started | `todo` |
| A landed round's cards are all handled but the set contains cards blocked on a named, tracked engine limitation (SWEEP_DRIVER_GAPS, an documented `docs/engine-coverage.md` exception) | `done` with a `## Notes` line naming the exception - do not hold a set at `in-progress` forever waiting on something the campaign itself will never close |

**Coverage numbers alone cannot tell you a round is `done`.** A round only
implements the templates on its own task list; a set can legitimately sit at
`done` well under 100% full (`hob` landed at 62% full/38% not-tested - untested-
but-handled cards, not silent ones - and is still `done` by campaign say-so, not
by the "Full = total" row above). `scripts/card_coverage.py`'s `SEED_ROUND_STATES`
carries forward whatever state a set is already at, but nothing in this repo
(no `campaign_rounds.json` or `STATE.md` exists here despite the generator's
own docstring naming them as the seed source) records which round is *currently*
running. When the coverage numbers don't unambiguously say `done`/`todo` by the
table above, ask whoever is driving the campaign which round just landed or is
in flight, rather than inferring it from the `status.md` bucket counts alone.

Edit the `state` column directly (`plan.md`'s Campaign-order table); the
generator will preserve it on the next run. Do the same review for `Round
0` (the metagame-decks row): `todo`/`in-progress`/`done` by whether its
listed cards are still not full.

### 5. Record what changed

Add one dated line to `plan.md`'s `## Notes` (edit the file directly - the
generator only preserves this section, it never writes to it) summarizing
what moved and why: sets that flipped to `done`, bugs found, anything
deferred and why. Keep it to a line or two per item - this is a durable log,
not a report to the human.

### 6. Report

A few lines to the human: sets whose state changed and to what, the overall
coverage delta (`## Overall coverage` table, before vs after), and any bug
that's now blocking more than one set (worth flagging once rather than N
times across N status.md files).

## What this skill does not do

- It does not implement anything or write tests - `card-coverage-campaign`
  does that.
- It does not fetch a single new set's spoilers ahead of the daily bulk
  snapshot - `card-coverage-new-set` does that.
- It does not commit by itself unless asked; leave the diff for review, or
  fold it into the same commit as a landing campaign round.
