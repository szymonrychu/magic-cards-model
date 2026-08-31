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


def test_the_counter_comparison_is_an_intervening_if_the_engine_cannot_read():
    """DDR#960 as the engine sees it: the clause fails closed, audibly.

    `intervening_if_holds` matches a fixed set of clause shapes and returns
    False for anything else, recording an `InterveningIfNotice` rather than
    guessing - the fail-closed discipline `docs/engine-coverage.md` documents.
    "it has fewer than four +1/+1 counters on it" is not one of the shapes it
    knows, so the answer is False even with no counters at all, and a notice
    names the clause.

    That is the honest state, and it is what makes the ruling itself `xfail`
    below: the engine gets the four-counter case right by accident and the
    zero-counter case wrong for the same reason.
    """
    scenario = board(0).build()
    oathsworn = scenario.creature("Ayara's Oathsworn", "alice")
    ability = parse_abilities(card("Ayara's Oathsworn"))[1]

    assert intervening_if_holds(scenario.game, ability, oathsworn) is False

    (notice,) = scenario.game.intervening_if_notices
    assert notice.source_name == "Ayara's Oathsworn"
    assert notice.clause == "it has fewer than four +1/+1 counters on it"


def test_four_counters_means_no_trigger_at_all():
    """DDR#960's headline answer, which the engine reaches for the wrong reason.

    CR 603.4 again: with four counters already on it, "fewer than four" is
    false when the combat damage is dealt, so the ability does not trigger and
    neither the counter nor the search happens. CR 603.2: "Whenever a game
    event or game state matches a triggered ability's trigger event, that
    ability automatically triggers" - and this one does not.

    The engine agrees on the outcome. It reaches it because
    `intervening_if_holds` refuses every shape of this clause (see the test
    above), not because it counted to four - so this passes as a *result* check
    only, and `test_three_counters_still_triggers_and_puts_the_fourth_on` is
    the one that would catch the difference.
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
    reason="machines/triggers.intervening_if_holds cannot read 'it has fewer "
    "than four +1/+1 counters on it' - a counter-count comparison is not "
    "one of its shapes - so it fails closed and the ability never "
    "triggers even when the condition is plainly true",
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

    Not runnable: the intervening *if* fails closed, so nothing reaches the
    stack. The search half would need a second piece anyway - the effect's own
    "Then if ..." reflexive condition - but the trigger never gets that far.
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
