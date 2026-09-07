"""Starting a game: decks, shuffling, opening hands, and the London mulligan.

CR 103 in order - decide who takes the first turn (103.1), set sideboards aside
(103.2a), shuffle (103.3), set life totals (103.4), draw opening hands and
mulligan (103.5).

Every library here is a real sixty-card decklist resolved against the printings
in `tests/fixtures/cards`, so a shuffle moves real cards and an opening hand is
seven of them.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Deck, DeckLimits, Game, Match, Player, Zone
from tests.cards import card

BURN_SIXTY = {
    "Mountain": 24,
    "Plains": 12,
    "Lightning Bolt": 4,
    "Grizzly Bears": 4,
    "Sol Ring": 4,
    "Questing Beast": 4,
    "Swords to Plowshares": 4,
    "Counterspell": 4,
}

ELVES_SIXTY = {
    "Forest": 26,
    "Island": 10,
    "Llanowar Elves": 4,
    "Birds of Paradise": 4,
    "Giant Growth": 4,
    "Delver of Secrets": 4,
    "Grizzly Bears": 4,
    "Chromatic Lantern": 4,
}


def deck(mainboard: dict[str, int], **kwargs) -> Deck:
    return Deck(mainboard=mainboard, **kwargs)


def match(seed: int | str = 1, **kwargs) -> Match:
    """A two-player match with both decks registered and both sideboards set."""
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
        **kwargs,
    )
    series.register_deck("alice", deck(BURN_SIXTY, sideboard={"Island": 15}))
    series.register_deck("bob", deck(ELVES_SIXTY, sideboard={"Swords to Plowshares": 4}))
    return series


# -- dealing the game (CR 103.2 - 103.5) ----------------------------------


def test_a_game_begins_with_seven_cards_from_a_real_deck():
    """CR 103.5: each player draws a hand equal to their starting hand size."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert all(state.zone is Zone.HAND for state in alice.hand)
    assert all(state.card.name in BURN_SIXTY for state in alice.hand)


def test_both_players_are_dealt_from_their_own_decks():
    game = match().start_game()

    bob = game.player("bob")

    assert len(bob.hand) == 7
    # Delver of Secrets is double-faced, so its printed name carries both faces.
    assert all(state.name.split(" //")[0] in ELVES_SIXTY for state in bob.library + bob.hand)
    assert "Mountain" not in {state.name for state in bob.library}


def test_the_sideboard_is_set_aside_and_never_shuffled_in():
    """CR 103.2a, 400.11a: sideboard cards are outside the game."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.sideboard) == 15
    assert len(alice.library) + len(alice.hand) == 60
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)


def test_every_copy_is_its_own_card_sharing_one_printing():
    """Twenty-four Mountains are twenty-four cards, not one card counted often."""
    game = match().start_game()
    alice = game.player("alice")

    mountains = [s for s in alice.library + alice.hand if s.name == "Mountain"]

    assert len(mountains) == 24
    assert len({state.id for state in mountains}) == 24


def test_the_game_starts_at_untap_with_life_at_twenty():
    """CR 103.4, 103.8: life totals, then the starting player's first turn.

    103.8 was written here as 103.7 from memory. Both numbers exist, so it
    read plausibly; 103.7 is not this rule. Looked up, not remembered.
    """
    game = match().start_game()

    assert game.turn is not None
    # CR 103.5 first: a dealt game rests in the mulligan step, before any turn.
    assert game.turn.step is Step.MULLIGAN
    assert game.turn.turn_number == 0

    game.settle_pregame()

    # CR 103.8: the starting player takes their first turn, which begins at untap.
    assert game.turn.step is Step.UNTAP
    assert all(player.life == 20 for player in game.players)


def test_a_player_without_a_registered_deck_starts_with_empty_zones():
    """A scenario that sets its own board up does not need a decklist."""
    series = Match(players=[Player(username="alice"), Player(username="bob")], card_resolver=card)
    series.register_deck("alice", deck(BURN_SIXTY))

    game = series.start_game()

    assert len(game.player("alice").library) == 53
    assert game.player("bob").library == []
    assert game.player("bob").hand == []


# -- shuffling (CR 103.3) --------------------------------------------------


def test_the_same_seed_deals_the_same_game_twice():
    """Determinism is the whole reason the seed is not optional."""
    first = [state.name for state in match(seed="kldc").start_game().player("alice").library]
    second = [state.name for state in match(seed="kldc").start_game().player("alice").library]

    assert first == second


def test_a_different_seed_deals_a_different_game():
    first = [state.name for state in match(seed="one").start_game().player("alice").library]
    second = [state.name for state in match(seed="two").start_game().player("alice").library]

    assert first != second


def test_two_players_do_not_get_the_same_shuffle():
    """One seed per match, but each player's shuffle is derived separately."""
    series = Match(players=[Player(username="alice"), Player(username="bob")], card_resolver=card)
    series.register_deck("alice", deck(BURN_SIXTY))
    series.register_deck("bob", deck(BURN_SIXTY))

    game = series.start_game()

    alice = [state.name for state in game.player("alice").library]
    bob = [state.name for state in game.player("bob").library]

    assert alice != bob
    # Same decklist, different order: the whole sixty still matches card for card.
    assert sorted(alice + [s.name for s in game.player("alice").hand]) == sorted(
        bob + [s.name for s in game.player("bob").hand]
    )


