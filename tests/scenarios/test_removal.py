"""Scenario: removal by damage, and the state-based action that kills.

The mechanic is CR 704.5g - a creature with lethal marked damage is destroyed.
Nothing in Lightning Bolt's text kills anything; the damage sits there and the
next state-based action check does the killing.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def board() -> Scenario:
    """Bob has a 2/2 out; alice holds a Bolt. Questing Beast is a 4/4."""
    return (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_lethal_damage_sends_the_creature_to_the_graveyard():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    assert bears.toughness == 2

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert bears.damage == 0, "damage is wiped when it changes zones"
    assert bears.zone is Zone.GRAVEYARD
    assert "Grizzly Bears" not in scenario.battlefield_names()
    assert [state.name for state in scenario.player("bob").graveyard] == ["Grizzly Bears"]


def test_the_bolt_itself_ends_up_in_its_casters_graveyard():
    """Corner case: the removal spell and the creature go to different graveyards."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert bolt.zone is Zone.GRAVEYARD
    assert [state.name for state in scenario.player("alice").graveyard] == ["Lightning Bolt"]


def test_damage_short_of_lethal_leaves_the_creature_alive():
    """Corner case: a 4/4 shrugs off three damage, and the damage stays marked."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Questing Beast"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beast = scenario.find("Questing Beast", Zone.BATTLEFIELD)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[beast])

    assert beast.zone is Zone.BATTLEFIELD
    assert beast.damage == 3
    assert not beast.has_lethal_damage


def test_damage_accumulates_until_it_is_lethal():
    """Corner case: two Bolts kill the 4/4 that one could not."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Questing Beast"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beast = scenario.find("Questing Beast", Zone.BATTLEFIELD)
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountains[0], username="alice", targets=[beast])
    assert beast.zone is Zone.BATTLEFIELD

    scenario.cast_and_resolve("Lightning Bolt", mountains[1], username="alice", targets=[beast])

    assert beast.zone is Zone.GRAVEYARD


def test_state_based_actions_are_checked_without_anyone_asking():
    """The creature dies during resolution, not when a caller remembers to check."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    # No explicit check_state_based_actions call anywhere in this test.
    assert bears.zone is Zone.GRAVEYARD


def test_a_creature_that_leaves_and_returns_has_no_damage():
    """Corner case: damage does not follow a card across zones."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    bears.mark_damage(1)

    scenario.game.destroy(bears)

    assert bears.damage == 0
