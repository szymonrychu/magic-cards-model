"""The Modern "allosaurus combo" deck, started for real.

The list is a registered tournament decklist: **pilot E_Kaminuma, 2026-08-28**,
source deck `videre-58654931`, the same sixty and fifteen written to
`magic-cards-model-api/decks/allosaurus_combo.txt`. Every name resolves to a
real Scryfall printing in `tests/fixtures/cards/`; nothing here is assembled
from archetype averages.

This file is a *deck* smoke test, not a mechanic file: it plays the deck through
the real `Match.start_game` path and asserts CR 103's opening against it.

- CR 100.2a: a constructed deck has a minimum deck size of 60 cards.
- CR 100.4a: in constructed play a sideboard may contain no more than fifteen
  cards, and the four-card limit of CR 100.2a applies to deck and sideboard
  combined.
- CR 103.2a: sideboard cards are set aside, and what is left is the deck.
- CR 103.3: each player shuffles their deck into a random order.
- CR 103.5: each player draws a number of cards equal to their starting hand
  size, normally seven.
- CR 401.1: when the game begins, each player's deck becomes their library.

The archetype's own engine is checked at the bottom: the CR 118.9 pitch cast on
Allosaurus Rider, Summoner's Pact and its bill, and Neoform's payoff that turns
the pitched creature into a fatty. Eldritch Evolution's own version of that
payoff is still unread - see the Neoform test's docstring for what it needs.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Deck, Game, Match, Player, Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

#: Pilot E_Kaminuma, 2026-08-28, source deck videre-58654931. Sixty cards.
ALLOSAURUS_COMBO_MAIN = {
    "Allosaurus Rider": 4,
    "Summoner's Pact": 4,
    "Neoform": 4,
    "Eldritch Evolution": 4,
    "Planar Genesis": 4,
    "Disciple of Freyalise": 2,
    "Generous Ent": 2,
    "Ghalta, Stampede Tyrant": 2,
    "Griselbrand": 1,
    "Atraxa, Grand Unifier": 1,
    "Ureni, the Song Unending": 1,
    "Xenagos, God of Revels": 1,
    "Hooting Mandrills": 1,
    "Endurance": 1,
    "Bridgeworks Battle": 1,
    "Preordain": 1,
    "Consign to Memory": 4,
    "Pact of Negation": 3,
    "Veil of Summer": 3,
    "Nature's Claim": 1,
    "Misty Rainforest": 4,
    "Scalding Tarn": 2,
    "Wooded Foothills": 1,
    "Hedge Maze": 3,
    "Breeding Pool": 1,
    "Forest": 2,
    "Island": 1,
    "Boseiju, Who Endures": 1,
}

#: The same player's fifteen-card sideboard.
ALLOSAURUS_COMBO_SIDE = {
    "Mystical Dispute": 4,
    "Nature's Claim": 3,
    "Thundertrap Trainer": 2,
    "Veil of Summer": 1,
    "Pact of Negation": 1,
    "Into the Flood Maw": 1,
    "Elesh Norn, Grand Cenobite": 1,
    "Abhorrent Oculus": 1,
    "Hooting Mandrills": 1,
}

#: An opponent to start a game against. Real cards, no archetype pretence -
#: this deck exists only so `Match.start_game` has two registered decks.
OPPONENT_SIXTY = {
    "Mountain": 24,
    "Lightning Bolt": 4,
    "Monastery Swiftspear": 4,
    "Goblin Guide": 4,
    "Lava Spike": 4,
    "Grizzly Bears": 4,
    "Shock": 4,
    "Burst Lightning": 4,
    "Sol Ring": 4,
    "Ornithopter": 4,
}


def allosaurus_deck() -> Deck:
    return Deck(mainboard=ALLOSAURUS_COMBO_MAIN, sideboard=ALLOSAURUS_COMBO_SIDE)


def match(seed: int | str = "allosaurus") -> Match:
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", allosaurus_deck())
    series.register_deck("bob", Deck(mainboard=OPPONENT_SIXTY, sideboard={"Mountain": 15}))
    return series


# -- the decklist itself (CR 100.2a, 100.4a) ------------------------------


def test_the_registered_list_is_sixty_and_fifteen():
    """CR 100.2a, 100.4a: the counts the tournament list was registered with."""
    deck = allosaurus_deck()

    assert deck.mainboard_size == 60
    assert deck.sideboard_size == 15


def test_the_registered_list_passes_deck_construction():
    """CR 100.2a's four-card limit, applied across deck and sideboard together
    (CR 100.4a). Nature's Claim, Veil of Summer, Pact of Negation and Hooting
    Mandrills are each split between the two boards and must still total four
    or fewer."""
    assert allosaurus_deck().check_legality(card) is not None


def test_every_card_in_the_list_is_a_real_printing():
    """No hand-written card data: every name resolves in the fixture pool,
    the double-faced ones by their front face."""
    deck = allosaurus_deck()

    for name in deck.card_names:
        assert card(name).name.split(" //")[0] == name


# -- starting the game (CR 103) -------------------------------------------


def test_the_opening_hand_is_seven_and_the_library_is_fifty_three():
    """CR 103.5: a hand equal to the starting hand size, normally seven, drawn
    from the sixty-card library CR 401.1 made out of the deck."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert len(alice.hand) + len(alice.library) == 60