def test_shuffling_moves_the_cards_without_changing_them():
    player = Player(username="alice").load_deck(deck(BURN_SIXTY), card)
    before = [state.name for state in player.library]

    player.shuffle(42)
    after = [state.name for state in player.library]

    assert after != before
    assert sorted(after) == sorted(before)
    assert len(after) == 60


def test_the_second_game_of_a_match_is_shuffled_differently():
    """The seed derives per game, so game two is not a replay of game one."""
    series = match()
    first = [state.name for state in series.start_game().player("alice").library]
    series.games[-1].end_with_winner("bob")

    second = [state.name for state in series.start_game().player("alice").library]

    assert first != second


# -- the London mulligan (CR 103.5) ---------------------------------------


def mulliganing_player() -> Player:
    player = Player(username="alice").load_deck(deck(BURN_SIXTY), card)
    player.shuffle("mull")
    player.draw_opening_hand()
    assert len(player.hand) == 7
    return player


def test_a_kept_opening_hand_costs_nothing():
    player = mulliganing_player()

    kept = player.keep_hand()

    assert len(kept) == 7
    assert len(player.library) == 53
    assert player.hand_kept


def test_one_mulligan_still_draws_seven_and_bottoms_one():
    """CR 103.5: the London mulligan draws a full hand, then bottoms one per mulligan."""
    player = mulliganing_player()

    redrawn = player.mulligan("again")

    assert len(redrawn) == 7
    assert len(player.hand) == 7
    assert player.cards_to_bottom == 1

    player.keep_hand()

    assert len(player.hand) == 6
    assert len(player.library) == 54


def test_the_bottomed_card_goes_to_the_bottom_of_the_library():
    """It is bottomed, not shuffled back: it is the last card of the library."""
    player = mulliganing_player()
    player.mulligan("again")
    chosen = player.hand[0]

    player.keep_hand([chosen])

    assert player.library[-1] is chosen
    assert chosen.zone is Zone.LIBRARY
    assert chosen not in player.hand


def test_mulliganing_to_five_bottoms_two():
    player = mulliganing_player()

    player.mulligan("one")
    player.mulligan("two")

    assert len(player.hand) == 7
    assert player.mulligans_taken == 2

    player.keep_hand(player.hand[:2])

    assert len(player.hand) == 5
    assert len(player.library) == 55


def test_a_hand_shuffled_back_can_come_back_different():
    """CR 103.5: the whole hand goes back into the library and the deck is reshuffled."""
    player = mulliganing_player()
    first = [state.id for state in player.hand]

    player.mulligan("different")

    assert [state.id for state in player.hand] != first
    assert len(player.library) == 53


def test_mulliganing_all_the_way_down_to_nothing():
    """Seven mulligans is a hand of zero, and there is no eighth."""
    player = mulliganing_player()
    for index in range(7):
        player.mulligan(f"mull-{index}")

    player.keep_hand()

    assert player.hand == []
    assert len(player.library) == 60


def test_there_is_no_eighth_mulligan():
    player = mulliganing_player()
    for index in range(7):
        player.mulligan(f"mull-{index}")

    with pytest.raises(ValueError, match="cannot mulligan past a hand of nothing"):
        player.mulligan("one more")


def test_bottoming_the_wrong_number_of_cards_is_refused():
    player = mulliganing_player()
    player.mulligan("one")
    player.mulligan("two")

    with pytest.raises(ValueError, match="must put 2 cards on the bottom, not 1"):
        player.keep_hand(player.hand[:1])


def test_bottoming_a_card_that_is_not_in_hand_is_refused():
    player = mulliganing_player()
    player.mulligan("one")
    elsewhere = player.library[0]

    with pytest.raises(ValueError, match="is not in alice's hand"):
        player.keep_hand([elsewhere])


def test_a_kept_hand_cannot_be_mulliganed():
    player = mulliganing_player()
    player.keep_hand()

    with pytest.raises(ValueError, match="already kept a hand"):
        player.mulligan("too late")


def test_a_hand_is_kept_once():
    player = mulliganing_player()
    player.keep_hand()

    with pytest.raises(ValueError, match="already kept a hand"):
        player.keep_hand()


def test_an_opening_hand_is_dealt_once():
    player = mulliganing_player()

    with pytest.raises(ValueError, match="already has an opening hand"):
        player.draw_opening_hand()


# -- who takes the first turn (CR 103.1) ----------------------------------


