"""UW control, start to opening hand: a real Modern list dealt through CR 103.

The list is eclipse4343's uw control from the 2026-08-23 event (source deck
``videre-58651065``), taken verbatim - every count is the one that was
registered, and every name resolves to a real Scryfall printing in
``tests/fixtures/cards``. Modern legality of all thirty-three distinct names
was checked with ``resolve_cards(format="modern", fields="legality")`` before
the list was written down; ``Deck.check_legality`` re-checks the construction
rules the CR owns.

The rules under test are the ones that govern getting a deck into a game:

- CR 100.2a - a constructed deck is at least sixty cards, at most four copies
  of anything that is not a basic land.
- CR 100.4a - a constructed sideboard is at most fifteen cards, and the
  four-copy limit applies to the deck and sideboard combined.
- CR 103.2a - sideboards are set aside before the game begins; CR 400.11a puts
  those cards outside the game.
- CR 103.3 - each player shuffles their deck into a random order.
- CR 103.4 - life totals are set (twenty in a two-player game here).
- CR 103.5 - each player draws a number of cards equal to their starting hand
  size, normally seven.

Nothing here plays a spell. What this deck's spells actually do - and the six
cards that do nothing at all - is measured in ``docs/deck-gaps/uw-control.md``.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Deck, Game, Match, Player, Zone
from tests.cards import card

#: eclipse4343, uw control, 2026-08-23, source deck videre-58651065. Sixty
#: cards across twenty-eight rows, no row repeated - the list summed to sixty
#: as registered and was not merged or repaired.
UW_CONTROL_MAIN = {
    "Hallowed Fountain": 2,
    "Orim's Chant": 4,
    "Arid Mesa": 3,
    "Supreme Verdict": 1,
    "Solitude": 3,
    "Tune the Narrative": 2,
    "Narset, Parter of Veils": 3,
    "Day's Undoing": 1,
    "Geier Reach Sanitarium": 1,
    "Wrath of the Skies": 4,
    "Prismatic Ending": 3,
    "Scalding Tarn": 2,
    "March of Otherworldly Light": 1,
    "Consult the Star Charts": 3,
    "Plains": 2,
    "Mystic Gate": 2,
    "Spell Snare": 2,
    "Monumental Henge": 1,
    "Counterspell": 4,
    "Hall of Storm Giants": 1,
    "Watery Grave": 1,
    "Thundering Falls": 1,
    "Flooded Strand": 4,
    "Isochron Scepter": 1,
    "Island": 2,
    "The Wandering Emperor": 1,
    "Teferi, Time Raveler": 3,
    "Meticulous Archive": 2,
}

#: The fifteen-card sideboard as registered. Supreme Verdict and Isochron
#: Scepter also appear in the mainboard, which is what makes CR 100.4a's
#: combined four-copy limit worth asserting on this list rather than a
#: constructed one.
UW_CONTROL_SIDE = {
    "Supreme Verdict": 1,
    "Kaheera, the Orphanguard": 1,
    "Mystical Dispute": 4,
    "Consign to Memory": 4,
    "Rest in Peace": 2,
    "High Noon": 2,
    "Isochron Scepter": 1,
}

#: A second real list to sit across the table, so the game being started is a
#: real two-player game rather than one deck and an empty seat. Burn is the
#: pool's own long-standing construction from `test_starting_a_game.py`.
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


def uw_control() -> Deck:
    return Deck(mainboard=dict(UW_CONTROL_MAIN), sideboard=dict(UW_CONTROL_SIDE))


def match(seed: int | str = "uw-control") -> Match:
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", uw_control())
    series.register_deck("bob", Deck(mainboard=dict(OPPOSING_SIXTY)))
    return series


def start() -> Game:
    return match().start_game()


# -- the list itself (CR 100.2a, 100.4a) -----------------------------------


def test_the_registered_list_is_sixty_and_fifteen():
    """CR 100.2a, CR 100.4a: the counts as registered, not as reconstructed."""
    deck = uw_control()

    assert deck.mainboard_size == 60
    assert sum(UW_CONTROL_SIDE.values()) == 15


def test_the_list_is_legal_against_the_real_printings():
    """CR 100.2a's four-copy limit read off each printing, not off the name."""
    deck = uw_control()

    assert deck.problems(card) == []
    assert deck.is_legal(card)
    deck.check_legality(card)


