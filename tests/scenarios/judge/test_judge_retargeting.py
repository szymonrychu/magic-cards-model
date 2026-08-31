"""Judge scenarios: aiming a retargeting spell at a spell that has no targets.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#959** - Deflecting Swat vs. Grizzly Bears. Nick wants to cast
  Deflecting Swat targeting Amy's Grizzly Bears - a creature spell on the
  stack with no targets of its own. Is that a legal play?

The ruling is yes. Deflecting Swat says "You may choose new targets for target
spell or ability" and names no property that spell must have - not a card type,
not a number of targets - so any spell on the stack is a legal target
(CR 115.1, CR 601.2c). That one of its instructions will be impossible to carry
out on resolution is CR 101.3's problem, not the announcement's. The episode
contrasts this with two cards that *do* name a property: Goblin Flectomancer
("target instant or sorcery spell") and Bolt Bend ("target spell or ability
with a single target", CR 115.9a).

Card text verified with `resolve_cards`; every CR number here was looked up
with `knowledge_search(type="rules")` in this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import targeting_profile
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Alice casting Grizzly Bears; Bob holding both retargeting spells."""
    return (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("bob", hand=["Deflecting Swat", "Bolt Bend"], battlefield=["Mountain"] * 4)
    )


def test_deflecting_swat_asks_for_a_spell_and_nothing_more():
    """DDR#959's parser half: the requirement is "target spell", full stop.

    Deflecting Swat (verified with `resolve_cards`): "If you control a
    commander, you may cast this spell without paying its mana cost. You may
    choose new targets for target spell or ability."

    CR 115.7d is the retargeting permission ("If an effect allows a player to
    'choose new targets' for a spell or ability, the player may leave any
    number of the targets unchanged"), and it names no requirement of its own -
    `machines/targeting.py` drops that phrase before reading the template, so
    what is left is CR 115.1's plain "target spell or ability". One requirement,
    restricted to the stack, with no card-type filter at all.
    """
    profile = targeting_profile(card("Deflecting Swat"))

    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.zones == frozenset({Zone.STACK})
    assert requirement.card_types == frozenset(), "no card type is demanded"
    assert requirement.count == 1


def test_deflecting_swat_may_target_a_creature_spell_with_no_targets():
    """DDR#959's ruling: the play is legal.

    CR 601.2c has the caster announce "an appropriate object or player for each
    target the spell requires"; Grizzly Bears is a spell on the stack, so it is
    appropriate. CR 601.3 is satisfied - a rule allows Nick to cast an instant -
    and nothing about a target's later usefulness is checked at announcement.

    Grizzly Bears has no oracle text at all (verified with `resolve_cards`), so
    it is exactly the episode's target: a spell with zero targets of its own.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.cast_onto_stack("Grizzly Bears", auto=True, username="alice")
    scenario.pass_priority("alice")

    scenario.cast_onto_stack("Deflecting Swat", auto=True, username="bob", targets=[bears])

    assert scenario.stack_names() == ["Grizzly Bears", "Deflecting Swat"]


def test_deflecting_swat_resolving_leaves_a_targetless_spell_alone():
    """DDR#959's follow-through: CR 101.3 ignores the impossible instruction.

    "Any part of an instruction that's impossible to perform is ignored. (In
    many cases the card will specify consequences for this; if it doesn't,
    there's no effect.)" There are no targets to choose new ones for, so
    nothing happens and Grizzly Bears resolves normally onto the battlefield.

    The episode also notes that Deflecting Swat says "you *may*", so a player
    who does not want to retarget never faces the question - which is CR 115.7d
    in the same breath.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.cast_onto_stack("Grizzly Bears", auto=True, username="alice")
    scenario.pass_priority("alice")
    swat = scenario.cast_onto_stack("Deflecting Swat", auto=True, username="bob", targets=[bears])

    scenario.resolve_top()
    scenario.resolve_top()

    assert swat.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD


def test_bolt_bend_cannot_be_aimed_at_a_spell_with_no_targets():
    """DDR#959's contrast case: Bolt Bend is the one that refuses this play.

    Bolt Bend (verified with `resolve_cards`): "This spell costs {3} less to
    cast if you control a creature with power 4 or greater. Change the target
    of target spell or ability with a single target."

    CR 115.9a: "An object that looks for a '[spell or ability] with [a number
    of] targets' checks the number of times any object or player was chosen as
    the target of that spell or ability when it was put on the stack". Grizzly
    Bears was put on the stack with zero, so it is not a legal target for Bolt
    Bend, and announcing it should be refused for *that* reason (CR 601.2c).

    The engine used to refuse it for the wrong reason: `targeting_profile`
    came back with **two** requirements - the intended "target spell", plus a
    second any-target-shaped one read out of the tail "with a single target" -
    so the message was "too few targets: 1 chosen where the spell requires 2"
    and Bolt Bend was castable at nothing at all. The tail is now read as
    `TargetRequirement.required_target_count`, and the refusal names the real
    reason. `tests/scenarios/test_single_target_restriction.py` carries the
    rest of the restriction's cases.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.cast_onto_stack("Grizzly Bears", auto=True, username="alice")
    scenario.pass_priority("alice")

    with pytest.raises(ValueError, match="single target"):
        scenario.cast_onto_stack("Bolt Bend", auto=True, username="bob", targets=[bears])


@pytest.mark.xfail(
    reason="CR 115.7d's 'choose new targets' is implemented only for a copy of "
    "a spell (Game.offer_new_targets_for_copy); nothing retargets a spell "
    "already on the stack, and Deflecting Swat has no effect_for row",
    strict=True,
)
def test_deflecting_swat_moves_a_bolt_from_its_caster_to_someone_else():
    """DDR#959's premise, spelled out on a spell that *does* have a target.

    CR 115.7d: "If an effect allows a player to 'choose new targets' for a
    spell or ability, the player may leave any number of the targets unchanged,
    even if those targets would be illegal." Bob redirects Alice's Lightning
    Bolt back at her.

    Not implemented: the engine's only retargeting path is
    `Game.offer_new_targets_for_copy`, built for CR 707.10c's copies (Alania,
    Divergent Storm). A real spell on the stack keeps the `TargetRef` it was
    announced with, and `effect_for("Deflecting Swat", ...)` is None, so the
    Swat resolves and changes nothing - the Bolt still hits bob.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", hand=["Deflecting Swat"], battlefield=["Mountain"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Deflecting Swat", auto=True, username="bob", targets=[bolt])

    scenario.resolve_top()
    scenario.resolve_top()

    assert scenario.player("alice").life == 17
    assert scenario.player("bob").life == 20
