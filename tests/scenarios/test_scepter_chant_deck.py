"""Scepter chant, played through the real start-of-game path (CR 103).

The decklist is a real Modern tournament list - pilot **cgouldner**, tournament
date **2026-08-25**, source deck `videre-58652729` - and is the same list
committed to `magic-cards-model-api/decks/scepter_chant.txt`. Every name here
resolves to a real Scryfall printing in `tests/fixtures/cards`.

The archetype's engine is Isochron Scepter (CR 207.2c's "Imprint" ability word)
holding Orim's Chant: the artifact exiles the Chant on entry, then its
`{2}, {T}` ability copies the exiled card and casts the copy for free
(CR 707.12, CR 112.1b), so every turn the opponent is told "target player can't
cast spells this turn." What this file asserts about that engine is exactly what
the engine can do today - the imprint half works, the copy-and-cast half does
not, and the `xfail` below is strict so it will fail loudly the day it starts
working. See `docs/deck-gaps/scepter-chant.md`.

CR numbers used here, each looked up with `knowledge_search` in the session that
wrote this file:

- **CR 103.3** - after the starting player is determined, each player shuffles.
- **CR 103.5** - each player draws a number of cards equal to their starting
  hand size, normally seven.
- **CR 103.8a** - in a two-player game the player who plays first skips the draw
  step of their first turn.
- **CR 401.1** - when a game begins, each player's deck becomes their library.
- **CR 402.1** - the hand is where a player holds cards that have been drawn.
- **CR 207.2c** - an ability word ("Imprint") has no special rules meaning.
- **CR 707.12** - an effect instructing a player to cast a copy of an object
  follows the rules for casting spells.
- **CR 112.1b** - some effects allow a player to cast a copy of a card; if the
  player does, that copy is a spell as well.
- **CR 602.2** - to activate an ability is to put it onto the stack and pay its
  costs.
- **CR 701.2a** - only an object's controller may activate its ability.
- **CR 702.139a** - companion functions outside the game.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Deck, Match, Player, Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

#: pilot cgouldner, 2026-08-25, source videre-58652729. Sums to 60.
SCEPTER_CHANT_MAIN = {
    "Counterspell": 3,
    "Solitude": 3,
    "Arid Mesa": 4,
    "Day's Undoing": 1,
    "Geier Reach Sanitarium": 1,
    "Wrath of the Skies": 3,
    "Monumental Henge": 1,
    "Meticulous Archive": 2,
    "Narset, Parter of Veils": 4,
    "Hallowed Fountain": 1,
    "Prismatic Ending": 2,
    "Sacred Foundry": 1,
    "Teferi, Time Raveler": 3,
    "Thundering Falls": 1,
    "Steam Vents": 1,
    "Island": 2,
    "Plains": 2,
    "Consult the Star Charts": 4,
    "Supreme Verdict": 1,
    "Orim's Chant": 4,
    "Galvanic Discharge": 3,
    "Flooded Strand": 4,
    "Scalding Tarn": 2,
    "Spell Snare": 2,
    "Hedge Maze": 1,
    "Force of Negation": 1,
    "Mystic Gate": 1,
    "Isochron Scepter": 2,
}

#: The same list's sideboard. Sums to 15.
SCEPTER_CHANT_SIDE = {
    "Consign to Memory": 3,
    "Kaheera, the Orphanguard": 1,
    "Mystical Dispute": 3,
    "Supreme Verdict": 1,
    "Day's Undoing": 1,
    "Ashiok, Dream Render": 1,
    "High Noon": 2,
    "Rest in Peace": 1,
    "Celestial Purge": 1,
    "Beza, the Bounding Spring": 1,
}


def scepter_chant() -> Deck:
    return Deck(
        name="Scepter chant",
        mainboard=dict(SCEPTER_CHANT_MAIN),
        sideboard=dict(SCEPTER_CHANT_SIDE),
    )


def match(seed: int | str = "scepter-chant") -> Match:
    """A two-player match with the real list registered for alice."""
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", scepter_chant())
    series.register_deck("bob", scepter_chant())
    return series


# -- the list itself ------------------------------------------------------


def test_the_registered_list_is_sixty_and_fifteen():
    """`Deck.check_legality` on top of the 60/15 and four-copy rules."""
    deck = scepter_chant()

    assert deck.mainboard_size == 60
    assert deck.sideboard_size == 15
    assert deck.problems(card) == []
    assert deck.is_legal(card)


def test_every_name_resolves_to_a_real_printing():
    """No hand-written card json anywhere in this list."""
    for name in scepter_chant().card_names:
        printing = card(name)
        assert printing.name.split(" //")[0] == name


# -- starting the game (CR 103) -------------------------------------------


def test_the_opening_hand_is_seven_and_the_library_is_fifty_three():
    """CR 103.5: a starting hand size of seven, drawn off CR 401.1's library."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert len(alice.hand) + len(alice.library) == 60
    assert all(state.zone is Zone.HAND for state in alice.hand)
    assert all(state.zone is Zone.LIBRARY for state in alice.library)


