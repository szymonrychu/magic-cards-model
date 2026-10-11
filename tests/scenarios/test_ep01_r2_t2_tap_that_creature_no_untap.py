"""A damage trigger that taps the creature it hurt and keeps it tapped
(EP-01 R2, T2 residual clauses): "Whenever this creature deals [combat] damage
to a creature, tap that creature and it doesn't untap during its controller's
next untap step."

CR numbers verified with `mise run rules:find`:

- CR 502.3: the untap step untaps all of a player's permanents, but "effects
  can keep one or more of a player's permanents from untapping" - the
  creature stays tapped through that controller's next untap step only.
- CR 701.26a: only untapped permanents can be tapped.
- CR 510.2: combat damage is dealt simultaneously; the trigger is put on the
  stack afterwards, so "that creature" is the one that was dealt damage.

Printings: Kashi-Tribe Elite (combat damage), Kashi-Tribe Warriors (the same
trigger without the legend line), Matsu-Tribe Sniper ("deals damage", an
activated ping, so any damage rather than combat damage).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _combat(attacker_name: str, blocker_name: str):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[attacker_name])
        .player("bob", battlefield=[blocker_name])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attacker = scenario.find(attacker_name, Zone.BATTLEFIELD, "alice")
    attacker.summoning_sick = False
    blocker = scenario.find(blocker_name, Zone.BATTLEFIELD, "bob")
    scenario.attack_with(attacker)
    scenario.advance()
    scenario.block(attacker, blocker)
    return scenario, attacker, blocker


def _finish_combat(scenario) -> None:
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def _bobs_next_untap(scenario) -> None:
    scenario.game.player("bob").untap_all(scenario.game.permanents_controlled_by("bob"))


def test_kashi_tribe_elite_taps_the_creature_it_damaged_and_keeps_it_tapped():
    scenario, _elite, wall = _combat("Kashi-Tribe Elite", "Wall of Omens")
    wall.untap()
    assert wall.untapped

    _finish_combat(scenario)

    assert wall.zone is Zone.BATTLEFIELD
    assert wall.tapped
    _bobs_next_untap(scenario)
    assert wall.tapped, "CR 502.3: it doesn't untap during its controller's next untap step"
    _bobs_next_untap(scenario)
    assert wall.untapped, "only the one untap step is skipped"


def test_kashi_tribe_warriors_is_the_same_trigger_on_a_different_printing():
    scenario, _warriors, wall = _combat("Kashi-Tribe Warriors", "Wall of Omens")

    _finish_combat(scenario)

    assert wall.tapped
    _bobs_next_untap(scenario)
    assert wall.tapped


def test_no_trigger_when_the_attacker_is_blocked_by_nothing_and_hits_the_player():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Kashi-Tribe Elite"])
        .player("bob", battlefield=["Wall of Omens"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    elite = scenario.find("Kashi-Tribe Elite", Zone.BATTLEFIELD, "alice")
    elite.summoning_sick = False
    wall = scenario.find("Wall of Omens", Zone.BATTLEFIELD, "bob")
    scenario.attack_with(elite)
    scenario.advance()
    scenario.no_blocks()
    _finish_combat(scenario)

    assert wall.untapped
    assert scenario.player("bob").life == 18


def test_matsu_tribe_sniper_reads_any_damage_not_only_combat_damage():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Matsu-Tribe Sniper"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sniper = scenario.find("Matsu-Tribe Sniper", Zone.BATTLEFIELD, "alice")
    sniper.summoning_sick = False
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")

    scenario.activate(sniper, tapping_for_cost=[sniper], targets=[angel])
    scenario.pass_until_resolved()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert angel.damage == 1
    assert angel.tapped
    _bobs_next_untap(scenario)
    assert angel.tapped
