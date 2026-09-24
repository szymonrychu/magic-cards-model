"""Attack and beginning-of-combat triggers whose size or condition is read off
the source itself (CR 603.2, CR 603.4, CR 608.2h), and a one-shot evasion
grant (CR 611.2).

- "Whenever Whiplash attacks, if he's equipped, each opponent loses X life
  and you gain X life, where X is the number of Equipment attached to him."
  (Whiplash, Vengeful Engineer) - CR 603.4's intervening if on the source's
  own equipped status (CR 301.5a), and a count of the Equipment attached to
  it. Avacynian Missionaries' "At the beginning of your end step, if this
  creature is equipped, transform it." is the second printing of the
  condition; Shagrat, Loot Bearer's "... amass Orcs X, where X is the number
  of Equipment attached to Shagrat" of the count.
- "Whenever Captain America attacks, each other Hero you control gets +X/+X
  until end of turn, where X is Captain America's toughness." (Captain
  America, Wings of Freedom); Wild Beastmaster's "each other creature you
  control gets +X/+X until end of turn, where X is this creature's power." is
  the second printing.
- "At the beginning of combat on your turn, another target creature you
  control gets +X/+0 until end of turn, where X is War Machine's power." (War
  Machine, Legacy of Iron); Brambleguard Captain's "target creature you
  control ... where X is this creature's power" and Armored Armadillo's "{3}
  {W}: This creature gets +X/+0 until end of turn, where X is its toughness."
  are the second printings.
- "Whenever Viv Vision attacks, draw a card if her power is 4 or greater."
  (Viv Vision, Teen Synthezoid); Tribute to the World Tree's "draw a card if
  its power is 3 or greater. Otherwise, put two +1/+1 counters on it." is the
  second printing.
- "Target creature gains vigilance until end of turn and can't be blocked
  this turn. Draw a card." (Pym Particles); Break Through the Line's "{R}:
  Target creature with power 2 or less gains haste until end of turn and
  can't be blocked this turn." is the second printing.
- Iron Man, Master of Machines' "Whenever Iron Man attacks, if an artifact
  entered the battlefield under your control this turn, draw a card." and
  Avengers Assemble!'s end-step draw, proven as they already read.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import evasion_restriction_refusal, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _pt(scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


def _to_attackers(scenario):
    scenario.advance()  # beginning of combat
    if scenario.stack_names():
        scenario.pass_until_resolved()
    if scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    assert scenario.step is Step.DECLARE_ATTACKERS


# -- Whiplash --------------------------------------------------------------------


def test_whiplash_drains_for_each_equipment_attached_to_him():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Whiplash, Vengeful Engineer", "Quick-Draw Dagger", "Stolen Stark Tech"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    whiplash = scenario.creature("Whiplash, Vengeful Engineer", "alice")
    for name in ("Quick-Draw Dagger", "Stolen Stark Tech"):
        scenario.find(name, Zone.BATTLEFIELD, "alice").attach_to(whiplash)
    _to_attackers(scenario)
    scenario.attack_with(whiplash)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22


def test_unequipped_whiplash_does_not_trigger():
    """CR 603.4: the intervening if is false when he attacks, so the ability
    never triggers at all."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Whiplash, Vengeful Engineer", "Quick-Draw Dagger"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    whiplash = scenario.creature("Whiplash, Vengeful Engineer", "alice")
    _to_attackers(scenario)
    scenario.attack_with(whiplash)

    assert scenario.stack_names() == []
    assert scenario.player("bob").life == 20
    assert scenario.game.intervening_if_notices == []


