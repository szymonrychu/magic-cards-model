"""Case cards: "To solve" and "Solved" (CR 719.3, CR 702.169).

Verified this session with `mise run rules:find 719` and `702.169`:

- CR 719.3a: "'To solve — [Condition]' means 'At the beginning of your end
  step, if [condition] and this Case is not solved, this Case becomes
  solved.'"
- CR 719.3b: "Solved is a designation a permanent can have. ... Once a
  permanent becomes solved, it stays solved until it leaves the battlefield.
  The solved designation is neither an ability nor part of the permanent's
  copiable values."
- CR 702.169c: a triggered "Solved — [Ability text]" "triggers only if this
  Case is solved"; CR 702.169d: an activated one is "[Ability text]. Activate
  only if this Case is solved."

Case of the Uneaten Feast (a life-gained condition, an activated Solved
ability) exposed it; Case of the Crimson Pulse (Pioneer/Standard legal, in no
deck) is the second printing - a hand-size condition and a *triggered*
Solved ability that must stay silent until the Case is solved.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

FEAST = "Case of the Uneaten Feast"
PULSE = "Case of the Crimson Pulse"


def _to_end_step(scenario) -> None:
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.game.sync_priority_with_step()
    scenario.advance()  # the end step begins: "To solve" checks
    scenario.pass_until_resolved()


def _next_turn_main(scenario) -> None:
    """Run out this turn, then the opponent's, into our next precombat main."""
    for _ in range(2):
        scenario.turn.advance_to(Step.CLEANUP)
        scenario.game.sync_priority_with_step()
        scenario.advance()
        scenario.advance()
    scenario.turn.advance_to(Step.PRECOMBAT_MAIN)
    scenario.game.sync_priority_with_step()


def _feast_board(**alice) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[FEAST, "Forest", "Forest"],
            graveyard=["Grizzly Bears", "Lightning Bolt"],
            library=["Forest"] * 10,
            **alice,
        )
        .player("bob", library=["Forest"] * 10)
    )


def test_gaining_five_life_solves_the_case_at_the_end_step():
    scenario = _feast_board().build()
    case = scenario.find(FEAST, Zone.BATTLEFIELD)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 5)

    _to_end_step(scenario)

    assert case.solved is True


def test_four_life_is_not_enough():
    scenario = _feast_board().build()
    case = scenario.find(FEAST, Zone.BATTLEFIELD)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 4)

    _to_end_step(scenario)

    assert case.solved is False


def test_the_solve_trigger_is_only_at_your_own_end_step():
    """"your end step" - bob's end step does not solve alice's Case even
    with the condition true then (life gained on bob's turn)."""
    scenario = _feast_board().build()
    case = scenario.find(FEAST, Zone.BATTLEFIELD)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.game.sync_priority_with_step()
    scenario.advance()
    scenario.advance()  # bob's upkeep
    assert scenario.turn.active_player == "bob"
    scenario.game.gain_life("alice", 6)

    _to_end_step(scenario)

    assert case.solved is False


def test_the_solved_ability_cannot_be_activated_while_unsolved():
    """CR 702.169d."""
    scenario = _feast_board().build()
    case = scenario.find(FEAST, Zone.BATTLEFIELD)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError, match="solved"):
        scenario.activate(case, sacrificing=[case])


def _solve_feast(scenario):
    case = scenario.find(FEAST, Zone.BATTLEFIELD)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 5)
    _to_end_step(scenario)
    assert case.solved
    _next_turn_main(scenario)
    assert case.solved  # CR 719.3b: it stays solved
    return case


def test_the_solved_ability_grants_creature_cards_a_graveyard_cast():
    scenario = _feast_board().build()
    case = _solve_feast(scenario)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, username="alice")

    scenario.activate(case, sacrificing=[case])
    scenario.pass_until_resolved()
    assert case.zone is Zone.GRAVEYARD

    casting = scenario.cast("Grizzly Bears", from_zone=Zone.GRAVEYARD)
    casting.use_permission()
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD


def test_a_noncreature_card_gains_nothing():
    scenario = _feast_board().build()
    case = _solve_feast(scenario)

    scenario.activate(case, sacrificing=[case])
    scenario.pass_until_resolved()

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    with pytest.raises(ValueError):
        casting.use_permission()


def test_the_grant_ends_at_end_of_turn():
    scenario = _feast_board().build()
    case = _solve_feast(scenario)
    scenario.activate(case, sacrificing=[case])
    scenario.pass_until_resolved()

    _next_turn_main(scenario)

    casting = scenario.cast("Grizzly Bears", from_zone=Zone.GRAVEYARD)
    with pytest.raises(ValueError):
        casting.use_permission()


def test_the_case_loses_solved_when_it_leaves():
    """CR 719.3b: "it stays solved until it leaves the battlefield"."""
    scenario = _feast_board().build()
    case = _solve_feast(scenario)

    scenario.game.return_to_hand(case)

    assert case.solved is False


def _pulse_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[PULSE], hand=["Forest"], library=["Forest"] * 10)
        .player("bob", library=["Forest"] * 10)
    )


def test_second_printing_an_empty_hand_solves_it():
    scenario = _pulse_board().build()
    case = scenario.find(PULSE, Zone.BATTLEFIELD)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Forest")

    _to_end_step(scenario)

    assert case.solved is True


def test_second_printing_a_card_in_hand_leaves_it_unsolved():
    scenario = _pulse_board().build()
    case = scenario.find(PULSE, Zone.BATTLEFIELD)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _to_end_step(scenario)

    assert case.solved is False


def test_a_triggered_solved_ability_does_not_trigger_while_unsolved():
    """CR 702.169c: "triggers only if this Case is solved"."""
    scenario = _pulse_board().build()
    scenario.start_at(Step.UPKEEP)
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.game.sync_priority_with_step()
    scenario.advance()
    scenario.advance()  # bob's upkeep
    for _ in range(1):
        scenario.turn.advance_to(Step.CLEANUP)
        scenario.game.sync_priority_with_step()
        scenario.advance()
        scenario.advance()  # alice's upkeep begins

    assert scenario.turn.active_player == "alice"
    assert all(PULSE not in str(trigger) for trigger in scenario.pending_triggers)
    assert PULSE not in " ".join(scenario.stack_names())


def test_a_triggered_solved_ability_triggers_once_solved():
    scenario = _pulse_board().build()
    case = scenario.find(PULSE, Zone.BATTLEFIELD)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Forest")
    _to_end_step(scenario)
    assert case.solved
    hand_before = len(scenario.player("alice").hand)
    assert hand_before == 0

    for _ in range(2):
        scenario.turn.advance_to(Step.CLEANUP)
        scenario.game.sync_priority_with_step()
        scenario.advance()
        scenario.advance()  # the next upkeep; alice's on the second pass
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").hand) == 2


def test_every_clause_is_credited():
    from magic_cards_model.support import card_support
    from tests.cards import card

    for name in (FEAST, PULSE):
        support = str(card_support(card(name)))
        assert "static_unaudited" not in support, name
        assert "'silent'" not in support, name
