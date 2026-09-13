"""The order of the cards a scry puts on the bottom is the scrier's choice.

- **CR 701.22a** - "To 'scry N' means to look at the top N cards of your
  library, then put any number of them on the bottom of your library in any
  order and the rest on top of your library in any order."
- **CR 401.4** - "If an effect puts two or more cards in a specific position in
  a library at the same time, the owner of those cards may arrange them in any
  order. That library's owner doesn't reveal the order in which the cards go
  into the library."

So a scry that bottoms two or more cards asks the same CR 401.4 order question
`Game.ask_library_bottom_order` already asks for "put the rest on the bottom in
any order" (battle 7, B7-12: Preordain's order was only the `moved` list's,
which no question said). An unscripted seat keeps the order it named the cards
in. Preordain is the deck-pool card; Magma Jet ("Magma Jet deals 2 damage to
any target. Scry 2.") is in neither deck pool.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, DecisionPending
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _library(*names: str, hand: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player("alice", library=list(names), hand=hand or [], battlefield=["Mountain", "Mountain"])
        .player("bob")
    )


def _names(scenario) -> list[str]:
    return [state.name for state in scenario.player("alice").library]


def test_bottoming_two_cards_asks_their_order():
    scenario = _library("Island", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island, mountain = scenario.top_of_library(2)
    scenario.scry_bottoming(island, mountain)
    scenario.will_choose_cards(mountain, island)

    scenario.game.scry("alice", 2, source="Preordain")

    kinds = [question.kind for question in scenario.questions_asked()]
    assert kinds == [DecisionKind.SCRY, DecisionKind.CHOOSE_CARDS]
    order_question = scenario.questions_asked()[1]
    assert order_question.source == "Preordain"
    assert set(order_question.cards) == {island.id, mountain.id}
    assert order_question.amount == 2
    assert _names(scenario) == ["Forest", "Mountain", "Island"]


def test_an_unscripted_order_keeps_the_order_the_cards_were_named_in():
    scenario = _library("Island", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island, mountain = scenario.top_of_library(2)
    scenario.scry_bottoming(mountain, island)

    scenario.game.scry("alice", 2, source="Preordain")

    assert _names(scenario) == ["Forest", "Mountain", "Island"]


def test_one_card_bottomed_asks_no_order():
    scenario = _library("Island", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.top_of_library(1)
    scenario.scry_bottoming(island)

    scenario.game.scry("alice", 2, source="Preordain")

    assert [question.kind for question in scenario.questions_asked()] == [DecisionKind.SCRY]


def test_a_paused_seat_is_asked_the_order_as_its_own_pending_question():
    scenario = _library("Island", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island, mountain = scenario.top_of_library(2)
    scenario.scry_bottoming(island, mountain)
    scenario.game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as paused:
        scenario.game.scry("alice", 2, source="Preordain")

    decision = paused.value.pending.decision
    assert decision.kind is DecisionKind.CHOOSE_CARDS
    assert "bottom" in decision.prompt
    assert decision.card_labels == ("Island", "Mountain")


def test_magma_jet_scries_two_and_asks_the_bottom_order():
    scenario = _library("Island", "Forest", "Swamp", hand=["Magma Jet"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island, forest = scenario.top_of_library(2)
    scenario.scry_bottoming(island, forest)
    scenario.will_choose_cards(forest, island, source="Magma Jet")

    scenario.cast_and_resolve(
        "Magma Jet", *scenario.untapped_sources("Mountain", "Mountain"), targets=["bob"]
    )

    assert scenario.player("bob").life == 18
    assert _names(scenario) == ["Swamp", "Forest", "Island"]
    known = [(entry.card_name, entry.index_from_top) for entry in scenario.game.known_to("alice")]
    assert ("Forest", 1) in known and ("Island", 2) in known
    assert island.zone is Zone.LIBRARY
