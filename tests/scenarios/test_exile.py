"""Scenario: exile.

The mechanic is the difference between exile and the graveyard. Swords to
Plowshares exiles, so the creature leaves for a shared zone nobody owns, and it
never touches its controller's graveyard on the way.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Swords to Plowshares"], battlefield=["Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_an_exiled_creature_goes_to_exile_not_the_graveyard():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)

    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.cast_and_resolve("Swords to Plowshares", plains, username="alice", targets=[bears])

    assert bears.zone is Zone.EXILE
    assert bears in scenario.game.exile
    assert "Grizzly Bears" not in scenario.battlefield_names()
    assert scenario.player("bob").graveyard == [], "exile is not the graveyard"


def test_exile_is_a_shared_zone():
    """Corner case: exile belongs to the game, not to a player."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)

    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.cast_and_resolve("Swords to Plowshares", plains, username="alice", targets=[bears])

    assert Zone.EXILE in scenario.game.shared_zones
    assert Zone.EXILE not in scenario.player("bob").zones
    assert scenario.find("Grizzly Bears", Zone.EXILE) is bears


def test_an_exiled_creature_arrives_untapped_and_undamaged():
    """Corner case: exile is a new object, so battlefield state is dropped."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    bears.tap()
    bears.mark_damage(1)

    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.cast_and_resolve("Swords to Plowshares", plains, username="alice", targets=[bears])

    assert bears.untapped
    assert bears.damage == 0


def test_a_scenario_can_start_with_cards_already_exiled():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Plains"], exile=["Grizzly Bears"])
        .player("bob")
        .build()
    )

    exiled = scenario.find("Grizzly Bears", Zone.EXILE)
    assert exiled.zone is Zone.EXILE
    assert "Grizzly Bears" not in scenario.battlefield_names()


def test_the_removal_spell_still_goes_to_the_graveyard():
    """Corner case: exiling something does not exile the spell that did it."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)

    (plains,) = scenario.untapped_sources("Plains", username="alice")
    swords = scenario.cast_and_resolve(
        "Swords to Plowshares", plains, username="alice", targets=[bears]
    )

    assert swords.zone is Zone.GRAVEYARD
    assert [state.name for state in scenario.player("alice").graveyard] == ["Swords to Plowshares"]


def _zones_containing(scenario: "Scenario", card) -> list[Zone]:
    """Every zone in the whole game state that currently lists this exact card.

    Used to prove a moved card is in exactly one zone - a card the engine
    duplicated across two zones would show up here twice.
    """
    found = []
    for zone, cards in scenario.game.shared_zones.items():
        if card in cards:
            found.append(zone)
    for player in scenario.game.players:
        for zone, cards in player.zones.items():
            if card in cards:
                found.append(zone)
    return found


def test_exiling_a_card_from_a_graveyard_leaves_the_graveyard():
    """`Game.exile_permanent` used to only remove from the battlefield, so a
    graveyard card it exiled ended up in both the graveyard and exile at once -
    the same card in two zones (CR 406.2's "from whatever zone it's currently
    in" says exile has to actually leave that zone)."""
    scenario = Scenario().player("alice", graveyard=["Grizzly Bears"]).player("bob").build()
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD)

    scenario.game.exile_permanent(bears)

    assert bears.zone is Zone.EXILE
    assert bears in scenario.game.exile
    assert bears not in scenario.player("alice").graveyard
    assert _zones_containing(scenario, bears) == [Zone.EXILE]


def test_exiling_a_permanent_from_the_battlefield_still_leaves_the_battlefield():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)

    scenario.game.exile_permanent(bears)

    assert bears.zone is Zone.EXILE
    assert bears in scenario.game.exile
    assert "Grizzly Bears" not in scenario.battlefield_names()
    assert _zones_containing(scenario, bears) == [Zone.EXILE]


def test_exiling_a_card_from_hand_leaves_the_hand():
    scenario = Scenario().player("alice", hand=["Grizzly Bears"]).player("bob").build()
    bears = scenario.find("Grizzly Bears", Zone.HAND)

    scenario.game.exile_permanent(bears)

    assert bears.zone is Zone.EXILE
    assert bears in scenario.game.exile
    assert bears not in scenario.player("alice").hand
    assert _zones_containing(scenario, bears) == [Zone.EXILE]


def test_returning_a_card_from_a_graveyard_to_hand_leaves_the_graveyard():
    """`Game.return_to_hand` had the identical bug shape as `exile_permanent`:
    only removing from the battlefield, so a Raise-Dead-style effect on a
    graveyard card would leave it in both the graveyard and the hand."""
    scenario = Scenario().player("alice", graveyard=["Grizzly Bears"]).player("bob").build()
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD)

    scenario.game.return_to_hand(bears)

    assert bears.zone is Zone.HAND
    assert bears in scenario.player("alice").hand
    assert bears not in scenario.player("alice").graveyard
    assert _zones_containing(scenario, bears) == [Zone.HAND]
