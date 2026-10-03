"""Esquire of the King: "{4}{W}, {T}: Creatures you control get +1/+1 until end
of turn. This ability costs {2} less to activate if you control a legendary
creature."

The reduction is CR 601.2f applied to an activated ability's cost via CR
602.2b, and a flat one: controlling two legendary creatures still takes {2}
off, once. It looks at the activator's own permanents (CR 613.5, computed
board), never an opponent's.
"""

import pytest

from magic_cards_model.machines import Step

from .harness import Scenario

ESQUIRE = "Esquire of the King"
KATARA = "Katara, Water Tribe's Hope"


def _board(*, alice, bob=()):
    scenario = Scenario().player("alice", battlefield=[ESQUIRE, *alice]).player("bob", battlefield=list(bob)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_three_mana_is_enough_with_a_legendary_creature():
    scenario = _board(alice=[KATARA, "Plains", "Plains", "Plains", "Grizzly Bears"])
    esquire = scenario.creature(ESQUIRE, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(esquire, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    scenario.resolve_top()
    chars = scenario.game.characteristics_of(bears)
    assert (chars.power, chars.toughness) == (3, 3)


def test_two_legendary_creatures_still_reduce_by_two_once():
    scenario = _board(alice=[KATARA, KATARA, "Plains", "Plains"])
    esquire = scenario.creature(ESQUIRE, "alice")
    with pytest.raises(ValueError):
        scenario.activate(esquire, *scenario.untapped_sources("Plains", "Plains"))


def test_without_a_legendary_creature_the_full_cost_is_owed():
    scenario = _board(alice=["Plains", "Plains", "Plains", "Grizzly Bears"])
    esquire = scenario.creature(ESQUIRE, "alice")
    with pytest.raises(ValueError):
        scenario.activate(esquire, *scenario.untapped_sources("Plains", "Plains", "Plains"))


def test_an_opponents_legendary_creature_does_not_reduce_it():
    scenario = _board(alice=["Plains", "Plains", "Plains"], bob=[KATARA])
    esquire = scenario.creature(ESQUIRE, "alice")
    with pytest.raises(ValueError):
        scenario.activate(esquire, *scenario.untapped_sources("Plains", "Plains", "Plains"))


def test_full_cost_still_works_without_a_legendary_creature():
    scenario = _board(alice=["Plains"] * 5 + ["Grizzly Bears"])
    esquire = scenario.creature(ESQUIRE, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(esquire, *scenario.untapped_sources(*["Plains"] * 5))
    scenario.resolve_top()
    assert scenario.game.characteristics_of(bears).power == 3
