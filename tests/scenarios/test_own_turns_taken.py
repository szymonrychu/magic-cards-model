"""Scenario: how many of their own turns a player has begun.

`TurnMachine.turn_number` counts rounds of the table and does not move for an
extra turn; `turns_taken` counts every player's turns. Neither answers "is this
my Nth turn", and it cannot be derived exactly from the rest of the persisted
state once an extra turn has been taken (the queue of extra turns is popped as
they begin, so no record of who took one survives). `turns_taken_by` is that
count, one entry per player, read through `TurnMachine.own_turns_taken`.

Rules read in full this session with `mise run rules:find`:

- **CR 102.1** - "The active player is the player whose turn it is." A player's
  own turn is one where they are the active player; the count goes up as that
  turn begins, so it reads N for the whole of their Nth turn.
- **CR 500.7** - "Some effects can give a player extra turns. They do this by
  adding the turns directly after the specified turn. ... The most recently
  created turn will be taken first." An extra turn is a turn of that player's,
  so it counts.
- **CR 103.8** - "The starting player takes their first turn." Before it, in
  the pregame, nobody has begun a turn, so every count is 0.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Game
from tests.scenarios.test_opening_hand_actions import broodscale, dealt, devoted, series

from .harness import Scenario


def two_players() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Forest"], battlefield=["Forest"])
        .player("bob", library=["Island"], battlefield=["Island"])
    )


def next_turn(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()


def test_each_players_own_turns_count_on_the_play_and_on_the_draw():
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    turn = scenario.turn

    assert turn.active_player == "alice"
    assert turn.own_turns_taken("alice") == 1, "alice, on the play, is in her first turn"
    assert turn.own_turns_taken("bob") == 0

    next_turn(scenario)
    assert turn.active_player == "bob"
    assert turn.own_turns_taken("bob") == 1, "bob, on the draw, is in his first turn"
    assert turn.own_turns_taken("alice") == 1

    next_turn(scenario)
    assert turn.active_player == "alice"
    assert turn.own_turns_taken("alice") == 2
    assert turn.own_turns_taken("bob") == 1


def test_an_extra_turn_is_one_of_that_players_own_turns():
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_extra_turn("alice")

    next_turn(scenario)
    turn = scenario.turn
    assert turn.active_player == "alice" and turn.taking_extra_turn
    assert turn.turn_number == 1, "the round of the table has not moved"
    assert turn.own_turns_taken("alice") == 2
    assert turn.own_turns_taken("bob") == 0

    next_turn(scenario)
    assert turn.active_player == "bob"
    assert turn.own_turns_taken("bob") == 1
    assert turn.own_turns_taken("alice") == 2


def test_the_pregame_reads_zero_and_the_first_turn_reads_one():
    match = series(devoted(), devoted(), seed="own-turns")
    game = dealt(match, {"alice": "Leyline of Abundance", "bob": "Leyline of Abundance"})

    assert game.turn.in_pregame
    assert game.turn.own_turns_taken("alice") == 0
    assert game.turn.own_turns_taken("bob") == 0

    game.declare_mulligan("alice", False)
    game.declare_mulligan("bob", False)
    game.finish_opening_hand_actions("alice")
    game.finish_opening_hand_actions("bob")

    assert not game.turn.in_pregame
    assert game.turn.own_turns_taken("alice") == 1
    assert game.turn.own_turns_taken("bob") == 0


def test_a_dealt_game_in_the_mulligan_step_counts_no_turns():
    game = series(devoted(), broodscale()).start_game()

    assert game.turn.step is Step.MULLIGAN
    assert game.turn.turns_taken_by == {}


def test_the_count_is_persisted_in_the_game_json_and_survives_a_decode():
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_extra_turn("alice")
    next_turn(scenario)
    next_turn(scenario)

    dumped = scenario.game.model_dump(mode="json")
    assert dumped["turn"]["turns_taken_by"] == {"alice": 2, "bob": 1}

    decoded = Game.model_validate(dumped)
    assert decoded.turn.own_turns_taken("alice") == 2
    assert decoded.turn.own_turns_taken("bob") == 1
