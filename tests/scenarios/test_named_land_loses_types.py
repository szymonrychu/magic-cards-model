"""Alpine Moon: "As this enchantment enters, choose a nonbasic land card name."
and "Lands your opponents control with the chosen name lose all land types and
abilities, and they gain "{T}: Add one mana of any color."".

No other printing legal in Modern, Pioneer or Standard carries either the
"nonbasic land card name" choice or the named-land type-and-ability loss
(searched in the Scryfall oracle dump, 2026-09-24; see MEMORY.md), so the
corner cases below are all on Alpine Moon itself, against several real lands.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 614.12a** - "If a replacement effect that modifies how a permanent
  enters the battlefield requires a choice, that choice is made before the
  permanent enters the battlefield."
- **CR 201.4a** - "If a player is instructed to choose a card name with certain
  characteristics, the player must choose the name of a card whose Oracle text
  matches those characteristics."
- **CR 205.3i** - the land types; Forest, Island, Mountain, Plains and Swamp
  are the basic ones.
- **CR 613.1d** - "Layer 4: Type-changing effects are applied." The land types
  go here.
- **CR 613.1f** - "Layer 6: Ability-adding effects, keyword counters,
  ability-removing effects ... are applied." The abilities go, then the
  granted mana ability comes (CR 613.3: timestamp order within a layer).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models.card import Color, Type
from magic_cards_model.models.card_state import ChoiceKind
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

ANY_COLOR = "{T}: Add one mana of any color."


def board(
    *,
    alice: list[str] | None = None,
    bob: list[str] | None = None,
    bob_hand: list[str] | None = None,
    name: str = "Steam Vents",
) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Alpine Moon"],
            battlefield=["Mountain", *(alice or [])],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=bob or [], hand=bob_hand or [], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose(name, username="alice", source="Alpine Moon")
    (mountain,) = [
        s for s in scenario.game.battlefield if s.name == "Mountain" and s.controller == "alice"
    ]
    scenario.cast_and_resolve("Alpine Moon", mountain)
    return scenario


def land(scenario: PlayedScenario, name: str, username: str):
    (state,) = [s for s in scenario.game.battlefield if s.name == name and s.controller == username]
    return state


def test_both_lines_are_handled() -> None:
    clauses = [c for c in classify_clauses(card("Alpine Moon")) if c.text]

    assert {c.category for c in clauses} == {HANDLED}


def test_the_choice_is_made_as_it_enters_and_recorded() -> None:
    scenario = board(bob=["Steam Vents"])

    moon = land(scenario, "Alpine Moon", "alice")
    assert moon.choice is not None
    assert moon.choice.kind is ChoiceKind.CARD_NAME
    assert moon.choice.value == "Steam Vents"


def test_an_opponent_s_land_with_that_name_loses_its_land_types() -> None:
    """Steam Vents is an Island Mountain; with the name chosen it has no land
    type at all - but it is still a land."""
    scenario = board(bob=["Steam Vents"])

    chars = scenario.game.characteristics_of(land(scenario, "Steam Vents", "bob"))

    assert Type.LAND in chars.types
    assert chars.subtypes == ()


def test_it_loses_every_ability_and_gains_any_color_mana() -> None:
    scenario = board(bob=["Steam Vents"])

    chars = scenario.game.characteristics_of(land(scenario, "Steam Vents", "bob"))

    assert chars.abilities == (ANY_COLOR,)


def test_the_gained_ability_makes_any_color() -> None:
    scenario = board(bob=["Spirebluff Canal"], name="Spirebluff Canal")
    canal = land(scenario, "Spirebluff Canal", "bob")

    options = scenario.game.mana_color_options(canal, 0, "bob")

    assert set(options) == {Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN}


def test_its_controller_s_own_land_with_that_name_is_untouched() -> None:
    """ "Lands your opponents control" - alice's own Steam Vents keeps
    everything."""
    scenario = board(alice=["Steam Vents"], bob=["Steam Vents"])

    mine = scenario.game.characteristics_of(land(scenario, "Steam Vents", "alice"))

    assert set(mine.subtypes) == {"Island", "Mountain"}
    assert ANY_COLOR not in mine.abilities


def test_an_opponent_s_land_with_another_name_is_untouched() -> None:
    scenario = board(bob=["Steam Vents", "Watery Grave"])

    grave = scenario.game.characteristics_of(land(scenario, "Watery Grave", "bob"))

    assert set(grave.subtypes) == {"Island", "Swamp"}
    assert ANY_COLOR not in grave.abilities


def test_every_opponent_land_with_the_name_is_caught() -> None:
    scenario = board(bob=["Steam Vents", "Steam Vents"])

    for state in [s for s in scenario.game.battlefield if s.name == "Steam Vents"]:
        assert scenario.game.characteristics_of(state).abilities == (ANY_COLOR,)


def test_a_land_that_enters_later_is_caught_too() -> None:
    """CR 611.3a: not locked in to the lands there when Alpine Moon entered."""
    scenario = board(bob_hand=["Steam Vents"])

    state = scenario.put_onto_battlefield("Steam Vents", "bob")

    assert scenario.game.characteristics_of(state).abilities == (ANY_COLOR,)


def test_everything_comes_back_when_alpine_moon_leaves() -> None:
    scenario = board(bob=["Steam Vents"])
    moon = land(scenario, "Alpine Moon", "alice")

    scenario.game.put_into_graveyard(moon)

    chars = scenario.game.characteristics_of(land(scenario, "Steam Vents", "bob"))
    assert set(chars.subtypes) == {"Island", "Mountain"}
    assert ANY_COLOR not in chars.abilities


def test_a_basic_land_name_is_refused() -> None:
    """CR 201.4a: "a nonbasic land card name" - Island is a basic land."""
    with pytest.raises(ValueError, match=r"CR 201\.4a"):
        board(bob=["Island"], name="Island")


def test_a_nonland_name_is_refused() -> None:
    with pytest.raises(ValueError, match=r"CR 201\.4a"):
        board(name="Lightning Bolt")
