"""The broodscale bloodchief Modern deck, dealt through the real start-of-game path.

This is a deck smoke test, not a mechanic test: it proves one real tournament
sixty can be registered, shuffled and dealt by the engine, with the counts CR
103 actually requires. What the cards *do* once drawn is a separate matter -
`docs/deck-gaps/broodscale-bloodchief.md` lists the nineteen abilities that
still resolve to nothing, and none of them are exercised here.

The list is a real registered deck: pilot **unagieel**, tournament date
**2026-08-30**, source deck `videre-58656378`, pulled with
`statistics_decks(format="modern", archetype_name="broodscale bloodchief")`.
Every one of its thirty distinct cards came back `legal` from
`resolve_cards(format="modern", fields="legality")` in the session that added
it, and every one is a real Scryfall printing in `tests/fixtures/cards/`.
The same list is written out in `magic-cards-model-api/decks/broodscale_bloodchief.txt`.

The rules this file asserts, each looked up with `knowledge_search`:

- **CR 100.2a** - a constructed deck is at least sixty cards, at most four of
  anything but a basic land. Six Forests is why "at most four" is not the
  whole rule.
- **CR 100.4a** - a constructed sideboard is at most fifteen cards, and the
  four-copy limit spans deck and sideboard together. This deck is exactly at
  that combined limit on Dismember (2 main + 1 side) and Vexing Bauble
  (1 main + 2 side), which is the interesting part of registering it.
- **CR 103.2a** - the sideboard is set aside; what remains is the library.
- **CR 103.3** - each player shuffles, so the order is random but the sixty
  cards are the same sixty.
- **CR 103.4** - starting life total 20.
- **CR 103.5** - each player draws a hand equal to their starting hand size,
  normally seven, which is what leaves 53 in the library.

- **CR 103.6**, **CR 103.6a**, **CR 103.6b** - the opening-hand actions that run
  once the mulligan process is complete. This deck has both shapes: Gemstone
  Caverns begins the game on the battlefield (and only for the player who is
  not the starting player), and Devourer of Destiny is revealed from the
  opening hand. Modelled now - see `tests/scenarios/test_opening_hand_actions.py`
  for the mechanic itself; the three tests at the bottom here are this deck's
  own two cards going through it.
"""

#: `id(state.card)` asserts CPython object identity, not game state -
#: `tests/cards.py`'s `card()` cache handing every physical copy the same
#: in-memory `Card` is a pure memory optimisation. A JSON decode has no way
#: to represent "these two value-equal objects were the same object", so the
#: T10 invariant's replay run - which continues from a genuinely decoded
#: game - honestly sees four distinct `Card` instances here, not the live
#: run's cached one. Not an engine defect.
import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Deck, Game, Match, Player, Zone
from tests.cards import card

IDENTITY_NOTE = (
    "T10: id(state.card) is CPython object identity, not game state - a "
    "decode of value-equal Card printings never shares one Python object, "
    "so the invariant's replay run legitimately sees 4 distinct ids here, "
    "not the live run's cached 1. Not an engine defect."
)

#: Broodscale bloodchief, Modern. Pilot unagieel, 2026-08-30, deck
#: videre-58656378. Sixty cards; the counts are the registered ones.
BROODSCALE_MAIN = {
    "Basking Broodscale": 4,
    "Blade of the Bloodchief": 3,
    "Emrakul, the Promised End": 4,
    "Devourer of Destiny": 2,
    "Glaring Fleshraker": 2,
    "Haywire Mite": 1,
    "Kozilek's Command": 4,
    "Malevolent Rumble": 4,
    "Sowing Mycospawn": 4,
    "Ancient Stirrings": 4,
    "Dismember": 2,
    "Soul-Guide Lantern": 1,
    "Vexing Bauble": 1,
    "Springleaf Drum": 1,
    "Urza's Saga": 4,
    "Eldrazi Temple": 4,
    "Ugin's Labyrinth": 3,
    "Boseiju, Who Endures": 2,
    "Cavern of Souls": 1,
    "Gemstone Caverns": 1,
    "Shifting Woodland": 1,
    "Yavimaya, Cradle of Growth": 1,
    "Forest": 6,
}

#: The registered fifteen. Dismember and Vexing Bauble appear here *and* in the
#: mainboard, which is what makes CR 100.4a's combined four-copy limit bite.
BROODSCALE_SIDE = {
    "Trinisphere": 2,
    "Disruptor Flute": 2,
    "Grafdigger's Cage": 3,
    "Soulless Jailer": 1,
    "Sire of Seven Deaths": 1,
    "Pithing Needle": 1,
    "Dismember": 1,
    "Vexing Bauble": 2,
    "Nature's Claim": 2,
}

