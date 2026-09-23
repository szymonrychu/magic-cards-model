"""Scenario: "if you control each creature on the battlefield with the
greatest power" - an intervening if (CR 603.4) over CR 208.1's power,
compared across every creature on the battlefield.

Might Makes Right's clause was unread, so `_fail_closed` recorded a notice
and the trigger never fired. Found by the behavioural sweep. "Each creature
... with the greatest power" is every creature tied for the highest power
among all creatures on the battlefield (computed, CR 613); the controller
must control all of them, so a tie with an opponent's creature fails it.

Rules verified with `mise run rules:find`: CR 603.4, CR 208.1.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _combat_with(alice: list[str], bob: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Might Makes Right", *alice], library=["Forest"] * 3)
        .player("bob", battlefield=bob, library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.advance()  # the beginning of combat step begins
    scenario.game.put_triggers_on_stack()
    return scenario


def test_the_largest_creature_lets_it_steal_an_opponents_creature():
    scenario = _combat_with(["Serra Angel"], ["Grizzly Bears"])

    assert scenario.stack_names() == ["Might Makes Right's triggered ability"]
    assert scenario.game.intervening_if_notices == []
    scenario.pass_until_resolved()
    assert scenario.creature("Grizzly Bears", "alice").controller == "alice"


def test_a_tie_with_an_opponents_creature_does_not_trigger():
    scenario = _combat_with(["Grizzly Bears"], ["Grizzly Bears"])

    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_an_opponents_larger_creature_does_not_trigger():
    scenario = _combat_with(["Grizzly Bears"], ["Serra Angel"])

    assert scenario.stack_names() == []
