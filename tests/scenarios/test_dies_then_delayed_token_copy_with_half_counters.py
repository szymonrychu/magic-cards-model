"""Scenario: "When this creature dies, if it had two or more +1/+1 counters
on it, create a token that's a copy of it at the beginning of the next end
step. The token enters with half that many +1/+1 counters on it, rounded
down." (Ochre Jelly's Split.)

"Split" is an ability word with no rules meaning (CR 207.2c). The dies
trigger is a leaves-the-battlefield ability that looks back in time (CR
603.10a), so its intervening *if* (CR 603.4) reads the counters the creature
had as it last existed on the battlefield - CR 122.2 has already made them
cease to exist on the move. Resolving, it creates a delayed triggered ability
(CR 603.7, 603.7a) that triggers once (CR 603.7b), at the beginning of the
next end step. The token copies the creature's copiable values (CR 707.2),
none of its counters, and enters with half the counter count, rounded down
(CR 614.1c's "enters with"). The creature that died may have left the
graveyard by then, and a token that died has ceased to exist (CR 704.5d):
neither stops the copy, which was made from the object as it last existed.

No second Modern/Pioneer/Standard printing carries "create a token that's a
copy of it at the beginning of the next end step" or "enters with half that
many" (Scryfall full-text search, 2026-10-03); the readers are written
against the templated shapes (any timing phrase the delayed-timing table
reads, any counter kind, "half that many"/"that many", rounded down or up).

CR numbers verified with `mise run rules:find`: 207.2c, 603.10a, 603.4,
122.2, 603.7, 603.7a, 603.7b, 707.2, 614.1c, 704.5d.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import is_token
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

JELLY = "Ochre Jelly"


def _settle(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _to_end_step(scenario):
    while scenario.step is not Step.END_STEP:
        _settle(scenario)
        scenario.advance()
    _settle(scenario)


def _to_next_turns_main_phase(scenario):
    _settle(scenario)
    scenario.advance()
    while scenario.step is not Step.UNTAP:
        _settle(scenario)
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)


def _board():
    return (
        Scenario()
        .player("alice", battlefield=[JELLY], library=["Forest"] * 5)
        .player("bob", library=["Forest"] * 5)
        .build()
    )


def _jelly_with(scenario, counters: int):
    jelly = scenario.creature(JELLY)
    if counters:
        scenario.game.add_counters(jelly, Counter.PLUS_ONE, counters)
    return jelly


def _jelly_tokens(scenario):
    return [c for c in scenario.game.battlefield if c.name == JELLY and is_token(c)]


def test_ochre_jelly_split_is_handled():
    bad = [c for c in card_support(card(JELLY)).clauses if c.outcome != "handled"]
    assert not bad, bad


@pytest.mark.parametrize(("counters", "expected"), [(2, 1), (3, 1), (5, 2)])
def test_dying_with_two_or_more_counters_makes_a_half_counter_copy_at_the_end_step(
    counters, expected
):
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jelly = _jelly_with(scenario, counters)
    scenario.game.destroy(jelly)
    _settle(scenario)
    assert jelly.zone is Zone.GRAVEYARD
    assert not _jelly_tokens(scenario), "the copy waits for the end step (CR 603.7)"
    assert len(scenario.game.delayed_triggers.triggers) == 1
    _to_end_step(scenario)
    (token,) = _jelly_tokens(scenario)
    assert token.controller == "alice"
    assert token.counter_count(Counter.PLUS_ONE) == expected
    # CR 707.2: a copy of the printing, with none of the original's counters.
    assert token.oracle_text == jelly.oracle_text
    assert scenario.game.delayed_triggers.triggers == []


@pytest.mark.parametrize("counters", [0, 1])
def test_dying_with_fewer_than_two_counters_does_not_trigger(counters):
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jelly = _jelly_with(scenario, counters)
    scenario.game.destroy(jelly)
    _settle(scenario)
    assert jelly.zone is Zone.GRAVEYARD
    assert scenario.game.delayed_triggers.triggers == []
    _to_end_step(scenario)
    assert not _jelly_tokens(scenario)


def test_the_token_copy_dying_again_splits_again_then_stops():
    """The ruling's chain: 5 counters -> a 2-counter token -> a 1-counter
    token, which dies with too few to split again. The dead token has ceased
    to exist (CR 704.5d) by the time its delayed trigger resolves."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jelly = _jelly_with(scenario, 5)
    scenario.game.destroy(jelly)
    _settle(scenario)
    _to_end_step(scenario)
    (first,) = _jelly_tokens(scenario)
    assert first.counter_count(Counter.PLUS_ONE) == 2

    _to_next_turns_main_phase(scenario)  # bob's turn
    scenario.game.destroy(first)
    _settle(scenario)
    assert not _jelly_tokens(scenario)
    _to_end_step(scenario)
    (second,) = _jelly_tokens(scenario)
    assert second.counter_count(Counter.PLUS_ONE) == 1

    _to_next_turns_main_phase(scenario)
    scenario.game.destroy(second)
    _settle(scenario)
    assert scenario.game.delayed_triggers.triggers == []
    _to_end_step(scenario)
    assert not _jelly_tokens(scenario)


