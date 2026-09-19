""" "Reveal the top N cards of your library. You may put a `<quality>` card from
among them into your hand. Put the rest into your graveyard." - read as one
template, and every revealed card recorded as a public reveal when it is shown.

Every CR number below was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 701.20a** - "To reveal a card, show that card to all players for a
  brief time." All N cards are shown to both players, so each is a public
  record (`viewers=None`) made while the card is still in the library.
- **CR 110.4a** - "The term 'permanent card' is used to refer to a card that
  could be put onto the battlefield. Specifically, it means an artifact,
  battle, creature, enchantment, land, or planeswalker card."
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - reveal, then the hand pick, then the
  graveyard, then (Malevolent Rumble) the Spawn.
- **CR 608.2d** - which card, and whether to take one, are choices made while
  the effect resolves; a card that is not offered cannot be chosen.

The card revealed and put into hand stays known to the opponent under the
known-draw carry (an owner policy, not a CR rule - see
`test_known_card_drawn_stays_known.py`), the same way Ancient Stirrings'
revealed card already does.

Malevolent Rumble is the reported card. Grisly Salvage (a five-card reveal
with a two-type quality) and Satyr Wayfinder (the same template on an enters
trigger) are off-pool proofs that the reader is the template.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.effects import EFFECTS
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario


def known(game: Game, viewer: str) -> list[tuple[str, Zone, int | None, bool]]:
    return [
        (entry.card_name, entry.zone, entry.index_from_top, entry.carried)
        for entry in game.known_to(viewer)
    ]


def _public_reveals(game: Game, source: str):
    return [r for r in game.reveals if r.source == source and r.viewers is None]


def _rumble_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Malevolent Rumble"],
            battlefield=["Forest", "Forest"],
            library=["Eldrazi Temple", "Lightning Bolt", "Forest", "Mishra's Bauble", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_rumble(scenario):
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.cast_and_resolve("Malevolent Rumble", *forests)


def test_malevolent_rumble_is_read_by_the_template_not_a_registry_row():
    assert "Malevolent Rumble" not in EFFECTS


def test_malevolent_rumble_reveals_all_four_publicly_and_the_kept_card_stays_known():
    scenario = _rumble_board()
    alice = scenario.player("alice")
    temple, bolt, forest, bauble = scenario.top_of_library(4)
    stamps = {state.id: state.zone_change_stamp for state in (temple, bolt, forest, bauble)}
    epoch = alice.library_epoch
    scenario.will_take_the_may(source="Malevolent Rumble")
    scenario.will_choose_cards(temple, source="Malevolent Rumble")

    _cast_rumble(scenario)

    reveals = _public_reveals(scenario.game, "Malevolent Rumble")
    assert [r.card_id for r in reveals] == [temple.id, bolt.id, forest.id, bauble.id]
    for reveal in reveals:
        assert reveal.zone is Zone.LIBRARY
        assert reveal.zone_change_stamp == stamps[reveal.card_id]
        assert reveal.library_epoch == epoch

    assert temple.zone is Zone.HAND
    assert {bolt.zone, forest.zone, bauble.zone} == {Zone.GRAVEYARD}
    assert [state.name for state in alice.library] == ["Island"]
    assert known(scenario.game, "bob") == [("Eldrazi Temple", Zone.HAND, None, True)]
    assert ("Eldrazi Temple", Zone.HAND, None, True) in known(scenario.game, "alice")
    spawn = [state for state in scenario.game.battlefield if state.name == "Eldrazi Spawn Token"]
    assert len(spawn) == 1


def test_malevolent_rumble_asks_its_may_about_the_permanent_cards_it_revealed():
    scenario = _rumble_board()
    temple, _bolt, forest, bauble = scenario.top_of_library(4)
    scenario.will_take_the_may(source="Malevolent Rumble")
    scenario.will_choose_cards(bauble, source="Malevolent Rumble")

    _cast_rumble(scenario)

    (may,) = [
        d
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.MAY and d.source == "Malevolent Rumble"
    ]
    assert set(may.cards) == {temple.id, forest.id, bauble.id}
    (choice,) = [
        d
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.CHOOSE_CARDS and d.source == "Malevolent Rumble"
    ]
    assert set(choice.cards) == {temple.id, forest.id, bauble.id}
    assert choice.amount == 1


def test_malevolent_rumble_declined_puts_all_four_in_the_graveyard_and_nothing_is_known():
    scenario = _rumble_board()
    alice = scenario.player("alice")
    four = scenario.top_of_library(4)
    scenario.will_take_the_may(False, source="Malevolent Rumble")

    _cast_rumble(scenario)

    assert len(_public_reveals(scenario.game, "Malevolent Rumble")) == 4
    assert all(state.zone is Zone.GRAVEYARD for state in four)
    assert alice.hand == []
    assert known(scenario.game, "bob") == []


def test_malevolent_rumble_cannot_take_a_nonpermanent_card():
    scenario = _rumble_board()
    _temple, bolt, _forest, _bauble = scenario.top_of_library(4)
    scenario.will_take_the_may(source="Malevolent Rumble")
    scenario.will_choose_cards(bolt, source="Malevolent Rumble")

    with pytest.raises(ValueError, match="not offered"):
        _cast_rumble(scenario)


def test_grisly_salvage_reveals_five_and_takes_a_land_that_stays_known():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grisly Salvage"],
            battlefield=["Swamp", "Forest"],
            library=["Grizzly Bears", "Lightning Bolt", "Forest", "Sol Ring", "Island", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears, bolt, forest, sol_ring, island = scenario.top_of_library(5)
    scenario.will_take_the_may(source="Grisly Salvage")
    scenario.will_choose_cards(forest, source="Grisly Salvage")

    mana = scenario.untapped_sources("Swamp", "Forest", username="alice")
    scenario.cast_and_resolve("Grisly Salvage", *mana)

    reveals = _public_reveals(scenario.game, "Grisly Salvage")
    assert [r.card_id for r in reveals] == [bears.id, bolt.id, forest.id, sol_ring.id, island.id]
    (choice,) = [
        d
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.CHOOSE_CARDS and d.source == "Grisly Salvage"
    ]
    assert set(choice.cards) == {bears.id, forest.id, island.id}, "creature or land cards"
    assert forest.zone is Zone.HAND
    assert {bears.zone, bolt.zone, sol_ring.zone, island.zone} == {Zone.GRAVEYARD}
    assert [state.name for state in alice.library] == ["Swamp"]
    assert known(scenario.game, "bob") == [("Forest", Zone.HAND, None, True)]


def test_satyr_wayfinders_enters_trigger_reads_the_same_template():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Satyr Wayfinder"],
            battlefield=["Forest", "Forest"],
            library=["Lightning Bolt", "Island", "Grizzly Bears", "Sol Ring", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bolt, island, bears, sol_ring = scenario.top_of_library(4)
    scenario.will_take_the_may(source="Satyr Wayfinder")
    scenario.will_choose_cards(island, source="Satyr Wayfinder")

    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.cast_and_resolve("Satyr Wayfinder", *forests)
    scenario.pass_until_resolved()

    reveals = _public_reveals(scenario.game, "Satyr Wayfinder")
    assert [r.card_id for r in reveals] == [bolt.id, island.id, bears.id, sol_ring.id]
    assert island.zone is Zone.HAND
    assert {bolt.zone, bears.zone, sol_ring.zone} == {Zone.GRAVEYARD}
    assert [state.name for state in alice.library] == ["Swamp"]
    assert known(scenario.game, "bob") == [("Island", Zone.HAND, None, True)]


# -- The quantity is read, not fixed at "a": Glacial Revelation's "any number
# of snow permanent cards" (CR 107.1c, CR 205.4g) --------------------------


def _glacial_revelation_board(library: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Glacial Revelation"],
            battlefield=["Forest", "Forest", "Forest"],
            library=library,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_glacial_revelation_takes_two_of_two_snow_permanents():
    """ "Reveal the top six cards of your library. You may put any number of
    snow permanent cards from among them into your hand. Put the rest into
    your graveyard." CR 205.4g: a snow permanent is one with the snow
    supertype - "Snow-Covered Forest"/"Snow-Covered Island" carry it, an
    ordinary "Forest" does not."""
    scenario = _glacial_revelation_board(
        [
            "Snow-Covered Forest",
            "Snow-Covered Island",
            "Lightning Bolt",
            "Forest",
            "Mishra's Bauble",
            "Swamp",
        ]
    )
    alice = scenario.player("alice")
    snow_forest, snow_island, bolt, forest, bauble, swamp = scenario.top_of_library(6)
    scenario.will_choose_cards(snow_forest, snow_island, source="Glacial Revelation")

    forests = scenario.untapped_sources("Forest", "Forest", "Forest", username="alice")
    scenario.cast_and_resolve("Glacial Revelation", *forests)

    assert snow_forest.zone is Zone.HAND and snow_island.zone is Zone.HAND
    assert {bolt.zone, forest.zone, bauble.zone, swamp.zone} == {Zone.GRAVEYARD}
    assert alice.library == []


def test_glacial_revelation_takes_only_one_of_two_snow_permanents():
    """CR 107.1c's "any number" permits a partial take - the second qualifying
    card is a legal answer left behind, not a forced one."""
    scenario = _glacial_revelation_board(
        [
            "Snow-Covered Forest",
            "Snow-Covered Island",
            "Lightning Bolt",
            "Forest",
            "Mishra's Bauble",
            "Swamp",
        ]
    )
    alice = scenario.player("alice")
    snow_forest, snow_island, bolt, forest, bauble, swamp = scenario.top_of_library(6)
    scenario.will_choose_cards(snow_forest, source="Glacial Revelation")

    forests = scenario.untapped_sources("Forest", "Forest", "Forest", username="alice")
    scenario.cast_and_resolve("Glacial Revelation", *forests)

    assert snow_forest.zone is Zone.HAND
    assert {snow_island.zone, bolt.zone, forest.zone, bauble.zone, swamp.zone} == {Zone.GRAVEYARD}
    assert alice.library == []


def test_glacial_revelation_declining_puts_every_card_into_the_graveyard():
    """The default answer (nothing chosen) is legal - CR 608.2d never forces
    a take when the printed maximum is not a floor."""
    scenario = _glacial_revelation_board(
        ["Snow-Covered Forest", "Lightning Bolt", "Forest", "Mishra's Bauble", "Swamp", "Island"]
    )
    alice = scenario.player("alice")
    revealed = scenario.top_of_library(6)

    forests = scenario.untapped_sources("Forest", "Forest", "Forest", username="alice")
    scenario.cast_and_resolve("Glacial Revelation", *forests)

    assert alice.hand == []
    assert all(state.zone is Zone.GRAVEYARD for state in revealed)
