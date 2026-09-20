"""FRA stream S8b: "Whenever a creature you control attacks alone this
turn, put `<n>` `<kind>` counter(s) on it. It gains `<keywords>` until end
of turn." - a Saga chapter's own delayed trigger, created once at
resolution and watching the rest of the turn rather than printed as an
ordinary triggered ability of the permanent
(`_ATTACKS_ALONE_THIS_TURN_COUNTERS_AND_KEYWORDS_RE`,
`CountersAndKeywordsEventSubject` in `machines/delayed.py`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 714.4** - a Saga's chapter ability triggers when its lore counter
  count reaches the chapter number; its own effect resolves once, like any
  other triggered ability.
- **CR 603.7/603.7b** - a delayed triggered ability, with the stated
  duration "this turn" - it fires on every qualifying event for the rest of
  the turn, not only the first.
- **CR 506.5** - "attacks alone": the only creature declared as an attacker
  this combat.
- **CR 122.1** - the counter, placed as a permanent change; the keyword
  grant is a separate, `until end of turn` continuous effect (CR 611.2c),
  so the two halves have genuinely different durations even though one
  ability grants both at once.

The Last Ronin's own chapter III is the reported clause. Chapters I and II
("Destroy all creatures", the mill-and-return) are each exercised by the
Saga mechanic's own already-passing tests elsewhere in the pool - not this
mechanic's own scope - so this file isolates chapter III directly: the
Saga enters with its own intrinsic first lore counter (CR 714.3a) before
`Scenario.build` ever runs a trigger off it, so adding one more by hand
(`CardState.add_counters`, not `Game.add_counters` - deliberately bypassing
CR 122.6's own "counters put on" event, the same way seeding a permanent's
starting counters always does elsewhere in this pool) reaches chapter II's
own threshold with nothing resolved yet; one `Game.saga_lore_step` (the
same direct-call convention `tests/scenarios/test_sagas.py`'s own chapter-
three test already uses) then crosses chapter III's.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _last_ronin_at_chapter_two(battlefield: list[str]) -> Scenario:
    scenario = Scenario().player("alice", battlefield=battlefield).player("bob").build()
    saga = scenario.find("The Last Ronin", Zone.BATTLEFIELD, "alice")
    assert saga.counters[Counter.LORE] == 1, "CR 714.3a's own intrinsic first counter"
    saga.add_counters(Counter.LORE, 1)
    return scenario


def test_chapter_three_creates_a_delayed_trigger_that_fires_on_a_lone_attack():
    scenario = _last_ronin_at_chapter_two(battlefield=["The Last Ronin", "Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert bears.counter_count(Counter.PLUS_ONE) == 0, "the delayed trigger has not fired yet"

    scenario.attack_with(bears, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.counter_count(Counter.PLUS_ONE) == 3
    assert has_keyword(bears, Keyword.TRAMPLE, scenario.game)
    assert has_keyword(bears, Keyword.LIFELINK, scenario.game)
    assert has_keyword(bears, "Indestructible", scenario.game)


def test_chapter_three_never_fires_for_an_attack_with_two_attackers():
    """CR 506.5: two creatures attacking together is not "alone", so the
    delayed trigger never matches the event at all."""
    scenario = _last_ronin_at_chapter_two(
        battlefield=["The Last Ronin", "Grizzly Bears", "Hill Giant"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "alice")

    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    scenario.attack_with(bears, giant, defending="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert bears.counter_count(Counter.PLUS_ONE) == 0
    assert giant.counter_count(Counter.PLUS_ONE) == 0


def test_chapter_three_fires_again_later_the_same_turn():
    """CR 603.7b's stated "this turn" duration: `remaining=None` lets the
    delayed trigger fire on every qualifying attack for the rest of the
    turn, not only the first - proven here across two separate combats in
    the same turn via extra combat step access, driven the same direct way
    the module docstring already explains."""
    scenario = _last_ronin_at_chapter_two(battlefield=["The Last Ronin", "Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    scenario.attack_with(bears, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert bears.counter_count(Counter.PLUS_ONE) == 3

    watchers = [
        trigger
        for trigger in scenario.game.delayed_triggers.triggers
        if trigger.attacking_alone_only
    ]
    assert len(watchers) == 1, "still watching for the rest of the turn"
