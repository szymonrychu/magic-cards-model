"""The London mulligan: `Match.run_mulligans` settles every opening hand.

CR 103.5, in the order the rule states it: "First, the starting player declares
whether they will take a mulligan. Then each other player in turn order does
the same. Once each player has made a declaration, all players who decided to
take mulligans do so at the same time." The process "is then repeated until no
player takes a mulligan", and "a player can take mulligans until their opening
hand would be zero cards, after which they may not take further mulligans".
CR 103.5c and CR 800.6 make the first mulligan free in a multiplayer game.

Every mulligan here is declared the way a player would: a scripted
`DecisionKind.MULLIGAN` answer on the game's decision script, the same
staging a scenario uses for a scry. Nobody mulliganing is not scripted at
all - the default answer is to keep, and that is tested too.

The decklist is Reironaldu's "eldrazi ramp", second place in the Modern
challenge at https://www.mtgtop8.com/event?e=90117&d=884028&f=mo (mtgtop8
deck 884028), played 2026-08-27. It was pulled with
`statistics_decks(format="modern", include_cards="full")` and all 29 distinct
cards verified Modern-legal with `resolve_cards` before being written here.
"""

import pytest

import magic_cards_model.models.game as game_module
from magic_cards_model.machines.decisions import (
    Answer,
    Decision,
    DecisionKind,
    DecisionPending,
    ScriptedAnswer,
    ask_mulligan,
)
from magic_cards_model.models import Deck, Game, Match, Player, Zone
from tests.cards import card

ELDRAZI_RAMP_MAIN = {
    "Boseiju, Who Endures": 1,
    "Cavern of Souls": 1,
    "Dryad Arbor": 1,
    "Eldrazi Temple": 4,
    "Forest": 5,
    "Gemstone Caverns": 1,
    "Mosswort Bridge": 1,
    "Ugin's Labyrinth": 4,
    "Disciple of Freyalise": 4,
    "Drowner of Truth": 2,
    "Emrakul, the Promised End": 4,
    "Fanatic of Rhonas": 4,
    "Slumbering Trudge": 4,
    "Sowing Mycospawn": 4,
    "Ulamog, the Ceaseless Hunger": 2,
    "Green Sun's Zenith": 4,
    "Kozilek's Command": 4,
    "Malevolent Rumble": 4,
    "Fight Rigging": 4,
    "Ugin, Eye of the Storms": 2,
}

ELDRAZI_RAMP_SIDE = {
    "Dismember": 1,
    "Elder Gargaroth": 1,
    "Force of Vigor": 2,
    "Grafdigger's Cage": 2,
    "Six": 1,
    "Thought-Knot Seer": 2,
    "Torpor Orb": 1,
    "Trinisphere": 3,
    "Warping Wail": 2,
}


def eldrazi_ramp() -> Deck:
    return Deck(mainboard=ELDRAZI_RAMP_MAIN, sideboard=ELDRAZI_RAMP_SIDE)


def match(seed: int | str = "mulligan", **kwargs) -> Match:
    """A two-player match, both seats on the registered tournament list."""
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
        **kwargs,
    )
    series.register_deck("alice", eldrazi_ramp())
    series.register_deck("bob", eldrazi_ramp())
    return series


def three_player_match(seed: int | str = "table") -> Match:
    """A multiplayer game is one that begins with more than two players (CR 800.1)."""
    series = Match(
        players=[Player(username=username) for username in ("alice", "bob", "carol")],
        card_resolver=card,
        seed=seed,
    )
    for username in ("alice", "bob", "carol"):
        series.register_deck(username, eldrazi_ramp())
    return series


def will_mulligan(game: Game, player: str, times: int = 1) -> None:
    """Script `times` declarations to take a mulligan, for one player."""
    game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.MULLIGAN, value=True, player=player, uses=times)
    )


def asked_of(game: Game, player: str) -> list[Decision]:
    """The mulligan declarations the engine put to one player, in order."""
    return [
        decision
        for decision in game.decisions.asked
        if decision.kind is DecisionKind.MULLIGAN and decision.player == player
    ]


# -- nobody mulligans (CR 103.5) -------------------------------------------


def test_unscripted_players_keep_the_hands_they_were_dealt():
    """The default declaration is to keep: CR 103.5, "dissatisfied ... may"."""
    series = match()
    game = series.start_game()
    dealt = {player.username: [state.id for state in player.hand] for player in game.players}

    settled = series.run_mulligans()

    assert settled is game
    for player in game.players:
        assert [state.id for state in player.hand] == dealt[player.username]
        assert len(player.hand) == 7
        assert len(player.library) == 53
        assert player.mulligans_taken == 0
        assert player.hand_kept
        assert player.first_mulligan_free is False


