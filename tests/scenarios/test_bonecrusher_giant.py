"""Bonecrusher Giant's "becomes the target of a spell" trigger (CR 702.21a's
own event, generic and not ward-specific).

"Whenever this creature becomes the target of a spell, this creature deals 2
damage to that spell's controller."

`TriggerEvent.BECOMES_TARGET` was already emitted by `Casting.
_emit_becomes_target` for *any* spell that targets a permanent (ward reads
it too) - the missing half was the effect itself, "that spell's controller"
read off `GameEvent.targeted_by` rather than `event.subject_id` (which is
Bonecrusher Giant, the thing that got targeted, not the spell that targeted
it).

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 702.21a, 120.1, 120.3a.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Lava Dart"], battlefield=["Mountain"])
        .player("bob", battlefield=["Bonecrusher Giant"])
    )


def resolve_all(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def test_targeting_it_with_a_spell_deals_2_damage_to_that_spells_caster():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Bonecrusher Giant", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    before = scenario.player("alice").life

    scenario.cast_onto_stack("Lava Dart", mountain, targets=[giant])
    assert scenario.stack_names() == [
        "Lava Dart",
        "Bonecrusher Giant's triggered ability",
    ]
    resolve_all(scenario)

    assert scenario.player("alice").life == before - 2
    assert giant.zone.value == "battlefield"  # Bonecrusher survives a 1-damage Dart


def test_a_spell_that_does_not_target_it_never_triggers():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    before = scenario.player("alice").life

    scenario.cast_and_resolve("Lava Dart", mountain, targets=["bob"])

    assert scenario.player("alice").life == before
