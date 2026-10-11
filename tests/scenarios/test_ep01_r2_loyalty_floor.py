"""Deification's second line (EP-01 R2, T2): "As long as you control a creature,
if damage dealt to a planeswalker you control of the chosen type would result
in all loyalty counters on it being removed, instead all but one of those
counters are removed."

Verified with `mise run rules:find`: CR 120.3c (damage dealt to a planeswalker
causes that many loyalty counters to be removed) and CR 614.1a (a replacement
effect using "instead").
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(*, creature=True, chosen="Chandra", walker="Chandra, Torch of Defiance"):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Deification"],
            battlefield=[walker, *(["Grizzly Bears"] if creature else [])],
        )
        .player("bob", battlefield=["Hill Giant"], hand=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose(chosen, source="Deification")
    scenario.put_onto_battlefield("Deification", "alice")
    return scenario, scenario.find(walker, Zone.BATTLEFIELD, "alice")


def _burn(scenario, walker, amount):
    bob_giant = scenario.creature("Hill Giant", "bob")
    return scenario.game.deal_damage(walker, amount, source=bob_giant)


def test_lethal_damage_to_a_walker_of_the_chosen_type_leaves_one_counter():
    scenario, chandra = _board()
    loyalty = chandra.counters["loyalty"]
    _burn(scenario, chandra, loyalty + 3)
    assert chandra.counters["loyalty"] == 1
    assert chandra.zone is Zone.BATTLEFIELD


def test_non_lethal_damage_removes_exactly_that_many_counters():
    scenario, chandra = _board()
    loyalty = chandra.counters["loyalty"]
    _burn(scenario, chandra, 2)
    assert chandra.counters["loyalty"] == loyalty - 2


def test_without_a_creature_the_floor_does_not_apply():
    scenario, chandra = _board(creature=False)
    loyalty = chandra.counters["loyalty"]
    _burn(scenario, chandra, loyalty)
    assert chandra.counters["loyalty"] == 0


def test_a_walker_not_of_the_chosen_type_gets_no_floor():
    scenario, chandra = _board(chosen="Jace")
    loyalty = chandra.counters["loyalty"]
    _burn(scenario, chandra, loyalty)
    assert chandra.counters["loyalty"] == 0


def test_a_walker_the_opponent_controls_gets_no_floor():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Deification"], battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant", "Chandra, Torch of Defiance"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Chandra", source="Deification")
    scenario.put_onto_battlefield("Deification", "alice")
    chandra = scenario.find("Chandra, Torch of Defiance", Zone.BATTLEFIELD, "bob")
    loyalty = chandra.counters["loyalty"]
    scenario.game.deal_damage(chandra, loyalty, source=scenario.creature("Hill Giant", "bob"))
    assert chandra.counters["loyalty"] == 0


def test_a_walker_on_one_counter_stays_on_one():
    scenario, chandra = _board()
    chandra.remove_counters("loyalty", chandra.counters["loyalty"] - 1)
    _burn(scenario, chandra, 5)
    assert chandra.counters["loyalty"] == 1
