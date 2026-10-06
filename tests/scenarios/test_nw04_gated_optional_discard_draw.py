"""Scenario: "If you control a <subtype>, you may discard a card. If you do, draw
a card."

Take Out the Trash: "~ deals 3 damage to target creature or planeswalker. If
you control a Raccoon, you may discard a card. If you do, draw a card." The
leading "If <condition>," gates the optional-cost-then-"If you do" pair:

- the condition is checked as the spell resolves, not as it is cast
  (CR 608.2c reads instructions in order against the game as it now is);
- with the condition false the player is not offered the discard at all, so
  nothing is discarded and nothing is drawn;
- with it true the discard is optional (CR 608.2d), "If you do" refers to
  having discarded (so an empty hand draws nothing), and the draw follows.

Rules, each read in full with `mise run rules:find`:

- CR 608.2c - the controller follows the instructions in the order written;
  later text may depend on earlier text.
- CR 608.2d - an effect that offers choices has the player announce them while
  applying it; an impossible option can't be chosen.
- CR 608.2b - a spell with all its targets illegal doesn't resolve at all.
- CR 701.9a - to discard a card, move it from hand to graveyard.

Listed printing: Take Out the Trash.

No other printing legal in Modern, Pioneer or Standard puts a leading
"If <condition>," in front of a "you may discard ... If you do" pair (Scryfall
`o:` regex searches over the three formats return only this card), so the
nearest printings - Boundary Lands Ranger and Wandering Champion, whose gate
is an intervening "if" on a trigger - are checked to read handled alongside it
and the reader's generality over the discard count is shown on the text
itself (`test_the_reader_is_not_fitted_to_one_count`).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import parse_mixed_effect_for_spell
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


@pytest.mark.parametrize(
    "name", ["Take Out the Trash", "Boundary Lands Ranger", "Wandering Champion"]
)
def test_every_listed_and_sibling_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(*, alice_battlefield=(), alice_hand=(), bob_battlefield=("Hill Giant",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Take Out the Trash", *alice_hand],
            battlefield=[*["Mountain"] * 4, *alice_battlefield],
            library=["Forest", "Island", "Swamp", "Plains"],
        )
        .player(
            "bob",
            hand=["Lightning Bolt"],
            battlefield=[*bob_battlefield, "Mountain"],
            library=["Mountain"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _trash(scenario, target):
    return scenario.cast_and_resolve(
        "Take Out the Trash", username="alice", targets=[target], auto=True
    )


def _hand(scenario):
    return sorted(state.name for state in scenario.player("alice").hand)


def _may_questions(scenario):
    return [q for q in scenario.questions_asked() if q.kind.name == "MAY"]


def test_with_a_raccoon_the_controller_may_discard_and_draws():
    scenario = _board(alice_battlefield=["Coati Scavenger"], alice_hand=["Swamp"])
    giant = scenario.creature("Hill Giant", "bob")
    swamp = scenario.find("Swamp", Zone.HAND, "alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_discard(swamp, username="alice")

    _trash(scenario, giant)

    assert giant.zone is Zone.GRAVEYARD  # 3 damage to a 3/3
    assert swamp.zone is Zone.GRAVEYARD
    assert _hand(scenario) == ["Forest"]  # the top card of the library


def test_declining_the_discard_draws_nothing():
    scenario = _board(alice_battlefield=["Coati Scavenger"], alice_hand=["Swamp"])
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(False, username="alice")

    _trash(scenario, giant)

    assert giant.zone is Zone.GRAVEYARD
    assert _hand(scenario) == ["Swamp"]
    assert len(scenario.player("alice").library) == 4


def test_with_an_empty_hand_there_is_nothing_to_discard_and_nothing_is_drawn():
    scenario = _board(alice_battlefield=["Coati Scavenger"])
    giant = scenario.creature("Hill Giant", "bob")

    _trash(scenario, giant)

    assert _hand(scenario) == []
    assert len(scenario.player("alice").library) == 4


def test_without_a_raccoon_the_player_is_not_offered_the_discard():
    scenario = _board(alice_battlefield=["Grizzly Bears"], alice_hand=["Swamp"])
    giant = scenario.creature("Hill Giant", "bob")

    _trash(scenario, giant)

    assert giant.zone is Zone.GRAVEYARD
    assert _hand(scenario) == ["Swamp"]
    assert _may_questions(scenario) == []
    assert len(scenario.player("alice").library) == 4


def test_another_raccoon_printing_counts():
    scenario = _board(alice_battlefield=["Keen-Eyed Curator"], alice_hand=["Swamp"])
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_discard(scenario.find("Swamp", Zone.HAND, "alice"), username="alice")

    _trash(scenario, giant)

    assert _hand(scenario) == ["Forest"]


def test_the_raccoon_is_checked_as_the_spell_resolves_not_as_it_is_cast():
    scenario = _board(alice_battlefield=["Coati Scavenger"], alice_hand=["Swamp"])
    giant = scenario.creature("Hill Giant", "bob")
    coati = scenario.creature("Coati Scavenger", "alice")
    scenario.cast_onto_stack("Take Out the Trash", username="alice", targets=[giant], auto=True)
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[coati],
    )
    scenario.resolve_top()  # the Bolt kills the Raccoon
    assert coati.zone is Zone.GRAVEYARD

    scenario.resolve_top()  # Take Out the Trash

    assert giant.zone is Zone.GRAVEYARD
    assert _may_questions(scenario) == []
    assert _hand(scenario) == ["Swamp"]


def test_a_raccoon_that_arrives_before_resolution_counts():
    scenario = _board(alice_hand=["Swamp", "Coati Scavenger"])
    giant = scenario.creature("Hill Giant", "bob")
    scenario.put_onto_battlefield("Coati Scavenger", username="alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_discard(scenario.find("Swamp", Zone.HAND, "alice"), username="alice")

    _trash(scenario, giant)

    assert len(scenario.player("alice").library) == 3


def test_the_damage_hits_a_planeswalker_and_the_gate_still_applies():
    scenario = _board(
        alice_battlefield=["Coati Scavenger"],
        alice_hand=["Swamp"],
        bob_battlefield=["Jace Beleren"],
    )
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_discard(scenario.find("Swamp", Zone.HAND, "alice"), username="alice")

    _trash(scenario, jace)

    assert jace.loyalty == 0 or jace.zone is Zone.GRAVEYARD
    assert _hand(scenario) == ["Forest"]


def test_when_the_target_is_gone_the_spell_does_nothing_and_nothing_is_looted():
    scenario = _board(alice_battlefield=["Coati Scavenger"], alice_hand=["Swamp"])
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_onto_stack("Take Out the Trash", username="alice", targets=[giant], auto=True)
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[giant],
    )
    scenario.resolve_top()
    scenario.resolve_top()

    assert _may_questions(scenario) == []
    assert _hand(scenario) == ["Swamp"]


def test_the_reader_is_not_fitted_to_one_count():
    assert parse_mixed_effect_for_spell(
        "If you control a Raccoon, you may discard two cards. If you do, draw two cards."
    )
    assert parse_mixed_effect_for_spell(
        "Take Out the Trash deals 3 damage to target creature or planeswalker. "
        "If you control a Raccoon, you may discard a card. If you do, draw a card."
    )


def test_a_gate_the_engine_cannot_read_leaves_the_pair_unread():
    assert not parse_mixed_effect_for_spell(
        "If the moon is full, you may discard a card. If you do, draw a card."
    )
