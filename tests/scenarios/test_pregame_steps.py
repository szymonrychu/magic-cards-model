"""The pregame as two steps the game rests in, before CR 103.8's first turn.

The mechanic this file covers is the *shape* of starting a game: where the game
sits between being dealt and taking its first turn, what it does and does not
claim about the turn while it sits there, and how a seat acts from outside
without the engine asking anybody anything.

`scenarios/test_mulligans.py` covers what the London mulligan does and
`scenarios/test_opening_hand_actions.py` covers what CR 103.6's actions do. This
file covers neither; it covers the two steps they now happen in.

Every CR number below was verified with `knowledge_search(q="...", type="rules")`
in the session that wrote this file. The search excerpts truncate at roughly two
hundred characters, so where a rule's tail is cut off that is marked rather than
filled in from memory:

- **CR 500.1** - "A turn consists of five phases, in this order: beginning,
  precombat main, combat, postcombat main, and ending. Each of these phases
  takes place every turn, even if nothing happens during the phase. Th[e ...]"
  (truncated). The part that matters is complete: a phase, and so every step in
  one, is part of *a turn*. That is why `Step.MULLIGAN` and
  `Step.PREGAME_ACTIONS` are in no `Phase` and why `phase` is None in them.
- **CR 103.5** - "Each player draws a number of cards equal to their starting
  hand size, which is normally seven. (Some effects can modify a player's
  starting hand size.) A player who is dissatisfied with their initi[al hand
  ...]" (truncated). The ordering sentence this file leans on - every player
  declares, then all who declared take their mulligans at the same time - is
  quoted in `models/match.py` and tested in `scenarios/test_mulligans.py`; the
  simultaneity is re-checked here because the declarations now arrive one call
  at a time and could have stopped being simultaneous.
- **CR 103.6** - "Some cards allow a player to take actions with them from
  their opening hand. Once the mulligan process (see rule 103.5) is complete,
  the starting player may take any such actions in any order. Then ea[ch other
  player ...]" (truncated). The starting player going first is stated outright,
  which is the seat order tested here.
- **CR 103.8** - "The starting player takes their first turn." In full. Which is
  what makes "turn 1 has not begun yet" a rules statement and not a convenience.
- **CR 117.1** - "Unless a spell or ability is instructing a player to take an
  action, which player can take actions at any given time is determined by a
  system of priority. The player with priority may cast spells, ac[tivate ...]"
  (truncated). Checked and *not* applicable as a grant: nothing found in
  CR 103.5 or CR 103.6 gives anybody priority before the first turn, so no
  CR 117 round is modelled in either pregame step.

The registered lists are reused rather than reinvented: devoted combo (pilot
**musasabi**, **2026-08-29**, deck `videre-58655572`), which plays four Leylines
of Abundance, and broodscale bloodchief (pilot **unagieel**, **2026-08-30**,
deck `videre-58656378`). Libraries are rigged so a specific card is dealt -
CR 103.3 staging, not a mock: every card is the real Scryfall printing the
registered list names.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Game, Match, Zone
from tests.scenarios.test_opening_hand_actions import (
    broodscale,
    dealt,
    devoted,
    series,
)


def two_leylines(seed: str = "pregame") -> tuple[Game, Match]:
    """A two-seat game with a Leyline of Abundance dealt to each opening hand."""
    match = series(devoted(), devoted(), seed=seed)
    game = dealt(match, {"alice": "Leyline of Abundance", "bob": "Leyline of Abundance"})
    return game, match


# -- where a dealt game rests (CR 103.5, CR 103.8) --------------------------


def test_a_dealt_game_rests_in_the_mulligan_step():
    """CR 103.5 runs before CR 103.8's first turn, so that is where the game is."""
    match = series(devoted(), broodscale())
    game = match.start_game()

    assert game.turn is not None
    assert game.turn.step is Step.MULLIGAN
    assert game.turn.in_pregame
    assert game.in_pregame


def test_the_mulligan_step_claims_nothing_about_a_turn():
    """The leak this restructure exists to close.

    Before it, a game ran CR 103.5 and CR 103.6 while its turn machine said
    `Step.UNTAP`, turn 1 - and the API's audit log recorded both pregame phases
    against "turn 1 / untap", which was simply false. CR 500.1 makes a step part
    of a turn and CR 103.8 has the first turn begin after all of this, so every
    count that would claim a turn had begun reads zero here.
    """
    game = series(devoted(), broodscale()).start_game()

    assert game.turn.step is Step.MULLIGAN
    assert game.turn.phase is None  # CR 500.1 lists five phases; this is in none
    assert game.turn.turn_number == 0
    assert game.turn.turns_taken == 0
    assert not game.turn.is_first_turn
    assert not game.turn.grants_priority  # nothing in CR 103.5/103.6 grants it


def test_resting_asks_nobody_anything():
    """The whole point: a rested-in step puts no question to anyone.

    The old shape ran both pregame sequences inside one call that put every
    question through `Game.ask`. Behind a live seat that blocks until a human
    answers, that cost one answer timeout per question per seat. A step the game
    rests in has no wait to hold, and the proof is that starting a game records
    no question at all.
    """
    game = series(devoted(), broodscale()).start_game()

    assert game.decisions.asked == []