def test_the_copy_is_made_even_if_the_card_left_the_graveyard():
    """CR 603.10a: the trigger looked back; the delayed trigger copies the
    object as it last existed, not the card wherever it is now."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jelly = _jelly_with(scenario, 4)
    scenario.game.destroy(jelly)
    _settle(scenario)
    scenario.game.exile_cards([jelly])
    assert jelly.zone is Zone.EXILE
    _to_end_step(scenario)
    (token,) = _jelly_tokens(scenario)
    assert token.counter_count(Counter.PLUS_ONE) == 2


def test_dying_during_the_end_step_waits_for_the_next_one():
    """CR 603.7a: a delayed ability created after the end step began does not
    see that beginning - it waits for the next turn's end step."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jelly = _jelly_with(scenario, 2)
    _to_end_step(scenario)
    scenario.game.destroy(jelly)
    _settle(scenario)
    assert not _jelly_tokens(scenario)
    _to_next_turns_main_phase(scenario)
    assert not _jelly_tokens(scenario)
    _to_end_step(scenario)
    (token,) = _jelly_tokens(scenario)
    assert token.counter_count(Counter.PLUS_ONE) == 1


def test_a_clone_copying_the_jelly_splits_into_a_jelly_not_a_clone():
    """CR 707.2: the copiable values of the object "it" names include the
    copy effect that made it - a Clone that entered as a copy of Ochre Jelly
    *was* Ochre Jelly on the battlefield (it had Split, which is why it
    triggered), so the token copies Ochre Jelly as it last existed (CR
    603.10a, 608.2h), never the Clone card in the graveyard - which would
    enter as a 0/0 Clone asking for its own copy choice."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Clone"],
            battlefield=[JELLY, "Island", "Island", "Island", "Island"],
            library=["Forest"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jelly = _jelly_with(scenario, 1)  # an X=0 Jelly would die before it is copied
    scenario.will_take_the_may(True, username="alice", source="Clone")
    scenario.will_choose_targets(jelly, username="alice", source="Clone")
    scenario.will_choose_cards(jelly, username="alice", source="Clone")
    # Put onto the battlefield with four +1/+1 counters (CR 614.1c), as the
    # copy of an X=0 Jelly would otherwise die to CR 704.5f on arrival.
    (clone,) = [c for c in scenario.player("alice").hand if c.name == "Clone"]
    scenario.game.put_onto_battlefield(clone, "alice", counters={Counter.PLUS_ONE: 4})
    _settle(scenario)
    assert clone.zone is Zone.BATTLEFIELD
    assert scenario.game.characteristics_of(clone).name == JELLY
    scenario.game.destroy(clone)
    _settle(scenario)
    assert clone.zone is Zone.GRAVEYARD
    assert len(scenario.game.delayed_triggers.triggers) == 1
    _to_end_step(scenario)
    (token,) = _jelly_tokens(scenario)
    assert token.counter_count(Counter.PLUS_ONE) == 2
    assert token.oracle_text == jelly.oracle_text
    assert not [c for c in scenario.game.battlefield if c.name == "Clone"]
