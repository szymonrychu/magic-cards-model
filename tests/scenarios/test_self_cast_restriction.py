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

from magic_cards_model.machines import Step
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
