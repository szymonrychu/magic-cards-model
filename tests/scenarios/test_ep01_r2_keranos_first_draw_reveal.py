"""Keranos, God of Storms (EP-01 R2, T2): "Reveal the first card you draw on
each of your turns. Whenever you reveal a land card this way, draw a card.
Whenever you reveal a nonland card this way, Keranos deals 3 damage to any
target."

Verified with `mise run rules:find`: CR 121.2 (cards are drawn one at a time),
CR 701.20a (to reveal a card), CR 603.11 / CR 607.2h (a trigger linked to the
reveal that made it). It is the mandatory, own-turns-only cousin of God-Eternal
Kefnet's "You may reveal the first card you draw each turn as you draw it"
(`test_ep01_r1_first_draw_reveal.py`).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario


def _draw_step(top: str, *, keranos_owner: str = "alice") -> PlayedScenario:
    keranos = ["Keranos, God of Storms"]
    scenario = (
        Scenario()
        .player(
            "bob",
            library=["Island"] * 10,
            battlefield=keranos if keranos_owner == "bob" else [],
        )
        .player(
            "alice",
            library=[top, "Plains", "Plains", "Plains", "Plains"],
            battlefield=keranos if keranos_owner == "alice" else [],
        )
        .build()
    )
    scenario.start_at(Step.CLEANUP)
    scenario.advance()
    scenario.advance()
    assert scenario.turn.active_player == "alice" and scenario.step is Step.UPKEEP
    return scenario


def test_a_revealed_land_draws_a_card():
    scenario = _draw_step("Forest")
    scenario.advance()
    assert scenario.step is Step.DRAW
    forest = scenario.find("Forest", Zone.HAND, "alice")
    assert forest.id in {known.card_id for known in scenario.game.known_to("bob")}
    assert scenario.stack_names() == ["Keranos, God of Storms's triggered ability"]
    hand_before = len(scenario.player("alice").hand)
    scenario.resolve_top()
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_a_revealed_nonland_deals_three_damage_to_the_chosen_target():
    scenario = _draw_step("Grizzly Bears")
    scenario.will_choose_targets("bob", username="alice")
    scenario.advance()
    assert scenario.stack_names() == ["Keranos, God of Storms's triggered ability"]
    scenario.resolve_top()
    assert scenario.player("bob").life == 17


def test_the_reveal_is_not_optional():
    scenario = _draw_step("Forest")
    scenario.advance()
    revealed = [
        question for question in scenario.questions_asked() if "reveal" in (question.prompt or "")
    ]
    assert revealed == []
    assert scenario.stack_names() == ["Keranos, God of Storms's triggered ability"]


def test_only_the_first_card_drawn_on_the_turn_is_revealed():
    scenario = _draw_step("Forest")
    scenario.advance()
    scenario.resolve_top()  # the land reveal's draw
    assert scenario.stack_names() == []


def test_keranos_reveals_nothing_on_the_opponents_turn():
    scenario = _draw_step("Forest", keranos_owner="bob")
    scenario.advance()
    # Alice's draw: bob controls Keranos, and it is not bob's turn anyway.
    assert scenario.stack_names() == []
