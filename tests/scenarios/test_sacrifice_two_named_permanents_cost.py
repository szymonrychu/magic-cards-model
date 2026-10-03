"""A sacrifice cost naming two different permanents (CR 118.3, CR 602.2).

Jarad, Golgari Lich Lord: "Sacrifice a Swamp and a Forest: Return this card
from your graveyard to your hand." The cost is two sacrifices, one per named
quality; both must be paid, by objects that have each quality. Jarad is the
only Modern, Pioneer or Standard printing with this "a X and a Y" cost.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

JARAD = "Jarad, Golgari Lich Lord"


def _board(battlefield):
    scenario = (
        Scenario()
        .player("alice", graveyard=[JARAD], battlefield=list(battlefield))
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_sacrificing_a_swamp_and_a_forest_returns_jarad_to_hand():
    scenario = _board(["Swamp", "Forest", "Island"])
    jarad = scenario.find(JARAD, Zone.GRAVEYARD, "alice")
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")

    scenario.activate(jarad, index=1, sacrificing=[forest, swamp])
    scenario.pass_until_resolved()

    assert jarad.zone is Zone.HAND
    assert swamp.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.GRAVEYARD
    assert scenario.find("Island", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD


def test_two_swamps_do_not_pay_for_a_swamp_and_a_forest():
    scenario = _board(["Swamp", "Swamp"])
    jarad = scenario.find(JARAD, Zone.GRAVEYARD, "alice")
    swamps = [s for s in scenario.game.permanents_controlled_by("alice") if s.name == "Swamp"]

    with pytest.raises(ValueError):
        scenario.activate(jarad, index=1, sacrificing=swamps)

    assert jarad.zone is Zone.GRAVEYARD
    assert all(swamp.zone is Zone.BATTLEFIELD for swamp in swamps)
