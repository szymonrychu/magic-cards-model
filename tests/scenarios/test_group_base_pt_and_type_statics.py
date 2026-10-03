"""Scenario: "`<creatures>` you control have base power and toughness N/N and
are `<creature type>`s in addition to their other [creature] types." - a
static group effect in two layers (`machines/layers._GROUP_BASE_PT_AND_TYPE_RE`).

March of the World Ooze is the reported card: "Creatures you control have
base power and toughness 6/6 and are Oozes in addition to their other types."
Graaz, Unstoppable Juggernaut is the second printing that proves the reader
is the template, not March's sentence: an "other" subject (Graaz itself is
excluded), an asymmetric 5/3, and "their other creature types". Both legal in
Modern and Pioneer (Scryfall legalities, 2026-10-03).

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 613.1d** - layer 4: type-changing effects.
- **CR 613.4b** - layer 7b: effects that set power and/or toughness, and
  effects that refer to *base* power and toughness.
- **CR 613.4c** - layer 7c: effects and counters that modify power and/or
  toughness, applied after 7b.
- **CR 613.7** / **613.7a** - within a sublayer, timestamp order; a static
  ability's effect has the timestamp of the object it is on.
- **CR 205.1b** - "in addition to its other types" keeps every prior type.
- **CR 611.3a** - a static ability's effect is not locked in.
- **CR 604.2** - a static ability's effect lasts as long as its permanent
  remains on the battlefield.
"""

from magic_cards_model.machines import Step
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _mine(scenario, name: str, username: str = "alice"):
    (state,) = [s for s in scenario.game.battlefield if s.name == name and s.controller == username]
    return state


def _chars(scenario, name: str, username: str = "alice"):
    return scenario.game.characteristics_of(_mine(scenario, name, username))


