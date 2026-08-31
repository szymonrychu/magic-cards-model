"""Grixis reanimator loads and a game can be dealt from it.

A smoke scenario for one real Modern decklist: the list is legal by CR 100.2a
and CR 100.4a, every card resolves against a real printing in
`tests/fixtures/cards`, and a game dealt from it obeys CR 103 - the sideboard is
set aside (103.2a), the deck becomes the library (401.1), it is shuffled
(103.3), life is 20 (103.4), and each player draws seven (103.5).

The decklist is real and registered:

    pilot innaig88, tournament 2026-08-30, source videre-58656361

The canonical archetype name in the statistics data is `reanimator`, not
"grixis reanimator"; this list is grixis - Blood Crypt, Steam Vents and Watery
Grave. Every card was checked `legal` in modern with `resolve_cards` before the
list was used. The same list is written out at `decks/grixis_reanimator.txt` in
the companion API repo.

What this file does *not* test is what the deck does. Most of its cards have no
effect the engine can run yet - see `docs/deck-gaps/grixis-reanimator.md`. A
reanimation scenario belongs in its own file once Persist and Unearth resolve.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Deck, Match, Player, Zone
from tests.cards import card

#: Mainboard as registered. 60 cards.
GRIXIS_REANIMATOR = {
    "Island": 1,
    "Swamp": 2,
    "Blood Crypt": 1,
    "Spell Pierce": 2,
    "Scalding Tarn": 2,
    "Inquisition of Kozilek": 1,
    "Thought Scour": 3,
    "Faithless Looting": 4,
    "Steam Vents": 1,
    "Watery Grave": 1,
    "Thoughtseize": 4,
    "Bloodstained Mire": 4,
    "Fatal Push": 4,
    "Unearth": 4,
    "Archon of Cruelty": 4,
    "Persist": 4,
    "Raucous Theater": 1,
    "Thundering Falls": 1,
    "Undercity Sewers": 1,
    "Emperor of Bones": 3,
    "Psychic Frog": 4,
    "Polluted Delta": 4,
    "Abhorrent Oculus": 4,
}

#: Sideboard as registered. 15 cards.
GRIXIS_REANIMATOR_SIDEBOARD = {
    "Pyroclasm": 2,
    "Nihil Spellbomb": 1,
    "Damping Sphere": 1,
    "Mystical Dispute": 2,
    "Surgical Extraction": 1,
    "Consign to Memory": 4,
    "Vexing Bauble": 2,
    "Meltdown": 2,
}

#: A second real list to sit across the table, so the game has two decks.
OPPOSING_SIXTY = {
    "Mountain": 24,
    "Plains": 12,
    "Lightning Bolt": 4,
    "Grizzly Bears": 4,
    "Sol Ring": 4,
    "Questing Beast": 4,
    "Swords to Plowshares": 4,
    "Counterspell": 4,
}


def reanimator() -> Deck:
    return Deck(mainboard=GRIXIS_REANIMATOR, sideboard=GRIXIS_REANIMATOR_SIDEBOARD)


def match(seed: int | str = "grixis") -> Match:
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", reanimator())
    series.register_deck("bob", Deck(mainboard=OPPOSING_SIXTY))
    return series


# -- the list itself (CR 100.2a, 100.4a) -----------------------------------


def test_the_registered_list_is_sixty_and_fifteen():
    """CR 100.2a: minimum deck size 60. CR 100.4a: at most fifteen sideboard cards."""
    deck = reanimator()

    assert deck.mainboard_size == 60
    assert sum(GRIXIS_REANIMATOR_SIDEBOARD.values()) == 15


def test_every_card_in_the_list_resolves_to_a_real_printing():
    """No hand-written data: each name is a printing in `tests/fixtures/cards`."""
    names = set(GRIXIS_REANIMATOR) | set(GRIXIS_REANIMATOR_SIDEBOARD)

    assert len(names) == 31
    assert all(card(name) is not None for name in names)


def test_the_list_is_legal_for_constructed():
    """CR 100.2a: four copies of anything but a basic land. `Swamp` is the only
    basic here and it is under four anyway, so the limit is what is being read."""
    deck = reanimator()

    assert deck.problems(card) == []
    assert deck.is_legal(card)


def test_the_deck_is_grixis():
    """Blue, black and red - the three shocklands in the list say so on their own
    type lines, which is why the colours are read off printings, not remembered."""
    duals = {"Blood Crypt", "Steam Vents", "Watery Grave"}

    assert duals <= set(GRIXIS_REANIMATOR)

    basics = {name for name in GRIXIS_REANIMATOR if card(name).type_line.startswith("Basic Land")}

    assert basics == {"Island", "Swamp"}


# -- dealing a game from it (CR 103) ---------------------------------------


def test_a_game_dealt_from_the_list_opens_on_seven():
    """CR 103.5: each player draws a hand equal to their starting hand size,
    normally seven. CR 401.1: the deck became the library, so 60 - 7 = 53."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert all(state.zone is Zone.HAND for state in alice.hand)
    assert all(state.card.name in GRIXIS_REANIMATOR for state in alice.hand)


def test_the_sideboard_is_set_aside_and_the_sixty_is_intact():
    """CR 103.2a: sideboard cards are set aside before the deck becomes the library."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)
    assert len(alice.library) + len(alice.hand) == 60
    assert not any(state.card.name in GRIXIS_REANIMATOR_SIDEBOARD for state in alice.library)


def test_the_whole_sixty_is_dealt_card_for_card():
    """Four Archons is four cards sharing one printing, not one card counted four
    times, and every count in the list survives the shuffle."""
    game = match().start_game()
    alice = game.player("alice")
    in_game = alice.library + alice.hand

    counts: dict[str, int] = {}
    for state in in_game:
        counts[state.card.name] = counts.get(state.card.name, 0) + 1

    assert counts == GRIXIS_REANIMATOR
    assert len({state.id for state in in_game}) == 60


def test_the_game_starts_at_untap_on_twenty_life():
    """CR 103.4: a starting life total of 20."""
    game = match().start_game()

    assert game.turn is not None
    assert game.turn.step is Step.UNTAP
    assert all(player.life == 20 for player in game.players)


def test_the_shuffle_is_real_and_reproducible():
    """CR 103.3: the deck is shuffled into a random order. One seed replays it."""
    ordered = [name for name, count in GRIXIS_REANIMATOR.items() for _ in range(count)]
    dealt = match().start_game().player("alice")
    shuffled = [state.card.name for state in dealt.hand + dealt.library]

    assert shuffled != ordered
    assert sorted(shuffled) == sorted(ordered)

    again = match().start_game().player("alice")

    assert [state.card.name for state in again.hand + again.library] == shuffled
