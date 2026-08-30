"""Declaring attackers: who may be chosen, and what choosing them costs (CR 508).

CR 508.1a is the whole legality check in one sentence: "The active player
chooses which creatures that they control, if any, will attack. The chosen
creatures must be untapped, they can't also be battles, and each one must
either have haste or have been ..." controlled by the active player since
their most recent turn began.

Summoning sickness has its own file; this one is about the rest - control,
tapped status, who may be attacked, and the fact that attacking taps
(CR 508.1f) unless the creature has vigilance (CR 702.20b).
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def two_players() -> Scenario:
    """Alice with two ground creatures and a Serra Angel, bob with a blocker."""
    return (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant", "Serra Angel"])
        .player("bob", battlefield=["Watchwolf"])
    )


def test_an_untapped_creature_is_declared_as_an_attacker():
    scenario = two_players().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    scenario.attack_with(bears)

    assert scenario.attackers() == [bears]
    assert scenario.game.is_attacking(bears)


def test_attacking_taps_the_creature():
    """CR 508.1f: tapping is not a cost, attacking simply causes it."""
    scenario = two_players().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    assert bears.untapped
    scenario.attack_with(bears)

    assert bears.tapped


def test_vigilance_keeps_the_attacker_untapped():
    """CR 702.20b: attacking doesn't cause creatures with vigilance to tap."""
    scenario = two_players().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    angel = scenario.creature("Serra Angel")
    scenario.attack_with(angel)

    assert angel.untapped
    assert scenario.game.is_attacking(angel)


def test_a_tapped_creature_cannot_be_declared_as_an_attacker():
    """CR 508.1a: the chosen creatures must be untapped."""
    scenario = two_players().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    bears.tap()

    with pytest.raises(ValueError, match="is tapped"):
        scenario.attack_with(bears)
    assert scenario.attackers() == []


def test_a_creature_cannot_attack_its_own_controller():
    """CR 508.1a: attackers are declared against a defending player, never yourself."""
    scenario = two_players().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    with pytest.raises(ValueError, match="own controller"):
        scenario.attack_with(bears, defending="alice")


def test_the_defending_players_creature_cannot_be_declared_as_an_attacker():
    """CR 508.1a: only the active player declares attackers, from what they control."""
    scenario = two_players().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wolf = scenario.creature("Watchwolf", "bob")
    with pytest.raises(ValueError, match="not controlled by the active player"):
        scenario.attack_with(wolf)


def test_the_same_creature_cannot_attack_twice():
    """One creature is one attacker; the second declaration is refused, not doubled."""
    scenario = two_players().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    scenario.attack_with(bears)

    with pytest.raises(ValueError, match="already attacking"):
        scenario.attack_with(bears)
    assert scenario.attackers() == [bears]


def test_a_refused_declaration_leaves_the_creature_untapped_and_out_of_combat():
    """An illegal attack changes nothing: the tap is part of the declaration."""
    scenario = two_players().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    with pytest.raises(ValueError):
        scenario.attack_with(bears, defending="alice")

    assert bears.untapped
    assert scenario.attackers() == []


def test_a_player_who_has_left_the_game_cannot_be_attacked():
    """CR 104.3a: a player who concedes leaves the game immediately."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.game.concede("bob")

    bears = scenario.creature("Grizzly Bears")
    with pytest.raises(ValueError, match="not a player in this game"):
        scenario.attack_with(bears, defending="bob")

    scenario.attack_with(bears, defending="carol")
    assert scenario.attackers() == [bears]


def test_a_noncreature_permanent_cannot_attack():
    """CR 508.1a: only creatures are chosen as attackers (CR 302.5)."""
    scenario = Scenario().player("alice", battlefield=["Sol Ring"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    ring = scenario.creature("Sol Ring")
    with pytest.raises(ValueError, match="not a creature"):
        scenario.attack_with(ring)


def test_everything_leaves_combat_when_the_combat_phase_ends():
    """CR 511.3: all creatures are removed from combat as the end of combat step ends."""
    scenario = two_players().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    scenario.attack_with(bears)

    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()

    assert scenario.attackers() == []
    assert not scenario.game.is_attacking(bears)
    assert bears.tapped, "leaving combat does not untap it"
