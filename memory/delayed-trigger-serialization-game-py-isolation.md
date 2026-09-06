---
name: delayed-trigger-serialization-game-py-isolation
description: DelayedTrigger.effect became a DelayedEffectSpec union while game.py was locked by a concurrent worktree - a narrow before-validator bridged its 3 legacy call sites until the lock lifted and T3b deleted it
metadata:
  type: project
---

**2026-09-07.** T3 of the stateless-library plan (`machines/delayed.py`)
deleted `DelayedTrigger.callback` (`exclude=True`, silently dropped by
`model_dump`) and the string-keyed `DELAYED_EFFECTS` registry, replacing both
with `DelayedTrigger.effect: DelayedEffectSpec` - a `kind`-discriminated union
of 22 frozen pydantic models, one per callback/registry entry, mirroring what
commit 739ee2b already did for `machines/layers.py`'s continuous effects.

The task's own isolation rule locked `models/game.py` (a concurrent worktree
owned it) while three call sites there still built `DelayedTrigger`s the old
way: warp's `effect="warp:exile"` and dash's/rebound's `callback=<function>`.
Rather than stop the whole task, `DelayedTrigger` grew one `model_validator
(mode="before")` that translated exactly those two legacy shapes into the new
`effect` field for as long as `models/game.py` stayed off limits.

**2026-09-07, later the same day (T3b).** The lock lifted. All three
`models/game.py` sites (`_create_resolution_delayed_triggers`'s warp and dash
branches, `_create_rebound_delayed_trigger`) were converted to build the spec
directly: `effect=ExileWarped()`, `effect=return_subject_to_hand`, `effect=
rebound_recast` - the same singleton instances the shim used to translate
`callback=` into, now passed under their real keyword. A grep of `src/` and
`tests/` for `DelayedTrigger(` plus any `callback=`/bare-string `effect=`
confirmed these were still the only three legacy-shape sites (the other
`callback=` hits are `machines/effects.py`/`machines/replacement.py` calling
`Game.create_reflexive_trigger`/`DelayedTriggers.create_reflexive`, which
already forwarded to `effect=callback` internally and were never part of the
shim; the `effect="..."` hits in `machines/keywords.py` are plain ability-text
strings for an unrelated helper, not `DelayedEffectSpec`).

With no caller left needing translation, the `_accept_legacy_effect_shapes`
before-validator was deleted from `DelayedTrigger` entirely, along with the
module-docstring paragraph describing it. `mise run test` stayed at 5773
passed / 72 skipped / 1 xfailed (same as baseline) and `mise run lint` stayed
clean - the shim's removal changed no behaviour, only closed the string-keyed
door back up.

Also surprising, from the original T3: the task's own requirement 7 claimed
reflexive triggers (`DelayedTriggers.create_reflexive`) "never persist" so
need no spec. False - `pending` (where a reflexive trigger's `DelayedTrigger`
lives) is exactly as persisted as `triggers`, and a reflexive ability sits on
the stack, serializable, for as long as any other trigger waiting on
priority. Verified by tracing `resolve_top`'s `effect_for` call, not by
trusting the premise.

**How to apply:** when an isolation rule locks a file mid-refactor, look for a
translation seam (a keyword alias, a discriminator shorthand, an old name
repointed to a new object) before assuming the task is blocked - but keep the
seam narrow and loud, say in code and in the report exactly what call sites
depend on it and what should replace it once the file unlocks, and then
actually go back and delete the seam once it does. A shim with an expiry
condition that nobody checks is exactly as much technical debt as one with no
expiry at all.

Related: [[silent-default-dispatch-tables]], [[effect-registry-is-the-dominant-gap]].