def test_every_player_is_asked_once_in_turn_order():
    """CR 103.5: starting player first, then each other player in turn order."""
    series = match()
    game = series.start_game()

    series.run_mulligans()

    # Narrowed to the declaration: CR 103.6's opening-hand actions follow this
    # process on the same script, and this list plays a Gemstone Caverns.
    assert [
        (d.player, d.kind) for d in game.decisions.asked if d.kind is DecisionKind.MULLIGAN
    ] == [
        ("alice", DecisionKind.MULLIGAN),
        ("bob", DecisionKind.MULLIGAN),
    ]


def test_the_declarations_follow_who_takes_the_first_turn():
    """Turn order is the game's player order, and start_game puts the first player first."""
    series = match()
    game = series.start_game(on_the_play="bob")

    assert [player.username for player in game.players] == ["bob", "alice"]

    series.run_mulligans()

    assert [d.player for d in game.decisions.asked if d.kind is DecisionKind.MULLIGAN] == [
        "bob",
        "alice",
    ]


# -- one and two mulligans (CR 103.5) ---------------------------------------


def test_one_mulligan_ends_on_six_with_the_first_hand_shuffled_back():
    """CR 103.5: shuffle back, draw a fresh hand, and bottom one at the keep."""
    series = match()
    game = series.start_game()
    alice = game.player("alice")
    first_hand = [state.id for state in alice.hand]
    will_mulligan(game, "alice")

    series.run_mulligans()

    assert len(alice.hand) == 6
    assert len(alice.library) == 54
    assert alice.mulligans_taken == 1
    assert alice.hand_kept
    # The whole first hand went back through the library: what is kept now is
    # a different seven minus the one bottomed.
    assert [state.id for state in alice.hand] != first_hand
    assert all(state.zone is Zone.HAND for state in alice.hand)
    # An unscripted opponent keeps the hand they were dealt.
    bob = game.player("bob")
    assert len(bob.hand) == 7
    assert bob.mulligans_taken == 0
    assert bob.first_mulligan_free is False
    assert [d.player for d in asked_of(game, "bob")] == ["bob"]


def test_the_bottomed_card_is_the_last_card_of_the_library():
    """CR 103.5: "on the bottom of their library" - bottomed, not shuffled back."""
    series = match()
    game = series.start_game()
    alice = game.player("alice")
    will_mulligan(game, "alice")

    series.run_mulligans()

    bottom = alice.library[-1]
    assert bottom.owner == "alice"
    assert bottom.zone is Zone.LIBRARY
    assert bottom not in alice.hand
    # Sixty distinct alice-owned cards between hand, library, and sideboard.
    everywhere = alice.hand + alice.library + alice.sideboard
    assert len({state.id for state in everywhere}) == 75


def test_two_mulligans_end_on_five():
    series = match()
    game = series.start_game()
    alice = game.player("alice")
    will_mulligan(game, "alice", times=2)

    series.run_mulligans()

    assert len(alice.hand) == 5
    assert len(alice.library) == 55
    assert alice.mulligans_taken == 2
    # Both mulligans drew a full hand; only the keep bottoms. Asked once per
    # round: the scripted answers cover two rounds, and the third declaration
    # falls through to the default keep.
    assert [d.player for d in asked_of(game, "alice")] == ["alice", "alice", "alice"]


def test_a_player_who_keeps_is_never_asked_again():
    """CR 103.5: "may not take any further mulligans" - keep once, then out."""
    series = match()
    game = series.start_game()
    game.decisions.add(ScriptedAnswer(kind=DecisionKind.MULLIGAN, value=False, player="alice"))
    will_mulligan(game, "bob", times=2)

    series.run_mulligans()

    alice = game.player("alice")
    bob = game.player("bob")
    assert len(alice.hand) == 7
    assert alice.mulligans_taken == 0
    # Alice declared keep in the first round and sat out every round after,
    # while bob mulliganed twice and was asked once more before keeping.
    assert [d.player for d in asked_of(game, "alice")] == ["alice"]
    assert [d.player for d in asked_of(game, "bob")] == ["bob", "bob", "bob"]
    assert len(bob.hand) == 5


# -- the zero-hand ceiling (CR 103.5) ---------------------------------------


