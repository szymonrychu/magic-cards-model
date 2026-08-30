"""Cycling: an activated ability that functions in the hand (CR 702.29).

CR 702.29a: "Cycling is an activated ability that functions only while the card
with cycling is in a player's hand. 'Cycling [cost]' means "[Cost], Discard this
card: Draw a card.""

That zone is the whole point of this file. `Game.begin_activating` only ever
activates an ability of a battlefield permanent, so cycling had no execution
path at all; `machines/keywords.KeywordActivation` is the general form that
names the zone an ability functions in.

CR 702.29b keeps the ability from vanishing elsewhere: "Although the cycling
ability can be activated only if the card is in a player's hand, it continues to
exist while the object is on the battlefield and in all other zones."

CR 702.29e is typecycling, and CR 702.29f says a typecycling ability *is* a
cycling ability. The discard is part of the cost (CR 601.2h shape), which is why
the card is already in the graveyard by the time the draw happens.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import (
    KeywordActivation,
    cycle,
    cycling_abilities,
    cycling_activation,
)
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from


def board(**kwargs) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", **kwargs)
        .player("bob", battlefield=["Mountain"])
    )


def pay_with(*sources):
    def hook(payment):
        for source in sources:
            payment.tap_for_mana(source, mana_from(source))

    return hook


def test_the_cycling_ability_is_read_off_the_printed_line():
    """CR 702.1a: the cost is printed after the keyword, mana or sentence."""
    (censor,) = cycling_abilities(card("Censor"))
    assert censor.cost == "{U}"
    assert censor.cost_is_mana

    (wraith,) = cycling_abilities(card("Street Wraith"))
    assert wraith.cost == "Pay 2 life"
    assert not wraith.cost_is_mana


def test_cycling_discards_the_card_and_draws_one():
    """CR 702.29a, the whole ability."""
    scenario = board(hand=["Censor"], library=["Lightning Bolt"], battlefield=["Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    censor = scenario.find("Censor", Zone.HAND, "alice")
    (island,) = scenario.untapped_sources("Island")
    drawn = cycle(scenario.game, censor, "alice", pay_with(island))

    assert censor.zone is Zone.GRAVEYARD
    assert [state.name for state in drawn] == ["Lightning Bolt"]
    assert scenario.find("Lightning Bolt", Zone.HAND, "alice").zone is Zone.HAND


def test_a_life_payment_cycling_cost_is_paid_in_life():
    """Street Wraith prints its cost after an em dash: `Cycling—Pay 2 life.`"""
    scenario = board(hand=["Street Wraith"], library=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    wraith = scenario.find("Street Wraith", Zone.HAND, "alice")
    cycle(scenario.game, wraith, "alice")

    assert scenario.player("alice").life == 18
    assert wraith.zone is Zone.GRAVEYARD


def test_cycling_cannot_be_activated_from_the_battlefield():
    """CR 702.29a: "functions only while the card ... is in a player's hand"."""
    scenario = board(battlefield=["Striped Riverwinder", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    riverwinder = scenario.creature("Striped Riverwinder")
    activation = cycling_activation(scenario.game, riverwinder, "alice")

    assert "functions in the hand" in (activation.why_not() or "")
    with pytest.raises(ValueError, match="functions in the hand"):
        activation.begin_paying()


def test_the_ability_still_exists_on_the_battlefield():
    """CR 702.29b: it continues to exist, it just cannot be activated."""
    scenario = board(battlefield=["Striped Riverwinder"]).build()
    riverwinder = scenario.creature("Striped Riverwinder")
    assert cycling_abilities(riverwinder.card)


def test_cycling_uses_the_stack_and_can_be_responded_to():
    """It is an ordinary activated ability, so it is not a mana ability.

    CR 605.1a would take it off the stack if it added mana; it draws a card, so
    the ability sits there and the opponent gets a window - which is also why
    the card is in the graveyard before the draw happens.
    """
    scenario = board(hand=["Censor"], library=["Lightning Bolt"], battlefield=["Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    censor = scenario.find("Censor", Zone.HAND, "alice")
    (island,) = scenario.untapped_sources("Island")
    activation = cycling_activation(scenario.game, censor, "alice")
    payment = activation.begin_paying()
    payment.tap_for_mana(island, mana_from(island))
    payment.pay()

    on_stack = activation.activate()
    assert on_stack in scenario.game.stack
    assert censor.zone is Zone.GRAVEYARD  # the discard was a cost
    assert scenario.player("alice").hand == []

    activation.resolve()
    assert scenario.game.stack_is_empty
    assert [state.name for state in scenario.player("alice").hand] == ["Lightning Bolt"]


def test_a_cost_that_cannot_be_paid_leaves_the_card_in_hand():
    """CR 118.3: no resources, no payment - and no discard either."""
    scenario = board(hand=["Censor"], library=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    censor = scenario.find("Censor", Zone.HAND, "alice")
    activation = cycling_activation(scenario.game, censor, "alice")
    payment = activation.begin_paying()
    with pytest.raises(ValueError):
        payment.pay()

    assert censor.zone is Zone.HAND


def test_typecycling_searches_the_library_for_that_type():
    """CR 702.29e: "[Type]cycling [cost]" searches instead of drawing.

    CR 702.29f makes it a cycling ability all the same, so it shares every other
    rule - the hand-only zone and the discard as a cost.
    """
    scenario = board(
        hand=["Generous Ent"],
        library=["Lightning Bolt", "Forest", "Island"],
        battlefield=["Forest", "Forest"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    ent = scenario.find("Generous Ent", Zone.HAND, "alice")
    (ability,) = cycling_abilities(ent.card)
    assert ability.canonical == "Forestcycling"

    found = cycle(
        scenario.game, ent, "alice", pay_with(*scenario.untapped_sources("Forest", "Forest"))
    )

    assert ent.zone is Zone.GRAVEYARD
    assert [state.name for state in found] == ["Forest"]
    assert scenario.find("Forest", Zone.HAND, "alice").zone is Zone.HAND


def test_the_activation_is_the_general_form_for_any_zone():
    """The gap this closes: an activated ability that is not on the battlefield."""
    scenario = board(hand=["Censor"], battlefield=["Island"]).build()
    censor = scenario.find("Censor", Zone.HAND, "alice")
    activation = cycling_activation(scenario.game, censor, "alice")

    assert isinstance(activation, KeywordActivation)
    assert activation.zone is Zone.HAND
    assert activation.why_not() is None
