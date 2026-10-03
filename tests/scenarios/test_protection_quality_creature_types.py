"""Protection from a creature type, "God creatures" (CR 702.16a: "If the
quality is a card type, subtype, or supertype, the ability applies to sources
that are permanents with that card type, subtype, or supertype and to any
sources not on the battlefield that are of that card type, subtype, or
supertype") - enforced for blocking (CR 702.16f), targeting (CR 702.16b),
damage (CR 702.16e) and attachment (CR 702.16c, CR 702.16d).

Plurals ("Elves", "Vampires") name the singular creature type; changeling
(CR 702.73a) makes a source every creature type, so it is a Goblin to Warren-
Scourge Elf and a Human to Yawgmoth.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import aura_state_based_actions
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _combat(attacker: str, *blockers: str):
    scenario = (
        Scenario()
        .player("alice", battlefield=[attacker])
        .player("bob", battlefield=list(blockers))
        .build()
    )
    protected = scenario.creature(attacker, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(protected)
    scenario.advance()
    return scenario, protected


# (protected creature, a source of the named type, a source of another type)
BLOCKING = [
    ("Baneslayer Angel", "Shivan Dragon", "Vampire Nighthawk"),
    ("Baneslayer Angel", "Pestilence Demon", "Vampire Nighthawk"),
    ("Midnight Duelist", "Vampire Nighthawk", "Hill Giant"),
    ("Nath's Buffoon", "Warren-Scourge Elf", "Hill Giant"),
    ("Warren-Scourge Elf", "Goblin Piledriver", "Hill Giant"),
    ("Warren-Scourge Elf", "Changeling Wayfinder", "Hill Giant"),
    ("Yawgmoth, Thran Physician", "Thraben Inspector", "Hill Giant"),
    ("Yawgmoth, Thran Physician", "Changeling Wayfinder", "Hill Giant"),
    ("Kitsune Riftwalker", "Hollowhenge Spirit", "Hill Giant"),
    ("Sigrid, God-Favored", "Ilharg, the Raze-Boar", "Hill Giant"),
]


@pytest.mark.parametrize(("protected", "stopper", "other"), BLOCKING)
def test_a_creature_of_the_type_cannot_block_it(protected, stopper, other):
    scenario, attacker = _combat(protected, stopper)

    with pytest.raises(ValueError, match="protection"):
        scenario.block(attacker, scenario.creature(stopper, "bob"))


@pytest.mark.parametrize(("protected", "stopper", "other"), BLOCKING)
def test_a_creature_of_another_type_can_block_it(protected, stopper, other):
    scenario, attacker = _combat(protected, other)
    blocker = scenario.creature(other, "bob")
    if "flying" in (card(protected).oracle_text or "").lower() and other == "Hill Giant":
        pytest.skip("a ground blocker cannot reach a flier")

    scenario.block(attacker, blocker)

    assert blocker in scenario.blockers()


@pytest.mark.parametrize(("protected", "stopper", "other"), BLOCKING)
def test_damage_from_a_creature_of_the_type_is_prevented(protected, stopper, other):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[protected])
        .player("bob", battlefield=[stopper, other])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature(protected, "alice")

    scenario.game.deal_damage(target, 2, source=scenario.creature(other, "bob"))
    assert target.damage == 2, "a source without the quality still hurts it"

    scenario.game.deal_damage(target, 2, source=scenario.creature(stopper, "bob"))
    assert target.damage == 2, "CR 702.16e: the damage from the type is prevented"


def test_protection_from_zombies_stops_a_zombies_damage_and_not_a_humans():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grave Bramble"])
        .player("bob", battlefield=["Walking Corpse", "Thraben Inspector"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bramble = scenario.creature("Grave Bramble", "alice")

    scenario.game.deal_damage(bramble, 2, source=scenario.creature("Walking Corpse", "bob"))
    assert bramble.damage == 0
    scenario.game.deal_damage(bramble, 1, source=scenario.creature("Thraben Inspector", "bob"))
    assert bramble.damage == 1


def test_a_creature_card_of_the_type_in_the_graveyard_is_still_a_source_of_it():
    """CR 702.16a: "and to any sources not on the battlefield that are of that
    ... subtype" - read by the printed type line there."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grave Bramble"])
        .player("bob", graveyard=["Walking Corpse"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bramble = scenario.creature("Grave Bramble", "alice")
    corpse = scenario.find("Walking Corpse", Zone.GRAVEYARD, "bob")

    assert scenario.game.protection_quality_against(bramble, corpse) == "Zombies"


def test_the_quality_is_false_for_a_noncreature_god():
    """ "God creatures" needs the creature type as well as the subtype."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Sigrid, God-Favored"])
        .player("bob", battlefield=["Ilharg, the Raze-Boar", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sigrid = scenario.creature("Sigrid, God-Favored", "alice")
    ilharg = scenario.creature("Ilharg, the Raze-Boar", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    assert scenario.game.protection_quality_against(sigrid, ilharg) == "God creatures"
    assert scenario.game.protection_quality_against(sigrid, giant) is None


def test_an_aura_cannot_enchant_what_it_is_protected_from_by_type():
    """CR 702.16c: an Aura that is a Zombie-less white spell does not match; a
    changeling Aura does not exist, so the colour family is covered in
    test_protection_quality_spell_and_value.py - here the negative: Pacifism
    (an Aura, not a Human) stays on Yawgmoth."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Yawgmoth, Thran Physician", "Pacifism"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    yawgmoth = scenario.creature("Yawgmoth, Thran Physician", "alice")
    pacifism = scenario.find("Pacifism", Zone.BATTLEFIELD, "alice")
    pacifism.attach_to(yawgmoth)

    assert aura_state_based_actions(scenario.game) == []
    assert pacifism.zone is Zone.BATTLEFIELD