def test_mulliganing_to_a_hand_of_nothing_and_keeping_it():
    """CR 103.5: "until their opening hand would be zero cards" - zero is legal."""
    series = match()
    game = series.start_game()
    alice = game.player("alice")
    will_mulligan(game, "alice", times=7)

    series.run_mulligans()

    assert alice.hand == []
    assert len(alice.library) == 60
    assert alice.mulligans_taken == 7
    assert alice.hand_kept
    # The eighth round offers no declaration: seven is all CR 103.5 allows.
    assert len(asked_of(game, "alice")) == 7
    # Bottoming seven from an empty hand bottoms nothing.
    assert alice.cards_to_bottom == 0


def test_a_player_at_the_ceiling_is_offered_no_declaration():
    """CR 103.5: "after which they may not take further mulligans" - not even a no."""
    series = match()
    game = series.start_game()
    alice = game.player("alice")
    will_mulligan(game, "alice", times=7)

    assert alice.can_mulligan
    series.run_mulligans()

    assert not alice.can_mulligan
    assert alice.hand_kept
    # Round eight put no question at all: seven for alice, and bob's one
    # declaration was the first round, where the default keep answered him.
    assert len(asked_of(game, "alice")) == 7
    mulligan_questions = [
        decision for decision in game.decisions.asked if decision.kind is DecisionKind.MULLIGAN
    ]
    # Counted by kind: CR 103.6's opening-hand actions run once this process is
    # complete and put their own questions on the same script (this list plays
    # a Gemstone Caverns), which is not what this test is about.
    assert len(mulligan_questions) == 8


# -- multiplayer: the free first mulligan (CR 103.5c, CR 800.6) --------------


def test_the_first_multiplayer_mulligan_costs_nothing():
    """CR 103.5c: "the first mulligan ... doesn't count toward the number of
    cards that player will put on the bottom"."""
    series = three_player_match()
    game = series.start_game()
    alice = game.player("alice")
    will_mulligan(game, "alice")

    series.run_mulligans()

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert alice.mulligans_taken == 1
    assert alice.first_mulligan_free
    assert alice.cards_to_bottom == 0
    # The free mulligan is every player's, whether or not they took it.
    assert all(player.first_mulligan_free for player in game.players)


def test_the_second_multiplayer_mulligan_bottoms_one():
    series = three_player_match()
    game = series.start_game()
    alice = game.player("alice")
    will_mulligan(game, "alice", times=2)

    series.run_mulligans()

    assert len(alice.hand) == 6
    assert len(alice.library) == 54
    assert alice.mulligans_taken == 2
    assert alice.cards_to_bottom == 1


def test_multiplayer_mulligans_to_a_hand_of_nothing_in_eight():
    """The free first mulligan also "doesn't count toward ... the number of
    mulligans that player may take" (CR 103.5c): the ceiling moves to eight."""
    series = three_player_match()
    game = series.start_game()
    alice = game.player("alice")
    will_mulligan(game, "alice", times=8)

    series.run_mulligans()

    assert alice.hand == []
    assert len(alice.library) == 60
    assert alice.mulligans_taken == 8
    assert len(asked_of(game, "alice")) == 8


def test_a_two_player_game_has_no_free_mulligan():
    """CR 103.5c is for "a multiplayer game and ... any Brawl game" - and CR
    800.1 makes multiplayer one that begins with more than two players."""
    series = match()
    game = series.start_game()
    alice = game.player("alice")
    will_mulligan(game, "alice")

    assert alice.first_mulligan_free is False

    series.run_mulligans()

    assert len(alice.hand) == 6
    assert len(alice.library) == 54
    assert alice.cards_to_bottom == 1


# -- reproducibility --------------------------------------------------------


def test_the_same_seed_and_declarations_replay_the_same_mulligans():
    def one_mulligan(seed: int | str) -> tuple[list[str], list[str]]:
        series = match(seed=seed)
        game = series.start_game()
        will_mulligan(game, "alice")
        series.run_mulligans()
        alice = game.player("alice")
        return [state.name for state in alice.hand], [state.name for state in alice.library]

    hand, library = one_mulligan("replay")
    assert one_mulligan("replay") == (hand, library)
    assert one_mulligan("elsewhere") != (hand, library)


# -- what run_mulligans refuses ---------------------------------------------


def test_run_mulligans_without_a_started_game_is_refused():
    with pytest.raises(ValueError, match="no game has been started"):
        match().run_mulligans()


