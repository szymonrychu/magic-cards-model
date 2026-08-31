"""Izzet prowess, a real Modern decklist, dealt through the real start-of-game path.

The list is the one `magic-cards-model-api/decks/izzet_prowess.txt` holds:
pilot **ratabruta**, tournament date **2026-08-30**, source deck id
**videre-58656391**. Every name in it was checked with
`resolve_cards(format="modern", fields="legality")` in the session that added it
and came back `legal`; the four one-of `Mountain` rows the source printed
separately are consolidated to `3 Mountain` here, which changes no count.

This is a smoke test for the whole path - `Deck` -> `Match.register_deck` ->
`Match.start_game` - not a mechanic file, so what it asserts is CR 100 and
CR 103 arithmetic rather than an interaction:

- CR 100.2a: a constructed deck has a minimum deck size of 60 cards, and no more
  than four of any card with a particular English name other than basic lands.
- CR 100.4a: a constructed sideboard may contain no more than fifteen cards, and
  the four-card limit spans deck and sideboard together.
- CR 103.3: each player shuffles their deck into a random order.
- CR 103.4 / CR 119.1: each player begins with a starting life total of 20.
- CR 103.5: each player draws a number of cards equal to their starting hand
  size, which is normally seven.
- CR 402.1: the hand is where a player holds the cards they have drawn.

The last test is the archetype's own mechanic rather than deck arithmetic:
Monastery Swiftspear's prowess (CR 702.108a - "Whenever you cast a noncreature
spell, this creature gets +1/+1 until end of turn"), driven off this deck's own
Lightning Bolt. `tests/scenarios/test_prowess.py` is the mechanic file; this is
the one assertion that ties the archetype's name to a card from its real list.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import prowess_bonus
from magic_cards_model.models import Deck, Game, Match, Player, Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

#: `decks/izzet_prowess.txt` mainboard, 60 cards.
IZZET_PROWESS_MAIN = {
    "Arid Mesa": 2,
    "Bloodstained Mire": 2,
    "Cori-Steel Cutter": 4,
    "Dragon's Rage Channeler": 4,
    "Expressive Iteration": 4,
    "Fiery Islet": 1,
    "Lava Dart": 4,
    "Lightning Bolt": 4,
    "Mishra's Bauble": 4,
    "Monastery Swiftspear": 4,
    "Mountain": 3,
    "Mutagenic Growth": 4,
    "Preordain": 4,
    "Scalding Tarn": 3,
    "Slickshot Show-Off": 4,
    "Steam Vents": 3,
    "Thundering Falls": 1,
    "Unholy Heat": 1,
    "Violent Urge": 1,
    "Wooded Foothills": 3,
}

#: `decks/izzet_prowess.txt` sideboard, 15 cards.
IZZET_PROWESS_SIDE = {
    "Consign to Memory": 4,
    "End the Festivities": 1,
    "Meltdown": 1,
    "Spell Pierce": 1,
    "Spell Snare": 3,
    "Tormod's Crypt": 2,
    "Unholy Heat": 3,
}


def izzet_prowess() -> Deck:
    return Deck(
        name="Izzet prowess",
        mainboard=dict(IZZET_PROWESS_MAIN),
        sideboard=dict(IZZET_PROWESS_SIDE),
    )


def match(seed: int | str = "izzet-prowess") -> Match:
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", izzet_prowess())
    return series


def start() -> Game:
    return match().start_game()


# -- deck construction (CR 100.2a, CR 100.4a) ------------------------------


def test_the_registered_list_is_a_legal_modern_deck():
    """CR 100.2a and CR 100.4a, enforced by the model rather than by eye."""
    deck = izzet_prowess()

    assert deck.mainboard_size == 60
    assert deck.sideboard_size == 15
    assert deck.check_legality(card) is deck


def test_no_nonbasic_name_exceeds_four_copies_across_deck_and_sideboard():
    """CR 100.4a: the four-card limit spans the deck and the sideboard.

    Unholy Heat is the list's own instance of it - one main, three side.
    """
    deck = izzet_prowess()

    assert deck.total_copies("Unholy Heat") == 4
    assert all(deck.total_copies(name) <= 4 for name in deck.card_names if name != "Mountain")


# -- dealing the game (CR 103.3 - 103.5) -----------------------------------


def test_the_opening_hand_is_seven_and_the_library_is_the_rest():
    """CR 103.5: a hand equal to the starting hand size, normally seven."""
    alice = start().player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert len(alice.hand) + len(alice.library) == 60


def test_every_dealt_card_is_a_card_from_this_list():
    """CR 402.1: the hand holds cards drawn from that player's own library."""
    alice = start().player("alice")

    dealt = alice.hand + alice.library

    assert all(state.zone is Zone.HAND for state in alice.hand)
    assert all(state.card.name in IZZET_PROWESS_MAIN for state in dealt)


def test_each_copy_is_its_own_card():
    """Four Lightning Bolts are four cards sharing one printing."""
    alice = start().player("alice")

    bolts = [s for s in alice.hand + alice.library if s.name == "Lightning Bolt"]

    assert len(bolts) == 4
    assert len({state.id for state in bolts}) == 4


def test_the_sideboard_is_set_aside_and_never_shuffled_in():
    """CR 100.4: the sideboard modifies the deck between games, not during one."""
    alice = start().player("alice")

    assert len(alice.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)
    assert "Consign to Memory" not in {state.name for state in alice.library}


def test_the_game_starts_at_twenty_life():
    """CR 103.4 and CR 119.1: a starting life total of 20."""
    game = start()

    assert all(player.life == 20 for player in game.players)


def test_the_shuffle_is_seeded_and_reproducible():
    """CR 103.3: a random order - deterministic here only because the seed is."""
    first = [state.name for state in match(seed="one").start_game().player("alice").library]
    again = [state.name for state in match(seed="one").start_game().player("alice").library]
    other = [state.name for state in match(seed="two").start_game().player("alice").library]

    assert first == again
    assert first != other


# -- the archetype's own mechanic (CR 702.108a) ----------------------------


def test_a_bolt_from_this_list_pumps_a_swiftspear_from_this_list():
    """CR 702.108a: prowess is "Whenever you cast a noncreature spell, this
    creature gets +1/+1 until end of turn". Both cards are this deck's own.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Monastery Swiftspear", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swiftspear = scenario.find("Monastery Swiftspear", Zone.BATTLEFIELD, "alice")

    assert scenario.game.power_of(swiftspear) == 1

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.game.power_of(swiftspear) == 1 + prowess_bonus[0]
    assert scenario.game.toughness_of(swiftspear) == 2 + prowess_bonus[1]
