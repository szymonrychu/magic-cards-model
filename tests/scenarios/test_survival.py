"""Scenario: Survival (CR 207.2c ability word - "Survival — At the
beginning of your second main phase, if [condition], [effect]", no rules
meaning of its own beyond tying together cards that share the trigger).
Kona, Rescue Beastie's own Survival clause is already covered by
`test_put_permanent_card_from_hand.py`.

This file is the off-pool proof the requirement names: **Cautious Survivor**
- "Survival — At the beginning of your second main phase, if this creature
is tapped, you gain 2 life." CR 500.6/505.1a: the second main phase is
`Step.POSTCOMBAT_MAIN` regardless of whether an additional combat phase
followed it, and the intervening *if* (CR 603.4) is checked once, as the
step begins - `start_at` jumps straight to a step without running the
per-step machinery that fires a "beginning of" trigger (see its own
docstring), so this file steps into postcombat main with `advance()` rather
than jumping to it, the same way `test_ordering_objects_onto_the_stack.py`
steps into an untap step for the identical reason.
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def test_off_pool_cautious_survivor_gains_life_at_second_main_if_tapped():
    scenario = Scenario().player("alice", battlefield=["Cautious Survivor"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    survivor = scenario.creature("Cautious Survivor", "alice")
    survivor.tap()
    life_before = scenario.player("alice").life

    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()
    scenario.pass_until_resolved()  # the Survival trigger

    assert scenario.player("alice").life == life_before + 2


def test_off_pool_cautious_survivor_gains_nothing_while_untapped():
    scenario = Scenario().player("alice", battlefield=["Cautious Survivor"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    life_before = scenario.player("alice").life

    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()

    assert scenario.pending_triggers == []
    assert scenario.game.stack_is_empty
    assert scenario.player("alice").life == life_before
