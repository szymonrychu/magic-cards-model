"""Once the game is over, nothing else happens in it.

Battle report B6-06: after `game_over`, a pass still resolved Thought-Knot Seer,
its enters trigger and two Glaring Fleshraker triggers went on the stack, and a
trigger-ordering and a target decision were raised and accepted.

Every CR number below was read in this session with `mise run rules:find`:

- **CR 104.1** - "A game ends immediately when a player wins, when the game is
  a draw, or when the game is restarted."
- **CR 704.5a** - "If a player has 0 or less life, that player loses the game."
- **CR 104.3b** - "If a player's life total is 0 or less, that player loses the
  game the next time a player would receive priority. (This is a state-based
  action. See rule 704.)"

Glaring Fleshraker: "Whenever you cast a colorless spell, create a 0/1
colorless Eldrazi Spawn creature token ... Whenever another colorless creature
you control enters, this creature deals 1 damage to each opponent."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import Decision, DecisionKind, default_answer
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

GAME_OVER = r"the game is over.*CR 104\.1"


def lethal_board(*, bob_life: int) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Thought-Knot Seer", "Wastes", "Lightning Bolt"],
            battlefield=["Glaring Fleshraker", "Wastes", "Wastes", "Wastes", "Wastes", "Mountain"],
            library=["Wastes"] * 5,
        )
        .player("bob", life=bob_life, hand=["Mox Opal", "Island"], library=["Island"] * 5)
    )


def _play_until_the_game_ends(scenario) -> None:
    for _ in range(20):
        if scenario.game.is_over or scenario.game.stack_is_empty:
            return
        scenario.pass_until_resolved()
    raise AssertionError("the stack never emptied and the game never ended")


def _cast_the_seer(scenario) -> None:
    wastes = scenario.untapped_sources("Wastes", "Wastes", "Wastes", "Wastes", username="alice")
    scenario.cast_onto_stack("Thought-Knot Seer", *wastes, username="alice")


def test_a_lethal_check_leaves_the_enters_triggers_on_the_stack_unresolved():
    """Bob at 2: the Spawn made by the cast trigger pings him to 1; Thought-Knot
    Seer resolves and its enters trigger and Fleshraker's trigger go on the
    stack, Fleshraker's on top. It resolves, the state-based check takes Bob to
    a loss (CR 704.5a), and the Seer's trigger is never resolved."""
    scenario = lethal_board(bob_life=2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_order_triggers("Thought-Knot Seer", "Glaring Fleshraker", username="alice")
    _cast_the_seer(scenario)

    _play_until_the_game_ends(scenario)

    assert scenario.game.winner == "alice"
    assert scenario.find("Thought-Knot Seer", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert any("Thought-Knot Seer" in name for name in scenario.stack_names())
    stack_before = list(scenario.stack_names())
    asked_before = len(scenario.game.decisions.asked)

    with pytest.raises(ValueError, match=GAME_OVER):
        scenario.game.pass_priority("alice")
    with pytest.raises(ValueError, match=GAME_OVER):
        scenario.game.resolve_top()

    assert scenario.stack_names() == stack_before
    assert len(scenario.game.decisions.asked) == asked_before


def test_a_spell_left_on_the_stack_is_not_resolved_by_a_pass():
    """The B6-06 shape: Bob at 1 dies to the Spawn ping while Thought-Knot Seer
    is still on the stack. Passing must not resolve it, and no trigger-ordering
    question is raised for what it would have caused."""
    scenario = lethal_board(bob_life=1).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_the_seer(scenario)

    _play_until_the_game_ends(scenario)

    assert scenario.game.winner == "alice"
    seer = scenario.find("Thought-Knot Seer", Zone.STACK)
    with pytest.raises(ValueError, match=GAME_OVER):
        scenario.game.pass_priority("alice")
    assert seer.zone is Zone.STACK
    assert not any(
        question.kind is DecisionKind.ORDER_TRIGGERS for question in scenario.questions_asked()
    )


def test_every_action_is_refused_with_the_game_over_reason():
    scenario = lethal_board(bob_life=1).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_the_seer(scenario)
    _play_until_the_game_ends(scenario)
    assert scenario.game.is_over

    game = scenario.game
    wastes_in_hand = scenario.find("Wastes", Zone.HAND, "alice")
    with pytest.raises(ValueError, match=GAME_OVER):
        game.play_land(wastes_in_hand, "alice")
    assert game.why_cannot_play_land("alice") is not None
    with pytest.raises(ValueError, match=GAME_OVER):
        scenario.cast("Lightning Bolt", username="alice")
    fleshraker = scenario.find("Glaring Fleshraker", Zone.BATTLEFIELD)
    with pytest.raises(ValueError, match=GAME_OVER):
        game.declare_attackers([(fleshraker, "bob")])
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    refusal = game.why_cannot_activate(mountain, 0, "alice")
    assert refusal is not None and "CR 104.1" in refusal
    with pytest.raises(ValueError, match=GAME_OVER):
        game.advance("alice")
    with pytest.raises(ValueError, match=GAME_OVER):
        game.concede("alice")
    decide = game.why_cannot_decide_for("alice", "alice")
    assert decide is not None and "CR 104.1" in decide

    assert legal_actions(game, "alice") == []
    assert legal_actions(game, "bob") == []


def test_no_trigger_goes_on_the_stack_and_no_decision_is_raised():
    scenario = lethal_board(bob_life=1).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_the_seer(scenario)
    _play_until_the_game_ends(scenario)
    game = scenario.game
    assert game.is_over

    game.decisions.pause_when_unanswered = True
    stack_before = list(scenario.stack_names())
    asked_before = len(game.decisions.asked)

    assert game.put_triggers_on_stack() == []
    question = Decision(kind=DecisionKind.MAY, player="alice", prompt="anything", source_id=None)
    answer = game.ask(question)

    assert answer == default_answer(question), "nothing paused and nobody was asked"
    assert scenario.stack_names() == stack_before
    assert len(game.decisions.asked) == asked_before
