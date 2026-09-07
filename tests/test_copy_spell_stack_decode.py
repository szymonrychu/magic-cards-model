"""Defect 2: a copy of a permanent spell, still on the stack, must decode as
a `TokenState` even though it is not yet a token.

`Game.copy_spell` (`models/game.py`) builds the copy with `state_type =
TokenState if spell.is_permanent else CardState`, and sets `token=False` on
purpose: CR 707.10f - "As that copy resolves, it ceases being a copy of a
spell and becomes a token permanent" - and CR 111.13 says the same from the
token side, so while the copy still sits on the stack it genuinely is not a
token yet. `token` only flips to `True` once `Game._resolve_top_impl` resolves
it (`models/game.py`, the `spell.token = True` line just below
`copy_spell`'s own docstring).

`CardState._resolve_token_subclass` used to key a decode's choice of class
solely on `data["token"]`. A game dumped while such a copy sits on the stack -
an ordinary state, priority just passing around it - carried `token: false`
for an object that is, in every other respect, a `TokenState`, so the decode
rebuilt it as a plain `CardState` and threw away `TokenState.move_to`'s CR
111.8 override before the object ever got a chance to need it.

Sage of the Skies is the one printing in the pool with a "copy this spell"
clause (`machines/effects.py`'s `_parse_copy_this_spell_clause`), but this
test calls `Game.copy_spell` directly on a real cast spell rather than routing
through Sage's own intervening-if cast trigger, since the trigger's own
condition (having cast another spell earlier this turn) is incidental to what
this test is about - `copy_spell` is the real, public engine method the
trigger itself calls, not a stand-in for it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.game import Game
from magic_cards_model.models.token import TokenState
from tests.scenarios.harness import Scenario


def test_a_copy_of_a_permanent_spell_survives_a_decode_as_a_tokenstate():
    scenario = (
        Scenario()
        .player("alice", hand=["Sage of the Skies"], battlefield=["Plains", "Plains", "Plains"])
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    original = scenario.cast_onto_stack("Sage of the Skies", *plains)

    copy = scenario.game.copy_spell(original, "alice")
    assert isinstance(copy, TokenState), "copy_spell already builds a TokenState in memory"
    assert copy.token is False, "CR 707.10f/111.13 - not yet a token while still on the stack"
    assert copy.zone is Zone.STACK

    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))
    decoded_copy = next(item for item in decoded.stack if item.id == copy.id)

    assert isinstance(decoded_copy, TokenState), (
        "a copy of a permanent spell, still on the stack, decoded back as a "
        "plain CardState - CR 111.8's protection is gone the moment it "
        "becomes a token, because TokenState.move_to's override no longer "
        "exists on this object"
    )
    assert decoded_copy.token is False, (
        "state_class must decide the class independently of token - the "
        "object is still, correctly, not a token yet"
    )

    # Resolve it (CR 707.10f/CR 608.3f): it becomes a real token permanent.
    resolved = decoded.resolve_top()
    assert resolved.token is True
    assert isinstance(resolved, TokenState), (
        "the object that started resolving was a TokenState; resolving it "
        "must not somehow change its class"
    )

    # CR 111.8, exercised directly the same way
    # test_module_state_survives_a_cold_decode.py exercises it for an
    # ordinary token: the first move off the battlefield is allowed, and
    # TokenState.move_to's override refuses the next one. A plain CardState
    # has no such refusal and would simply reassign `zone`.
    resolved.move_to(Zone.GRAVEYARD)
    assert resolved.left_the_battlefield
    resolved.move_to(Zone.HAND)
    assert resolved.zone is Zone.GRAVEYARD, "CR 111.8: a token that left the battlefield stays put"