def test_a_game_the_match_did_not_start_is_refused():
    onlookers = Game(
        players=[Player(username="alice"), Player(username="bob")],
        schema_version=Game.CURRENT_SCHEMA_VERSION,
    )

    with pytest.raises(ValueError, match="not one this match started"):
        match().run_mulligans(onlookers)


# -- which cards go to the bottom (CR 103.5, CR 103.5c, CR 800.6) -----------
#
# Keeping a hand after a mulligan costs "the number of cards that player will
# put on the bottom of their library" (CR 103.5c, CR 800.6). The count is the
# rules'; *which* cards is the player's, and `Match.run_mulligans` now asks it
# as a `CHOOSE_CARDS` question - the same kind CR 701.9b's cleanup discard
# uses - instead of silently taking the back of the hand. A scripted answer
# wins first, then the replay tape (see the "pausing instead of blocking"
# section below), and only then does `default_answer` speak for the player -
# there is exactly one way to answer a decision from outside the engine.


def bottoming_offers(game: Game, player: str) -> list[Decision]:
    """The `CHOOSE_CARDS` bottoming questions put to one player, in order."""
    return [
        decision
        for decision in game.decisions.asked
        if decision.kind is DecisionKind.CHOOSE_CARDS and decision.player == player
    ]


def test_the_bottoming_question_is_not_asked_when_nothing_is_bottomed():
    """No mulligan, no cost: "a choice among zero cards is not a choice"."""
    series = match()
    game = series.start_game()

    series.run_mulligans()

    assert bottoming_offers(game, "alice") == []
    assert bottoming_offers(game, "bob") == []


def test_the_unanswered_bottoming_still_takes_the_back_of_the_hand():
    """The load-bearing default: `default_answer` for an exact `CHOOSE_CARDS`
    is "the back of the offered cards", and the hand is offered in hand order,
    so an unanswered question bottoms what `keep_hand(None)` always bottomed."""
    series = match()
    game = series.start_game()
    alice = game.player("alice")
    will_mulligan(game, "alice")

    series.run_mulligans()

    (offer,) = bottoming_offers(game, "alice")
    assert offer.amount == 1
    assert len(offer.cards) == 7
    assert alice.library[-1].id == offer.cards[-1], "the back of the hand went to the bottom"
    assert [state.id for state in alice.hand] == list(offer.cards[:-1])


def test_a_scripted_bottoming_answer_chooses_which_card_goes_to_the_bottom():
    """The whole point of asking: the player picks, and it is not the back."""
    series = match()
    game = series.start_game()
    alice = game.player("alice")
    # Staging, not mocking: alice takes a real mulligan through the real engine
    # before the process is run, which is the only way to name a card of the
    # post-mulligan hand in a script - card ids are minted per game.
    # `Player.mulligan` mints every moved card's own `zone_change_stamp` with
    # no `Game` method's `_id_allocator_scope` open around it here.
    with game._id_allocator_scope():  # noqa: SLF001
        alice.mulligan(seed="staged")
    assert alice.cards_to_bottom == 1
    chosen = alice.hand[3]

    game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.CHOOSE_CARDS, value=(chosen.id,), player="alice")
    )

    series.run_mulligans()

    assert alice.library[-1] is chosen, "the script named it, not the front and not the back"
    assert chosen not in alice.hand
    assert len(alice.hand) == 6


def test_two_mulligans_offer_the_whole_hand_and_bottom_two_of_a_scripted_choice():
    """CR 103.5c/CR 800.6's count: two mulligans, two cards on the bottom, and
    both come out of the seven the player is holding when they keep."""
    series = match()
    game = series.start_game()
    alice = game.player("alice")
    with game._id_allocator_scope():  # noqa: SLF001
        alice.mulligan(seed="staged-1")
        alice.mulligan(seed="staged-2")
    assert alice.cards_to_bottom == 2
    chosen = (alice.hand[0].id, alice.hand[1].id)

    game.decisions.add(ScriptedAnswer(kind=DecisionKind.CHOOSE_CARDS, value=chosen, player="alice"))

    series.run_mulligans()

    (offer,) = bottoming_offers(game, "alice")
    assert (len(offer.cards), offer.amount) == (7, 2)
    assert len(alice.hand) == 5
    # The hand kept is the offer minus what was chosen, not just five cards
    # of some size - pinning both halves of the split.
    assert [state.id for state in alice.hand] == list(offer.cards[2:])
    assert [state.id for state in alice.library[-2:]] == list(chosen)


