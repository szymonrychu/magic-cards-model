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


def redirection_board() -> Scenario:
    """Alice pointing a Bolt at Bob; Bob holding the Swat to send it back."""
    return (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", hand=["Deflecting Swat"], battlefield=["Mountain"] * 3)
    )


def test_deflecting_swat_moves_a_bolt_from_its_caster_to_someone_else():
    """DDR#959's premise, spelled out on a spell that *does* have a target.

    CR 115.7d: "If an effect allows a player to 'choose new targets' for a
    spell or ability, the player may leave any number of the targets unchanged,
    even if those targets would be illegal." Bob redirects Alice's Lightning
    Bolt back at her, and it is *Bob* who chooses - the Swat's controller, not
    the Bolt's (CR 115.7's "some effects allow a player to change the
    target(s)"; the player is the one the effect names).

    The Swat resolves first (CR 608.2: last on, first off), so the Bolt is
    still on the stack with its old target when the new one is chosen, and only
    then does the Bolt itself resolve into alice's face for its printed 3.
    """
    scenario = redirection_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Deflecting Swat", auto=True, username="bob", targets=[bolt])
    scenario.will_choose_targets("alice", username="bob")

    scenario.resolve_top()
    scenario.resolve_top()

    assert scenario.player("alice").life == 17
    assert scenario.player("bob").life == 20


def test_declining_the_swats_may_leaves_the_bolt_where_it_was():
    """CR 115.7d is a permission, and Deflecting Swat spells it "you may".

    A controller who declines the CR 608.2d question changes nothing, and the
    Bolt resolves at the target it was announced with - which is the same
    outcome as an unread effect, so this is the case that has to be driven by
    an explicit refusal rather than by silence.
    """
    scenario = redirection_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Deflecting Swat", auto=True, username="bob", targets=[bolt])
    scenario.will_take_the_may(False, username="bob")

    scenario.resolve_top()
    scenario.resolve_top()

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 17


def test_the_swats_own_controller_is_the_one_asked():
    """CR 115.7d hands the choice to the player the retargeting effect names.

    Alice cast the Bolt, but it is Bob's Swat, so it is Bob who answers - a
    scripted answer addressed to alice is never consumed, and the question put
    to bob falls through to the default instead.
    """
    scenario = redirection_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Deflecting Swat", auto=True, username="bob", targets=[bolt])
    scenario.will_take_the_may(False, username="alice")

    scenario.resolve_top()

    assert [question.player for question in scenario.questions_asked()] == ["bob", "bob"]
