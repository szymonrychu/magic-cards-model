"""Caretaker's Talent's token-enters trigger (CR 111.1, CR 603.2h).

"Whenever one or more tokens you control enter, draw a card. This ability
triggers only once each turn."

Two engine gaps this file closes:

- **"tokens" is CR 111.1's token, not a card type** `_types_match` already
  reads - `machines/triggers.condition_matches`'s ENTERS_THE_BATTLEFIELD
  branch checks `CardState.token` directly for the word "token" in the
  condition, so a nontoken permanent entering never fires this.
- **CR 603.2h's "only once each turn"** is a new gate
  (`TriggeredAbility.once_per_turn`, `Game.once_per_turn_triggers`) - three
  tokens entering from one spell (Spectral Procession) still draws only one
  card, not three.

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 111.1, CR 603.2c, CR 603.2h.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Spectral Procession", "Grizzly Bears"],
            battlefield=["Caretaker's Talent"] + ["Plains"] * 6,
            library=["Forest"] * 3,
        )
        .player("bob")
    )


def resolve_all(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def test_tokens_entering_draws_exactly_one_card_however_many_arrive():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand) - 1  # Spectral Procession leaves the hand

    sources = scenario.untapped_sources(*(["Plains"] * 6))
    scenario.cast_and_resolve("Spectral Procession", *sources)
    resolve_all(scenario)

    spirits = [state for state in scenario.game.battlefield if state.token]
    assert len(spirits) == 3
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_a_nontoken_creature_entering_does_not_trigger_it():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.player("alice").mana_pool.floating = {}
    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")
    resolve_all(scenario)

    assert bears.token is False
    remaining = [c.name for c in scenario.player("alice").hand]
    assert remaining == ["Spectral Procession"]  # untouched: no draw happened


def test_a_second_batch_of_tokens_the_same_turn_does_not_draw_again():
    """CR 603.2h: once already triggered this turn, a second batch of
    tokens - Spectral Procession's three, cast a second time from a rigged
    hand - does not draw a second card."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spectral Procession", "Spectral Procession"],
            battlefield=["Caretaker's Talent"] + ["Plains"] * 12,
            library=["Forest"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources(*(["Plains"] * 12))
    scenario.cast_and_resolve("Spectral Procession", *sources[:6])
    resolve_all(scenario)
    after_first = len(scenario.player("alice").hand)
    assert after_first == 2  # the second Spectral Procession, plus one drawn card

    scenario.cast_and_resolve("Spectral Procession", *sources[6:])
    resolve_all(scenario)

    assert len(scenario.player("alice").hand) == after_first - 1  # no second draw this turn