def test_the_copy_limit_spans_the_two_boards():
    """CR 100.4a: Supreme Verdict is 1 + 1 and Isochron Scepter is 1 + 1."""
    deck = uw_control()

    assert deck.total_copies("Supreme Verdict") == 2
    assert deck.total_copies("Isochron Scepter") == 2


def test_only_the_basics_are_over_four_free():
    """The two basics here are the only names CR 100.2a exempts, and neither
    is actually over four - so every count in the list is inside the limit on
    its own merits.

    Read off the `basic` supertype rather than "has any supertype": this list
    carries four legendary permanents, and legendary is a supertype that
    exempts nothing.
    """
    supertyped = {name for name in UW_CONTROL_MAIN if card(name).supertypes}
    basics = {
        name
        for name in UW_CONTROL_MAIN
        if any(str(s).lower().endswith("basic") for s in card(name).supertypes)
    }

    assert basics == {"Plains", "Island"}
    assert supertyped - basics == {
        "Geier Reach Sanitarium",
        "Narset, Parter of Veils",
        "Teferi, Time Raveler",
        "The Wandering Emperor",
    }
    assert max(UW_CONTROL_MAIN.values()) == 4


# -- dealing the game (CR 103.2a - 103.5) ----------------------------------


def test_the_opening_hand_is_seven_and_the_library_is_fifty_three():
    """CR 103.5: seven cards, drawn from the sixty that were shuffled."""
    alice = start().player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert len(alice.hand) + len(alice.library) == 60
    assert all(state.zone is Zone.HAND for state in alice.hand)


def test_every_card_dealt_comes_from_this_decklist():
    """A drawn card is a real printing of a name that was registered."""
    alice = start().player("alice")

    assert all(state.card.name in UW_CONTROL_MAIN for state in alice.hand + alice.library)


def test_the_whole_sixty_is_present_card_for_card():
    """CR 103.3 shuffles the deck; it does not lose or duplicate any of it."""
    alice = start().player("alice")

    dealt: dict[str, int] = {}
    for state in alice.hand + alice.library:
        dealt[state.card.name] = dealt.get(state.card.name, 0) + 1

    assert dealt == UW_CONTROL_MAIN
    assert len({state.id for state in alice.hand + alice.library}) == 60


def test_the_sideboard_is_set_aside_and_never_shuffled_in():
    """CR 103.2a, CR 400.11a: fifteen cards outside the game."""
    alice = start().player("alice")

    assert len(alice.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)
    assert "Mystical Dispute" not in {state.name for state in alice.library + alice.hand}
    assert "Kaheera, the Orphanguard" not in {state.name for state in alice.library + alice.hand}


def test_the_mainboard_copy_of_a_sideboard_card_is_still_in_the_deck():
    """Supreme Verdict is 1 main and 1 side: setting the sideboard aside must
    not take the mainboard copy with it."""
    alice = start().player("alice")

    in_deck = [s for s in alice.library + alice.hand if s.name == "Supreme Verdict"]
    in_side = [s for s in alice.sideboard if s.name == "Supreme Verdict"]

    assert len(in_deck) == 1
    assert len(in_side) == 1


def test_life_totals_and_the_first_step():
    """CR 103.4: life totals are set before the first turn begins."""
    game = start()

    assert game.turn is not None
    # CR 103.5 first: a dealt game rests in the mulligan step, before any turn.
    assert game.turn.step is Step.MULLIGAN
    assert game.turn.turn_number == 0

    game.settle_pregame()

    # CR 103.8: the starting player takes their first turn, which begins at untap.
    assert game.turn.step is Step.UNTAP
    assert all(player.life == 20 for player in game.players)


def test_the_same_seed_deals_the_same_opening_hand():
    """CR 103.3's shuffle is random, but the seed makes it reproducible."""
    first = [state.name for state in match("uw-1").start_game().player("alice").hand]
    second = [state.name for state in match("uw-1").start_game().player("alice").hand]
    other = [state.name for state in match("uw-2").start_game().player("alice").hand]

    assert first == second
    assert first != other