def test_a_free_first_mulligan_costs_no_bottoming_question():
    """CR 103.5c and CR 800.6: in a multiplayer game the first mulligan "doesn't
    count toward the number of cards that player will put on the bottom", so
    there is nothing to choose and nothing is asked."""
    series = three_player_match()
    game = series.start_game()
    will_mulligan(game, "alice")

    series.run_mulligans()

    alice = game.player("alice")
    assert alice.first_mulligan_free
    assert alice.mulligans_taken == 1
    assert len(alice.hand) == 7
    assert bottoming_offers(game, "alice") == []


def test_a_chosen_bottoming_replays_identically():
    """Determinism survives the second question too: nothing random happens in
    the bottoming, so the same seed and the same choices give the same library."""

    def run() -> tuple[list[str], list[str]]:
        series = match(seed="replay")
        game = series.start_game()
        alice = game.player("alice")
        with game._id_allocator_scope():  # noqa: SLF001
            alice.mulligan(seed="staged")
        chosen = alice.hand[0]
        game.decisions.add(
            ScriptedAnswer(kind=DecisionKind.CHOOSE_CARDS, value=(chosen.id,), player="alice")
        )
        series.run_mulligans()
        return [c.name for c in alice.hand], [c.name for c in alice.library]

    assert run() == run()


def test_the_bottoming_is_asked_after_every_declaration_of_the_round():
    """The keep, and therefore the bottoming, happens once the round's
    declarations are all in - CR 103.5's "once each player has made a
    declaration" - never interleaved into the declaration loop.

    `decisions.asked` records every question in the order it was actually put,
    whatever answered it, so the round's sequencing is provable straight off
    it: no `CHOOSE_CARDS` for either player appears between the two rounds'
    `MULLIGAN` declarations.
    """
    series = match()
    game = series.start_game()
    game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.MULLIGAN, value=True, player="alice", uses=1)
    )

    series.run_mulligans()

    order = [
        (decision.player, decision.kind)
        for decision in game.decisions.asked
        if decision.kind in (DecisionKind.MULLIGAN, DecisionKind.CHOOSE_CARDS)
    ]
    assert order == [
        # Round one: both declare before anything is taken or bottomed.
        ("alice", DecisionKind.MULLIGAN),
        ("bob", DecisionKind.MULLIGAN),
        # Bob kept, so his bottoming (of nothing) is not asked; alice mulligans.
        ("alice", DecisionKind.MULLIGAN),
        ("alice", DecisionKind.CHOOSE_CARDS),
    ]


def test_every_declaration_is_collected_before_any_mulligan_is_taken(monkeypatch):
    """CR 103.5: "Once each player has made a declaration, all players who
    decided to take mulligans do so at the same time."

    `test_the_bottoming_is_asked_after_every_declaration_of_the_round` proves
    the *order* `decisions.asked` records the two rounds' declarations in, but
    that order is identical whether or not alice's round-one mulligan is
    applied before bob is asked his - it only orders the questions, never the
    state each one is asked against. This test proves the engine-ordering half
    that order alone cannot: it wraps `ask_mulligan` at the one seam
    `Game.settle_pregame` calls it through -
    `magic_cards_model.models.game.ask_mulligan`, the name that module binds
    at import and the name `settle_pregame`'s own `while` loop looks up at
    call time - recording every player's hand size and `mulligans_taken` at
    the instant each question is put, then calling straight through to the
    real `ask_mulligan`. That makes it a spy, not a stand-in: every answer it
    returns, and every card it moves, is the engine's own; nothing here fakes
    a rule or a card.

    Had the engine resolved each declaration as it arrived instead of
    collecting the whole round first, bob's round-one snapshot would have
    found alice already on a fresh hand with `mulligans_taken == 1` - the
    exact miss this replaces from `test_every_declaration_is_collected_
    before_any_mulligan_is_taken` on the deleted `DecisionProvider` version of
    this file, where a `RecordingProvider.decide` callback took the same
    snapshot at the same moment. Confirmed by deliberately breaking the
    engine's round-collection guard and watching this assertion fail on
    bob's round-one snapshot for exactly that reason, then reverting.
    """
    series = match()
    game = series.start_game()
    will_mulligan(game, "alice")
    will_mulligan(game, "bob")
    snapshots: list[tuple[str, tuple[tuple[str, int, int], ...]]] = []
    real_ask_mulligan = game_module.ask_mulligan

    def watching_ask_mulligan(script, player, **kwargs):
        snapshots.append(
            (player, tuple((p.username, len(p.hand), p.mulligans_taken) for p in game.players))
        )
        return real_ask_mulligan(script, player, **kwargs)

    monkeypatch.setattr(game_module, "ask_mulligan", watching_ask_mulligan)

    series.run_mulligans()

    round_one = snapshots[:2]
    assert [asked for asked, _ in round_one] == ["alice", "bob"]
    for _, table in round_one:
        assert table == (("alice", 7, 0), ("bob", 7, 0))

    round_two = snapshots[2:]
    assert [asked for asked, _ in round_two] == ["alice", "bob"]
    for _, table in round_two:
        assert table == (("alice", 7, 1), ("bob", 7, 1))

    assert game.player("alice").mulligans_taken == 1
    assert game.player("bob").mulligans_taken == 1


