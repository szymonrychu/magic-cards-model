"""Scenario: a mass pump followed by a condition-gated rider (EC7 remainder).

Break of Day (fateful hour), Heroic Charge (kicker), Kytheon's Tactics (spell
mastery), Unbreakable Formation (addendum), Zealous Display ("if it's not your
turn, untap those creatures"), Golden Demise (city's blessing, "instead only
creatures your opponents control") and Guul Draz Overseer ("if that land is a
Swamp, ... instead", an event anaphor). Every gate is run both true and false.

Rules: CR 608.2c (later text modifies earlier text), CR 614.1a ("instead"),
CR 611.2c (the group is fixed when the effect begins), CR 702.131 (ascend),
CR 702.33d (kicker), CR 107.4/CR 305 (land types), CR 701.26 (untap).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from tests.scenarios.harness import Scenario


def computed(scenario: Scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def has(scenario: Scenario, creature, keyword: str) -> bool:
    return has_keyword(creature, keyword, scenario.game)


def cast_in_main(scenario: Scenario, name: str, *lands: str, kicker: int = 0):
    casting = scenario.cast(name, "alice")
    if kicker:
        casting.pay_kicker(kicker)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*lands))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()


# -- Break of Day: fateful hour ------------------------------------------------


def break_of_day(life: int):
    scenario = (
        Scenario()
        .player("alice", hand=["Break of Day"], battlefield=["Grizzly Bears", "Plains", "Plains"])
        .player("bob")
        .build()
    )
    scenario.player("alice").life = life
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    cast_in_main(scenario, "Break of Day", "Plains", "Plains")
    return scenario, bears


def test_break_of_day_gives_indestructible_at_five_or_less_life():
    scenario, bears = break_of_day(5)
    assert computed(scenario).of(bears).power_toughness == (3, 3)
    assert has(scenario, bears, "indestructible")


def test_break_of_day_gives_no_indestructible_above_five_life():
    scenario, bears = break_of_day(6)
    assert computed(scenario).of(bears).power_toughness == (3, 3)
    assert not has(scenario, bears, "indestructible")


# -- Heroic Charge: kicker -----------------------------------------------------


def heroic_charge(kicker: int):
    lands = ["Plains"] * 4 + ["Mountain"] * 2
    scenario = (
        Scenario()
        .player("alice", hand=["Heroic Charge"], battlefield=["Grizzly Bears", *lands])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    paid = ["Plains"] * 4 + ["Mountain"] * 2 if kicker else ["Plains"] * 4
    cast_in_main(scenario, "Heroic Charge", *paid, kicker=kicker)
    return scenario, bears


def test_heroic_charge_kicked_also_gains_trample():
    scenario, bears = heroic_charge(1)
    assert computed(scenario).of(bears).power_toughness == (4, 3)
    assert has(scenario, bears, "trample")


def test_heroic_charge_unkicked_only_pumps():
    scenario, bears = heroic_charge(0)
    assert computed(scenario).of(bears).power_toughness == (4, 3)
    assert not has(scenario, bears, "trample")


# -- Kytheon's Tactics: spell mastery -----------------------------------------


def kytheons_tactics(graveyard: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kytheon's Tactics"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Plains"],
            graveyard=graveyard,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    cast_in_main(scenario, "Kytheon's Tactics", "Plains", "Plains", "Plains")
    return scenario, bears


def test_kytheons_tactics_with_spell_mastery_gains_vigilance():
    scenario, bears = kytheons_tactics(["Shock", "Opt"])
    assert computed(scenario).of(bears).power_toughness == (4, 3)
    assert has(scenario, bears, "vigilance")


def test_kytheons_tactics_without_spell_mastery_only_pumps():
    scenario, bears = kytheons_tactics(["Shock", "Grizzly Bears"])
    assert computed(scenario).of(bears).power_toughness == (4, 3)
    assert not has(scenario, bears, "vigilance")


# -- Unbreakable Formation: addendum ------------------------------------------


def unbreakable_formation(step: Step):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Unbreakable Formation"],
            battlefield=["Grizzly Bears", "Serra Angel", "Plains", "Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if step is not Step.PRECOMBAT_MAIN:
        scenario.start_at(step)
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    cast_in_main(scenario, "Unbreakable Formation", "Plains", "Plains", "Plains")
    return scenario, bears, angel


def test_unbreakable_formation_cast_in_main_phase_adds_counters_and_vigilance():
    scenario, bears, angel = unbreakable_formation(Step.PRECOMBAT_MAIN)
    assert has(scenario, bears, "indestructible")
    assert bears.counter_count("+1/+1") == 1
    assert angel.counter_count("+1/+1") == 1
    assert has(scenario, bears, "vigilance")
    assert computed(scenario).of(bears).power_toughness == (3, 3)


def test_unbreakable_formation_cast_outside_main_phase_only_grants_indestructible():
    scenario, bears, angel = unbreakable_formation(Step.BEGINNING_OF_COMBAT)
    assert has(scenario, bears, "indestructible")
    assert has(scenario, angel, "indestructible")
    assert bears.counter_count("+1/+1") == 0
    assert not has(scenario, bears, "vigilance")


# -- Zealous Display: "if it's not your turn, untap those creatures" ------------


def zealous_display(caster: str):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Zealous Display"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Plains"],
        )
        .player(
            "bob",
            hand=["Zealous Display"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.creature("Grizzly Bears", caster)
    mine.tap()
    if caster == "bob":
        scenario.pass_priority("alice")
    casting = scenario.cast("Zealous Display", caster)
    payment = casting.begin_paying()
    scenario.pay_with(
        payment, *scenario.untapped_sources("Plains", "Plains", "Plains", username=caster)
    )
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    return scenario, mine


def test_zealous_display_on_the_opponents_turn_untaps_the_creatures():
    scenario, bears = zealous_display("bob")
    assert computed(scenario).of(bears).power_toughness == (4, 2)
    assert not bears.tapped


def test_zealous_display_on_your_own_turn_leaves_them_tapped():
    scenario, bears = zealous_display("alice")
    assert computed(scenario).of(bears).power_toughness == (4, 2)
    assert bears.tapped


# -- Golden Demise: city's blessing, "instead only creatures your opponents control" --


def golden_demise(permanents: int):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Golden Demise"],
            battlefield=["Serra Angel", "Swamp", "Swamp", "Swamp"] + ["Forest"] * (permanents - 4),
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.creature("Serra Angel", "alice")
    theirs = scenario.creature("Serra Angel", "bob")
    cast_in_main(scenario, "Golden Demise", "Swamp", "Swamp", "Swamp")
    return scenario, mine, theirs


def test_golden_demise_without_the_blessing_shrinks_every_creature():
    scenario, mine, theirs = golden_demise(4)
    assert not scenario.player("alice").has_citys_blessing
    assert computed(scenario).of(mine).power_toughness == (2, 2)
    assert computed(scenario).of(theirs).power_toughness == (2, 2)


def test_golden_demise_with_the_blessing_shrinks_only_opponents_creatures():
    scenario, mine, theirs = golden_demise(10)
    assert scenario.player("alice").has_citys_blessing
    assert computed(scenario).of(mine).power_toughness == (4, 4)
    assert computed(scenario).of(theirs).power_toughness == (2, 2)


# -- Guul Draz Overseer: landfall, "if that land is a Swamp ... instead" --------


def guul_draz(land: str):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[land],
            battlefield=["Guul Draz Overseer", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    overseer = scenario.creature("Guul Draz Overseer", "alice")
    scenario.play_land(land)
    scenario.resolve_top()
    return scenario, bears, overseer


def test_guul_draz_overseer_swamp_gives_plus_two_instead():
    scenario, bears, overseer = guul_draz("Swamp")
    assert computed(scenario).of(bears).power_toughness == (4, 2)
    assert computed(scenario).of(overseer).power_toughness == (3, 4), "other creatures only"


def test_guul_draz_overseer_other_land_gives_plus_one():
    scenario, bears, overseer = guul_draz("Forest")
    assert computed(scenario).of(bears).power_toughness == (3, 2)
    assert computed(scenario).of(overseer).power_toughness == (3, 4)
