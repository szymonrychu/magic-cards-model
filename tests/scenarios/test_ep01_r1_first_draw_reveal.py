"""God-Eternal Kefnet (EP-01 round 1, task T7): "You may reveal the first card
you draw each turn as you draw it. Whenever you reveal an instant or sorcery
card this way, copy that card and you may cast the copy. That copy costs {2}
less to cast."

- CR 121.2 / CR 702.94a's shape: the reveal is asked as the turn's first card
  is drawn, of the drawing player only.
- CR 603.3: the linked trigger waits for the next priority.
- CR 707.12: the copy is created in the zone the card is in (the hand) and is
  cast following CR 601.2a-i; CR 601.2f / CR 118.7: {2} less to cast reduces
  generic mana only.
- CR 707.10a: a copy that is not cast ceases to exist.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario


def _draw_step(
    top: str, *, battlefield: list[str], opponent_kefnet: bool = False
) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "bob",
            library=["Island"] * 10,
            battlefield=["God-Eternal Kefnet"] if opponent_kefnet else [],
        )
        .player("alice", library=[top] + ["Plains"] * 10, battlefield=battlefield)
        .build()
    )
    scenario.start_at(Step.CLEANUP)
    scenario.advance()
    scenario.advance()
    assert scenario.turn.active_player == "alice" and scenario.step is Step.UPKEEP
    return scenario


def _reveal_questions(scenario: PlayedScenario, name: str):
    return [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.MAY and q.source == name and "reveal" in q.prompt
    ]


def test_revealed_sorcery_is_copied_and_the_copy_cast_for_two_less():
    scenario = _draw_step("Divination", battlefield=["God-Eternal Kefnet", "Island", "Island"])
    scenario.will_take_the_may(True, username="alice", source="God-Eternal Kefnet", times=2)
    scenario.advance()
    assert scenario.step is Step.DRAW
    divination = scenario.find("Divination", Zone.HAND, "alice")
    (question,) = _reveal_questions(scenario, "God-Eternal Kefnet")
    assert question.player == "alice" and question.card == divination.id
    assert scenario.stack_names() == ["God-Eternal Kefnet's triggered ability"]
    assert divination.id in {known.card_id for known in scenario.game.known_to("bob")}

    scenario.resolve_top()

    assert scenario.stack_names() == ["Divination"]
    copy = scenario.find("Divination", Zone.STACK)
    assert copy.is_copy
    # {2}{U} less {2} is {U}: one Island tapped, the other left.
    tapped = [p for p in scenario.game.battlefield if p.name == "Island" and p.tapped]
    assert len(tapped) == 1
    # The original stays in hand, untouched.
    assert scenario.find("Divination", Zone.HAND, "alice").id == divination.id


def test_declining_the_cast_leaves_no_copy_behind():
    scenario = _draw_step("Divination", battlefield=["God-Eternal Kefnet", "Island"])
    scenario.will_take_the_may(True, username="alice", source="God-Eternal Kefnet", times=1)
    scenario.will_take_the_may(False, username="alice", source="God-Eternal Kefnet", times=1)
    scenario.advance()
    scenario.resolve_top()
    assert scenario.stack_names() == []
    copies = [c for c in scenario.player("alice").hand if c.is_copy]
    assert copies == []


def test_a_revealed_creature_is_not_copied():
    scenario = _draw_step("Grizzly Bears", battlefield=["God-Eternal Kefnet"])
    scenario.will_take_the_may(True, username="alice", source="God-Eternal Kefnet", times=1)
    scenario.advance()
    assert _reveal_questions(scenario, "God-Eternal Kefnet")
    assert scenario.stack_names() == []
    assert len([c for c in scenario.player("alice").hand if c.name == "Grizzly Bears"]) == 1


def test_declining_the_reveal_triggers_nothing_and_asks_no_more():
    scenario = _draw_step("Divination", battlefield=["God-Eternal Kefnet", "Island", "Island"])
    scenario.will_take_the_may(False, username="alice", source="God-Eternal Kefnet", times=1)
    scenario.advance()
    assert scenario.stack_names() == []
    assert len(_reveal_questions(scenario, "God-Eternal Kefnet")) == 1


def test_only_the_controller_of_kefnet_is_asked():
    scenario = _draw_step("Divination", battlefield=[], opponent_kefnet=True)
    scenario.advance()
    assert _reveal_questions(scenario, "God-Eternal Kefnet") == []
    assert scenario.stack_names() == []
