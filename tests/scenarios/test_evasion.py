"""Evasion in combat: flying, reach, menace, and trample (CR 702).

CR 702.9b: "A creature with flying can't be blocked except by creatures with
flying and/or reach. A creature with flying can block a creature with or
without flying." CR 702.17b says the same thing from reach's side.

CR 702.111b: "A creature with menace can't be blocked except by two or more
creatures." That one is a restriction on the whole block declaration, not on
any single blocker, which is why it is checked once the declaration is done.

CR 702.19b: "The controller of an attacking creature with trample first assigns
damage to the creature(s) blocking it. Once all those blocking creatures are
assigned lethal damage, any excess damage is assigned as ..." - and here that
excess goes straight through to the defending player.

Keywords come off the printing's Scryfall `keywords` field: the engine has no
layers, so nothing grants or removes them.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def duel(attacker: str, *blockers: str, bob_life: int = 20) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=[attacker])
        .player("bob", life=bob_life, battlefield=list(blockers))
    )


# -- flying and reach ------------------------------------------------------


def test_a_ground_creature_cannot_block_a_flyer():
    """CR 702.9b: neither flying nor reach means it cannot be chosen."""
    scenario = duel("Wind Drake", "Watchwolf").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    drake = scenario.creature("Wind Drake")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(drake)

    assert not scenario.game.can_block(wolf, drake)
    with pytest.raises(ValueError, match="neither flying nor reach"):
        scenario.block(drake, wolf)


def test_reach_blocks_a_flyer():
    """CR 702.17b: reach is the answer to flying without flying."""
    scenario = duel("Wind Drake", "Giant Spider").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    drake = scenario.creature("Wind Drake")
    spider = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(drake)
    scenario.block(drake, spider)
    scenario.combat_damage()

    assert scenario.player("bob").life == 20
    assert drake.zone is Zone.GRAVEYARD, "the Spider's 2 power is lethal for a 2/2"
    assert spider.damage == 2


def test_a_flyer_blocks_a_flyer():
    scenario = duel("Wind Drake", "Serra Angel").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    drake = scenario.creature("Wind Drake")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.attack_with(drake)
    scenario.block(drake, angel)
    scenario.combat_damage()

    assert drake.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.BATTLEFIELD


def test_a_flyer_can_block_a_ground_creature():
    """CR 702.9b, second sentence: flying restricts blocking it, not blocking with it."""
    scenario = duel("Grizzly Bears", "Serra Angel").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.attack_with(bears)
    scenario.block(bears, angel)

    assert scenario.blockers() == [angel]


def test_a_flyer_gets_through_a_board_of_ground_creatures():
    scenario = duel("Wind Drake", "Watchwolf", "Hill Giant", bob_life=20).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    drake = scenario.creature("Wind Drake")
    scenario.attack_with(drake)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 18


# -- menace ----------------------------------------------------------------


def test_menace_cannot_be_blocked_by_one_creature():
    """CR 702.111b: one blocker on a creature with menace is an illegal declaration."""
    scenario = duel("Boggart Brute", "Watchwolf", "Hill Giant").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    brute = scenario.creature("Boggart Brute")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(brute)

    with pytest.raises(ValueError, match="fewer than two creatures"):
        scenario.block(brute, wolf)
    assert scenario.blockers() == []


def test_menace_can_be_blocked_by_two_creatures():
    scenario = duel("Boggart Brute", "Watchwolf", "Hill Giant").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    brute = scenario.creature("Boggart Brute")
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(brute)
    scenario.block(brute, wolf, giant)
    scenario.combat_damage()

    assert brute.zone is Zone.GRAVEYARD, "3/2 into 3+3 power"
    assert wolf.zone is Zone.GRAVEYARD, "the Brute's 3 is lethal for a 3/3"
    assert giant.damage == 0


def test_menace_with_only_one_legal_blocker_gets_through():
    """A single untapped creature simply cannot stop it (CR 702.111b)."""
    scenario = duel("Boggart Brute", "Watchwolf", bob_life=20).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    brute = scenario.creature("Boggart Brute")
    scenario.attack_with(brute)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 17


# -- trample ---------------------------------------------------------------


def test_trample_sends_the_excess_to_the_defending_player():
    """CR 702.19b: 2 of the Dreadmaw's 6 is lethal for a 2/2, 4 goes through."""
    scenario = duel("Colossal Dreadmaw", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    maw = scenario.creature("Colossal Dreadmaw")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(maw)
    scenario.block(maw, bears)
    assigned = scenario.combat_damage()

    assert [amount for _, amount in assigned] == [2, 4, 2]
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 16


def test_trample_assigns_lethal_to_every_blocker_before_anything_goes_through():
    """CR 702.19b: 2 for the Bears and 3 for the Giant, leaving 1 to trample."""
    scenario = duel("Colossal Dreadmaw", "Grizzly Bears", "Hill Giant").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    maw = scenario.creature("Colossal Dreadmaw")
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(maw)
    scenario.block(maw, bears, giant)
    scenario.combat_damage()

    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 19


def test_trample_gives_nothing_through_when_the_blockers_soak_it_all():
    """A 6/6 into a 2/4 and a 3/3 has 1 left; into a 2/4 and a 6/4 it has none."""
    scenario = duel("Colossal Dreadmaw", "Giant Spider", "Craw Wurm").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    maw = scenario.creature("Colossal Dreadmaw")
    spider = scenario.creature("Giant Spider", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.attack_with(maw)
    scenario.block(maw, spider, wurm)
    scenario.combat_damage()

    assert scenario.player("bob").life == 20
    assert spider.zone is Zone.GRAVEYARD
    assert wurm.damage == 2


def test_trample_can_win_the_game_through_a_blocker():
    """The excess is real damage to a player, so it can be the last of it."""
    scenario = duel("Colossal Dreadmaw", "Grizzly Bears", bob_life=4).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    maw = scenario.creature("Colossal Dreadmaw")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(maw)
    scenario.block(maw, bears)
    scenario.combat_damage()

    assert scenario.player("bob").life == 0
    assert scenario.game.winner == "alice"


def test_trample_goes_through_when_the_blocker_leaves_combat():
    """CR 702.19d: blocked with no blockers left, trample still gets there.

    Without trample this attacker would deal nothing at all (CR 510.1c) - the
    case the declare-blockers file pins down with a Grizzly Bears.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Colossal Dreadmaw", "Plains"], hand=["Swords to Plowshares"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    maw = scenario.creature("Colossal Dreadmaw")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(maw)
    scenario.block(maw, bears)

    (plains,) = scenario.untapped_sources("Plains")
    scenario.cast_and_resolve("Swords to Plowshares", plains, targets=[bears])
    assert bears.zone is Zone.EXILE

    scenario.combat_damage()
    # 20 starting, +2 from Swords gaining bob life equal to the exiled Bears'
    # power, -6 trample damage from the Dreadmaw going through unblocked.
    assert scenario.player("bob").life == 16