def _board(alice, *, hand=(), bob=("Llanowar Elves",)):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), hand=list(hand), library=["Forest"] * 6)
        .player("bob", battlefield=list(bob), library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_static_lines_are_handled() -> None:
    clauses = [c for c in classify_clauses(card("March of the World Ooze")) if c.text]
    assert {c.category for c in clauses} == {HANDLED}, clauses
    graaz = [
        c
        for c in classify_clauses(card("Graaz, Unstoppable Juggernaut"))
        if "base power and toughness" in c.text
    ]
    assert [c.category for c in graaz] == [HANDLED], graaz


# -- March of the World Ooze --------------------------------------------------


def test_a_creature_you_control_is_a_6_6_ooze_and_keeps_its_types() -> None:
    scenario = _board(["March of the World Ooze", "Grizzly Bears"])

    bears = _chars(scenario, "Grizzly Bears")

    assert (bears.power, bears.toughness) == (6, 6)
    assert "Ooze" in bears.subtypes
    assert "Bear" in bears.subtypes


def test_an_opponents_creature_is_unchanged() -> None:
    scenario = _board(["March of the World Ooze"])

    elves = _chars(scenario, "Llanowar Elves", "bob")

    assert (elves.power, elves.toughness) == (1, 1)
    assert "Ooze" not in elves.subtypes


def test_a_noncreature_permanent_is_not_an_ooze() -> None:
    scenario = _board(["March of the World Ooze", "Forest"])

    forest = _chars(scenario, "Forest")

    assert "Ooze" not in forest.subtypes
    assert forest.power is None
    assert "Ooze" not in _chars(scenario, "March of the World Ooze").subtypes


def test_a_creature_that_enters_later_is_affected() -> None:
    """CR 611.3a."""
    scenario = _board(["March of the World Ooze"], hand=["Grizzly Bears"])

    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")

    chars = scenario.game.characteristics_of(bears)
    assert (chars.power, chars.toughness) == (6, 6)
    assert "Ooze" in chars.subtypes


def test_a_plus_one_counter_applies_on_top_of_the_set_base() -> None:
    """CR 613.4b then 613.4c: the counter modifies the 6/6, it is not
    overwritten by it."""
    scenario = _board(["March of the World Ooze", "Grizzly Bears"])
    _mine(scenario, "Grizzly Bears").add_counters("+1/+1", 1)

    bears = _chars(scenario, "Grizzly Bears")

    assert (bears.power, bears.toughness) == (7, 7)


def test_a_pump_applies_on_top_of_the_set_base() -> None:
    """CR 613.4c: Giant Growth's +3/+3 lands after the 7b set, whatever the
    timestamps."""
    scenario = _board(["March of the World Ooze", "Grizzly Bears", "Forest"], hand=["Giant Growth"])
    bears = _mine(scenario, "Grizzly Bears")

    scenario.cast_and_resolve("Giant Growth", *scenario.untapped_sources("Forest"), targets=[bears])

    chars = scenario.game.characteristics_of(bears)
    assert (chars.power, chars.toughness) == (9, 9)


def test_an_anthem_and_a_counter_both_stack_on_the_set_base() -> None:
    scenario = _board(["March of the World Ooze", "Glorious Anthem", "Grizzly Bears"])
    _mine(scenario, "Grizzly Bears").add_counters("+1/+1", 2)

    bears = _chars(scenario, "Grizzly Bears")

    assert (bears.power, bears.toughness) == (9, 9)


def test_a_characteristic_defining_pt_is_overridden() -> None:
    """CR 613.4b applies after 7a: Tarmogoyf's own count is replaced."""
    scenario = _board(["March of the World Ooze", "Tarmogoyf"])

    goyf = _chars(scenario, "Tarmogoyf")

    assert (goyf.power, goyf.toughness) == (6, 6)
    assert "Lhurgoyf" in goyf.subtypes and "Ooze" in goyf.subtypes


def test_the_effect_ends_when_march_leaves_and_counters_stay() -> None:
    """CR 604.2."""
    scenario = _board(["March of the World Ooze", "Grizzly Bears"])
    _mine(scenario, "Grizzly Bears").add_counters("+1/+1", 1)
    scenario.game.put_into_graveyard(_mine(scenario, "March of the World Ooze"))

    bears = _chars(scenario, "Grizzly Bears")

    assert (bears.power, bears.toughness) == (3, 3)
    assert "Ooze" not in bears.subtypes


def test_the_elephant_from_its_own_trigger_is_a_6_6_ooze() -> None:
    """March's trigger and static together: the 3/3 Elephant token it makes is
    a creature you control, so it is 6/6 and an Ooze Elephant."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["March of the World Ooze"], library=["Plains"] * 3)
        .player("bob", battlefield=["Mountain"], hand=["Lightning Bolt"], library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Lightning Bolt", username="bob", auto=True, targets=["alice"])
    scenario.pass_until_resolved()

    elephant = _chars(scenario, "Elephant Token")
    assert (elephant.power, elephant.toughness) == (6, 6)
    assert {"Elephant", "Ooze"} <= set(elephant.subtypes)


# -- Graaz, Unstoppable Juggernaut: "other", 5/3, "creature types" -----------


def test_graaz_makes_other_creatures_5_3_juggernauts_but_not_itself() -> None:
    scenario = _board(["Graaz, Unstoppable Juggernaut", "Grizzly Bears"])

    bears = _chars(scenario, "Grizzly Bears")
    graaz = _chars(scenario, "Graaz, Unstoppable Juggernaut")

    assert (bears.power, bears.toughness) == (5, 3)
    assert {"Bear", "Juggernaut"} <= set(bears.subtypes)
    assert (graaz.power, graaz.toughness) == (7, 5)


def test_graaz_does_not_reach_an_opponents_creature() -> None:
    scenario = _board(["Graaz, Unstoppable Juggernaut"])

    elves = _chars(scenario, "Llanowar Elves", "bob")

    assert (elves.power, elves.toughness) == (1, 1)
    assert "Juggernaut" not in elves.subtypes


def test_two_base_sets_apply_in_timestamp_order() -> None:
    """CR 613.7: within 7b, the later timestamp wins. March entered first and
    Graaz later, so Grizzly Bears is 5/3; Graaz itself is not "other" to its
    own line, so only March's 6/6 reaches it."""
    scenario = _board(
        ["March of the World Ooze", "Grizzly Bears"], hand=["Graaz, Unstoppable Juggernaut"]
    )
    scenario.put_onto_battlefield("Graaz, Unstoppable Juggernaut", "alice")

    bears = _chars(scenario, "Grizzly Bears")
    graaz = _chars(scenario, "Graaz, Unstoppable Juggernaut")

    assert (bears.power, bears.toughness) == (5, 3)
    assert {"Ooze", "Juggernaut", "Bear"} <= set(bears.subtypes)
    assert (graaz.power, graaz.toughness) == (6, 6)
