"""Scenario: a triggered ability's own mandatory "remove N `<kind>` counter(s)
from it." effect, self-referential the way CR 607.1's within-one-ability
anaphora already reads "it" elsewhere in this pool.

Clockwork Steed: "At end of combat, if this creature attacked or blocked
this combat, remove a +1/+0 counter from it." The intervening *if* (CR
603.4) is a separate workstream's own condition reader
(`machines/triggers.py`) and is not wired to this trigger yet, so this file
reaches the effect the same direct way `test_counters_that_many_trigger.py`
reaches Marauding Mako's "that many" effect when its own triggering event
cannot yet be constructed live: through the parser, with a real
`AbilityOnStack` built by hand and `event=None`.

Every CR number here was looked up with `mise run rules:find <n>` in the
session that wrote this file:

- **CR 122.1a** - what a +1/+1 (or, generally, a +X/+Y) counter does.
- **CR 607.1** - within-one-ability anaphora ("it" pointing back to the
  object an earlier clause of the same ability already named).
- **CR 609.3** - "If an effect attempts to do something impossible, it does
  only as much as possible" - removing more counters than are present.
"""

from magic_cards_model.machines.abilities import parse_abilities
from magic_cards_model.machines.effects import _parse_remove_n_counters_from_self_clause
from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _triggered_ability(card_name: str, index: int):
    return parse_abilities(card(card_name))[index]


def test_clockwork_steeds_own_trigger_removes_one_counter():
    """Four +1/+0 counters on it, as it enters with (proven separately in
    `test_counters.py`/`test_up_to_x_counters_with_total_cap.py`) - the
    trigger takes exactly one off."""
    effect = _parse_remove_n_counters_from_self_clause("remove a +1/+0 counter from it.")
    assert effect is not None

    scenario = Scenario().player("alice", battlefield=["Clockwork Steed"]).player("bob").build()
    steed = scenario.creature("Clockwork Steed")
    steed.add_counters("+1/+0", 4)
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=_triggered_ability("Clockwork Steed", 2),
        source_id=steed.id,
        source_name="Clockwork Steed",
        controller="alice",
        event=None,
    )

    effect(scenario.game, ability)

    assert steed.counter_count("+1/+0") == 3
    assert scenario.game.characteristics_of(steed).power == 3


def test_removing_more_than_present_takes_only_what_is_there():
    """CR 609.3: no counters on it at all - "remove a counter" removes zero,
    never errors."""
    effect = _parse_remove_n_counters_from_self_clause("remove a +1/+0 counter from it.")
    assert effect is not None

    scenario = Scenario().player("alice", battlefield=["Clockwork Steed"]).player("bob").build()
    steed = scenario.creature("Clockwork Steed")
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=_triggered_ability("Clockwork Steed", 2),
        source_id=steed.id,
        source_name="Clockwork Steed",
        controller="alice",
        event=None,
    )

    effect(scenario.game, ability)

    assert steed.counter_count("+1/+0") == 0


def test_the_reader_is_general_across_counter_kind_and_amount():
    """A made-up "remove 2 charge counters from it." - a different kind and a
    different fixed amount than Clockwork Steed's own "a +1/+0 counter" -
    proving the grammar rather than Steed's own sentence."""
    effect = _parse_remove_n_counters_from_self_clause("remove 2 charge counters from it.")
    assert effect is not None

    scenario = Scenario().player("alice", battlefield=["Sol Ring"]).player("bob").build()
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    ring.add_counters("charge", 5)
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=_triggered_ability("Clockwork Steed", 2),
        source_id=ring.id,
        source_name="Sol Ring",
        controller="alice",
        event=None,
    )

    effect(scenario.game, ability)

    assert ring.counter_count("charge") == 3
