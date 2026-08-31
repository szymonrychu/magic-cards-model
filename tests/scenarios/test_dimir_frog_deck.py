"""Dimir frog, played through the real path: register, shuffle, deal (CR 103).

The list is a registered tournament decklist - pilot SizzleSkeleton, event of
2026-08-30, source deck videre-58656338 - not an aggregate, and every name
resolves to a real Scryfall printing in `tests/fixtures/cards`. It is the
archetype at roughly 1.6% of the Modern metagame, and this file is the smoke
test that the sixty and the fifteen it registered are the sixty and fifteen the
engine loads.

Rules used, all looked up this session:

- CR 100.2a - a constructed deck has a minimum deck size of 60 cards, and no
  more than four of any card that is not a basic land.
- CR 100.4a - a constructed sideboard is at most fifteen cards, and the
  four-card limit applies to the combined deck and sideboard.
- CR 103.2a / CR 400.11a - the sideboard is set aside before the shuffle, which
  is what puts it outside the game.
- CR 103.3 - each player shuffles their deck into a random order.
- CR 401.1 - when a game begins, each player's deck becomes their library.
- CR 402.1 - at the beginning of the game each player draws a number of cards
  equal to their starting hand size, normally seven.
- CR 402.2 - maximum hand size is normally seven.
"""

from magic_cards_model.models import Deck, Match, Player, Zone
from tests.cards import card

#: Mainboard, 60 cards. videre-58656338, SizzleSkeleton, 2026-08-30.
DIMIR_FROG_MAIN = {
    "Verdant Catacombs": 2,
    "Thoughtseize": 4,
    "Undercity Sewers": 2,
    "Spell Snare": 2,
    "Tamiyo, Inquisitive Student": 2,
    "Swamp": 1,
    "Subtlety": 3,
    "Scalding Tarn": 2,
    "Sink into Stupor": 2,
    "Sheoldred's Edict": 2,
    "Psychic Frog": 4,
    "Quantum Riddler": 4,
    "Orcish Bowmasters": 2,
    "Polluted Delta": 4,
    "Otawara, Soaring City": 1,
    "Murktide Regent": 1,
    "Lórien Revealed": 1,
    "Kaito, Bane of Nightmares": 1,
    "Island": 2,
    "Force of Negation": 3,
    "Fatal Push": 4,
    "Drown in the Loch": 1,
    "Darkslick Shores": 2,
    "Counterspell": 2,
    "Cling to Dust": 1,
    "Preordain": 2,
    "Watery Grave": 3,
}

#: Sideboard, 15 cards. Spell Snare is the one card on both boards: two main
#: plus one here is three, inside CR 100.4a's combined four-card limit.
DIMIR_FROG_SIDE = {
    "Toxic Deluge": 2,
    "Spell Snare": 1,
    "Nihil Spellbomb": 1,
    "Mystical Dispute": 2,
    "Engineered Explosives": 2,
    "Consign to Memory": 4,
    "Harbinger of the Seas": 3,
}


def dimir_frog() -> Deck:
    return Deck(mainboard=dict(DIMIR_FROG_MAIN), sideboard=dict(DIMIR_FROG_SIDE))


def match(seed: int | str = 1) -> Match:
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", dimir_frog())
    series.register_deck("bob", Deck(mainboard=dict(DIMIR_FROG_MAIN)))
    return series


# -- the list itself (CR 100.2a, CR 100.4a) -------------------------------


def test_the_registered_list_is_sixty_and_fifteen():
    """CR 100.2a minimum deck size, CR 100.4a sideboard maximum."""
    deck = dimir_frog()

    assert deck.mainboard_size == 60
    assert deck.sideboard_size == 15


def test_the_list_is_legal_against_the_real_printings():
    """CR 100.2a / CR 100.4a, judged off the printings rather than the names.

    Spell Snare is the case that matters: two main and one board is three
    copies across the combined deck and sideboard, which CR 100.4a allows.
    """
    deck = dimir_frog()

    assert deck.problems(card) == []
    assert deck.is_legal(card)
    assert deck.total_copies("Spell Snare") == 3


def test_every_name_on_the_list_resolves_to_a_real_printing():
    """No hand-written card data: each of the 33 names is a Scryfall fixture."""
    names = set(DIMIR_FROG_MAIN) | set(DIMIR_FROG_SIDE)

    assert len(names) == 33
    for name in sorted(names):
        printing = card(name)
        assert printing.name.split("//")[0].strip() == name


# -- starting a game with it (CR 103) -------------------------------------


def test_the_deck_becomes_a_library_and_deals_seven():
    """CR 401.1 the deck becomes the library; CR 402.1 draws the starting seven."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert len(alice.hand) + len(alice.library) == 60
    assert all(state.zone is Zone.HAND for state in alice.hand)
    assert all(state.zone is Zone.LIBRARY for state in alice.library)


def test_the_opening_hand_is_cards_off_this_list():
    """Nothing is dealt that was not registered - a shuffle moves real cards."""
    game = match().start_game()
    alice = game.player("alice")

    for state in alice.hand:
        assert state.card.name.split("//")[0].strip() in DIMIR_FROG_MAIN


def test_the_sideboard_is_set_aside_and_not_in_the_library():
    """CR 103.2a: the sideboard is set aside before the shuffle (CR 400.11a).

    Harbinger of the Seas is board-only, so no copy of it may be anywhere in
    the game; Spell Snare is on both boards, so exactly the two mainboard
    copies are in the library plus hand and the third is not.
    """
    game = match().start_game()
    alice = game.player("alice")

    in_game = [*alice.library, *alice.hand]
    assert len(alice.sideboard) == 15
    assert not [s for s in in_game if s.card.name == "Harbinger of the Seas"]
    assert len([s for s in in_game if s.card.name == "Spell Snare"]) == 2


def test_the_starting_hand_size_is_seven():
    """CR 402.1 draws the starting hand size; CR 402.2 makes it normally seven."""
    game = match().start_game()

    assert game.player("alice").starting_hand_size == 7
    assert game.player("alice").maximum_hand_size == 7


def test_two_seeds_shuffle_the_same_sixty_differently():
    """CR 103.3: the shuffle is a random order, and this list is not staged.

    Same registered sixty, two match seeds, two different libraries - the deck
    reaches the game through the real shuffle rather than in list order.
    """
    one = match(seed=1).start_game().player("alice")
    two = match(seed=2).start_game().player("alice")

    order_one = [state.card.name for state in [*one.hand, *one.library]]
    order_two = [state.card.name for state in [*two.hand, *two.library]]

    assert sorted(order_one) == sorted(order_two)
    assert order_one != order_two
