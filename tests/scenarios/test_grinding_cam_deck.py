"""Smoke test for the Modern "grinding cam" decklist.

The list is `magic-cards-model-api/decks/grinding_cam.txt` - pilot **AgentP**,
tournament date **2026-08-29**, source deck `videre-58656072` - a real
registered sixty plus fifteen, not an aggregate. Every name resolves to a real
Scryfall printing in `tests/fixtures/cards`; nothing here is hand-written.

What this file asserts is CR 103 for this particular deck, and nothing else. It
is deliberately not a mechanics file: the deck's mechanics are surveyed in
`docs/deck-gaps/grinding-cam.md`, and the gaps found there are large enough
(Mox Amber makes mana it should not, Loki never triggers, Metallic Rebuke
counters nothing) that a scenario driving them would have to be bent until it
passed. The one such assertion here is `xfail(strict=True)`.

Rules used, each looked up with `knowledge_search` while writing this file:

- **CR 100.2a** - constructed minimum deck size is 60, four copies of a card.
- **CR 100.4a** - a constructed sideboard is at most fifteen cards, and the
  four-card limit spans deck and sideboard together.
- **CR 103.2a** - sideboard cards are set aside before the game begins.
- **CR 103.3** - each player shuffles their deck into a random order.
- **CR 103.4** - each player begins with a starting life total of 20.
- **CR 103.5** - each player draws a number of cards equal to their starting
  hand size, normally seven.
- **CR 103.8a** - in a two-player game, the player who plays first skips the
  draw step of their first turn. (Not 103.7: an older test in this directory
  cites 103.7 for this, which is wrong.)
- **CR 401.1** - when a game begins, each player's deck becomes their library.
- **CR 402.1** - the hand is where a player holds cards that have been drawn.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Deck, DeckLimits, Match, Player, Zone
from tests.cards import card

#: `magic-cards-model-api/decks/grinding_cam.txt`, mainboard. 60 cards.
GRINDING_CAM_MAIN = {
    "Emry, Lurker of the Loch": 4,
    "Tamiyo, Inquisitive Student": 4,
    "Key to the Side-Door": 4,
    "Mox Amber": 4,
    "Mox Opal": 4,
    "Pithing Needle": 1,
    "Grinding Station": 3,
    "Island": 4,
    "Metallic Rebuke": 4,
    "Sewer-veillance Cam": 4,
    "Sink into Stupor": 3,
    "Urza's Saga": 4,
    "Aether Spellbomb": 1,
    "Minamo, School at Water's Edge": 3,
    "Tormod's Crypt": 1,
    "Mishra's Bauble": 4,
    "Otawara, Soaring City": 4,
    "Loki, God of Mischief": 4,
}

#: The same list's sideboard. 15 cards.
GRINDING_CAM_SIDE = {
    "Spell Snare": 1,
    "Consign to Memory": 4,
    "Harbinger of the Seas": 2,
    "Torpor Orb": 2,
    "Strix Serenade": 1,
    "Dismember": 2,
    "Soul-Guide Lantern": 1,
    "Force of Negation": 2,
}


def grinding_cam() -> Deck:
    return Deck(
        mainboard=GRINDING_CAM_MAIN,
        sideboard=GRINDING_CAM_SIDE,
        limits=DeckLimits.constructed(),
    )


def match(seed: int | str = "grinding-cam") -> Match:
    """A grinding-cam mirror.

    Both seats register the same registered list rather than pairing it against
    a second archetype: that keeps every printing in this file inside the one
    decklist being added, and it makes the "each seat gets its own physical
    cards" assertion below sharper, since the two libraries have to differ
    while holding card-for-card the same seventy-five.
    """
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", grinding_cam())
    series.register_deck("bob", grinding_cam())
    return series


# -- the list itself (CR 100.2a, CR 100.4a) --------------------------------


def test_the_registered_list_is_sixty_and_fifteen():
    """CR 100.2a's minimum sixty, CR 100.4a's fifteen-card sideboard."""
    deck = grinding_cam()

    assert deck.mainboard_size == 60
    assert deck.sideboard_size == 15


def test_the_list_is_legal_under_constructed_limits():
    """CR 100.2a's four-copy limit, spanning the sideboard per CR 100.4a.

    `Deck.check_legality` raises `DeckIllegal` listing every problem, so a
    clean return is the assertion.
    """
    assert grinding_cam().check_legality(card).mainboard_size == 60


def test_only_basic_lands_may_exceed_four_copies_and_none_here_do():
    """CR 100.2a: any number of basic lands, at most four of anything else.

    Four Island is the deck's only basic, and four is not an exception - so
    every count in the combined seventy-five is at or under four, which is why
    the legality check above has nothing to say.
    """
    deck = grinding_cam()

    for name in deck.card_names:
        assert deck.total_copies(name) <= 4, name


def test_every_name_resolves_to_a_real_printing():
    """No hand-written card json: every name is a fixture from Scryfall."""
    for name in grinding_cam().card_names:
        assert card(name) is not None


# -- dealing the game (CR 103.2a - CR 103.5) --------------------------------


def test_the_opening_hand_is_seven_and_the_library_is_the_rest():
    """CR 103.5's starting hand size of seven, out of CR 401.1's library."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert len(alice.hand) + len(alice.library) == 60


