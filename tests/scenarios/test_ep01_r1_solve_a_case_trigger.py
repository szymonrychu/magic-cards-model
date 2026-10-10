"""CR 702.169 / CR 719.3: "Whenever you solve a Case" (Case File Auditor).

A Case "becomes solved" through its own "To solve" end-step trigger (CR
719.3a); "you solve a Case" is the controller of the Case that just became
solved (CR 719.3b: solved is a designation). Case File Auditor's
"When this creature enters and whenever you solve a Case, look at the top six
cards of your library. You may reveal an enchantment card from among them and
put it into your hand." reads as two abilities sharing one effect; this file
pins the second.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

AUDITOR = "Case File Auditor"
FEAST = "Case of the Uneaten Feast"


def _board(bob_battlefield=()) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[AUDITOR, FEAST, "Forest", "Forest"],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Forest"] * 10)
    )


def _to_end_step_trigger(scenario) -> None:
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.game.sync_priority_with_step()
    scenario.advance()
    scenario.game.put_triggers_on_stack()


def _auditor_triggers(scenario) -> list[str]:
    return [name for name in scenario.stack_names() if name.startswith(AUDITOR)]


def test_solving_your_case_triggers_the_auditor():
    scenario = _board().build()
    case = scenario.find(FEAST, Zone.BATTLEFIELD)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 5)
    _to_end_step_trigger(scenario)
    assert _auditor_triggers(scenario) == []  # not solved yet

    scenario.pass_until_resolved()  # the "To solve" trigger resolves

    assert case.solved is True
    scenario.game.put_triggers_on_stack()
    assert _auditor_triggers(scenario) == [f"{AUDITOR}'s triggered ability"]


def test_an_unsolved_case_does_not_trigger_the_auditor():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 4)
    _to_end_step_trigger(scenario)
    scenario.pass_until_resolved()
    scenario.game.put_triggers_on_stack()

    assert _auditor_triggers(scenario) == []
