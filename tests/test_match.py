import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Match, Player, Zone


def match(best_of: int = 3) -> Match:
    return Match(
        players=[Player(username="alice"), Player(username="bob")],
        best_of=best_of,
    )


def test_a_match_runs_games_one_at_a_time():
    series = match()
    game = series.start_game()

    assert series.current_game is game
    with pytest.raises(ValueError, match="still in progress"):
        series.start_game()


def test_a_new_game_starts_the_turn_at_untap():
    game = match().start_game()

    assert game.turn is not None
    assert game.turn.step is Step.UNTAP
    assert game.turn.active_player == "alice"
    assert not game.is_over


def test_a_game_owns_the_shared_zones_and_players_own_theirs():
    game = match().start_game()

    assert set(game.shared_zones) == {Zone.BATTLEFIELD, Zone.STACK, Zone.EXILE, Zone.COMMAND}
    assert set(game.player("alice").zones) == {
        Zone.LIBRARY,
        Zone.HAND,
        Zone.GRAVEYARD,
        Zone.SIDEBOARD,
    }


def test_taking_two_games_wins_a_best_of_three():
    series = match()
    assert series.wins_needed == 2

    series.start_game().end_with_winner("alice")
    assert series.winner is None
    assert series.score == {"alice": 1, "bob": 0}

    series.start_game().end_with_winner("alice")

    assert series.winner == "alice"
    assert series.is_over
    assert series.score == {"alice": 2, "bob": 0}


def test_a_match_goes_to_a_third_game_when_split():
    series = match()
    series.start_game().end_with_winner("alice")
    series.start_game().end_with_winner("bob")

    assert series.winner is None
    assert not series.is_over

    series.start_game().end_with_winner("bob")
    assert series.winner == "bob"


def test_no_game_four_in_a_best_of_three():
    series = match()
    for winner in ("alice", "bob", "alice"):
        series.start_game().end_with_winner(winner)

    with pytest.raises(ValueError, match="already won the match"):
        series.start_game()


def test_conceding_hands_the_game_to_the_last_player_standing():
    game = match().start_game()

    game.concede("bob")

    assert game.winner == "alice"
    assert game.is_over
    with pytest.raises(ValueError, match="game is over"):
        game.advance()


def test_unknown_players_are_rejected():
    game = match().start_game()

    with pytest.raises(KeyError):
        game.player("carol")
    with pytest.raises(KeyError):
        game.end_with_winner("carol")
