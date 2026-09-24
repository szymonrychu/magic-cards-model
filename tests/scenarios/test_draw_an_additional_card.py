""" "Draw an additional card" - a draw-step trigger's extra draw.

CR 504.1: "First, the active player draws a card. This turn-based action
doesn't use the stack." CR 504.2: "Second, the active player gets priority."
So an "At the beginning of your draw step, draw an additional card." trigger
resolves *after* the turn's normal draw, and "additional" is only that: one
more card on top of CR 504.1's, drawn the ordinary way (CR 121.2).

The Immortal Sun (legal in Modern and Pioneer, in no deck list here) prints it:
"At the beginning of your draw step, draw an additional card."

Every CR number here was read whole with `mise run rules:find`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import trigger_effect_for
from tests.scenarios.harness import Scenario


def _sun_board(owner: str = "bob"):
    """The Immortal Sun on `owner`'s side of a two-player game where alice
    plays first (so her first draw step is skipped, CR 103.8a)."""
    boards = {"alice": [], "bob": []}
    boards[owner] = ["The Immortal Sun"]
    return (
        Scenario()
        .automatic_turn_based_actions()
        .player("alice", library=["Island"] * 6, battlefield=boards["alice"])
        .player("bob", library=["Island"] * 6, battlefield=boards["bob"])
        .build()
    )


def _advance_to(scenario, username: str, step: Step) -> None:
    """Step by step, resolving whatever triggers on the way - never
    `start_at`, which walks the turn machine past the turn-based draw."""
    for _ in range(200):
        while scenario.game.stack or scenario.pending_triggers:
            scenario.pass_until_resolved()
        if scenario.turn.active_player == username and scenario.step is step:
            return
        scenario.advance()
    raise AssertionError(f"never reached {username}'s {step}")


def test_the_clause_reads_as_a_one_card_draw():
    assert trigger_effect_for("The Immortal Sun", None, "draw an additional card.") is not None


def test_the_active_player_draws_the_normal_card_and_one_more():
    """CR 504.1's draw, then the trigger's: two cards in bob's draw step."""
    scenario = _sun_board("bob")
    _advance_to(scenario, "bob", Step.PRECOMBAT_MAIN)

    assert len(scenario.player("bob").hand) == 2
    assert len(scenario.player("bob").library) == 4


def test_only_its_controllers_draw_step():
    """ "Your draw step": bob's Sun does nothing in alice's draw step."""
    scenario = _sun_board("bob")
    _advance_to(scenario, "bob", Step.PRECOMBAT_MAIN)
    _advance_to(scenario, "alice", Step.PRECOMBAT_MAIN)

    # alice's second turn: her one normal draw, nothing from bob's Sun.
    assert len(scenario.player("alice").hand) == 1


def test_a_skipped_draw_step_skips_the_trigger_too():
    """CR 103.8a skips alice's whole first draw step - "at the beginning of
    your draw step" never happens, so the Sun draws nothing either. CR 500.11:
    to skip a step is "to proceed past it as though it didn't exist"."""
    scenario = _sun_board("alice")
    _advance_to(scenario, "alice", Step.PRECOMBAT_MAIN)

    assert scenario.player("alice").hand == []


def test_several_additional_cards_read_the_same_way():
    """The count is read, not assumed to be one."""
    assert trigger_effect_for("x", None, "draw two additional cards.") is not None
