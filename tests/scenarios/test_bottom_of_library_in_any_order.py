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

The order question is also a question a live seat pauses on, so it has to
survive the engine's resume-by-replay (`machines/decisions.py`, "Pausing
instead of blocking"): the committed game goes through JSON, the paused
`PendingDecision` goes through JSON, the answer goes onto the `Answer` tape
through JSON, and the command re-run from the decoded snapshot reaches the
order the player chose - the same library a live, scripted answer reaches.
"""

import json
from collections.abc import Callable

import pytest
from pydantic import TypeAdapter

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import (
    Answer,
    CardSplit,
    DecisionKind,
    DecisionPending,
    PendingDecision,
    ScriptedAnswer,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.game import Game
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


# -- replay and round trip ---------------------------------------------------
#
# Resuming is replay, not a checkpoint: every attempt decodes the committed
# snapshot afresh, loads the tape of answers given so far, re-runs the same
# command, and pauses on the next question nothing has answered yet.

_PENDING = TypeAdapter(PendingDecision)


def _committed_json(game: Game) -> str:
    return json.dumps(game.model_dump(mode="json"))


def _resume_by_replay(
    snapshot: str, answer: Callable[[PendingDecision], Answer]
) -> tuple[Game, list[PendingDecision]]:
    """Resolve the top of the stack in `snapshot` the way a paused live seat
    does, answering each pause with `answer` and storing every pause and every
    answer as JSON between attempts. Returns the finished game and the pauses
    in the order they were raised."""
    tape: list[Answer] = []
    pauses: list[PendingDecision] = []
    for _attempt in range(10):
        game = Game.model_validate(json.loads(snapshot))
        game.decisions.begin_replay(tape)
        game.decisions.pause_when_unanswered = True
        try:
            game.resolve_top()
        except DecisionPending as paused:
            stored = _PENDING.validate_json(_PENDING.dump_json(paused.pending))
            assert stored == paused.pending, "the paused decision must survive JSON unchanged"
            pauses.append(stored)
            tape = [Answer.model_validate_json(entry.model_dump_json()) for entry in tape]
            tape.append(Answer.model_validate_json(answer(stored).model_dump_json()))
            continue
        game.decisions.finish_replay()
        return game, pauses
    raise AssertionError(f"still pausing after {len(pauses)} answers: {pauses}")


def _ids_by_label(decision, *names: str):
    by_name = dict(zip(decision.card_labels, decision.cards, strict=True))
    return tuple(by_name[name] for name in names)


def _answer_split_then_order(take: list[str], order: list[str]):
    def answer(pending: PendingDecision) -> Answer:
        decision = pending.decision
        if decision.kind is DecisionKind.SCRY:
            moved = _ids_by_label(decision, *take)
            return Answer(
                seq=pending.seq,
                kind=decision.kind,
                player=decision.player,
                split=CardSplit(moved=moved),
            )
        assert decision.kind is DecisionKind.CHOOSE_CARDS
        return Answer(
            seq=pending.seq,
            kind=decision.kind,
            player=decision.player,
            card_ids=_ids_by_label(decision, *order),
        )

    return answer


def _stirrings_on_the_stack() -> PlayedScenario:
    scenario = _stirrings_board(STIRRINGS_LIBRARY)
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_onto_stack("Ancient Stirrings", forest)
    return scenario


STIRRINGS_ORDER = ["Swamp", "Island", "Grizzly Bears", "Lightning Bolt"]


def test_a_paused_order_resumes_from_a_json_snapshot_to_the_chosen_order():
    scenario = _stirrings_on_the_stack()
    snapshot = _committed_json(scenario.game)

    resumed, pauses = _resume_by_replay(
        snapshot, _answer_split_then_order(["Sol Ring"], STIRRINGS_ORDER)
    )

    assert [(p.seq, p.decision.kind) for p in pauses] == [
        (0, DecisionKind.SCRY),
        (1, DecisionKind.CHOOSE_CARDS),
    ]
    order = pauses[1].decision
    assert order.player == "alice"
    assert order.source == "Ancient Stirrings"
    assert order.amount == 4
    assert order.exact is True
    assert set(order.card_labels) == {"Lightning Bolt", "Grizzly Bears", "Island", "Swamp"}
    assert "608.2d" in pauses[1].rule
    alice = resumed.player("alice")
    assert [state.name for state in alice.hand] == ["Sol Ring"]
    assert [state.name for state in alice.library] == ["Mountain", *STIRRINGS_ORDER]


def test_the_resumed_order_matches_a_live_answer_to_the_same_question():
    """The tape answer and a live scripted answer are the same answer, so the
    library ends up the same card objects in the same order either way."""
    scenario = _stirrings_on_the_stack()
    snapshot = _committed_json(scenario.game)
    resumed, _pauses = _resume_by_replay(
        snapshot, _answer_split_then_order(["Sol Ring"], STIRRINGS_ORDER)
    )

    live = PlayedScenario(Game.model_validate(json.loads(snapshot)))
    library = {state.name: state for state in live.player("alice").library}
    _script_split(live, [library["Sol Ring"].id])
    live.will_choose_cards(*(library[name] for name in STIRRINGS_ORDER), source="Ancient Stirrings")
    live.resolve_top()

    assert [state.id for state in resumed.player("alice").library] == [
        state.id for state in live.player("alice").library
    ]
    # Everything but the answer bookkeeping: the replay read its answers off
    # the tape, the live run off the script.
    assert resumed.model_dump(mode="json", exclude={"decisions"}) == live.game.model_dump(
        mode="json", exclude={"decisions"}
    )


def test_the_finished_game_round_trips_with_the_order_question_on_record():
    scenario = _stirrings_on_the_stack()
    resumed, pauses = _resume_by_replay(
        _committed_json(scenario.game),
        _answer_split_then_order(["Sol Ring"], STIRRINGS_ORDER),
    )

    decoded = Game.model_validate(json.loads(_committed_json(resumed)))

    assert decoded.model_dump(mode="json") == resumed.model_dump(mode="json")
    assert [state.name for state in decoded.player("alice").library] == [
        "Mountain",
        *STIRRINGS_ORDER,
    ]
    (order,) = [
        d
        for d in decoded.decisions.asked
        if d.kind is DecisionKind.CHOOSE_CARDS and d.source == "Ancient Stirrings"
    ]
    assert order == pauses[1].decision
    assert decoded.decisions.recorded == resumed.decisions.recorded
    assert decoded.decisions.recorded[1].card_ids == _ids_by_label(order, *STIRRINGS_ORDER)


def test_a_tape_order_that_leaves_a_card_out_is_refused_on_replay():
    scenario = _stirrings_on_the_stack()
    snapshot = _committed_json(scenario.game)

    with pytest.raises(ValueError, match="needs 4 card"):
        _resume_by_replay(
            snapshot, _answer_split_then_order(["Sol Ring"], ["Grizzly Bears", "Lightning Bolt"])
        )


def test_adventurous_impulse_resumes_to_the_chosen_order():
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
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_onto_stack("Adventurous Impulse", forest)

    resumed, pauses = _resume_by_replay(
        _committed_json(scenario.game),
        _answer_split_then_order(["Grizzly Bears"], ["Sol Ring", "Lightning Bolt"]),
    )

    assert [p.decision.kind for p in pauses] == [DecisionKind.SCRY, DecisionKind.CHOOSE_CARDS]
    assert set(pauses[1].decision.card_labels) == {"Lightning Bolt", "Sol Ring"}
    alice = resumed.player("alice")
    assert [state.name for state in alice.hand] == ["Grizzly Bears"]
    assert [state.name for state in alice.library] == ["Island", "Sol Ring", "Lightning Bolt"]


def test_charbelchers_order_resumes_to_the_chosen_order():
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
    belcher = scenario.find("Goblin Charbelcher", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        belcher, *scenario.untapped_sources(*FOUR_LANDS), targets=[scenario.player("bob")]
    )

    resumed, pauses = _resume_by_replay(
        _committed_json(scenario.game),
        _answer_split_then_order([], ["Forest", "Lightning Bolt", "Sol Ring"]),
    )

    (order,) = pauses
    assert order.seq == 0
    assert order.decision.kind is DecisionKind.CHOOSE_CARDS
    assert order.decision.source == "Goblin Charbelcher"
    assert order.decision.amount == 3
    assert resumed.player("bob").life == 18
    assert [state.name for state in resumed.player("alice").library] == [
        "Island",
        "Forest",
        "Lightning Bolt",
        "Sol Ring",
    ]
