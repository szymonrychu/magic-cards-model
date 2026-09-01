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

Caged Sun's trigger now parses, matches `ExtraTriggerEvent.MANA_ADDED`, and is
resolved inline by `Game.resolve_triggered_mana_abilities` exactly as CR 605.4a
requires; CR 104.4b's loop bound lives there too. Firebending now parses as the
CR 702.189a keyword it is, rather than as a static ability. What is still
missing for each episode is named in each `xfail` below, and lives in files this
change does not touch. Every CR number here was looked up with
`knowledge_search(type="rules")`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind, parse_abilities
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Choice, ChoiceKind
from tests.cards import card
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# DDR#990 - Caged Sun's triggered mana ability
# --------------------------------------------------------------------------


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
    caged_sun = scenario.find("Caged Sun", Zone.BATTLEFIELD, "alice")
    # CR 614.1c/614.12a: "As this artifact enters, choose a color." A staged
    # battlefield never ran the as-enters replacement, so the answer is set
    # here, the same way `test_chosen_color_mana.py` sets Mikokoro's Citadel's.
    caged_sun.choice = Choice(kind=ChoiceKind.COLOR, value=Color.RED.value)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")

    scenario.activate(mountain)

    assert scenario.stack_names() == [], "CR 605.4a: a triggered mana ability never uses the stack"
    assert scenario.player("alice").mana_pool.floating.get(Color.RED) == 2


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
    caged_sun = scenario.find("Caged Sun", Zone.BATTLEFIELD, "alice")
    caged_sun.choice = Choice(kind=ChoiceKind.COLOR, value=Color.RED.value)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")

    scenario.activate(mountain)

    assert scenario.game.drawn is True


# --------------------------------------------------------------------------
# DDR#988 - firebending X, and when X is read
# --------------------------------------------------------------------------


def test_firebending_parses_as_a_keyword_with_its_own_self_defined_x():
    """DDR#988's first obstacle, now cleared.

    Firebending Student's second line is "Firebending X, where X is this
    creature's power." (reminder text stripped). CR 702.189a: "Firebending is a
    triggered ability. 'Firebending N' means 'Whenever this creature attacks,
    add N {R}. ...'" - so the line is a keyword, and N here is written as an X
    the card defines in its own words.

    It used to land as a `StaticAbility`: the keyword-line parser comma-split
    it and the tail matched no keyword, and the trailing full stop disqualified
    the line anyway. `_parse_keyword_parameter` reads the whole
    `Keyword X, where X is ...` form instead, and keeps the parameter verbatim -
    **CR 608.2h** is why it is not resolved to a number here: "the answer is
    determined only once, when the effect is applied", which is as the
    firebending ability resolves, not as the card is read.
    """
    abilities = parse_abilities(card("Firebending Student"))
    keywords = [ability for ability in abilities if ability.kind is AbilityKind.KEYWORD]

    assert [keyword.canonical for keyword in keywords] == ["Prowess", "Firebending"]
    firebending = keywords[1]
    assert firebending.parameter == "X, where X is this creature's power"
    assert firebending.count is None, "CR 608.2h: the number is read on resolution"


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
