""" "Choose up to one target creature spell or planeswalker spell" (Subtlety),
and the owner-not-controller choice of where it goes.

Two shapes had to be built for this ETB trigger to do anything:

- **A count-agnostic target that may legally be zero.** CR 115.6 (verified
  this session): "up to one" is nought or one, so a resolution that chooses
  no target is not a fizzle - it is the same "the target is gone, so this
  part does nothing" shape CR 608.2b already gives an ordinary target that
  turned out illegal. `machines/targeting.py` already read the phrase this
  way (`minimum=0, maximum=1`); this wave's job was to build an effect that
  reads that answer correctly rather than assuming a target is always there.
- **A choice that belongs to the target's owner, not to Subtlety's own
  controller.** CR 108.3: ownership and control are different things, and
  "its owner puts it on their choice of the top or bottom of their library"
  names the *owner* twice ("its owner", "their library") - `DecisionKind.
  PUT_ON_TOP_OR_BOTTOM` is asked of `spell.owner`, never of the ability's
  `controller`, which only matters once both players are different (the
  Grizzly Bears spell being aimed at here is bob's own, and Subtlety is
  alice's).

CR 601.2c/608.2b are what let this whole thing use "counter"-adjacent
machinery without literally countering: Subtlety's own reminder text and
official ruling both say the targeted spell is *not* countered - it never
goes to a graveyard, and nothing that cares "was this spell countered"
(CR 701.6a, CR 603.10e) should ever see it as having been. `_put_spell_in_
library` is deliberately not `Game.counter`, and this file checks that too.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board() -> Scenario:
    """Bob's own main phase (he is listed first, so he is active), so his
    sorcery-speed Grizzly Bears can legally go on the stack at all; Subtlety
    has flash (CR 702.8b), so alice can still answer from outside her own
    turn.
    """
    return (
        Scenario()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("alice", hand=["Subtlety"], battlefield=["Island"] * 4)
    )


def test_subtlety_puts_the_targeted_creature_spell_on_top_of_its_owners_library():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    islands = scenario.untapped_sources(*(["Island"] * 4), username="alice")

    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")

    scenario.choose_trigger_targets("Subtlety", [bears])
    scenario.will_choose_top(True, username="bob")
    subtlety = scenario.cast_onto_stack("Subtlety", *islands, username="alice")

    scenario.pass_until_resolved()  # Subtlety resolves and enters
    assert subtlety.zone is Zone.BATTLEFIELD

    scenario.pass_until_resolved()  # Subtlety's own ETB trigger resolves

    assert bears.zone is Zone.LIBRARY
    assert scenario.player("bob").library[0] is bears
    assert scenario.stack_names() == []


def test_the_owner_not_the_caster_chooses_top_or_bottom():
    """Bob owns Grizzly Bears; alice controls Subtlety. The choice of top or
    bottom is scripted for *bob*, and answering it for alice instead would
    leave the question unanswered and fall through to the documented
    default (top) - scripting bob to choose the bottom, and asserting on
    that specific outcome, is what actually proves the chooser is right
    rather than merely that the default happened to match.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    islands = scenario.untapped_sources(*(["Island"] * 4), username="alice")

    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")
    scenario.choose_trigger_targets("Subtlety", [bears])
    scenario.will_choose_top(False, username="bob")
    scenario.cast_onto_stack("Subtlety", *islands, username="alice")

    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.LIBRARY
    assert scenario.player("bob").library[-1] is bears


def test_choosing_no_target_still_resolves_the_trigger():
    """CR 115.6's "up to one" includes zero - Subtlety's ETB is not required
    to name a target at all, and must resolve cleanly (no notice, no error,
    the stack simply empties) when none is chosen.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources(*(["Island"] * 4), username="alice")

    scenario.choose_trigger_targets("Subtlety", [])
    scenario.pass_priority("bob")
    subtlety = scenario.cast_and_resolve("Subtlety", *islands, username="alice")
    scenario.pass_until_resolved()  # the ETB trigger, targeting nothing

    assert subtlety.zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == []
    assert scenario.game.targeting_notices == []


def test_the_targeted_spell_is_not_countered():
    """CR 701.6a/603.10e: this is not a counter. `Game.counter` is never
    called, so `TriggerEvent.SPELL_IS_COUNTERED` never fires and the spell
    never touches a graveyard - it goes straight from the stack to the
    library, exactly as `_put_spell_in_library` is built to do.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    islands = scenario.untapped_sources(*(["Island"] * 4), username="alice")

    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")
    scenario.choose_trigger_targets("Subtlety", [bears])
    scenario.cast_onto_stack("Subtlety", *islands, username="alice")

    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert bears.zone is not Zone.GRAVEYARD
    assert bears.zone is Zone.LIBRARY