def test_the_turn_cannot_be_advanced_before_it_has_begun():
    """CR 500.1's steps are parts of a turn, and CR 103.8's has not started."""
    game = series(devoted(), broodscale()).start_game()

    with pytest.raises(ValueError, match="pregame"):
        game.advance()
    with pytest.raises(ValueError, match="pregame"):
        game.advance_to(Step.PRECOMBAT_MAIN)


# -- declaring through the step (CR 103.5) ---------------------------------


def test_each_seat_declares_and_the_last_one_ends_the_process():
    """CR 103.5's declarations arrive one at a time and resolve together."""
    match = series(devoted(), broodscale())
    game = match.start_game()

    assert game.awaiting_mulligan_declarations == ["alice", "bob"]

    assert game.declare_mulligan("alice", False) is Step.MULLIGAN
    assert game.awaiting_mulligan_declarations == ["bob"]

    assert game.declare_mulligan("bob", False) is Step.PREGAME_ACTIONS
    assert all(player.hand_kept for player in game.players)


def test_a_declared_mulligan_opens_a_fresh_round():
    """ "The process is then repeated until no player takes a mulligan" (CR 103.5)."""
    match = series(devoted(), broodscale())
    game = match.start_game()
    alice = game.player("alice")

    game.declare_mulligan("alice", True)
    game.declare_mulligan("bob", False)

    assert game.turn.step is Step.MULLIGAN
    assert alice.mulligans_taken == 1
    assert not alice.hand_kept
    assert game.player("bob").hand_kept
    # Bob kept, so only the seat that mulliganed is asked again.
    assert game.awaiting_mulligan_declarations == ["alice"]


def test_no_mulligan_is_taken_until_every_declaration_is_in():
    """CR 103.5: "all players who decided to take mulligans do so at the same time".

    Declarations arriving as separate calls is exactly what could have broken
    this, so it is checked here as well as in `test_mulligans.py`.
    """
    match = series(devoted(), broodscale())
    game = match.start_game()
    dealt_hands = {p.username: [s.id for s in p.hand] for p in game.players}

    game.declare_mulligan("alice", True)

    # Alice has declared; nothing has happened to anyone's hand yet.
    for player in game.players:
        assert [s.id for s in player.hand] == dealt_hands[player.username]
    assert game.player("alice").mulligans_taken == 0

    game.declare_mulligan("bob", True)

    for player in game.players:
        assert [s.id for s in player.hand] != dealt_hands[player.username]
        assert player.mulligans_taken == 1


def test_a_seat_may_not_declare_twice_in_a_round():
    match = series(devoted(), broodscale())
    game = match.start_game()
    game.declare_mulligan("alice", False)

    with pytest.raises(ValueError, match="already declared"):
        game.declare_mulligan("alice", False)


def test_a_seat_that_has_kept_is_not_asked_again():
    match = series(devoted(), broodscale())
    game = match.start_game()
    game.declare_mulligan("alice", True)
    game.declare_mulligan("bob", False)

    with pytest.raises(ValueError, match="already kept a hand"):
        game.declare_mulligan("bob", False)


def test_declaring_a_mulligan_past_the_ceiling_is_refused():
    """CR 103.5's ceiling: "until their opening hand would be zero cards"."""
    match = series(devoted(), broodscale())
    game = match.start_game()
    alice = game.player("alice")

    while alice.can_mulligan:
        game.declare_mulligan("alice", True)
        if not game.player("bob").hand_kept:
            game.declare_mulligan("bob", False)

    assert alice.mulligans_taken == 7
    assert game.awaiting_mulligan_declarations == []
    with pytest.raises(ValueError, match="hand of nothing"):
        game.declare_mulligan("alice", True)


def test_the_declaration_driven_path_replays_the_settled_one():
    """Same seed, same declarations, same game - however the answers arrived.

    The seeded replay is the reason the mulligan reshuffle keeps deriving its
    seed from the match seed rather than from a live RNG, and splitting the
    process into one call per declaration is exactly what could have broken it.
    """
    driven_match = series(devoted(), broodscale(), seed="replay")
    driven = driven_match.start_game()
    driven.declare_mulligan("alice", True)
    driven.declare_mulligan("bob", False)
    driven.declare_mulligan("alice", False)

    settled_match = series(devoted(), broodscale(), seed="replay")
    settled = settled_match.start_game()
    settled.decisions.add(
        ScriptedAnswer(kind=DecisionKind.MULLIGAN, value=True, player="alice", uses=1)
    )
    settled_match.run_mulligans(settled)

    for username in ("alice", "bob"):
        assert [s.name for s in driven.player(username).hand] == [
            s.name for s in settled.player(username).hand
        ]
        assert [s.name for s in driven.player(username).library] == [
            s.name for s in settled.player(username).library
        ]


# -- the opening-hand step (CR 103.6) --------------------------------------


