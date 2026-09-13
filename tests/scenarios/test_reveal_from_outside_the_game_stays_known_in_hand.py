"""A card revealed from outside the game and put into its owner's hand is a
card every player knows in that hand.

- **CR 400.11a** - "Cards in a player's sideboard are outside the game."
- **CR 108.3b** - "Some spells and abilities allow a player to take cards they
  own from outside the game and bring them into the game."
- **CR 701.20a** - "To reveal a card, show that card to all players for a brief
  time." **CR 701.20b** - "Revealing a card doesn't cause it to leave the zone
  it's in", so the reveal is recorded against the sideboard and the card is
  then put into the hand.
- **CR 400.7** - the move makes a new object, so the sideboard record alone
  ends as the card leaves.

Every player watched the card be revealed and then go into that hand, so -
the same owner policy as the known-draw carry (`test_known_card_drawn_stays_
known.py`), not a CR rule - a live record follows a card straight from a
hidden group its owner holds (the library, or outside the game) into that
owner's hand, until the card's next zone change.

Karn, the Great Creator's -2 is the reported card. Burning Wish and Living
Wish ("You may reveal a <quality> card you own from outside the game and put it
into your hand. Exile <this>.") are the same instruction on a spell, and so is
Glittering Wish, whose quality is CR 105.2b's color count ("A multicolored
object is two or more of the five colors"); all three are listed in neither
`~/Documents/mtg-decks/decks/*/decklist.txt` nor
`magic-cards-model-api/decks/*.txt`. CR 201.5: "Text that refers to the object
it's on by name means just that particular object", so the Wish exiles itself;
CR 608.2n's graveyard step then finds no spell to put there.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario
from tests.scenarios.test_outside_the_game import KARN_MINUS_TWO, _karn_board, _main_phase


def known(game: Game, viewer: str) -> list[tuple[str, Zone, int | None, bool]]:
    return [
        (entry.card_name, entry.zone, entry.index_from_top, entry.carried)
        for entry in game.known_to(viewer)
    ]


# -- Karn, the Great Creator (B2-05) -------------------------------------------


def test_karn_s_revealed_sideboard_card_is_known_to_the_opponent_in_hand():
    scenario = _karn_board(sideboard=["Grafdigger's Cage", "Lightning Bolt"])
    karn = _main_phase(scenario)
    alice = scenario.player("alice")
    (cage,) = [state for state in alice.outside_the_game if state.name == "Grafdigger's Cage"]
    scenario.will_choose_cards(cage, username="alice")

    scenario.activate(karn, index=KARN_MINUS_TWO)
    scenario.pass_until_resolved()

    assert cage.zone is Zone.HAND
    (reveal,) = scenario.game.reveals
    assert reveal.zone is Zone.SIDEBOARD, "CR 701.20b: shown where it sat"
    assert known(scenario.game, "bob") == [("Grafdigger's Cage", Zone.HAND, None, True)]
    assert known(scenario.game, "alice") == [("Grafdigger's Cage", Zone.HAND, None, True)]


def test_karn_s_fetched_card_stops_being_known_when_it_leaves_the_hand():
    scenario = _karn_board(sideboard=["Grafdigger's Cage"])
    karn = _main_phase(scenario)
    alice = scenario.player("alice")
    (cage,) = list(alice.outside_the_game)
    scenario.will_choose_cards(cage, username="alice")
    scenario.activate(karn, index=KARN_MINUS_TWO)
    scenario.pass_until_resolved()
    assert known(scenario.game, "bob") == [("Grafdigger's Cage", Zone.HAND, None, True)]

    scenario.game.discard_cards("alice", [cage])

    assert known(scenario.game, "bob") == []


def test_karn_choosing_a_face_up_exiled_card_carries_nothing():
    """CR 406.3: already public in exile, never revealed, so nothing to carry."""
    scenario = _karn_board(exile=["Ensnaring Bridge"])
    karn = _main_phase(scenario)
    bridge = scenario.find("Ensnaring Bridge", Zone.EXILE)
    scenario.will_choose_cards(bridge, username="alice")

    scenario.activate(karn, index=KARN_MINUS_TWO)
    scenario.pass_until_resolved()

    assert bridge.zone is Zone.HAND
    assert known(scenario.game, "bob") == []


# -- the Wish shape ------------------------------------------------------------


def _wish_board(wish: str, lands: list[str], sideboard: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[wish], battlefield=lands, sideboard=sideboard)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_burning_wish_reveals_a_sorcery_into_hand_known_to_all_and_exiles_itself():
    scenario = _wish_board(
        "Burning Wish", ["Mountain", "Mountain"], ["Preordain", "Lightning Bolt"]
    )
    alice = scenario.player("alice")
    (preordain,) = [state for state in alice.outside_the_game if state.name == "Preordain"]
    scenario.will_take_the_may(True, username="alice", source="Burning Wish")
    scenario.will_choose_cards(preordain, username="alice", source="Burning Wish")

    wish = scenario.cast_and_resolve(
        "Burning Wish", *scenario.untapped_sources("Mountain", "Mountain")
    )

    assert preordain.zone is Zone.HAND
    assert [state.name for state in alice.outside_the_game] == ["Lightning Bolt"]
    (reveal,) = scenario.game.reveals
    assert reveal.card_id == preordain.id
    assert reveal.zone is Zone.SIDEBOARD
    assert reveal.viewers is None
    assert known(scenario.game, "bob") == [("Preordain", Zone.HAND, None, True)]
    assert wish.zone is Zone.EXILE, "CR 201.5: 'Exile Burning Wish' is this spell"
    assert wish not in alice.graveyard


def test_burning_wish_offers_only_a_card_of_the_stated_quality():
    """A sideboard with no sorcery has no candidate (CR 608.2d); the spell
    still exiles itself."""
    scenario = _wish_board("Burning Wish", ["Mountain", "Mountain"], ["Lightning Bolt"])

    wish = scenario.cast_and_resolve(
        "Burning Wish", *scenario.untapped_sources("Mountain", "Mountain")
    )

    assert scenario.player("alice").hand == []
    assert scenario.game.reveals == []
    assert wish.zone is Zone.EXILE


def test_declining_the_wish_reveals_nothing():
    scenario = _wish_board("Burning Wish", ["Mountain", "Mountain"], ["Preordain"])
    scenario.will_take_the_may(False, username="alice", source="Burning Wish")

    wish = scenario.cast_and_resolve(
        "Burning Wish", *scenario.untapped_sources("Mountain", "Mountain")
    )

    assert scenario.player("alice").hand == []
    assert scenario.game.reveals == []
    assert known(scenario.game, "bob") == []
    assert wish.zone is Zone.EXILE


def test_living_wish_reads_a_two_type_quality():
    scenario = _wish_board("Living Wish", ["Forest", "Forest"], ["Lightning Bolt", "Breeding Pool"])
    alice = scenario.player("alice")
    (pool,) = [state for state in alice.outside_the_game if state.name == "Breeding Pool"]
    scenario.will_take_the_may(True, username="alice", source="Living Wish")
    scenario.will_choose_cards(pool, username="alice", source="Living Wish")

    wish = scenario.cast_and_resolve("Living Wish", *scenario.untapped_sources("Forest", "Forest"))

    assert pool.zone is Zone.HAND
    assert known(scenario.game, "bob") == [("Breeding Pool", Zone.HAND, None, True)]
    assert wish.zone is Zone.EXILE


def test_glittering_wish_reads_a_color_count_quality():
    """CR 105.2b: only a card of two or more colors is offered."""
    scenario = _wish_board(
        "Glittering Wish",
        ["Forest", "Plains"],
        ["Lightning Bolt", "Lightning Helix", "Breeding Pool"],
    )
    alice = scenario.player("alice")
    (helix,) = [state for state in alice.outside_the_game if state.name == "Lightning Helix"]
    scenario.will_take_the_may(True, username="alice", source="Glittering Wish")
    scenario.will_choose_cards(helix, username="alice", source="Glittering Wish")

    wish = scenario.cast_and_resolve(
        "Glittering Wish", *scenario.untapped_sources("Forest", "Plains")
    )

    (offered,) = [d for d in scenario.game.decisions.asked if d.kind.value == "choose_cards"]
    assert offered.cards == (helix.id,)
    assert helix.zone is Zone.HAND
    (reveal,) = scenario.game.reveals
    assert reveal.card_id == helix.id
    assert reveal.viewers is None
    assert known(scenario.game, "bob") == [("Lightning Helix", Zone.HAND, None, True)]
    assert wish.zone is Zone.EXILE