#: A second real sixty for the opponent's seat, so a game has two decks in it.
#: Reused from `test_starting_a_game.py`'s pool rather than invented here.
OPPONENT_SIXTY = {
    "Mountain": 24,
    "Plains": 12,
    "Lightning Bolt": 4,
    "Grizzly Bears": 4,
    "Sol Ring": 4,
    "Questing Beast": 4,
    "Swords to Plowshares": 4,
    "Counterspell": 4,
}


def broodscale_deck() -> Deck:
    return Deck(
        name="Broodscale Bloodchief",
        mainboard=dict(BROODSCALE_MAIN),
        sideboard=dict(BROODSCALE_SIDE),
    )


def match(seed: int | str = "broodscale") -> Match:
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", broodscale_deck())
    series.register_deck("bob", Deck(name="Burn", mainboard=dict(OPPONENT_SIXTY)))
    return series


def started() -> Game:
    return match().start_game()


# -- the list itself (CR 100.2a, 100.4a) -----------------------------------


def test_every_card_in_the_list_is_a_real_printing_in_the_pool():
    """A missing fixture would make the rest of this file test nothing."""
    deck = broodscale_deck()

    missing = [name for name in deck.card_names if card(name) is None]

    assert missing == []


def test_the_registered_list_is_sixty_and_fifteen():
    """CR 100.2a's minimum deck size, CR 100.4a's sideboard maximum."""
    deck = broodscale_deck()

    assert deck.mainboard_size == 60
    assert deck.sideboard_size == 15


def test_the_registered_list_is_legal():
    """CR 100.2a and 100.4a together, checked against the real printings.

    This is the rule that needs the card data: six Forests pass only because
    Forest is a basic land, and Dismember's and Vexing Bauble's split counts
    pass only because three and three are still within four.
    """
    deck = broodscale_deck()

    assert deck.problems(card) == []
    deck.check_legality(card)


def test_the_split_counts_are_at_the_combined_four_copy_limit():
    """CR 100.4a: the four-copy limit applies to deck and sideboard combined."""
    deck = broodscale_deck()

    assert deck.total_copies("Dismember") == 3
    assert deck.total_copies("Vexing Bauble") == 3
    assert deck.total_copies("Basking Broodscale") == 4


def test_six_forests_are_legal_because_forest_is_basic():
    """CR 100.2a: any number of basic lands, and only of basic lands."""
    assert BROODSCALE_MAIN["Forest"] > 4
    assert "Basic" in (card("Forest").type_line or "")


# -- dealing the game (CR 103.2a - 103.5) ----------------------------------


def test_the_deck_deals_an_opening_hand_of_seven():
    """CR 103.5: a hand equal to the starting hand size, normally seven."""
    alice = started().player("alice")

    assert len(alice.hand) == 7
    assert all(state.zone is Zone.HAND for state in alice.hand)


def test_the_library_is_the_other_fifty_three():
    """CR 103.2a then 103.5: sixty set aside from the sideboard, seven drawn."""
    alice = started().player("alice")

    assert len(alice.library) == 53
    assert len(alice.library) + len(alice.hand) == 60


def test_the_sideboard_is_set_aside_and_not_in_the_library():
    """CR 103.2a: sideboard cards are not part of the deck the game starts with."""
    alice = started().player("alice")

    assert len(alice.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)
    # Three Grafdigger's Cages are sideboard-only, so none may be in the sixty.
    in_deck = {state.name for state in alice.library + alice.hand}
    assert "Grafdigger's Cage" not in in_deck
    assert "Trinisphere" not in in_deck


def test_every_dealt_card_is_a_card_of_this_decklist():
    alice = started().player("alice")

    dealt = [state for state in alice.library + alice.hand]

    assert all(state.card.name in BROODSCALE_MAIN for state in dealt)
    assert len(dealt) == 60


def test_the_sixty_dealt_are_the_sixty_registered_card_for_card():
    """CR 103.3 shuffles the order, not the contents."""
    alice = started().player("alice")

    counts: dict[str, int] = {}
    for state in alice.library + alice.hand:
        counts[state.card.name] = counts.get(state.card.name, 0) + 1

    assert counts == BROODSCALE_MAIN


@pytest.mark.no_replay(reason=IDENTITY_NOTE)
def test_every_copy_is_its_own_card():
    """Four Basking Broodscales are four cards sharing one printing."""
    alice = started().player("alice")

    broodscales = [s for s in alice.library + alice.hand if s.name == "Basking Broodscale"]

    assert len(broodscales) == 4
    assert len({state.id for state in broodscales}) == 4
    assert len({id(state.card) for state in broodscales}) == 1


