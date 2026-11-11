"""Scenario: "Once during each of your turns, you may play a permanent card you
own from outside the game or from your graveyard." (The Holodeck).

CR 400.11a: the sideboard is outside the game; CR 400.11c: a card there can be
affected only by what brings it in, this permission among them. CR 601.3 (cast)
and CR 305.1 (a land play, still the turn's land drop) are the two ways to
play. One use each of the controller's turns, shared by both zones; never on
an opponent's turn, never another player's card, never a nonpermanent card. No
other legal printing grants this (Scryfall, in the writing session; Wish's
resolution-time "play a card you own from outside the game" is a different
reader).

CR rules cited here were looked up with `mise run rules:find` in the writing
session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


CAST_PERMISSION = "Cast permission"


def cast(scenario, name, zone, *sources):
    card = scenario.find(name, zone, "alice")
    return scenario.game.cast(card, "alice", keyword=CAST_PERMISSION, mana_sources=list(sources))


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["The Holodeck", "Forest", "Forest", "Forest"],
            sideboard=["Grizzly Bears", "Lightning Bolt", "Swamp"],
            graveyard=["Llanowar Elves", "Plains"],
            library=["Island"] * 6,
        )
        .player("bob", sideboard=["Savannah Lions"], library=["Island"] * 6)
    )


def test_a_permanent_card_is_cast_from_outside_the_game():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    actions = legal_actions(scenario.game, "alice")
    bears = scenario.find("Grizzly Bears", Zone.SIDEBOARD, "alice")
    assert any(a.kind is ActionKind.CAST and a.card_id == bears.id for a in actions)
    cast(scenario, "Grizzly Bears", Zone.SIDEBOARD, *scenario.untapped_sources("Forest", "Forest"))
    scenario.pass_until_resolved()
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


def test_once_each_turn_across_both_zones():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast(scenario, "Grizzly Bears", Zone.SIDEBOARD, *scenario.untapped_sources("Forest", "Forest"))
    scenario.pass_until_resolved()
    with pytest.raises(ValueError):
        cast(scenario, "Llanowar Elves", Zone.GRAVEYARD, *scenario.untapped_sources("Forest"))
    with pytest.raises(ValueError):
        scenario.play_land("Plains", from_zone=Zone.GRAVEYARD)


def test_a_land_is_played_from_the_graveyard_as_the_land_drop():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.play_land("Plains", from_zone=Zone.GRAVEYARD)
    assert plains.zone is Zone.BATTLEFIELD
    with pytest.raises(ValueError):
        scenario.play_land("Swamp", from_zone=Zone.SIDEBOARD)


def test_a_land_is_played_from_outside_the_game():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamp = scenario.play_land("Swamp", from_zone=Zone.SIDEBOARD)
    assert swamp.zone is Zone.BATTLEFIELD


def test_a_nonpermanent_card_is_not_reached():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    with pytest.raises(ValueError):
        cast(scenario, "Lightning Bolt", Zone.SIDEBOARD, *scenario.untapped_sources("Forest"))


def test_not_on_an_opponents_turn():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    bears = scenario.find("Grizzly Bears", Zone.SIDEBOARD, "alice")
    assert not any(
        a.card_id == bears.id for a in legal_actions(scenario.game, "alice") if a.card_id
    )


def test_the_holodeck_is_usable_again_on_the_next_turn():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Plains", from_zone=Zone.GRAVEYARD)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    while not (scenario.turn.active_player == "alice" and scenario.step is Step.PRECOMBAT_MAIN):
        scenario.advance()
    for land in scenario.game.permanents_controlled_by("alice"):
        land.tapped = False
    cast(scenario, "Llanowar Elves", Zone.GRAVEYARD, *scenario.untapped_sources("Forest"))
    scenario.pass_until_resolved()
    assert scenario.creature("Llanowar Elves", "alice").zone is Zone.BATTLEFIELD
