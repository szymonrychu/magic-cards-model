"""CR 115.9a: "target spell or ability **with a single target**".

Bolt Bend (verified with `resolve_cards`): "This spell costs {3} less to cast
if you control a creature with power 4 or greater. Change the target of target
spell or ability with a single target."

The phrase names a property of the spell being targeted - how many targets it
was put on the stack with - not a second target of Bolt Bend's own. CR 115.9a:
"An object that looks for a '[spell or ability] with [a number of] targets'
checks the number of times any object or player was chosen as the target of
that spell or ability when it was put on the stack."

`machines/targeting.py` used to read the trailing word "target" as a whole
second requirement, so Bolt Bend asked for two targets and no announcement
could ever satisfy it (CR 601.2c) - the card was uncastable at anything at
all. The restriction now rides on the one requirement it qualifies
(`TargetRequirement.required_target_count`).

This file is about the restriction itself: what satisfies it, what does not,
and that it stays on the card that prints it. `judge/test_judge_retargeting.py`
covers DDR#959's own no-targets case and the separate, still-unmodelled
question of a resolving spell actually *changing* another spell's target
(CR 115.7a).

Every CR number here was looked up with `knowledge_search(type="rules")` in
this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import targeting_profile
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Alice casts the spell to be aimed at; Bob holds the retargeting spells."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt", "Prey Upon", "Grizzly Bears"],
            battlefield=["Mountain", "Forest", "Forest", "Grizzly Bears"],
        )
        .player(
            "bob",
            hand=["Bolt Bend", "Deflecting Swat"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Memnite"],
        )
    )


def test_the_restriction_is_read_as_one_requirement_not_two():
    """CR 115.1: "the targets are object(s) and/or player(s) the spell or
    ability will affect", declared one per instance of the word "target"
    (CR 601.2c). Bolt Bend prints the word twice but asks for one target: the
    second is CR 115.9a's count, a property of the first.
    """
    profile = targeting_profile(card("Bolt Bend"))

    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.count == 1
    assert requirement.zones == frozenset({Zone.STACK})
    assert requirement.required_target_count == 1


def test_bolt_bend_may_target_a_spell_with_exactly_one_target():
    """The legal case: Lightning Bolt was put on the stack with one target
    (CR 115.9a counts the times a target was chosen), so the announcement
    stands.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.pass_priority("alice")

    bend = scenario.cast_onto_stack("Bolt Bend", auto=True, username="bob", targets=[bolt])

    assert bend.zone is Zone.STACK
    assert scenario.stack_names() == ["Lightning Bolt", "Bolt Bend"]


def test_bolt_bend_refuses_a_spell_with_no_targets():
    """A creature spell chose nothing, so it has zero targets - not one
    (CR 115.9a), and CR 601.2c refuses the announcement.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.cast_onto_stack("Grizzly Bears", auto=True, username="alice")
    scenario.pass_priority("alice")

    with pytest.raises(ValueError, match="single target"):
        scenario.cast_onto_stack("Bolt Bend", auto=True, username="bob", targets=[bears])


def test_bolt_bend_refuses_a_spell_with_two_targets():
    """Prey Upon (verified with `resolve_cards`): "Target creature you control
    fights target creature you don't control." Two instances of the word
    "target", two targets chosen, so CR 115.9a's count is two and the
    announcement is refused just as firmly as the zero-target case.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "bob")

    prey = scenario.cast_onto_stack(
        "Prey Upon",
        auto=True,
        username="alice",
        targets=[bears, memnite],
    )
    scenario.pass_priority("alice")

    with pytest.raises(ValueError, match="single target"):
        scenario.cast_onto_stack("Bolt Bend", auto=True, username="bob", targets=[prey])


def test_a_retargeting_spell_without_the_restriction_still_takes_any_spell():
    """The restriction stays on the card that prints it. Deflecting Swat
    ("You may choose new targets for target spell or ability") names no count
    at all, so a spell with no targets is a legal target for it (CR 115.1) -
    the contrast DDR#959 draws, and proof the new
    `required_target_count` is not being applied card-wide.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.cast_onto_stack("Grizzly Bears", auto=True, username="alice")
    scenario.pass_priority("alice")

    swat = scenario.cast_onto_stack("Deflecting Swat", auto=True, username="bob", targets=[bears])

    assert swat.zone is Zone.STACK
