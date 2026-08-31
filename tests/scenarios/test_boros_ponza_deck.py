"""Scenario: the Modern boros ponza decklist loads and deals a real game.

A smoke test for one archetype's sixty, not for a mechanic. It proves the list
in `magic-cards-model-api/decks/boros_ponza.txt` resolves card-for-card against
the printings in `tests/fixtures/cards`, passes `Deck.check_legality`, and can
be dealt through the ordinary `Match.start_game` path.

The list is a real registered deck: pilot **Zompatanfo**, tournament date
**2026-08-30**, source deck `videre-58656392`, pulled with
`statistics_decks(format="modern", archetype_name="boros ponza")`. Every one of
its 25 distinct cards was checked with `resolve_cards(format="modern",
fields="legality")` and came back `legal`.

CR, all verified with `knowledge_search(type="rules")` before being written here:

- 103.2a - sideboard cards are set aside; what remains is the deck.
- 103.3 - each player shuffles their deck into a random order.
- 103.4 - each player begins the game with a starting life total of 20.
- 103.5 - each player draws a number of cards equal to their starting hand size,
  normally seven.
- 401.1 - when a game begins, each player's deck becomes their library.

What the deck cannot yet do is not tested here; `docs/deck-gaps/boros-ponza.md`
records the four cards that resolve silently.
"""

from magic_cards_model.models import Deck, Match, Player, Zone
from tests.cards import card

#: Pilot Zompatanfo, tournament date 2026-08-30, source deck videre-58656392.
#: Copied from `magic-cards-model-api/decks/boros_ponza.txt`. Split entries in
#: the source (Solitude 3 + 1) are consolidated; the totals are unchanged.
BOROS_PONZA_MAIN = {
    "Avengers Disassembled": 4,
    "Castle Ardenvale": 1,
    "Cleansing Wildfire": 4,
    "Cori Mountain Monastery": 4,
    "Demolition Field": 4,
    "Erode": 4,
    "Field of Ruin": 4,
    "Galvanic Discharge": 4,
    "High Noon": 2,
    "Mountain": 2,
    "Path to Exile": 4,
    "Plains": 4,
    "Price of Freedom": 4,
    "Rustvale Bridge": 1,
    "Sacred Foundry": 3,
    "Solitude": 4,
    "Sunken Citadel": 3,
    "The Legend of Roku // Avatar Roku": 1,
    "Wrath of the Skies": 3,
}

BOROS_PONZA_SIDE = {
    "High Noon": 2,
    "Kaheera, the Orphanguard": 1,
    "Orim's Chant": 2,
    "Rest in Peace": 2,
    "Rustvale Bridge": 2,
    "Surgical Extraction": 1,
    "The Legend of Roku // Avatar Roku": 1,
    "Wear // Tear": 3,
    "Wrath of God": 1,
}


def ponza() -> Deck:
    return Deck(mainboard=BOROS_PONZA_MAIN, sideboard=BOROS_PONZA_SIDE)


def match(seed: int | str = "ponza") -> Match:
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", ponza())
    series.register_deck("bob", ponza())
    return series


# -- the list itself -------------------------------------------------------


def test_the_registered_list_is_sixty_and_fifteen():
    assert sum(BOROS_PONZA_MAIN.values()) == 60
    assert sum(BOROS_PONZA_SIDE.values()) == 15


def test_no_card_appears_more_than_four_times_across_both_boards():
    """Basic lands are exempt; nothing else in this list is close to the limit."""
    totals: dict[str, int] = {}
    for board in (BOROS_PONZA_MAIN, BOROS_PONZA_SIDE):
        for name, count in board.items():
            totals[name] = totals.get(name, 0) + count

    over = {
        name: count
        for name, count in totals.items()
        if count > 4 and name not in {"Mountain", "Plains"}
    }

    assert over == {}


def test_every_card_in_the_list_resolves_to_a_real_printing():
    """No hand-written json: each name is a fixture in `tests/fixtures/cards`."""
    for name in {*BOROS_PONZA_MAIN, *BOROS_PONZA_SIDE}:
        assert card(name).name == name


def test_the_deck_passes_the_engines_own_legality_check():
    ponza().check_legality(card)


# -- dealing a game with it (CR 103) ---------------------------------------


def test_the_deck_deals_an_opening_hand_of_seven():
    """CR 103.5: a hand equal to the starting hand size, normally seven."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert all(state.zone is Zone.HAND for state in alice.hand)


def test_the_library_is_the_deck_minus_the_opening_hand():
    """CR 401.1: the deck becomes the library; CR 103.5 draws seven off it."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.library) == 53
    assert len(alice.library) + len(alice.hand) == 60
    assert all(state.zone is Zone.LIBRARY for state in alice.library)


def test_the_sideboard_is_set_aside_and_not_shuffled_in():
    """CR 103.2a: sideboard cards are set aside before the deck is the deck."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)
    assert "Wrath of God" not in {state.name for state in alice.library + alice.hand}


def test_the_dealt_sixty_is_the_registered_sixty_card_for_card():
    game = match().start_game()
    alice = game.player("alice")

    # The Legend of Roku is a transforming Saga, so a CardState in the library
    # reports the front face's name while the decklist carries the printed
    # double-faced name. Compare on the front face.
    expected = {name.split(" //")[0]: count for name, count in BOROS_PONZA_MAIN.items()}

    dealt: dict[str, int] = {}
    for state in alice.library + alice.hand:
        dealt[state.name] = dealt.get(state.name, 0) + 1

    assert dealt == expected


def test_every_copy_is_its_own_card():
    """Four Field of Ruin are four cards sharing one printing, not one card."""
    game = match().start_game()
    alice = game.player("alice")

    fields = [s for s in alice.library + alice.hand if s.name == "Field of Ruin"]

    assert len(fields) == 4
    assert len({state.id for state in fields}) == 4


def test_both_players_start_on_twenty_life():
    """CR 103.4: each player begins the game with a starting life total of 20."""
    game = match().start_game()

    assert all(player.life == 20 for player in game.players)


def test_the_shuffle_is_a_shuffle_and_it_replays():
    """CR 103.3: a random order - and off the match seed, the same one twice."""
    first = [state.name for state in match(seed="ponza-a").start_game().player("alice").library]
    again = [state.name for state in match(seed="ponza-a").start_game().player("alice").library]
    other = [state.name for state in match(seed="ponza-b").start_game().player("alice").library]

    assert first == again
    assert first != other
    assert len(first) == 53
    # A shuffled library is not the decklist in registration order: the four
    # Field of Ruin do not sit in one adjacent block.
    positions = [index for index, name in enumerate(first) if name == "Field of Ruin"]
    assert positions != list(range(positions[0], positions[0] + len(positions)))
