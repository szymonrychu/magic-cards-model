"""The Modern storm decklist, dealt and then played far enough to see whether
its three load-bearing primitives work.

The list is a real registered sixty: pilot IrIWANG, 2026-08-29, source deck
videre-58655658, archetype "storm". It is the Lesson/Learn build of the
archetype - First Day of Class, Highway Robbery and maindeck Stormscale Scion
where the more common Ruby Storm list plays Reckless Impulse, Wish and
Grapeshot - so it is a different deck from `decks/ruby_storm.txt`, not the same
sixty under another name. The three "Mountain" rows the source list prints
separately are merged into one here.

Dealing the game is CR 103 in order: sideboards set aside (CR 103.2a), each
deck becomes its owner's library (CR 401.1), libraries shuffled (CR 103.3),
life set to 20 (CR 103.4), seven cards drawn (CR 103.5). Construction is
CR 100.2a (sixty-card minimum, four-copy limit) and CR 100.4a (a sideboard of
no more than fifteen, with the four-copy limit spanning both boards).

Then three archetype primitives, because a storm deck that cannot count its
own spells is dead on the table:

- a ritual has to actually put mana in the pool (CR 106.4),
- Ruby Medallion's static discount has to reach the total cost (CR 601.2f),
- storm has to copy the spell once per spell cast before it (CR 702.40a).

Every CR number in this module was looked up with `knowledge_search` in the
session that wrote it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.models import Color, Deck, Match, Player, Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

#: Storm - pilot IrIWANG, 2026-08-29, source deck videre-58655658. Sixty cards.
STORM_MAINBOARD = {
    "Ruby Medallion": 4,
    "Ral, Monsoon Mage": 4,
    "First Day of Class": 4,
    "Highway Robbery": 4,
    "Hex Magic": 4,
    "Manamorphose": 4,
    "Pyretic Ritual": 4,
    "Desperate Ritual": 4,
    "Past in Flames": 3,
    "Wrenn's Resolve": 2,
    "Stormscale Scion": 2,
    "Valakut Awakening": 1,
    "Mountain": 3,
    "Scalding Tarn": 3,
    "Bloodstained Mire": 3,
    "Wooded Foothills": 3,
    "Arid Mesa": 2,
    "Thundering Falls": 2,
    "Steam Vents": 1,
    "Stomping Ground": 1,
    "Commercial District": 1,
    "Boseiju, Who Endures": 1,
}

#: The same list's fifteen-card sideboard, all Lessons plus the Learn targets.
STORM_SIDEBOARD = {
    "Divide by Zero": 3,
    "Boomerang Basics": 2,
    "Redirect Lightning": 2,
    "Abandon Attachments": 1,
    "Improvisation Capstone": 1,
    "Mascot Exhibition": 1,
    "Iroh's Demonstration": 1,
    "It'll Quench Ya!": 1,
    "Origin of Metalbending": 1,
    "Price of Freedom": 1,
    "Firebending Lesson": 1,
}


def storm_deck() -> Deck:
    return Deck(mainboard=dict(STORM_MAINBOARD), sideboard=dict(STORM_SIDEBOARD))


def match(seed: int | str = "storm") -> Match:
    """A two-player match with the storm list registered for alice."""
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", storm_deck())
    series.register_deck(
        "bob",
        Deck(mainboard={"Mountain": 48, "Lightning Bolt": 4, "Grizzly Bears": 4, "Shock": 4}),
    )
    return series


# -- construction (CR 100.2a, 100.4a) -------------------------------------


def test_the_storm_list_is_a_legal_sixty_with_a_fifteen_card_sideboard():
    """CR 100.2a: a sixty-card minimum and no more than four of any nonbasic.

    CR 100.4a: a sideboard of no more than fifteen, with that same four-copy
    limit applying to the combined deck and sideboard.
    """
    deck = storm_deck()

    assert deck.mainboard_size == 60
    assert sum(STORM_SIDEBOARD.values()) == 15
    assert deck.problems(card) == []
    assert deck.is_legal(card)


def test_every_card_in_the_list_is_a_real_printing():
    """No hand-written card data: each name resolves in the fixture pool."""
    for name in list(STORM_MAINBOARD) + list(STORM_SIDEBOARD):
        assert card(name).name.split("//")[0].strip() == name


# -- dealing the game (CR 103) --------------------------------------------


def test_the_storm_deck_deals_an_opening_hand_of_seven():
    """CR 103.5: each player draws a hand equal to their starting hand size.

    CR 401.1: the deck becomes the library, so the fifty-three left behind
    are the sixty minus the seven drawn.
    """
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert len(alice.hand) + len(alice.library) == 60
    assert all(state.zone is Zone.HAND for state in alice.hand)
    assert all(state.card.name.split("//")[0].strip() in STORM_MAINBOARD for state in alice.hand)


def test_the_sideboard_is_set_aside_and_never_in_the_library():
    """CR 103.2a: sideboard cards are set aside before the deck is shuffled."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)
    library_and_hand = {state.card.name for state in alice.library + alice.hand}
    assert not (library_and_hand & set(STORM_SIDEBOARD))


