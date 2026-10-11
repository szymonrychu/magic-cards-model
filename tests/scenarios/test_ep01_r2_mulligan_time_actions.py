"""Scenario: "Any time you could mulligan and this card is in your hand, you may
exile all the cards from your hand, then draw that many cards." (CR 103.5b: the
player may do it at a time they would declare whether they take a mulligan,
this need not be the first round; if they do it, they then declare.)
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

SEVEN = ["Island", "Island", "Forest", "Forest", "Swamp", "Mountain", "Plains"]


def _pregame(alice_hand, library):
    scenario = (
        Scenario()
        .player("alice", hand=list(alice_hand), library=list(library))
        .player("bob", hand=list(SEVEN), library=["Island"] * 20)
        .build()
    )
    scenario.game.begin_pregame("seed")
    assert scenario.game.turn.step is Step.MULLIGAN
    return scenario


def _names(cards):
    return [c.name for c in cards]


def test_the_seat_is_offered_the_action_while_a_declaration_is_owed():
    scenario = _pregame(["Serum Powder", *SEVEN[:6]], ["Mountain"] * 20)
    (offer,) = scenario.game.mulligan_time_options("alice")
    assert offer.source == "Serum Powder"
    assert scenario.game.mulligan_time_options("bob") == []


def test_performing_it_exiles_the_whole_hand_and_draws_that_many():
    scenario = _pregame(["Serum Powder", *SEVEN[:6]], ["Mountain"] * 20)
    (offer,) = scenario.game.mulligan_time_options("alice")
    scenario.game.take_mulligan_time_action("alice", offer.card)
    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Mountain"] * 7
    assert sorted(_names(c for c in scenario.game.exile if c.owner == "alice")) == sorted(
        ["Serum Powder", *SEVEN[:6]]
    )
    assert "alice" in scenario.game.awaiting_mulligan_declarations


def test_the_seat_still_declares_after_performing_it():
    scenario = _pregame(["Serum Powder", *SEVEN[:6]], ["Mountain"] * 20)
    (offer,) = scenario.game.mulligan_time_options("alice")
    scenario.game.take_mulligan_time_action("alice", offer.card)
    scenario.game.declare_mulligan("alice", False)
    assert scenario.player("alice").mulligans_taken == 0


def test_a_hand_without_the_card_is_refused():
    scenario = _pregame(SEVEN, ["Mountain"] * 20)
    with pytest.raises(ValueError, match="CR 103.5b"):
        scenario.game.take_mulligan_time_action("alice", scenario.player("alice").hand[0].id)


def test_it_is_not_offered_once_the_seat_has_kept():
    scenario = _pregame(["Serum Powder", *SEVEN[:6]], ["Mountain"] * 20)
    scenario.game.declare_mulligan("alice", False)
    assert scenario.game.mulligan_time_options("alice") == []


def test_it_is_offered_again_in_a_later_round():
    scenario = _pregame(["Serum Powder"] * 7, ["Serum Powder"] * 20)
    scenario.game.declare_mulligan("alice", True)
    scenario.game.declare_mulligan("bob", False)
    assert scenario.game.turn.step is Step.MULLIGAN
    hand = scenario.player("alice").hand
    assert hand and all(c.name == "Serum Powder" for c in hand)
    assert len(scenario.game.mulligan_time_options("alice")) == len(hand)


def test_an_unattended_seat_declines_by_default():
    scenario = _pregame(["Serum Powder", *SEVEN[:6]], ["Mountain"] * 20)
    scenario.game.settle_pregame()
    assert "Serum Powder" in _names(scenario.player("alice").hand)
    assert [c for c in scenario.game.exile if c.owner == "alice"] == []


def test_an_unattended_seat_can_be_scripted_to_use_it():
    scenario = _pregame(["Serum Powder", *SEVEN[:6]], ["Mountain"] * 20)
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.OPENING_HAND_ACTION,
            value=True,
            player="alice",
            source="Serum Powder",
        )
    )
    scenario.game.settle_pregame()
    assert _names(scenario.player("alice").hand) == ["Mountain"] * 7
    assert all(c.zone is Zone.EXILE for c in scenario.game.exile)
