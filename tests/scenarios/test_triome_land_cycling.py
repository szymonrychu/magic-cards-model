"""A triome: three basic land types, a three-colour mana ability, "This land
enters tapped." and Cycling {3} (R0c T4: Spara's Headquarters).

CR numbers looked up with `mise run rules:find` in the session that wrote this:

- **CR 305.6** - a land with a basic land type has that type's intrinsic
  "{T}: Add" ability, so the three types alone are what make three colours.
- **CR 205.3i** - the basic land types are Plains, Island, Swamp, Mountain and
  Forest.
- **CR 614.1c** - "This land enters tapped" is a replacement effect.
- **CR 702.29a / 702.29b** - cycling is an activated ability that functions
  only in hand, and it continues to exist elsewhere.

Generality is proven on Zagoth Triome (Swamp Forest Island, legal in Modern
and Pioneer, not in any decks/*.txt): different colours, same template.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import cycling_abilities
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from

SPARA = "Spara's Headquarters"
ZAGOTH = "Zagoth Triome"


def _board(**kwargs) -> Scenario:
    return Scenario().manual_turn_based_actions().player("alice", **kwargs).player("bob")


@pytest.mark.parametrize(
    ("name", "subtypes"),
    [(SPARA, {"Forest", "Plains", "Island"}), (ZAGOTH, {"Swamp", "Forest", "Island"})],
)
def test_a_triome_carries_its_three_basic_land_types(name, subtypes):
    """CR 205.3i / CR 305.6."""
    printing = card(name)
    assert Type.LAND in printing.types
    assert subtypes <= set(printing.subtypes)


@pytest.mark.parametrize("name", [SPARA, ZAGOTH])
def test_a_triome_enters_tapped(name):
    """CR 614.1c: the replacement effect applies as the land enters."""
    scenario = _board(hand=[name]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    land = scenario.play_land(name)
    assert land.zone is Zone.BATTLEFIELD
    assert land.tapped


@pytest.mark.parametrize("name", [SPARA, ZAGOTH])
def test_a_tapped_triome_cannot_be_tapped_for_mana(name):
    scenario = _board(hand=[name]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    land = scenario.play_land(name)
    with pytest.raises(ValueError):
        scenario.activate(land, color=Color.GREEN)
    assert not scenario.player("alice").mana_pool.floating


@pytest.mark.parametrize(
    ("name", "color"),
    [
        (SPARA, Color.GREEN),
        (SPARA, Color.WHITE),
        (SPARA, Color.BLUE),
        (ZAGOTH, Color.BLACK),
        (ZAGOTH, Color.GREEN),
        (ZAGOTH, Color.BLUE),
    ],
)
def test_an_untapped_triome_taps_for_each_of_its_colours(name, color):
    scenario = _board(battlefield=[name]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (land,) = scenario.untapped_sources(name)
    scenario.activate(land, color=color)
    assert scenario.player("alice").mana_pool.floating == {color: 1}
    assert land.tapped


@pytest.mark.parametrize(("name", "color"), [(SPARA, Color.BLACK), (ZAGOTH, Color.WHITE)])
def test_a_triome_cannot_make_a_colour_it_does_not_print(name, color):
    scenario = _board(battlefield=[name]).build()
    (land,) = scenario.untapped_sources(name)
    with pytest.raises(ValueError):
        mana_from(land, color)


def test_cycling_cost_is_three_generic_and_functions_only_in_hand():
    """CR 702.29a, 702.29b: the ability exists on the battlefield too."""
    (ability,) = cycling_abilities(card(SPARA))
    assert ability.cost == "{3}"
    scenario = _board(battlefield=[SPARA]).build()
    (land,) = scenario.untapped_sources(SPARA)
    assert cycling_abilities(land.card)


@pytest.mark.parametrize("name", [SPARA, ZAGOTH])
def test_cycling_a_triome_discards_it_and_draws_a_card(name):
    scenario = _board(hand=[name], library=["Lightning Bolt"], battlefield=["Mountain"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    land = scenario.find(name, Zone.HAND, "alice")
    scenario.cycle(land, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    assert land.zone is Zone.GRAVEYARD
    assert [c.name for c in scenario.player("alice").hand] == ["Lightning Bolt"]
    assert scenario.player("alice").library == []


def test_cycling_with_too_little_mana_leaves_the_triome_in_hand():
    scenario = _board(
        hand=[SPARA], library=["Lightning Bolt"], battlefield=["Mountain"] * 2
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    land = scenario.find(SPARA, Zone.HAND, "alice")
    with pytest.raises(ValueError):
        scenario.cycle(land, *scenario.untapped_sources("Mountain", "Mountain"))
    assert land.zone is Zone.HAND
    assert scenario.player("alice").library[0].name == "Lightning Bolt"


def test_a_cycled_triome_does_not_count_as_a_land_drop():
    """Cycling is not playing it: the land drop is still available."""
    scenario = _board(
        hand=[SPARA, ZAGOTH], library=["Island"], battlefield=["Mountain"] * 3
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cycle(
        scenario.find(SPARA, Zone.HAND, "alice"),
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
    )
    land = scenario.play_land(ZAGOTH)
    assert land.zone is Zone.BATTLEFIELD