def test_the_opening_hand_is_in_the_hand_zone_and_comes_from_this_deck():
    """CR 402.1: the hand holds what was drawn - from this deck, not any other."""
    game = match().start_game()
    alice = game.player("alice")

    assert all(state.zone is Zone.HAND for state in alice.hand)
    # Sink into Stupor and Tamiyo are double-faced, so the printed name carries
    # both faces; the decklist names only the front.
    assert all(state.name.split(" //")[0] in GRINDING_CAM_MAIN for state in alice.hand)


def test_the_library_holds_only_mainboard_cards():
    """CR 401.1: the deck becomes the library - the sideboard is not in it."""
    game = match().start_game()
    alice = game.player("alice")

    in_library = {state.name.split(" //")[0] for state in alice.library}

    assert in_library <= set(GRINDING_CAM_MAIN)
    assert "Consign to Memory" not in in_library
    assert "Torpor Orb" not in in_library


def test_the_sideboard_is_set_aside_and_never_shuffled_in():
    """CR 103.2a: sideboard cards are set aside before the deck is shuffled."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)
    assert len(alice.library) + len(alice.hand) == 60


def test_both_seats_are_dealt_their_own_physical_copies():
    """One list per seat, shuffled separately (CR 103.3), dealt separately.

    A mirror is the strict version of this: the two libraries must be in
    different orders and yet hold card-for-card the same sixty, and no card
    object may appear in both seats.
    """
    game = match().start_game()
    alice, bob = game.player("alice"), game.player("bob")

    assert len(bob.hand) == 7
    assert len(bob.library) == 53
    assert [s.name for s in alice.library] != [s.name for s in bob.library]
    assert sorted(s.name for s in alice.library + alice.hand) == sorted(
        s.name for s in bob.library + bob.hand
    )
    assert not {s.id for s in alice.library + alice.hand} & {s.id for s in bob.library + bob.hand}


def test_each_copy_is_its_own_card_sharing_one_printing():
    """Four Urza's Sagas are four cards, not one card counted four times."""
    game = match().start_game()
    alice = game.player("alice")

    sagas = [s for s in alice.library + alice.hand if s.name == "Urza's Saga"]

    assert len(sagas) == 4
    assert len({state.id for state in sagas}) == 4
    assert len({id(state.card) for state in sagas}) == 1


def test_life_totals_start_at_twenty():
    """CR 103.4: each player begins with a starting life total of 20."""
    game = match().start_game()

    assert all(player.life == 20 for player in game.players)


def test_the_shuffle_is_seeded_and_reproducible():
    """CR 103.3's random order, made deterministic by the match seed."""
    first = [s.name for s in match(seed="one").start_game().player("alice").library]
    second = [s.name for s in match(seed="one").start_game().player("alice").library]
    third = [s.name for s in match(seed="two").start_game().player("alice").library]

    assert first == second
    assert first != third
    assert sorted(first) != []


def test_the_starting_player_skips_their_first_draw_step():
    """CR 103.8a, not CR 103.7.

    In a two-player game the player who plays first skips the draw step of
    their first turn, so their hand is still the seven of CR 103.5 when the
    first main phase arrives.
    """
    game = match().start_game()
    starting = game.turn.active_player
    player = game.player(starting)

    assert game.turn.step is Step.UNTAP
    assert len(player.hand) == 7

    while game.turn.step is not Step.PRECOMBAT_MAIN:
        game.advance(game.controller_of_player(game.turn.active_player))

    assert len(player.hand) == 7, "CR 103.8a: no draw on the starting player's first turn"


# -- what the engine cannot do with this deck yet ---------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Mox Amber's 'among legendary creatures and planeswalkers you control' "
        "qualifier is dropped: parse_mana_abilities reads only 'Add one mana of "
        "any color', so a Mox Amber with no legends on the battlefield adds mana "
        "it should not (CR 605.2 - a mana ability stays one even when the game "
        "state does not let it produce mana). See docs/deck-gaps/grinding-cam.md."
    ),
)
def test_mox_amber_adds_nothing_without_a_legendary_creature_or_planeswalker():
    from magic_cards_model.models import Color
    from tests.scenarios.harness import Scenario

    scenario = Scenario().player("alice", battlefield=["Mox Amber"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (amber,) = scenario.untapped_sources("Mox Amber")

    with pytest.raises(ValueError):
        scenario.activate(amber, color=Color.BLUE)
