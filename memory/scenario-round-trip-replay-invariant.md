# T10: the round-trip/replay invariant, and what it found (2026-09-07)

`tests/scenarios/conftest.py`'s `pytest_pyfunc_call` runs every scenario test
once for real, then - if it checkpointed a `Game` via `harness.checkpoint` -
a second time with `checkpoint` swapping in a decode of the first run's own
initial snapshot. Two literal runs of the same test body, not a recorded
command log: the test function's own body already is the command sequence,
and `ids.py`'s deterministic id allocator is what makes the replay mint the
same ids the first run did, from the same decoded starting point.

**Rejected design**: installing `game._allocate_id` as the process-wide
default allocator for the rest of a checkpointed test (so every uncovered
`Game` method's `new_id()` found it instead of `uuid4`). This broke
`test_legal_actions_mutates_nothing` on its own first, non-replayed run:
`machines/legal_actions.py` builds throwaway `Casting`/`CostPayment` objects
to judge affordability without ever touching the real game, and with the
default installed those speculative mints became persisted, observable state
(`Game.objects_created` advancing). Determinism has to be scoped to the
specific `Game` methods whose ids are actually kept - only
`Game._id_allocator_scope()`, opened per method, can tell a query from a
mutation apart.

**The dominant finding**: `ids.py`'s own docstring names a short, explicit
list of `Game` methods that open `_id_allocator_scope()` and claims nothing
else mints an id. Untrue - roughly 30 more methods across `models/game.py`,
`models/token.py`, and `machines/keywords.py` (`sacrifice`, `draw_cards`,
`discard_cards`, `put_into_graveyard`, `exile_permanent`/`exile_cards`,
`grant_play_permission`, `create_delayed_trigger`, `put_triggers_on_stack`,
`Game.emit` itself, `enter_the_battlefield`, `put_onto_battlefield`,
`cleanup_step`, `create_tokens`, `token_copy_of`, `cascade`, `dredge`,
`discard`, and others) mint ids with no scope open, falling back to plain
`uuid4()`. A live game never notices because it never compares itself to
another run of itself; T10's invariant does exactly that and found ~300
scenario failures from this one gap before the fixes landed. All fixed by
wrapping each method's body in `with self._id_allocator_scope():`, the same
idiom `destroy`/`sacrifice` already used - not a blanket transformation.

**A real, independent bug this surfaced**: `machines/keywords.cascade`'s
"put the exiled cards on the bottom in a random order" called
`random.Random(seed)` with `seed=None` from its only production caller
(`_cascade_effect`), reading OS entropy instead of `game.shuffle_seed`/
`game.shuffles_performed` the way every other "random order" clause in this
engine already does. Harmless-looking (order doesn't matter to `assert`s
that don't check it) until you replay the game and the bottomed cards land
in a different order every process - fixed to default to the game-seeded
convention when no explicit seed is given.

**A real modeling gap this surfaced**: `Game.copy_spell`/`_resolve_top_impl`
built a copy of a permanent spell as a plain `CardState` with `token`
flipped to `True` on resolution (CR 707.10f/111.13), never actually
promoting it to a `TokenState` instance. The live game never enforced CR
111.8 on it (a token that left the battlefield can't come back); a decoded
copy did, because decode reads the same `token` flag and rebuilds a genuine
`TokenState`. Fixed: `copy_spell` now builds a `TokenState` (`token=False`
while still a spell copy) whenever the original is a permanent.

**A real dump-crash bug this surfaced**: `DecisionScript.provider: Any = None`
had no `exclude=True` - the same fix `Match.card_resolver` already carries.
Any game with a live decision provider attached (the api's per-game mailbox,
or a test's own recording stub) crashed `model_dump(mode="json")` outright
with `PydanticSerializationError: Unable to serialize unknown type`. Fixed
the same way `card_resolver` was.

**Left as findings, not fixed** (both `xfail(strict=True)`, reasons in the
test files): `CardState._planeswalker_start_loyal`'s `mode="after"` validator
cannot distinguish "a permanent is genuinely entering the battlefield" from
"this object is being reconstructed by `model_validate`", so a planeswalker
sitting on the battlefield with zero loyalty for a real, deliberate reason
(`test_ral_monsoon_mage.py`'s bare `.transform()`) gets two loyalty counters
re-seeded onto it by a decode the live game never triggered. And four
`assert len({id(state.card) for state in copies}) == 1` deck-smoke
assertions test CPython object identity of `tests/cards.py`'s memoization
cache, which a JSON decode can never reproduce (two value-equal objects
never decode to one Python object) - not an engine defect at all, but the
replay run legitimately can't satisfy it either.

**Test-code-side gaps, fixed in the test files themselves, not the engine**:
several scenario tests reach past the harness into `Player`/`DelayedTriggers`
/`ContinuousEffects` methods directly (`Player.draw_opening_hand`,
`.draw_up_to`, `.mulligan`, `.bring_into_the_game`, `.move`/`.add`,
`CardState.move_to`, `.delayed_triggers.create`/`.fire`,
`.continuous_effects.create`) with no `Game` method's scope open around the
call. Each site now opens `game._id_allocator_scope()` itself (or is routed
through the `Game`-level wrapper that already does, like
`Game.create_delayed_trigger`).

Runtime: 55.5s baseline -> ~123s with the invariant on (round-trip always,
full replay by default; `MTG_SCENARIO_REPLAY=0` drops the replay half).
