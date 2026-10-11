"""Scenario: Konda's Banner - "can be attached only to a legendary creature"
(CR 301.5c, CR 702.6a), and the two groups defined relative to the equipped
creature: "Creatures that share a color with equipped creature get +1/+1" and
"Creatures that share a creature type with equipped creature get +1/+1"
(CR 613.4c, CR 611.3a, CR 205.3).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
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


def pt(scenario, state):
    chars = scenario.game.characteristics_of(state)
    return chars.power, chars.toughness


def banner(scenario):
    return scenario.find("Konda's Banner", Zone.BATTLEFIELD, "alice")


def attach(scenario, target):
    banner(scenario).attach_to(target)


def test_it_cannot_equip_a_nonlegendary_creature():
    scenario = board(["Konda's Banner", "Grizzly Bears", "Plains", "Plains"])
    with pytest.raises(ValueError, match="legendary"):
        equip_activation(
            scenario.game, banner(scenario), scenario.creature("Grizzly Bears"), "alice"
        )


def test_it_can_equip_a_legendary_creature():
    scenario = board(["Konda's Banner", "Syr Gwyn, Hero of Ashvale", "Plains", "Plains"])
    gwyn = scenario.creature("Syr Gwyn, Hero of Ashvale")
    assert equip_activation(scenario.game, banner(scenario), gwyn, "alice") is not None


def test_same_colour_creatures_get_the_pump():
    """Equipped Syr Gwyn is red, white and black: any creature sharing one of
    them is pumped (the equipped creature itself shares all three)."""
    scenario = board(
        ["Konda's Banner", "Syr Gwyn, Hero of Ashvale", "Savannah Lions", "Wind Drake"],
        ["Grizzly Bears", "Goblin Guide"],
    )
    gwyn = scenario.creature("Syr Gwyn, Hero of Ashvale")
    attach(scenario, gwyn)
    lions = scenario.creature("Savannah Lions")
    drake = scenario.creature("Wind Drake")
    goblin = scenario.creature("Goblin Guide", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    assert pt(scenario, lions) == (3, 2)
    assert pt(scenario, goblin) == (3, 3)  # an opponent's red creature shares red
    assert pt(scenario, drake) == (int(drake.card.power), int(drake.card.toughness))
    assert pt(scenario, bears) == (2, 2)


def test_same_creature_type_creatures_get_the_pump():
    scenario = board(
        ["Konda's Banner", "Syr Gwyn, Hero of Ashvale", "Elite Vanguard"],
        ["Grizzly Bears"],
    )
    attach(scenario, scenario.creature("Syr Gwyn, Hero of Ashvale"))
    vanguard = scenario.creature("Elite Vanguard")
    # white (shares white with Gwyn) and Human (shares Human): two instances
    assert pt(scenario, vanguard) == (4, 3)


def test_nothing_is_pumped_while_unattached():
    scenario = board(["Konda's Banner", "Savannah Lions"])
    lions = scenario.creature("Savannah Lions")
    assert pt(scenario, lions) == (2, 1)
