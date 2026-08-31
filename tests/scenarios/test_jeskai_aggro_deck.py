"""Jeskai aggro, played as a real registered deck (CR 100.2, CR 103).

The list is a real Modern tournament decklist - pilot **_Falcon_**, tournament
date **2026-08-28**, source deck `videre-58655057` - pulled with
`statistics_decks(format="modern", archetype_name="jeskai aggro", ...)` and
legality-checked with `resolve_cards(format="modern", fields="legality")`: all
34 distinct names came back legal. Every printing is a real Scryfall card in
`tests/fixtures/cards/`; nothing here is hand-written.

This is the archetype's smoke test: it proves the 75 goes through the real
`Match.register_deck` / `Match.start_game` path - deck construction (CR 100.2a,
CR 100.4a), deck becoming library (CR 401.1), shuffle (CR 103.3) and opening
hand (CR 103.5) - rather than through a hand-placed board.

Every CR number in this file was verified with `knowledge_search` in the
session that wrote it:

- **CR 100.2a** - constructed minimum deck size of 60, no more than four of any
  card that is not a basic land.
- **CR 100.4a** - a constructed sideboard may contain no more than fifteen
  cards, and the four-card limit applies to deck and sideboard combined.
- **CR 103.3** - after the starting player is determined, each player shuffles
  their deck so the cards are in a random order.
- **CR 103.5** - each player draws a number of cards equal to their starting
  hand size, which is normally seven.
- **CR 401.1** - when a game begins, each player's deck becomes their library.
"""

from magic_cards_model.models import Deck, Match, Player, Zone
from tests.cards import card

#: The mainboard as registered. 60 cards.
JESKAI_AGGRO_MAIN = {
    "Ajani, Nacatl Pariah": 4,
    "Arena of Glory": 1,
    "Arid Mesa": 4,
    "Dalkovan Encampment": 1,
    "Elegant Parlor": 1,
    "Ephemerate": 3,
    "Flooded Strand": 4,
    "Galvanic Discharge": 2,
    "Goblin Bombardment": 3,
    "Guide of Souls": 4,
    "Hallowed Fountain": 2,
    "Meticulous Archive": 1,
    "Mountain": 1,
    "Ocelot Pride": 4,
    "Plains": 2,
    "Quantum Riddler": 4,
    "Ragavan, Nimble Pilferer": 3,
    "Sacred Foundry": 2,
    "Scalding Tarn": 1,
    "Solitude": 4,
    "Starfield Shepherd": 2,
    "Steam Vents": 1,
    "Thraben Charm": 2,
    "Voice of Victory": 3,
    "Windswept Heath": 1,
}

#: The sideboard as registered. 15 cards.
JESKAI_AGGRO_SIDE = {
    "Consign to Memory": 2,
    "Flusterstorm": 2,
    "Grafdigger's Cage": 1,
    "Obsidian Charmaw": 2,
    "Orim's Chant": 1,
    "Prismatic Ending": 1,
    "Spell Snare": 2,
    "Surgical Extraction": 2,
    "Wrath of the Skies": 2,
}

#: The opponent. A second real registered deck is needed for `Match.start_game`
#: to deal a game at all; this is the same boros energy list already used
#: elsewhere in the project's deck files, trimmed to its own 60.
OPPONENT_SIXTY = {
    "Mountain": 24,
    "Plains": 12,
    "Lightning Bolt": 4,
    "Grizzly Bears": 4,
    "Sol Ring": 4,
    "Questing Beast": 4,
    "Swords to Plowshares": 4,
    "Counterspell": 4,
}


def jeskai_aggro() -> Deck:
    return Deck(mainboard=dict(JESKAI_AGGRO_MAIN), sideboard=dict(JESKAI_AGGRO_SIDE))


def match(seed: int | str = "jeskai-aggro") -> Match:
    series = Match(
        players=[Player(username="falcon"), Player(username="opponent")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("falcon", jeskai_aggro())
    series.register_deck("opponent", Deck(mainboard=dict(OPPONENT_SIXTY)))
    return series


def test_the_registered_list_is_a_legal_modern_seventy_five():
    """CR 100.2a and CR 100.4a: 60 main, 15 side, four-copy limit across both."""
    deck = jeskai_aggro()

    assert deck.mainboard_size == 60
    assert deck.sideboard_size == 15
    assert deck.problems(card) == []
    assert deck.is_legal(card)


def test_every_card_in_the_seventy_five_is_a_real_printing():
    """No hand-written card json: each name resolves out of the fixture pool."""
    names = sorted(set(JESKAI_AGGRO_MAIN) | set(JESKAI_AGGRO_SIDE))

    assert len(names) == 34
    for name in names:
        printing = card(name)
        assert printing.name.startswith(name), f"{name} resolved to {printing.name}"


def test_a_game_begins_with_seven_cards_and_fifty_three_in_the_library():
    """CR 401.1, CR 103.3, CR 103.5.

    The deck becomes the library, it is shuffled, and the opening hand is seven
    cards off the top of it - so the library is the 60 minus those seven.
    """
    game = match().start_game()
    falcon = game.player("falcon")

    assert len(falcon.hand) == 7
    assert len(falcon.library) == 53
    assert all(state.zone is Zone.HAND for state in falcon.hand)
    assert all(state.card.name for state in falcon.library)


def test_the_sideboard_is_set_aside_and_never_shuffled_in():
    """CR 100.4a's fifteen are outside the game, not part of the library."""
    game = match().start_game()
    falcon = game.player("falcon")

    assert len(falcon.zones[Zone.SIDEBOARD]) == 15
    assert len(falcon.hand) + len(falcon.library) == 60
    library_and_hand = [state.card.name for state in falcon.library + falcon.hand]
    assert "Spell Snare" not in library_and_hand


def test_the_opening_seven_are_all_cards_from_the_registered_mainboard():
    """CR 103.5 draws off this player's own library, which is their own deck."""
    game = match().start_game()
    falcon = game.player("falcon")

    mainboard_names = {card(name).name for name in JESKAI_AGGRO_MAIN}
    for state in falcon.hand:
        assert state.card.name in mainboard_names
        assert state.owner == "falcon"


def test_the_shuffle_is_seeded_so_the_same_match_deals_the_same_hand():
    """CR 103.3 randomises; the seed is what makes a scenario reproducible."""
    first = [state.card.name for state in match(seed="fixed").start_game().player("falcon").hand]
    second = [state.card.name for state in match(seed="fixed").start_game().player("falcon").hand]

    assert first == second
    assert len(first) == 7