def test_the_sideboard_is_set_aside_rather_than_shuffled_in():
    """CR 103.2a: sideboard cards are set aside before the deck becomes the
    library, so none of the fifteen can be drawn."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)
    assert "Mystical Dispute" not in {state.name for state in alice.library + alice.hand}


def test_the_opening_hand_is_drawn_from_this_deck_and_no_other():
    """CR 103.3, 401.1: alice's library is her own shuffled deck. Nothing from
    bob's sixty is in it."""
    game = match().start_game()
    alice = game.player("alice")

    for state in alice.library + alice.hand:
        assert state.card.name.split(" //")[0] in ALLOSAURUS_COMBO_MAIN
    assert "Mountain" not in {state.name for state in alice.library}


def test_the_shuffle_is_a_shuffle_not_the_registered_order():
    """CR 103.3: "in a random order". Two seeds give two different libraries -
    the list is not simply dealt out top to bottom."""

    def sixty(seed: str) -> list[str]:
        alice = match(seed=seed).start_game().player("alice")
        return [state.name for state in alice.hand + alice.library]

    one, two = sixty("one"), sixty("two")

    assert one != two
    # The same sixty cards either way - a shuffle reorders, it does not change
    # what CR 103.2a left in the deck.
    assert sorted(one) == sorted(two)


def test_every_copy_is_its_own_card():
    """Four Allosaurus Riders are four cards sharing one printing."""
    game = match().start_game()
    alice = game.player("alice")

    riders = [s for s in alice.library + alice.hand if s.name == "Allosaurus Rider"]

    assert len(riders) == 4
    assert len({state.id for state in riders}) == 4
    assert len({id(state.card) for state in riders}) == 1


def test_the_game_starts_at_untap_with_both_players_at_twenty():
    """CR 103.4: a starting life total of 20. CR 103.8: the starting player
    takes their first turn."""
    game = match().start_game()

    assert isinstance(game, Game)
    assert game.turn is not None
    # CR 103.5 first: a dealt game rests in the mulligan step, before any turn.
    assert game.turn.step is Step.MULLIGAN
    assert game.turn.turn_number == 0

    game.settle_pregame()

    # CR 103.8: the starting player takes their first turn, which begins at untap.
    assert game.turn.step is Step.UNTAP
    assert all(player.life == 20 for player in game.players)


# -- the archetype's own engine -------------------------------------------


