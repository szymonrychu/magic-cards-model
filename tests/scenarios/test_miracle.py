"""Miracle: reveal the turn's first draw, then cast it for its miracle cost
while the linked trigger resolves (CR 702.94).

Every CR number below was read whole with `mise run rules:find` (CR effective
2026-09-25) in the session that wrote this file:

- **CR 702.94a** - "Miracle is a static ability linked to a triggered
  ability. (See rule 603.11.) 'Miracle [cost]' means 'You may reveal this card
  from your hand as you draw it if it's the first card you've drawn this turn.
  When you reveal this card this way, you may cast it by paying [cost] rather
  than its mana cost.'"
- **CR 702.94b** - "If a player chooses to reveal a card using its miracle
  ability, they play with that card revealed until that card leaves their
  hand, that ability resolves, or that ability otherwise leaves the stack."
- **CR 603.11 / CR 607.2h** - the static ability and the trigger are linked:
  the trigger "refers only to actions taken as a result of the static
  ability", so only a reveal made this way triggers it.
- **CR 603.3** - the trigger goes on the stack "the next time a player would
  receive priority".
- **CR 608.2g** - a spell cast while an ability resolves follows CR 601.2a-i,
  "except no player receives priority after it's cast" - which is why a
  sorcery (Terminus) is cast in the draw step or on an opponent's turn.
- **CR 107.3a** - an X in an alternative cost is chosen and announced as the
  spell is cast (Entreat the Angels' Miracle {X}{W}{W}).
- **CR 121.2** - a multi-card draw is that many individual draws, so only the
  first of them can be the turn's first card drawn.
- **CR 400.7** - a card that left the hand is a new object: the trigger cannot
  cast it any more.

Proofs: Terminus (Miracle {W}), Thunderous Wrath (Miracle {R}, targets chosen
on the cast), Reforge the Soul (the reported card, Miracle {1}{R}) and Entreat
the Angels (Miracle {X}{W}{W}) - none of them in the api deck pool.
"""

import json
from collections.abc import Callable

import pytest
from pydantic import TypeAdapter

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import (
    Answer,
    Decision,
    DecisionKind,
    DecisionPending,
    PendingDecision,
)
from magic_cards_model.machines.keywords import executes, keyword_triggered_abilities
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.game import Game
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

REVEAL_PROMPT = "reveal"


def _reveal_questions(scenario: PlayedScenario, name: str, player: str | None = None):
    return [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.MAY
        and q.source == name
        and REVEAL_PROMPT in q.prompt
        and (player is None or q.player == player)
    ]


def _cast_questions(scenario: PlayedScenario, name: str):
    return [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.MAY and q.source == name and "miracle cost" in q.prompt
    ]


def _miracle_triggers(scenario: PlayedScenario):
    return [
        item
        for item in [*scenario.game.stack, *scenario.game.pending_triggers]
        if getattr(item, "is_ability", False)
        and getattr(item.ability, "keyword", None) == "miracle"
    ]


def _alices_upkeep(scenario: PlayedScenario) -> PlayedScenario:
    """Bob plays first and skips his first draw (CR 103.8a); run his turn out
    and stop at Alice's upkeep, with her turn's draw still to come."""
    scenario.start_at(Step.CLEANUP)
    scenario.advance()  # Alice's untap step
    scenario.advance()  # her upkeep
    assert scenario.turn.active_player == "alice" and scenario.step is Step.UPKEEP
    return scenario


def _draw_step_board(
    top: str,
    *,
    alice_battlefield: list[str],
    bob_battlefield: list[str] | None = None,
    bob_hand: list[str] | None = None,
    alice_hand: list[str] | None = None,
) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "bob",
            hand=bob_hand or [],
            library=["Island"] * 10,
            battlefield=bob_battlefield or [],
        )
        .player(
            "alice",
            hand=alice_hand or [],
            library=[top] + ["Plains"] * 10,
            battlefield=alice_battlefield,
        )
        .build()
    )
    return _alices_upkeep(scenario)


def _into_draw_step(scenario: PlayedScenario) -> None:
    scenario.advance()
    assert scenario.step is Step.DRAW


# -- the keyword --------------------------------------------------------------


