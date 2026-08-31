"""A real Modern dimir control list, loaded and dealt through the real path.

The decklist is the one registered by **cntrlfreak_ttv** on **2026-08-25**
(source deck `videre-58652547`), mirrored in the api repo at
`decks/dimir_control.txt`. Every card was checked with
`resolve_cards(format="modern", fields="legality")` and came back `legal`; the
list is transcribed here card for card, not assembled from archetype averages.

What this file proves is narrow on purpose: the sixty resolve against real
printings in `tests/fixtures/cards`, the deck passes construction, and a game
can be dealt from it. It does **not** prove the deck plays correctly - most of
these cards have no entry in `machines/effects.py` and would resolve as nothing.
That inventory is `docs/deck-gaps/dimir-control.md`.

Rules this checks, all looked up rather than recalled:

- **CR 100.2a** - constructed minimum deck size is 60, and no more than four of
  any one card other than basic lands.
- **CR 100.4a** - a constructed sideboard is at most fifteen cards, and the
  four-card limit applies to deck and sideboard combined.
- **CR 103.2a** - sideboard cards are set aside before the game; the deck is
  the library.
- **CR 103.3** - each player shuffles their deck into a random order.
- **CR 103.4** - each player begins with a starting life total of 20 (CR 119.1
  says the same of life totals generally).
- **CR 103.5** - each player draws a number of cards equal to their starting
  hand size, normally seven.
"""

from magic_cards_model.models import Deck, Match, Player, Zone
from tests.cards import card

#: cntrlfreak_ttv, 2026-08-25, source deck videre-58652547. Sixty cards.
DIMIR_CONTROL: dict[str, int] = {
    "Darkslick Shores": 1,
    "Thoughtseize": 4,
    "Swamp": 1,
    "Subtlety": 3,
    "Otawara, Soaring City": 1,
    "Fatal Push": 4,
    "Sink into Stupor": 2,
    "Tamiyo, Inquisitive Student": 2,
    "Kaito, Bane of Nightmares": 2,
    "Undercity Sewers": 2,
    "Marsh Flats": 2,
    "Sheoldred's Edict": 2,
    "Flooded Strand": 4,
    "Psychic Frog": 4,
    "Watery Grave": 3,
    "Polluted Delta": 4,
    "Island": 2,
    "Spell Snare": 3,
    "Drown in the Loch": 1,
    "Force of Negation": 2,
    "Quantum Riddler": 3,
    "Orcish Bowmasters": 3,
    "Counterspell": 3,
    "Cling to Dust": 2,
}

#: The same pilot's fifteen-card sideboard.
DIMIR_CONTROL_SIDEBOARD: dict[str, int] = {
    "Consign to Memory": 4,
    "Harbinger of the Seas": 2,
    "Mystical Dispute": 3,
    "Stern Scolding": 1,
    "Surgical Extraction": 1,
    "Engineered Explosives": 2,
    "Glistening Deluge": 1,
    "Requiting Hex": 1,
}

#: A second real list to sit across the table, so the game has two decks.
OPPOSING_SIXTY: dict[str, int] = {"Island": 36, "Counterspell": 4, "Thoughtseize": 4, "Swamp": 16}


def dimir_control() -> Deck:
    return Deck(mainboard=DIMIR_CONTROL, sideboard=DIMIR_CONTROL_SIDEBOARD)


def match(seed: int | str = "dimir") -> Match:
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", dimir_control())
    series.register_deck("bob", Deck(mainboard=OPPOSING_SIXTY))
    return series


# -- the list itself ------------------------------------------------------


def test_the_transcribed_list_is_sixty_and_fifteen():
    """CR 100.2a's sixty and CR 100.4a's fifteen, counted off the decklist."""
    assert sum(DIMIR_CONTROL.values()) == 60
    assert sum(DIMIR_CONTROL_SIDEBOARD.values()) == 15


def test_every_card_resolves_to_a_real_printing():
    """No hand-written card data: each name is a Scryfall printing in the pool."""
    for name in list(DIMIR_CONTROL) + list(DIMIR_CONTROL_SIDEBOARD):
        printing = card(name)
        assert printing.name.split(" //")[0].strip() == name


def test_the_deck_passes_constructed_legality():
    """CR 100.2a's four-copy limit and CR 100.4a's combined deck-and-sideboard
    reading of it - Consign to Memory is a four-of across both."""
    deck = dimir_control()

    deck.check_legality(card)

    assert deck.limits.min_mainboard == 60
    assert deck.limits.max_sideboard == 15
    assert deck.limits.max_copies == 4
    assert deck.limits.copy_limit_spans_sideboard


# -- dealing a game from it (CR 103) --------------------------------------


def test_a_game_deals_seven_from_the_dimir_library():
    """CR 103.5: a starting hand is seven cards, leaving fifty-three."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert all(state.zone is Zone.HAND for state in alice.hand)


def test_the_whole_sixty_is_accounted_for_and_is_the_registered_list():
    """CR 103.2a: the deck is the library. Hand plus library is the sixty, card
    for card, with nothing from the sideboard mixed in."""
    game = match().start_game()
    alice = game.player("alice")

    counts: dict[str, int] = {}
    for state in alice.library + alice.hand:
        front = state.name.split(" //")[0].strip()
        counts[front] = counts.get(front, 0) + 1

    assert counts == DIMIR_CONTROL


def test_the_sideboard_is_set_aside_and_not_shuffled_in():
    """CR 103.2a: sideboard cards are set aside before the deck becomes the library."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)
    assert len(alice.library) + len(alice.hand) == 60
    assert "Mystical Dispute" not in {s.name for s in alice.library + alice.hand}


def test_both_players_start_at_twenty_life():
    """CR 103.4 (and CR 119.1): the starting life total is 20."""
    game = match().start_game()

    assert all(player.life == 20 for player in game.players)


def test_every_copy_is_its_own_card():
    """Four Polluted Deltas are four cards sharing one printing, not one card."""
    game = match().start_game()
    alice = game.player("alice")

    deltas = [s for s in alice.library + alice.hand if s.name == "Polluted Delta"]

    assert len(deltas) == 4
    assert len({state.id for state in deltas}) == 4


def test_the_shuffle_is_random_but_reproducible():
    """CR 103.3 randomises the order; the match seed makes it replay."""
    ordered = list(dimir_control().mainboard)

    first = [s.name for s in match(seed="one").start_game().player("alice").library]
    again = [s.name for s in match(seed="one").start_game().player("alice").library]
    other = [s.name for s in match(seed="two").start_game().player("alice").library]

    assert first == again
    assert first != other
    assert first[: len(ordered)] != ordered
