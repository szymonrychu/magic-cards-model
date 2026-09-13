""" "Put the rest on the bottom of your library in any order" asks the player for
the order whenever the order can matter.

Every CR number below was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 401.4** - "If an effect puts two or more cards in a specific position
  in a library at the same time, the owner of those cards may arrange them in
  any order. That library's owner doesn't reveal the order in which the cards
  go into the library." So the order is a real choice, asked of the owner.
- **CR 608.2d** - the choice is made while the effect resolves, and an answer
  that does not name every card going to the bottom exactly once is refused.

The question is the engine's existing ordered `CHOOSE_CARDS` answer - the
same one Brainstorm's "put two cards from your hand on top of your library in
any order" already uses - with every card going to the bottom offered and all
of them required, the first named nearest the top. An unscripted player keeps
the order the cards were in, so a rigged library stays rigged.

Two templates carry the phrase here: the look-and-reveal family (Ancient
Stirrings, and off-pool Adventurous Impulse) and Goblin Charbelcher's
reveal-until.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import (
    CardSplit,
    DecisionKind,
    DecisionPending,
    ScriptedAnswer,
)
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

FOUR_LANDS = ["Wastes"] * 4


def _script_split(scenario, moved) -> None:
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=tuple(moved)), player="alice")
    )


def _order_questions(scenario, source: str):
    return [
        d
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.CHOOSE_CARDS and d.source == source
    ]


def _stirrings_board(library: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", hand=["Ancient Stirrings"], battlefield=["Forest"], library=library)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_stirrings(scenario) -> None:
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Ancient Stirrings", forest)


STIRRINGS_LIBRARY = ["Sol Ring", "Lightning Bolt", "Grizzly Bears", "Island", "Swamp", "Mountain"]


def test_stirrings_asks_for_the_order_of_the_four_cards_going_to_the_bottom():
    scenario = _stirrings_board(STIRRINGS_LIBRARY)
    alice = scenario.player("alice")
    sol_ring, bolt, bears, island, swamp = scenario.top_of_library(5)
    _script_split(scenario, [sol_ring.id])
    scenario.will_choose_cards(swamp, island, bears, bolt, source="Ancient Stirrings")

    _cast_stirrings(scenario)

    (question,) = _order_questions(scenario, "Ancient Stirrings")
    assert question.player == "alice"
    assert set(question.cards) == {bolt.id, bears.id, island.id, swamp.id}
    assert question.amount == 4
    assert question.exact is True
    assert "bottom of your library" in question.prompt
    assert sol_ring.zone is Zone.HAND
    assert [state.name for state in alice.library] == [
        "Mountain",
        "Swamp",
        "Island",
        "Grizzly Bears",
        "Lightning Bolt",
    ]


def test_an_unscripted_order_keeps_the_looked_at_order():
    scenario = _stirrings_board(STIRRINGS_LIBRARY)
    alice = scenario.player("alice")
    (sol_ring,) = scenario.top_of_library(1)
    _script_split(scenario, [sol_ring.id])

    _cast_stirrings(scenario)

    assert len(_order_questions(scenario, "Ancient Stirrings")) == 1
    assert [state.name for state in alice.library] == [
        "Mountain",
        "Lightning Bolt",
        "Grizzly Bears",
        "Island",
        "Swamp",
    ]


def test_an_order_that_leaves_a_card_out_is_refused():
    scenario = _stirrings_board(STIRRINGS_LIBRARY)
    sol_ring, bolt, bears, _island, _swamp = scenario.top_of_library(5)
    _script_split(scenario, [sol_ring.id])
    scenario.will_choose_cards(bears, bolt, source="Ancient Stirrings")

    with pytest.raises(ValueError, match="needs 4 card"):
        _cast_stirrings(scenario)


def test_the_order_question_pauses_a_seat_that_has_not_answered():
    scenario = _stirrings_board(STIRRINGS_LIBRARY)
    (sol_ring,) = scenario.top_of_library(1)
    _script_split(scenario, [sol_ring.id])
    scenario.game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as paused:
        _cast_stirrings(scenario)

    decision = paused.value.pending.decision
    assert decision.kind is DecisionKind.CHOOSE_CARDS
    assert decision.source == "Ancient Stirrings"
    assert decision.amount == 4


def test_a_single_card_going_to_the_bottom_asks_no_order():
    scenario = _stirrings_board(["Sol Ring", "Island"])
    alice = scenario.player("alice")
    (sol_ring,) = scenario.top_of_library(1)
    _script_split(scenario, [sol_ring.id])

    _cast_stirrings(scenario)

    assert _order_questions(scenario, "Ancient Stirrings") == []
    assert [state.name for state in alice.library] == ["Island"]


def test_identical_cards_going_to_the_bottom_ask_no_order():
    """Five Islands put back in any order are the same library in every order,
    so there is no choice to offer."""
    scenario = _stirrings_board(["Island"] * 6)
    _script_split(scenario, [])

    _cast_stirrings(scenario)

    assert _order_questions(scenario, "Ancient Stirrings") == []


def test_adventurous_impulse_asks_for_the_order_of_the_rest():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Adventurous Impulse"],
            battlefield=["Forest"],
            library=["Grizzly Bears", "Lightning Bolt", "Sol Ring", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears, bolt, sol_ring = scenario.top_of_library(3)
    _script_split(scenario, [bears.id])
    scenario.will_choose_cards(sol_ring, bolt, source="Adventurous Impulse")

    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Adventurous Impulse", forest)

    (question,) = _order_questions(scenario, "Adventurous Impulse")
    assert set(question.cards) == {bolt.id, sol_ring.id}
    assert bears.zone is Zone.HAND
    assert [state.name for state in alice.library] == ["Island", "Sol Ring", "Lightning Bolt"]


def test_charbelchers_revealed_cards_go_to_the_bottom_in_the_chosen_order():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Goblin Charbelcher", *FOUR_LANDS],
            library=["Lightning Bolt", "Sol Ring", "Forest", "Island"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bolt, sol_ring, forest = scenario.top_of_library(3)
    scenario.will_choose_cards(forest, bolt, sol_ring, source="Goblin Charbelcher")

    belcher = scenario.find("Goblin Charbelcher", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        belcher, *scenario.untapped_sources(*FOUR_LANDS), targets=[scenario.player("bob")]
    )
    scenario.resolve_top()

    (question,) = _order_questions(scenario, "Goblin Charbelcher")
    assert set(question.cards) == {bolt.id, sol_ring.id, forest.id}
    assert question.amount == 3
    assert scenario.player("bob").life == 18
    assert [state.name for state in alice.library] == [
        "Island",
        "Forest",
        "Lightning Bolt",
        "Sol Ring",
    ]
