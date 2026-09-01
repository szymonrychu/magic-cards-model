"""Judge scenarios: abilities that trigger on a *game state*, not an event.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#961** - The Millennium Calendar vs. Tishana's Tidebinder. Amy puts the
  thousandth time counter on The Millennium Calendar, triggering its last
  ability. Nick counters that ability with Tishana's Tidebinder. Is the
  Calendar sacrificed? Does Nick lose life?

He does. CR 603.8 covers abilities that "trigger when a game state ... is true,
rather than triggering when an event occurs", and the reason Dark Depths does
not loop forever is that such an ability, once it has triggered, will not
trigger again until the first one has left the stack. Countering it *is*
leaving the stack (CR 701.6a), so the state trigger is free the instant
Tishana's Tidebinder's first sentence finishes - and the Tidebinder's second
sentence, which strips the Calendar's abilities, only runs afterwards
(CR 608.2c: instructions are followed in the order written). By the time the
second trigger reaches the stack the Calendar has no abilities left, so nothing
stops it.

The Calendar's ability parses as a trigger condition (the comma inside "1,000"
is no longer read as the CR 603.1 boundary), and CR 603.8's own machinery is
now built: `machines/triggers.state_triggers_for` sweeps the battlefield for a
"there are N or more <kind> counters on <this permanent>" condition wherever
triggers are flushed before priority, and `Game.state_trigger_latches` holds
each one shut until its ability has left the stack - by resolving *or* by being
countered (CR 701.6a: "To counter a spell or ability means to cancel it,
removing it from the stack").

CR 704.1a is what puts this in `machines/triggers.py` rather than among the
state-based actions: "Abilities that watch for a specified game state are
triggered abilities, not state-based actions."

The full ruling is still `xfail`, for one reason and one only: the Calendar's
own *effect* ("sacrifice it and each opponent loses 1,000 life") has no entry
in `machines/effects.py`, so the second trigger resolves and does nothing.

Card text verified with `resolve_cards`; every CR number here was looked up
with `knowledge_search(type="rules")` in this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind, parse_abilities
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_the_calendars_state_trigger_condition_reads_past_the_number():
    """DDR#961's first obstacle, now cleared.

    The Millennium Calendar (verified with `resolve_cards`): "When there are
    1,000 or more time counters on The Millennium Calendar, sacrifice it and
    each opponent loses 1,000 life."

    CR 603.1 templates the ability as "[When] [trigger condition], [effect]",
    and `machines/abilities.py` cuts at the first top-level comma to find that
    boundary. It used to cut inside the number, leaving the condition as
    "there are 1"; a comma between two digits is no longer a boundary, so the
    whole condition survives.

    What is still missing is CR 603.8's state-trigger machinery itself - the
    condition parses, but nothing watches the game state for it, which is what
    the `xfail` below is measured against.
    """
    abilities = parse_abilities(card("The Millennium Calendar"))
    triggered = [ability for ability in abilities if ability.kind is AbilityKind.TRIGGERED]
    state_trigger = triggered[-1]

    assert state_trigger.condition == (
        "there are 1,000 or more time counters on The Millennium Calendar"
    )
    assert state_trigger.effect == "sacrifice it and each opponent loses 1,000 life."
    assert state_trigger.event is None, "no TriggerEvent shape was matched for it"


def test_a_thousand_time_counters_trigger_once_and_then_latch():
    """DDR#961's premise.

    CR 603.8's state trigger fires the moment the game state matches -
    CR 603.2: "Whenever a game event or game state matches a triggered
    ability's trigger event, that ability automatically triggers" - and
    CR 704.1a is explicit that these are triggered abilities, not state-based
    actions ("Abilities that watch for a specified game state are triggered
    abilities, not state-based actions").

    CR 603.3 then puts it on the stack "the next time a player would receive
    priority", which is what `put_triggers_on_stack` represents. The rest of
    CR 603.8 is the latch that keeps Dark Depths from looping: the ability
    "doesn't trigger again until it has left the stack", so a second sweep
    while the first is still sitting there produces nothing.

    999 counters is not the condition, and 1,001 is - the count is read past
    its own digit-group comma.
    """
    scenario = (
        Scenario().player("alice", battlefield=["The Millennium Calendar"]).player("bob").build()
    )
    calendar = scenario.find("The Millennium Calendar", Zone.BATTLEFIELD, "alice")
    calendar.add_counters("time", 999)

    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.put_triggers_on_stack() == [], "999 is not 1,000 or more"

    calendar.add_counters("time", 2)
    (first,) = scenario.game.put_triggers_on_stack()

    assert first.source_name == "The Millennium Calendar"
    assert first.controller == "alice"
    assert scenario.stack_names() == ["The Millennium Calendar's triggered ability"]
    # CR 603.8's latch: still on the stack, so it has not triggered again.
    assert scenario.game.put_triggers_on_stack() == []


def test_the_state_trigger_fires_again_once_the_first_one_has_resolved():
    """The other half of CR 603.8's latch: the ability left the stack, so it may
    trigger again, and it does.

    Why it does is currently the gate named in the `xfail` below - the
    Calendar's effect is written in `machines/effects.py` but `Game._effect_of`
    never asks for it, so the ability resolves doing nothing and the thousand
    counters are still sitting there when the sweep next runs. Once that gate
    is dropped the ability really does sacrifice the Calendar, and the sweep
    *still* produces a second trigger, because `Game.sacrifice` emits
    CR 603.10a's look-back `IS_SACRIFICED` event while the permanent is still
    on the battlefield and `Game.emit` runs the CR 603.8 sweep on it. That is
    a `models/game.py` timing question, not this file's; either way the rule
    being asserted here - "doesn't trigger again until it has left the stack" -
    holds."""
    scenario = (
        Scenario().player("alice", battlefield=["The Millennium Calendar"]).player("bob").build()
    )
    calendar = scenario.find("The Millennium Calendar", Zone.BATTLEFIELD, "alice")
    calendar.add_counters("time", 1000)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (first,) = scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    # `resolve_top` flushes CR 603.3's triggers itself, so the second one is
    # already there: the ability left the stack, the condition is still true.
    assert scenario.stack_names() == ["The Millennium Calendar's triggered ability"]
    (second,) = scenario.game.stack
    assert second.id != first.id


@pytest.mark.xfail(
    reason="ONE gap, and it is one line in models/game.py. The Calendar's own effect is built "
    "now - `machines/effects._parse_sacrifice_self_clause` reads 'sacrifice it' (CR 701.21a) "
    "and `parse_clause_effect` reads 'each opponent loses 1,000 life' past its digit-group "
    "comma - and `trigger_effect_for` accepts `event=None` so a CR 603.8 state trigger, which "
    "has no `TriggerEvent` to be keyed under, reaches the text-driven fallback. But "
    "`Game._effect_of` is gated on `and ability.ability.event is not None`, so it never asks "
    "`trigger_effect_for` at all for such an ability and the trigger resolves doing nothing. "
    "Dropping that one conjunct from the `isinstance(ability.ability, TriggeredAbility)` test "
    "makes this test - and both Caged Sun tests in test_judge_mana_abilities.py, whose trigger "
    "condition is also unread by the event parser - pass, with no other change anywhere in "
    "the suite.",
    strict=True,
)
def test_countering_the_state_trigger_lets_it_trigger_again_before_the_abilities_go():
    """DDR#961's ruling, in full.

    Tishana's Tidebinder (verified with `resolve_cards`): "When this creature
    enters, counter up to one target activated or triggered ability. If an
    ability of an artifact, creature, or planeswalker is countered this way,
    that permanent loses all abilities for as long as this creature remains on
    the battlefield."

    The sequence the episode walks through, rule by rule:

    1. The Tidebinder's first sentence counters the Calendar's trigger.
       CR 701.6a: countering removes it from the stack.
    2. The Calendar still has a thousand time counters and its state trigger is
       no longer on the stack, so CR 603.8 lets it trigger again immediately.
       CR 603.3 has it wait to be put on the stack "the next time a player would
       receive priority" - and CR 603.2 is clear that triggering needs no
       priority of its own.
    3. Only *then* does the Tidebinder's second sentence strip the Calendar's
       abilities (CR 608.2c, instructions in the order written).
    4. The second trigger goes on the stack and resolves. Bob loses 1,000 life
       and is dead by CR 704.5a.

    Nothing here is buildable: `machines/triggers.py` has no notion of a
    condition that is re-checked once the ability leaves the stack, so even a
    Calendar whose text parsed would only ever trigger once, if at all.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Millennium Calendar"])
        .player("bob", hand=["Tishana's Tidebinder"], battlefield=["Island"] * 3)
        .build()
    )
    calendar = scenario.find("The Millennium Calendar", Zone.BATTLEFIELD, "alice")
    calendar.add_counters("time", 1000)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (first_trigger,) = scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")
    scenario.choose_trigger_targets("Tishana's Tidebinder", [first_trigger])
    scenario.cast_and_resolve(
        "Tishana's Tidebinder",
        *scenario.untapped_sources("Island", "Island", "Island", username="bob"),
        username="bob",
    )
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert calendar.zone is Zone.GRAVEYARD, "the second trigger sacrificed it"
    assert scenario.player("bob").life == -980
