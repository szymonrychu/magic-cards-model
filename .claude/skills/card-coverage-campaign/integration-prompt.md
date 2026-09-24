# Integration prompt template (round merger, model: opus)

Fill every `<...>` placeholder before dispatching this as an `Agent` prompt,
fresh agent (not a fork), `model: "opus"`. One of these per round, dispatched
only after every task worktree of the round has finished
`workbench:plan-execute`'s implement -> review -> fix cycle.

---

You are integrating round `<ROUND_ID>` (`<ROUND_LABEL>`) of the
magic-cards-model card-coverage campaign: merging every task worktree of
this round into `main`, verified, or reporting exactly why not.

Task worktrees (one per completed task): `<TASK_ID>=<WORKTREE_PATH>` (repeat
for every task in the round).

Engine repo: `/Users/szymonri/Documents/magic-trainer/code/magic-cards-model`
API repo (sibling): `/Users/szymonri/Documents/magic-trainer/code/magic-cards-model-api`

## 1. Build one integration worktree

```sh
python3 /Users/szymonri/Documents/claude-infra-plugin/skills/worktree-create/scripts/create.py \
  --name <round-id-lower>-integ --repo magic-cards-model
```

from `/Users/szymonri/Documents/magic-trainer`. Work only there, by absolute
path; never call `EnterWorktree`.

## 2. Merge every task branch into it

Merge each task's branch in turn. Resolve conflicts from `git show
<ref>:<file>` per side, never from how the conflict markers happen to lay
the two versions out (they have spliced two different functions' bodies
together before - read each side whole).

- **Schema version bumps**: if two tasks each bumped
  `Game.CURRENT_SCHEMA_VERSION`, renumber the second (and its migration/test)
  to the next free integer after the merge - never leave two tasks claiming
  the same version.
- **The dispatch fingerprint**
  (`tests/dispatch_fingerprint_baseline.json`): never hand-merge it.
  Regenerate after every task is merged in:
  ```sh
  mise run dispatch:fingerprint
  ```
- **Goldens** (`tests/golden/`): never hand-edit. If a merged change alters
  a swept card's recorded behaviour on purpose, regenerate and review the
  diff:
  ```sh
  mise run golden:update
  ```

## 3. The full gate - every one of these, in order, none skipped

Wrap each full-suite invocation in `suite-lock.sh` (serializes against any
other agent's full-suite run on this machine):

```sh
/Users/szymonri/Documents/claude-infra-plugin/skills/worktree-merge/scripts/suite-lock.sh -- \
  mise run lint
/Users/szymonri/Documents/claude-infra-plugin/skills/worktree-merge/scripts/suite-lock.sh -- \
  mise run test:full
```

Then the API's own tiers, against this merged engine (not against its own
`main` engine dependency) - use a sibling symlink so the API resolves your
merged tree:

```sh
cd /Users/szymonri/Documents/magic-trainer/code/magic-cards-model-api
# ensure magic-cards-model resolves to the integration worktree, e.g. a
# sibling symlink or path override per this repo's own dependency wiring
/Users/szymonri/Documents/claude-infra-plugin/skills/worktree-merge/scripts/suite-lock.sh -- \
  mise run lint
/Users/szymonri/Documents/claude-infra-plugin/skills/worktree-merge/scripts/suite-lock.sh -- \
  mise run test
/Users/szymonri/Documents/claude-infra-plugin/skills/worktree-merge/scripts/suite-lock.sh -- \
  mise run test:pg
```

**Never land red.** If any gate fails, fix it in the integration worktree
(a real conflict-resolution defect, not a reason to skip a gate) and rerun
from the top of this section. A test that needs an "unsupported card"
example must pick one dynamically (`tests.cards.gap_example`, or the API's
own synthetic-card fixtures) - never hardcode a card that happens to be
unsupported today, since this round is in the business of making cards
supported.

## 4. Confirm every card of the round is handled

For every card named across every task's `requirement` this round:

```sh
mise exec -- uv run python scripts/sweep_pool.py --card "<name>"
```

Every clause must read `handled` (no `silent`, no `notice`; a
`static_unaudited` clause must have a scenario test proving it, per COMMON
ACCEPTANCE (a)). **This must be zero exceptions.** If a card is not fully
handled, that is round work that did not land - name it explicitly in your
report; do not fast-forward `main` with an unfinished card silently
included.

## 5. Fast-forward main - do not push

```sh
cd /Users/szymonri/Documents/magic-trainer/code/magic-cards-model
git merge-base --is-ancestor <round-id-lower>-integ main && echo "would be no-op - stop, something didn't commit"
git checkout main
git merge --ff-only <round-id-lower>-integ
```

Do not `git push`. Leave the pushed/deploy decision to the human or a
separate deploy step - this round's job is a verified, green, local `main`.

## 6. Update the coverage docs for the landed round

```sh
mise exec -- uv run python scripts/card_coverage.py --workers 8
```

(or invoke the `card-coverage-refresh` skill, which does this plus moves the
round's `state` to `done` and records why). Commit the regenerated
`docs/card_coverage/` changes as their own commit, separate from the engine
change commits that already landed via the per-task merges.

## 7. Report

New `main` sha; each gate's pass/fail summary line (engine lint, engine
test:full - passed/failed/skipped counts -, api lint, api test, api
test:pg); the card-by-card confirmation from step 4 (all handled, or the
named exceptions); and whether `docs/card_coverage/` was regenerated and
committed. If anything from this round did not land, say so explicitly and
name it - do not report the round as done with an unfinished card folded in
quietly.
