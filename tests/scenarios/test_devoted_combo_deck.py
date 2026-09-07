"""Scenario: the Modern "devoted combo" decklist loads and a game starts on it.

A smoke test for one archetype the project did not have: that a real registered
sixty-and-fifteen can be resolved card by card out of `tests/fixtures/cards`,
loaded into a library, shuffled, and dealt into an opening hand that is exactly
what CR 103 requires - nothing about what the cards do, which is
`docs/deck-gaps/devoted-combo.md`'s subject.

The decklist is musasabi's "devoted combo", played 2026-08-29 (source deck
`videre-58655572`). It was pulled with `statistics_decks(format="modern",
archetype_name="devoted combo", date_from="2026-06-01", include_cards="full",
limit=5)` and every one of its 38 distinct names verified Modern-legal with
`resolve_cards(names=[...], format="modern", fields="legality")` before being
written here. The same list is in
`magic-cards-model-api/decks/devoted_combo.txt`.

Every CR number below was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 100.2a** - a constructed deck has a minimum deck size of 60 cards and
  may contain any number of basic lands but no more than four of anything else.
- **CR 100.4a** - a constructed sideboard may contain no more than fifteen
  cards, and the four-card limit applies to deck and sideboard combined.
- **CR 103.2a** - sideboards are set aside first; after that each player's deck
  is their deck for the game.
- **CR 103.3** - each player shuffles their deck into a random order.
- **CR 103.5** - each player draws a number of cards equal to their starting
  hand size, normally seven.
- **CR 108.3** - the owner of a card is the player who started the game with it
  in their deck.
- **CR 119.1** - each player begins the game with a starting life total of 20.
- **CR 401.1** - when a game begins, each player's deck becomes their library.
- **CR 103.6 / CR 103.6a** - opening-hand actions, the sequence that begins once
  the mulligan process completes; CR 103.6a is the "begin the game with that
  card on the battlefield" action Leyline of Abundance prints. Modelled now;
  the mechanic itself is `tests/scenarios/test_opening_hand_actions.py`, and
  the last two tests here are this list's own four Leylines going through it.
"""

from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Deck, Match, Player, Zone
from tests.cards import card

#: musasabi, 2026-08-29, source deck videre-58655572. 60 cards.
DEVOTED_COMBO_MAIN = {
    "Devoted Druid": 4,
    "Delighted Halfling": 4,
    "Badgermole Cub": 4,
    "Tyvar, Jubilant Brawler": 4,
    "Birds of Paradise": 2,
    "Vizier of Remedies": 1,
    "Fiend Artisan": 1,
    "Duskwatch Recruiter": 1,
    "Formidable Speaker": 1,
    "Shang-Chi, Master of Kung Fu": 1,
    "Tyvar, the Pummeler": 1,
    "Walking Ballista": 1,
    "Leyline of Abundance": 4,
    "Agatha's Soul Cauldron": 2,
    "Green Sun's Zenith": 4,
    "Nature's Rhythm": 4,
    "Summoner's Pact": 1,
    "Windswept Heath": 3,
    "Verdant Catacombs": 3,
    "Wooded Foothills": 2,
    "Misty Rainforest": 2,
    "Overgrown Tomb": 2,
    "Temple Garden": 1,
    "Underground Mortuary": 1,
    "Nurturing Peatland": 1,
    "Boseiju, Who Endures": 1,
    "Dryad Arbor": 2,
    "Forest": 2,
}

#: The same list's sideboard. 15 cards.
DEVOTED_COMBO_SIDE = {
    "Thoughtseize": 3,
    "Fatal Push": 2,
    "Force of Vigor": 2,
    "Vexing Bauble": 2,
    "Collector Ouphe": 1,
    "Crystal Barricade": 1,
    "Endurance": 1,
    "Keen-Eyed Curator": 1,
    "Guerrilla Gorilla": 1,
    "Kraul Harpooner": 1,
}


def devoted_combo() -> Deck:
    return Deck(
        name="devoted combo",
        mainboard=dict(DEVOTED_COMBO_MAIN),
        sideboard=dict(DEVOTED_COMBO_SIDE),
    )


def match(seed: str = "devoted") -> Match:
    """A two-player match with the registered list in both seats."""
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", devoted_combo())
    series.register_deck("bob", devoted_combo())
    return series


# -- the decklist itself (CR 100.2a, CR 100.4a) ----------------------------


def test_every_card_in_the_list_resolves_to_a_real_printing():
    """The pool has all 38 distinct names, mainboard and sideboard alike."""
    deck = devoted_combo()

    for card_name in deck.card_names:
        printing = card(card_name)
        assert printing.name.split("//")[0].strip() == card_name.split("//")[0].strip()


