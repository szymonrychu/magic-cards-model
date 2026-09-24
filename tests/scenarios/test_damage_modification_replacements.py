"""Replacement effects that modify damage as it would be dealt (CR 614.1a,
CR 614.2, CR 616.1).

- "If a source you control would deal noncombat damage to an opponent or a
  permanent an opponent controls, instead it deals that much damage plus X,
  where X is Hawkeye's power." (Hawkeye, Young Avenger) - Torbran, Thane of
  Red Fell's "... it deals that much damage plus 2 instead." is the second
  printing of the template; the "plus X, where X is `<this>`'s power" amount
  is printed on no other card and is read as the replacement applies. When
  both apply to one event, CR 616.1 lets the affected player or the
  controller of the affected object choose the order - for two additions
  the result is the same either way.
- "If damage would be dealt to Wolverine, instead that damage is dealt, but
  all other damage already dealt to him is healed." (Wolverine, Fierce
  Fighter) - damage already marked (CR 120.3e) is removed as the new damage
  is dealt; damage dealt simultaneously with it (CR 510.2's one combat
  damage event) is not "already dealt" and stays.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _bolt(scenario, target, mountain="Mountain", username="alice"):
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources(mountain, username=username),
        username=username,
        targets=[target],
    )


# -- Hawkeye -----------------------------------------------------------------------


def test_hawkeye_adds_his_power_to_noncombat_damage_to_an_opponent():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Lightning Bolt"], battlefield=["Hawkeye, Young Avenger", "Mountain"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt(scenario, "bob")
    assert scenario.player("bob").life == 20 - 3 - 2


def test_hawkeye_adds_his_power_to_damage_to_an_opponents_creature():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Lightning Bolt"], battlefield=["Hawkeye, Young Avenger", "Mountain"]
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    giant_damage_before = giant.damage
    _bolt(scenario, giant)
    assert giant.zone is Zone.GRAVEYARD or giant.damage - giant_damage_before == 5


def test_hawkeye_leaves_damage_to_your_own_permanents_alone():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Hawkeye, Young Avenger", "Snapping Sailback", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sailback = scenario.creature("Snapping Sailback", "alice")
    _bolt(scenario, sailback)
    assert sailback.damage == 3


def test_hawkeye_does_not_touch_combat_damage():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hawkeye, Young Avenger", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.advance()
    scenario.advance()
    scenario.attack_with(bears)
    scenario.advance()
    scenario.no_blocks()
    scenario.advance()
    scenario.combat_damage()
    assert scenario.player("bob").life == 18


def test_hawkeye_reads_his_power_as_the_damage_is_dealt():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Lightning Bolt"], battlefield=["Hawkeye, Young Avenger", "Mountain"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hawkeye = scenario.creature("Hawkeye, Young Avenger", "alice")
    hawkeye.add_counters("+1/+1", 3)
    _bolt(scenario, "bob")
    assert scenario.player("bob").life == 20 - 3 - 5


def test_an_opponents_source_is_not_one_you_control():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hawkeye, Young Avenger"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.deal_damage(
        scenario.player("alice"), 3, source=scenario.creature("Hill Giant", "bob")
    )
    assert scenario.player("alice").life == 17


def test_hawkeye_and_torbran_both_add():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Hawkeye, Young Avenger", "Torbran, Thane of Red Fell", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt(scenario, "bob")
    assert scenario.player("bob").life == 20 - 3 - 2 - 2


def test_torbran_adds_two_to_a_red_source():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Lightning Bolt"], battlefield=["Torbran, Thane of Red Fell", "Mountain"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt(scenario, "bob")
    assert scenario.player("bob").life == 15


# -- Wolverine ---------------------------------------------------------------------


def test_wolverine_heals_old_damage_as_new_damage_is_dealt():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wolverine, Fierce Fighter"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolverine = scenario.creature("Wolverine, Fierce Fighter", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.game.deal_damage(wolverine, 3, source=giant)
    assert wolverine.damage == 3
    scenario.game.deal_damage(wolverine, 4, source=giant)
    scenario.state_based_actions()

    assert wolverine.zone is Zone.BATTLEFIELD, "only the 4 remains - toughness 5"
    assert wolverine.damage == 4


def test_wolverine_still_dies_to_one_lethal_hit():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wolverine, Fierce Fighter"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolverine = scenario.creature("Wolverine, Fierce Fighter", "alice")
    scenario.game.deal_damage(wolverine, 5, source=scenario.creature("Hill Giant", "bob"))
    scenario.state_based_actions()
    assert wolverine.zone is Zone.GRAVEYARD


def test_simultaneous_combat_damage_is_not_already_dealt():
    """CR 510.2: two blockers' damage is dealt at once, so neither heals the
    other - 3 and 3 is 6 damage to a toughness-5 Wolverine."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Wolverine, Fierce Fighter"])
        .player("bob", battlefield=["Hill Giant", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolverine = scenario.creature("Wolverine, Fierce Fighter", "alice")
    first, second = scenario.creatures("Hill Giant", "Hill Giant", username="bob")
    scenario.advance()
    scenario.advance()
    scenario.attack_with(wolverine)
    scenario.advance()
    scenario.block(wolverine, first, second)
    scenario.advance()
    scenario.will_assign_combat_damage((first, 3))
    scenario.combat_damage()
    scenario.state_based_actions()
    assert wolverine.zone is Zone.GRAVEYARD


def test_damage_from_an_earlier_step_is_healed_by_a_later_hit():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wolverine, Fierce Fighter"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Hill Giant", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolverine = scenario.creature("Wolverine, Fierce Fighter", "alice")
    scenario.game.deal_damage(wolverine, 4, source=scenario.creature("Hill Giant", "bob"))
    scenario.game.deal_damage(wolverine, 3, source=scenario.creature("Hill Giant", "bob"))
    scenario.state_based_actions()
    assert wolverine.damage == 3
    assert wolverine.zone is Zone.BATTLEFIELD


@pytest.mark.parametrize(
    "name",
    ["Hawkeye, Young Avenger", "Wolverine, Fierce Fighter", "Torbran, Thane of Red Fell"],
)
def test_every_clause_is_handled(name):
    for clause in card_support(card(name)).clauses:
        assert clause.outcome == "handled", (name, clause.text, clause.outcome)
