"""A search whose text says to reveal the found card shows it to every player,
and the card stays known in its owner's hand.

- **CR 701.23a** - "To search for a card in a zone, look at all cards in that
  zone (even if it's a hidden zone) and find a card that matches the given
  description."
- **CR 701.23e** - "If the effect that contains the search instruction doesn't
  also contain instructions to reveal the found card(s), then they're not
  revealed." So a printed "reveal it" / "reveal that card" / "reveal them"
  does reveal, and a search without it reveals nothing.
- **CR 701.20a** - "To reveal a card, show that card to all players for a brief
  time." **CR 701.20b** - "Revealing a card doesn't cause it to leave the zone
  it's in", so the card is revealed from the library, then put into the hand.

The reveal is recorded as a public `Reveal` (`viewers=None`) against the
library, and the move library-to-hand is the known-draw carry (an owner
policy, not a CR rule - see `test_known_card_drawn_stays_known.py`): the card
is known in hand until it changes zones again. The shuffle comes last, after
the put, in the order the text prints it, so the carry sees a live record.

Every search-and-put template that reads "reveal" goes through one funnel,
`Game.search_and_put`: the singular search (Expedition Map, Ranger-Captain of
Eos, Trinket Mage's "reveal that card"), a spell (Sylvan Scrying), the counted
"up to N ... reveal them" (Tooth and Nail), the board-count bound (Beseech the
Queen), and a conditional consequence (Formidable Speaker). Trinket Mage,
Sylvan Scrying, Beseech the Queen, Tooth and Nail and Demonic Tutor are listed
in neither `~/Documents/mtg-decks/decks/*/decklist.txt` nor
`magic-cards-model-api/decks/*.txt`.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario, mana_from


def known(game: Game, viewer: str) -> list[tuple[str, Zone, int | None, bool]]:
    return [
        (entry.card_name, entry.zone, entry.index_from_top, entry.carried)
        for entry in game.known_to(viewer)
    ]


def _resolve_everything(scenario: Scenario) -> None:
    game = scenario.game
    for _ in range(10):
        game.put_triggers_on_stack()
        if not game.stack:
            return
        scenario.pass_until_resolved()


# -- the reported cards (B2-04) -----------------------------------------------


def test_expedition_map_s_revealed_land_is_known_to_the_opponent_in_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Expedition Map", "Forest", "Forest"],
            library=["Grizzly Bears", "Urza's Tower", "Forest"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card_map = scenario.find("Expedition Map", Zone.BATTLEFIELD)
    tower = scenario.find("Urza's Tower", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(tower, username="alice", source="Expedition Map")

    scenario.activate(
        card_map, *scenario.untapped_sources("Forest", "Forest"), sacrificing=[card_map]
    )
    scenario.pass_until_resolved()

    assert tower.zone is Zone.HAND
    (reveal,) = scenario.game.reveals
    assert reveal.card_id == tower.id
    assert reveal.viewers is None, "CR 701.20a: shown to all players"
    assert reveal.zone is Zone.LIBRARY, "CR 701.20b: revealed where it was found"
    assert reveal.source == "Expedition Map"
    assert known(scenario.game, "bob") == [("Urza's Tower", Zone.HAND, None, True)]
    assert known(scenario.game, "alice") == [("Urza's Tower", Zone.HAND, None, True)]


def test_ranger_captain_s_revealed_creature_is_known_to_the_opponent_in_hand():
    scenario = (
        Scenario()
        .player(
            "bob",
            hand=["Ranger-Captain of Eos"],
            library=["Grizzly Bears", "Ocelot Pride", "Plains"],
            battlefield=["Plains", "Plains", "Plains"],
        )
        .player("alice")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pride = scenario.find("Ocelot Pride", Zone.LIBRARY, "bob")
    scenario.will_take_the_may(True, username="bob", source="Ranger-Captain of Eos")
    scenario.will_choose_cards(pride, username="bob", source="Ranger-Captain of Eos")

    scenario.cast_and_resolve(
        "Ranger-Captain of Eos", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    _resolve_everything(scenario)

    assert pride.zone is Zone.HAND
    assert known(scenario.game, "alice") == [("Ocelot Pride", Zone.HAND, None, True)]


def test_the_revealed_find_stops_being_known_when_it_leaves_the_hand():
    """The carry lasts until the card's next zone change (CR 400.7)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Expedition Map", "Forest", "Forest"],
            library=["Urza's Tower", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card_map = scenario.find("Expedition Map", Zone.BATTLEFIELD)
    tower = scenario.find("Urza's Tower", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(tower, username="alice", source="Expedition Map")
    scenario.activate(
        card_map, *scenario.untapped_sources("Forest", "Forest"), sacrificing=[card_map]
    )
    scenario.pass_until_resolved()
    assert known(scenario.game, "bob") == [("Urza's Tower", Zone.HAND, None, True)]

    scenario.game.discard_cards("alice", [tower])

    assert tower.zone is Zone.GRAVEYARD
    assert known(scenario.game, "bob") == []


def test_finding_nothing_reveals_nothing():
    """CR 701.23b: a stated quality need not be found, and a card not found is
    not revealed."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Expedition Map", "Forest", "Forest"],
            library=["Urza's Tower", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card_map = scenario.find("Expedition Map", Zone.BATTLEFIELD)
    scenario.will_choose_cards(username="alice", source="Expedition Map")

    scenario.activate(
        card_map, *scenario.untapped_sources("Forest", "Forest"), sacrificing=[card_map]
    )
    scenario.pass_until_resolved()

    assert scenario.player("alice").hand == []
    assert scenario.game.reveals == []
    assert known(scenario.game, "bob") == []


# -- no "reveal" printed (CR 701.23e) ------------------------------------------


def test_a_search_to_hand_without_reveal_records_nothing():
    """Demonic Tutor: "Search your library for a card, put that card into your
    hand, then shuffle." No reveal is printed, so nobody but the searcher ever
    sees the card, and the searcher's view ends in the shuffle."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Demonic Tutor"],
            library=["Grizzly Bears", "Lightning Bolt"],
            battlefield=["Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(bolt, username="alice", source="Demonic Tutor")

    scenario.cast_and_resolve("Demonic Tutor", *scenario.untapped_sources("Swamp", "Swamp"))

    assert bolt.zone is Zone.HAND
    assert scenario.game.reveals == []
    assert known(scenario.game, "bob") == []
    assert known(scenario.game, "alice") == []


# -- generality: other wordings and other templates ---------------------------


def test_trinket_mage_s_reveal_that_card_is_the_same_reveal():
    """Trinket Mage prints "reveal that card", not "reveal it", on a trigger."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Trinket Mage"],
            library=["Grizzly Bears", "Ornithopter", "Island"],
            battlefield=["Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.find("Ornithopter", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, username="alice", source="Trinket Mage")
    scenario.will_choose_cards(thopter, username="alice", source="Trinket Mage")

    scenario.cast_and_resolve(
        "Trinket Mage", *scenario.untapped_sources("Island", "Island", "Island")
    )
    _resolve_everything(scenario)

    assert thopter.zone is Zone.HAND
    assert known(scenario.game, "bob") == [("Ornithopter", Zone.HAND, None, True)]


def test_sylvan_scrying_a_spell_s_revealed_find_is_known():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sylvan Scrying"],
            library=["Grizzly Bears", "Breeding Pool"],
            battlefield=["Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pool = scenario.find("Breeding Pool", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(pool, username="alice", source="Sylvan Scrying")

    scenario.cast_and_resolve("Sylvan Scrying", *scenario.untapped_sources("Forest", "Forest"))

    assert pool.zone is Zone.HAND
    assert known(scenario.game, "bob") == [("Breeding Pool", Zone.HAND, None, True)]


def test_beseech_the_queen_s_revealed_find_is_known():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Beseech the Queen"],
            library=["Lightning Bolt", "Grizzly Bears"],
            battlefield=["Swamp", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(bears, username="alice", source="Beseech the Queen")

    scenario.cast_and_resolve(
        "Beseech the Queen", *scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    )

    assert bears.zone is Zone.HAND
    assert known(scenario.game, "bob") == [("Grizzly Bears", Zone.HAND, None, True)]


def test_tooth_and_nail_reveal_them_makes_both_finds_known():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Tooth and Nail"],
            library=["Craw Wurm", "Forest", "Grizzly Bears"],
            battlefield=["Forest"] * 7,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.find("Craw Wurm", Zone.LIBRARY, "alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(wurm, bears, username="alice", source="Tooth and Nail")

    casting = scenario.cast("Tooth and Nail")
    casting.choose_modes([1])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources(*["Forest"] * 7):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert wurm.zone is Zone.HAND and bears.zone is Zone.HAND
    assert sorted(known(scenario.game, "bob")) == [
        ("Craw Wurm", Zone.HAND, None, True),
        ("Grizzly Bears", Zone.HAND, None, True),
    ]


def test_formidable_speaker_s_conditional_search_reveals_its_find():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Formidable Speaker", "Lightning Bolt"],
            library=["Forest", "Grizzly Bears"],
            battlefield=["Forest"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_discard(bolt, username="alice")
    scenario.will_choose_cards(bears, username="alice", source="Formidable Speaker")

    scenario.cast_and_resolve("Formidable Speaker", *scenario.untapped_sources(*["Forest"] * 3))
    _resolve_everything(scenario)

    assert bears.zone is Zone.HAND
    assert known(scenario.game, "bob") == [("Grizzly Bears", Zone.HAND, None, True)]
