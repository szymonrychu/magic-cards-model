"""Inspired Tethermage's own "Whenever you put one or more loyalty counters
on a planeswalker, put a +1/+1 counter on this creature." (CR 122.6, CR
606.4).

A different shape from the self-referential "one or more +1/+1 counters are
put on this creature" `ExtraTriggerEvent.COUNTERS_PUT` already read: active
voice ("you put", not "are put"), and the subject is "a planeswalker" - any
planeswalker the controller puts loyalty counters on, not the ability's own
source. `Game.add_counters` already emits `COUNTERS_PUT` generically (CR
602.2's `[+N]` loyalty-ability payment routes through it, `machines/cost.py`
line ~2852) - the gap was purely in the condition parser, which left this
whole shape with `event=None` and so unmatched by anything.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_inspired_tethermage_grows_when_another_planeswalker_gains_loyalty():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Inspired Tethermage", "Karn, the Great Creator"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tethermage = scenario.creature("Inspired Tethermage", "alice")
    karn = scenario.find("Karn, the Great Creator", Zone.BATTLEFIELD, username="alice")

    scenario.activate(karn, index=0, username="alice")  # Karn's own [+1]
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == [
        "Karn, the Great Creator's activated ability",
        "Inspired Tethermage's triggered ability",
    ]
    scenario.pass_until_resolved()  # Karn's [+1]
    scenario.pass_until_resolved()  # Tethermage's own trigger
    assert tethermage.counter_count("+1/+1") == 1


def test_inspired_tethermage_does_not_fire_for_a_creatures_counters():
    """The kind and the type both have to match: a +1/+1 counter arriving on
    a creature is not a loyalty counter arriving on a planeswalker."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Inspired Tethermage", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, "+1/+1", 1)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_inspired_tethermage_does_not_fire_for_an_opponents_planeswalker():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Inspired Tethermage"], library=["Forest"])
        .player("bob", battlefield=["Karn, the Great Creator"], library=["Forest"])
        .build()
    )
    scenario.start_at(Step.CLEANUP)
    scenario.advance()
    # CR 606.3 is a main-phase-of-your-own-turn ability; one `advance()`
    # only reaches bob's untap, which grants no priority at all.
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    karn = scenario.find("Karn, the Great Creator", Zone.BATTLEFIELD, username="bob")

    scenario.activate(karn, index=0, username="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Karn, the Great Creator's activated ability"]
