"""Scenario: Craft (CR 702.167), an activated ability that exiles materials.

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 702.167a** - "'Craft with [materials] [cost],' ... means '[Cost],
  Exile this permanent, Exile [materials] from among permanents you control
  and/or cards in your graveyard: Return this card to the battlefield
  transformed under its owner's control. Activate only as a sorcery.'"
- **CR 702.167b** - a material described by card type or subtype alone is
  either a permanent of that type or a card of that type in a graveyard.
- **CR 602.5d / CR 307.5** - "Activate only as a sorcery": own main phase,
  empty stack, priority.
- **CR 712.14a** - put onto the battlefield transformed, a double-faced
  card enters with its back face up.
- **CR 406.2** - exile moves an object from whatever zone it is in.

Clay-Fired Bricks (Craft with artifact) is the reported template; Tithing
Blade (creature), Waterlogged Hulk (a subtype, Island), Visage of Dread (a
count, two creatures) and Sunbird Standard ("one or more", no quality) are
the other material shapes.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import craft_abilities, craft_activation
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(crafter: str, battlefield: list[str], *, graveyard=None, bob=None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[crafter, *battlefield],
            graveyard=list(graveyard or []),
            library=["Plains"] * 4,
        )
        .player("bob", battlefield=list(bob or []), library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _craft(scenario, crafter_name, materials, lands):
    crafter = scenario.find(crafter_name, Zone.BATTLEFIELD, "alice")
    activation = craft_activation(scenario.game, crafter, "alice", materials)
    payment = activation.begin_paying()
    scenario.pay_with(payment, *lands)
    activation.activate()
    return crafter


def test_craft_reads_its_materials_and_cost():
    (ability,) = craft_abilities(card("Clay-Fired Bricks"))
    assert ability.canonical == "Craft"


def test_crafting_with_an_artifact_you_control_returns_the_card_transformed():
    scenario = _board("Clay-Fired Bricks", ["Market Gnome", *["Plains"] * 7])
    gnome = scenario.creature("Market Gnome", "alice")
    landmark = _craft(
        scenario, "Clay-Fired Bricks", [gnome], scenario.untapped_sources(*["Plains"] * 7)
    )
    assert landmark.zone is Zone.EXILE
    assert gnome.zone is Zone.EXILE
    # Market Gnome's own "exiled from the battlefield while you're
    # activating a craft ability" trigger joins it (CR 603.2).
    assert "Clay-Fired Bricks's activated ability" in scenario.stack_names()
    while scenario.game.stack:
        scenario.pass_until_resolved()
    returned = scenario.find("Cosmium Kiln", Zone.BATTLEFIELD, "alice")
    assert returned.transformed
    assert gnome.zone is Zone.EXILE


def test_an_artifact_card_in_the_graveyard_is_a_material_too():
    """CR 702.167b: "artifact" is an artifact permanent or an artifact card
    in a graveyard."""
    scenario = _board("Clay-Fired Bricks", ["Plains"] * 7, graveyard=["Market Gnome"])
    gnome = scenario.find("Market Gnome", Zone.GRAVEYARD, "alice")
    _craft(scenario, "Clay-Fired Bricks", [gnome], scenario.untapped_sources(*["Plains"] * 7))
    assert gnome.zone is Zone.EXILE
    while scenario.game.stack:
        scenario.pass_until_resolved()
    assert scenario.find("Cosmium Kiln", Zone.BATTLEFIELD, "alice").transformed


def test_a_material_of_the_wrong_type_is_refused():
    scenario = _board("Clay-Fired Bricks", ["Grizzly Bears", *["Plains"] * 7])
    landmark = scenario.find("Clay-Fired Bricks", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError, match="CR 702.167"):
        craft_activation(scenario.game, landmark, "alice", [bears])
    assert bears.zone is Zone.BATTLEFIELD


def test_the_crafting_permanent_is_not_its_own_material():
    scenario = _board("Clay-Fired Bricks", ["Plains"] * 7)
    landmark = scenario.find("Clay-Fired Bricks", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError, match="CR 702.167"):
        craft_activation(scenario.game, landmark, "alice", [landmark])


def test_no_material_is_refused():
    scenario = _board("Clay-Fired Bricks", ["Plains"] * 7)
    landmark = scenario.find("Clay-Fired Bricks", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError, match="CR 702.167"):
        craft_activation(scenario.game, landmark, "alice", [])


def test_an_opponents_permanent_is_not_a_material():
    """CR 702.167a: "from among permanents you control"."""
    scenario = _board("Clay-Fired Bricks", ["Plains"] * 7, bob=["Market Gnome"])
    landmark = scenario.find("Clay-Fired Bricks", Zone.BATTLEFIELD, "alice")
    gnome = scenario.creature("Market Gnome", "bob")
    with pytest.raises(ValueError, match="CR 702.167"):
        craft_activation(scenario.game, landmark, "alice", [gnome])


def test_craft_is_sorcery_speed():
    """CR 602.5d: not in the combat phase."""
    scenario = _board("Clay-Fired Bricks", ["Market Gnome", *["Plains"] * 7])
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    landmark = scenario.find("Clay-Fired Bricks", Zone.BATTLEFIELD, "alice")
    gnome = scenario.creature("Market Gnome", "alice")
    activation = craft_activation(scenario.game, landmark, "alice", [gnome])
    with pytest.raises(ValueError, match="sorcery"):
        activation.begin_paying()
    assert gnome.zone is Zone.BATTLEFIELD


def test_a_creature_material():
    """Tithing Blade: "Craft with creature {4}{B}"."""
    scenario = _board("Tithing Blade", ["Grizzly Bears", *["Swamp"] * 5])
    bears = scenario.creature("Grizzly Bears", "alice")
    _craft(scenario, "Tithing Blade", [bears], scenario.untapped_sources(*["Swamp"] * 5))
    while scenario.game.stack:
        scenario.pass_until_resolved()
    assert scenario.find("Consuming Sepulcher", Zone.BATTLEFIELD, "alice").transformed


def test_a_subtype_material_is_a_land_of_that_type():
    """Waterlogged Hulk: "Craft with Island" - an Island you control."""
    scenario = _board("Waterlogged Hulk", ["Island", *["Island"] * 4])
    (material, *lands) = scenario.untapped_sources(*["Island"] * 5)
    _craft(scenario, "Waterlogged Hulk", [material], lands)
    assert material.zone is Zone.EXILE
    while scenario.game.stack:
        scenario.pass_until_resolved()
    assert scenario.find("Watertight Gondola", Zone.BATTLEFIELD, "alice").transformed


def test_a_land_of_another_subtype_is_refused():
    scenario = _board("Waterlogged Hulk", ["Plains", *["Island"] * 4])
    hulk = scenario.find("Waterlogged Hulk", Zone.BATTLEFIELD, "alice")
    (plains,) = scenario.untapped_sources("Plains")
    with pytest.raises(ValueError, match="Island"):
        craft_activation(scenario.game, hulk, "alice", [plains])


def test_a_counted_material_needs_exactly_that_many():
    """Visage of Dread: "Craft with two creatures" - one is not enough; one
    on the battlefield and one in the graveyard are."""
    scenario = _board(
        "Visage of Dread", ["Grizzly Bears", *["Swamp"] * 6], graveyard=["Llanowar Elves"]
    )
    visage = scenario.find("Visage of Dread", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError, match="two"):
        craft_activation(scenario.game, visage, "alice", [bears])
    _craft(scenario, "Visage of Dread", [bears, elves], scenario.untapped_sources(*["Swamp"] * 6))
    assert bears.zone is Zone.EXILE
    assert elves.zone is Zone.EXILE


def test_one_or_more_takes_any_other_permanents_and_cards():
    """Sunbird Standard: "Craft with one or more" - anything, any number."""
    scenario = _board(
        "Sunbird Standard", ["Grizzly Bears", *["Plains"] * 5], graveyard=["Lightning Bolt"]
    )
    sunbird = scenario.find("Sunbird Standard", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError, match="CR 702.167"):
        craft_activation(scenario.game, sunbird, "alice", [])
    bears = scenario.creature("Grizzly Bears", "alice")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    _craft(scenario, "Sunbird Standard", [bears, bolt], scenario.untapped_sources(*["Plains"] * 5))
    assert bears.zone is Zone.EXILE
    assert bolt.zone is Zone.EXILE