def test_miracle_is_a_static_ability_linked_to_a_trigger():
    """CR 702.94a: the keyword line writes out one triggered ability, "When
    you reveal this card this way, you may cast it by paying [cost] rather
    than its mana cost" - the printed cost carried into it."""
    (ability,) = keyword_triggered_abilities(card("Terminus"))
    assert ability.keyword == "miracle"
    assert ability.condition == "you reveal this card this way"
    assert "{W}" in (ability.effect or "")
    (wrath,) = keyword_triggered_abilities(card("Thunderous Wrath"))
    assert "{R}" in (wrath.effect or "")
    assert executes("Miracle")


# -- the proofs -----------------------------------------------------------------


def test_terminus_revealed_in_the_draw_step_is_cast_for_w_and_tucks_every_creature():
    """The whole mechanic: the turn's first draw is revealed as it is drawn,
    the linked trigger goes on the stack before anyone gets priority (CR
    603.3), and resolving it casts a sorcery in the draw step (CR 608.2g) for
    {W} rather than {4}{W}{W}. Every creature goes to the bottom of its
    owner's library."""
    scenario = _draw_step_board(
        "Terminus",
        alice_battlefield=["Plains", "Grizzly Bears"],
        bob_battlefield=["Savannah Lions", "Goblin Guide"],
    )
    scenario.will_take_the_may(True, username="alice", source="Terminus", times=2)

    _into_draw_step(scenario)

    terminus = scenario.find("Terminus", Zone.HAND, "alice")
    (question,) = _reveal_questions(scenario, "Terminus")
    assert question.player == "alice"
    assert question.card == terminus.id
    assert scenario.stack_names() == ["Terminus's triggered ability"]
    assert scenario.game.revealed_for_miracle(terminus)
    assert terminus.id in {known.card_id for known in scenario.game.known_to("bob")}

    scenario.resolve_top()

    assert scenario.stack_names() == ["Terminus"]
    assert _cast_questions(scenario, "Terminus")
    record = scenario.game.cast_record_of(scenario.find("Terminus", Zone.STACK))
    assert record is not None and record.keyword == "Miracle"
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "alice")
    assert plains.tapped, "{W} was paid, and only {W}"

    scenario.resolve_top()

    assert [p.name for p in scenario.game.battlefield] == ["Plains"]
    assert scenario.player("alice").library[-1].name == "Grizzly Bears"
    assert {c.name for c in scenario.player("bob").library[-2:]} == {
        "Savannah Lions",
        "Goblin Guide",
    }
    assert scenario.find("Terminus", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_thunderous_wrath_chooses_its_target_as_it_is_cast_from_the_trigger():
    """CR 601.2c inside CR 608.2g: the target is announced while the miracle
    trigger resolves, not when the card was revealed."""
    scenario = _draw_step_board(
        "Thunderous Wrath", alice_battlefield=["Mountain"], bob_battlefield=["Grizzly Bears"]
    )
    scenario.will_take_the_may(True, username="alice", source="Thunderous Wrath", times=2)
    scenario.will_choose_targets("bob", username="alice", source="Thunderous Wrath")

    _into_draw_step(scenario)
    scenario.resolve_top()
    wrath = scenario.find("Thunderous Wrath", Zone.STACK)
    assert [t.username for t in wrath.targets] == ["bob"]
    scenario.resolve_top()

    assert scenario.player("bob").life == 15
    assert scenario.find("Mountain", Zone.BATTLEFIELD, "alice").tapped


def test_reforge_the_soul_cast_for_its_miracle_cost_and_the_opponents_first_draw_asks():
    """Reforge the Soul (the reported card) for {1}{R}: each player discards
    their hand and draws seven. Alice's seven are not her first draws this
    turn, so none of them asks; Bob's first card of those seven is his first
    draw this turn - on Alice's turn, inside a resolving multi-card draw - so
    he is asked about it, once (CR 121.2), and only about that card."""
    scenario = (
        Scenario()
        .player(
            "bob",
            hand=["Island", "Island"],
            library=["Thunderous Wrath", "Terminus"] + ["Island"] * 10,
            battlefield=["Mountain"],
        )
        .player(
            "alice",
            hand=["Island"],
            library=["Reforge the Soul"] + ["Terminus"] * 3 + ["Plains"] * 10,
            battlefield=["Mountain", "Mountain"],
        )
        .build()
    )
    _alices_upkeep(scenario)
    scenario.will_take_the_may(True, username="alice", source="Reforge the Soul", times=2)
    scenario.will_take_the_may(False, username="bob", source="Thunderous Wrath")

    _into_draw_step(scenario)
    scenario.resolve_top()
    record = scenario.game.cast_record_of(scenario.find("Reforge the Soul", Zone.STACK))
    assert record is not None and record.keyword == "Miracle"
    assert all(m.tapped for m in scenario.game.battlefield if m.controller == "alice")
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == 7
    assert len(scenario.player("bob").hand) == 7
    assert _reveal_questions(scenario, "Terminus") == []
    (bobs,) = _reveal_questions(scenario, "Thunderous Wrath", "bob")
    assert bobs.card == scenario.find("Thunderous Wrath", Zone.HAND, "bob").id
    assert _miracle_triggers(scenario) == []


def test_entreat_the_angels_announces_x_for_its_miracle_cost():
    """CR 107.3a: an X in an alternative cost is announced as the spell is
    cast. Miracle {X}{W}{W} with four Plains: X is 2, two Angels."""
    scenario = _draw_step_board("Entreat the Angels", alice_battlefield=["Plains"] * 4)
    scenario.will_take_the_may(True, username="alice", source="Entreat the Angels", times=2)
    scenario.will_choose("2", username="alice", source="Entreat the Angels")

    _into_draw_step(scenario)
    scenario.resolve_top()
    (x_question,) = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.CHOOSE_A_QUALITY and q.source == "Entreat the Angels"
    ]
    assert x_question.options == ("0", "1", "2")
    scenario.resolve_top()

    angels = [p for p in scenario.game.battlefield if p.name != "Plains"]
    assert len(angels) == 2
    assert all(p.tapped for p in scenario.game.battlefield if p.name == "Plains")


