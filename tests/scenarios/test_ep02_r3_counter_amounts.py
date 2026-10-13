"""EP-02 R3 T2: counter and X amounts read off the source or a referenced object.

Rabble-Rouser: "Attacking creatures get +X/+0 until end of turn, where X is
this creature's power." The mass pump's "+X" slot may sit in either stat
(CR 608.2h: X is taken once as the ability resolves; CR 611.2c: the set of
affected creatures is fixed when the effect begins).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _characteristics(scenario, card):
    return scenario.game.characteristics_of(card).power_toughness


def _rabble_scenario(extra=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Rabble-Rouser", "Grizzly Bears", "Savannah Lions", "Mountain", *extra],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_rabble_rouser_pumps_attackers_by_its_own_power():
    scenario = _rabble_scenario()
    rouser = scenario.find("Rabble-Rouser", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.activate(rouser, *scenario.untapped_sources("Mountain"), index=0)
    scenario.resolve_top()
    # Rabble-Rouser is a 1/1; the Bears (2/2) attack and get +1/+0.
    assert _characteristics(scenario, bears) == (3, 2)


def test_rabble_rouser_leaves_non_attackers_alone():
    scenario = _rabble_scenario()
    rouser = scenario.find("Rabble-Rouser", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    scenario.attack_with(bears)
    scenario.activate(rouser, *scenario.untapped_sources("Mountain"), index=0)
    scenario.resolve_top()
    assert _characteristics(scenario, lions) == (2, 1)


def test_rabble_rouser_x_counts_its_plus_one_counters():
    scenario = _rabble_scenario()
    rouser = scenario.find("Rabble-Rouser", Zone.BATTLEFIELD, "alice")
    rouser.add_counters(Counter.PLUS_ONE, 2)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.activate(rouser, *scenario.untapped_sources("Mountain"), index=0)
    scenario.resolve_top()
    assert _characteristics(scenario, bears) == (5, 2)


def test_rabble_rouser_pumps_only_creatures_attacking_when_it_resolves():
    scenario = _rabble_scenario()
    rouser = scenario.find("Rabble-Rouser", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    scenario.attack_with(bears, lions)
    scenario.activate(rouser, *scenario.untapped_sources("Mountain"), index=0)
    scenario.resolve_top()
    assert _characteristics(scenario, bears) == (3, 2)
    assert _characteristics(scenario, lions) == (3, 1)


def _settle(scenario, limit=16):
    """Put triggers on the stack and resolve until the stack is empty."""
    for _ in range(limit):
        scenario.game.put_triggers_on_stack()
        if not scenario.stack_names():
            return
        scenario.pass_until_resolved()
    raise AssertionError(f"stack never emptied: {scenario.stack_names()}")


def _main_board(*battlefield, hand=(), opponent=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(battlefield), hand=list(hand), library=["Forest"] * 8)
        .player("bob", battlefield=list(opponent), library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _named(scenario, name):
    return [c for c in scenario.game.permanents_controlled_by("alice") if c.name == name]


# -- Fabricate N (CR 702.123a): counters on it, or N Servo tokens if you do not


def test_fabricate_taken_puts_the_counters_on_the_creature():
    scenario = _main_board(hand=["Cultivator of Blades"])
    scenario.will_take_the_may(True)
    cultivator = scenario.put_onto_battlefield("Cultivator of Blades")
    _settle(scenario)
    assert cultivator.counter_count(Counter.PLUS_ONE) == 2
    assert _named(scenario, "Servo Token") == []


def test_fabricate_declined_makes_that_many_servos_instead():
    scenario = _main_board(hand=["Cultivator of Blades"])
    scenario.will_take_the_may(False)
    cultivator = scenario.put_onto_battlefield("Cultivator of Blades")
    _settle(scenario)
    assert cultivator.counter_count(Counter.PLUS_ONE) == 0
    assert len(_named(scenario, "Servo Token")) == 2


def test_fabricate_one_scales_down_to_a_single_counter_or_servo():
    scenario = _main_board(hand=["Maulfist Squad"])
    scenario.will_take_the_may(False)
    scenario.put_onto_battlefield("Maulfist Squad")
    _settle(scenario)
    assert len(_named(scenario, "Servo Token")) == 1


def test_fabricate_two_on_a_second_printing_with_counters():
    scenario = _main_board(hand=["Angel of Invention"])
    scenario.will_take_the_may(True)
    angel = scenario.put_onto_battlefield("Angel of Invention")
    _settle(scenario)
    assert angel.counter_count(Counter.PLUS_ONE) == 2


# -- Cultivator of Blades: "you may have other attacking creatures get +X/+X"


def _cultivator_attack(take_the_may=True, extra=("Savannah Lions",), counters=0, bystanders=()):
    scenario = _main_board("Cultivator of Blades", "Grizzly Bears", *extra, *bystanders)
    cultivator = scenario.creature("Cultivator of Blades", "alice")
    if counters:
        cultivator.add_counters(Counter.PLUS_ONE, counters)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(take_the_may)
    scenario.attack_with(cultivator, bears)
    _settle(scenario)
    return scenario, cultivator, bears


def test_cultivator_pumps_other_attackers_by_its_power():
    scenario, cultivator, bears = _cultivator_attack()
    # Cultivator is a 1/1: the attacking Bears get +1/+1, Cultivator itself nothing.
    assert _characteristics(scenario, bears) == (3, 3)
    assert _characteristics(scenario, cultivator) == (1, 1)


def test_cultivator_x_includes_its_own_counters():
    scenario, cultivator, bears = _cultivator_attack(counters=2)
    assert _characteristics(scenario, bears) == (5, 5)


def test_cultivator_declined_pumps_nothing():
    scenario, _cultivator, bears = _cultivator_attack(take_the_may=False)
    assert _characteristics(scenario, bears) == (2, 2)


def test_cultivator_does_not_pump_creatures_that_are_not_attacking():
    scenario, _cultivator, _bears = _cultivator_attack()
    lions = scenario.creature("Savannah Lions", "alice")
    assert _characteristics(scenario, lions) == (2, 1)


# -- Unleash (CR 702.98a): may enter with a +1/+1 counter; can't block with one


def _blocker_scenario(counter_choice):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"], hand=["Hellhole Flailer"], library=["Forest"] * 8)
        .player("bob", battlefield=["Grizzly Bears"], hand=["Rakdos Drake"], library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(counter_choice)
    return scenario


def test_unleash_taken_enters_with_a_counter():
    scenario = _blocker_scenario(True)
    flailer = scenario.put_onto_battlefield("Hellhole Flailer")
    assert flailer.counter_count(Counter.PLUS_ONE) == 1


def test_unleash_declined_enters_without_a_counter():
    scenario = _blocker_scenario(False)
    flailer = scenario.put_onto_battlefield("Hellhole Flailer")
    assert flailer.counter_count(Counter.PLUS_ONE) == 0


def test_unleashed_creature_with_a_counter_cannot_block():
    from magic_cards_model.machines.combat import block_refusal

    scenario = _blocker_scenario(True)
    drake = scenario.put_onto_battlefield("Rakdos Drake", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    attack = scenario.game.combat.attack_by(bears.id)
    reason = block_refusal(scenario.game, drake, attack)
    assert reason is not None and "unleash" in reason.lower()


def test_unleashed_creature_without_a_counter_can_block():
    from magic_cards_model.machines.combat import block_refusal

    scenario = _blocker_scenario(False)
    drake = scenario.put_onto_battlefield("Rakdos Drake", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    attack = scenario.game.combat.attack_by(bears.id)
    assert block_refusal(scenario.game, drake, attack) is None


def test_unleashed_creature_blocks_again_once_the_counter_is_gone():
    from magic_cards_model.machines.combat import block_refusal

    scenario = _blocker_scenario(True)
    drake = scenario.put_onto_battlefield("Rakdos Drake", "bob")
    drake.remove_counters(Counter.PLUS_ONE, 1)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    attack = scenario.game.combat.attack_by(bears.id)
    assert block_refusal(scenario.game, drake, attack) is None
