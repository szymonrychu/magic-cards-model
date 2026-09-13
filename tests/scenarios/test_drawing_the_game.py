"""Scenario: drawing the game (CR 104.4a).

CR 104.4a: "If all the players remaining in a game lose simultaneously, the
game is a draw." Before this was modelled, a check that removed every player
still in the game left `Game.winner` None and `Game.is_over` False, so a drawn
game was indistinguishable from one still in progress.

The corner cases are the point:

- Simultaneous means the **same state-based-action check** (CR 704.3), not the
  same turn. Two lethally aimed spells resolving one after the other end the
  game at the first resolution, and the second player never loses - CR 104.1
  ends the game immediately once somebody has won, and nothing happens after
  that.
- "All the players remaining" is who is still in the game (CR 104.5) when the
  check runs. A player who left earlier is counted in neither direction: their
  departure does not stop the draw, and their loss is not part of it.
- A check that would remove some but not all of the remaining players is a win
  for a survivor (CR 104.2a), not a draw - and a prevention shield that saves
  one player at the same check is enough to make a survivor.
- The game ended by a concession cannot be drawn by a later check: CR 104.2a's
  win "happens immediately", so the game is over before any check runs.

Every CR number here was looked up with `knowledge_search(q="...", type="rules")`
in the session that wrote this file: CR 104.1 (the game ends immediately when a
player wins, when the game is a draw, or when it is restarted), CR 104.2a (the
last player standing wins, immediately), CR 104.3a (a concession leaves the
game immediately), CR 104.4a (the draw rule itself), CR 104.5 (a player who
loses, or the game is a draw for, leaves the game), CR 704.3 (the checks repeat
before a player would get priority), CR 704.5a (0 or less life loses), CR 119.2
and CR 120.3a (damage to a player is life loss), CR 615.7 (the Bandage shield),
CR 100.6 and CR 100.6a (what a match is; the CR leaves how a drawn game scores
one to the Tournament Rules).

Reaching a state where every player would lose at one check is staging: the
damage is dealt through `Game.deal_damage` by hand, the way
`test_prevention_effects.py` builds shields by hand, so a single check catches
everybody. Every card on the board is a real printing.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Match, Player

from .harness import Scenario

# -- CR 104.4a: all remaining players lose at the same check -----------------


def test_both_players_losing_at_the_same_check_is_a_draw():
    """Damage to a player is life loss (CR 119.2, CR 120.3a) and losing for
    being at 0 or less life waits for the check (CR 704.5a), so both players
    can be at 0 before any check runs. One check then removes them both, which
    is exactly CR 104.4a's simultaneity.
    """
    scenario = Scenario().player("alice", life=3).player("bob", life=3).build()
    game = scenario.game
    game.deal_damage(scenario.player("alice"), 3)
    game.deal_damage(scenario.player("bob"), 3)
    assert [p.username for p in game.players_in_game] == ["alice", "bob"]

    game.check_state_based_actions()

    assert game.drawn
    assert game.winner is None
    assert game.is_over
    assert game.players_in_game == [], "CR 104.5: a player the game is a draw for leaves it"


def test_a_drawn_game_is_over_even_though_nobody_won():
    """The distinction the old model could not make: `is_over` is True (CR 104.1
    ends a drawn game) while `winner` stays None (CR 104.2a needs a player still
    in the game, and there is none), so the turn machine is done with it.
    """
    scenario = Scenario().player("alice", life=0).player("bob", life=0).build()
    game = scenario.game

    game.check_state_based_actions()

    assert game.winner is None
    assert game.drawn
    assert game.is_over
    with pytest.raises(ValueError, match="the game is over"):
        game.advance()


def test_overkill_leaves_both_below_zero_and_still_draws():
    """CR 704.5a is "If a player has 0 or less life" - less than zero included,
    and the amount does not matter once both are through.
    """
    scenario = Scenario().player("alice", life=3).player("bob", life=3).build()
    game = scenario.game
    game.deal_damage(scenario.player("alice"), 10)
    game.deal_damage(scenario.player("bob"), 10)

    game.check_state_based_actions()

    assert game.drawn
    assert scenario.player("alice").life == -7
    assert game.winner is None


def test_the_engine_can_be_told_the_game_is_a_draw():
    """`end_in_draw` is the staging entry for the draws no state-based-action
    check produces: the mandatory-action loop of CR 104.4b has no loop
    machinery behind it, and CR 104.4c's "an effect may state that the game is
    a draw" has no registry effect to reach. CR 104.5 still sends everyone
    still in the game out of it.
    """
    scenario = Scenario().player("alice").player("bob").build()
    game = scenario.game

    game.end_in_draw()

    assert game.drawn
    assert game.is_over
    assert game.winner is None
    assert game.players_in_game == []
    with pytest.raises(ValueError, match="already over"):
        game.end_in_draw()


# -- the negative cases ------------------------------------------------------


def test_a_survivor_wins_instead_of_the_game_being_a_draw():
    """The control for CR 104.4a: only one player is at 0 at the check, so it is
    an ordinary loss and CR 104.2a hands the win to the other.
    """
    scenario = Scenario().player("alice", life=3).player("bob", life=3).build()
    game = scenario.game
    game.deal_damage(scenario.player("bob"), 3)

    game.check_state_based_actions()

    assert game.winner == "alice"
    assert not game.drawn


def test_a_shield_that_saves_one_player_stops_it_being_a_draw():
    """Both players would be at 0 at the same check, but Bandage's shield
    (CR 615.7) prevents the damage headed at alice first - so the check removes
    only bob, and CR 104.4a does not apply: alice wins (CR 104.2a).
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", life=1, hand=["Bandage"], battlefield=["Plains"], library=["Island"])
        .player("bob", life=1)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.cast_and_resolve("Bandage", plains, username="alice", targets=["alice"])

    game = scenario.game
    game.deal_damage(scenario.player("alice"), 1)
    game.deal_damage(scenario.player("bob"), 1)
    assert scenario.player("alice").life == 1, "CR 615.7: the shield prevented the damage"
    assert scenario.player("bob").life == 0

    game.check_state_based_actions()

    assert game.winner == "alice"
    assert not game.drawn


