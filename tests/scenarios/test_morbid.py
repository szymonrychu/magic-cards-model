"""Scenario: Morbid (CR 207.2c ability word - "Morbid — [effect] if a
creature died this turn", no rules meaning of its own beyond tying together
cards that share the condition). Gruesome Discovery's own Morbid clause (an
ordinary triggered-ability intervening *if*) is already covered by
`test_reveal_hand_and_choose.py`.

This file is the off-pool proof the requirement names: **Festerhide Boar** -
"Morbid — This creature enters with two +1/+1 counters on it if a creature
died this turn." A CR 614.1c replacement effect, not a triggered ability at
all - the condition sits on the *entering* half of the permanent's own
characteristics (CR 613.2, sublayer 7d for the counters themselves once they
land), checked once, as the permanent enters, off `Game.creatures_died_this_
turn` (CR 700.4's "dies", the same running count Darklight Phoenix's own
triggered "two or more creatures died this turn" already reads in
`test_turn_history_predicates.py`, just the bare singular form here).

`machines/replacement.py`'s `_ENTERS_WITH` regex read only a *leading* "If
`<condition>`, [subject] enters with ..." form before this file was written;
Festerhide Boar's own condition is *trailing* ("... enters with ... if
`<condition>`."), the shape this proof exposed as unread and this task
fixes with a general parser (`_read_enters_condition`'s new "a creature died
this turn" case, reached from either position the sentence prints it in).
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def _computed(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def test_off_pool_festerhide_boar_enters_with_two_counters_after_a_death():
    scenario = (
        Scenario().player("alice", hand=["Festerhide Boar"], battlefield=["Grizzly Bears"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.destroy(bears)
    assert scenario.game.creatures_died_this_turn == 1

    boar = scenario.put_onto_battlefield("Festerhide Boar")

    assert boar.counter_count("+1/+1") == 2
    chars = _computed(scenario, boar)
    assert chars.power == 5  # printed 3 + two +1/+1 counters
    assert chars.toughness == 5


def test_off_pool_festerhide_boar_enters_with_no_counters_without_a_death():
    scenario = Scenario().player("alice", hand=["Festerhide Boar"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.creatures_died_this_turn == 0

    boar = scenario.put_onto_battlefield("Festerhide Boar")

    assert boar.counter_count("+1/+1") == 0
    chars = _computed(scenario, boar)
    assert chars.power == 3
    assert chars.toughness == 3
