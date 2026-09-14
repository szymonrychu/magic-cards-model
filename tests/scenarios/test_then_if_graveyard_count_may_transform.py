"""A self transform read as one clause among several, and a graveyard-count
condition checked partway through an effect.

Search for Azcanta: "At the beginning of your upkeep, surveil 1. Then if you
have seven or more cards in your graveyard, you may transform Search for
Azcanta." Cloistered Youth: "At the beginning of your upkeep, you may
transform this creature." Neither is an intervening *if* trigger: the
condition, where there is one, sits inside the effect.

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 603.4** - only an "if" that immediately follows the trigger condition
  is an intervening *if*; anywhere else "if" has its normal English meaning.
- **CR 608.2c** - instructions are followed in the order written, so the
  surveil has already happened when the graveyard is counted.
- **CR 608.2d** - "you may" is a choice made while the effect is applied.
- **CR 701.25a** - surveil N: look at the top N, put any number into the
  graveyard.
- **CR 701.27a** - to transform a permanent, turn it over so its other face is up.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

SIX = ["Forest"] * 6


def _azcanta(graveyard, library=("Island", "Island")):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Search for Azcanta"],
            graveyard=list(graveyard),
            library=list(library),
        )
        .player("bob", library=["Forest"])
        .build()
    )
    azcanta = scenario.find("Search for Azcanta", Zone.BATTLEFIELD, "alice")
    return scenario, azcanta


def test_the_surveilled_card_is_counted_and_azcanta_transforms():
    scenario, azcanta = _azcanta(SIX)
    scenario.advance()  # untap -> upkeep
    assert scenario.step is Step.UPKEEP
    (top,) = scenario.top_of_library(1, "alice")
    scenario.surveil_to_graveyard(top, username="alice")
    scenario.will_take_the_may(username="alice")

    scenario.pass_until_resolved()

    assert len(scenario.game.player("alice").graveyard) == 7
    assert azcanta.transformed


def test_six_cards_after_the_surveil_is_not_enough():
    scenario, azcanta = _azcanta(SIX)
    scenario.advance()
    scenario.surveil_keeping_everything_on_top(username="alice")
    scenario.will_take_the_may(username="alice")

    scenario.pass_until_resolved()

    assert len(scenario.game.player("alice").graveyard) == 6
    assert not azcanta.transformed


def test_declining_the_may_leaves_azcanta_as_it_is():
    scenario, azcanta = _azcanta([*SIX, "Forest"])
    scenario.advance()
    scenario.surveil_keeping_everything_on_top(username="alice")
    scenario.will_take_the_may(False, username="alice")

    scenario.pass_until_resolved()

    assert not azcanta.transformed


def test_cloistered_youth_may_transform_itself():
    """Off the reported card: the same "you may transform this <type>" clause,
    with no condition and a different self-reference."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cloistered Youth"], library=["Island", "Island"])
        .player("bob", library=["Forest"])
        .build()
    )
    youth = scenario.creature("Cloistered Youth", "alice")
    scenario.advance()
    scenario.will_take_the_may(username="alice")

    scenario.pass_until_resolved()

    assert youth.transformed
