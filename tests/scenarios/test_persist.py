"""Persist: coming back once, with a -1/-1 counter (CR 702.79).

CR 702.79a: "Persist is a triggered ability. 'Persist' means "When this permanent
is put into a graveyard from the battlefield, if it had no -1/-1 counters on it,
return it to the battlefield under its owner's control with a -1/-1 counter on
it.""

The intervening *if* is the whole mechanic, and it is asked about the permanent
as it *last existed*: CR 122.2 destroys an object's counters as it changes
zones, so by the time the trigger resolves there are no counters left to look
at. CR 603.10a lets a dies trigger look back in time and CR 704.8 calls that
last known information; `CardState.last_known_counters` is where it is kept.

So a Kitchen Finks that dies clean comes back, and the one that comes back dies
for good - which is the corner case that separates persist from a loop.

The trigger now happens on its own: `machines/keywords.keyword_triggered_abilities`
writes CR 702.79a's expansion out as a `TriggeredAbility`, intervening *if* and
all, and `machines/triggers.py` matches the dies event against it like any
printed trigger. What it does when it resolves is `persist_return`, and that is
still driven by hand here - see the xfail at the bottom and
`docs/engine-coverage.md`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.keywords import (
    has_persist,
    keyword_triggered_abilities,
    persist_return,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.cards import card
from tests.scenarios.harness import Scenario

NO_KEYWORD_EFFECT_DISPATCH = (
    "The persist trigger is generated, its intervening if is checked at CR 603.4 and "
    "again at CR 608.2a, and it goes on the stack - then resolves doing nothing: "
    "Game._effect_of looks an ability's effect up by (card name, event) in "
    "machines/effects.TRIGGER_EFFECTS, and a keyword ability belongs to no card name. "
    "machines/keywords.keyword_effect_for answers and nothing consults it. "
    "See docs/engine-coverage.md."
)


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Kitchen Finks", "Mountain"], hand=["Lightning Bolt"])
        .player("bob", battlefield=["Colossal Dreadmaw"])
    )


def test_persist_is_read_off_the_printing():
    assert has_persist(card("Kitchen Finks"))
    assert not has_persist(card("Grizzly Bears"))


def test_a_creature_that_dies_clean_comes_back_with_a_counter():
    """CR 702.79a, the whole ability."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    finks = scenario.creature("Kitchen Finks")

    scenario.game.destroy(finks)
    assert finks.zone is Zone.GRAVEYARD

    assert persist_return(scenario.game, finks) is finks
    assert finks.zone is Zone.BATTLEFIELD
    assert finks.counter_count(Counter.MINUS_ONE) == 1


def test_the_returned_creature_is_smaller():
    """CR 122.1a: a -1/-1 counter takes a 3/2 down to a 2/1."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    finks = scenario.creature("Kitchen Finks")
    assert (finks.power, finks.toughness) == (3, 2)

    scenario.game.destroy(finks)
    persist_return(scenario.game, finks)

    assert (finks.power, finks.toughness) == (2, 1)


def test_persist_does_not_fire_twice():
    """The intervening *if*: the second death had a -1/-1 counter on it."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    finks = scenario.creature("Kitchen Finks")

    scenario.game.destroy(finks)
    persist_return(scenario.game, finks)
    scenario.game.destroy(finks)

    assert persist_return(scenario.game, finks) is None
    assert finks.zone is Zone.GRAVEYARD


def test_the_if_reads_the_counters_it_had_as_it_left():
    """CR 704.8: last known information, because CR 122.2 has already wiped them."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    finks = scenario.creature("Kitchen Finks")
    finks.add_counters(Counter.MINUS_ONE, 1)

    scenario.game.destroy(finks)
    assert finks.counter_count(Counter.MINUS_ONE) == 0  # CR 122.2
    assert finks.last_known_counters[Counter.MINUS_ONE] == 1

    assert persist_return(scenario.game, finks) is None


def test_a_creature_killed_by_its_own_persist_counter_stays_dead():
    """A 3/2 that comes back a 2/1 and takes a second counter dies to CR 704.5f."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    finks = scenario.creature("Kitchen Finks")

    scenario.game.destroy(finks)
    persist_return(scenario.game, finks)
    scenario.game.add_counters(finks, Counter.MINUS_ONE, 1)
    scenario.state_based_actions()

    assert finks.zone is Zone.GRAVEYARD
    assert persist_return(scenario.game, finks) is None


def test_persist_refuses_a_creature_that_is_not_in_a_graveyard():
    """The trigger is "put into a graveyard from the battlefield" and nothing else."""
    scenario = board().build()
    finks = scenario.creature("Kitchen Finks")

    with pytest.raises(ValueError, match="not a graveyard"):
        persist_return(scenario.game, finks)


def test_persist_refuses_a_card_without_the_keyword():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.game.destroy(dreadmaw)

    with pytest.raises(ValueError, match="no persist ability"):
        persist_return(scenario.game, dreadmaw)


def test_persist_is_a_triggered_ability_the_engine_can_produce():
    """CR 702.79a: a triggered ability with an intervening *if* (CR 603.4)."""
    abilities = keyword_triggered_abilities(card("Kitchen Finks"))
    (ability,) = [a for a in abilities if a.keyword == "persist"]
    assert ability.event is TriggerEvent.DIES
    assert ability.intervening_if == "it had no -1/-1 counters on it"
    assert ability.effect == (
        "return it to the battlefield under its owner's control with a -1/-1 counter on it"
    )


def test_dying_clean_puts_the_persist_trigger_on_the_stack():
    """CR 603.2 and CR 603.10a: the dies event finds the keyword's trigger.

    Nothing here drives persist. The Finks is destroyed and the trigger is on
    the stack the next time a player would receive priority.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    finks = scenario.creature("Kitchen Finks")

    scenario.game.destroy(finks)
    scenario.game.put_triggers_on_stack()

    assert "Kitchen Finks's triggered ability" in scenario.stack_names()


def test_the_intervening_if_stops_it_triggering_a_second_time():
    """CR 603.4: a false clause means it does not trigger *at all*.

    The Finks that has already persisted has a -1/-1 counter on it, and CR 122.2
    puts that counter into `last_known_counters` as it dies. So there is no
    second trigger to respond to, which is a different thing from a trigger that
    resolves and does nothing.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    finks = scenario.creature("Kitchen Finks")

    scenario.game.destroy(finks)
    persist_return(scenario.game, finks)
    assert finks.counter_count(Counter.MINUS_ONE) == 1
    scenario.game.pending_triggers.clear()
    scenario.game.stack.clear()

    scenario.game.destroy(finks)

    assert scenario.game.pending_triggers == []


def test_the_persist_trigger_returns_the_creature_when_it_resolves():
    """CR 702.79a's effect half, applied by the game rather than by the test."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    finks = scenario.creature("Kitchen Finks")

    scenario.game.destroy(finks)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert finks.zone is Zone.BATTLEFIELD
    assert finks.counter_count(Counter.MINUS_ONE) == 1
