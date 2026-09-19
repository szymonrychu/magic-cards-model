"""Ferocity of the Hunt's own "When enchanted creature dies, ..." (CR 303.4b,
303.4m's "enchanted [object]"; CR 603.10a's look-back).

`condition_matches`'s DIES branch used to read only the self-referential
"When this creature dies" and the "another"/"other" widened forms; an Aura's
own "enchanted creature" subject - naming neither the Aura itself nor a
generic "another" creature, but specifically whatever it is attached to -
matched nothing at all before this fix (`sweep_pool`'s `unmatchable_condition`
category).
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_ferocity_of_the_hunt_triggers_when_the_enchanted_creature_dies():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ferocity of the Hunt"],
            battlefield=["Grizzly Bears", "Swamp", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    aura = scenario.cast_and_resolve(
        "Ferocity of the Hunt", username="alice", targets=[bears], auto=True
    )
    assert aura.attached_to == bears.id

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Ferocity of the Hunt's triggered ability"]


def test_ferocity_of_the_hunt_does_not_trigger_for_an_unrelated_creature_dying():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ferocity of the Hunt"],
            battlefield=["Grizzly Bears", "Steppe Lynx", "Swamp", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    lynx = scenario.creature("Steppe Lynx", "alice")

    scenario.cast_and_resolve("Ferocity of the Hunt", username="alice", targets=[bears], auto=True)

    scenario.game.destroy(lynx)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_bequeathal_off_pool_proof_draws_two_cards_when_the_enchanted_creature_dies():
    """Off-pool generality proof: Bequeathal prints the identical "When
    enchanted creature dies, ..." sentence with a differently shaped effect
    ("you draw two cards" rather than a reanimation-style return)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bequeathal"],
            battlefield=["Grizzly Bears", "Forest"],
            library=["Mountain", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve("Bequeathal", username="alice", targets=[bears], auto=True)

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Bequeathal's triggered ability"]
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 2
