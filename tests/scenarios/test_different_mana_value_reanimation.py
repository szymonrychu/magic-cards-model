"""Agadeem's Awakening: "Return from your graveyard to the battlefield any
number of target creature cards that each have a different mana value X or
less." - CR 601.2c's own cross-target restriction (no two targets may share
a mana value), read by `machines/targeting.py`'s `distinct_mana_values`
(`TargetingProfile._why_not`), and CR 107.3a's announced X.

`machines/spell_texts_r0a.py`'s `parse_return_from_graveyard_to_battlefield_
distinct_clause` reads the whole sentence: the zone phrase ("from your
graveyard") sits right after the verb, before the object noun phrase,
unlike every other "return target ... from your graveyard" shape this file
reads elsewhere.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 601.2c** - "the player announces their choice of an appropriate
  object or player for each target the spell requires."
- **CR 202.3** - a permanent's mana value; two objects "share a mana value"
  when both compute to the same number.
- **CR 107.3a** - X is fixed once, as the spell is cast.
- **CR 603.6a** - "if multiple abilities have triggered ... but ... enter the
  battlefield ... simultaneously" - this reader puts every legal target onto
  the battlefield together, one arrival.
- **CR 608.2b** - a target rechecked for legality (it must still be in the
  graveyard) the instant it would be affected.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(graveyard: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Agadeem's Awakening"],
            battlefield=["Swamp"] * 6,
            graveyard=graveyard,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_agadeems_awakening_returns_creatures_with_distinct_mana_values():
    """Grizzly Bears (2) and Elvish Mystic (1) have different mana values, so
    both may be targeted at once with X = 2."""
    scenario = _board(["Grizzly Bears", "Elvish Mystic", "Craw Wurm"])
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    mystic = scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice")

    casting = scenario.cast("Agadeem's Awakening")
    casting.x_value = 2  # CR 107.3a: X is announced before targets are chosen
    casting.choose_targets([bears, mystic])
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*(["Swamp"] * 5)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD and bears.controller == "alice"
    assert mystic.zone is Zone.BATTLEFIELD and mystic.controller == "alice"


def test_agadeems_awakening_refuses_two_targets_with_the_same_mana_value():
    """Two Grizzly Bears (2 each) share a mana value - CR 601.2c's own
    "each have a different mana value" is unmet, so the second cannot be
    added to the same announcement."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Agadeem's Awakening"],
            battlefield=["Swamp"] * 6,
            graveyard=["Grizzly Bears", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears_1, bears_2 = scenario.player("alice").graveyard

    casting = scenario.cast("Agadeem's Awakening")
    casting.x_value = 2
    with pytest.raises(ValueError, match="different mana value"):
        casting.choose_targets([bears_1, bears_2])


def test_agadeems_awakening_refuses_a_creature_over_the_x_bound():
    """Craw Wurm (mana value 6) is over an announced X of 2."""
    scenario = _board(["Grizzly Bears", "Craw Wurm"])
    wurm = scenario.find("Craw Wurm", Zone.GRAVEYARD, "alice")

    casting = scenario.cast("Agadeem's Awakening")
    casting.x_value = 2
    with pytest.raises(ValueError):
        casting.choose_targets([wurm])


def test_agadeems_awakening_may_target_zero_creatures():
    """CR 115.6/CR 107.1c: "any number of" legally includes zero."""
    scenario = _board(["Grizzly Bears"])

    casting = scenario.cast("Agadeem's Awakening")
    casting.x_value = 2
    casting.choose_targets([])
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*(["Swamp"] * 5)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    bears = scenario.player("alice").graveyard[0]
    assert bears.zone is Zone.GRAVEYARD
