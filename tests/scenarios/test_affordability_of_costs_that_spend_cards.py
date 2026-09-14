"""Affordability of a cast whose cost spends cards rather than mana.

A pitch cost ("exile a blue card from your hand"), an evoke cost that exiles a
card, and a mandatory "as an additional cost, sacrifice a creature" are all
paid with objects. `legal_actions` has to say whether the objects are there,
and it has to say the same thing `Game.cast` then does.

Rules, each read in full with `mise run rules:find` in the session that wrote
this file:

- **CR 601.2a** - to propose a cast the player "first moves that card ... from
  where it is to the stack", so by the time the cost is paid (CR 601.2h) the
  spell is no longer in the hand and cannot pitch itself.
- **CR 118.3** - "A player can't pay a cost without having the necessary
  resources to pay it fully."
- **CR 118.9 / 118.9d** - an alternative cost is paid rather than the mana
  cost, and additional costs still apply to it.
- **CR 118.8 / 118.8b** - additional costs are part of what is paid; only an
  optional one may be left out.
- **CR 601.2f** - the total cost is the mana cost or alternative cost plus all
  additional costs.
"""

import pytest

from magic_cards_model.machines import Step, legal_actions, payability
from magic_cards_model.models import ActionKind, Affordability, Zone
from tests.scenarios.harness import Scenario


def _board(hand, battlefield=(), bob_battlefield=()):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=list(battlefield))
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _rows(scenario, name):
    card = scenario.find(name, Zone.HAND, "alice")
    return [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.card_id == card.id and action.kind is ActionKind.CAST
    ]


def _alternative_row(scenario, name):
    (row,) = [row for row in _rows(scenario, name) if row.alternative_cost is not None]
    return row


def _plain_row(scenario, name):
    (row,) = [row for row in _rows(scenario, name) if row.alternative_cost is None]
    return row


# --------------------------------------------------------------------------
# A pitch cost: "exile a blue card from your hand rather than pay"
# --------------------------------------------------------------------------


def test_force_of_will_alone_cannot_pitch_itself():
    scenario = _board(["Force of Will"])

    row = _alternative_row(scenario, "Force of Will")

    assert row.affordable is Affordability.NO
    assert "found 0 eligible" in (row.unaffordable_reason or "")
    assert not payability(
        scenario.game, "alice", scenario.find("Force of Will", Zone.HAND, "alice")
    ).payable


def test_force_of_will_with_another_blue_card_can_pitch():
    scenario = _board(["Force of Will", "Preordain"])

    row = _alternative_row(scenario, "Force of Will")

    assert row.affordable is Affordability.YES
    assert payability(
        scenario.game, "alice", scenario.find("Force of Will", Zone.HAND, "alice")
    ).payable


def test_a_nonblue_card_does_not_count():
    scenario = _board(["Force of Will", "Lightning Bolt"])

    assert _alternative_row(scenario, "Force of Will").affordable is Affordability.NO


def test_the_same_template_on_an_off_pool_card():
    """Snapback prints the pitch without Force of Will's life payment."""
    alone = _board(["Snapback"])
    with_blue = _board(["Snapback", "Preordain"])

    assert _alternative_row(alone, "Snapback").affordable is Affordability.NO
    assert _alternative_row(with_blue, "Snapback").affordable is Affordability.YES


def test_a_count_of_two_needs_two_other_cards():
    """Allosaurus Rider exiles two green cards; itself plus one is not two."""
    one = _board(["Allosaurus Rider", "Llanowar Elves"])
    two = _board(["Allosaurus Rider", "Llanowar Elves", "Wood Elves"])

    assert _alternative_row(one, "Allosaurus Rider").affordable is Affordability.NO
    assert _alternative_row(two, "Allosaurus Rider").affordable is Affordability.YES


# --------------------------------------------------------------------------
# Evoke whose cost is exiling a card
# --------------------------------------------------------------------------


def test_solitude_alone_cannot_be_evoked_and_the_cast_agrees():
    scenario = _board(["Solitude"])
    solitude = scenario.find("Solitude", Zone.HAND, "alice")

    assert _alternative_row(scenario, "Solitude").affordable is Affordability.NO
    with pytest.raises(ValueError):
        scenario.game.cast(solitude, "alice", alternative_cost="Evoke")
    assert solitude.zone is Zone.HAND


def test_solitude_with_a_white_card_can_be_evoked_and_the_cast_agrees():
    scenario = _board(["Solitude", "Swords to Plowshares"])
    solitude = scenario.find("Solitude", Zone.HAND, "alice")
    swords = scenario.find("Swords to Plowshares", Zone.HAND, "alice")

    assert _alternative_row(scenario, "Solitude").affordable is Affordability.YES
    scenario.game.cast(solitude, "alice", alternative_cost="Evoke", choosing=[swords])
    assert swords.zone is Zone.EXILE


def test_grief_evoke_counts_another_black_card():
    alone = _board(["Grief"])
    with_black = _board(["Grief", "Thoughtseize"])

    assert _alternative_row(alone, "Grief").affordable is Affordability.NO
    assert _alternative_row(with_black, "Grief").affordable is Affordability.YES


# --------------------------------------------------------------------------
# A mandatory additional cost (CR 118.8, 601.2f)
# --------------------------------------------------------------------------


def test_a_sacrifice_as_an_additional_cost_needs_a_creature():
    scenario = _board(["Bone Splinters"], battlefield=["Swamp"], bob_battlefield=["Grizzly Bears"])

    row = _plain_row(scenario, "Bone Splinters")

    assert row.affordable is Affordability.NO
    assert row.cost is not None and "sacrifice a creature" in row.cost


def test_a_sacrifice_as_an_additional_cost_with_a_creature_is_affordable():
    scenario = _board(
        ["Bone Splinters"],
        battlefield=["Swamp", "Llanowar Elves"],
        bob_battlefield=["Grizzly Bears"],
    )

    assert _plain_row(scenario, "Bone Splinters").affordable is Affordability.YES
