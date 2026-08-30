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

from magic_cards_model.machines.decisions import (
    Decision,
    DecisionKind,
    ScriptedAnswer,
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

    assert [(d.player, d.kind) for d in game.decisions.asked] == [
        ("alice", DecisionKind.MULLIGAN),
        ("bob", DecisionKind.MULLIGAN),
    ]


def test_the_declarations_follow_who_takes_the_first_turn():
    """Turn order is the game's player order, and start_game puts the first player first."""
    series = match()
    game = series.start_game(on_the_play="bob")

    assert [player.username for player in game.players] == ["bob", "alice"]

    series.run_mulligans()

    assert [d.player for d in game.decisions.asked] == ["bob", "alice"]


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
    assert len(game.decisions.asked) == 8


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
    onlookers = Game(players=[Player(username="alice"), Player(username="bob")])

    with pytest.raises(ValueError, match="not one this match started"):
        match().run_mulligans(onlookers)