# -- multiplayer: the boundary of "all the players remaining" ----------------


def test_two_of_three_losing_simultaneously_is_a_win_for_the_third():
    """CR 104.4a needs *all* the players remaining to lose. Bob and carol lose
    at the same check; alice is still in the game, so it is not a draw and she
    wins (CR 104.2a).
    """
    scenario = (
        Scenario().player("alice", life=10).player("bob", life=3).player("carol", life=3).build()
    )
    game = scenario.game
    game.deal_damage(scenario.player("bob"), 3)
    game.deal_damage(scenario.player("carol"), 3)

    game.check_state_based_actions()

    assert game.winner == "alice"
    assert not game.drawn
    assert [p.username for p in game.players_in_game] == ["alice"]


def test_all_three_losing_at_the_same_check_is_a_draw():
    """The three-player version of the draw: when every player still in the
    game loses at one check, "all the players remaining" is all of them.
    """
    scenario = (
        Scenario().player("alice", life=3).player("bob", life=3).player("carol", life=3).build()
    )
    game = scenario.game
    for username in ("alice", "bob", "carol"):
        game.deal_damage(scenario.player(username), 3)

    game.check_state_based_actions()

    assert game.drawn
    assert game.winner is None
    assert game.players_in_game == []


def test_players_who_left_earlier_do_not_stop_a_draw():
    """CR 104.4a counts the players *remaining* in the game (CR 104.5). Carol
    conceded before the check, so "all the players remaining" is alice and bob,
    and their simultaneous loss is still a draw - the departed player neither
    blocks it nor wins it.
    """
    scenario = (
        Scenario().player("alice", life=3).player("bob", life=3).player("carol", life=3).build()
    )
    game = scenario.game
    game.concede("carol")
    assert game.winner is None, "two players remain, so nobody has won yet"

    game.deal_damage(scenario.player("alice"), 3)
    game.deal_damage(scenario.player("bob"), 3)
    game.check_state_based_actions()

    assert game.drawn
    assert game.winner is None


def test_a_concede_wins_the_game_before_a_draw_can_happen():
    """CR 104.3a: a concession leaves the game immediately, and CR 104.2a's win
    "happens immediately" - so the game is over (CR 104.1) while bob sits at 0
    life, and no check ever turns it into a draw. A check that finds the game
    already over does nothing.
    """
    scenario = Scenario().player("alice", life=10).player("bob", life=0).build()
    game = scenario.game

    game.concede("alice")

    assert game.winner == "bob"
    assert not game.drawn
    assert game.is_in_game("bob")

    assert game.check_state_based_actions() == []
    assert game.is_in_game("bob"), "the game is over, so the loss at 0 life never happens"


