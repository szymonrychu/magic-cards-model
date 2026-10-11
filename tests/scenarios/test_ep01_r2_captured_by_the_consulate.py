"""Captured by the Consulate (EP-01 R2, T2): "Whenever an opponent casts a
spell, if it has a single target, change the target to enchanted creature if
able."

Rules read with `mise run rules:find` this session:

- CR 603.2 / CR 603.4 - the trigger and its intervening "if".
- CR 115.7a - changing a target to a new one that is legal; "if able" means a
  target that is not legal for the spell leaves it unchanged.
- CR 115.1 - a spell with no target, or with two, has no single target.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import TargetRef
from tests.scenarios.harness import Scenario


def _board(bob_hand):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "bob",
            hand=bob_hand,
            battlefield=["Grizzly Bears", "Mountain", "Mountain", "Island"],
        )
        .player("alice", battlefield=["Captured by the Consulate"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.find("Captured by the Consulate", Zone.BATTLEFIELD).attach_to(bears)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, bears


def _cast_and_trigger(scenario, name, targets):
    lands = [
        scenario.find("Mountain", Zone.BATTLEFIELD, "bob"),
        scenario.find("Island", Zone.BATTLEFIELD, "bob"),
    ]
    spell = scenario.cast_onto_stack(name, *lands, username="bob", targets=targets)
    scenario.game.put_triggers_on_stack()
    return spell


def test_a_single_target_spell_is_retargeted_to_the_enchanted_creature():
    scenario, bears = _board(["Lightning Bolt"])
    spell = _cast_and_trigger(scenario, "Lightning Bolt", ["alice"])
    assert "Captured by the Consulate's triggered ability" in scenario.stack_names()
    scenario.resolve_top()
    assert [t.card_id for t in spell.targets] == [bears.id]


def test_a_spell_with_no_target_is_left_alone():
    scenario, _ = _board(["Opt"])
    _cast_and_trigger(scenario, "Opt", [])
    assert "Captured by the Consulate's triggered ability" not in scenario.stack_names()


def test_a_two_target_spell_does_not_trigger():
    scenario, bears = _board(["Arc Trail"])
    _cast_and_trigger(scenario, "Arc Trail", ["alice", bears])
    assert "Captured by the Consulate's triggered ability" not in scenario.stack_names()


def test_a_spell_that_cannot_target_the_enchanted_creature_keeps_its_target():
    scenario, bears = _board(["Lightning Bolt"])
    spell = _cast_and_trigger(scenario, "Lightning Bolt", ["alice"])
    # the enchanted creature leaves the battlefield: no legal new target
    scenario.game.destroy(bears)
    scenario.resolve_top()
    assert spell.targets == [TargetRef.to_player("alice")]