def test_the_registered_list_is_sixty_and_fifteen():
    """CR 100.2a's minimum deck size and CR 100.4a's sideboard ceiling."""
    deck = devoted_combo()

    assert deck.mainboard_size == 60
    assert deck.sideboard_size == 15


def test_the_registered_list_breaks_no_construction_rule():
    """CR 100.2a's four-card limit, CR 100.4a's across deck and sideboard.

    Two Forests and two Dryad Arbors sit under the limit anyway, so this is the
    ordinary four-of check rather than CR 100.2a's basic-land exemption.
    """
    deck = devoted_combo()

    assert deck.problems(card) == []
    deck.check_legality(card)


# -- starting a game on it (CR 103) ----------------------------------------


def test_starting_a_game_deals_seven_and_leaves_fifty_three():
    """CR 103.5's seven-card opening hand off CR 401.1's library of sixty."""
    game = match().start_game()

    for player in game.players:
        assert len(player.hand) == 7
        assert len(player.library) == 53
        assert len(player.hand) + len(player.library) == 60


def test_the_sideboard_is_set_aside_not_shuffled_in():
    """CR 103.2a: the sideboard is set aside before the deck is the deck."""
    game = match().start_game()

    for player in game.players:
        assert len(player.sideboard) == 15
        assert {state.card.name for state in player.sideboard} == {
            card(name).name for name in DEVOTED_COMBO_SIDE
        }
        assert {state.card.name for state in player.library} <= {
            card(name).name for name in DEVOTED_COMBO_MAIN
        }


def test_every_card_is_owned_by_the_player_who_started_with_it():
    """CR 108.3, and CR 103.2a for the fifteen in the sideboard."""
    game = match().start_game()

    for player in game.players:
        every = [state for zone in player.zones.values() for state in zone]
        assert len(every) == 75
        for state in every:
            assert state.owner == player.username


def test_both_players_begin_at_twenty_life():
    """CR 119.1: the starting life total, which loading a deck does not change."""
    game = match().start_game()

    for player in game.players:
        assert player.life == 20


def test_the_shuffle_is_seeded_and_the_deal_is_reproducible():
    """CR 103.3's random order, made replayable by the match seed.

    Two matches on the same seed deal the same opening hand; a different seed
    deals a different one. Without the second half this would pass on a
    shuffle that never happened.
    """
    first = match("devoted").start_game()
    same = match("devoted").start_game()
    other = match("devoted-2").start_game()

    def opener(game, username):
        return [state.card.name for state in game.player(username).hand]

    assert opener(first, "alice") == opener(same, "alice")
    assert opener(first, "alice") != opener(other, "alice")


# -- the opening-hand action this list wants (CR 103.6, CR 103.6a) ---------


def test_a_leyline_in_the_opening_hand_can_begin_the_game_on_the_battlefield():
    """CR 103.6a: the player taking this action puts that card onto the battlefield.

    Staged rather than hoped for: the library is rigged so a Leyline of
    Abundance is dealt, which is CR 103.3 staging, not a mock - every card is
    the same real printing from the registered list. The action itself is
    declared, because CR 103.6's "may" is declined by an unscripted player.
    """
    series = match()
    game = series.start_game(deal_opening_hands=False)
    alice = game.player("alice")
    leyline = next(state for state in alice.library if state.card.name == "Leyline of Abundance")
    alice.library.remove(leyline)
    alice.library.insert(0, leyline)
    # `deal_opening_hands=False` above split the deal in two so the library
    # could be rigged first; the deferred draw happens with no `Game` method
    # on the call stack to open `_id_allocator_scope`, so it has to here -
    # see `tests/scenarios/test_opening_hand_actions.py::dealt`'s own note.
    with game._id_allocator_scope():  # noqa: SLF001
        alice.draw_opening_hand()
    game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.OPENING_HAND_ACTION,
            value=True,
            player="alice",
            source="Leyline of Abundance",
        )
    )
    series.run_mulligans(game)

    assert leyline.zone is Zone.BATTLEFIELD


def test_an_undeclared_leyline_stays_in_hand():
    """CR 103.6 is a "may": nothing starts on the battlefield by itself."""
    series = match()
    game = series.start_game(deal_opening_hands=False)
    alice = game.player("alice")
    leyline = next(state for state in alice.library if state.card.name == "Leyline of Abundance")
    alice.library.remove(leyline)
    alice.library.insert(0, leyline)
    # `deal_opening_hands=False` above split the deal in two so the library
    # could be rigged first; the deferred draw happens with no `Game` method
    # on the call stack to open `_id_allocator_scope`, so it has to here -
    # see `tests/scenarios/test_opening_hand_actions.py::dealt`'s own note.
    with game._id_allocator_scope():  # noqa: SLF001
        alice.draw_opening_hand()
    series.run_mulligans(game)

    assert leyline.zone is Zone.HAND