def test_allosaurus_rider_is_pitch_cast_for_two_green_cards():
    """CR 118.9: "an alternative cost is a cost listed in a spell's text ...
    that its controller may pay rather than paying the spell's mana cost."
    Allosaurus Rider prints one, and it is what makes this deck a turn-one
    deck. CR 118.9b makes it optional; CR 613.4a then defines its power from
    its characteristic-defining ability rather than a printed box."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Allosaurus Rider", "Veil of Summer", "Nature's Claim"],
            battlefield=["Forest", "Island"],
        )
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Allosaurus Rider")
    (option,) = casting.alternative_costs
    assert option.description == "exile two green cards from your hand"

    pitched = [
        scenario.find("Veil of Summer", Zone.HAND),
        scenario.find("Nature's Claim", Zone.HAND),
    ]
    casting.use_alternative_cost(choosing=pitched)
    casting.begin_paying().pay()
    rider = scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert rider.zone is Zone.BATTLEFIELD
    assert all(state.zone is Zone.EXILE for state in pitched)
    # CR 613.4a: 1 plus the two lands she controls.
    assert scenario.game.power_of(rider) == 3
    # CR 118.9: paid instead of the mana cost, so neither land was tapped.
    assert len(scenario.untapped_sources("Forest", "Island")) == 2


# -- Gaps -----------------------------------------------------------------


def test_neoform_turns_the_pitched_rider_into_a_fatty():
    """The whole archetype in one line: pitch Allosaurus Rider (mana value 7,
    CR 118.9c - the alternative cost does not change it), sacrifice it to
    Neoform (CR 118.8a additional cost), and search out the mana-value-8
    creature. CR 701.23a is the search, CR 701.23b why failing to find would
    have been legal, and CR 701.24a/701.24b the shuffle that follows.

    The number the search is bounded by is not printed on Neoform at all: it is
    CR 202.3's mana value of the creature that paid CR 118.8a's additional
    cost, read back off `Game.cast_record(spell).additional_cost_cards` -
    CR 601.2h had it sacrificed before the spell was ever put on the stack, so
    by resolution it is a card in a graveyard, whose mana value is the same
    number it was on the battlefield.

    Eldritch Evolution is *almost* the same clause and is still unread: its
    "Search your library for a creature card with mana value X or less, where X
    is 2 plus the sacrificed creature's mana value" is the comparison version
    of the same sentence, but its third sentence, "Exile Eldritch Evolution",
    replaces where the resolving spell itself goes (CR 614.1 / CR 608.2n's
    graveyard), which needs a `machines/replacement.py` effect this engine has
    no shape for yet - and CR 608.2c has no notion of running half of it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Allosaurus Rider", "Veil of Summer", "Nature's Claim", "Neoform"],
            library=["Griselbrand", "Forest", "Forest"],
            battlefield=["Forest", "Island"],
        )
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Allosaurus Rider")
    casting.use_alternative_cost(
        choosing=[
            scenario.find("Veil of Summer", Zone.HAND),
            scenario.find("Nature's Claim", Zone.HAND),
        ]
    )
    casting.begin_paying().pay()
    rider = scenario.put_on_stack(casting)
    scenario.resolve_top()

    # CR 118.8a's printed additional cost, chosen and paid as part of casting
    # (CR 601.2h) - the Rider is the creature the search's number is read off.
    scenario.will_choose_cards(scenario.find("Griselbrand", Zone.LIBRARY))
    scenario.cast_and_resolve(
        "Neoform",
        *scenario.untapped_sources("Forest", "Island"),
        sacrificing=[rider],
    )

    assert rider.zone is Zone.GRAVEYARD
    griselbrand = scenario.find("Griselbrand", Zone.BATTLEFIELD)
    assert griselbrand.zone is Zone.BATTLEFIELD
    # CR 202.3 off the two printed mana costs: {5}{G}{G} is 7, {4}{B}{B}{B}{B}
    # is 8, and 8 is the "1 plus" the sacrificed creature's. The alternative
    # cost the Rider was cast for never touched its mana value (CR 118.9c).
    assert rider.card.mana_cost == "{5}{G}{G}"
    assert griselbrand.card.mana_cost == "{4}{B}{B}{B}{B}"
    assert griselbrand.counter_count("+1/+1") == 1


def test_summoners_pact_fetches_the_rider_and_bills_the_next_upkeep():
    """The other half of the turn-one draw: a {0} tutor whose price is a
    CR 603.7 delayed triggered ability, created as the spell resolves
    (CR 603.7a, 610.2). CR 701.23 is the search, CR 701.24b the shuffle.

    Both halves work, so this is an assertion and not an `xfail`: the card is
    found, and the unpaid bill ends the game at alice's next upkeep.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Summoner's Pact"],
            library=["Allosaurus Rider", *["Forest"] * 8],
            battlefield=["Forest"],
        )
        .player("bob", library=["Island"] * 8, battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.will_choose_cards(scenario.find("Allosaurus Rider", Zone.LIBRARY))
    pact = scenario.cast_and_resolve("Summoner's Pact")

    assert pact.zone is Zone.GRAVEYARD
    assert [state.name for state in scenario.game.player("alice").hand] == ["Allosaurus Rider"]
    (delayed,) = scenario.game.delayed_triggers.triggers
    assert delayed.controller == "alice"
    assert delayed.step is Step.UPKEEP

    # It fires at her next upkeep, two turns on.
    for _ in range(30):
        if scenario.stack_names():
            break
        scenario.advance()

    assert scenario.stack_names() == ["Summoner's Pact's triggered ability"]
    assert scenario.step is Step.UPKEEP

    # Nothing pays it, so CR 104.3e ends the game for her, and CR 104.5 takes
    # her out of it.
    scenario.pass_until_resolved()

    assert not scenario.game.is_in_game("alice")
