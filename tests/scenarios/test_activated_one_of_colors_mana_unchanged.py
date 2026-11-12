"""Scenario: an ACTIVATED "{T}: Add {X} or {Y}." mana ability is unchanged by the
triggered one-of-colours reader.

The triggered reader (`mana._parse_mana_adding_trigger`) now also claims the
effect text "Add {B} or {G}." in the ABILITY_TEXT chain, so the dispatch
fingerprint moved rows for lands and creatures whose activated mana ability has
that text. An activated mana ability never goes through that chain for its
mana: `parse_mana_abilities` reads the `{T}: Add ...` line and the activation
path produces the mana without the stack. These tests pin that behaviour on
real printings, written to pass before the reader existed:

- Blooming Marsh: "{T}: Add {B} or {G}." (a dual land).
- Gruul Guildgate: "{T}: Add {R} or {G}." (a different pair).
- The Emperor of Palamecia: "{T}: Add {U} or {R}. Spend this mana only to cast
  a noncreature spell." (a creature, with a CR 106.6 restriction).

Rules, looked up with `mise run rules:find` this session:

- **CR 605.1a / 605.3b** - a mana ability does not use the stack and resolves
  immediately; the colour is chosen by its controller (CR 106.4 puts the mana
  in the pool).
- **CR 106.6** - a "Spend this mana only ..." restriction travels with the mana.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color
from tests.scenarios.harness import Scenario


def _board(*battlefield: str) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice", library=["Forest"] * 3, hand=["Llanowar Elves"], battlefield=list(battlefield)
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


@pytest.mark.parametrize(
    ("land", "colors"),
    [
        ("Blooming Marsh", (Color.BLACK, Color.GREEN)),
        ("Gruul Guildgate", (Color.RED, Color.GREEN)),
    ],
)
def test_a_dual_land_adds_the_colour_its_controller_names_without_the_stack(land, colors):
    for chosen in colors:
        scenario = _board(land)
        (source,) = scenario.untapped_sources(land)

        ability = scenario.activate(source, color=chosen)

        assert ability is None, "a mana ability produces no object on the stack"
        assert scenario.game.stack_is_empty
        assert source.tapped
        assert scenario.player("alice").mana_pool.floating == {chosen: 1}


def test_a_dual_land_pays_for_a_spell_of_one_of_its_colours():
    scenario = _board("Blooming Marsh")
    (marsh,) = scenario.untapped_sources("Blooming Marsh")

    elves = scenario.cast_and_resolve("Llanowar Elves", auto=True)

    assert elves.zone.value == "battlefield"
    assert marsh.tapped


def test_a_restricted_dual_creature_keeps_its_spend_restriction():
    scenario = _board("The Emperor of Palamecia")
    emperor = scenario.creature("The Emperor of Palamecia", "alice")
    emperor.summoning_sick = False

    ability = scenario.activate(emperor, color=Color.RED)

    assert ability is None
    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}
    (restricted,) = scenario.player("alice").mana_pool.restricted
    assert restricted.total == 1