# -- the corners -----------------------------------------------------------------


def test_a_declined_reveal_triggers_nothing_and_shows_nothing():
    """ "You may reveal": declining keeps the card hidden (no reveal record,
    nothing an opponent knows) and the linked trigger never triggers
    (CR 607.2h)."""
    scenario = _draw_step_board("Terminus", alice_battlefield=["Plains", "Grizzly Bears"])
    scenario.will_take_the_may(False, username="alice", source="Terminus")

    _into_draw_step(scenario)

    terminus = scenario.find("Terminus", Zone.HAND, "alice")
    assert len(_reveal_questions(scenario, "Terminus")) == 1
    assert scenario.stack_names() == []
    assert _miracle_triggers(scenario) == []
    assert not scenario.game.revealed_for_miracle(terminus)
    assert terminus.id not in {r.card_id for r in scenario.game.reveals}
    assert terminus.id not in {known.card_id for known in scenario.game.known_to("bob")}


def test_an_unscripted_player_does_not_reveal():
    """The documented default keeps hidden information hidden."""
    scenario = _draw_step_board("Terminus", alice_battlefield=["Plains"])
    _into_draw_step(scenario)
    assert len(_reveal_questions(scenario, "Terminus")) == 1
    assert _miracle_triggers(scenario) == []


def test_the_second_card_drawn_this_turn_is_not_asked_about():
    """The draw step's Plains is the turn's first draw; Terminus drawn off
    Opt later that turn is the second, so no question is asked."""
    scenario = (
        Scenario()
        .player("bob", library=["Island"] * 5)
        .player(
            "alice",
            library=["Plains", "Island", "Terminus"] + ["Plains"] * 5,
            battlefield=["Island"],
            hand=["Opt"],
        )
        .build()
    )
    _alices_upkeep(scenario)
    _into_draw_step(scenario)
    scenario.advance()
    assert scenario.step is Step.PRECOMBAT_MAIN
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    scenario.scry_bottoming(scenario.find("Island", Zone.LIBRARY, "alice"))
    scenario.cast_and_resolve("Opt", island)

    assert scenario.find("Terminus", Zone.HAND, "alice").zone is Zone.HAND
    assert _reveal_questions(scenario, "Terminus") == []
    assert _miracle_triggers(scenario) == []


