"""Judge scenarios: the intervening *if* clause, checked twice.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#960** - Getting Extra Searches with Ayara's Oathsworn. Amy deals combat
  damage with an Ayara's Oathsworn that already has four +1/+1 counters. Does
  she search again?

The answer is no, and the reason is not "the search clause checks for four" -
it is that the whole ability never triggers. CR 603.4: "A triggered ability may
read 'When/Whenever/At [trigger event], if [condition], [effect].' When the
trigger event occurs, the ability checks whether the stated condition is true.
The ability triggers only if it's true". Both the counter and the search sit
after that condition, in one ability's effect, so failing it costs Amy both.

Card text verified with `resolve_cards`; every CR number here was looked up
with `knowledge_search(type="rules")` in this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind, parse_abilities
from magic_cards_model.machines.triggers import intervening_if_holds
from tests.cards import card
from tests.scenarios.harness import Scenario


def board(counters: int) -> Scenario:
    """Alice attacking with an Ayara's Oathsworn carrying `counters` counters."""
    return (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt"] * 3,
            battlefield=["Ayara's Oathsworn"],
        )
        .player("bob")
    )


def test_the_counter_and_the_search_are_one_ability_behind_one_condition():
    """DDR#960's structural point, read off the card.

    Ayara's Oathsworn (verified with `resolve_cards`): "Whenever this creature
    deals combat damage to a player, if it has fewer than four +1/+1 counters
    on it, put a +1/+1 counter on it. Then if it has exactly four +1/+1
    counters on it, search your library for a card, put it into your hand, then
    shuffle."

    CR 603.1 templates a triggered ability as "[When/Whenever/At] [trigger
    condition or event], [effect]. [Instructions (if any).]", and the whole
    paragraph is one ability. The parser agrees: one `TRIGGERED` ability, whose
    `intervening_if` is the "fewer than four" clause and whose effect carries
    *both* the counter and the search. There is no second trigger to fire the
    search on its own, which is the episode's answer to "can I remove a counter
    in response and search again?"
    """
    abilities = parse_abilities(card("Ayara's Oathsworn"))
    triggered = [ability for ability in abilities if ability.kind is AbilityKind.TRIGGERED]

    assert len(triggered) == 1
    (oathsworn,) = triggered
    assert oathsworn.intervening_if == "it has fewer than four +1/+1 counters on it"
    assert "put a +1/+1 counter on it" in oathsworn.effect
    assert "search your library" in oathsworn.effect


def test_the_counter_comparison_is_read_and_counted():
    """DDR#960 as the engine sees it now: the clause is read, not refused.

    `intervening_if_holds` used to match a fixed set of clause shapes that did
    not include a counter-count comparison, so "it has fewer than four +1/+1
    counters on it" failed closed and recorded an `InterveningIfNotice` -
    which meant the engine got the four-counter case right by accident and the
    zero-counter case wrong for the same reason.

    `_counter_count_holds` now answers it off the permanent's own counters
    (CR 122.1: a counter is "a marker placed on an object ... that ...
    interacts with a rule, ability, or effect"), so CR 603.4's check is a real
    comparison: true below four, false at four, and no notice either way,
    because nothing went unread.
    """
    for counters, expected in ((0, True), (3, True), (4, False), (5, False)):
        scenario = board(counters).build()
        oathsworn = scenario.creature("Ayara's Oathsworn", "alice")
        oathsworn.add_counters("+1/+1", counters)
        ability = parse_abilities(card("Ayara's Oathsworn"))[1]

        assert intervening_if_holds(scenario.game, ability, oathsworn) is expected
        assert scenario.game.intervening_if_notices == []


def test_four_counters_means_no_trigger_at_all():
    """DDR#960's headline answer, which the engine reaches for the wrong reason.

    CR 603.4 again: with four counters already on it, "fewer than four" is
    false when the combat damage is dealt, so the ability does not trigger and
    neither the counter nor the search happens. CR 603.2: "Whenever a game
    event or game state matches a triggered ability's trigger event, that
    ability automatically triggers" - and this one does not.

    The engine agrees on the outcome, and now for the stated reason:
    `intervening_if_holds` counts the four counters and answers false (see
    `test_the_counter_comparison_is_read_and_counted`), rather than refusing
    the clause's shape and failing closed the way it used to.
    """
    scenario = board(4).build()
    oathsworn = scenario.creature("Ayara's Oathsworn", "alice")
    oathsworn.add_counters("+1/+1", 4)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(oathsworn)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.game.put_triggers_on_stack() == []
    assert oathsworn.counters["+1/+1"] == 4
    assert scenario.player("alice").hand == []


@pytest.mark.xfail(
    reason="the trigger itself now works - `machines/triggers.intervening_if_holds` reads the "
    "counter-count comparison and the ability does go on the stack (measured: the "
    "`len(on_stack) == 1` assertion below passes). What is missing is the *effect*: "
    "`machines/effects.py` has no entry for Ayara's Oathsworn, so resolving the ability puts "
    "no fourth counter on and searches no library. That file is Task 2.11's.",
    strict=True,
)
def test_three_counters_still_triggers_and_puts_the_fourth_on():
    """DDR#960's other half: below four, the ability triggers and does both
    things.

    With three counters, "fewer than four" is true when the damage is dealt
    (CR 603.4's first check) and still true as the ability resolves (its
    second), so the fourth counter goes on. CR 608.2c then has the controller
    follow the instructions in the order written, and the "Then if it has
    exactly four" clause is now satisfied by the counter just added - so the
    search happens too.

    The trigger half now runs: the clause is true at three counters, so the
    ability triggers and goes on the stack. The resolution half does not -
    there is no scripted effect for it - so the fourth counter never arrives
    and the search that the "Then if ..." reflexive condition would allow
    never happens either.
    """
    scenario = board(3).build()
    oathsworn = scenario.creature("Ayara's Oathsworn", "alice")
    oathsworn.add_counters("+1/+1", 3)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(oathsworn)
    scenario.no_blocks()
    scenario.combat_damage()
    on_stack = scenario.game.put_triggers_on_stack()

    assert len(on_stack) == 1

    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert oathsworn.counters["+1/+1"] == 4
    assert len(scenario.player("alice").hand) == 1
