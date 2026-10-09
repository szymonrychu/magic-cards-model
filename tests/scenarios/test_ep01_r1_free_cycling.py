"""CR 702.29a / 118.9: a static ability that replaces the cost of cycling.

    New Perspectives - As long as you have seven or more cards in hand, you
    may pay {0} rather than pay cycling costs.

The condition is read when the cycling ability is activated (CR 602.2b, 611.3a);
the replaced cost covers every cycling cost, mana or not, typecycling included.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import cycle
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

FILLER = ["Grizzly Bears"] * 4


def _board(hand, **kwargs):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hand,
            library=["Lightning Bolt"] * 3,
            battlefield=["New Perspectives"],
            **kwargs,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_mana_cycling_cost_is_paid_with_nothing_at_seven_cards():
    scenario = _board(["Censor", "Street Wraith", "Ash Barrens", *FILLER[:4]])
    censor = scenario.find("Censor", Zone.HAND, "alice")
    drawn = cycle(scenario.game, censor, "alice")
    assert censor.zone is Zone.GRAVEYARD
    assert [state.name for state in drawn] == ["Lightning Bolt"]


def test_a_life_cycling_cost_is_replaced_too():
    scenario = _board(["Censor", "Street Wraith", "Ash Barrens", *FILLER[:4]])
    wraith = scenario.find("Street Wraith", Zone.HAND, "alice")
    cycle(scenario.game, wraith, "alice")
    assert scenario.game.player("alice").life == 20


def test_typecycling_is_replaced_as_well():
    scenario = _board(["Censor", "Street Wraith", "Ash Barrens", *FILLER[:4]])
    barrens = scenario.find("Ash Barrens", Zone.HAND, "alice")
    cycle(scenario.game, barrens, "alice")
    assert barrens.zone is Zone.GRAVEYARD


def test_with_six_cards_in_hand_the_cost_is_the_printed_one():
    scenario = _board(["Censor", "Street Wraith", *FILLER[:4]])
    censor = scenario.find("Censor", Zone.HAND, "alice")
    with pytest.raises(ValueError):
        cycle(scenario.game, censor, "alice")
    wraith = scenario.find("Street Wraith", Zone.HAND, "alice")
    cycle(scenario.game, wraith, "alice")
    assert scenario.game.player("alice").life == 18


def test_the_opponents_new_perspectives_does_nothing_for_you():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Censor", "Street Wraith", *FILLER], library=["Island"] * 3)
        .player("bob", battlefield=["New Perspectives"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wraith = scenario.find("Street Wraith", Zone.HAND, "alice")
    cycle(scenario.game, wraith, "alice")
    assert scenario.game.player("alice").life == 18


def test_the_cycling_action_is_listed_as_affordable_without_mana():
    from magic_cards_model.machines import legal_actions
    from magic_cards_model.models import ActionKind

    scenario = _board(["Censor", "Street Wraith", "Ash Barrens", *FILLER[:4]])
    censor = scenario.find("Censor", Zone.HAND, "alice")
    rows = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.card_id == censor.id and action.kind is ActionKind.ACTIVATE_OFF_ZONE
    ]
    assert rows, "cycling is listed"
    assert all(row.affordable.value != "no" for row in rows)


def test_the_same_cycling_action_is_unaffordable_at_six_cards():
    from magic_cards_model.machines import legal_actions
    from magic_cards_model.models import ActionKind

    scenario = _board(["Censor", "Street Wraith", *FILLER[:4]])
    censor = scenario.find("Censor", Zone.HAND, "alice")
    rows = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.card_id == censor.id and action.kind is ActionKind.ACTIVATE_OFF_ZONE
    ]
    assert rows
    assert all(row.affordable.value == "no" for row in rows)
