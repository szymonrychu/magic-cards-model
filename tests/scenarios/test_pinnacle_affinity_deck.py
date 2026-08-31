"""Pinnacle affinity: a real Modern list loads, shuffles, and starts a game.

The decklist below is a registered tournament deck, not an aggregate - pilot
**Shamplade**, tournament date **2026-08-29**, source deck `videre-58656063`,
pulled with `statistics_decks(format="modern", archetype_name="pinnacle
affinity", date_from="2026-06-01", include_cards="full")`. Every one of its 28
distinct cards was checked with `resolve_cards(..., format="modern",
fields="legality")` and came back `legal`. The same list is written out as
`decks/pinnacle_affinity.txt` in the companion `magic-cards-model-api` repo.

This is a smoke test, so it proves exactly one thing: the deck goes through the
real construction and game-start path and comes out the other side with the
zones CR 103 requires. It does *not* prove the deck plays correctly - six of its
cards are still silent in `machines/effects.py`.
`docs/deck-gaps/pinnacle-affinity.md` is the inventory. The archetype's
improvise engine (CR 702.126a) is now modelled in
`machines/objects_as_costs.py`, and the last test in this file checks that
Kappa Cannoneer makes the offer.

Rules verified with `knowledge_search` for this file:

- CR 100.2a: constructed decks have a minimum deck size of 60 cards, and a
  constructed deck may contain any number of basic land cards.
- CR 100.4a: a constructed sideboard is at most fifteen cards, and the
  four-card limit applies to the combined deck and sideboard.
- CR 103.3: after the starting player is determined, each player shuffles their
  deck so the cards are in a random order.
- CR 103.5: each player draws a number of cards equal to their starting hand
  size, which is normally seven.
- CR 401.1: when a game begins, each player's deck becomes their library.
- CR 402.1: at the beginning of the game each player draws a number of cards
  equal to their starting hand size.
- CR 702.126a: improvise - "For each generic mana in this spell's total cost,
  you may tap an untapped artifact you control rather than pay that mana."
"""

from magic_cards_model.models import Deck, Match, Player, Zone
from tests.cards import card

#: Shamplade, 2026-08-29, source deck videre-58656063. Sixty cards.
PINNACLE_AFFINITY_MAIN = {
    "Fiery Islet": 4,
    "Mishra's Bauble": 4,
    "Spirebluff Canal": 4,
    "Tormod's Crypt": 4,
    "Kappa Cannoneer": 4,
    "Skateboard": 1,
    "Pinnacle Emissary": 4,
    "Shadowspear": 1,
    "Shivan Reef": 2,
    "Island": 1,
    "Welding Jar": 1,
    "Sink into Stupor": 1,
    "Weapons Manufacturing": 4,
    "Mox Opal": 4,
    "Experimental Synthesizer": 4,
    "Engineered Explosives": 4,
    "Pithing Needle": 1,
    "Metallic Rebuke": 3,
    "Claws of Gix": 4,
    "Urza's Saga": 4,
    "Steam Vents": 1,
}

#: The same registered list's sideboard. Fifteen cards.
PINNACLE_AFFINITY_SIDE = {
    "Damping Sphere": 2,
    "Blood Moon": 2,
    "Mystical Dispute": 2,
    "Consign to Memory": 3,
    "Galvanic Blast": 3,
    "Emry, Lurker of the Loch": 2,
    "Whipflare": 1,
}

#: The opponent. A second real deck is not what this file is testing, so it is
#: the plain sixty `tests/scenarios/test_starting_a_game.py` already uses.
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


def affinity_deck() -> Deck:
    return Deck(mainboard=dict(PINNACLE_AFFINITY_MAIN), sideboard=dict(PINNACLE_AFFINITY_SIDE))


