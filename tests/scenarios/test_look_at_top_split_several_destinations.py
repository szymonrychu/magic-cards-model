"""A look at the top of a library split into several destinations moves each
looked-at card exactly once (CR 400.7, CR 400.1), and the look is known to the
looker (CR 701.20e).

- **CR 400.7** - "An object that moves from one zone to another becomes a new
  object with no memory of, or relation to, its previous existence." A card
  put into a hand has left the library; it is not in both.
- **CR 401.4** - "If an effect puts two or more cards in a specific position in
  a library at the same time, the owner of those cards may arrange them in any
  order."
- **CR 608.2c** - the instructions are followed in the order written, so every
  card is looked at before the sentence that moves it.

Expressive Iteration ("Look at the top three cards of your library. Put one of
them into your hand, put one of them on the bottom of your library, and exile
one of them. You may play the exiled card this turn.") is the deck-pool card
that exposed the duplicate (battle 7, B7-01): its card put into hand was left
in the library as well. Sleight of Hand ("Look at the top two cards of your
library. Put one of them into your hand and the other on the bottom of your
library.") is in neither deck pool and proves the same guarantee on a
two-destination look worded differently.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
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
from magic_cards_model.models.game import PlayAction
from tests.scenarios.harness import Scenario


def _iteration_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Expressive Iteration"],
            library=["Mountain", "Forest", "Lightning Bolt", "Island", "Swamp"],
            battlefield=["Island", "Mountain"],
        )
        .player("bob")
    )


def test_the_card_put_into_hand_is_no_longer_in_the_library():
    """B7-01: one object in two zones. Five cards, three looked at, one to
    hand and one exiled: three are left in the library (CR 400.7)."""
    scenario = _iteration_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountain, forest, bolt = scenario.top_of_library(3, "alice")
    scenario.will_choose_cards(bolt, source="Expressive Iteration")
    scenario.will_choose_cards(forest, source="Expressive Iteration")

    scenario.cast_and_resolve(
        "Expressive Iteration", *scenario.untapped_sources("Island", "Mountain")
    )

    assert bolt.zone is Zone.HAND
    assert bolt in alice.hand
    assert not any(state is bolt for state in alice.library)
    assert len(alice.library) == 3
    assert alice.library[-1] is forest, "put on the bottom of the library"
    assert mountain.zone is Zone.EXILE
    scenario.assert_in_exactly_one_zone(mountain, forest, bolt)
    assert scenario.game.play_permission_for(mountain, "alice", PlayAction.PLAY) is not None


def _known(game, viewer: str) -> list[tuple[str, Zone, int | None]]:
    return [(entry.card_name, entry.zone, entry.index_from_top) for entry in game.known_to(viewer)]


def test_the_looker_knows_the_cards_where_they_sit_while_the_split_is_pending():
    """B7-05: the look is recorded before the first question is asked."""
    scenario = _iteration_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    scenario.cast_onto_stack(
        "Expressive Iteration", *scenario.untapped_sources("Island", "Mountain")
    )
    game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as paused:
        scenario.resolve_top()

    assert paused.value.pending.decision.kind is DecisionKind.CHOOSE_CARDS
    assert _known(game, "alice") == [
        ("Mountain", Zone.LIBRARY, 0),
        ("Forest", Zone.LIBRARY, 1),
        ("Lightning Bolt", Zone.LIBRARY, 2),
    ]
    assert _known(game, "bob") == [], "CR 701.20e: a look is the looker's alone"


def test_after_the_split_the_bottomed_card_stays_known_and_the_exiled_card_is_public():
    scenario = _iteration_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    mountain, forest, bolt = scenario.top_of_library(3, "alice")
    scenario.will_choose_cards(bolt, source="Expressive Iteration")
    scenario.will_choose_cards(forest, source="Expressive Iteration")

    scenario.cast_and_resolve(
        "Expressive Iteration", *scenario.untapped_sources("Island", "Mountain")
    )

    assert ("Forest", Zone.LIBRARY, 2) in _known(game, "alice")
    assert [entry for entry in _known(game, "alice") if entry[1] is Zone.LIBRARY] == [
        ("Forest", Zone.LIBRARY, 2)
    ], "one look per card: the pending look is replaced, not added to"
    assert _known(game, "bob") == []
    assert mountain.zone is Zone.EXILE and mountain.face_up, "CR 400.2: exile is public"


def test_sleight_of_hand_puts_one_card_in_hand_and_the_other_on_the_bottom_once_each():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sleight of Hand"],
            library=["Mountain", "Forest", "Swamp"],
            battlefield=["Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountain, forest = scenario.top_of_library(2, "alice")
    # The two-way look asks the look-and-split question: `moved` is the card
    # picked for the hand (`Game.look_at_top_and_split`).
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.SCRY, value=CardSplit(moved=(forest.id,)), source="Sleight of Hand"
        )
    )

    scenario.cast_and_resolve("Sleight of Hand", *scenario.untapped_sources("Island"))

    assert forest.zone is Zone.HAND
    assert [state.name for state in alice.library] == ["Swamp", "Mountain"]
    scenario.assert_in_exactly_one_zone(mountain, forest)
    assert ("Mountain", Zone.LIBRARY, 1) in _known(scenario.game, "alice")


def _hand_pick(scenario, card, source: str) -> None:
    """The look-and-split question's `moved` pile is the card for the hand."""
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=(card.id,)), source=source)
    )


