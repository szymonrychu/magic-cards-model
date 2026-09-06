---
name: delayed-trigger-serialization-game-py-isolation
description: DelayedTrigger.effect became a DelayedEffectSpec union while game.py was locked by a concurrent worktree - a narrow before-validator bridges its 3 legacy call sites instead
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
owned it) while three call sites there still build `DelayedTrigger`s the old
way: warp's `effect="warp:exile"` and dash's/rebound's `callback=<function>`.
Rather than stop the whole task, `DelayedTrigger` grew one `model_validator
(mode="before")` that translates exactly those two legacy shapes into the new
`effect` field - a keyword rename (`callback` -> `effect`) plus "a bare string
is shorthand for `{kind: string}`" (only ever valid for a zero-argument
member). Every empty-closure spec also kept its old bare-function name as a
singleton instance (`return_subject_to_hand = ReturnSubjectToHand()`), so a
reference-by-name in `game.py` now hands over a real, serializable object
without that file changing a line. Both shims fail loud (`ValidationError`) on
anything outside that closed shape - not a revival of the deleted registry,
which they never consult.

Also surprising: the task's own requirement 7 claimed reflexive triggers
(`DelayedTriggers.create_reflexive`) "never persist" so need no spec. False -
`pending` (where a reflexive trigger's `DelayedTrigger` lives) is exactly as
persisted as `triggers`, and a reflexive ability sits on the stack, serializable,
for as long as any other trigger waiting on priority. Verified by tracing
`resolve_top`'s `effect_for` call, not by trusting the premise.

**How to apply:** when an isolation rule locks a file mid-refactor, look for a
translation seam (a keyword alias, a discriminator shorthand, an old name
repointed to a new object) before assuming the task is blocked - but keep the
seam narrow and loud, and say in code and in the report exactly what call
sites depend on it and what should replace it once the file unlocks.

Related: [[silent-default-dispatch-tables]], [[effect-registry-is-the-dominant-gap]].
