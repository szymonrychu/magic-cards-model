"""Esper control, the real Modern list, loaded and dealt through the engine.

The decklist below is a registered tournament list - pilot `yriel`, tournament
date 2026-08-30, source deck `videre-58656301` - pulled with
`statistics_decks(format="modern", archetype_name="esper control")` and checked
card by card with `resolve_cards(format="modern", fields="legality")`: all 33
distinct names came back `legal`. It is the same list mirrored at
`magic-cards-model-api/decks/esper_control.txt`.

This is a smoke scenario: it proves the sixty and the fifteen resolve against
real printings in `tests/fixtures/cards`, that the list is legal by CR 100.2a
and CR 100.4a, and that a game starts as CR 103 requires - deck becomes library
(CR 401.1), shuffle (CR 103.3), life at 20 (CR 103.4), and a seven-card opening
hand (CR 103.5).

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file: 100.2a, 100.4a, 103.3, 103.4, 103.5, 401.1.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Deck, DeckLimits, Match, Player, Zone
from tests.cards import card

#: Mainboard as registered: 60 cards. The source data prints some lands as
#: several separate one-of rows (Quantum Riddler arrives as 2 + 2); merging
#: those into one line changes nothing about the counts.
ESPER_CONTROL_MAIN = {
    "Psychic Frog": 4,
    "Quantum Riddler": 4,
    "Solitude": 4,
    "Ketramose, the New Dawn": 4,
    "Orcish Bowmasters": 2,
    "Relic of Progenitus": 4,
    "Prismatic Ending": 4,
    "Ephemerate": 2,
    "Inquisition of Kozilek": 2,
    "Thoughtseize": 4,
    "No More Lies": 2,
    "Spell Snare": 1,
    "Teferi, Time Raveler": 1,
    "Meticulous Archive": 1,
    "Shadowy Backstreet": 1,
    "Undercity Sewers": 1,
    "Island": 1,
    "Plains": 1,
    "Swamp": 1,
    "Marsh Flats": 4,
    "Godless Shrine": 1,
    "Watery Grave": 1,
    "Flooded Strand": 3,
    "Polluted Delta": 4,
    "Hallowed Fountain": 1,
    "Otawara, Soaring City": 1,
    "Takenuma, Abandoned Mire": 1,
}

#: Sideboard as registered: 15 cards.
ESPER_CONTROL_SIDE = {
    "Consign to Memory": 4,
    "Mystical Dispute": 2,
    "Wrath of the Skies": 3,
    "Grafdigger's Cage": 1,
    "White Orchid Phantom": 3,
    "Fatal Push": 1,
    "Spell Snare": 1,
}


def esper_control() -> Deck:
    return Deck(
        name="Esper control",
        mainboard=dict(ESPER_CONTROL_MAIN),
        sideboard=dict(ESPER_CONTROL_SIDE),
        limits=DeckLimits.constructed(),
    )


def match(seed: int | str = "esper") -> Match:
    """Esper control against the same list, so either seat exercises the deck."""
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", esper_control())
    series.register_deck("bob", esper_control())
    return series


# -- the decklist itself ---------------------------------------------------


def test_the_registered_list_is_sixty_and_fifteen():
    """CR 100.2a: minimum deck size 60. CR 100.4a: at most fifteen sideboard."""
    deck = esper_control()

    assert deck.mainboard_size == 60
    assert deck.sideboard_size == 15


def test_the_registered_list_passes_construction():
    """CR 100.2a's four-copy limit spans the sideboard too (CR 100.4a)."""
    esper_control().check_legality(card)


def test_every_card_in_the_list_is_a_real_printing():
    """No hand-written card data: each name resolves in the fixture pool."""
    for name in {**ESPER_CONTROL_MAIN, **ESPER_CONTROL_SIDE}:
        assert card(name).name.split("//")[0].strip() == name


# -- starting a game with it (CR 103) --------------------------------------


def test_the_deck_becomes_a_library_and_deals_seven():
    """CR 401.1: the deck becomes the library. CR 103.5: draw seven."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert len(alice.library) + len(alice.hand) == 60
    assert all(state.zone is Zone.HAND for state in alice.hand)
    assert all(state.name.split("//")[0].strip() in ESPER_CONTROL_MAIN for state in alice.hand)


def test_the_sideboard_is_set_aside():
    """CR 100.4a's fifteen stay out of the library."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)
    assert "Wrath of the Skies" not in {state.name for state in alice.library}


def test_the_game_starts_at_untap_with_life_at_twenty():
    """CR 103.4: each player begins at 20."""
    game = match().start_game()

    assert game.turn is not None
    assert game.turn.step is Step.UNTAP
    assert all(player.life == 20 for player in game.players)


def test_the_deck_is_shuffled_not_dealt_in_list_order():
    """CR 103.3: shuffle so the cards are in a random order."""
    game = match().start_game()
    alice = game.player("alice")

    dealt = [state.name for state in alice.hand + alice.library]
    in_list_order = [name for name, count in ESPER_CONTROL_MAIN.items() for _ in range(count)]

    assert dealt != in_list_order
    assert sorted(dealt) == sorted(in_list_order)


def test_each_copy_is_its_own_card():
    """Four Thoughtseize are four cards sharing one printing."""
    game = match().start_game()
    alice = game.player("alice")

    seizes = [s for s in alice.library + alice.hand if s.name == "Thoughtseize"]

    assert len(seizes) == 4
    assert len({state.id for state in seizes}) == 4


# -- what the deck needs that the engine does not have yet -----------------


@pytest.mark.xfail(
    reason="Grafdigger's Cage's static prohibition is unmodelled: nothing in "
    'machines/ reads "Players can\'t cast spells from graveyards or libraries", '
    "and the sweeper's classifier files the card as no_rules_text because "
    "has_rules_text() skips every static line on a permanent.",
    strict=True,
)
def test_grafdiggers_cage_is_a_modelled_static_ability():
    from magic_cards_model.machines.abilities import parse_abilities

    cage = card("Grafdigger's Cage")
    abilities = parse_abilities(cage)

    assert abilities, "Grafdigger's Cage parses into abilities"
    assert any(getattr(ability, "effect", None) is not None for ability in abilities)