def test_the_first_game_uses_the_players_agreed_order():
    """CR 103.1: any mutually agreeable method. Seat order is one, and it replays."""
    game = match().start_game()

    assert game.turn is not None
    assert game.turn.active_player == "alice"
    assert match().first_players == []


def test_a_chosen_starting_player_takes_the_first_turn():
    series = match()

    game = series.start_game(on_the_play="bob")

    assert game.turn is not None
    assert game.turn.active_player == "bob"
    assert series.first_players == ["bob"]
    assert series.choosers == [None]


def test_a_random_first_game_is_still_reproducible():
    """Random by CR 103.1, but off the match seed, so a scenario replays."""
    picks = {
        match(seed=seed, random_first_player=True).start_game().turn.active_player
        for seed in range(12)
    }

    assert picks == {"alice", "bob"}
    first = match(seed=5, random_first_player=True).start_game().turn
    again = match(seed=5, random_first_player=True).start_game().turn
    assert first is not None and again is not None
    assert first.active_player == again.active_player


def test_the_loser_of_the_previous_game_chooses_and_plays_first():
    """CR 103.1: in games after the first, the loser of the previous game chooses."""
    series = match()
    series.start_game().end_with_winner("alice")

    assert series.chooser_for_next_game() == "bob"

    second = series.start_game()

    assert second.turn is not None
    assert second.turn.active_player == "bob"
    assert series.first_players == ["alice", "bob"]
    assert series.choosers == [None, "bob"]


def test_the_loser_may_choose_to_go_second():
    """The choice is the loser's, and it is not always to play first."""
    series = match()
    series.start_game().end_with_winner("alice")

    second = series.start_game(on_the_play="alice")

    assert second.turn is not None
    assert second.turn.active_player == "alice"
    assert series.choosers == [None, "bob"]


def test_game_three_follows_the_loser_of_game_two():
    series = match()
    series.start_game().end_with_winner("alice")
    series.start_game().end_with_winner("bob")

    third = series.start_game()

    assert third.turn is not None
    assert third.turn.active_player == "alice"
    assert series.first_players == ["alice", "bob", "alice"]


def test_the_starting_player_is_first_in_the_game_and_the_others_keep_their_order():
    series = match()
    series.start_game().end_with_winner("alice")

    second = series.start_game()

    assert [player.username for player in second.players] == ["bob", "alice"]
    assert len(second.player("alice").hand) == 7


def test_an_unknown_starting_player_is_refused():
    with pytest.raises(KeyError):
        match().start_game(on_the_play="carol")


# -- decks and libraries that run out -------------------------------------


def test_a_five_card_library_deals_what_it_has_and_records_the_failed_draw():
    """CR 103.5 draws seven; a library of five cannot, and the player is dead on upkeep."""
    tiny = deck({"Mountain": 5}, limits=DeckLimits.unlimited())
    player = Player(username="alice").load_deck(tiny, card)

    hand = player.draw_opening_hand()

    assert len(hand) == 5
    assert player.library == []
    assert player.tried_to_draw_from_empty_library


def test_an_empty_library_deals_no_opening_hand_at_all():
    player = Player(username="alice").load_deck(Deck(limits=DeckLimits.unlimited()), card)

    assert player.draw_opening_hand() == []
    assert player.tried_to_draw_from_empty_library


def test_a_player_who_could_not_draw_their_opening_hand_loses():
    alice = Player(username="alice").load_deck(
        deck({"Mountain": 5}, limits=DeckLimits.unlimited()), card
    )
    bob = Player(username="bob").load_deck(deck(BURN_SIXTY), card)
    alice.draw_opening_hand()
    bob.draw_opening_hand()

    game = Game(players=[alice, bob], schema_version=Game.CURRENT_SCHEMA_VERSION)
    game.check_state_based_actions()

    assert game.winner == "bob"


def test_an_illegal_deck_cannot_be_registered_for_a_match():
    """A five-of is caught when the deck is handed in, not mid-game."""
    series = Match(players=[Player(username="alice"), Player(username="bob")], card_resolver=card)

    with pytest.raises(ValueError, match="5 copies of Lightning Bolt"):
        series.register_deck("alice", deck(dict(BURN_SIXTY) | {"Lightning Bolt": 5}))


def test_a_deck_can_be_registered_for_a_format_the_limits_do_not_describe():
    """The limits travel with the decklist, so an odd format is not a special case."""
    series = Match(players=[Player(username="alice"), Player(username="bob")], card_resolver=card)
    sealed = Deck(mainboard={"Forest": 20, "Grizzly Bears": 20}, limits=DeckLimits.limited())

    series.register_deck("alice", sealed)
    game = series.start_game()

    assert len(game.player("alice").hand) == 7
    assert len(game.player("alice").library) == 33


def test_registering_a_deck_for_someone_who_is_not_in_the_match_is_refused():
    with pytest.raises(KeyError, match="no player named carol"):
        match().register_deck("carol", deck(BURN_SIXTY))
