---
name: keyword-activation-round-trip-identity
description: making AbilityOnStack.keyword_activation/.unless_payment round-trip surfaced a second, subtler bug - a decoded KeywordActivation.card is a copy, not the battlefield object, so mutating it through .attach_to() silently misses the real game
metadata:
  type: project
---

**2026-09-07.** T4 of the stateless-library plan (`machines/triggers.py`)
typed `AbilityOnStack.keyword_activation: KeywordActivation | None` and
`.unless_payment: CostPayment | None`, dropping the `Any, exclude=True` that
had silently dropped both on every round trip (the same "a wrong game state
that looks right is worse than an unimplemented one" shape
`memory/silent-default-dispatch-tables.md` names).

`KeywordActivation` needed three things resolved first, all inside its own
`Any`/cyclic fields: `.game` (a live `Game`, still `exclude=True`, relinked by
`Game.model_post_init` walking `self.stack`/`self.pending_triggers` the same
way it already relinks `Player.game`), `.on_stack` (points back at the very
`AbilityOnStack` holding it - `exclude=True` to stop a dump recursing forever,
re-wired from the other side by a new `AbilityOnStack.model_post_init`), and
`.result` (stays `exclude=True`; a persisted ability is always pre-resolution
per `machines/decisions.py`'s pause-and-replay design, so it is never needed).
`unless_payment` took the "reduce to data" option: `CostPayment` was already
plain data once its own `.game` is excluded, and `_ward_effect` never reads
`.game` at all - only `.step`.

**The real surprise**, caught only by writing the round-trip test with an
actual assertion on the game state rather than "did it raise": `KeywordActivation.
card: CardState` is not `Any`/excluded and needed no type change to serialize,
but a JSON round trip still breaks it, because pydantic has no notion of
shared object identity across a dump. In the live path `activation.card` *is*
the exact same Python object as the equipment sitting in `game.battlefield`;
after a dump-and-decode they are two objects with the same `id` and nothing
else in common. `_equip_effect` called `activation.card.attach_to(creature)`
directly - on the live path that mutates the real permanent, on a decoded
copy it mutates a throwaway duplicate, and `game.find_by_id(cutter.id)` shows
the Equipment forever unattached with no error anywhere. Fixed by re-resolving
`activation.card` through `game.find_by_id` before mutating it, the same
CR 113.7a re-check `_equip_effect` already did for its *target* but not for
its own source. `_crew_effect`/`_cycling_effect` were already safe: neither
mutates through `activation.card` directly, only by id.

**How to apply:** typing a field correctly and getting a clean dump/decode is
not the same claim as "resolves identically" - a `CardState` (or any object)
reachable from two places in the same dump becomes two unrelated copies on
decode, and any effect that mutates one of those copies by reference rather
than by re-resolving through `game.find_by_id` will silently miss the real
game. The round-trip test has to assert on the *live* state the mutation was
supposed to reach (`game.find_by_id(id)`, not the handle the effect function
already held), or it proves nothing.

Related: [[silent-default-dispatch-tables]],
[[delayed-trigger-serialization-game-py-isolation]].
