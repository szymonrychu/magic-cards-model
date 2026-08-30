"""Defender: a creature that cannot attack (CR 702.3).

CR 702.3a: "Defender is a static ability." CR 702.3b: "A creature with defender
can't attack." That is the whole keyword - it says nothing about blocking, about
tapping, or about damage, and the tests here are mostly about what it does *not*
stop.

CR 506.4a is the other half of the story: "Once a creature has been declared as
an attacking or blocking creature, spells or abilities that would have kept that
creature from attacking or blocking don't remove the creature from combat." A
declaration that never happened cannot be undone, so a refused attack has to
leave the board untouched, and that is asserted here.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def duel(*alice: str, bob: tuple[str, ...] = ()) -> Scenario:
    return Scenario().player("alice", battlefield=list(alice)).player("bob", battlefield=list(bob))


def test_a_wall_cannot_be_declared_as_an_attacker():
    """CR 702.3b, the whole rule."""
    scenario = duel("Fog Bank").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bank = scenario.creature("Fog Bank")
    assert not scenario.can_attack(bank)
    with pytest.raises(ValueError, match="has defender"):
        scenario.attack_with(bank)


def test_a_refused_attack_leaves_the_wall_untapped_and_out_of_combat():
    """CR 508.1f taps as attacking *causes* it, so a refusal taps nothing."""
    scenario = duel("Fog Bank").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bank = scenario.creature("Fog Bank")
    with pytest.raises(ValueError):
        scenario.attack_with(bank)

    assert bank.untapped
    assert not scenario.game.is_attacking(bank)
    assert scenario.attackers() == []


def test_defender_does_not_stop_it_blocking():
    """Defender says nothing about blocking - that is the point of a Wall."""
    scenario = duel("Colossal Dreadmaw", bob=("Aether Membrane",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    dreadmaw = scenario.creature("Colossal Dreadmaw")
    membrane = scenario.creature("Aether Membrane", "bob")
    scenario.attack_with(dreadmaw)

    assert scenario.game.can_block(membrane, dreadmaw)
    scenario.block(dreadmaw, membrane)
    assert scenario.blockers() == [membrane]


def test_a_defender_blocker_still_deals_and_takes_damage():
    """A 0/5 Wall assigns nothing (CR 510.1a) but soaks the whole attack.

    Nothing about defender changes CR 510: the Wall takes the two damage and
    marks it (CR 704.5g is not met), and assigns none back because a creature
    that would assign 0 damage assigns none at all.
    """
    scenario = duel("Grizzly Bears", bob=("Aether Membrane",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    membrane = scenario.creature("Aether Membrane", "bob")
    scenario.attack_with(bears)
    scenario.block(bears, membrane)
    scenario.combat_damage()

    assert membrane.zone is Zone.BATTLEFIELD
    assert membrane.damage == 2
    assert bears.damage == 0
    assert scenario.player("bob").life == 20


def test_the_wall_that_is_also_a_flyer_can_still_block_a_ground_creature():
    """Two keywords on one card do not interfere: Fog Bank has defender and flying."""
    scenario = duel("Watchwolf", bob=("Fog Bank",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wolf = scenario.creature("Watchwolf")
    bank = scenario.creature("Fog Bank", "bob")
    scenario.attack_with(wolf)
    scenario.block(wolf, bank)

    assert scenario.blockers() == [bank]
    assert not scenario.can_attack(bank)
