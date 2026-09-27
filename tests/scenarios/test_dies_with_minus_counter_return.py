"""Retched Wretch: "When this creature dies, if it had a -1/-1 counter on
it, return it to the battlefield under its owner's control and it loses all
abilities."

Three rules stack up in this one sentence:

- **CR 603.4/CR 603.10a** - the intervening *if* ("it had a -1/-1 counter on
  it") looks back at the creature as it last existed on the battlefield,
  already read generically by `machines/conditions/objects._has_counters`'s
  past-tense branch (nothing here duplicates that reader).
- **CR 400.7** - the returned permanent is a *new* object: it enters with no
  memory of the counter that sent it to the graveyard, and CR 122.2 means it
  comes back with zero counters even though it "had" one a moment ago.
- **CR 613.1f** - "it loses all abilities" is a fresh layer 6 removal on that
  new incarnation, the identical `machines/layers.lose_all_abilities`
  modification Humility and the Enduring cycle's own dies trigger already
  apply elsewhere - reused here, not reimplemented
  (`machines/minus_counters._parse_return_self_loses_all_abilities_clause`).

No second Modern/Pioneer/Standard-legal printing of this exact combined
"return it to the battlefield under its owner's control and it loses all
abilities" sentence exists - a Scryfall full-text search turned up only
Retched Wretch itself (dated MEMORY.md line records the search). The two
primitives this reader glues together are each independently precedented
elsewhere in the pool already (a plain "return it to the battlefield under
its owner's control" shape, and `lose_all_abilities` itself, both proven on
cards that are not this one), so this file's own multiple scenarios - with
and without the counter, and a second death after the ability is gone - are
what prove the combination rather than a single happy path.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return Scenario().player("alice", battlefield=["Retched Wretch"]).player("bob")


def test_dying_with_a_counter_returns_the_creature_with_no_abilities():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wretch = scenario.creature("Retched Wretch")
    wretch.add_counters(Counter.MINUS_ONE, 1)

    scenario.game.destroy(wretch)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert wretch.zone is Zone.BATTLEFIELD
    assert wretch.counter_count(Counter.MINUS_ONE) == 0, "CR 122.2: a new object, no counters"
    assert (wretch.power, wretch.toughness) == (4, 2)


def test_the_returned_creature_has_lost_its_own_dies_trigger():
    """CR 613.1f: "loses all abilities" takes the trigger itself away, so a
    second death does not return it again."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wretch = scenario.creature("Retched Wretch")
    wretch.add_counters(Counter.MINUS_ONE, 1)

    scenario.game.destroy(wretch)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert wretch.zone is Zone.BATTLEFIELD

    scenario.game.destroy(wretch)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert wretch.zone is Zone.GRAVEYARD


def test_dying_clean_does_not_return_it():
    """CR 603.4: no -1/-1 counter, so the intervening *if* is false and the
    ability never triggers at all - not a trigger that resolves and does
    nothing."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wretch = scenario.creature("Retched Wretch")
    assert wretch.counter_count(Counter.MINUS_ONE) == 0

    scenario.game.destroy(wretch)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert wretch.zone is Zone.GRAVEYARD


def test_a_response_that_exiles_the_card_leaves_nothing_to_return():
    """CR 400.7: exiled in response, it is a new object no longer in the
    graveyard it died into - the trigger still resolves, but finds nothing
    of its own left to act on."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wretch = scenario.creature("Retched Wretch")
    wretch.add_counters(Counter.MINUS_ONE, 1)

    scenario.game.destroy(wretch)
    scenario.game.put_triggers_on_stack()
    scenario.game.exile_cards([wretch])
    scenario.pass_until_resolved()

    assert wretch.zone is Zone.EXILE
