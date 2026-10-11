"""Scenario: two static abilities that change what damage does - "All damage is
dealt as though its source had wither." (Everlasting Torment, CR 702.80a,
CR 120.3d) and "Lethal damage dealt to creatures you control is determined by
their power rather than their toughness." (Zilortha, Strength Incarnate,
CR 120.6, CR 704.5g, CR 510.1c).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import lethal_for
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def duel(alice, bob):
    return Scenario().player("alice", battlefield=list(alice)).player("bob", battlefield=list(bob))


def fight(scenario):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.attack_with(bears)
    scenario.block(bears, angel)
    scenario.combat_damage()
    return bears, angel


def test_without_torment_combat_damage_is_marked():
    bears, angel = fight(duel(["Grizzly Bears"], ["Serra Angel"]).build())
    assert angel.damage == 2 and angel.counter_count(Counter.MINUS_ONE) == 0


def test_torment_makes_a_non_wither_creature_deal_minus_one_counters():
    bears, angel = fight(duel(["Grizzly Bears", "Everlasting Torment"], ["Serra Angel"]).build())
    assert angel.damage == 0
    assert angel.counter_count(Counter.MINUS_ONE) == 2


def test_torment_applies_whoever_controls_it():
    bears, angel = fight(duel(["Grizzly Bears"], ["Serra Angel", "Everlasting Torment"]).build())
    assert angel.counter_count(Counter.MINUS_ONE) == 2


def test_torment_turns_noncombat_damage_into_counters_too():
    scenario = duel(["Grizzly Bears", "Everlasting Torment"], ["Serra Angel"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.game.deal_damage(angel, 3, source=bears)
    assert angel.damage == 0 and angel.counter_count(Counter.MINUS_ONE) == 3


def test_torment_leaves_player_damage_as_life_loss():
    scenario = duel(["Grizzly Bears", "Everlasting Torment"], []).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears"))
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.player("bob").life == 18


def test_zilortha_makes_power_the_lethal_threshold_of_your_creatures():
    """Giant Spider is a 2/4: two damage is lethal under Zilortha."""
    scenario = duel(["Zilortha, Strength Incarnate", "Giant Spider"], ["Giant Spider"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.creature("Giant Spider", "alice")
    theirs = scenario.creature("Giant Spider", "bob")
    source = scenario.creature("Zilortha, Strength Incarnate")
    scenario.game.deal_damage(mine, 2, source=source)
    scenario.game.deal_damage(theirs, 2, source=source)
    scenario.game.check_state_based_actions()
    assert mine.zone is Zone.GRAVEYARD
    assert theirs.zone is Zone.BATTLEFIELD


def test_zilortha_changes_the_damage_a_blocked_attacker_must_assign():
    scenario = duel(["Zilortha, Strength Incarnate", "Giant Spider"], ["Grizzly Bears"]).build()
    spider = scenario.creature("Giant Spider", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    assert lethal_for(bears, spider, scenario.game) == 2
    assert lethal_for(spider, bears, scenario.game) == 2


def test_without_zilortha_toughness_is_the_threshold():
    scenario = duel(["Giant Spider"], []).build()
    spider = scenario.creature("Giant Spider")
    bears_source = spider
    assert lethal_for(bears_source, spider, scenario.game) == 4
