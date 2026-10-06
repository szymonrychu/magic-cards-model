"""Group attack requirement with a duration: "Until your next turn, creatures
your opponents control attack each combat if able."

Listed-card context (NW-01, task T3): **The Akroan War** chapter II. The
requirement is CR 508.1d's; "until your next turn" is CR 611.2a's duration;
the set of creatures is fixed as the effect begins (CR 611.2c), so a creature
that enters afterwards is not bound.

Rules read with `mise run rules:find` in the session that wrote this file:
CR 508.1d, CR 611.2a, CR 611.2c.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _resolve_stack(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _advance_until(scenario, predicate) -> None:
    while not predicate(scenario):
        scenario.advance()
        _resolve_stack(scenario)


def _to_bobs_attack(scenario) -> None:
    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.BEGINNING_OF_COMBAT,
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)


def _saga_at_chapter_two():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["The Akroan War"], battlefield=["Grizzly Bears"], library=["Plains"] * 10
        )
        .player(
            "bob",
            battlefield=["Colossal Dreadmaw", "Runeclaw Bear", "Hill Giant"],
            hand=["Grizzly Bears"],
            library=["Forest"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("The Akroan War", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(saga, "alice")
    scenario.choose_trigger_targets(
        "The Akroan War", [scenario.creature("Colossal Dreadmaw", "bob")]
    )
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    scenario.game.add_counters(saga, Counter.LORE, 1)
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    return scenario


def test_each_opponent_creature_must_attack_on_its_controllers_turn():
    scenario = _saga_at_chapter_two()
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    _to_bobs_attack(scenario)

    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with()
    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(runeclaw)

    scenario.attack_with(runeclaw, giant, defending="alice")
    assert scenario.attackers() == [runeclaw, giant]


def test_the_creature_you_took_is_not_an_opponents_creature():
    scenario = _saga_at_chapter_two()
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")

    assert dreadmaw.controller == "alice"
    _to_bobs_attack(scenario)
    scenario.attack_with(
        scenario.creature("Runeclaw Bear", "bob"), scenario.creature("Hill Giant", "bob")
    )


def test_a_tapped_opponent_creature_breaks_no_requirement():
    scenario = _saga_at_chapter_two()
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.PRECOMBAT_MAIN,
    )
    runeclaw.tap()
    _to_bobs_attack(scenario)

    scenario.attack_with(giant)

    assert scenario.attackers() == [giant]


def test_a_creature_that_arrives_later_is_not_bound():
    """CR 611.2c: only the creatures on the battlefield as chapter II resolved."""
    scenario = _saga_at_chapter_two()
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    late = scenario.put_onto_battlefield("Grizzly Bears", "bob")
    _to_bobs_attack(scenario)

    scenario.attack_with(runeclaw, giant)

    assert scenario.attackers() == [runeclaw, giant]
    assert late.zone is Zone.BATTLEFIELD


def test_the_requirement_ends_when_alices_next_turn_begins():
    scenario = _saga_at_chapter_two()
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    _to_bobs_attack(scenario)
    scenario.attack_with(runeclaw, giant)
    _advance_until(scenario, lambda s: s.turn.active_player == "alice")
    _advance_until(scenario, lambda s: s.turn.active_player == "bob")
    _to_bobs_attack(scenario)

    scenario.attack_with()

    assert scenario.attackers() == []
