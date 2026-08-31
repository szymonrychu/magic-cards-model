"""Scenario: "whenever one or more counters are put on this permanent".

Basking Broodscale is the engine of the broodscale-bloodchief archetype, and
until now its trigger did not exist at all: `machines/abilities._trigger_event`
had no `TriggerEvent` for a counters-placed condition, so the ability parsed
with `event=None` and `triggered_abilities_of` dropped it. `machines/triggers.py`
now reads the condition itself (`_unread_trigger_events` ->
`ExtraTriggerEvent.COUNTERS_PUT`) and matches it.

The matcher is complete; the **emit is not**. `Game.add_counters`
(`models/game.py`, Task 1.5's file) is the one place counters are put on a
permanent, and it emits only for lore counters (CR 107.15a's Saga chapters), so
adapting the Broodscale still fires nothing - see the strict `xfail` at the end,
which is the whole remaining gap in one assertion.

Card text verified with `resolve_cards`. Every CR number here was looked up with
`knowledge_search(type="rules")` in the session that wrote this file:

- **CR 122.6** - "Some spells and abilities refer to counters being put on an
  object. This refers to putting counters on that object while it's on the
  battlefield and also to an object that's given counters as it enters the
  battlefield."
- **CR 122.1** - "A counter is a marker placed on an object or player that
  modifies its characteristics and/or interacts with a rule, ability, or
  effect." The kind is any name at all, which is why the matcher compares the
  kind the condition names against the kind the event carries.
- **CR 701.46a** - "'Adapt N' means 'If this permanent has no +1/+1 counters on
  it, put N +1/+1 counters on it.'"
- **CR 603.2c** - "An ability triggers only once each time its trigger event
  occurs. However, it can trigger repeatedly if one event contains multiple
  occurrences." "One or more counters" is one event with a count, so two
  counters arriving together are one trigger, not two.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import ExtraTriggerEvent, GameEvent
from tests.scenarios.harness import Scenario


def broodscale_board() -> Scenario:
    """Alice with a Basking Broodscale and enough green mana to adapt it."""
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Basking Broodscale",
                "Grizzly Bears",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
            ],
        )
        .player("bob")
    )


def counters_put(scenario, permanent, kind: str = "+1/+1", amount: int = 1) -> GameEvent:
    """The CR 122.6 event, raised through `Game.emit` - the real dispatcher.

    Staging the event rather than the action is deliberate and is the only
    honest way to test the matcher today: nothing in `models/game.py` raises
    it, which is exactly what the `xfail` at the bottom of this file records.
    Everything downstream of the event - `Game.emit`'s source sweep,
    `triggers_for`, `condition_matches`, CR 603.3's stack - is the engine's own.
    """
    event = GameEvent(
        event=ExtraTriggerEvent.COUNTERS_PUT,
        subject_id=permanent.id,
        subject_name=permanent.name,
        subject_controller=permanent.controller,
        subject_card=permanent.card,
        subject_types=permanent.types,
        subject_subtypes=permanent.subtypes,
        counter_kind=kind,
        amount=amount,
        player=permanent.controller,
    )
    scenario.game.emit(event)
    return event


def test_counters_put_on_the_broodscale_trigger_its_ability():
    """CR 122.6's event, matched against the Broodscale's own condition.

    "Whenever one or more +1/+1 counters are put on this creature, you may
    create a 0/1 colorless Eldrazi Spawn creature token" - one +1/+1 counter
    put on it is that event, and the ability triggers (CR 603.2).
    """
    scenario = broodscale_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    broodscale = scenario.creature("Basking Broodscale", "alice")

    counters_put(scenario, broodscale)

    assert [trigger.source_name for trigger in scenario.pending_triggers] == ["Basking Broodscale"]


def test_two_counters_at_once_are_one_trigger():
    """CR 603.2c: one event with two occurrences of nothing - one event, one
    trigger. The condition says "one or more", so the count is part of the
    event rather than a repetition of it."""
    scenario = broodscale_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    broodscale = scenario.creature("Basking Broodscale", "alice")

    counters_put(scenario, broodscale, amount=2)

    assert len(scenario.pending_triggers) == 1


def test_counters_on_another_creature_do_not_trigger_it():
    """The negative half. The condition names *this creature* (CR 122.6 is
    about counters put on "that object"), so a counter arriving on the Bears
    next to it is not the Broodscale's event."""
    scenario = broodscale_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    counters_put(scenario, bears)

    assert scenario.pending_triggers == []


def test_a_counter_of_another_kind_does_not_trigger_it():
    """The other negative. CR 122.1 leaves the set of counter kinds open, and
    the condition names one: a charge counter put on the Broodscale is a real
    CR 122.6 event that this ability does not watch."""
    scenario = broodscale_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    broodscale = scenario.creature("Basking Broodscale", "alice")

    counters_put(scenario, broodscale, kind="charge")

    assert scenario.pending_triggers == []


def test_emperor_of_bones_watches_its_own_counters_the_same_way():
    """The second printing of the shape in the pool, so the matcher is not
    fitted to one card: Emperor of Bones' "Whenever one or more +1/+1 counters
    are put on this creature, put a creature card exiled with this creature
    onto the battlefield ...".
    """
    scenario = (
        Scenario().player("alice", battlefield=["Emperor of Bones", "Swamp"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emperor = scenario.creature("Emperor of Bones", "alice")

    counters_put(scenario, emperor)

    assert [trigger.source_name for trigger in scenario.pending_triggers] == ["Emperor of Bones"]


def test_a_second_adapt_puts_no_counter_on_and_so_fires_nothing():
    """CR 701.46a: "If this permanent has no +1/+1 counters on it, put N +1/+1
    counters on it" - a Broodscale that already has one gets none, so there is
    no CR 122.6 event and nothing to trigger. This half needs no emit at all:
    the absence of the event is the whole point, and the engine plays the
    adapt for real.
    """
    scenario = broodscale_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    broodscale = scenario.creature("Basking Broodscale", "alice")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", username="alice")

    scenario.activate(broodscale, *forests[:2])
    scenario.resolve_top()
    assert broodscale.counter_count("+1/+1") == 1

    scenario.activate(broodscale, *forests[2:])
    scenario.resolve_top()

    assert broodscale.counter_count("+1/+1") == 1, "CR 701.46a's own condition"
    assert scenario.pending_triggers == []


@pytest.mark.xfail(
    strict=True,
    reason="the matcher is here and works (every test above), but nothing emits the CR 122.6 "
    "event: `Game.add_counters` in models/game.py - Task 1.5's file - is the single place "
    "counters are put on a permanent and it emits only for lore counters (CR 107.15a). "
    "Adapting the Broodscale therefore puts the counter on and triggers nothing.",
)
def test_adapting_the_broodscale_creates_an_eldrazi_spawn():
    """The plan's own scenario, end to end.

    CR 701.46a's adapt puts a +1/+1 counter on the Broodscale, which is CR
    122.6's event, which triggers "you may create a 0/1 colorless Eldrazi Spawn
    creature token with 'Sacrifice this token: Add {C}.'" - the loop the whole
    broodscale-bloodchief archetype is built out of.
    """
    scenario = broodscale_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    broodscale = scenario.creature("Basking Broodscale", "alice")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", username="alice")

    scenario.activate(broodscale, *forests[:2])
    scenario.resolve_top()

    assert broodscale.counter_count("+1/+1") == 1
    assert [trigger.source_name for trigger in scenario.pending_triggers] == ["Basking Broodscale"]
