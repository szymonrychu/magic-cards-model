"""Scenario: "Target permanent becomes an artifact in addition to its other
types until end of turn." (Liquimetal Coating) - layer 4 type-changing
(CR 613.1d), additive rather than a replacement: CR 613.1d's own text says
type-changing effects "include effects that change an object's card type,
subtype, and/or supertype", and this one keeps every type already there
rather than overwriting them the way Karn, the Great Creator's "becomes a[n]
<type> creature ..." (a different, already-modelled shape) does.

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario


def coating_board() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Liquimetal Coating", "Grizzly Bears", "Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_liquimetal_coating_makes_a_creature_an_artifact_in_addition_to_its_types():
    """CR 613.1d: the target gains the artifact type without losing creature."""
    scenario = coating_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    coating = scenario.find("Liquimetal Coating", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(coating, targets=[bears])
    scenario.resolve_top()

    types = scenario.game.characteristics_of(bears).types
    assert Type.ARTIFACT in types
    assert Type.CREATURE in types


def test_liquimetal_coating_can_target_a_land():
    """ "Target permanent" - no type restriction of its own - so a land is a
    legal target too, and keeps being a land."""
    scenario = coating_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    coating = scenario.find("Liquimetal Coating", Zone.BATTLEFIELD)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")

    scenario.activate(coating, targets=[forest])
    scenario.resolve_top()

    types = scenario.game.characteristics_of(forest).types
    assert Type.ARTIFACT in types
    assert Type.LAND in types


def test_liquimetal_coating_can_target_an_opponents_permanent():
    """ "Target permanent" names no controller restriction (CR 115.1)."""
    scenario = coating_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    coating = scenario.find("Liquimetal Coating", Zone.BATTLEFIELD)
    bobs_bear = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(coating, targets=[bobs_bear])
    scenario.resolve_top()

    assert Type.ARTIFACT in scenario.game.characteristics_of(bobs_bear).types


def test_liquimetal_coatings_type_change_wears_off_in_cleanup():
    """CR 514.2/CR 703.4p: the "until end of turn" duration ends in cleanup."""
    scenario = coating_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    coating = scenario.find("Liquimetal Coating", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(coating, targets=[bears])
    scenario.resolve_top()
    assert Type.ARTIFACT in scenario.game.characteristics_of(bears).types

    scenario.game.continuous_effects.end_the_turn()

    assert Type.ARTIFACT not in scenario.game.characteristics_of(bears).types
    assert Type.CREATURE in scenario.game.characteristics_of(bears).types
