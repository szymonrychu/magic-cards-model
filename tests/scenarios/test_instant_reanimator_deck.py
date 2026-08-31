"""The Modern "instant reanimator" deck, registered and started for real.

A smoke scenario for one whole tournament decklist: it registers through
`Match.register_deck` (which runs `Deck.check_legality`), starts a game, and
checks the zones the rules put the cards in.

The rules this asserts, each looked up this session with
`knowledge_search(type="rules")`:

- CR 100.2a: "In constructed play ... each deck has a minimum deck size of 60
  cards."
- CR 100.4a: "In constructed play, a sideboard may contain no more than fifteen
  cards. The four-card limit (see rule 100.2a) applies to the combined deck and
  sideboard."
- CR 401.1: "When a game begins, each player's deck becomes their library."
- CR 103.3: "After the starting player has been determined ... each player
  shuffles their deck so that the cards are in a random order."
- CR 103.5: "Each player draws a number of cards equal to their starting hand
  size, which is normally seven."
- CR 402.1: "At the beginning of the game, each player draws a number of cards
  equal to their starting hand size."

The decklist is pepeteam's "instant reanimator", played 2026-08-29 (source deck
videre-58655435). It was pulled with `statistics_decks(format="modern",
archetype_name="instant reanimator", date_from="2026-06-01",
include_cards="full")` and every one of its 34 distinct cards was verified
Modern-legal with `resolve_cards(format="modern", fields="legality")` before
being written here - all 34 came back `legal`.

A second list from the same query (Asa_Akira, 2026-08-28) was rejected because
it contains "Kavaero, Mind-Bitten", which `resolve_cards` returns in
`not_found`, so no real printing could be fetched for it.

What this file does *not* claim: that the deck plays correctly. Most of its
cards have no effect wired up - see `docs/deck-gaps/instant-reanimator.md`.
"""

from magic_cards_model.models import Deck, Match, Player, Zone
from tests.cards import card

#: pepeteam, 2026-08-29, source deck videre-58655435. 60 cards.
INSTANT_REANIMATOR_MAIN = {
    "Breeding Pool": 1,
    "Flooded Strand": 4,
    "Godless Shrine": 1,
    "Hallowed Fountain": 1,
    "Island": 1,
    "Marsh Flats": 3,
    "Meticulous Archive": 1,
    "Plains": 1,
    "Polluted Delta": 4,
    "Shadowy Backstreet": 1,
    "Swamp": 1,
    "Undercity Sewers": 1,
    "Watery Grave": 1,
    "Atraxa, Grand Unifier": 4,
    "Fallaji Archaeologist": 3,
    "Griselbrand": 2,
    "Psychic Frog": 4,
    "Quantum Riddler": 1,
    "Solitude": 4,
    "Ephemerate": 4,
    "Faithful Mending": 2,
    "Force of Negation": 2,
    "Goryo's Vengeance": 4,
    "March of Otherworldly Light": 2,
    "Otherworldly Gaze": 2,
    "Prismatic Ending": 1,
    "Spell Snare": 1,
    "Thoughtseize": 3,
}

#: The same registration's sideboard. 15 cards.
INSTANT_REANIMATOR_SIDE = {
    "Clarion Conqueror": 2,
    "Consign to Memory": 3,
    "Mystical Dispute": 3,
    "Quantum Riddler": 2,
    "Surgical Extraction": 1,
    "Teferi, Time Raveler": 1,
    "Wrath of the Skies": 3,
}


def instant_reanimator() -> Deck:
    return Deck(mainboard=INSTANT_REANIMATOR_MAIN, sideboard=INSTANT_REANIMATOR_SIDE)


def match(seed: int | str = "reanimator") -> Match:
    """A two-player match with the registered list in both seats."""
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", instant_reanimator())
    series.register_deck("bob", instant_reanimator())
    return series


def test_the_registered_list_is_sixty_and_fifteen() -> None:
    """CR 100.2a's minimum deck size and CR 100.4a's sideboard maximum."""
    deck = instant_reanimator()

    assert sum(INSTANT_REANIMATOR_MAIN.values()) == 60
    assert sum(INSTANT_REANIMATOR_SIDE.values()) == 15
    # `check_legality` is what `register_deck` calls; it raises on a violation.
    assert deck.check_legality(card) is deck


def test_no_card_exceeds_the_four_copy_limit_across_deck_and_sideboard() -> None:
    """CR 100.4a: "The four-card limit ... applies to the combined deck and sideboard."

    Quantum Riddler is the card that makes this worth asserting on this list:
    one main and two side, four total across the registration would be the cap.
    """
    combined: dict[str, int] = dict(INSTANT_REANIMATOR_MAIN)
    for name, count in INSTANT_REANIMATOR_SIDE.items():
        combined[name] = combined.get(name, 0) + count

    basics = {"Island", "Plains", "Swamp"}
    over = {name: count for name, count in combined.items() if count > 4 and name not in basics}
    assert over == {}
    assert combined["Quantum Riddler"] == 3


def test_starting_a_game_deals_seven_and_leaves_the_rest_in_the_library() -> None:
    """CR 401.1, CR 103.5: the deck becomes the library, then seven are drawn."""
    game = match().start_game()

    for player in game.players:
        assert len(player.hand) == 7  # CR 103.5 / CR 402.1
        assert len(player.library) == 53  # 60 - 7, CR 401.1
        assert all(state.zone is Zone.HAND for state in player.hand)
        assert all(state.zone is Zone.LIBRARY for state in player.library)


def test_the_sideboard_stays_out_of_the_library() -> None:
    """CR 100.4: the sideboard is "additional cards", not part of the deck.

    So the 75 registered cards exist, but only 60 of them are in the library
    and hand once the game begins.
    """
    game = match().start_game()

    for player in game.players:
        assert len(player.sideboard) == 15
        assert all(state.zone is Zone.SIDEBOARD for state in player.sideboard)
        assert len(player.hand) + len(player.library) == 60


def test_every_card_on_the_list_resolves_to_a_real_printing() -> None:
    """No hand-written card data: each name is a Scryfall printing in the pool."""
    names = set(INSTANT_REANIMATOR_MAIN) | set(INSTANT_REANIMATOR_SIDE)

    for name in sorted(names):
        printing = card(name)
        assert printing.name == name
        assert printing.type_line


def test_shuffling_puts_the_library_in_a_different_order_per_seed() -> None:
    """CR 103.3: the deck is shuffled "so that the cards are in a random order"."""
    one = [state.name for state in match(seed="one").start_game().players[0].library]
    two = [state.name for state in match(seed="two").start_game().players[0].library]

    assert one != two
    assert sorted(one) != []
