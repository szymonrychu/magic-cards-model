"""Declaring blockers: who may block what, and what stays true afterwards (CR 509).

CR 509.1a: "The defending player chooses which creatures they control, if any,
will block. The chosen creatures must be untapped and they can't also be
battles. For each of the chosen creatures, the defending p..." - and then picks
one attacker for each of them.

The declaration is legal or illegal as a whole (CR 509.1), which is why
`declare_blockers` takes the finished set: a restriction like menace cannot be
judged one blocker at a time. Evasion has its own file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def attacking_board() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=["Watchwolf", "Craw Wurm"])
    )


def test_an_untapped_creature_blocks_an_attacker():
    scenario = attacking_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(bears)
    scenario.advance()  # declare blockers
    scenario.block(bears, wolf)

    assert scenario.blockers() == [wolf]
    assert scenario.game.is_blocked(bears)
    assert scenario.game.is_blocking(wolf)


def test_blocking_does_not_tap_the_blocker():
    """Nothing in CR 509.1 taps a blocker; only attacking taps (CR 508.1f)."""
    scenario = attacking_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(bears)
    scenario.block(bears, wolf)

    assert wolf.untapped


def test_a_tapped_creature_cannot_block():
    """CR 509.1a: the chosen creatures must be untapped."""
    scenario = attacking_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    wolf = scenario.creature("Watchwolf", "bob")
    wolf.tap()
    scenario.attack_with(bears)

    with pytest.raises(ValueError, match="is tapped"):
        scenario.block(bears, wolf)
    assert scenario.blockers() == []


def test_the_attacking_player_cannot_block_their_own_attacker():
    """CR 802.4a: a defending player can block only with creatures they control."""
    scenario = attacking_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears, giant = scenario.creatures("Grizzly Bears", "Hill Giant")
    scenario.attack_with(bears)

    with pytest.raises(ValueError, match="not controlled by bob"):
        scenario.block(bears, giant)


def test_a_creature_cannot_block_an_attacker_aimed_at_another_player():
    """CR 802.4a: blockers may block only creatures attacking their controller."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob")
        .player("carol", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    wolf = scenario.creature("Watchwolf", "carol")
    scenario.attack_with(bears, defending="bob")

    with pytest.raises(ValueError, match="not controlled by bob"):
        scenario.block(bears, wolf)


def test_two_creatures_can_block_one_attacker():
    """CR 509.1a lets any number of blockers be chosen for the same attacker."""
    scenario = attacking_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    giant = scenario.creature("Hill Giant")
    wolf = scenario.creature("Watchwolf", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.attack_with(giant)
    scenario.block(giant, wolf, wurm)

    assert scenario.blockers() == [wolf, wurm]


def test_one_creature_cannot_block_two_attackers():
    """CR 509.1a: each chosen blocker is assigned one attacker to block."""
    scenario = attacking_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears, giant = scenario.creatures("Grizzly Bears", "Hill Giant")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(bears, giant)
    scenario.block(bears, wolf)

    with pytest.raises(ValueError, match="more than one attacker"):
        scenario.block(giant, wolf)


def test_a_creature_that_is_not_attacking_cannot_be_blocked():
    scenario = attacking_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears, giant = scenario.creatures("Grizzly Bears", "Hill Giant")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(bears)

    with pytest.raises(ValueError, match="is not attacking"):
        scenario.block(giant, wolf)


def test_an_illegal_declaration_leaves_the_earlier_blocks_intact():
    """CR 509.1: the declaration is judged as a whole, and refused as a whole."""
    scenario = attacking_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears, giant = scenario.creatures("Grizzly Bears", "Hill Giant")
    wolf = scenario.creature("Watchwolf", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.attack_with(bears, giant)
    scenario.block(bears, wolf)

    wurm.tap()
    with pytest.raises(ValueError, match="is tapped"):
        scenario.block(giant, wurm)

    assert scenario.blockers() == [wolf]
    assert scenario.game.is_blocked(bears)
    assert not scenario.game.is_blocked(giant)


def test_an_attacker_stays_blocked_after_its_blocker_leaves_combat():
    """CR 509.1h: blocked stays blocked, so the attacker deals no damage at all.

    Swords to Plowshares exiles the blocker between the declare blockers step
    and combat damage. The Bears are still a blocked creature with nothing
    blocking them, so CR 510.1c gives them nothing to assign damage to.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Plains"], hand=["Swords to Plowshares"])
        .player("bob", life=20, battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(bears)
    scenario.advance()
    scenario.block(bears, wolf)

    (plains,) = scenario.untapped_sources("Plains")
    scenario.cast_and_resolve("Swords to Plowshares", plains, targets=[wolf])
    assert wolf.zone is Zone.EXILE

    assert scenario.game.is_blocked(bears), "removing the blocker does not unblock it"
    assert scenario.combat_damage() == []
    # Swords to Plowshares gains bob life equal to the Watchwolf's power (3)
    # as part of exiling it - a real effect of the Swords, not of the Bears
    # getting through, which is what this assertion is actually pinning down.
    assert scenario.player("bob").life == 23, "the Bears got through to nobody"
