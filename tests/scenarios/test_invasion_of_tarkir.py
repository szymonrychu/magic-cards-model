"""Invasion of Tarkir // Defiant Thundermaw.

Verified this session with `mise run rules:find` against the current CR:

- **CR 508.1a-h** - declaring attackers is a turn-based action.
- **CR 603.3b/603.3d** - a triggered ability goes on the stack the next time
  a player would receive priority, its targets chosen the same way CR
  601.2c-d chooses a spell's.

Back face (Defiant Thundermaw): "Whenever a Dragon you control attacks, it
deals 2 damage to any target." The condition names a creature *subtype*
(CR 205.3m) - Archive Dragon (a real, Modern/Pioneer-legal Dragon Wizard)
proves the trigger fires for any Dragon, not only Defiant Thundermaw itself,
and Goblin Guide (not a Dragon) proves it does not fire for a non-Dragon
attacker.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

TARKIR = "Invasion of Tarkir"
THUNDERMAW = "Defiant Thundermaw"


def _stage_thundermaw(scenario) -> None:
    card = scenario.find(TARKIR, Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(card, "alice", transformed=True)


def test_a_dragon_attacking_deals_2_damage_to_any_target():
    scenario = (
        Scenario()
        .player("alice", hand=[TARKIR], battlefield=["Archive Dragon"])
        .player("bob")
        .build()
    )
    _stage_thundermaw(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dragon = scenario.creature("Archive Dragon", "alice")
    bob = scenario.player("bob")
    life_before = bob.life

    scenario.choose_trigger_targets(THUNDERMAW, ["bob"])
    scenario.attack_with(dragon, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bob.life == life_before - 2


def test_defiant_thundermaw_itself_attacking_also_triggers():
    """The condition is unqualified ("a Dragon you control", not "another
    Dragon") - Defiant Thundermaw is itself a Dragon."""
    scenario = Scenario().player("alice", hand=[TARKIR]).player("bob").build()
    _stage_thundermaw(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    thundermaw = scenario.creature(THUNDERMAW, "alice")
    bob = scenario.player("bob")
    life_before = bob.life

    scenario.choose_trigger_targets(THUNDERMAW, ["bob"])
    scenario.attack_with(thundermaw, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bob.life == life_before - 2


def test_a_non_dragon_attacking_does_not_trigger_it():
    """Elite Vanguard is a vanilla Human Soldier - no ability of its own to
    confound the stack check with."""
    scenario = (
        Scenario()
        .player("alice", hand=[TARKIR], battlefield=["Elite Vanguard"])
        .player("bob")
        .build()
    )
    _stage_thundermaw(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    elite_vanguard = scenario.creature("Elite Vanguard", "alice")
    bob = scenario.player("bob")
    life_before = bob.life

    scenario.attack_with(elite_vanguard, defending="bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack == [], "a non-Dragon attacking is not this trigger's condition"
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    scenario.combat_damage()

    # Only Elite Vanguard's own combat damage reaches bob - no extra 2 from
    # a trigger that never should have fired.
    assert bob.life == life_before - elite_vanguard.power