def test_the_shuffle_is_random_but_reproducible():
    """CR 103.3: a random order, and the same seed reproduces it exactly."""

    def library_of(seed: str) -> list[str]:
        return [state.name for state in match(seed=seed).start_game().player("alice").library]

    def sixty_of(seed: str) -> list[str]:
        alice = match(seed=seed).start_game().player("alice")
        return [state.name for state in alice.library + alice.hand]

    assert library_of("brood") == library_of("brood")
    assert library_of("brood") != library_of("scale")
    # A different shuffle deals a different seven, so only the whole sixty is
    # comparable card for card - the library alone is 53 of a different 53.
    assert sorted(sixty_of("brood")) == sorted(sixty_of("scale"))


def test_the_game_starts_at_twenty_life_in_the_untap_step():
    """CR 103.4 for the life total, and the first turn beginning after it."""
    game = started()

    assert all(player.life == 20 for player in game.players)
    assert game.turn is not None
    # CR 103.5 first: a dealt game rests in the mulligan step, before any turn.
    assert game.turn.step is Step.MULLIGAN
    assert game.turn.turn_number == 0

    game.settle_pregame()

    # CR 103.8: the starting player takes their first turn, which begins at untap.
    assert game.turn.step is Step.UNTAP


def test_both_seats_are_dealt_from_their_own_deck():
    game = started()

    bob = game.player("bob")

    assert len(bob.hand) == 7
    assert len(bob.library) == 53
    assert all(state.card.name in OPPONENT_SIXTY for state in bob.library + bob.hand)
    assert "Basking Broodscale" not in {state.name for state in bob.library + bob.hand}


# -- what this deck does at the start of a game (CR 103.6) ----------------


def rigged_and_settled(top: str, *, on_the_play: str) -> Game:
    """Deal alice a named card off the top, then run CR 103.5 and CR 103.6.

    CR 103.3 staging - the sixty are the registered sixty, only the order is
    chosen - which is what makes a one-of like Gemstone Caverns reachable at
    all. The action itself is scripted rather than defaulted: CR 103.6's "may"
    is declined by an unscripted player, by design.
    """
    series = match()
    game = series.start_game(deal_opening_hands=False, on_the_play=on_the_play)
    alice = game.player("alice")
    state = next(s for s in alice.library if s.card.name == top)
    alice.library.remove(state)
    alice.library.insert(0, state)
    # `deal_opening_hands=False` above split the deal in two so the library
    # could be rigged first; the deferred draw happens with no `Game` method
    # on the call stack to open `_id_allocator_scope`, so it has to here -
    # see `tests/scenarios/test_opening_hand_actions.py::dealt`'s own note.
    with game._id_allocator_scope():  # noqa: SLF001
        for player in game.players:
            player.draw_opening_hand()
    game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.OPENING_HAND_ACTION, value=True, player="alice", source=top
        )
    )
    series.run_mulligans(game)
    return game


def test_gemstone_caverns_can_begin_the_game_on_the_battlefield():
    """CR 103.6a: a card that lets a player begin the game with it on the
    battlefield is put there, by the non-starting player, after mulligans.

    "If this card is in your opening hand and you're not the starting player,
    you may begin the game with Gemstone Caverns on the battlefield with a luck
    counter on it. If you do, exile a card from your hand." - so bob is on the
    play here, and alice pays the exile.
    """
    game = rigged_and_settled("Gemstone Caverns", on_the_play="bob")
    alice = game.player("alice")

    (caverns,) = [s for s in game.battlefield if s.name == "Gemstone Caverns"]

    assert caverns.zone is Zone.BATTLEFIELD
    assert caverns.counter_count("luck") == 1
    # `Game.exile`: exile is shared (CR 400.1), and reading a pile of alice's
    # own here is what let the rider exile into one for as long as it did.
    assert len(game.exile) == 1
    assert game.exile[0].owner == alice.username


def test_the_starting_player_is_never_offered_the_caverns():
    """CR 103.8 names the starting player, and the card excludes them."""
    game = rigged_and_settled("Gemstone Caverns", on_the_play="alice")

    assert game.battlefield == []
    assert [
        d.source for d in game.decisions.asked if d.kind is DecisionKind.OPENING_HAND_ACTION
    ] == []


def test_devourer_of_destiny_can_be_revealed_from_the_opening_hand():
    """CR 103.6b: the card is shown and stays where it is (CR 701.20b)."""
    game = rigged_and_settled("Devourer of Destiny", on_the_play="alice")
    alice = game.player("alice")

    (devourer,) = [s for s in alice.hand if s.name == "Devourer of Destiny"]

    assert devourer.zone is Zone.HAND
    assert devourer.id in game.opening_hand_reveals
    assert [reveal.card_name for reveal in game.reveals] == ["Devourer of Destiny"]
