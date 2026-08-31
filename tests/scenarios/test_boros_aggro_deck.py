"""Boros aggro (Modern, 1.8% of the metagame) as a real, playable deck.

The list is a registered tournament decklist - pilot AeonLock, 2026-08-30,
source deck videre-58656372 - pulled with `statistics_decks(format="modern",
archetype_name="boros aggro")` and legality-checked against Modern with
`resolve_cards(..., format="modern", fields="legality")`. It is duplicated in
`magic-cards-model-api/decks/boros_aggro.txt`.

This is the smoke test for that list: sixty real printings shuffle, deal, and
leave the game in the state CR 103 describes.

- CR 100.2a: a constructed deck has a minimum deck size of 60 cards, and no
  more than four of any card that is not a basic land.
- CR 100.4a: a constructed sideboard may contain no more than fifteen cards,
  and the four-card limit applies to the combined deck and sideboard.
- CR 401.1: when a game begins, each player's deck becomes their library.
- CR 103.3: each player shuffles their deck so the cards are in a random order.
- CR 103.5: each player draws a number of cards equal to their starting hand
  size, which is normally seven.

Card names are the engine's printed names, so the two double-faced cards and
the one split card carry both faces: `card()` in `tests/cards.py` indexes a
multifaced printing under its front face as well, which is how the decklist
rows below resolve.
"""

from magic_cards_model.models import Deck, Match, Player, Zone
from tests.cards import card

#: Mainboard, 60 cards. Every row is one row of the registered list.
BOROS_AGGRO_MAIN = {
    "Ajani, Nacatl Pariah": 4,
    "Arid Mesa": 4,
    "Belladonna Took": 1,
    "Blood Moon": 2,
    "Dalkovan Encampment": 1,
    "Elegant Parlor": 2,
    "Flooded Strand": 4,
    "Galvanic Discharge": 4,
    "Goblin Bombardment": 3,
    "Guide of Souls": 4,
    "Marsh Flats": 3,
    "March of Otherworldly Light": 1,
    "Mountain": 1,
    "Ocelot Pride": 4,
    "Plains": 2,
    "Ragavan, Nimble Pilferer": 4,
    "Ranger-Captain of Eos": 2,
    "Sacred Foundry": 3,
    "Seasoned Pyromancer": 3,
    "Solitude": 2,
    "Sunbaked Canyon": 1,
    "Thraben Charm": 2,
    "Voice of Victory": 2,
    "Witch Enchanter": 1,
}

#: Sideboard, 15 cards.
BOROS_AGGRO_SIDE = {
    "Celestial Purge": 1,
    "Clarion Conqueror": 1,
    "Containment Priest": 1,
    "High Noon": 2,
    "Obsidian Charmaw": 2,
    "Rest in Peace": 1,
    "Surgical Extraction": 1,
    "Vexing Bauble": 2,
    "Wear // Tear": 1,
    "The Legend of Roku": 1,
    "Wrath of the Skies": 2,
}


def boros_aggro() -> Deck:
    return Deck(mainboard=dict(BOROS_AGGRO_MAIN), sideboard=dict(BOROS_AGGRO_SIDE))


def match(seed: int | str = "boros-aggro") -> Match:
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", boros_aggro())
    series.register_deck("bob", boros_aggro())
    return series


# -- the list itself (CR 100.2a, CR 100.4a) --------------------------------


def test_every_card_in_the_list_is_a_real_printing():
    """No hand-written card data: each row resolves in the fixture pool."""
    for name in list(BOROS_AGGRO_MAIN) + list(BOROS_AGGRO_SIDE):
        assert card(name).name


def test_the_list_is_a_legal_sixty_fifteen():
    """CR 100.2a and CR 100.4a: 60 main, 15 side, four copies of anything but a
    basic land."""
    deck = boros_aggro()

    assert deck.mainboard_size == 60
    assert deck.sideboard_size == 15
    assert deck.problems(card) == []
    assert deck.is_legal(card)


# -- starting the game (CR 103) --------------------------------------------


def test_the_deck_becomes_a_library_and_deals_seven():
    """CR 401.1, CR 103.5: 60 cards become the library, seven of them are drawn."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert all(state.zone is Zone.HAND for state in alice.hand)
    assert all(state.zone is Zone.LIBRARY for state in alice.library)


def test_the_sideboard_is_set_aside_not_shuffled_in():
    """CR 103.2a: the sideboard is set aside before the deck is shuffled, so no
    sideboard card can be drawn."""
    game = match().start_game()
    alice = game.player("alice")

    drawn_and_undrawn = {state.name for state in alice.hand + alice.library}
    for name in BOROS_AGGRO_SIDE:
        if name in BOROS_AGGRO_MAIN:
            continue
        assert card(name).name not in drawn_and_undrawn


def test_both_players_are_dealt_from_their_own_copy_of_the_list():
    game = match().start_game()

    for username in ("alice", "bob"):
        player = game.player(username)
        assert len(player.hand) == 7
        assert len(player.library) == 53


def test_the_shuffle_is_a_shuffle_not_the_registered_order():
    """CR 103.3: the library is in a random order, so two seeds disagree."""
    first = match(seed="seed-one").start_game().player("alice")
    second = match(seed="seed-two").start_game().player("alice")

    assert [state.name for state in first.library] != [state.name for state in second.library]
    assert sorted(state.name for state in first.hand + first.library) == sorted(
        state.name for state in second.hand + second.library
    )
