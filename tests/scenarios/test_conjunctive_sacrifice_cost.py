"""A sacrifice cost naming two objects joined by "and": "Sacrifice a Swamp
and a Forest" (Jarad, Golgari Lich Lord's graveyard ability).

The phrase is two sacrifices, each held to its own quality, and both are part
of the one total cost. CR 601.2h (via CR 602.2b for an activated ability):
"Partial payments are not allowed. Unpayable costs can't be paid." CR 118.3:
a player can't pay a cost without the resources to pay it fully - so with only
one of the two lands, the ability can't be activated, and the cost is never
"sacrifice anything" for a quality word it does not read.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_zone_abilities, off_zone_activation
from magic_cards_model.models import Zone

from .harness import Scenario

JARAD = "Jarad, Golgari Lich Lord"


def _jarad_return_index(jarad) -> int:
    (index,) = [
        i
        for i, entry in enumerate(off_zone_abilities(jarad.card))
        if entry.family == "printed" and "Sacrifice a Swamp and a Forest" in entry.ability.text
    ]
    return index


def test_both_named_lands_are_sacrificed_and_jarad_returns_to_hand() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Swamp", "Forest", "Island"], graveyard=[JARAD])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jarad = scenario.find(JARAD, Zone.GRAVEYARD, "alice")
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")

    activation = off_zone_activation(
        scenario.game, jarad, "alice", _jarad_return_index(jarad), sacrificing=[swamp, forest]
    )
    activation.begin_paying().pay()
    activation.activate()
    scenario.pass_until_resolved()

    assert swamp.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.GRAVEYARD
    assert island.zone is Zone.BATTLEFIELD
    assert jarad.zone is Zone.HAND


def test_a_dual_land_pays_one_half_and_a_basic_the_other() -> None:
    """Overgrown Tomb is a Swamp Forest: it can be the Forest while a Swamp
    is the Swamp - each half of the cost is its own sacrifice."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Swamp", "Overgrown Tomb"], graveyard=[JARAD])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jarad = scenario.find(JARAD, Zone.GRAVEYARD, "alice")
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "alice")
    tomb = scenario.find("Overgrown Tomb", Zone.BATTLEFIELD, "alice")

    activation = off_zone_activation(
        scenario.game, jarad, "alice", _jarad_return_index(jarad), sacrificing=[swamp, tomb]
    )
    activation.begin_paying().pay()
    activation.activate()
    scenario.pass_until_resolved()

    assert swamp.zone is Zone.GRAVEYARD
    assert tomb.zone is Zone.GRAVEYARD
    assert jarad.zone is Zone.HAND


def test_one_land_alone_cannot_pay_the_cost() -> None:
    """CR 601.2h / 118.3: no partial payment - a Swamp with no Forest to go
    with it leaves the cost unpayable, and nothing is sacrificed."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Swamp", "Island"], graveyard=[JARAD])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jarad = scenario.find(JARAD, Zone.GRAVEYARD, "alice")
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")

    with pytest.raises((ValueError, AssertionError)):
        activation = off_zone_activation(
            scenario.game, jarad, "alice", _jarad_return_index(jarad), sacrificing=[swamp, island]
        )
        activation.begin_paying().pay()
        activation.activate()

    assert swamp.zone is Zone.BATTLEFIELD
    assert island.zone is Zone.BATTLEFIELD
    assert jarad.zone is Zone.GRAVEYARD
