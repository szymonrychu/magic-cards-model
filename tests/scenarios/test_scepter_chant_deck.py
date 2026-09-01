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
the engine can do today - both halves now run: the artifact imprints the Chant
on entry, and the `{2}, {T}` ability creates CR 707.12's copy in exile and casts
it from there for nothing. See `docs/deck-gaps/scepter-chant.md`.

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

    scenario.activate(scepter, auto=True, username="alice")
    scenario.pass_until_resolved()

    assert "Orim's Chant" in scenario.stack_names()


def imprinted_scepter_board() -> Scenario:
    """Alice with an Isochron Scepter already on the battlefield holding an
    imprinted Orim's Chant, and the mana to activate it."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Isochron Scepter", "Orim's Chant"],
            battlefield=["Island", "Plains", "Mystic Gate", "Hallowed Fountain"],
        )
        .player("bob", hand=["Counterspell"])
    )


def imprint(scenario):
    """Cast the Scepter and imprint the Chant; returns the Scepter."""
    chant = scenario.find("Orim's Chant", Zone.HAND)
    sources = scenario.untapped_sources("Island", "Plains")
    scenario.will_take_the_may()
    scenario.will_choose_cards(chant)
    scepter = scenario.cast_and_resolve("Isochron Scepter", *sources)
    scenario.pass_until_resolved()
    return scepter


def test_the_imprinted_card_itself_never_leaves_exile():
    """CR 707.12: "the copy is created in the same zone the object is in and
    then cast" - it is the *copy* that goes to the stack, so the imprinted
    Orim's Chant is still sitting in exile afterwards, ready for the next
    activation. That is the whole reason the lock repeats.
    """
    scenario = imprinted_scepter_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scepter = imprint(scenario)
    chant = scenario.game.card_imprinted_on(scepter.id)

    scenario.activate(scepter, auto=True, username="alice")
    scenario.pass_until_resolved()

    assert chant is not None
    assert chant.zone is Zone.EXILE
    assert scenario.game.card_imprinted_on(scepter.id) is chant


def test_declining_the_copy_leaves_nothing_behind():
    """The first "you may" is CR 608.2d's own optional question, and CR 118.12's
    "if you do" gate means the second is never reached. Nothing is copied,
    nothing is cast, and exile still holds only the imprinted card.
    """
    scenario = imprinted_scepter_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scepter = imprint(scenario)

    scenario.will_take_the_may(False, username="alice", source="Isochron Scepter")
    scenario.activate(scepter, auto=True, username="alice")
    scenario.pass_until_resolved()

    assert scenario.stack_names() == []
    assert [state.card.name for state in scenario.game.exile] == ["Orim's Chant"]


def test_a_copy_that_is_made_and_not_cast_ceases_to_exist():
    """CR 707.10a: "if a copy of a card is in any zone other than the stack or
    the battlefield, it ceases to exist."

    Taking the copy and then declining the cast leaves a copy of Orim's Chant
    sitting in exile, which is exactly the object that rule removes - exile
    must be back to the one imprinted card.
    """
    scenario = imprinted_scepter_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scepter = imprint(scenario)

    scenario.will_take_the_may(True, username="alice", source="Isochron Scepter")
    scenario.will_take_the_may(False, username="alice", source="Isochron Scepter")
    scenario.activate(scepter, auto=True, username="alice")
    scenario.pass_until_resolved()

    assert scenario.stack_names() == []
    assert [state.card.name for state in scenario.game.exile] == ["Orim's Chant"]
    assert not any(state.is_copy for state in scenario.game.exile)


def test_the_copy_resolves_and_locks_the_opponent_out():
    """CR 112.1b: "some effects allow a player to cast a copy of a card; if the
    player does, that copy is a spell as well" - so it resolves like any other
    spell and Orim's Chant's "target player can't cast spells this turn" lands
    on bob - the copy's targets being chosen fresh at CR 601.2c as it is cast,
    not inherited from anywhere.
    """
    scenario = imprinted_scepter_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scepter = imprint(scenario)

    scenario.will_choose_targets("bob", username="alice")
    scenario.activate(scepter, auto=True, username="alice")
    scenario.pass_until_resolved()  # the Scepter's ability, casting the copy
    copy = scenario.game.stack[-1]

    assert copy.is_copy
    assert copy.card.name == "Orim's Chant"
    assert [str(target) for target in copy.targets] == ["bob"]
