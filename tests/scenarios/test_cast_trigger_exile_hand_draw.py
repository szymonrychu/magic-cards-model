"""Scenario: a cast trigger's optional cost is exiling the caster's whole
hand rather than paying mana or life - Herigast, Erupting Nullkite's own
"you may exile your hand. If you do, draw three cards."

Herigast, Erupting Nullkite: "When you cast this spell, you may exile your
hand. If you do, draw three cards." (Modern).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 118.12** - "[A player] may [do something]. If [that player] does,
  [effect]": exiling the hand is the cost, paid (or not) as the trigger
  resolves, before the "draw three cards" consequence.
- **CR 701.13a** - to exile an object is to move it to the exile zone.
- **CR 601.2i** - Herigast itself is already cast (on the stack) by the time
  its own trigger resolves, so "your hand" at that moment never includes the
  card that triggered this in the first place.
- **CR 608.2d** - a plain "may" is always legal to decline, and exiling zero
  cards is a legal way to accept it.

Read by the new `_parse_may_exile_hand_if_you_do_clause`
(`machines/effects.py`), the exile-a-whole-zone twin of the existing
mana/life/energy "you may pay `<cost>`. If you do, `<consequence>`." family -
none of which pay a resource at all here, so none of them matched.
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def _board(hand: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest", "Forest", "Forest", "Island"],
            hand=["Herigast, Erupting Nullkite", *hand],
            battlefield=["Wastes"] * 9,
        )
        .build()
    )


def test_paid_exiles_the_rest_of_the_hand_and_draws_three():
    scenario = _board(["Mountain", "Swamp"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True)
    sources = scenario.untapped_sources(*["Wastes"] * 9)

    scenario.cast_onto_stack("Herigast, Erupting Nullkite", *sources)
    scenario.pass_until_resolved()  # the cast trigger

    alice = scenario.player("alice")
    exiled_names = {state.name for state in scenario.game.exile if state.owner == "alice"}
    assert {"Mountain", "Swamp"} <= exiled_names
    assert len(alice.hand) == 3
    assert len(alice.library) == 1


def test_declined_keeps_the_hand_and_draws_nothing():
    scenario = _board(["Mountain", "Swamp"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False)
    sources = scenario.untapped_sources(*["Wastes"] * 9)

    scenario.cast_onto_stack("Herigast, Erupting Nullkite", *sources)
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert {state.name for state in alice.hand} == {"Mountain", "Swamp"}
    assert [state for state in scenario.game.exile if state.owner == "alice"] == []
    assert len(alice.library) == 4


def test_an_already_empty_hand_is_still_a_legal_yes_and_still_draws_three():
    """CR 608.2d: accepting an optional action never needs the action to do
    anything - Herigast itself has already left the hand for the stack
    (CR 601.2i) by the time this is asked, so with nothing else in hand the
    "yes" exiles zero cards and the draw still happens."""
    scenario = _board([])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True)
    sources = scenario.untapped_sources(*["Wastes"] * 9)

    scenario.cast_onto_stack("Herigast, Erupting Nullkite", *sources)
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert [state for state in scenario.game.exile if state.owner == "alice"] == []
    assert len(alice.hand) == 3
    assert len(alice.library) == 1
