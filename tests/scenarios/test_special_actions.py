"""Scenario: special actions, specifically playing a land.

The mechanic is CR 116: a special action does not use the stack and nobody gets
priority in response. Playing a land is the one that matters most.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Forest", "Mountain", "Grizzly Bears"], library=["Forest"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
    )


def test_playing_a_land_puts_it_straight_onto_the_battlefield():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.play_land("Forest")

    assert forest.zone is Zone.BATTLEFIELD
    assert "Forest" in scenario.battlefield_names()
    assert scenario.game.stack_is_empty, "a land never uses the stack"


def test_playing_a_land_does_not_pass_priority():
    """The mechanic under test: no window opens for the opponent."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.priority_holder == "alice"

    scenario.play_land("Forest")

    assert scenario.priority_holder == "alice", "bob never got a chance to respond"
    assert scenario.game.priority is not None
    assert scenario.game.priority.passes == 0


def test_only_one_land_per_turn():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Forest")

    assert not scenario.game.can_play_land("alice")
    with pytest.raises(ValueError, match="cannot play a land"):
        scenario.play_land("Mountain")

    assert scenario.find("Mountain", Zone.HAND), "the second land stays in hand"


def test_lands_are_sorcery_speed():
    """Corner case: not in the upkeep, not during combat."""
    scenario = board().build()
    scenario.start_at(Step.UPKEEP)

    assert not scenario.game.can_play_land("alice")
    with pytest.raises(ValueError, match="cannot play a land"):
        scenario.play_land("Forest")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert not scenario.game.can_play_land("alice")


def test_a_land_cannot_be_played_with_something_on_the_stack():
    """Corner case: sorcery timing means an empty stack too."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])

    assert not scenario.game.can_play_land("alice")


def test_the_non_active_player_cannot_play_a_land():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert not scenario.game.can_play_land("bob")


def test_only_lands_can_be_played_as_a_land():
    """Corner case: a creature is not a land, whatever the caller thinks."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError, match="is not a land"):
        scenario.play_land("Grizzly Bears")


def test_a_land_played_this_turn_is_available_for_mana():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.play_land("Forest")

    assert forest.untapped
    assert scenario.untapped_sources("Forest") == [forest]
