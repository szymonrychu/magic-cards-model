"""Reveal the top N, take "a <kind> card and/or a <kind> card", bin the rest.

Kiora, Master of the Depths' -2: "Reveal the top four cards of your library.
You may put a creature card and/or a land card from among them into your
hand. Put the rest into your graveyard." Two independent optional picks from
the same revealed cards - up to one creature card and up to one land card -
not the single pick of Grisly Salvage's "a creature or land card".

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 701.20a** - every revealed card is shown to all players.
- **CR 608.2d** - each pick is a choice made as the ability resolves; a
  player is never offered a pick with no legal card.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _kiora(library: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kiora, Master of the Depths"], library=library)
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kiora = scenario.find("Kiora, Master of the Depths", Zone.BATTLEFIELD, "alice")
    return scenario, kiora


def _resolve(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def _names(cards) -> list[str]:
    return sorted(card.name for card in cards)


def test_minus_two_takes_a_creature_and_a_land_and_bins_the_rest():
    scenario, kiora = _kiora(["Grizzly Bears", "Forest", "Lightning Bolt", "Island", "Swamp"])
    scenario.will_take_the_may(True, times=2)
    scenario.will_choose_cards(scenario.find("Forest", Zone.LIBRARY, "alice"))
    scenario.activate(kiora, index=1)
    _resolve(scenario)

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Forest", "Grizzly Bears"]
    assert _names(alice.graveyard) == ["Island", "Lightning Bolt"]
    assert _names(alice.library) == ["Swamp"]
    assert kiora.counters[Counter.LOYALTY] == 2


def test_minus_two_may_take_only_the_land():
    scenario, kiora = _kiora(["Grizzly Bears", "Forest", "Lightning Bolt", "Island"])
    scenario.will_take_the_may(False)
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(scenario.find("Forest", Zone.LIBRARY, "alice"))
    scenario.activate(kiora, index=1)
    _resolve(scenario)

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Forest"]
    assert _names(alice.graveyard) == ["Grizzly Bears", "Island", "Lightning Bolt"]


def test_minus_two_may_take_nothing():
    scenario, kiora = _kiora(["Grizzly Bears", "Forest", "Lightning Bolt", "Island"])
    scenario.will_take_the_may(False, times=2)
    scenario.activate(kiora, index=1)
    _resolve(scenario)

    alice = scenario.player("alice")
    assert alice.hand == []
    assert len(alice.graveyard) == 4


def test_with_no_creature_revealed_only_the_land_is_offered():
    """CR 608.2d: no question with no legal answer."""
    scenario, kiora = _kiora(["Lightning Bolt", "Forest", "Island", "Lightning Bolt"])
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(scenario.find("Forest", Zone.LIBRARY, "alice"))
    scenario.activate(kiora, index=1)
    _resolve(scenario)

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Forest"]
    mays = [q for q in scenario.questions_asked() if q.source == "Kiora, Master of the Depths"]
    assert all("creature" not in q.prompt for q in mays)


def test_the_player_chooses_which_land():
    scenario, kiora = _kiora(["Forest", "Island", "Grizzly Bears", "Lightning Bolt"])
    island = scenario.find("Island", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(False)  # no creature
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(island)
    scenario.activate(kiora, index=1)
    _resolve(scenario)

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Island"]
    assert _names(alice.graveyard) == ["Forest", "Grizzly Bears", "Lightning Bolt"]


def test_one_dryad_arbor_fills_only_one_slot():
    """A creature land card is one card: taken as the creature, it is no
    longer among the revealed cards for the land pick."""
    scenario, kiora = _kiora(["Dryad Arbor", "Lightning Bolt", "Lightning Bolt", "Island"])
    scenario.will_take_the_may(True, times=2)
    scenario.activate(kiora, index=1)
    _resolve(scenario)

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Dryad Arbor", "Island"]
    assert _names(alice.graveyard) == ["Lightning Bolt", "Lightning Bolt"]


def test_every_revealed_card_is_revealed_to_all_players():
    """CR 701.20a."""
    scenario, kiora = _kiora(["Grizzly Bears", "Forest", "Lightning Bolt", "Island"])
    top_four = list(scenario.player("alice").library[:4])
    scenario.will_take_the_may(True, times=2)
    scenario.activate(kiora, index=1)
    _resolve(scenario)

    revealed_ids = {record.card_id for record in scenario.game.reveals}
    assert {card.id for card in top_four} <= revealed_ids


def test_a_short_library_reveals_what_it_has():
    scenario, kiora = _kiora(["Grizzly Bears", "Forest"])
    scenario.will_take_the_may(True, times=2)
    scenario.activate(kiora, index=1)
    _resolve(scenario)

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Forest", "Grizzly Bears"]
    assert alice.library == []
