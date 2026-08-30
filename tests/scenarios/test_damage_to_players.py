"""Scenario: damage aimed at a player, and losing the game to it.

The mechanic is CR 120.3a - damage dealt to a player by a source without
infect causes that player to lose that much life (CR 119.2 is the general
statement) - and CR 704.5a, the state-based action that removes a
player at zero or less life from the game. Together they are the only way this
engine can currently end a game other than a concession.

Nothing about the loss happens when the damage is dealt: the life goes away
during resolution, and the player leaves the game the next time state-based
actions are checked (CR 704.3), which resolution does on its way out.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def burn(bob_life: int = 20, bolts: int = 1) -> Scenario:
    """Alice holds Bolts and the Mountains to cast them; bob has a 2/2 out."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"] * bolts,
            battlefield=["Mountain"] * bolts,
        )
        .player("bob", life=bob_life, battlefield=["Grizzly Bears"])
    )


def test_a_bolt_to_the_face_takes_three_life():
    """The happy path: three damage to a player is three life (CR 119.2, 120.3a)."""
    scenario = burn().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    bolt = scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.player("bob").life == 17
    assert bolt.zone is Zone.GRAVEYARD
    assert not scenario.game.is_over


def test_a_bolt_to_the_face_leaves_the_creature_alone():
    """Corner case: the same card, the other choice of target (CR 115.1).

    "Any target" is chosen on announcement, so a Bolt pointed at bob does
    nothing whatsoever to the Bears standing next to him.
    """
    scenario = burn().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert bears.damage == 0
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 17


def test_a_bolt_at_the_creature_leaves_the_player_alone():
    """The other half of the split: the creature dies, bob is untouched."""
    scenario = burn().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


def test_two_bolts_can_be_split_between_a_creature_and_a_face():
    """Corner case: one Bolt each way in one turn, neither affecting the other."""
    scenario = burn(bolts=2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountains[0], username="alice", targets=[bears])
    scenario.cast_and_resolve("Lightning Bolt", mountains[1], username="alice", targets=["bob"])

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


def test_a_player_reduced_to_exactly_zero_loses_the_game():
    """CR 704.5a is zero *or less*, so exactly nothing left is still a loss."""
    scenario = burn(bob_life=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.player("bob").life == 0
    assert scenario.game.winner == "alice"
    assert scenario.game.is_over


def test_a_player_driven_below_zero_loses_and_keeps_the_negative_total():
    """Corner case: damage is not capped at the life total.

    Excess damage is dealt; the life total goes negative and the player loses
    all the same. Nothing rounds it up to zero.
    """
    scenario = burn(bob_life=2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.player("bob").life == -1
    assert scenario.game.winner == "alice"


def test_a_player_already_at_zero_life_loses_at_the_next_check():
    """Corner case: the loss is a state-based action, not part of the damage.

    Bob starts at zero, and alice's Bolt goes at the Bears rather than at him.
    He still loses, because CR 704.5a is checked whenever state-based actions
    are, which is before any player would next get priority (CR 704.3).
    """
    scenario = burn(bob_life=0).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert scenario.game.winner == "alice"
    assert "bob" not in [player.username for player in scenario.game.players_in_game]


def test_the_game_is_over_once_a_player_dies_to_damage():
    """CR 704.5a removes the player, and the last one left wins (CR 104.2a)."""
    scenario = burn(bob_life=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.game.is_over
    with pytest.raises(ValueError, match="the game is over"):
        scenario.advance()


def three_players(carol_life: int = 20) -> Scenario:
    """Three players, so one can leave without ending the game.

    Alice has two Bolts and two Mountains, which is what it takes to aim a
    second one at somebody who is no longer there.
    """
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob")
        .player("carol", life=carol_life)
    )


def test_damage_aimed_at_a_conceded_player_does_nothing():
    """Corner case: a player who conceded has left the game (CR 800.4a).

    Concession is immediate, so carol is not there to be dealt damage. With a
    third player still in, the game carries on and the Bolt resolves finding
    nothing to hit.
    """
    scenario = three_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.concede("carol")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    bolt = scenario.cast_and_resolve(
        "Lightning Bolt", mountain, username="alice", targets=["carol"]
    )

    assert scenario.player("carol").life == 20
    assert bolt.zone is Zone.GRAVEYARD
    assert not scenario.game.is_over


def test_a_second_bolt_at_a_player_who_already_lost_does_nothing():
    """Corner case: the target is not a player in the game any more.

    Carol dies to the first Bolt. The second one is announced at a player who
    is gone, and resolves with nothing to damage rather than pushing her life
    total further down.
    """
    scenario = three_players(carol_life=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountains[0], username="alice", targets=["carol"])
    assert scenario.player("carol").life == 0
    assert not scenario.game.is_over, "bob is still playing"

    scenario.cast_and_resolve("Lightning Bolt", mountains[1], username="alice", targets=["carol"])

    assert scenario.player("carol").life == 0
    assert scenario.game.players_in_game == [
        scenario.player("alice"),
        scenario.player("bob"),
    ]


def test_a_dead_player_stays_dead_if_life_comes_back():
    """Corner case: CR 104.3a is one-way.

    Once the state-based action has taken carol out, adding life back does not
    put her back in the game.
    """
    scenario = three_players(carol_life=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountains[0], username="alice", targets=["carol"])

    scenario.player("carol").gain_life(10)
    scenario.game.check_state_based_actions()

    assert scenario.player("carol").life == 10
    assert not scenario.game.is_in_game("carol")


def test_lightning_helix_burns_a_face_and_gains_the_life():
    """Damage and life gain in one resolution, in the order the card prints them.

    Helix is the cheapest way to prove `gain_life` works off the same effect
    registry, and that the life goes to the spell's controller (CR 118.3),
    not to whoever was hit.
    """
    scenario = (
        Scenario()
        .player("alice", life=15, hand=["Lightning Helix"], battlefield=["Mountain", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Plains", username="alice")

    scenario.cast_and_resolve("Lightning Helix", *sources, username="alice", targets=["bob"])

    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 18


def test_a_spell_that_needs_a_target_cannot_be_cast_without_one():
    """CR 601.2c: a spell requiring a target needs a legal one chosen.

    Lightning Bolt reads "any target", so casting it with none is not a spell
    that fizzles harmlessly - it is not a legal cast at all, and nobody's life
    total is ever at risk.
    """
    scenario = burn().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    with pytest.raises(ValueError, match="target"):
        scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[])

    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20


def test_a_creature_only_spell_cannot_target_a_player():
    """Swords to Plowshares reads 'target creature'.

    Now that a player is a target the engine can express, aiming a
    creature-only spell at one is a legality question the engine answers at
    announcement (CR 601.2c).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Swords to Plowshares"], battlefield=["Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains", username="alice")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Swords to Plowshares", plains, username="alice", targets=["bob"])