def test_whiplash_rechecks_being_equipped_on_resolution():
    """CR 608.2a: the Equipment leaving before the trigger resolves turns
    the intervening if false again, and the ability does nothing."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Whiplash, Vengeful Engineer", "Quick-Draw Dagger"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    whiplash = scenario.creature("Whiplash, Vengeful Engineer", "alice")
    dagger = scenario.find("Quick-Draw Dagger", Zone.BATTLEFIELD, "alice")
    dagger.attach_to(whiplash)
    _to_attackers(scenario)
    scenario.attack_with(whiplash)
    assert len(scenario.stack_names()) == 1

    scenario.game.destroy(dagger)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20


def test_avacynian_missionaries_transform_only_while_equipped():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Avacynian Missionaries // Lunarch Inquisitors", "Quick-Draw Dagger"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    missionaries = scenario.creature("Avacynian Missionaries", "alice")
    scenario.find("Quick-Draw Dagger", Zone.BATTLEFIELD, "alice").attach_to(missionaries)
    scenario.advance()
    assert scenario.step is Step.END_STEP
    scenario.pass_until_resolved()

    assert missionaries.name == "Lunarch Inquisitors"


def test_unequipped_avacynian_missionaries_stay_as_they_are():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Avacynian Missionaries // Lunarch Inquisitors"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    missionaries = scenario.creature("Avacynian Missionaries", "alice")
    scenario.advance()
    scenario.pass_until_resolved()
    assert missionaries.name == "Avacynian Missionaries"


def test_shagrat_amasses_for_each_equipment_attached_to_him():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Shagrat, Loot Bearer", "Quick-Draw Dagger", "Raven Wings"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shagrat = scenario.creature("Shagrat, Loot Bearer", "alice")
    scenario.find("Raven Wings", Zone.BATTLEFIELD, "alice").attach_to(shagrat)
    dagger = scenario.find("Quick-Draw Dagger", Zone.BATTLEFIELD, "alice")
    scenario.choose_trigger_targets("Shagrat, Loot Bearer", [dagger])
    _to_attackers(scenario)
    scenario.attack_with(shagrat)
    scenario.pass_until_resolved()

    assert dagger.attached_to == shagrat.id
    (army,) = [s for s in scenario.game.battlefield if "Army" in s.subtypes]
    assert army.counter_count("+1/+1") == 2


# -- Captain America ---------------------------------------------------------------


def test_captain_america_pumps_each_other_hero_by_his_toughness():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Captain America, Wings of Freedom",
                "Okoye, Dora Milaje Leader",
                "Grizzly Bears",
            ],
        )
        .player("bob", battlefield=["Stature, Size Shifter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    captain = scenario.creature("Captain America, Wings of Freedom", "alice")
    okoye = scenario.creature("Okoye, Dora Milaje Leader", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    stature = scenario.creature("Stature, Size Shifter", "bob")
    captain.add_counters("+1/+1", 2)  # toughness 3
    _to_attackers(scenario)
    scenario.attack_with(captain)
    scenario.pass_until_resolved()

    assert _pt(scenario, okoye) == (6, 5), "Okoye 3/2 + 3/+3"
    assert _pt(scenario, captain) == (5, 3), "each *other* Hero"
    assert _pt(scenario, bears) == (2, 2), "not a Hero"
    assert _pt(scenario, stature) == (1, 1), "not one alice controls"


def test_captain_americas_pump_is_locked_in_on_resolution():
    """CR 608.2h: X is his toughness as the ability resolves; a later change
    to it does not resize the pump."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Captain America, Wings of Freedom", "Okoye, Dora Milaje Leader"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    captain = scenario.creature("Captain America, Wings of Freedom", "alice")
    okoye = scenario.creature("Okoye, Dora Milaje Leader", "alice")
    _to_attackers(scenario)
    scenario.attack_with(captain)
    scenario.pass_until_resolved()
    assert _pt(scenario, okoye) == (4, 3)

    captain.add_counters("+1/+1", 3)
    assert _pt(scenario, okoye) == (4, 3)


def test_the_pump_ends_at_end_of_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Captain America, Wings of Freedom", "Okoye, Dora Milaje Leader"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    captain = scenario.creature("Captain America, Wings of Freedom", "alice")
    okoye = scenario.creature("Okoye, Dora Milaje Leader", "alice")
    _to_attackers(scenario)
    scenario.attack_with(captain)
    scenario.pass_until_resolved()
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.turn_based_actions()
    assert _pt(scenario, okoye) == (3, 2)


