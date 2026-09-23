"""Scenario: the intervening "if you control a(n) `<quality>`" -
`triggers._you_control_a_holds`, read for Birthing Ritual's "if you control a
creature" (`test_sacrificed_mana_value_bound.py`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 603.4** - "When the trigger event occurs, the ability checks whether
  the stated condition is true. The ability triggers only if it is ... it
  checks the stated condition again as it resolves. If the condition isn't
  true at that time, the ability is removed from the stack and does nothing."

Lagonna-Band Elder is the off-pool proof (Modern- and Pioneer-legal, not in
any `magic-cards-model-api` deck): an enters trigger rather than an end-step
one, and a noncreature quality - "When this creature enters, if you control
an enchantment, you gain 3 life."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

ELDER = "Lagonna-Band Elder"
ELDER_TRIGGER = f"{ELDER}'s triggered ability"


def _elder_enters(*battlefield: str) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", hand=[ELDER], battlefield=list(battlefield), library=["Plains"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(ELDER, "alice")
    scenario.game.put_triggers_on_stack()
    return scenario


def test_the_elder_gains_three_life_when_you_control_an_enchantment():
    scenario = _elder_enters("Glorious Anthem")
    assert scenario.stack_names() == [ELDER_TRIGGER]

    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 23


def test_the_elder_does_not_trigger_without_an_enchantment():
    """CR 603.4: false as the event occurs, so the ability never triggers."""
    scenario = _elder_enters("Plains")

    assert scenario.stack_names() == []
    assert scenario.player("alice").life == 20


def test_an_opponent_s_enchantment_does_not_count():
    scenario = (
        Scenario()
        .player("alice", hand=[ELDER], library=["Plains"] * 5)
        .player("bob", battlefield=["Glorious Anthem"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(ELDER, "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_the_enchantment_gone_before_resolution_means_nothing_happens():
    """CR 603.4's second check: the condition is asked again as the ability
    resolves, and it is false by then."""
    scenario = _elder_enters("Glorious Anthem")
    assert scenario.stack_names() == [ELDER_TRIGGER]
    anthem = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(anthem)

    scenario.pass_until_resolved()

    assert scenario.stack_names() == []
    assert scenario.player("alice").life == 20
