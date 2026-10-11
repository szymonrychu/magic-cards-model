"""Scenario: Bludgeon Brawl - "Each noncreature, non-Equipment artifact is an
Equipment with equip {X} and 'Equipped creature gets +X/+0,' where X is that
artifact's mana value."

CR 613.1d (layer 4: the Equipment subtype), CR 613.1f (layer 6: the equip
ability and the static ability), CR 702.6a (equip), CR 613.4c (the pump,
sublayer 7c). X is each artifact's own mana value (CR 202.3), so a {2} Mind
Stone is equip {2} for +2/+0, and an artifact creature or a real Equipment is
left alone.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

BRAWL = "Bludgeon Brawl"


def board(alice, bob=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice))
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def chars(scenario, name, username="alice"):
    return scenario.game.characteristics_of(scenario.find(name, Zone.BATTLEFIELD, username))


def test_a_plain_artifact_becomes_an_equipment_with_its_mana_value():
    scenario = board([BRAWL, "Mind Stone", "Grizzly Bears", "Plains", "Plains"])
    stone = chars(scenario, "Mind Stone")

    assert "Equipment" in stone.subtypes
    assert "Equip {2}" in stone.abilities


def test_equipping_it_pumps_by_the_artifacts_mana_value():
    scenario = board([BRAWL, "Mind Stone", "Grizzly Bears", "Plains", "Plains"])
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears")

    activation = equip_activation(scenario.game, stone, bears, "alice")
    assert str(activation.cost.mana) == "{2}"
    stone.attach_to(bears)

    pumped = scenario.game.characteristics_of(bears)
    assert (pumped.power, pumped.toughness) == (4, 2)


def test_each_artifact_uses_its_own_mana_value():
    scenario = board([BRAWL, "Sol Ring", "Grizzly Bears"], bob=["Mind Stone"])
    assert "Equip {1}" in chars(scenario, "Sol Ring").abilities
    assert "Equip {2}" in chars(scenario, "Mind Stone", "bob").abilities


def test_a_real_equipment_and_an_artifact_creature_are_left_alone():
    scenario = board([BRAWL, "Bonesplitter", "Ornithopter", "Grizzly Bears"])
    splitter = chars(scenario, "Bonesplitter")
    copter = chars(scenario, "Ornithopter")

    assert "Equip {1}" in splitter.abilities and splitter.abilities.count("Equip {1}") == 1
    assert "Equipment" not in copter.subtypes
    assert not any(line.startswith("Equip") for line in copter.abilities)


def test_without_the_enchantment_it_is_just_an_artifact():
    scenario = board(["Mind Stone", "Grizzly Bears"])
    stone = chars(scenario, "Mind Stone")

    assert "Equipment" not in stone.subtypes
    assert not any(line.startswith("Equip") for line in stone.abilities)
