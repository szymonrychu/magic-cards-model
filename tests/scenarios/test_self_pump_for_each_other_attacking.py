"""Scenario: "Whenever this creature attacks, it gets +N/+M until end of
turn for each other attacking `<quality>`." - one reader
(`_parse_self_pump_for_each_clause` fed by `_for_each_multiplier`'s
"(other) attacking `<qualifier>`" branch), proven on Goblin Piledriver
(+2/+0 per other attacking Goblin) and, with a different quality and a
different per-unit pump, on Cenn's Heir (+1/+1 per other attacking Kithkin).

CR 608.2h: the count is information from the game, determined once, when the
ability resolves (so an attacker removed from combat while the trigger waits
on the stack is not counted). CR 508.1k: an attacking creature is one that
was chosen as an attacker and has not been removed from combat; "other"
leaves the pumped creature itself out of its own count.
"""

from magic_cards_model.machines import Step

from .harness import Scenario

PILEDRIVER = "Goblin Piledriver"
HEIR = "Cenn's Heir"


def _attack(alice_board: list[str], *attackers: str):
    scenario = Scenario().player("alice", battlefield=alice_board).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    creatures = scenario.creatures(*attackers)
    scenario.attack_with(*creatures)
    return scenario, creatures


def _pt(scenario, creature):
    return scenario.game.characteristics_of(creature).power_toughness


def test_piledriver_gets_plus_two_power_per_other_attacking_goblin():
    scenario, (piledriver, _g1, _g2) = _attack(
        [PILEDRIVER, "Raging Goblin", "Raging Goblin"], PILEDRIVER, "Raging Goblin", "Raging Goblin"
    )
    scenario.resolve_top()
    assert _pt(scenario, piledriver) == (1 + 4, 2)


def test_no_other_attacker_means_no_pump():
    scenario, (piledriver,) = _attack([PILEDRIVER], PILEDRIVER)
    scenario.resolve_top()
    assert _pt(scenario, piledriver) == (1, 2)
    assert scenario.game.continuous_effects.effects == []


def test_a_non_goblin_attacker_is_not_counted():
    scenario, (piledriver, _bears, _goblin) = _attack(
        [PILEDRIVER, "Grizzly Bears", "Raging Goblin"], PILEDRIVER, "Grizzly Bears", "Raging Goblin"
    )
    scenario.resolve_top()
    assert _pt(scenario, piledriver) == (1 + 2, 2)


def test_a_goblin_that_stays_home_is_not_counted():
    scenario, (piledriver,) = _attack([PILEDRIVER, "Raging Goblin"], PILEDRIVER)
    scenario.resolve_top()
    assert _pt(scenario, piledriver) == (1, 2)


def test_the_pumped_goblin_does_not_count_itself():
    """Two Piledrivers: each triggers, each counts only the other one."""
    scenario, (first, second) = _attack([PILEDRIVER, PILEDRIVER], PILEDRIVER, PILEDRIVER)
    scenario.resolve_top()
    scenario.resolve_top()
    assert _pt(scenario, first) == (3, 2)
    assert _pt(scenario, second) == (3, 2)


def test_an_attacker_that_left_combat_before_resolution_is_not_counted():
    """Mogg Fanatic (a Goblin) attacks, then is sacrificed with the trigger
    still on the stack: CR 608.2h counts as the ability resolves."""
    scenario, (piledriver, fanatic, _guide) = _attack(
        [PILEDRIVER, "Mogg Fanatic", "Raging Goblin"], PILEDRIVER, "Mogg Fanatic", "Raging Goblin"
    )
    scenario.activate(fanatic, sacrificing=[fanatic], targets=[scenario.player("bob")])
    scenario.resolve_top()  # Fanatic's ability
    scenario.resolve_top()  # Piledriver's trigger
    assert _pt(scenario, piledriver) == (1 + 2, 2)


def test_the_pump_ends_at_end_of_turn():
    scenario, (piledriver, _guide) = _attack(
        [PILEDRIVER, "Raging Goblin"], PILEDRIVER, "Raging Goblin"
    )
    scenario.resolve_top()
    assert _pt(scenario, piledriver) == (3, 2)
    scenario.game.cleanup_step()
    assert _pt(scenario, piledriver) == (1, 2)


def test_cenns_heir_gets_plus_one_plus_one_per_other_attacking_kithkin():
    """Second printing: different quality (Kithkin) and a +1/+1 per unit."""
    scenario, (heir, _other_heir, _bears) = _attack(
        [HEIR, HEIR, "Grizzly Bears"], HEIR, HEIR, "Grizzly Bears"
    )
    # Both heirs trigger; resolve both. Each counts the other Heir only.
    scenario.resolve_top()
    scenario.resolve_top()
    assert _pt(scenario, heir) == (1 + 1, 1 + 1)


def test_cenns_heir_alone_is_not_pumped():
    scenario, (heir,) = _attack([HEIR, "Grizzly Bears"], HEIR)
    scenario.resolve_top()
    assert _pt(scenario, heir) == (1, 1)
