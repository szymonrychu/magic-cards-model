"""Judge scenarios: what counts as a mana ability, and what that costs you.

Sourced from the DDR judge transcripts. Episodes covered:

- **DDR#990** - Toph, the First Metalbender + Caged Sun (a triggered mana
  ability that feeds itself, and why nobody ever gets priority to stop it)
- **DDR#988** - When is Firebending Student's power checked? (an ability whose
  X is defined by its own text, read as the ability resolves)

The two episodes are the same question from opposite ends. CR 605.1b is the
definition both turn on: "A triggered ability is a mana ability if it meets all
of the following criteria: it doesn't require a target (see rule 115.6), it
triggers from the activation or resolution of an activated mana ability ...".
Caged Sun's bottom ability meets it, which is what makes the loop unstoppable
(CR 605.4a: "A triggered mana ability doesn't go on the stack, so it can't be
targeted, countered, or otherwise responded to"); firebending does not, because
attacking is not the activation or resolution of a mana ability, which is what
makes DDR#988's question about *when* X is read a real question at all.

Every test here is `xfail`: neither card's ability reaches the engine.
`machines/triggers.triggered_abilities_of` returns an empty list for Caged Sun
and, for Firebending Student, only its prowess - the CR 702.189a keyword line is
not expanded into the trigger it stands for. Every CR number here was looked up
with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# DDR#990 - Caged Sun's triggered mana ability
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="Caged Sun is inert in this engine: `triggered_abilities_of(card("
    "'Caged Sun'))` is empty and `effect_for('Caged Sun', ...)` is None, so "
    "neither its 'As this artifact enters, choose a color' nor its "
    "'Whenever a land's ability causes you to add ... add an additional one "
    "mana of that color' has any reader. Tapping a Mountain adds one red, not "
    "two.",
)
def test_caged_sun_adds_an_additional_mana_when_a_land_makes_the_chosen_color():
    """DDR#990's prerequisite: the ordinary, non-looping use of Caged Sun.

    Caged Sun (confirmed with `resolve_cards`): "Whenever a land's ability
    causes you to add one or more mana of the chosen color, add an additional
    one mana of that color." CR 605.1b makes this a triggered mana ability -
    it needs no target and it triggers from the resolution of the Mountain's
    activated mana ability - and CR 605.4a resolves it "immediately after the
    mana ability that triggered it, without waiting for priority".

    So one tap of one Mountain leaves two red mana in the pool.
    """
    scenario = Scenario().player("alice", battlefield=["Caged Sun", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")

    scenario.activate(mountain)

    assert scenario.player("alice").mana_pool.floating.get(Color.RED) == 2


@pytest.mark.xfail(
    strict=True,
    reason="two separate gaps stack here: Toph's 'Nontoken artifacts you "
    "control are lands in addition to their other types' has no entry in "
    "`machines/layers.LAYER_EFFECTS` (see test_judge_layers.py's DDR#994), and "
    "Caged Sun's own trigger is unparsed as above. `Game.drawn` is also "
    "documented as covering only CR 104.4a's simultaneous loss - its docstring "
    "says CR 104.4b's mandatory-action loops 'have no loop machinery behind "
    "them' - so nothing in the engine could detect this loop even with both "
    "cards working.",
)
def test_toph_turning_caged_sun_into_a_land_draws_the_game():
    """DDR#990: the loop is mandatory and nobody ever gets priority in it.

    With Toph making Caged Sun a land, Caged Sun's own bottom ability becomes
    "a land's ability" causing alice to add red - so it triggers off itself,
    forever. CR 605.1b still calls that a mana ability (the episode's ruling,
    against CR 605.5a's older wording, is that being a mana ability is a
    property of the ability rather than of the game state), and CR 605.4a keeps
    it off the stack, so no player ever receives priority to break it.

    CR 104.4b: "If a game that's not using the limited range of influence
    option (including a two-player game) somehow enters a 'loop' of mandatory
    actions, repeating a sequence of events with no way to stop, the game is a
    draw."
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Toph, the First Metalbender", "Caged Sun", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")

    scenario.activate(mountain)

    assert scenario.game.drawn is True


# --------------------------------------------------------------------------
# DDR#988 - firebending X, and when X is read
# --------------------------------------------------------------------------


def _firebending_student_attacks(pump: bool = False):
    """Alice attacks with Firebending Student, optionally holding a pump spell
    she can cast in response to the firebending trigger.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"] if pump else [],
            battlefield=["Firebending Student"] + (["Forest"] if pump else []),
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    student = scenario.creature("Firebending Student", "alice")
    scenario.attack_with(student)
    return scenario, student


@pytest.mark.xfail(
    strict=True,
    reason="`triggered_abilities_of(card('Firebending Student'))` returns only "
    "its prowess trigger - the 'Firebending X, where X is this creature's "
    "power' keyword line is not expanded into the CR 702.189a triggered ability "
    "it stands for, so attacking adds no mana at all and the pool stays empty.",
)
def test_firebending_adds_mana_equal_to_the_creatures_power_when_it_attacks():
    """DDR#988's prerequisite: firebending is a triggered ability that uses the stack.

    CR 702.189a: "Firebending is a triggered ability. 'Firebending N' means
    'Whenever this creature attacks, add N {R}. Until end of combat, you don't
    lose this mana as steps and phases end.'" It is *not* a mana ability: CR
    605.1b requires a triggered mana ability to trigger from the activation or
    resolution of an activated mana ability, and attacking is neither - which
    is exactly why the episode's question about timing exists.

    Firebending Student is a 1/2 (confirmed with `resolve_cards`), so a plain
    attack adds one red.
    """
    scenario, _ = _firebending_student_attacks()

    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert scenario.player("alice").mana_pool.floating.get(Color.RED) == 1


@pytest.mark.xfail(
    strict=True,
    reason="same gap: with no firebending trigger on the stack there is nothing "
    "to respond to, and no mana is added however large the creature gets.",
)
def test_pumping_the_student_in_response_to_the_trigger_gets_more_mana():
    """DDR#988's actual ruling: X is read as the firebending ability resolves.

    "Firebending X, where X is this creature's power" defines X in its own
    text, so nothing is announced when the ability goes on the stack. CR
    608.2h: "If an effect requires information from the game (such as the
    number of creatures on the battlefield), the answer is determined only
    once, when the effect is applied." So pumping the Student while its
    firebending trigger waits on the stack increases the mana it makes.

    Giant Growth on a 1/2 makes it a 4/5, and it is a noncreature spell, so
    prowess (CR 702.108a) resolves first and pushes it to 5/6 - five red.
    """
    scenario, student = _firebending_student_attacks(pump=True)

    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_onto_stack("Giant Growth", forest, username="alice", targets=[student])
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert scenario.game.power_of(student) == 5
    assert scenario.player("alice").mana_pool.floating.get(Color.RED) == 5
