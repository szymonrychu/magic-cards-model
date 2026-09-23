"""Scenario: "Whenever a creature attacks you or a planeswalker you control"
- a trigger on the *defending* side of an attack.

The condition names the attacked, not the attacker's controller: the
creature attacking belongs to an opponent, and "you control" belongs to the
planeswalker being attacked (CR 508.1b: each attacking creature attacks a
player, planeswalker or battle). Read as a "creature you control attacks"
condition it never fired - found by the behavioural sweep on Slumbering
Dragon; Isperia, Supreme Judge and Circle of Flame (with its "without flying"
qualifier on the attacker) print the same template and prove it generally.

Rules verified with `mise run rules:find` in the session that wrote this file:
CR 508.1b (what each attacker attacks), CR 506.2 (the defending player),
CR 603.2 (a matching event triggers the ability).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _bob_attacks(defender_board: list[str], attacker: str = "Grizzly Bears"):
    scenario = (
        Scenario()
        .player("bob", battlefield=[attacker], library=["Forest"] * 3)
        .player("alice", battlefield=defender_board, library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario, scenario.creature(attacker, "bob")


def test_slumbering_dragon_grows_when_a_creature_attacks_its_controller():
    scenario, bears = _bob_attacks(["Slumbering Dragon"])

    scenario.attack_with(bears, defending="alice")
    assert "Slumbering Dragon's triggered ability" in scenario.stack_names()
    scenario.pass_until_resolved()

    dragon = scenario.creature("Slumbering Dragon", "alice")
    assert dragon.counter_count("+1/+1") == 1


def test_it_triggers_when_the_attack_is_on_a_planeswalker_its_controller_controls():
    scenario, bears = _bob_attacks(["Slumbering Dragon", "Kaito, Bane of Nightmares"])
    kaito = scenario.find("Kaito, Bane of Nightmares", Zone.BATTLEFIELD, "alice")

    scenario.attack_with(bears, defending=kaito)

    assert "Slumbering Dragon's triggered ability" in scenario.stack_names()


def test_it_does_not_trigger_on_its_own_controllers_attack():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Slumbering Dragon", "Grizzly Bears"])
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"), defending="bob")

    assert scenario.stack_names() == []


def test_isperia_draws_when_a_creature_attacks_its_controller():
    """The same template on a different card and effect: "you may draw a
    card" (CR 603.5's optional effect; the default answer takes it)."""
    scenario, bears = _bob_attacks(["Isperia, Supreme Judge"])
    hand_before = len(scenario.player("alice").hand)

    scenario.attack_with(bears, defending="alice")
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").hand) == hand_before + 1
