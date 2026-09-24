"""Assigning combat damage equal to toughness rather than power, as a one-shot
effect (CR 510.1a's "equal to its power", replaced; CR 611.2a/611.2c).

- "Whenever you attack, you may pay 2 life. If you do, until end of turn,
  creatures you control with toughness greater than their power assign
  combat damage equal to their toughness rather than their power." (The
  Kingpin of Crime) - CR 508.3d's "whenever you attack" trigger, CR 119.4's
  optional life payment, and an effect that modifies the rules of the game
  rather than any characteristic (CR 611.2c), so a creature is judged when it
  assigns its damage, not when the effect began.
- Bill the Pony's "Sacrifice a Food: Until end of turn, target creature you
  control assigns combat damage equal to its toughness rather than its
  power." is the second printing of the one-shot form.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _kingpin_attack(*, pay: bool, attackers=("The Kingpin of Crime", "Hill Giant")):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["The Kingpin of Crime", "Hill Giant", "Snapping Sailback"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.advance()
    scenario.advance()
    scenario.will_pay_the_life(pay)
    scenario.attack_with(*(scenario.creature(name, "alice") for name in attackers))
    scenario.pass_until_resolved()
    scenario.advance()
    scenario.no_blocks()
    scenario.advance()
    return scenario


def test_kingpin_paid_makes_toughness_greater_than_power_creatures_hit_for_toughness():
    scenario = _kingpin_attack(pay=True)
    scenario.combat_damage()
    # The Kingpin is 1/5: 5 damage. Hill Giant is 3/3: toughness is not
    # greater than power, so it still deals 3.
    assert scenario.player("alice").life == 18, "paid 2 life"
    assert scenario.player("bob").life == 20 - 5 - 3


def test_kingpin_declined_changes_nothing():
    scenario = _kingpin_attack(pay=False)
    scenario.combat_damage()
    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20 - 1 - 3


def test_the_effect_reads_the_creature_as_it_assigns_damage():
    """CR 611.2c: it modifies the rules of the game, so a creature whose
    toughness only exceeds its power later in the turn is still covered."""
    scenario = _kingpin_attack(pay=True)
    giant = scenario.creature("Hill Giant", "alice")
    giant.add_counters("-1/-1", 1)  # 2/2 - still not greater
    assert scenario.game.power_of(giant) == 2
    scenario.combat_damage()
    assert scenario.player("bob").life == 20 - 5 - 2


def test_bill_the_pony_makes_its_target_assign_damage_equal_to_toughness():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Bill the Pony", "Snapping Sailback"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bill = scenario.creature("Bill the Pony", "alice")
    from magic_cards_model.machines.effects import create_tokens
    from magic_cards_model.models.token import PREDEFINED

    (food,) = create_tokens(scenario.game, PREDEFINED["Food"], "alice", 1)
    scenario.activate(bill, index=0, sacrificing=[food], targets=[bill])
    scenario.pass_until_resolved()
    scenario.advance()
    scenario.advance()
    scenario.attack_with(bill)
    scenario.advance()
    scenario.no_blocks()
    scenario.advance()
    scenario.combat_damage()
    assert scenario.player("bob").life == 16, "Bill the Pony is 1/4"


@pytest.mark.parametrize("name", ["The Kingpin of Crime", "Bill the Pony"])
def test_every_clause_is_handled(name):
    for clause in card_support(card(name)).clauses:
        assert clause.outcome == "handled", (name, clause.text, clause.outcome)
