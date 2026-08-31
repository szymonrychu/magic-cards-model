"""Modern UR aggro: a real registered decklist loads and deals a real game.

The list is the one in `decks/ur_aggro.txt` (magic-cards-model-api) - pilot
**duanceyao**, tournament date **2026-08-29**, source deck `videre-58654130`,
pulled with `statistics_decks(format="modern", archetype_name="ur aggro")`. Every
card in it came back `legal` for modern from `resolve_cards(fields="legality")`,
and every printing here is the real Scryfall card in `tests/fixtures/cards/`.

This is a smoke test for the deck itself, not for a mechanic: it proves the
sixty and the fifteen are constructible (CR 100.2a, 100.4a), that the sideboard
is set aside rather than shuffled in (CR 103.2a), and that starting a game deals
what CR 103.5 and CR 103.4 require. What the deck's cards *do* on resolution is a
separate question - `docs/deck-gaps/ur-aggro.md` records which of them the effect
registry cannot yet resolve.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Deck, Game, Match, Player, Zone
from tests.cards import card

#: The registered mainboard. The source list prints Mountain as two separate
#: one-ofs; a decklist is a multiset, so they are the same two Mountains.
UR_AGGRO_MAIN = {
    "Assault Strobe": 2,
    "Thundering Falls": 1,
    "Cori-Steel Cutter": 4,
    "Dragon's Rage Channeler": 4,
    "Expressive Iteration": 2,
    "Fiery Islet": 1,
    "Lava Dart": 4,
    "Stomping Ground": 1,
    "Steam Vents": 3,
    "Scalding Tarn": 4,
    "Monstrous Rage": 2,
    "Mountain": 2,
    "Mutagenic Growth": 3,
    "Slickshot Show-Off": 4,
    "Monastery Swiftspear": 4,
    "Mishra's Bauble": 4,
    "Lightning Bolt": 4,
    "Unholy Heat": 1,
    "Bloodstained Mire": 3,
    "Wooded Foothills": 3,
    "Preordain": 4,
}

UR_AGGRO_SIDE = {
    "Consign to Memory": 3,
    "Expressive Iteration": 1,
    "Heritage Reclamation": 1,
    "Surgical Extraction": 2,
    "Pick Your Poison": 1,
    "Spell Pierce": 2,
    "Unholy Heat": 3,
    "Meltdown": 2,
}

#: The opponent. Any real sixty will do for a smoke test, and this one is
#: already in the pool as a registered list (`tests/scenarios/harness.py`'s
#: neighbours use the same shape) - it exists here only so `start_game` has two
#: players with libraries.
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


def ur_aggro() -> Deck:
    return Deck(mainboard=dict(UR_AGGRO_MAIN), sideboard=dict(UR_AGGRO_SIDE))


def match(seed: int | str = "ur-aggro") -> Match:
    series = Match(
        players=[Player(username="duanceyao"), Player(username="opponent")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("duanceyao", ur_aggro())
    series.register_deck("opponent", Deck(mainboard=dict(OPPOSING_SIXTY)))
    return series


# -- the list itself (CR 100.2a, 100.4a) ----------------------------------


def test_the_registered_list_is_sixty_and_fifteen():
    """CR 100.2a: a constructed deck is at least sixty cards.
    CR 100.4a: its sideboard is at most fifteen.
    """
    deck = ur_aggro()

    assert deck.mainboard_size == 60
    assert sum(UR_AGGRO_SIDE.values()) == 15
    assert deck.size == 75


def test_every_card_on_the_list_is_a_real_printing_and_the_deck_is_legal():
    """CR 100.2a's four-card limit, checked against the printings, not the names.

    `problems` reports an unknown name too, so this is also the assertion that
    every one of the twenty-seven cards has a fixture.
    """
    assert ur_aggro().problems(card) == []
    assert ur_aggro().is_legal(card)


def test_the_copy_limit_is_respected_across_both_boards():
    """CR 100.4a: the four-card limit applies to the deck and sideboard combined.

    This list is right at the line twice - four Unholy Heat and three Expressive
    Iteration are each split between the boards - so it is the case that would
    catch a decklist transcribed one board at a time.
    """
    deck = ur_aggro()

    assert deck.total_copies("Unholy Heat") == 4
    assert deck.total_copies("Expressive Iteration") == 3
    assert deck.problems(card) == []


def test_registering_the_deck_for_a_match_is_accepted():
    """`Match.register_deck` refuses an illegal list, so this is the real path."""
    series = match()

    assert len(series.games) == 0
    assert series.decks["duanceyao"].mainboard_size == 60


# -- starting the game (CR 103.2a, 103.4, 103.5) --------------------------


def test_the_game_deals_seven_and_leaves_fifty_three():
    """CR 103.5: each player draws a hand equal to their starting hand size,
    normally seven - so a sixty-card library has fifty-three left.
    """
    game = match().start_game()
    pilot = game.player("duanceyao")

    assert len(pilot.hand) == 7
    assert len(pilot.library) == 53
    assert all(state.zone is Zone.HAND for state in pilot.hand)
    assert all(state.zone is Zone.LIBRARY for state in pilot.library)


def test_the_sixty_dealt_is_exactly_the_sixty_registered():
    """Card for card, hand plus library is the registered mainboard."""
    game = match().start_game()
    pilot = game.player("duanceyao")

    dealt: dict[str, int] = {}
    for state in pilot.hand + pilot.library:
        dealt[state.name] = dealt.get(state.name, 0) + 1

    assert dealt == UR_AGGRO_MAIN


def test_the_sideboard_is_set_aside_and_never_shuffled_in():
    """CR 103.2a: sideboard cards are set aside before the deck is shuffled."""
    game = match().start_game()
    pilot = game.player("duanceyao")

    assert len(pilot.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in pilot.sideboard)
    assert len(pilot.hand) + len(pilot.library) == 60
    # Meltdown is sideboard-only on this list, so it must not be in the sixty.
    assert "Meltdown" not in {state.name for state in pilot.hand + pilot.library}


def test_every_copy_of_a_four_of_is_its_own_card():
    """Four Lightning Bolts are four cards sharing one printing, not one card."""
    game = match().start_game()
    pilot = game.player("duanceyao")

    bolts = [s for s in pilot.hand + pilot.library if s.name == "Lightning Bolt"]

    assert len(bolts) == 4
    assert len({state.id for state in bolts}) == 4
    assert len({state.card.id for state in bolts}) == 1


def test_the_game_starts_at_untap_with_life_at_twenty():
    """CR 103.4: each player begins with a starting life total of 20."""
    game = match().start_game()

    assert isinstance(game, Game)
    assert game.turn is not None
    assert game.turn.step is Step.UNTAP
    assert all(player.life == 20 for player in game.players)


def test_the_same_seed_deals_the_same_opening_hand():
    """CR 103.3's shuffle is random, but seeded here so a scenario replays."""
    first = [state.name for state in match(seed="ur-1").start_game().player("duanceyao").hand]
    again = [state.name for state in match(seed="ur-1").start_game().player("duanceyao").hand]
    other = [state.name for state in match(seed="ur-2").start_game().player("duanceyao").hand]

    assert first == again
    assert first != other
