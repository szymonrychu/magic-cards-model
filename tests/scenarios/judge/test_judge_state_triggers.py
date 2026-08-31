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

The Calendar's ability now parses as a trigger condition (the comma inside
"1,000" is no longer read as the CR 603.1 boundary), but there is still no
state-trigger machinery for it to plug into, so the ruling itself remains out
of reach.

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


def test_a_thousand_time_counters_trigger_nothing():
    """DDR#961's premise, which the engine never even reaches.

    CR 603.8's state trigger should fire the moment the game state matches -
    CR 603.2: "Whenever a game event or game state matches a triggered
    ability's trigger event, that ability automatically triggers" - and
    CR 704.1a is explicit that these are triggered abilities, not state-based
    actions.

    With a thousand time counters sitting on the Calendar, nothing goes on the
    stack, the Calendar is not sacrificed, and Bob keeps his 20 life. Recorded
    as the honest baseline the `xfail` below is measured against.
    """
    scenario = (
        Scenario().player("alice", battlefield=["The Millennium Calendar"]).player("bob").build()
    )
    calendar = scenario.find("The Millennium Calendar", Zone.BATTLEFIELD, "alice")
    calendar.add_counters("time", 1000)

    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.game.pending_triggers == []
    assert scenario.stack_names() == []
    assert calendar.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 20


@pytest.mark.xfail(
    reason="CR 603.8 state triggers are not modelled at all: the Calendar's "
    "condition parses now, but nothing watches the game state for it, so "
    "nothing ever triggers to be countered, re-trigger, or resolve",
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
