"""EP-01 round 2, task T7: static replacement and combat-damage statics left
over from round 1 (CR 510.1a, 614.1, 614.12).

"Each creature [you control] assigns combat damage equal to its toughness
rather than its power." - the unconditional twin of Ghalta's gated grant,
proven on a "you control" printing (Belligerent Brontodon, Assault Formation)
and on the all-creatures wording (Doran, the Siege Tower).
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _attack_unblocked(battlefield_alice, battlefield_bob=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(battlefield_alice))
        .player("bob", life=20, battlefield=list(battlefield_bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _damage_to_bob(scenario, attacker):
    scenario.attack_with(attacker, defending="bob")
    scenario.no_blocks()
    dealt = scenario.combat_damage()
    bob = scenario.player("bob")
    return sum(amount for target, amount in dealt if target is bob)


def test_assault_formation_grants_toughness_damage_to_another_creature():
    scenario = _attack_unblocked(["Assault Formation", "Prudent Fateseer // Peer Review"])
    seer = scenario.creature("Prudent Fateseer", "alice")
    assert _damage_to_bob(scenario, seer) == 4


def test_belligerent_brontodon_itself_assigns_its_toughness():
    scenario = _attack_unblocked(["Belligerent Brontodon"])
    brontodon = scenario.creature("Belligerent Brontodon", "alice")
    assert _damage_to_bob(scenario, brontodon) == 6


def test_you_control_wording_does_not_reach_an_opponents_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Assault Formation"])
        .player("bob", life=20, battlefield=["Wall of Omens"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chars = scenario.game.computed_board().of(scenario.creature("Wall of Omens", "bob"))
    assert not any("toughness rather than its power" in a for a in chars.abilities)


def test_doran_reaches_every_creature_including_an_opponents():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Doran, the Siege Tower"])
        .player("bob", life=20, battlefield=["Wall of Omens"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    doran = scenario.creature("Doran, the Siege Tower", "alice")
    assert _damage_to_bob(scenario, doran) == 5
