"""A "Whenever a creature you control dies" condition printed on a
*noncreature* source (CR 700.4, 603.10a).

Gardenize and Way of the Necromancer (Reality Fracture) both print this
sentence on an Enchantment. `condition_matches`'s DIES branch used to refuse
to widen past the source's own death unless the condition also said
"another"/"other" - a rule that makes sense on a *creature* source (Blood
Artist's own "this creature or another creature dies" needs the word to tell
"besides me" from "instead of me" apart), but is simply wrong on a source that
could never be the dying creature in the first place: an Enchantment is never
a candidate for its own "a creature ... dies" condition, so there is nothing
to disambiguate and the plain form has to match every creature death under
the stated control, the same way it already does for a played-out instant.

Before this fix, Gardenize's and Way of the Necromancer's own trigger never
fired for anyone's creature dying, including the controller's - `sweep_pool`'s
`unmatchable_condition` category, not a classifier artifact.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_gardenize_charges_when_a_controlled_creature_dies():
    scenario = (
        Scenario().player("alice", battlefield=["Gardenize", "Grizzly Bears"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gardenize = scenario.find("Gardenize", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Gardenize's triggered ability"]
    scenario.pass_until_resolved()
    assert gardenize.counter_count("charge") == 1


def test_gardenize_does_not_fire_for_an_opponents_creature_dying():
    """The "you control" clause still holds - the fix widens past the
    self-referential guard, it does not remove the controller clause."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gardenize"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_cauldron_of_essence_off_pool_proof_drains_a_life_on_a_creature_dying():
    """Off-pool generality proof: Cauldron of Essence prints the identical
    "Whenever a creature you control dies" sentence on an Artifact, with a
    differently shaped effect ("each opponent loses 1 life and you gain 1
    life") - not the mechanic's reported card and not in the fixture pool
    before this file."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cauldron of Essence", "Grizzly Bears"], life=20)
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Cauldron of Essence's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 21
    assert scenario.player("bob").life == 19