def test_the_starting_player_is_the_first_seat_to_act():
    """CR 103.6: "the starting player may take any such actions ... Then ea[ch]"."""
    match = series(devoted(), devoted())
    game = dealt(
        match,
        {"alice": "Leyline of Abundance", "bob": "Leyline of Abundance"},
        on_the_play="bob",
    )
    game.declare_mulligan("bob", False)
    game.declare_mulligan("alice", False)

    assert game.turn.step is Step.PREGAME_ACTIONS
    assert game.turn.starting_player == "bob"
    assert game.opening_hand_actor == "bob"

    game.finish_opening_hand_actions("bob")

    assert game.opening_hand_actor == "alice"


def test_a_seat_may_not_act_out_of_turn():
    """CR 103.6 names its own order, so the other seat's turn is not yet."""
    game, _ = two_leylines()
    game.declare_mulligan("alice", False)
    game.declare_mulligan("bob", False)
    leyline = next(s for s in game.player("bob").hand if s.name == "Leyline of Abundance")

    assert game.opening_hand_actor == "alice"
    with pytest.raises(ValueError, match="not bob's"):
        game.take_opening_hand_action("bob", leyline.id)
    with pytest.raises(ValueError, match="not bob's"):
        game.finish_opening_hand_actions("bob")


def test_a_seat_takes_its_action_by_naming_the_card():
    """CR 103.6a, driven the way a live seat drives it: no question, just the move."""
    game, _ = two_leylines()
    game.declare_mulligan("alice", False)
    game.declare_mulligan("bob", False)
    leyline = next(s for s in game.player("alice").hand if s.name == "Leyline of Abundance")

    offered = game.opening_hand_options("alice")
    assert [decision.source for decision in offered] == ["Leyline of Abundance"]
    assert offered[0].card == leyline.id
    assert offered[0].kind is DecisionKind.OPENING_HAND_ACTION

    game.take_opening_hand_action("alice", leyline.id)

    assert leyline.zone is Zone.BATTLEFIELD
    assert leyline in game.battlefield
    # Still nothing was asked: the answer came in with the call.
    assert game.decisions.asked == []


def test_a_card_that_offers_no_action_is_refused():
    """CR 103.6's question exists only where a card "allows a player to take" one."""
    game, _ = two_leylines()
    game.declare_mulligan("alice", False)
    game.declare_mulligan("bob", False)
    other = next(s for s in game.player("alice").hand if s.name != "Leyline of Abundance")

    with pytest.raises(ValueError, match="offers that action"):
        game.take_opening_hand_action("alice", other.id)


def test_the_last_seat_finishing_begins_the_first_turn():
    """CR 103.8, in full: "The starting player takes their first turn"."""
    game, _ = two_leylines()
    game.declare_mulligan("alice", False)
    game.declare_mulligan("bob", False)

    game.finish_opening_hand_actions("alice")
    assert game.turn.step is Step.PREGAME_ACTIONS  # bob has not finished

    assert game.finish_opening_hand_actions("bob") is Step.UNTAP
    assert game.turn.turn_number == 1
    assert game.turn.turns_taken == 1
    assert game.turn.active_player == "alice"
    assert not game.in_pregame


def test_beginning_the_first_turn_untaps_nothing_and_draws_nothing():
    """The pointer moves; CR 500's turn-based actions are the turn's, not this.

    A Leyline put onto the battlefield under CR 103.6a is the thing that would
    notice a stray untap, and the seven cards in hand are what would notice a
    stray draw.
    """
    game, _ = two_leylines()
    game.declare_mulligan("alice", False)
    game.declare_mulligan("bob", False)
    leyline = next(s for s in game.player("alice").hand if s.name == "Leyline of Abundance")
    game.take_opening_hand_action("alice", leyline.id)
    leyline.tapped = True
    library_before = len(game.player("alice").library)

    game.finish_opening_hand_actions("alice")
    game.finish_opening_hand_actions("bob")

    assert game.turn.step is Step.UNTAP
    assert leyline.tapped, "the untap step's own action has not happened yet"
    assert len(game.player("alice").hand) == 6  # seven dealt, one is on the battlefield
    assert len(game.player("alice").library) == library_before


def test_a_whole_pregame_played_live_asks_nothing():
    """End to end, the measurement that motivated this: zero blocking questions.

    Both seats declare and both seats take their CR 103.6 turn, and the engine
    never once blocks the calling thread on a live seat's answer. Under the old
    shape this same game asked four questions - one per seat per sequence -
    each of which a live seat answered by blocking the thread until a human or
    a timeout arrived.
    """
    game, _ = two_leylines()

    game.declare_mulligan("alice", False)
    game.declare_mulligan("bob", False)
    game.finish_opening_hand_actions("alice")
    game.finish_opening_hand_actions("bob")

    assert game.turn.step is Step.UNTAP
    assert game.decisions.asked == []


def test_settling_a_pregame_is_still_one_call_for_a_headless_caller():
    """The default path is unchanged: no answerer, hands kept, promptly."""
    match = series(devoted(), broodscale())
    game = match.start_game()

    assert game.settle_pregame() is Step.UNTAP
    assert all(player.hand_kept for player in game.players)
    assert all(len(player.hand) == 7 for player in game.players)
    assert game.turn.turn_number == 1
