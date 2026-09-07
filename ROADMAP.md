# ROADMAP

`docs/engine-coverage.md` tracks rules coverage in detail; this file only says
what this component is, what phase it is in, and what is next. Terse - see
`docs/architecture.md` at the workbench root for the eight-component target
shape and the reasoning behind it.

## What this is

`magic-cards-model` is component 1 of that shape: a **stateless rules
library**, not a service. It ships no Dockerfile and no Helm chart - that is a
deliberate decision, not an oversight. Every other component in the target
shape is a Deployment with its own image and chart; this one is consumed as a
git dependency pinned to a commit sha (`magic-cards-model @ git+ssh://...@
<sha>`), resolved through the consumer's `uv.lock`. `mise.toml`'s
`docker:push`/`image-tag` tasks delegate to `../magic-cards-model-api` for
exactly this reason - the images this engine ends up in are built there, not
here.

The library owes its consumers two guarantees, stated in full in `CLAUDE.md`:
decode any game state, and enumerate every legal action available to a player
at any point in time.

## What just landed: phase 1, the stateless-library branch

Before this branch, the library could do neither guarantee. `Game.model_dump()`
raised on any game with a live continuous effect, a delayed trigger, or a kept
keyword activation - all three carried a bare Python closure with no pydantic
schema - and legal-action enumeration did not exist at all; the only "what can
this seat do" answer was the API's own mutate-and-rewind HTTP probe, which
deadlocked in production (`memory/harness-deadlock-defaulted-every-decision.md`).

This branch fixed both, in dependency order:

- Deterministic object ids (`ids.py`), so replaying the same commands from a
  decoded snapshot mints the same ids and produces a byte-identical game.
- Every callable field on a persisted model became data: `ContinuousEffect`'s
  `selector`/`modification`/`condition` (`machines/layers.py`),
  `DelayedTrigger.effect` (`machines/delayed.py`), and
  `AbilityOnStack.keyword_activation`/`unless_payment` are now pydantic
  discriminated unions instead of closures.
- A paused game became representable: `DecisionScript.provider`, a live
  object that blocked the resolving thread, is now a recorded-answer tape
  plus `DecisionPending`, and a pause is `(committed state, command, answers
  so far)` rather than a field on `Game` (`machines/decisions.py`).
- Announcement became one atomic call: `Casting` validates fully before any
  mutation (`machines/casting.py`).
- Legal-action enumeration landed in the library itself
  (`machines/legal_actions.py`), including an affordability check that
  mutates nothing.
- `Game.schema_version` refuses to decode a game written by a different
  engine instead of silently treating it as current.
- The round-trip/replay invariant is wired into the scenario harness
  (`tests/scenarios/conftest.py`): every scenario now proves it round-trips
  and replays, with no opt-in required.

`memory/*.md` has the dated entries for the non-obvious decisions inside that
work; `git log --oneline main..HEAD` has the commits.

## What is next

The effect-registry coverage gap is the dominant open work, and it predates
this branch and survives it unchanged: `machines/effects.py` keys a spell's
effect by card name, `machines/layers.py`'s `LAYER_EFFECTS` keys a static
ability the same way, and `machines/replacement.py`'s `REPLACEMENTS` does too
for replacement/prevention effects. A card with no entry in any of the three
resolves, leaves the stack, and changes nothing - silently. See
`memory/effect-registry-is-the-dominant-gap.md` for the measured survey (22
spell entries, 25 trigger entries, 6 activated entries for the whole pool; 63
of 85 instants and sorceries in the fixture pool have no effect at all) and the
ranked order of work, and `docs/engine-coverage.md` for the mechanic-by-
mechanic detail of what is and is not modelled.
