"""Scenario: an activated ability granted to a card in exile, activated from
exile (Q, Stacking the Deck).

"When Q enters, shuffle your library, then exile cards from the top of your
library until you exile a nonland card. That nonland card gains "Exile a card
from your hand: Create a copy of this card. You may cast the copy. Activate
only during your turn and only if this card is exiled.""

CR 113.6b: an ability that states which zones it functions in functions only
from those zones - "only if this card is exiled" puts it in exile. CR 707.12:
the copy is created in the zone the card is in and cast while the ability
resolves, paying its mana cost; CR 707.10a: a copy not cast ceases to exist.
CR 400.7: the grant belongs to that object in exile and ends when it leaves.
No other legal printing grants an exiled card an ability like this (Scryfall,
in the writing session); the corner cases vary timing and zone instead.

CR rules cited here were looked up with `mise run rules:find` in the writing
session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_zone_activation
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario

GRANTED = (
    "Exile a card from your hand: Create a copy of this card. You may cast the copy. "
    "Activate only during your turn and only if this card is exiled."
)


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Q, Stacking the Deck", "Island", "Island"],
            battlefield=["Mountain"] * 4 + ["Forest"] * 4,
            library=["Forest", "Grizzly Bears", "Forest", "Forest"],
        )
        .player("bob", library=["Island"] * 5)
    )


def q_enters(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Q, Stacking the Deck", *scenario.untapped_sources(*["Mountain"] * 4))
    scenario.pass_until_resolved()
    return scenario.find("Grizzly Bears", Zone.EXILE, "alice")


def activate(scenario, card, paid_with):
    activation = off_zone_activation(scenario.game, card, "alice", 0, exiling=[paid_with])
    activation.begin_paying().pay()
    activation.activate()
    scenario.pass_until_resolved()


def test_q_exiles_down_to_the_one_nonland_card_and_grants_it_the_ability():
    scenario = board().build()
    bears = q_enters(scenario)
    assert bears.granted_ability_texts == (GRANTED,)
    library = scenario.player("alice").library
    assert all(card.card.is_land for card in library), "nothing past the nonland card moved"


def test_the_granted_ability_casts_a_copy_and_keeps_the_original_in_exile():
    scenario = board().build()
    bears = q_enters(scenario)
    island = scenario.find("Island", Zone.HAND, "alice")
    scenario.will_take_the_may(True)
    activate(scenario, bears, island)
    assert island.zone is Zone.EXILE, "the cost: a card exiled from the hand"
    assert scenario.stack_names() == ["Grizzly Bears"], "the copy is a spell on the stack"
    scenario.pass_until_resolved()
    copies = [p for p in scenario.game.battlefield if p.name == "Grizzly Bears"]
    assert len(copies) == 1 and copies[0].controller == "alice"
    assert bears.zone is Zone.EXILE
    assert bears.granted_ability_texts == (GRANTED,), "it can be activated again"


def test_a_declined_copy_ceases_to_exist():
    scenario = board().build()
    bears = q_enters(scenario)
    scenario.will_take_the_may(False)
    activate(scenario, bears, scenario.find("Island", Zone.HAND, "alice"))
    assert [c for c in scenario.game.exile if c.name == "Grizzly Bears"] == [bears]
    assert scenario.stack_names() == []


def test_the_granted_ability_is_refused_on_an_opponents_turn():
    scenario = board().build()
    bears = q_enters(scenario)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    with pytest.raises(ValueError):
        activation = off_zone_activation(
            scenario.game, bears, "alice", 0, exiling=[scenario.find("Island", Zone.HAND, "alice")]
        )
        activation.begin_paying().pay()
        activation.activate()


def test_q_stacking_the_deck_a_library_of_lands_grants_nothing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Q, Stacking the Deck"],
            battlefield=["Mountain"] * 4,
            library=["Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Q, Stacking the Deck", *scenario.untapped_sources(*["Mountain"] * 4))
    scenario.pass_until_resolved()
    assert scenario.player("alice").library == []
    assert all(not card.granted_ability_texts for card in scenario.game.exile)