# -- simultaneous means the same check, not the same turn --------------------


def test_lethal_spells_resolving_in_sequence_end_the_game_at_the_first():
    """Two Bolts, one at each player, on the stack together. The last cast
    resolves first (CR 608: last in, first out) and takes bob out, the game
    ends (CR 104.1), and the second Bolt resolving into a finished game cannot
    turn alice's win into a draw - it is never resolved at all, because
    nothing resolves in a game that is over. (The Bolt
    aimed at the loser is gone with her: CR 800.4a takes her objects out of the
    game when she leaves, so the spell left on the stack is the winner's.)
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            life=3,
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
            library=["Island"],
        )
        .player("bob", life=3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", first, username="alice", targets=["alice"])
    scenario.cast_onto_stack("Lightning Bolt", second, username="alice", targets=["bob"])

    scenario.resolve_top()  # the Bolt aimed at bob; last cast resolves first

    game = scenario.game
    assert game.winner == "alice"
    assert not game.drawn
    assert not game.is_in_game("bob")

    with pytest.raises(ValueError, match=r"the game is over.*CR 104\.1"):
        scenario.resolve_top()  # CR 104.1: nothing resolves into a finished game
    assert game.winner == "alice"
    assert not game.drawn
    assert game.is_in_game("alice"), "the game ended before her loss could be checked"


# -- the match container -----------------------------------------------------


def _match() -> Match:
    """A best of three with no decks registered: the games are staged, not dealt."""
    return Match(players=[Player(username="alice"), Player(username="bob")])


def _draw_the_game(game: Game) -> None:
    """Stage both players to 0 life and run the check that draws (CR 104.4a)."""
    game.deal_damage(game.player("alice"), 20)
    game.deal_damage(game.player("bob"), 20)
    game.check_state_based_actions()
    assert game.drawn and game.winner is None


def test_a_match_records_a_drawn_game_and_starts_the_next():
    """A drawn game is a finished game - CR 104.1 ends it - so it lands in
    `finished_games`, counts in `draws`, and scores for nobody. CR 100.6a is
    what a match is; the CR leaves how a drawn game scores one to the
    Tournament Rules (CR 100.6), so `winner` stays None and the next game
    starts.
    """
    series = _match()
    game = series.start_game(deal_opening_hands=False)

    _draw_the_game(game)

    assert game.is_over
    assert len(series.finished_games) == 1 and series.finished_games[0] is game
    assert series.draws == 1
    assert series.score == {"alice": 0, "bob": 0}
    assert series.winner is None
    assert series.current_game is None
    assert series.chooser_for_next_game() is None, "no single loser to hand the choice to"

    next_game = series.start_game(deal_opening_hands=False)
    assert next_game is not game
    assert not next_game.is_over
    assert series.draws == 1


def test_a_draw_does_not_count_toward_the_games_needed_to_win():
    """`wins_needed` counts wins, and a drawn game is a win for nobody: a best
    of three at 0-0-1 is not over, and it still takes two wins to finish it.
    """
    series = _match()
    _draw_the_game(series.start_game(deal_opening_hands=False))
    assert not series.is_over

    series.start_game(deal_opening_hands=False).end_with_winner("alice")
    assert series.winner is None, "one win and a draw is not the two needed"

    series.start_game(deal_opening_hands=False).end_with_winner("alice")
    assert series.winner == "alice"
    assert series.is_over
    assert series.score == {"alice": 2, "bob": 0}
    assert series.draws == 1


def test_a_best_of_three_where_every_game_draws_ends_with_no_winner():
    """A draw uses up a game without moving either score, so a best of three
    that draws out is over - `best_of` games happened - with `winner` None,
    rather than running a fourth game.
    """
    series = _match()
    for _ in range(3):
        _draw_the_game(series.start_game(deal_opening_hands=False))

    assert series.draws == 3
    assert series.is_over
    assert series.winner is None
    with pytest.raises(ValueError, match="cannot run a game 4"):
        series.start_game(deal_opening_hands=False)