def _looker(library: list[str], hand: list[str], islands: int) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=hand, library=library, battlefield=["Island"] * islands)
        .player("bob")
    )


def test_forbidden_alchemy_puts_one_in_hand_and_the_rest_into_the_graveyard():
    scenario = _looker(
        ["Mountain", "Forest", "Lightning Bolt", "Island", "Swamp"], ["Forbidden Alchemy"], 3
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    looked = scenario.top_of_library(4, "alice")
    _hand_pick(scenario, looked[2], "Forbidden Alchemy")

    scenario.cast_and_resolve(
        "Forbidden Alchemy", *scenario.untapped_sources("Island", "Island", "Island")
    )

    assert looked[2].zone is Zone.HAND
    assert [state.zone for state in (looked[0], looked[1], looked[3])] == [Zone.GRAVEYARD] * 3
    assert [state.name for state in alice.library] == ["Swamp"]
    scenario.assert_in_exactly_one_zone(*looked)


def test_anticipate_asks_the_order_of_the_rest_on_the_bottom():
    """CR 401.4: "in any order" is the owner's arrangement, asked."""
    scenario = _looker(
        ["Mountain", "Forest", "Lightning Bolt", "Island"], ["Anticipate"], 2
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountain, forest, bolt = scenario.top_of_library(3, "alice")
    _hand_pick(scenario, bolt, "Anticipate")
    scenario.will_choose_cards(forest, mountain, source="Anticipate")

    scenario.cast_and_resolve("Anticipate", *scenario.untapped_sources("Island", "Island"))

    assert bolt.zone is Zone.HAND
    assert [state.name for state in alice.library] == ["Island", "Forest", "Mountain"]
    assert ("Forest", Zone.LIBRARY, 1) in _known(scenario.game, "alice")
    assert ("Mountain", Zone.LIBRARY, 2) in _known(scenario.game, "alice")
    scenario.assert_in_exactly_one_zone(mountain, forest, bolt)


def test_shimmer_of_possibility_bottoms_the_rest_in_a_random_order_known_to_nobody():
    scenario = _looker(
        ["Mountain", "Forest", "Lightning Bolt", "Island", "Swamp"], ["Shimmer of Possibility"], 2
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    looked = scenario.top_of_library(4, "alice")
    _hand_pick(scenario, looked[0], "Shimmer of Possibility")

    scenario.cast_and_resolve(
        "Shimmer of Possibility", *scenario.untapped_sources("Island", "Island")
    )

    assert looked[0].zone is Zone.HAND
    assert alice.library[0].name == "Swamp"
    assert sorted(state.name for state in alice.library[1:]) == [
        "Forest",
        "Island",
        "Lightning Bolt",
    ]
    assert DecisionKind.CHOOSE_CARDS not in [q.kind for q in scenario.questions_asked()]
    assert [entry for entry in _known(scenario.game, "alice") if entry[1] is Zone.LIBRARY] == []
    scenario.assert_in_exactly_one_zone(*looked)


def test_browse_puts_one_in_hand_and_exiles_the_rest():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Mountain", "Forest", "Lightning Bolt", "Island", "Swamp", "Plains"],
            battlefield=["Browse", "Island", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    looked = scenario.top_of_library(5, "alice")
    _hand_pick(scenario, looked[2], "Browse")
    browse = scenario.find("Browse", Zone.BATTLEFIELD, "alice")

    scenario.activate(browse, *scenario.untapped_sources("Island", "Island", "Island", "Island"))
    scenario.resolve_top()

    assert looked[2].zone is Zone.HAND
    assert [state.zone for state in looked if state is not looked[2]] == [Zone.EXILE] * 4
    assert [state.name for state in alice.library] == ["Plains"]
    scenario.assert_in_exactly_one_zone(*looked)
