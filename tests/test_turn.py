import pytest

from magic_cards_model.machines import TURN_ORDER, Phase, Step, TurnMachine


def machine(*players: str) -> TurnMachine:
    return TurnMachine(players=list(players or ("alice", "bob")))


def test_a_turn_runs_through_every_step_in_order():
    turn = machine()
    seen = [turn.step]
    for _ in range(len(TURN_ORDER) - 1):
        seen.append(turn.advance())

    assert seen == list(TURN_ORDER)
    assert turn.turn_number == 1
    assert turn.active_player == "alice"


def test_cleanup_passes_the_turn_to_the_next_player():
    turn = machine()
    turn.advance_to(Step.CLEANUP)

    assert turn.advance() is Step.UNTAP
    assert turn.active_player == "bob"
    assert turn.turn_number == 1  # still the first round


def test_turn_number_increments_once_play_comes_back_around():
    turn = machine()
    turn.advance_to(Step.CLEANUP)
    turn.advance()  # bob's turn
    turn.advance_to(Step.CLEANUP)
    turn.advance()  # back to alice

    assert turn.active_player == "alice"
    assert turn.turn_number == 2


def test_phases_group_their_steps():
    turn = machine()

    assert turn.phase is Phase.BEGINNING
    turn.advance_to(Step.DECLARE_BLOCKERS)
    assert turn.phase is Phase.COMBAT
    turn.advance_to(Step.END_STEP)
    assert turn.phase is Phase.ENDING


def test_sorcery_timing():
    turn = machine()
    turn.advance_to(Step.PRECOMBAT_MAIN)

    assert turn.can_cast_sorcery(stack_is_empty=True, player="alice")
    # Not with something on the stack, not on someone else's turn.
    assert not turn.can_cast_sorcery(stack_is_empty=False, player="alice")
    assert not turn.can_cast_sorcery(stack_is_empty=True, player="bob")

    turn.advance_to(Step.DECLARE_ATTACKERS)
    assert not turn.can_cast_sorcery(stack_is_empty=True, player="alice")


def test_untap_and_cleanup_grant_nobody_priority():
    turn = machine()

    assert not turn.grants_priority  # untap
    turn.advance()
    assert turn.grants_priority  # upkeep
    turn.advance_to(Step.CLEANUP)
    assert not turn.grants_priority


def test_cannot_advance_backwards():
    turn = machine()
    turn.advance_to(Step.END_STEP)

    with pytest.raises(ValueError, match="already passed"):
        turn.advance_to(Step.UPKEEP)