def test_wild_beastmaster_pumps_each_other_creature_by_its_power():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Wild Beastmaster", "Grizzly Bears", "Hill Giant"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beastmaster = scenario.creature("Wild Beastmaster", "alice")
    beastmaster.add_counters("+1/+1", 2)  # power 3
    _to_attackers(scenario)
    scenario.attack_with(beastmaster)
    scenario.pass_until_resolved()

    assert _pt(scenario, scenario.creature("Grizzly Bears", "alice")) == (5, 5)
    assert _pt(scenario, scenario.creature("Hill Giant", "alice")) == (6, 6)
    assert _pt(scenario, beastmaster) == (3, 3)


# -- War Machine ----------------------------------------------------------------


def test_war_machine_gives_another_target_creature_his_power():
    scenario = (
        Scenario()
        .player("alice", battlefield=["War Machine, Legacy of Iron", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    war_machine = scenario.creature("War Machine, Legacy of Iron", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    war_machine.add_counters("+1/+1", 2)  # power 3
    scenario.choose_trigger_targets("War Machine, Legacy of Iron", [bears])
    scenario.advance()
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    scenario.pass_until_resolved()

    assert _pt(scenario, bears) == (5, 2)
    assert _pt(scenario, war_machine) == (3, 5)


def test_war_machine_alone_has_no_other_creature_to_target():
    """ "another target creature": the source is no legal target for itself,
    so with no other creature the trigger is removed as it would be put on
    the stack (CR 603.3d) and War Machine stays a 1/3."""
    scenario = Scenario().player("alice", battlefield=["War Machine, Legacy of Iron"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    war_machine = scenario.creature("War Machine, Legacy of Iron", "alice")
    scenario.advance()
    assert scenario.stack_names() == []
    scenario.pass_until_resolved()
    assert _pt(scenario, war_machine) == (1, 3)


def test_brambleguard_captain_gives_its_power_to_its_target():
    scenario = (
        Scenario().player("alice", battlefield=["Brambleguard Captain", "Grizzly Bears"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Brambleguard Captain", [bears])
    scenario.advance()
    scenario.pass_until_resolved()
    assert _pt(scenario, bears) == (4, 2)


def test_armored_armadillo_gets_its_toughness_as_power():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Armored Armadillo", "Plains", "Plains", "Plains", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    armadillo = scenario.creature("Armored Armadillo", "alice")
    before = _pt(scenario, armadillo)
    scenario.activate(armadillo, *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains"))
    scenario.pass_until_resolved()
    assert _pt(scenario, armadillo) == (before[0] + before[1], before[1])


# -- Viv Vision -------------------------------------------------------------------


def test_viv_vision_draws_when_her_power_is_four_or_greater():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Plains", "Plains"], battlefield=["Viv Vision, Teen Synthezoid"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    viv = scenario.creature("Viv Vision, Teen Synthezoid", "alice")
    viv.add_counters("+1/+1", 2)
    _to_attackers(scenario)
    scenario.attack_with(viv)
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 1


def test_viv_vision_below_four_power_draws_nothing():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Plains", "Plains"], battlefield=["Viv Vision, Teen Synthezoid"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    viv = scenario.creature("Viv Vision, Teen Synthezoid", "alice")
    viv.add_counters("+1/+1", 1)  # 3/3
    _to_attackers(scenario)
    scenario.attack_with(viv)
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 0


def test_tribute_to_the_world_tree_draws_for_a_big_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Plains"],
            hand=["Hill Giant"],
            battlefield=["Tribute to the World Tree"] + ["Mountain"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.cast_and_resolve("Hill Giant", *scenario.untapped_sources(*["Mountain"] * 4))
    scenario.pass_until_resolved()
    assert [state.name for state in scenario.player("alice").hand] == ["Plains"]
    assert giant.counter_count("+1/+1") == 0


def test_tribute_to_the_world_tree_otherwise_grows_a_small_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Plains"],
            hand=["Grizzly Bears"],
            battlefield=["Tribute to the World Tree", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.cast_and_resolve(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    scenario.pass_until_resolved()
    assert scenario.player("alice").hand == []
    assert bears.counter_count("+1/+1") == 2


# -- Pym Particles ----------------------------------------------------------------


def test_pym_particles_grants_vigilance_and_unblockability_then_draws():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Plains"],
            hand=["Pym Particles"],
            battlefield=["Grizzly Bears", "Island"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve(
        "Pym Particles", *scenario.untapped_sources("Island"), targets=[bears]
    )

    assert has_keyword(bears, "vigilance", scenario.game)
    assert evasion_restriction_refusal(scenario.game, bears, giant) is not None
    assert [state.name for state in scenario.player("alice").hand] == ["Plains"]


def test_pym_particles_wears_off_at_end_of_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Plains"],
            hand=["Pym Particles"],
            battlefield=["Grizzly Bears", "Island"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve(
        "Pym Particles", *scenario.untapped_sources("Island"), targets=[bears]
    )
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.turn_based_actions()

    assert not has_keyword(bears, "vigilance", scenario.game)
    assert evasion_restriction_refusal(scenario.game, bears, giant) is None


def test_break_through_the_line_makes_a_small_creature_hasty_and_unblockable():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Break Through the Line", "Grizzly Bears", "Mountain"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    line = scenario.find("Break Through the Line", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.activate(line, *scenario.untapped_sources("Mountain"), targets=[bears])
    scenario.pass_until_resolved()

    assert has_keyword(bears, "haste", scenario.game)
    assert evasion_restriction_refusal(scenario.game, bears, giant) is not None


# -- already-read triggers, proven -------------------------------------------------


def test_iron_man_draws_when_an_artifact_entered_this_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Plains"],
            hand=["Quick-Draw Dagger"],
            battlefield=["Iron Man, Master of Machines", "Plains", "Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    iron_man = scenario.creature("Iron Man, Master of Machines", "alice")
    scenario.choose_trigger_targets("Quick-Draw Dagger", [iron_man])
    scenario.cast_and_resolve(
        "Quick-Draw Dagger", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    scenario.pass_until_resolved()
    _to_attackers(scenario)
    scenario.attack_with(iron_man)
    scenario.pass_until_resolved()
    assert [state.name for state in scenario.player("alice").hand] == ["Plains"]


def test_iron_man_draws_nothing_without_a_new_artifact():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Plains"], battlefield=["Iron Man, Master of Machines"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    iron_man = scenario.creature("Iron Man, Master of Machines", "alice")
    _to_attackers(scenario)
    scenario.attack_with(iron_man)
    scenario.pass_until_resolved()
    assert scenario.player("alice").hand == []


def test_avengers_assemble_draws_at_end_step_after_a_hero_attacked():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Plains"],
            battlefield=["Avengers Assemble!", "Okoye, Dora Milaje Leader"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    okoye = scenario.creature("Okoye, Dora Milaje Leader", "alice")
    _to_attackers(scenario)
    scenario.attack_with(okoye)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
        scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert [state.name for state in scenario.player("alice").hand] == ["Plains"]


@pytest.mark.parametrize(
    "name",
    [
        "Whiplash, Vengeful Engineer",
        "Captain America, Wings of Freedom",
        "War Machine, Legacy of Iron",
        "Viv Vision, Teen Synthezoid",
        "Pym Particles",
        "Iron Man, Master of Machines",
        "Avengers Assemble!",
        "Avacynian Missionaries // Lunarch Inquisitors",
        "Shagrat, Loot Bearer",
        "Wild Beastmaster",
        "Brambleguard Captain",
        "Armored Armadillo",
        "Tribute to the World Tree",
        "Break Through the Line",
    ],
)
def test_every_clause_is_handled(name):
    for clause in card_support(card(name)).clauses:
        assert clause.outcome == "handled", (name, clause.text, clause.outcome)
