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
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_mana_abilities
from magic_cards_model.models import Color
from tests.scenarios.harness import Scenario


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
