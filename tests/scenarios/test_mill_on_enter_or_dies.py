"""Stitcher's Supplier: "When this creature enters or dies, mill three cards."
(R0c T4).

CR numbers looked up with `mise run rules:find` in the session that wrote this:

- **CR 701.17a** - to mill a number of cards, put that many cards from the top
  of the library into the graveyard.
- **CR 701.17b** - a player can't mill more cards than their library holds;
  instructed to, they mill as many as possible.
- **CR 603.6a / 603.6c** - an enters trigger fires when the permanent arrives;
  a leaves-the-battlefield (dies) trigger looks back at the permanent.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

SUPPLIER = "Stitcher's Supplier"
LIBRARY = ["Island", "Forest", "Mountain", "Swamp", "Plains"]


def _resolve_triggers(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _board(library=LIBRARY, **kwargs):
    scenario = (
        Scenario()
        .player("alice", library=list(library), **kwargs)
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _names(cards) -> list[str]:
    return [c.name for c in cards]


def test_entering_mills_the_top_three_cards_of_your_library():
    scenario = _board(hand=[SUPPLIER], battlefield=["Swamp"])
    (swamp,) = scenario.untapped_sources("Swamp")
    scenario.cast_and_resolve(SUPPLIER, swamp)
    _resolve_triggers(scenario)

    graveyard = _names(scenario.player("alice").graveyard)
    assert sorted(graveyard) == sorted(["Island", "Forest", "Mountain"])
    assert _names(scenario.player("alice").library) == ["Swamp", "Plains"]
    assert scenario.find(SUPPLIER, Zone.BATTLEFIELD, "alice")


def test_the_opponents_library_is_untouched():
    scenario = _board(hand=[SUPPLIER], battlefield=["Swamp"])
    (swamp,) = scenario.untapped_sources("Swamp")
    scenario.cast_and_resolve(SUPPLIER, swamp)
    _resolve_triggers(scenario)
    assert len(scenario.player("bob").library) == 4
    assert scenario.player("bob").graveyard == []


def test_dying_mills_three_more_cards():
    scenario = _board(battlefield=[SUPPLIER])
    supplier = scenario.creature(SUPPLIER, "alice")
    scenario.game.destroy(supplier)
    _resolve_triggers(scenario)

    assert supplier.zone is Zone.GRAVEYARD
    graveyard = _names(scenario.player("alice").graveyard)
    assert len(graveyard) == 4  # the Supplier itself plus three milled
    assert SUPPLIER in graveyard
    assert len(scenario.player("alice").library) == 2


def test_entering_then_dying_triggers_each_time():
    scenario = _board(library=LIBRARY + ["Island", "Forest"], battlefield=[SUPPLIER])
    supplier = scenario.creature(SUPPLIER, "alice")
    scenario.game.destroy(supplier)
    _resolve_triggers(scenario)
    assert len(scenario.player("alice").library) == 4


def test_a_library_of_two_mills_both_cards_and_does_not_lose_yet():
    """CR 701.17b: mill as many as possible. Emptying the library is not
    losing - only a later draw from it is."""
    scenario = _board(library=["Island", "Forest"], battlefield=[SUPPLIER])
    supplier = scenario.creature(SUPPLIER, "alice")
    scenario.game.destroy(supplier)
    _resolve_triggers(scenario)

    assert scenario.player("alice").library == []
    assert len(scenario.player("alice").graveyard) == 3
    scenario.game.check_state_based_actions()
    assert not scenario.game.is_over


def test_an_empty_library_mills_nothing_and_the_trigger_still_resolves():
    scenario = _board(library=[], battlefield=[SUPPLIER])
    supplier = scenario.creature(SUPPLIER, "alice")
    scenario.game.destroy(supplier)
    _resolve_triggers(scenario)

    assert _names(scenario.player("alice").graveyard) == [SUPPLIER]
    assert scenario.game.stack == []


def test_a_library_of_exactly_three_is_emptied():
    scenario = _board(
        library=["Island", "Forest", "Mountain"], hand=[SUPPLIER], battlefield=["Swamp"]
    )
    (swamp,) = scenario.untapped_sources("Swamp")
    scenario.cast_and_resolve(SUPPLIER, swamp)
    _resolve_triggers(scenario)
    assert scenario.player("alice").library == []
    assert len(scenario.player("alice").graveyard) == 3


def test_exiling_it_does_not_mill():
    """It only mills on enter or die: exile is neither."""
    scenario = _board(battlefield=[SUPPLIER])
    supplier = scenario.creature(SUPPLIER, "alice")
    scenario.game.exile_cards([supplier])
    _resolve_triggers(scenario)
    assert supplier.zone is Zone.EXILE
    assert len(scenario.player("alice").library) == 5
