"""A "Tap N untapped attacking creatures you control named X" cost.

Templar Knight: "{W}, Tap five untapped attacking creatures you control named
Templar Knight: Search your library for a legendary artifact card, put it onto
the battlefield, then shuffle." CR 118.3: a cost that names a quality is paid
with the objects chosen as the ability is announced (CR 601.2b via 602.2b),
and every word of that quality is a demand: "attacking" is CR 506.4's status
(a creature declared as an attacker and still in combat), "named Templar
Knight" is CR 201.2's name comparison. Templar Knight has vigilance, so its
attackers stay untapped and can pay it (CR 702.20b).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost.text import cost_component_for_phrase
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

KNIGHT = "Templar Knight"
COST = "Tap five untapped attacking creatures you control named Templar Knight"


def _board(*extra: str):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[KNIGHT] * 5 + ["Plains", *extra],
            library=["Akroma's Memorial", "Island", "Island"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _knights(scenario):
    return [s for s in scenario.game.battlefield if s.name == KNIGHT]


def _to_declare_attackers(scenario):
    while scenario.advance() is not Step.DECLARE_ATTACKERS:
        pass


def test_five_attacking_knights_pay_and_fetch_a_legendary_artifact():
    scenario = _board()
    knights = _knights(scenario)
    _to_declare_attackers(scenario)
    scenario.attack_with(*knights)
    plains = scenario.untapped_sources("Plains")
    scenario.activate(knights[0], *plains, tapping_for_cost=knights)
    scenario.pass_until_resolved()

    assert all(k.tapped for k in knights)
    assert scenario.find("Akroma's Memorial", Zone.BATTLEFIELD, "alice")


def test_knights_that_are_not_attacking_cannot_pay():
    scenario = _board()
    knights = _knights(scenario)
    plains = scenario.untapped_sources("Plains")
    with pytest.raises(ValueError, match="attacking"):
        scenario.activate(knights[0], *plains, tapping_for_cost=knights)


def test_an_attacking_creature_with_another_name_cannot_pay():
    scenario = _board("Grizzly Bears")
    knights = _knights(scenario)
    bears = scenario.creature("Grizzly Bears")
    _to_declare_attackers(scenario)
    scenario.attack_with(*knights, bears)
    plains = scenario.untapped_sources("Plains")
    with pytest.raises(ValueError, match="named Templar Knight"):
        scenario.activate(knights[0], *plains, tapping_for_cost=[*knights[:4], bears])


def test_the_cost_reads_count_status_and_name():
    component = cost_component_for_phrase(COST, payer="alice")
    assert component is not None
    assert component.required == 5
    assert component.requirement.attacking is True
    assert component.requirement.named == KNIGHT
