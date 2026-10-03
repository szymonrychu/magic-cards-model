"""A spell's own printed casting gate: "You can't cast this spell unless
<condition>." (CR 601.2e).

Proft, Sinister Mastermind: "Threshold — You can't cast this spell unless
there are seven or more cards in your graveyard." Threshold (CR 207.2c) is
an ability word with no rules meaning of its own; the restriction is the
sentence after it, handed to `Game.condition_holds` - the same reader
"Activate only if <condition>" (CR 602.5b) already shares across unrelated
cards, so this gate is not a graveyard-count special case, only a new place
that reader is asked from.

No other printed card carries this exact sentence (checked via a full-text
Scryfall search this session, zero other matches), so there is no second
card to prove the shape on the way `test_costs.py`'s "or pay" wave proved
itself on Bayou Groff - the underlying condition reader's own generality is
what other, unrelated tests already establish.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(graveyard_cards: int) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Proft, Sinister Mastermind"],
            library=["Grizzly Bears"],
            battlefield=["Swamp", "Swamp", "Swamp"],
            graveyard=["Grizzly Bears"] * graveyard_cards,
        )
        .player("bob")
    )


def test_proft_is_uncastable_with_fewer_than_seven_cards_in_the_graveyard():
    scenario = _board(6).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")

    try:
        scenario.cast("Proft, Sinister Mastermind", username="alice")
        raised = None
    except ValueError as error:
        raised = error
    assert raised is not None
    assert "CR 601.2e" in str(raised)
    assert sources  # unused; the cast never got far enough to pay


def test_proft_is_castable_with_seven_cards_in_the_graveyard():
    scenario = _board(7).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")

    proft = scenario.cast_and_resolve("Proft, Sinister Mastermind", *sources, username="alice")

    assert proft.name == "Proft, Sinister Mastermind"


def test_proft_becomes_castable_once_the_graveyard_reaches_the_threshold():
    """The gate is read live, at CR 601.2f's cost-determination moment - or
    at least by the time the cast is proposed - not fixed at the start of
    the game."""
    scenario = _board(6).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.player("alice").graveyard.append(scenario.game.player("alice").library.pop())
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")

    proft = scenario.cast_and_resolve("Proft, Sinister Mastermind", *sources, username="alice")

    assert proft.name == "Proft, Sinister Mastermind"


def test_proft_has_menace_and_its_discard_ability_ignores_the_cast_restriction():
    """CR 702.111b: menace. The "{B}, Discard this card" ability works from
    the hand (CR 113.6b) with fewer than seven cards in the graveyard; the
    cast restriction (CR 601.3) is about casting only."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Proft, Sinister Mastermind"],
            battlefield=["Swamp"],
            graveyard=["Grizzly Bears"] * 2,
        )
        .player("bob", battlefield=["Grizzly Bears"])
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    proft = scenario.find("Proft, Sinister Mastermind", Zone.HAND, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")

    scenario.activate(proft, swamp, index=0, username="alice", discarding=[proft], targets=[bears])
    scenario.pass_until_resolved()

    assert proft.zone is Zone.GRAVEYARD
    assert scenario.game.power_of(bears) == 2 - 3
    assert scenario.game.toughness_of(bears) == 2 - 1


def test_proft_on_the_battlefield_has_menace():
    """CR 702.111b: one blocker is illegal, two are fine."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Proft, Sinister Mastermind"])
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
    ).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    proft = scenario.creature("Proft, Sinister Mastermind", "alice")
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob")
    scenario.attack_with(proft)
    scenario.advance("alice")

    with pytest.raises(ValueError):
        scenario.block(proft, first)
    scenario.block(proft, first, second)
    assert scenario.game.is_blocked(proft)


def test_second_printing_cast_only_if_another_spell_was_cast_this_turn():
    """Clause (c), CR 601.3's other template: "Cast this spell only if you've
    cast another spell this turn." (Hewed Stone Retainers, Modern/Pioneer legal)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hewed Stone Retainers", "Opt"],
            library=["Grizzly Bears"] * 3,
            battlefield=["Island", "Island", "Swamp", "Swamp", "Forest", "Forest"],
        )
        .player("bob")
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    with pytest.raises(ValueError, match="601"):
        scenario.cast("Hewed Stone Retainers", username="alice")

    (island,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_and_resolve("Opt", island, username="alice")
    sources = scenario.untapped_sources("Island", "Swamp", "Swamp", "Forest", username="alice")
    retainers = scenario.cast_and_resolve("Hewed Stone Retainers", *sources, username="alice")

    assert retainers.name == "Hewed Stone Retainers"
