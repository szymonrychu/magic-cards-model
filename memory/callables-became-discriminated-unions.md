---
name: callables-became-discriminated-unions
description: Why a persisted callable field became a pydantic discriminated union on kind, not a keyed registry - a keyed registry still defaults silently on decode, and a key alone cannot carry an effect's own captured parameters
metadata:
  type: project
---

**2026-09-07.** The stateless-library work found three fields that had to
survive `Game.model_dump(mode="json")` and did not: `ContinuousEffect.selector`
/ `.modification` / `.condition` (`machines/layers.py`), `DelayedTrigger.effect`
(`machines/delayed.py`), and `AbilityOnStack.keyword_activation` /
`.unless_payment`. Each used to be a bare Python closure, `exclude=True`'d so
it never even attempted to survive a dump - which is worse than a crash: a
decoded game silently lost the behaviour with no error at all.

A name-keyed registry (`selector_key: str`, looked up in a module-level
`SELECTORS: dict[str, Callable]`) was the obvious alternative and was rejected.
It still fails "decode any game state" in exactly the shape
`memory/silent-default-dispatch-tables.md` already named as this codebase's
dominant defect class: the decoded dict yields a key, and a `dict.get()` that
misses on an unknown key defaults to a no-op rather than refusing. A pydantic
discriminated union on `kind` (`Field(discriminator="kind")`, see
`machines/layers.py`'s `Selector`/`Modification`/`Count` and
`machines/delayed.py`'s `DelayedEffectSpec`) refuses at decode instead, with a
validation error naming the tag it does not recognise - the same fail-closed
shape `Game.schema_version` already chose over a defaulted field (see
`memory/game-schema-version-fail-closed.md`).

The other reason a key alone could never have worked: the closures being
replaced were not pure dispatch, they closed over per-instance data - a
`CountOtherCreaturesNamed`'s name, a `PermanentsControlledByWithCounters`'s
username, `ExileWarped`'s subject id. A string key has nowhere to put that. A
discriminated union subclass carries its own typed fields alongside `kind`, so
the union member *is* the closure's captured state, made data. That is what
actually made the old closures unserializable in the first place - not that
they were callables in the abstract, but that they carried per-instance
parameters a lookup key cannot express.

Not every callable in this codebase needed this treatment.
`machines/replacement.py`'s `CardReplacement` (`applies`/`apply`, both plain
`Callable` fields) is still a dataclass with bare closures, correctly: it is
never persisted on `Game` state. `parsed_card_replacements` rebuilds it fresh
from the card's own name on every query, so it was never subject to the
round-trip requirement at all. The distinguishing question is not "is this a
callable" but "does this value have to survive a `model_dump` of `Game`" - the
same three name-keyed registries `memory/effect-registry-is-the-dominant-gap.md`
already flagged (`effects.py`'s `EFFECTS`/`TRIGGER_EFFECTS`/`ACTIVATED_EFFECTS`,
`layers.LAYER_EFFECTS`, `replacement.REPLACEMENTS`) stay exactly as they were,
keyed by card name, because none of them is ever written into a `Game`
snapshot - they are re-derived from the card on the battlefield every time,
which is a different problem (the dominant coverage gap, not a serialization
one) left for later work.

Related: [[silent-default-dispatch-tables]],
[[game-schema-version-fail-closed]], [[effect-registry-is-the-dominant-gap]],
[[delayed-trigger-serialization-game-py-isolation]].