def test_the_sideboard_is_outside_the_game():
    """CR 103.2a: fifteen cards set aside, never shuffled into the library."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)
    assert len(alice.library) + len(alice.hand) == 60


def test_every_card_dealt_came_from_this_list():
    """CR 401.1: the deck became the library, and nothing else did."""
    game = match().start_game()
    alice = game.player("alice")

    for state in alice.library + alice.hand:
        assert state.name.split(" //")[0] in SCEPTER_CHANT_MAIN


def test_the_shuffle_is_seeded_and_reproducible():
    """CR 103.3's shuffle, driven by the match seed rather than by chance."""
    first = [state.name for state in match(seed="fixed").start_game().player("alice").library]
    second = [state.name for state in match(seed="fixed").start_game().player("alice").library]

    assert first == second


# -- the archetype's engine ------------------------------------------------


def test_isochron_scepter_imprints_orims_chant_on_entry():
    """CR 207.2c: "Imprint" is an ability word, so the trigger is an ordinary
    enters-the-battlefield trigger that exiles a card from hand. This half of
    the engine works.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Isochron Scepter", "Orim's Chant"],
            battlefield=["Island", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    chant = scenario.find("Orim's Chant", Zone.HAND)
    sources = scenario.untapped_sources("Island", "Plains")

    scenario.will_take_the_may()
    scenario.will_choose_cards(chant)
    scepter = scenario.cast_and_resolve("Isochron Scepter", *sources)
    scenario.pass_until_resolved()

    assert scepter.zone is Zone.BATTLEFIELD
    assert chant.zone is Zone.EXILE
    assert scenario.game.card_imprinted_on(scepter.id) is chant


@pytest.mark.xfail(
    strict=True,
    reason=(
        "The lock does not function. Isochron Scepter's '{2}, {T}: You may copy "
        "the exiled card. If you do, you may cast the copy without paying its "
        "mana cost.' returns None from activated_effect_for - neither clause "
        "parses and no notice is recorded, so activating it does nothing at "
        "all. CR 707.12's cast-a-copy and CR 112.1b's copy-as-a-spell have no "
        "representation in the engine. See docs/deck-gaps/scepter-chant.md."
    ),
)
def test_the_scepter_recasts_the_imprinted_chant():
    """CR 602.2 / CR 701.2a: activating the Scepter should copy the imprinted
    Orim's Chant and let its controller cast the copy for free (CR 707.12),
    locking the opponent out of casting spells that turn.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Isochron Scepter", "Orim's Chant"],
            battlefield=["Island", "Plains", "Mystic Gate", "Hallowed Fountain"],
        )
        .player("bob", hand=["Counterspell"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    chant = scenario.find("Orim's Chant", Zone.HAND)
    sources = scenario.untapped_sources("Island", "Plains")

    scenario.will_take_the_may()
    scenario.will_choose_cards(chant)
    scepter = scenario.cast_and_resolve("Isochron Scepter", *sources)
    scenario.pass_until_resolved()

    payment = scenario.game.begin_activating(scepter, 0, "alice")
    scenario.auto_pay(payment)
    scenario.pass_until_resolved()

    assert "Orim's Chant" in scenario.stack_names()
