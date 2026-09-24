"""A Theros god's type removal: "As long as your devotion to red and green is
less than seven, Xenagos isn't a creature." (Xenagos, God of Revels), and the
one-colour form "As long as your devotion to blue is less than five, Thassa
isn't a creature." (Thassa, Deep-Dwelling - the second printing, legal in
Modern and Pioneer, in no deck in the api's pool).

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 700.5** - "A player's devotion to [color] is equal to the number of
  mana symbols of that color among the mana costs of permanents that player
  controls. A player's devotion to [color 1] and [color 2] is equal to the
  number of mana symbols among the mana costs of permanents that player
  controls that are [color 1], [color 2], or both colors."
- **CR 613.1d** - "Layer 4: Type-changing effects are applied. These include
  effects that change an object's card type, subtype, and/or supertype."
- **CR 611.3a** - a static ability's effect "isn't 'locked in'".
- **CR 508.1a** - only creatures are declared as attackers.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models.card import Type
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

XENAGOS = "Xenagos, God of Revels"
THASSA = "Thassa, Deep-Dwelling"


def board(alice: list[str], bob: list[str] | None = None) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=alice, library=["Forest"] * 5)
        .player("bob", battlefield=bob or [], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def types_of(scenario: PlayedScenario, name: str, username: str = "alice") -> tuple[Type, ...]:
    (state,) = [s for s in scenario.game.battlefield if s.name == name and s.controller == username]
    return tuple(scenario.game.characteristics_of(state).types)


@pytest.mark.parametrize("name", [XENAGOS, THASSA])
def test_the_devotion_line_is_handled(name: str) -> None:
    (clause,) = [c for c in classify_clauses(card(name)) if "devotion" in c.text]

    assert clause.category == HANDLED


def test_on_its_own_the_god_is_not_a_creature() -> None:
    """Xenagos alone: its own {R}{G} is two - under seven."""
    scenario = board([XENAGOS])

    types = types_of(scenario, XENAGOS)

    assert Type.CREATURE not in types
    assert Type.ENCHANTMENT in types


def test_with_enough_devotion_it_is_a_creature() -> None:
    """2 (Xenagos) + 3 (Boggart Ram-Gang) + 3 (Ball Lightning) = 8."""
    scenario = board([XENAGOS, "Boggart Ram-Gang", "Ball Lightning"])

    types = types_of(scenario, XENAGOS)

    assert Type.CREATURE in types
    chars = scenario.game.characteristics_of(scenario.creature(XENAGOS, "alice"))
    assert (chars.power, chars.toughness) == (6, 5)


def test_a_hybrid_symbol_of_both_colors_counts_once() -> None:
    """CR 700.5's "[color 1], [color 2], or both colors": Boggart Ram-Gang's
    three {R/G} are three symbols, not six - 2 + 3 = 5, under seven."""
    scenario = board([XENAGOS, "Boggart Ram-Gang"])

    assert Type.CREATURE not in types_of(scenario, XENAGOS)


def test_one_under_the_number_is_not_enough() -> None:
    """Thassa: 1 + 3 (The Mindskinner) = 4, under five."""
    scenario = board([THASSA, "The Mindskinner"])

    assert Type.CREATURE not in types_of(scenario, THASSA)


def test_exactly_the_number_is_enough() -> None:
    """ "less than five": at five it is a creature - 1 + 3 + 1 (Delver of
    Secrets' {U})."""
    scenario = board([THASSA, "The Mindskinner", "Delver of Secrets"])

    assert Type.CREATURE in types_of(scenario, THASSA)


def test_the_one_color_god_at_its_own_threshold() -> None:
    """Thassa: 1 + 3 + 3 = 7, well past five."""
    scenario = board([THASSA, "The Mindskinner", "The Mindskinner"])

    assert Type.CREATURE in types_of(scenario, THASSA)


def test_an_opponent_s_permanents_do_not_count() -> None:
    scenario = board([XENAGOS], ["Boggart Ram-Gang", "Ball Lightning"])

    assert Type.CREATURE not in types_of(scenario, XENAGOS)


def test_losing_devotion_turns_it_back_into_a_non_creature() -> None:
    """CR 611.3a: not locked in."""
    scenario = board([XENAGOS, "Boggart Ram-Gang", "Ball Lightning"])
    assert Type.CREATURE in types_of(scenario, XENAGOS)

    scenario.game.put_into_graveyard(scenario.creature("Ball Lightning", "alice"))

    assert Type.CREATURE not in types_of(scenario, XENAGOS)


def test_a_god_that_is_not_a_creature_cannot_attack() -> None:
    scenario = board([XENAGOS])
    xenagos = next(s for s in scenario.game.battlefield if s.name == XENAGOS)
    xenagos.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert not scenario.can_attack(xenagos)


def test_a_god_with_devotion_can_attack() -> None:
    scenario = board([XENAGOS, "Boggart Ram-Gang", "Ball Lightning"])
    xenagos = scenario.creature(XENAGOS, "alice")
    xenagos.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert scenario.can_attack(xenagos)


def test_a_permanent_gained_by_a_control_change_counts() -> None:
    """CR 700.5a: devotion is counted after control-changing effects - a
    stolen Ball Lightning is one of the permanents alice controls. 2
    (Xenagos) + 3 (Predator Ooze) = 5, then + 3 = 8."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[XENAGOS, "Predator Ooze", "Mountain", "Mountain", "Mountain"],
            hand=["Threaten"],
            library=["Forest"] * 5,
        )
        .player("bob", battlefield=["Ball Lightning"], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert Type.CREATURE not in types_of(scenario, XENAGOS)
    bolt = scenario.creature("Ball Lightning", "bob")

    scenario.cast_and_resolve(
        "Threaten", *scenario.untapped_sources("Mountain", "Mountain", "Mountain"), targets=[bolt]
    )

    assert bolt.controller == "alice"
    assert Type.CREATURE in types_of(scenario, XENAGOS)