def test_a_multi_card_draw_asks_only_about_its_first_card():
    """CR 121.2: Brainstorm is three individual draws. With a Plains on top,
    the Terminus under it is the second card drawn - not asked about; with
    Terminus on top, it is asked about, and the Terminus after it is not.
    (No draw step here: the turn-based draw is off, so Brainstorm's draws are
    Alice's first this turn.)"""
    for library, asked in (
        (["Plains", "Terminus", "Terminus"], 0),
        (["Terminus", "Terminus", "Plains"], 1),
    ):
        scenario = (
            Scenario()
            .manual_turn_based_actions()
            .player(
                "alice",
                hand=["Brainstorm"],
                library=library + ["Plains"] * 5,
                battlefield=["Island"],
            )
            .player("bob", library=["Island"] * 5)
            .build()
        )
        scenario.start_at(Step.PRECOMBAT_MAIN)
        scenario.will_take_the_may(False, username="alice", source="Terminus")
        scenario.cast_and_resolve("Brainstorm", scenario.find("Island", Zone.BATTLEFIELD))

        assert len(scenario.player("alice").hand) == 1
        assert len(_reveal_questions(scenario, "Terminus")) == asked
        assert _miracle_triggers(scenario) == []


def test_on_an_opponents_turn_off_an_instant_cantrip_the_sorcery_is_cast_anyway():
    """Bob casts Opt during Alice's turn and draws Terminus - his first card
    this turn. Revealed, the trigger resolves on Alice's turn and casts a
    sorcery there (CR 608.2g ignores timing)."""
    scenario = (
        Scenario()
        .player("alice", library=["Plains"] * 5, battlefield=["Grizzly Bears"])
        .player(
            "bob",
            hand=["Opt"],
            library=["Terminus"] + ["Island"] * 5,
            battlefield=["Island", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "alice"
    scenario.will_take_the_may(True, username="bob", source="Terminus", times=2)
    scenario.pass_priority("alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "bob")
    scenario.scry_keeping_everything_on_top(username="bob")
    scenario.cast_onto_stack("Opt", island, username="bob")
    scenario.pass_until_resolved()

    (question,) = _reveal_questions(scenario, "Terminus", "bob")
    assert scenario.stack_names() == ["Terminus's triggered ability"]
    scenario.pass_until_resolved()

    assert scenario.stack_names() == ["Terminus"]
    assert scenario.find("Plains", Zone.BATTLEFIELD, "bob").tapped
    scenario.pass_until_resolved()
    assert scenario.player("alice").library[-1].name == "Grizzly Bears"


def test_a_card_discarded_before_the_trigger_resolves_is_not_cast():
    """CR 702.94b ends the reveal as the card leaves the hand, and CR 400.7
    makes the card in the graveyard a new object the trigger cannot cast:
    Bob's Kolaghan's Command in response makes Alice discard Terminus."""
    scenario = _draw_step_board(
        "Terminus",
        alice_battlefield=["Plains", "Grizzly Bears"],
        bob_battlefield=["Swamp", "Mountain", "Mountain"],
        bob_hand=["Kolaghan's Command"],
    )
    scenario.will_take_the_may(True, username="alice", source="Terminus", times=2)
    _into_draw_step(scenario)
    terminus = scenario.find("Terminus", Zone.HAND, "alice")
    assert scenario.game.revealed_for_miracle(terminus)

    scenario.pass_priority("alice")
    casting = scenario.cast("Kolaghan's Command", "bob")
    casting.choose_modes([2, 4])
    casting.choose_targets(["alice", "alice"])
    scenario.pay_with(
        casting.begin_paying(),
        *scenario.untapped_sources("Swamp", "Mountain", "Mountain", username="bob"),
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert terminus.zone is Zone.GRAVEYARD
    assert not scenario.game.revealed_for_miracle(terminus)
    scenario.resolve_top()

    assert _cast_questions(scenario, "Terminus") == []
    assert terminus.zone is Zone.GRAVEYARD
    assert scenario.creature("Grizzly Bears").zone is Zone.BATTLEFIELD


def test_insufficient_mana_leaves_it_in_hand():
    """Only an Island: {W} cannot be paid (CR 118.3), so the cast is illegal
    (CR 601.2h) and the card stays in hand."""
    scenario = _draw_step_board("Terminus", alice_battlefield=["Island", "Grizzly Bears"])
    scenario.will_take_the_may(True, username="alice", source="Terminus", times=2)
    _into_draw_step(scenario)
    scenario.resolve_top()

    terminus = scenario.find("Terminus", Zone.HAND, "alice")
    (pay,) = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.PAY_MANA and q.source == "Terminus"
    ]
    assert pay.affirmative_is_legal is False
    assert scenario.stack_names() == []
    assert terminus.zone is Zone.HAND
    assert not scenario.game.revealed_for_miracle(terminus), "the trigger resolved (CR 702.94b)"
    assert scenario.creature("Grizzly Bears").zone is Zone.BATTLEFIELD


def test_declining_the_cast_leaves_it_in_hand_at_its_printed_cost_only():
    """Declining at resolution leaves the card in hand, revealed no longer
    (CR 702.94b); the miracle cost was only on offer while the trigger
    resolved, so in the main phase the only cast is for {4}{W}{W}."""
    scenario = _draw_step_board("Terminus", alice_battlefield=["Plains"] * 6)
    scenario.will_take_the_may(True, username="alice", source="Terminus")
    scenario.will_take_the_may(False, username="alice", source="Terminus")
    _into_draw_step(scenario)
    scenario.resolve_top()

    terminus = scenario.find("Terminus", Zone.HAND, "alice")
    assert scenario.stack_names() == []
    assert not scenario.game.revealed_for_miracle(terminus)
    assert not any(p.tapped for p in scenario.game.battlefield)
    scenario.advance()
    assert scenario.step is Step.PRECOMBAT_MAIN
    casts = [
        action for action in legal_actions(scenario.game, "alice") if action.card_id == terminus.id
    ]
    assert casts
    assert all(str(action.cost) == "{4}{W}{W}" for action in casts)


# -- pausing and replay ------------------------------------------------------------

_PENDING = TypeAdapter(PendingDecision)


def _resume_by_replay(
    snapshot: str, command: Callable[[Game], object], answer: Callable[[PendingDecision], Answer]
) -> tuple[Game, list[PendingDecision]]:
    tape: list[Answer] = []
    pauses: list[PendingDecision] = []
    for _attempt in range(6):
        game = Game.model_validate(json.loads(snapshot))
        game.decisions.begin_replay(tape)
        game.decisions.pause_when_unanswered = True
        try:
            command(game)
        except DecisionPending as paused:
            stored = _PENDING.validate_json(_PENDING.dump_json(paused.pending))
            assert stored == paused.pending
            pauses.append(stored)
            actions = legal_actions(game, stored.decision.player, pending=stored)
            assert {a.decision_option for a in actions} == {"true", "false"}
            tape.append(Answer.model_validate_json(answer(stored).model_dump_json()))
            continue
        game.decisions.finish_replay()
        return game, pauses
    raise AssertionError(f"still pausing after {pauses}")


def test_a_paused_seat_is_asked_at_draw_time_and_the_answer_replays():
    """The reveal is a real question on the paused-decision tape, enumerated
    by `legal_actions` while pending, and a replayed answer reproduces the
    trigger exactly."""
    scenario = _draw_step_board("Terminus", alice_battlefield=["Plains"])
    snapshot = json.dumps(scenario.game.model_dump(mode="json"))

    def answer(pending: PendingDecision) -> Answer:
        decision: Decision = pending.decision
        assert decision.kind is DecisionKind.MAY
        return Answer(seq=pending.seq, kind=decision.kind, player=decision.player, accept=True)

    game, pauses = _resume_by_replay(snapshot, lambda g: g.advance("alice"), answer)

    (pause,) = pauses
    assert pause.decision.player == "alice"
    assert pause.decision.source == "Terminus"
    assert [item.name for item in game.stack] == ["Terminus's triggered ability"]
    terminus = next(c for c in game.player("alice").hand if c.name == "Terminus")
    assert game.revealed_for_miracle(terminus)
    again = Game.model_validate(json.loads(json.dumps(game.model_dump(mode="json"))))
    assert again.model_dump(mode="json") == game.model_dump(mode="json")


@pytest.mark.parametrize("name", ["Terminus", "Thunderous Wrath", "Reforge the Soul"])
def test_the_reveal_question_names_the_card_to_its_owner_only(name: str):
    scenario = _draw_step_board(name, alice_battlefield=["Plains"])
    scenario.will_take_the_may(False, username="alice", source=name)
    _into_draw_step(scenario)
    (question,) = _reveal_questions(scenario, name)
    assert question.player == "alice"
    assert all(q.player != "bob" for q in _reveal_questions(scenario, name))