def match(seed: int | str = "pinnacle-affinity") -> Match:
    """A two-player match with the affinity list registered and legality checked."""
    series = Match(
        players=[Player(username="shamplade"), Player(username="opponent")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("shamplade", affinity_deck())
    series.register_deck("opponent", Deck(mainboard=dict(OPPOSING_SIXTY)))
    return series


# -- the list itself (CR 100.2a, 100.4a) ----------------------------------


def test_the_registered_list_is_sixty_and_fifteen():
    """CR 100.2a, 100.4a: sixty in the deck, at most fifteen in the sideboard."""
    deck = affinity_deck()

    assert deck.mainboard_size == 60
    assert deck.sideboard_size == 15
    assert deck.size == 75


def test_the_registered_list_is_legal_against_the_real_printings():
    """CR 100.2a's four-card limit, checked against the pool's actual printings.

    Nothing here is exempt by basic-land supertype except the single Island, so
    this is the copy limit doing real work over 27 nonbasic names.
    """
    deck = affinity_deck()

    assert deck.problems(card) == []
    assert deck.is_legal(card)


def test_every_card_on_the_list_is_a_real_printing_in_the_pool():
    """No hand-written card data: each name resolves to a Scryfall printing."""
    names = set(PINNACLE_AFFINITY_MAIN) | set(PINNACLE_AFFINITY_SIDE)

    assert len(names) == 28
    for name in names:
        assert card(name).name.split("//")[0].strip() == name


def test_the_copy_limit_spans_the_sideboard_for_this_list():
    """CR 100.4a: the four-card limit applies to the combined deck and sideboard.

    Emry is a two-of in the board with no maindeck copies. Trading the three
    Galvanic Blasts for three more Emrys keeps the sideboard at a legal fifteen,
    so the only thing left to complain about is the copy limit itself.
    """
    swapped = dict(PINNACLE_AFFINITY_SIDE) | {"Emry, Lurker of the Loch": 5}
    del swapped["Galvanic Blast"]
    over = Deck(mainboard=dict(PINNACLE_AFFINITY_MAIN), sideboard=swapped)

    assert over.sideboard_size == 15

    assert over.total_copies("Emry, Lurker of the Loch") == 5
    assert over.problems(card) == [
        "5 copies of Emry, Lurker of the Loch, which is limited to 4",
    ]


# -- starting the game (CR 103.3, 103.5, 401.1, 402.1) --------------------


def test_the_deck_becomes_a_library_and_deals_a_seven_card_hand():
    """CR 401.1: the deck becomes the library. CR 103.5 / 402.1: seven cards."""
    game = match().start_game()
    pilot = game.player("shamplade")

    assert len(pilot.hand) == 7
    assert len(pilot.library) == 53
    assert len(pilot.library) + len(pilot.hand) == 60
    assert all(state.zone is Zone.HAND for state in pilot.hand)
    assert all(state.zone is Zone.LIBRARY for state in pilot.library)


def test_the_sideboard_is_set_aside_rather_than_shuffled_in():
    """CR 103.2a: the sideboard is set aside before the deck is shuffled."""
    game = match().start_game()
    pilot = game.player("shamplade")

    assert len(pilot.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in pilot.sideboard)
    assert "Blood Moon" not in {state.name for state in pilot.library + pilot.hand}


def test_the_dealt_cards_are_the_registered_list_and_nothing_else():
    """Every physical card in the game came off the list, at its listed count."""
    game = match().start_game()
    pilot = game.player("shamplade")

    dealt: dict[str, int] = {}
    for state in pilot.library + pilot.hand:
        front = state.name.split("//")[0].strip()
        dealt[front] = dealt.get(front, 0) + 1

    assert dealt == PINNACLE_AFFINITY_MAIN


def test_the_shuffle_is_a_real_shuffle_and_reproducible():
    """CR 103.3: the deck is randomized, and the seed makes it replayable.

    Two matches on the same seed deal the same hand; two on different seeds do
    not. Both halves matter - an unshuffled library would pass the first.
    """
    same = [
        [state.name for state in match(seed).start_game().player("shamplade").hand]
        for seed in ("pinnacle-affinity", "pinnacle-affinity")
    ]
    reseeded = match("a-different-seed").start_game().player("shamplade")
    other = [state.name for state in reseeded.hand]

    assert same[0] == same[1]
    assert other != same[0]
    assert [state.name for state in match().start_game().player("shamplade").library][:21] != list(
        PINNACLE_AFFINITY_MAIN
    )


def test_the_opponent_is_dealt_from_their_own_deck():
    """The two libraries never mix: no affinity card reaches the opponent."""
    game = match().start_game()
    opponent = game.player("opponent")

    assert len(opponent.hand) == 7
    assert len(opponent.library) == 53
    drawn = {state.name for state in opponent.library + opponent.hand}
    assert drawn <= set(OPPOSING_SIXTY)
    assert not drawn & set(PINNACLE_AFFINITY_MAIN)


# -- what the deck still cannot do ----------------------------------------


def test_improvise_lets_artifacts_pay_the_generic_part_of_a_cost():
    """CR 702.126a: "For each generic mana in this spell's total cost, you may
    tap an untapped artifact you control rather than pay that mana."

    Kappa Cannoneer's printed text carries improvise, so the engine ought to
    recognise it as an available cost-payment option on the spell. It lives in
    `machines/objects_as_costs.py` with the rest of the family that pays a cost
    with objects (convoke, delve, crew); `tests/scenarios/test_improvise.py`
    plays it out on a real board.
    """
    cannoneer = card("Kappa Cannoneer")

    assert "Improvise" in (cannoneer.oracle_text or "")
    assert "improvise" in {keyword.lower() for keyword in cannoneer.keywords}

    from magic_cards_model.machines.objects_as_costs import improvise_payment  # noqa: PLC0415

    assert improvise_payment(cannoneer) is not None
