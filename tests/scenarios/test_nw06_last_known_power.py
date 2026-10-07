"""Last-known power/toughness keeps counters (CR 608.2h, CR 113.7a, CR 122.2).

The snapshot used to be skipped whenever the computed value equalled the
printing plus counters, so after the zone change (counters gone, CR 122.2) the
bare printing came back. Goblin Fireleaper ("When this creature dies, it deals
damage equal to its power to target creature an opponent controls") reads it.
"""

import pytest

from magic_cards_model.machines import Step

from .harness import Scenario


def _drain(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goblin Fireleaper", "Mountain", "Mountain"])
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _die(scenario, leaper, giant) -> None:
    scenario.will_choose_targets(giant)
    scenario.game.destroy(leaper)
    _drain(scenario)


def test_plus_counters_survive_death_in_the_damage_the_trigger_deals():
    scenario = _board()
    leaper = scenario.creature("Goblin Fireleaper", "alice")
    giant = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.game.add_counters(leaper, "+1/+1", 2)
    _die(scenario, leaper, giant)
    assert giant.damage == 3, "1 printed + 2 counters"
    assert leaper.last_known_power == 3
    assert leaper.last_known_toughness == 1 + 2


def test_minus_counters_survive_death_too():
    scenario = _board()
    leaper = scenario.creature("Goblin Fireleaper", "alice")
    giant = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.game.add_counters(leaper, "+1/+1", 3)
    scenario.game.add_counters(leaper, "-1/-1", 1)
    _die(scenario, leaper, giant)
    assert giant.damage == 3, "1 + 3 - 1"


def test_pump_plus_counters_both_count():
    scenario = _board()
    leaper = scenario.creature("Goblin Fireleaper", "alice")
    giant = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.game.add_counters(leaper, "+1/+1", 2)
    scenario.activate(leaper, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.resolve_top()
    assert scenario.game.power_of(leaper) == 4
    _die(scenario, leaper, giant)
    assert giant.damage == 4


@pytest.mark.parametrize("how", ["destroy", "sacrifice", "exile_permanent", "return_to_hand"])
def test_snapshot_is_taken_on_every_leave_path(how):
    scenario = _board()
    leaper = scenario.creature("Goblin Fireleaper", "alice")
    scenario.game.add_counters(leaper, "+1/+1", 2)
    getattr(scenario.game, how)(leaper)
    assert leaper.power == 3
    assert leaper.toughness == 3
