"""Furnace Scamp: "Whenever this creature deals combat damage to a player, you
may sacrifice it. If you do, this creature deals 3 damage to that player."

CR 118.12 makes "if you do" depend on the sacrifice actually being made; CR
608.2h uses the Scamp's last known information as the source of the 3 damage
once it has left the battlefield; CR 607.1 makes "that player" the player the
combat damage landed on, never a target.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def hit(scenario, defending: str = "bob"):
    scamp = scenario.creature("Furnace Scamp", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scamp, defending=defending)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    return scamp


def board() -> Scenario:
    return Scenario().player("alice", battlefield=["Furnace Scamp"]).player("bob")


def test_sacrificing_deals_three_more_damage_to_the_player_it_hit():
    scenario = board().build()
    scenario.will_take_the_may(True, source="Furnace Scamp")
    scamp = hit(scenario)
    assert scenario.player("bob").life == 19
    while scenario.game.stack:
        scenario.resolve_top()
    assert scamp.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 16


def test_declining_keeps_the_scamp_and_deals_no_extra_damage():
    scenario = board().build()
    scenario.will_take_the_may(False, source="Furnace Scamp")
    scamp = hit(scenario)
    while scenario.game.stack:
        scenario.resolve_top()
    assert scamp.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 19


def test_that_player_is_the_one_damaged_not_just_any_opponent():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Furnace Scamp"])
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.will_take_the_may(True, source="Furnace Scamp")
    hit(scenario, defending="carol")
    while scenario.game.stack:
        scenario.resolve_top()
    assert scenario.player("carol").life == 16
    assert scenario.player("bob").life == 20


def test_a_blocked_scamp_deals_no_damage_to_a_player_and_does_not_trigger():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Furnace Scamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scamp = scenario.creature("Furnace Scamp", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scamp)
    scenario.block(scamp, bears)
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack == []
    assert scenario.player("bob").life == 20
