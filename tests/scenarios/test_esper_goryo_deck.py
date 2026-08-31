"""Esper Goryo, a real Modern list, dealt through the real start-of-game path.

The list is jussupinator's, 2026-08-29, source deck videre-58656080, pulled with
`statistics_decks(format="modern", archetype_name="esper goryo", ...)`. Every
name in it resolves to a real Scryfall printing in `tests/fixtures/cards`, and
every card in it was checked Modern-legal with
`resolve_cards(format="modern", fields="legality")` - 31 names sent, 31 rows
back, all legal.

This is a smoke test for the archetype, not for a mechanic: it asserts the deck
is constructible (CR 100.2a, 100.4a) and that a game dealt from it has the sizes
CR 103 requires (103.3 shuffle, 103.5 opening hand). The archetype's actual
engine - Goryo's Vengeance reanimating Atraxa or Griselbrand - is not yet
modelled; see `docs/deck-gaps/esper-goryo.md` and the xfail at the bottom.
"""

import pytest

from magic_cards_model.models import Deck, Game, Match, Player, Zone
from tests.cards import card

#: jussupinator, 2026-08-29, source deck videre-58656080. Sums to 60.
ESPER_GORYO_MAIN = {
    "Undercity Sewers": 1,
    "Psychic Frog": 4,
    "Faithful Mending": 4,
    "Flooded Strand": 4,
    "Island": 1,
    "Shadowy Backstreet": 1,
    "Goryo's Vengeance": 4,
    "Swamp": 1,
    "Griselbrand": 1,
    "Meticulous Archive": 1,
    "Plains": 1,
    "Hallowed Fountain": 1,
    "Prismatic Ending": 2,
    "Polluted Delta": 4,
    "Godless Shrine": 1,
    "Hedge Maze": 1,
    "Solitude": 4,
    "Watery Grave": 1,
    "Quantum Riddler": 4,
    "Thoughtseize": 3,
    "Force of Negation": 2,
    "Ephemerate": 4,
    "March of Otherworldly Light": 1,
    "Atraxa, Grand Unifier": 4,
    "Teferi, Time Raveler": 1,
    "Marsh Flats": 4,
}

#: The same list's sideboard. Sums to 15.
ESPER_GORYO_SIDE = {
    "Consign to Memory": 4,
    "Wrath of the Skies": 3,
    "Nihil Spellbomb": 1,
    "Mystical Dispute": 2,
    "Teferi, Time Raveler": 1,
    "Thoughtseize": 1,
    "March of Otherworldly Light": 1,
    "Spell Snare": 2,
}


def esper_goryo() -> Deck:
    return Deck(mainboard=dict(ESPER_GORYO_MAIN), sideboard=dict(ESPER_GORYO_SIDE))


def match(seed: int | str = "esper-goryo") -> Match:
    """Esper Goryo against a mirror of itself, both decks registered."""
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", esper_goryo())
    series.register_deck("bob", esper_goryo())
    return series


# -- deck construction (CR 100.2a, 100.4a) --------------------------------


def test_the_registered_list_is_a_legal_sixty():
    """CR 100.2a: sixty cards minimum, four copies of any nonbasic maximum."""
    deck = esper_goryo()

    assert deck.mainboard_size == 60
    assert deck.problems(card) == []
    assert deck.is_legal(card)


def test_the_registered_sideboard_is_fifteen():
    """CR 100.4a: a constructed sideboard is at most fifteen cards, and the
    four-copy limit of CR 100.2a applies across deck and sideboard together."""
    deck = esper_goryo()

    assert sum(deck.sideboard.values()) == 15
    for name in set(ESPER_GORYO_MAIN) | set(ESPER_GORYO_SIDE):
        combined = ESPER_GORYO_MAIN.get(name, 0) + ESPER_GORYO_SIDE.get(name, 0)
        assert combined <= 4 or card(name).is_basic_land, name


def test_every_name_in_the_list_is_a_real_printing():
    """No hand-written card data: each name resolves out of the fixture pool."""
    for name in set(ESPER_GORYO_MAIN) | set(ESPER_GORYO_SIDE):
        assert card(name).name.split("//")[0].strip() == name


# -- dealing the game (CR 103.3, 103.5) -----------------------------------


def test_a_game_from_this_list_opens_on_seven_and_leaves_fifty_three():
    """CR 103.5: each player draws a hand equal to their starting hand size,
    which is normally seven, off the shuffled library of CR 103.3."""
    game = match().start_game()
    alice = game.player("alice")

    assert isinstance(game, Game)
    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert len(alice.hand) + len(alice.library) == 60
    assert all(state.zone is Zone.HAND for state in alice.hand)
    assert all(state.card.name.split("//")[0].strip() in ESPER_GORYO_MAIN for state in alice.hand)


def test_the_sideboard_is_set_aside_rather_than_shuffled_in():
    """CR 103.2a: sideboard cards are set aside before the deck is shuffled."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.sideboard) == 15
    assert len(alice.library) + len(alice.hand) == 60
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)


def test_both_seats_are_dealt_from_their_own_copy_of_the_list():
    game = match().start_game()

    for username in ("alice", "bob"):
        player = game.player(username)
        assert len(player.hand) == 7
        assert len(player.library) == 53


def test_the_shuffle_is_seeded_and_two_seeds_deal_differently():
    """CR 103.3: the deck is randomised. Two different seeds must not produce
    the same opening seven, or nothing was actually shuffled."""
    one = [state.name for state in match(seed="seed-one").start_game().player("alice").hand]
    two = [state.name for state in match(seed="seed-two").start_game().player("alice").hand]

    assert one != two


# -- the archetype's actual engine ----------------------------------------


@pytest.mark.xfail(
    reason=(
        "Goryo's Vengeance is not modelled. `effect_for` returns "
        "`delayed_notice_only` for it: the paragraph's third sentence, "
        "'Exile it at the beginning of the next end step', is a delayed "
        "triggered ability (CR 603.7a) the engine cannot build, and an "
        "ability resolves whole or fails closed, so the reanimation in the "
        "first sentence never happens either. See docs/deck-gaps/esper-goryo.md."
    ),
    strict=True,
)
def test_goryos_vengeance_reanimates_a_legendary_creature():
    """The archetype's whole point: Goryo's Vengeance returns a legendary
    creature card from the graveyard to the battlefield with haste."""
    from magic_cards_model.machines.effects import effect_for

    vengeance = card("Goryo's Vengeance")
    effect = effect_for(vengeance.name, vengeance.oracle_text or "")

    assert effect is not None
    assert getattr(effect, "__name__", "") != "delayed_notice_only"
