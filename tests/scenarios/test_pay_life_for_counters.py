"""An optional cost paid on resolution, its amount read off another
permanent's own characteristic (CR 118.12, CR 119.4): "Whenever another
creature you control enters, you may pay life equal to its power. If you do,
put that many +1/+1 counters on it." (Madame Null, Power Broker).

The trigger condition itself, "another creature you control enters", is
already generic (EPF Point Squad's own Alliance trigger already reads and
plays it); this file is only about `machines/counter_payoffs._may_pay_life_
equal_to_its_power_then_counters`'s own resolution.

"That many" here is *not* CR 607.1's anaphora onto the triggering event
(`machines/effects.that_many`, which reads `GameEvent.amount`) - the
triggering ENTERS_THE_BATTLEFIELD event carries no such count at all. It is
the amount of life actually paid, computed and paid by this resolution
itself, which is why `machines/counter_payoffs.py`'s own docstring records
this reader as its own case rather than delegating to `that_many`.

No second Modern/Pioneer/Standard-legal printing combines "pay life equal to
a characteristic" with "put that many counters" (verified via `card_search`
in the session that wrote this file - see the dated MEMORY.md line), so this
file proves the reader only on Madame Null herself, across the corner cases
that matter: declining the cost, a life total too low to pay, and a 0-power
entering creature.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 118.12** - "[A player] may [do something]. If [that player] does,
  [effect]" - the action is a cost, paid on resolution.
- **CR 119.4** - paying life: only legal at or above the life total being
  paid, and 0 is always payable.
- **CR 107.1a** - "equal to" defines an amount by another value in the game.
- **CR 603.6** - a trigger condition tested only once, when the event occurs;
  changing the entering creature's power afterward does not change what was
  already paid.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(hand):
    return (
        Scenario()
        .player("alice", battlefield=["Madame Null, Power Broker"], hand=list(hand))
        .player("bob")
    )


def _enter(scenario, name):
    """Put `name` onto the battlefield from alice's hand as a real
    ENTERS_THE_BATTLEFIELD event (`tests/scenarios/harness.py`'s own
    "battlefield=" bypasses actually casting anything" convention is for the
    *starting* board only - this is mid-game, so it goes through the real
    zone-change primitive, then the ordinary priority machinery puts
    whatever it triggered on the stack)."""
    card = scenario.find(name, Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(card, "alice")
    scenario.game.put_triggers_on_stack()
    return card


def test_paying_life_equal_to_the_entering_creatures_power_gives_it_that_many_counters():
    scenario = _board(["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    life_before = alice.life
    scenario.will_pay_the_life(True, source="Madame Null, Power Broker")

    bears = _enter(scenario, "Grizzly Bears")

    assert scenario.stack_names() == ["Madame Null, Power Broker's triggered ability"]
    scenario.resolve_top()

    assert alice.life == life_before - 2
    assert bears.counter_count(Counter.PLUS_ONE) == 2


def test_declining_the_payment_leaves_life_and_counters_untouched():
    scenario = _board(["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    life_before = alice.life
    scenario.will_pay_the_life(False, source="Madame Null, Power Broker")

    bears = _enter(scenario, "Grizzly Bears")
    scenario.resolve_top()

    assert alice.life == life_before
    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_madame_null_herself_entering_does_not_trigger_her_own_ability():
    """ "another creature" (CR 400.7's "another" - excludes the source)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Madame Null, Power Broker"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp")
    scenario.cast_and_resolve("Madame Null, Power Broker", *sources)

    assert scenario.stack_names() == []


def test_a_zero_power_entering_creature_pays_zero_life_and_gets_no_counters():
    """CR 119.4b: paying 0 life is always legal, and CR 107.1c leaves nothing
    to put when the computed amount is 0."""
    scenario = _board(["Ornithopter"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    life_before = alice.life
    scenario.will_pay_the_life(True, source="Madame Null, Power Broker")

    ornithopter = _enter(scenario, "Ornithopter")
    scenario.resolve_top()

    assert alice.life == life_before
    assert ornithopter.counter_count(Counter.PLUS_ONE) == 0


def test_cannot_pay_more_life_than_the_controller_has():
    """CR 119.4: the affirmative is illegal below the life total being paid,
    so CR 608.2d forces the only legal answer (no scripted answer queued
    here) rather than letting the payment go through anyway."""
    scenario = _board(["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    alice.life = 1

    bears = _enter(scenario, "Grizzly Bears")
    scenario.resolve_top()

    assert alice.life == 1
    assert bears.counter_count(Counter.PLUS_ONE) == 0
    (asked,) = [q for q in scenario.questions_asked() if q.prompt == "pay 2 life"]
    assert asked.affirmative_is_legal is False
