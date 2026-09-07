"""Scenario: the turn-based actions of CR 703.

The mechanic is the things a step does *by itself* as it begins: no player
chooses them (CR 703.2), they do not use the stack (CR 703.1), and they happen
before state-based actions and before anybody receives priority (CR 703.3).

The engine only drives them when the game is built with
`automatic_turn_based_actions()` - see the note on
`Game.automatic_turn_based_actions` for why that is opt-in. Every test in this
file turns it on, because that is the mechanic under test.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import Answer, DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone

from .harness import PlayedScenario, Scenario


def driven(*, alice: dict | None = None, bob: dict | None = None) -> PlayedScenario:
    """Two players in a game that performs its own turn-based actions."""
    return (
        Scenario()
        .automatic_turn_based_actions()
        .player("alice", **(alice or {}))
        .player("bob", **(bob or {}))
        .build()
    )


def advance_to(scenario: PlayedScenario, username: str, step: Step) -> None:
    """Advance step by step until it is `username`'s `step`.

    Deliberately never uses `start_at`, which walks the turn machine directly
    and so skips exactly the actions this file is about.
    """
    for _ in range(200):
        if scenario.turn.active_player == username and scenario.step is step:
            return
        scenario.advance()
    raise AssertionError(f"never reached {username}'s {step}")


# -- the draw step (CR 504.1, 703.4d) --------------------------------------


def test_the_draw_step_draws_a_card_by_itself():
    """CR 703.4d: immediately after the draw step begins, the active player draws."""
    scenario = driven(
        alice={"library": ["Mountain"]},
        bob={"library": ["Island", "Forest"]},
    )
    advance_to(scenario, "bob", Step.DRAW)

    assert [state.name for state in scenario.player("bob").hand] == ["Island"]
    assert [state.name for state in scenario.player("bob").library] == ["Forest"]


def test_the_draw_step_puts_nothing_on_the_stack():
    """CR 703.1: a turn-based action does not use the stack."""
    scenario = driven(alice={"library": ["Mountain"]}, bob={"library": ["Island"]})
    advance_to(scenario, "bob", Step.DRAW)

    assert scenario.game.stack == []
    assert scenario.priority_holder == "bob", "priority still goes to the active player"


def test_the_player_who_plays_first_skips_their_first_draw_step():
    """CR 103.8a: in a *two-player* game, the starting player skips that one draw."""
    scenario = driven(alice={"library": ["Mountain", "Forest"]}, bob={"library": ["Island"]})
    advance_to(scenario, "alice", Step.DRAW)

    assert scenario.player("alice").hand == []
    assert len(scenario.player("alice").library) == 2


def test_the_starting_player_draws_on_their_second_turn():
    """The skip is one draw step, not a standing exemption (CR 103.8a)."""
    scenario = driven(alice={"library": ["Mountain", "Forest"]}, bob={"library": ["Island"]})
    advance_to(scenario, "alice", Step.DRAW)
    assert scenario.player("alice").hand == []

    advance_to(scenario, "alice", Step.PRECOMBAT_MAIN)
    advance_to(scenario, "alice", Step.DRAW)

    assert [state.name for state in scenario.player("alice").hand] == ["Mountain"]
    assert scenario.turn.turn_number == 2


def test_nobody_skips_the_first_draw_step_in_a_three_player_game():
    """CR 103.8c and CR 800.7: the skip is a two-player rule only.

    "In a multiplayer game other than a Two-Headed Giant game, the starting
    player doesn't skip the draw step of their first turn."
    """
    scenario = (
        Scenario()
        .automatic_turn_based_actions()
        .player("alice", library=["Mountain"])
        .player("bob", library=["Island"])
        .player("carol", library=["Forest"])
        .build()
    )
    advance_to(scenario, "alice", Step.DRAW)

    assert [state.name for state in scenario.player("alice").hand] == ["Mountain"]


def test_drawing_from_an_empty_library_in_the_draw_step_loses_the_game():
    """CR 104.3c and CR 704.5b, end to end through the turn machine.

    Bob's library is empty when his draw step begins. The draw is not an error:
    he draws nothing, and the state-based action CR 703.3 runs immediately
    afterwards takes him out, which leaves alice the winner (CR 104.2a).
    """
    scenario = driven(alice={"library": ["Mountain"]}, bob={"library": []})
    advance_to(scenario, "bob", Step.DRAW)

    assert scenario.player("bob").tried_to_draw_from_empty_library
    assert not scenario.game.is_in_game("bob")
    assert scenario.game.winner == "alice"


# -- the untap step (CR 502.3, 703.4c) -------------------------------------


def test_the_untap_step_untaps_by_itself():
    """CR 703.4c: the active player untaps their permanents as the step begins."""
    scenario = driven(
        alice={"library": ["Mountain"], "battlefield": ["Mountain"]},
        bob={"library": ["Island"], "battlefield": ["Island"]},
    )
    (island,) = scenario.untapped_sources("Island", username="bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    island.tap()
    mountain.tap()

    advance_to(scenario, "bob", Step.UPKEEP)

    assert island.untapped, "bob untaps in his own untap step"
    assert mountain.tapped, "alice's permanents are not bob's to untap"


# -- the cleanup step (CR 514.1, 514.2, 703.4n, 703.4p) --------------------


def test_the_cleanup_step_discards_down_to_maximum_hand_size():
    """CR 703.4n / 514.1: the active player discards to their maximum hand size."""
    scenario = driven(alice={"hand": ["Mountain"] * 9}, bob={})
    advance_to(scenario, "alice", Step.CLEANUP)

    alice = scenario.player("alice")
    assert len(alice.hand) == alice.maximum_hand_size == 7
    assert len(alice.graveyard) == 2
    assert all(state.zone is Zone.GRAVEYARD for state in alice.graveyard)


def test_a_hand_at_maximum_size_discards_nothing():
    """Exactly seven is not "more cards than their maximum hand size" (CR 402.2)."""
    scenario = driven(alice={"hand": ["Mountain"] * 7}, bob={})
    advance_to(scenario, "alice", Step.CLEANUP)

    assert len(scenario.player("alice").hand) == 7
    assert scenario.player("alice").graveyard == []


def test_a_hand_at_or_under_maximum_size_is_never_asked_to_discard():
    """CR 514.1's turn-based action only fires when the hand has more cards
    than the maximum - at or under it there is nothing to discard and, per CR
    701.9b, nothing to choose either. A live seat behind the api parks a whole
    decision timeout waiting on an answer to "discard 0 card(s)", which cannot
    be a real choice - so this must never even reach `Game.ask`
    (`decisions.asked`), not just resolve to an empty discard."""
    scenario = driven(alice={"hand": ["Mountain"] * 7}, bob={})
    advance_to(scenario, "alice", Step.CLEANUP)

    discard_questions = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.CHOOSE_CARDS
    ]
    assert discard_questions == []


def test_only_the_active_player_discards_in_cleanup():
    """CR 514.1 names the active player; a bloated hand elsewhere is untouched."""
    scenario = driven(alice={}, bob={"hand": ["Island"] * 10})
    advance_to(scenario, "alice", Step.CLEANUP)

    assert len(scenario.player("bob").hand) == 10


def test_the_cleanup_step_discard_is_the_players_own_choice():
    """CR 701.9b: "effects that cause a player to discard a card allow the
    affected player to choose which card to discard." The cleanup discard
    (CR 514.1, 703.4n) is that case, so a scripted choice - not the engine's
    default - decides which of 8 cards is discarded, and only that one moves.
    """
    scenario = driven(alice={"hand": ["Island", *(["Mountain"] * 7)]}, bob={})
    alice = scenario.player("alice")
    island, *mountains = alice.hand
    chosen_mountain = mountains[3]
    scenario.will_discard(chosen_mountain, username="alice")

    advance_to(scenario, "alice", Step.CLEANUP)

    assert chosen_mountain.zone is Zone.GRAVEYARD
    assert island.zone is Zone.HAND
    assert all(m.zone is Zone.HAND for m in mountains if m is not chosen_mountain)
    assert len(alice.hand) == 7


def test_choosing_a_different_card_than_the_default_proves_the_choice_is_real():
    """The unscripted default keeps the back of the hand (CR 701.9b's fallback,
    documented in `machines/decisions.default_answer`). Scripting the front
    card instead, and seeing *that* one in the graveyard, proves the answer
    was actually consulted rather than the default silently winning anyway.
    """
    scenario = driven(alice={"hand": ["Island", *(["Mountain"] * 7)]}, bob={})
    alice = scenario.player("alice")
    island, *mountains = alice.hand
    default_choice = mountains[-1]  # the back of the hand, what an unscripted answer takes
    scenario.will_discard(island, username="alice")

    advance_to(scenario, "alice", Step.CLEANUP)

    assert island.zone is Zone.GRAVEYARD
    assert default_choice.zone is Zone.HAND
    assert len(alice.hand) == 7


def test_choosing_two_cards_out_of_nine():
    """More than one card over the limit: CR 514.1 still asks once, for all of
    the excess at once, not once per card.
    """
    scenario = driven(alice={"hand": ["Island", "Plains", *(["Mountain"] * 7)]}, bob={})
    alice = scenario.player("alice")
    island, plains, *mountains = alice.hand
    scenario.will_discard(island, plains, username="alice")

    advance_to(scenario, "alice", Step.CLEANUP)

    assert island.zone is Zone.GRAVEYARD
    assert plains.zone is Zone.GRAVEYARD
    assert all(m.zone is Zone.HAND for m in mountains)
    assert len(alice.hand) == 7


def test_an_illegal_discard_answer_is_refused_and_does_not_corrupt_state():
    """CR 608.2d: "the player can't choose an option that's illegal or
    impossible." Naming a card that is not in the hand, or the wrong number of
    cards, is refused by `Game.ask` before anything is discarded - the hand is
    exactly as it was, not partially discarded.
    """
    # Too few: two cards are over the limit, only one is named.
    scenario = driven(alice={"hand": ["Island", *(["Mountain"] * 8)]}, bob={})
    alice = scenario.player("alice")
    scenario.will_discard(alice.hand[0], username="alice")
    with pytest.raises(ValueError):
        advance_to(scenario, "alice", Step.CLEANUP)
    assert len(alice.hand) == 9
    assert alice.graveyard == []

    # Not in the hand at all: bob's card, named for alice's discard.
    scenario = driven(alice={"hand": ["Island", *(["Mountain"] * 8)]}, bob={"hand": ["Plains"]})
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    scenario.will_discard(alice.hand[0], bob.hand[0], username="alice")
    with pytest.raises(ValueError):
        advance_to(scenario, "alice", Step.CLEANUP)
    assert len(alice.hand) == 9
    assert alice.graveyard == []
    assert bob.hand == [bob.hand[0]]


def test_nothing_scripted_uses_the_old_default():
    """No script, no tape: the back of the hand, exactly as before this
    machinery existed (see `test_the_cleanup_step_discards_down_to_maximum_hand_size`
    for the original assertion). This test pins the specific cards, not just
    the count.
    """
    scenario = driven(alice={"hand": ["Island", *(["Mountain"] * 7)]}, bob={})
    alice = scenario.player("alice")
    island, *mountains = alice.hand

    advance_to(scenario, "alice", Step.CLEANUP)

    assert mountains[-1].zone is Zone.GRAVEYARD
    assert island.zone is Zone.HAND
    assert len(alice.hand) == 7


def test_a_scripted_answer_still_beats_a_recorded_tape_entry():
    """`Game.ask` tries the script before the replay tape (see its docstring),
    so a tape entry sitting on the game does not get a say once a scenario has
    scripted the answer itself.
    """
    scenario = driven(alice={"hand": ["Island", *(["Mountain"] * 7)]}, bob={})
    alice = scenario.player("alice")
    island, *mountains = alice.hand
    # Declaring no attackers is scripted, not taped, so it does not shift the
    # tape's own position: the cleanup discard below is still the tape's
    # first entry.
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.DECLARE_ATTACKERS, value=(), player="alice")
    )
    scenario.game.decisions.recorded = [
        Answer(seq=0, kind=DecisionKind.CHOOSE_CARDS, player="alice", card_ids=(mountains[0].id,))
    ]
    scenario.will_discard(island, username="alice")

    advance_to(scenario, "alice", Step.CLEANUP)

    assert scenario.game.decisions.consumed == 0, "the tape entry was never read"
    assert island.zone is Zone.GRAVEYARD
    assert all(m.zone is Zone.HAND for m in mountains)


def test_a_recorded_tape_answers_when_nothing_is_scripted():
    """The tape branch itself: with no script, `Game.ask` falls through to
    `decisions.recorded` before it falls through to `default_answer`.
    """
    scenario = driven(alice={"hand": ["Island", *(["Mountain"] * 7)]}, bob={})
    alice = scenario.player("alice")
    island, *mountains = alice.hand
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.DECLARE_ATTACKERS, value=(), player="alice")
    )
    scenario.game.decisions.recorded = [
        Answer(seq=0, kind=DecisionKind.CHOOSE_CARDS, player="alice", card_ids=(island.id,))
    ]

    advance_to(scenario, "alice", Step.CLEANUP)

    assert scenario.game.decisions.consumed == 1
    assert island.zone is Zone.GRAVEYARD, "the tape named the front of the hand"
    assert all(m.zone is Zone.HAND for m in mountains)


def test_the_cleanup_step_removes_all_damage_from_permanents():
    """CR 703.4p / 514.2: all damage marked on permanents is removed.

    Damage below lethal survives every state-based check in the turn and is
    wiped here, which is what stops two turns of chip damage adding up.
    """
    scenario = driven(
        alice={"battlefield": ["Grizzly Bears"]},
        bob={"battlefield": ["Serra Angel"]},
    )
    bears = scenario.creature("Grizzly Bears", username="alice")
    angel = scenario.creature("Serra Angel", username="bob")
    scenario.game.deal_damage(bears, 1)
    scenario.game.deal_damage(angel, 3)

    advance_to(scenario, "alice", Step.CLEANUP)

    assert bears.damage == 0
    assert angel.damage == 0, "every permanent, not only the active player's"
    assert bears.zone is Zone.BATTLEFIELD


def test_damage_survives_until_the_cleanup_step():
    """The corner the wipe is easy to get wrong: it is cleanup, not end of turn."""
    scenario = driven(alice={"battlefield": ["Grizzly Bears"]}, bob={})
    bears = scenario.creature("Grizzly Bears", username="alice")
    scenario.game.deal_damage(bears, 1)

    advance_to(scenario, "alice", Step.END_STEP)

    assert bears.damage == 1, "still marked while the end step is happening"


# -- what is not automatic --------------------------------------------------


def test_reaching_declare_attackers_still_declares_nothing():
    """CR 703.4i and CR 703.4j are combat's turn-based actions, and are still caller-driven.

    Tracked in docs/engine-coverage.md: the combat steps do nothing on their
    own even with automatic turn-based actions on.
    """
    scenario = driven(alice={"battlefield": ["Grizzly Bears"]}, bob={})
    advance_to(scenario, "alice", Step.DECLARE_ATTACKERS)

    assert scenario.attackers() == []
