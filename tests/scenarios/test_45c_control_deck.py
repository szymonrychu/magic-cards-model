"""The Modern "45c control" decklist, from registered list to opening hand.

The list is a real registered deck: **pilot albertosd87**, tournament date
**2026-08-28**, source `videre-58655085`. Every name resolves to a real
Scryfall printing in `tests/fixtures/cards/`, and legality was confirmed with
`resolve_cards(format="modern", fields="legality")` before it was written down -
all 37 distinct names came back `legal`.

What this file checks is the CR 103 opening, not a mechanic:

- CR 100.2a: a constructed deck has a minimum deck size of 60 cards, and may
  contain any number of basic land cards but no more than four of any other.
- CR 100.4a: a constructed sideboard may contain no more than fifteen cards,
  and the four-card limit applies to the combined deck and sideboard.
- CR 103.5: each player draws a number of cards equal to their starting hand
  size, which is normally seven.
- CR 103.8a: in a two-player game, the player who plays first skips the draw
  step of their first turn - so the opening hand is the whole of what they
  have seen.

Every CR number above was verified with `knowledge_search(type="rules")` in the
session that wrote this file. In particular CR 103.8a is *not* 103.7.
"""

from magic_cards_model.models import Deck, Match, Player
from tests.cards import card

#: pilot albertosd87, 2026-08-28, source videre-58655085. Sums to 60.
MAINBOARD = {
    "Coiling Oracle": 2,
    "Arid Mesa": 2,
    "Hedge Maze": 1,
    "Omnath, Locus of Creation": 2,
    "Risen Reef": 3,
    "Windswept Heath": 4,
    "Ephemerate": 1,
    "Voice of Resurgence": 2,
    "Flooded Strand": 2,
    "Witch Enchanter": 1,
    "Wooded Foothills": 1,
    "Plains": 1,
    "Indatha Triome": 1,
    "Steam Vents": 1,
    "Temple Garden": 1,
    "Raugrin Triome": 1,
    "Breeding Pool": 1,
    "Sacred Foundry": 1,
    "Stomping Ground": 1,
    "Solitude": 4,
    "Hallowed Fountain": 1,
    "Overgrown Tomb": 1,
    "Forest": 1,
    "Leyline Binding": 4,
    "Renegade Rallier": 3,
    "Quantum Riddler": 4,
    "Birthing Ritual": 4,
    "Starfield Vocalist": 3,
    "Phelia, Exuberant Shepherd": 2,
    "Consign to Memory": 2,
    "Misty Rainforest": 2,
}

#: Sums to 15. Consign to Memory is the one name in both boards (2 + 1 = 3),
#: which CR 100.4a's combined four-card limit allows.
SIDEBOARD = {
    "Consign to Memory": 1,
    "High Noon": 2,
    "Pest Control": 2,
    "Clarion Conqueror": 3,
    "White Orchid Phantom": 2,
    "Prismatic Ending": 2,
    "Endurance": 3,
}


def registered_deck() -> Deck:
    return Deck(mainboard=dict(MAINBOARD), sideboard=dict(SIDEBOARD))


def test_the_registered_list_is_sixty_and_fifteen():
    """CR 100.2a's minimum deck size and CR 100.4a's fifteen-card sideboard."""
    deck = registered_deck()

    assert deck.mainboard_size == 60
    assert deck.sideboard_size == 15


def test_the_registered_list_is_legal():
    """CR 100.2a, 100.4a, checked against the real printings, not the names.

    The copy limit spans both boards (CR 100.4a), which is what makes the
    2 + 1 Consign to Memory split worth checking rather than assuming.
    """
    deck = registered_deck()

    assert deck.problems(card) == []
    assert deck.is_legal(card)


def test_every_name_resolves_to_a_real_printing():
    """No hand-written card data: each name is a Scryfall printing in the pool."""
    for name in {**MAINBOARD, **SIDEBOARD}:
        assert card(name).name


def test_the_opening_hand_is_seven_and_the_library_is_fifty_three():
    """CR 103.5: the starting hand size is normally seven.

    CR 103.8a is why seven is the whole story for the player on the play - they
    skip the draw step of their first turn, so nothing else has been seen yet.
    The sideboard was set aside before the shuffle (CR 103.2a), so all fifteen
    are still outside the game and none of them is in the sixty.
    """
    match = Match(
        players=[Player(username="albertosd87"), Player(username="opponent")],
        decks={"albertosd87": registered_deck()},
        card_resolver=card,
        seed="45c-control",
    )

    game = match.start_game(on_the_play="albertosd87")
    pilot = game.player("albertosd87")

    assert len(pilot.hand) == 7
    assert len(pilot.library) == 53
    assert len(pilot.sideboard) == 15
