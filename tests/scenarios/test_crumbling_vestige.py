"""Crumbling Vestige: "This land enters tapped. When this land enters, add
one mana of any color. {T}: Add {C}."

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 605.1b** - "A triggered ability is a mana ability if it meets all of
  the following criteria: it doesn't require a target ... it triggers from
  the activation or resolution of an activated mana ability ..." Crumbling
  Vestige's ETB trigger fires from a permanent entering the battlefield, not
  from another mana ability's activation or resolution, so it fails this
  criterion.
- **CR 605.5** - "Abilities that don't meet the criteria specified in rules
  605.1a-b ... aren't mana abilities." The ETB trigger is therefore an
  ordinary triggered ability: it uses the stack (CR 113.4) and can be
  responded to, unlike the land's own separate `{T}: Add {C}.` (CR 605.1a).
- **CR 105.1/105.4** - "any color" is one of the five colors, chosen by the
  ability's controller (CR 608.2d) as it resolves.
- **CR 117.1d/605.3b** - contrasted here only to show the *other* ability
  really does skip the stack: a mana ability "doesn't use the stack" and
  "can't be targeted, countered, or otherwise responded to" (CR 605.3b).

The same shape generalised: `_ADD_ONE_MANA_OF_ANY_COLOR_TRIGGER_RE` reads
"add `<count>` mana of any (one )?color[, where X is ...]" - a printed count
(Boommobile's "four"), or CR 107.3's X (Sanctum of Fruitful Harvest's "the
number of Shrines you control", CR 608.2h: read the instant the ability
resolves) - not only Crumbling Vestige's literal "one". Every card here is an
ordinary triggered ability by the same CR 605.1b/605.5 reasoning above; none
of them triggers from a mana ability's own activation or resolution.

- **CR 505.1** - "the first main phase (also known as the precombat main
  phase)" - Sanctum of Fruitful Harvest's own trigger condition.
- **CR 107.1b** - a result below zero is zero instead; not reachable by any
  card here (a Shrine count and a printed count are never negative), but the
  same floor `resolve_mana_count_expression`'s callers all share.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_mana_abilities
from magic_cards_model.models import Color
from tests.scenarios.harness import Scenario


def _walk_to(scenario, step: Step) -> None:
    """Advance turn-by-turn - never jump - until `step`, resolving anything
    that fires along the way. CR 500.6's "a step began" event is emitted by
    `Game.advance`, not by `start_at`, which moves the turn machine directly
    and fires nothing - so a "beginning of your first main phase" trigger can
    only be proven by walking there. Copied from `test_energy_payment.py`'s
    identical helper rather than imported, so this file about one mechanic
    does not reach into another's test module for its plumbing."""
    while scenario.step is not step:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def test_the_etb_trigger_adds_one_mana_of_the_chosen_color():
    scenario = Scenario().player("alice", hand=["Crumbling Vestige"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vestige = scenario.play_land("Crumbling Vestige")
    assert vestige.tapped

    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 1
    scenario.will_choose(Color.GREEN.value, source="Crumbling Vestige")
    scenario.resolve_top()

    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1}


def test_the_etb_trigger_goes_on_the_stack_and_can_be_responded_to():
    """CR 605.5's own consequence: unlike a real mana ability (CR 605.3b:
    "doesn't use the stack ... can't be ... responded to"), this trigger is
    an ordinary object on the stack the moment the land enters, before
    anyone has had a chance to add the mana at all."""
    scenario = Scenario().player("alice", hand=["Crumbling Vestige"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Crumbling Vestige")

    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 1
    assert scenario.player("alice").mana_pool.is_empty, "the mana is not added until it resolves"


def test_the_tap_ability_is_a_separate_fixed_colorless_source():
    """The land's other line, `{T}: Add {C}.`, is read by `machines/
    abilities.py`'s ordinary mana-ability parser (CR 605.1a) as a plain
    colorless source, unaffected by the ETB trigger's own "any color" - the
    land stays tapped from its own CR 614.1c `ENTERS_TAPPED` replacement,
    since nothing here untaps it (that is Amulet of Vigor's own trigger, in
    `test_amulet_of_vigor.py`, not this file's mechanic)."""
    scenario = Scenario().player("alice", hand=["Crumbling Vestige"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vestige = scenario.play_land("Crumbling Vestige")
    scenario.game.put_triggers_on_stack()
    scenario.will_choose(Color.BLUE.value, source="Crumbling Vestige")
    scenario.resolve_top()

    assert vestige.tapped, "nothing in this file's own mechanic untaps it"
    (ability,) = parse_mana_abilities(vestige.card, vestige.up_face_name)
    assert ability.produces() == [Color.COLORLESS]


def test_each_of_the_five_colors_is_a_legal_answer():
    """CR 105.1: "any color" spans white, blue, black, red, and green - not
    just green, which the other tests in this file happen to pick."""
    for color in (Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN):
        scenario = Scenario().player("alice", hand=["Crumbling Vestige"]).build()
        scenario.start_at(Step.PRECOMBAT_MAIN)
        scenario.play_land("Crumbling Vestige")
        scenario.game.put_triggers_on_stack()
        scenario.will_choose(color.value, source="Crumbling Vestige")
        scenario.resolve_top()
        assert scenario.player("alice").mana_pool.floating == {color: 1}


def test_colorless_is_never_offered_as_an_answer():
    """CR 105.4: "if a player is asked to choose a color, they must choose
    one of the five colors ... [n]either is 'colorless'." The decision's own
    `options` should never include it."""
    scenario = Scenario().player("alice", hand=["Crumbling Vestige"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Crumbling Vestige")
    scenario.game.put_triggers_on_stack()
    scenario.will_choose(Color.WHITE.value, source="Crumbling Vestige")
    scenario.resolve_top()

    (question,) = [q for q in scenario.questions_asked() if q.source == "Crumbling Vestige"]
    assert "C" not in question.options
    assert set(question.options) == {"W", "U", "B", "R", "G"}


# --------------------------------------------------------------------------
# The same trigger shape with a count above "one" (G7-3): before this fix
# `_ADD_ONE_MANA_OF_ANY_COLOR_TRIGGER_RE` matched only the literal text "add
# one mana of any color", so Boommobile's "four" and Sanctum of Fruitful
# Harvest's X both fell straight through `trigger_effect_for`'s dispatch
# unread - the trigger reached the stack and resolved doing nothing.
# --------------------------------------------------------------------------


def test_boommobiles_etb_adds_four_mana_of_one_color():
    """Boommobile: "When this Vehicle enters, add four mana of any one
    color." A printed count above Crumbling Vestige's "one", read by the
    same generalised regex and resolved as one colour choice multiplied out
    ("any **one** color", not four independent choices)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Boommobile"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Boommobile", auto=True)
    assert scenario.player("alice").mana_pool.is_empty, "the four Mountains paid the {2}{R}{R} cost"

    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 1
    scenario.will_choose(Color.RED.value, source="Boommobile")
    scenario.resolve_top()

    assert scenario.player("alice").mana_pool.floating == {Color.RED: 4}


def test_sanctum_of_fruitful_harvests_first_main_phase_trigger_reads_shrines_live():
    """Sanctum of Fruitful Harvest (off-pool): "At the beginning of your
    first main phase, add X mana of any one color, where X is the number of
    Shrines you control." CR 505.1's precombat main phase, CR 608.2h: X is
    read as the trigger resolves against the *live* board - Sanctum itself
    (a `Type.ENCHANTMENT` with the Shrine subtype) is the only Shrine here,
    so X = 1, not a fixed number baked into the ability at parse time.

    A second real Shrine would prove a count above one, but every other
    printed Shrine (`Honden of Infinite Rage`, `Crescent Island Temple`,
    `Go-Shintai of Life's Origin`) carries its own unrelated "for each"/mass
    clause this wave does not fix - adding one as a fixture would grow the
    pool sweep's `--effects` silent count, which is not this wave's to grow.
    `count_expression`'s own reading above one is already proven on a
    different subject in `test_count_expression_life_loss.py` (Grist's
    graveyard count, 20 life to 18); this test's own job is only to prove
    *this trigger* reads `count_expression`'s answer live rather than a
    number fixed at parse time, which a lone Shrine already shows."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sanctum of Fruitful Harvest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    scenario.will_choose(Color.WHITE.value, source="Sanctum of Fruitful Harvest")

    _walk_to(scenario, Step.PRECOMBAT_MAIN)

    assert scenario.player("alice").mana_pool.floating == {Color.WHITE: 1}
