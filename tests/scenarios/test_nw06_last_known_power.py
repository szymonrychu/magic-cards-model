"""Last-known power/toughness keeps counters (CR 608.2h, CR 113.7a, CR 122.2).

The snapshot used to be skipped whenever the computed value equalled the
printing plus counters, so after the zone change (counters gone, CR 122.2) the
bare printing came back. Goblin Fireleaper ("When this creature dies, it deals
damage equal to its power to target creature an opponent controls") reads it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.triggers import (
    GameEvent,
    event_subject_power,
    event_subject_toughness,
)
from magic_cards_model.models import Zone

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
    assert leaper.last_known_power_toughness() == (3, 3)


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
def test_last_known_stats_are_right_on_every_leave_path(how):
    scenario = _board()
    leaper = scenario.creature("Goblin Fireleaper", "alice")
    scenario.game.add_counters(leaper, "+1/+1", 2)
    getattr(scenario.game, how)(leaper)
    assert leaper.last_known_power_toughness() == (3, 3)


def test_minus_counters_and_pump_in_the_last_known_stats():
    scenario = _board()
    leaper = scenario.creature("Goblin Fireleaper", "alice")
    scenario.game.add_counters(leaper, "+1/+1", 3)
    scenario.game.add_counters(leaper, "-1/-1", 1)
    scenario.activate(leaper, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.resolve_top()
    scenario.game.destroy(leaper)
    assert leaper.last_known_power_toughness() == (4, 3)


def test_a_permanent_that_never_left_reads_its_live_stats():
    scenario = _board()
    leaper = scenario.creature("Goblin Fireleaper", "alice")
    scenario.game.add_counters(leaper, "+1/+1", 2)
    assert leaper.last_known_power_toughness() == (3, 3)


def test_event_subject_readers_see_the_counters():
    scenario = _board()
    leaper = scenario.creature("Goblin Fireleaper", "alice")
    scenario.game.add_counters(leaper, "+1/+1", 2)
    scenario.game.destroy(leaper)
    event = GameEvent(event=TriggerEvent.DIES, subject_id=leaper.id)
    assert event_subject_power(scenario.game, event) == 3
    assert event_subject_toughness(scenario.game, event) == 3


def test_source_characteristic_reader_keeps_counters_after_leaving():
    from magic_cards_model.machines.effects.draw_discard import _source_characteristic

    scenario = _board()
    leaper = scenario.creature("Goblin Fireleaper", "alice")
    scenario.game.add_counters(leaper, "+1/+1", 2)
    scenario.game.destroy(leaper)
    assert _source_characteristic(scenario.game, leaper, "power") == 3
    assert _source_characteristic(scenario.game, leaper, "toughness") == 3


def test_effect_cancelling_the_counters_still_reads_the_net_power():
    """Oona's Prowler 3/1 with two +1/+1 counters and -2/-0: computed power
    3 equals the bare printing, yet the counters were still contributing."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Oona's Prowler"], hand=["Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    prowler = scenario.creature("Oona's Prowler", "alice")
    scenario.game.add_counters(prowler, "+1/+1", 2)
    plains = scenario.find("Plains", Zone.HAND, "alice")
    scenario.activate(prowler, discarding=[plains])
    scenario.resolve_top()
    base = scenario.game.power_of(prowler)
    scenario.game.destroy(prowler)
    assert prowler.last_known_power_toughness()[0] == base
    assert base == 3