def test_both_players_begin_at_twenty_life():
    """CR 103.4: each player begins the game with a starting life total of 20."""
    game = match().start_game()

    assert game.player("alice").life == 20
    assert game.player("bob").life == 20


def test_the_library_is_shuffled_rather_than_dealt_in_list_order():
    """CR 103.3: each player shuffles their deck into a random order.

    Two seeds deal two different orders out of the same sixty cards - which
    the drawn hand has to be folded back in to see, since CR 103.5 has
    already moved seven of them out of the library by the time this looks.
    """

    def dealt(seed: str) -> list[str]:
        alice = match(seed=seed).start_game().player("alice")
        return [state.card.name for state in alice.library + alice.hand]

    one, two = dealt("a"), dealt("b")

    assert one != two
    assert sorted(one) == sorted(two)


# -- the three primitives the archetype stands on -------------------------


def test_a_ritual_nets_mana_into_the_pool():
    """CR 106.4: "add mana" puts that mana into the player's mana pool.

    Two Mountains pay Pyretic Ritual's {1}{R}; the ritual then adds {R}{R}{R},
    so the pool ends at three red - a net gain of one, which is the whole
    reason the deck plays it.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Pyretic Ritual"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Pyretic Ritual", auto=True)

    assert scenario.player("alice").mana_pool.floating == {Color.RED: 3}


def test_ruby_medallion_discounts_a_red_spell():
    """CR 601.2f: cost-reduction effects are applied to the total cost.

    Hex Magic is printed at {2}{R}. With a Ruby Medallion out it costs
    {1}{R}; with no Medallion the printed cost stands. CR 118.7a keeps the
    generic-mana discount off the coloured pip.
    """
    with_medallion = (
        Scenario()
        .player("alice", hand=["Hex Magic"], battlefield=["Ruby Medallion", "Mountain"])
        .player("bob")
        .build()
    )
    with_medallion.start_at(Step.PRECOMBAT_MAIN)
    spell = with_medallion.find("Hex Magic", Zone.HAND, "alice")
    discounted = Casting(
        spell=spell, caster="alice", origin_zone=Zone.HAND, game=with_medallion.game
    ).total_cost

    without = (
        Scenario()
        .player("alice", hand=["Hex Magic"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    without.start_at(Step.PRECOMBAT_MAIN)
    spell = without.find("Hex Magic", Zone.HAND, "alice")
    printed = Casting(
        spell=spell, caster="alice", origin_zone=Zone.HAND, game=without.game
    ).total_cost

    assert str(printed) == "{2}{R}"
    assert str(discounted) == "{1}{R}"


def test_storm_copies_the_spell_once_per_spell_cast_before_it():
    """CR 702.40a: "copy it for each other spell that was cast before it this
    turn."

    Two rituals first, then Stormscale Scion: the storm trigger sees two
    earlier spells and makes two copies, so three Dragons end up on the
    battlefield. CR 707.10 keeps the copies out of the cast count, which is
    what stops the count from running away.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Pyretic Ritual", "Pyretic Ritual", "Stormscale Scion"],
            battlefield=["Mountain"] * 8,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Pyretic Ritual", auto=True)
    scenario.cast_and_resolve("Pyretic Ritual", auto=True)
    cast_this_turn = scenario.game.spells_cast_this_turn["alice"]
    assert [state.name for state in cast_this_turn] == ["Pyretic Ritual", "Pyretic Ritual"]

    scenario.cast_onto_stack("Stormscale Scion", auto=True)
    assert scenario.stack_names() == ["Stormscale Scion", "Stormscale Scion's triggered ability"]

    while scenario.game.stack:
        scenario.resolve_top()

    dragons = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and state.name == "Stormscale Scion"
    ]
    assert len(dragons) == 3
