"""Scenario: a static ability gives a group of permanents an equip or crew
ability - "Equipment you control have equip {1}." (Astor, Bearer of Blades),
"Equipment you control have equip Knight {0}." (Syr Gwyn, Hero of Ashvale),
"Vehicles you control have crew 1." (Astor).

CR 613.1f (layer 6 ability grant), CR 702.6a (equip), CR 702.6c (a permanent
with several equip abilities: the player picks one whose quality the target
has, so the cheaper granted one is used), CR 702.122a (crew).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation, equip_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board(alice, bob=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice))
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def equip_cost(scenario, equipment, target, username="alice"):
    return str(equip_activation(scenario.game, equipment, target, username).cost.mana)


def test_astor_makes_a_costlier_equip_cost_one():
    scenario = board(["Astor, Bearer of Blades", "Basilisk Collar", "Grizzly Bears", "Plains"])
    collar = scenario.find("Basilisk Collar", Zone.BATTLEFIELD, "alice")
    assert equip_cost(scenario, collar, scenario.creature("Grizzly Bears")) == "{1}"


def test_without_astor_the_printed_cost_applies():
    scenario = board(["Basilisk Collar", "Grizzly Bears", "Plains"])
    collar = scenario.find("Basilisk Collar", Zone.BATTLEFIELD, "alice")
    assert equip_cost(scenario, collar, scenario.creature("Grizzly Bears")) == "{2}"


def test_an_opponents_equipment_is_not_reached():
    scenario = board(["Astor, Bearer of Blades"], ["Basilisk Collar", "Grizzly Bears"])
    collar = scenario.find("Basilisk Collar", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    assert equip_cost(scenario, collar, bears, "bob") == "{2}"


def test_syr_gwyn_makes_equipping_a_knight_free_only_for_knights():
    scenario = board(
        ["Syr Gwyn, Hero of Ashvale", "Basilisk Collar", "Grizzly Bears"],
    )
    collar = scenario.find("Basilisk Collar", Zone.BATTLEFIELD, "alice")
    gwyn = scenario.creature("Syr Gwyn, Hero of Ashvale")
    bears = scenario.creature("Grizzly Bears")
    assert equip_cost(scenario, collar, gwyn) == "{0}"
    assert equip_cost(scenario, collar, bears) == "{2}"


def test_astor_gives_a_vehicle_crew_one():
    scenario = board(["Astor, Bearer of Blades", "Esika's Chariot", "Grizzly Bears"])
    chariot = scenario.find("Esika's Chariot", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears")
    activation = crew_activation(scenario.game, chariot, [bears], "alice")
    assert activation is not None