# -- pausing instead of blocking: the tape and `DecisionPending` ------------
#
# `ask_mulligan` reads the replay tape and can pause exactly like `Game.ask`
# does (see `machines/decisions.py`'s module docstring) - both new in the same
# commit that gave `Game.ask` a tape and a pause, and neither had a test until
# here.


def test_a_recorded_tape_answers_the_mulligan_declaration():
    """`DecisionScript.recorded` answers CR 103.5's declaration the same way
    `Game.ask` reads it for a resolving effect's choice - one `Answer` per
    question, in order, matching `test_the_bottoming_is_asked_after_every_
    declaration_of_the_round`'s own proof of the exact sequence: alice
    mulligans, bob keeps, then alice keeps and the process ends.
    """
    series = match()
    game = series.start_game()
    game.decisions.recorded = [
        Answer(seq=0, kind=DecisionKind.MULLIGAN, player="alice", accept=True),
        Answer(seq=1, kind=DecisionKind.MULLIGAN, player="bob", accept=False),
        Answer(seq=2, kind=DecisionKind.MULLIGAN, player="alice", accept=False),
    ]

    series.run_mulligans()

    alice = game.player("alice")
    bob = game.player("bob")
    assert alice.mulligans_taken == 1
    assert len(alice.hand) == 6
    assert bob.mulligans_taken == 0
    assert len(bob.hand) == 7
    # The bottoming question that follows has no tape entry of its own, so it
    # falls through to `default_answer` exactly as an unscripted one would -
    # the tape not fully covering a run is not itself an error.
    assert game.decisions.consumed == 3


def test_a_scripted_declaration_still_wins_over_a_recorded_tape_entry():
    """`ask_mulligan` tries the script before the replay tape, always - the
    same order `Game.ask` uses for a resolving effect's own choice. Called
    directly rather than through `Match.run_mulligans`, which would go on to
    put CR 103.6's opening-hand questions to the same unscripted tape.
    """
    series = match()
    game = series.start_game()
    game.decisions.recorded = [
        Answer(seq=0, kind=DecisionKind.MULLIGAN, player="alice", accept=True),
    ]
    game.decisions.add(ScriptedAnswer(kind=DecisionKind.MULLIGAN, value=False, player="alice"))

    answer = ask_mulligan(game.decisions, "alice")

    assert answer is False, "the script's keep, not the tape's mulligan, decided"
    assert game.decisions.consumed == 0, "the tape entry was never read"


def test_a_mulligan_tape_entry_for_the_wrong_player_is_refused():
    """The same corrupt-tape refusal `Game.ask`'s tape already has - see
    `tests/scenarios/test_decisions_during_resolution.py::
    test_a_tape_entry_for_the_wrong_player_raises_a_corrupt_tape_error` -
    proven here for `ask_mulligan`'s own call to `take_from_tape`."""
    series = match()
    game = series.start_game()
    game.decisions.recorded = [
        Answer(seq=0, kind=DecisionKind.MULLIGAN, player="bob", accept=True),
    ]

    with pytest.raises(ValueError, match="corrupt or out of order"):
        series.run_mulligans()


def test_pause_when_unanswered_raises_decision_pending_for_the_mulligan_declaration():
    """With nothing scripted and no tape, `pause_when_unanswered`
    turns CR 103.5's declaration into a raised `DecisionPending` - the same
    proof `test_pause_when_unanswered_raises_decision_pending_through_a_
    resolving_spell` gives for `Game.ask`, given here for `ask_mulligan`,
    which never goes through `Game.ask` at all.
    """
    series = match()
    game = series.start_game()
    game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as excinfo:
        series.run_mulligans()

    pending = excinfo.value.pending
    assert pending.decision.kind is DecisionKind.MULLIGAN
    assert pending.decision.player == "alice"
    assert pending.seq == 0
    assert "103.5" in pending.rule
