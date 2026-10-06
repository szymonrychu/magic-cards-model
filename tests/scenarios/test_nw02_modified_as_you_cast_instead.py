"""Flame Discharge ({X}{R}): "Flame Discharge deals X damage to target
creature or planeswalker. If you controlled a modified creature as you cast
this spell, it deals X plus 2 damage instead. (Equipment, Auras you control,
and counters are modifications.)"

CR 700.9: a permanent is modified if it has a counter on it, is equipped, or
is enchanted by an Aura *its controller* controls. "As you cast this spell"
(CR 601.2i: the spell becomes cast) fixes the question at the moment of
casting - it is a fact recorded on the cast (`CastRecord.
modified_creature_controlled_as_cast`), not a board check on resolution - so
a counter put on afterwards does not count, and one taken off afterwards
does not un-count. CR 614.1a: "instead" replaces the base instruction.

The present-tense "if you control a modified creature" reader
(`machines/conditions/board.py:_is_modified`) is a different clause and is
checked untouched at the bottom (Kami's Flare, T1's wave-2 card, shares it).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Flame Discharge"],
            battlefield=["Mountain", "Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Serra Angel", "Grizzly Bears"])
    )


def _cast_flame_discharge(scenario, target, *, x: int = 2):
    """Announce with X, pay, and leave it on the stack (not yet resolved)."""
    casting = scenario.cast("Flame Discharge", targets=[target])
    casting.x_value = x
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * (x + 1)))
    return scenario.put_on_stack(casting)


def test_without_a_modified_creature_it_deals_x():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _cast_flame_discharge(scenario, angel)
    scenario.resolve_top()

    assert angel.zone is Zone.BATTLEFIELD
    assert angel.damage == 2


def test_a_counter_on_your_creature_as_you_cast_makes_it_x_plus_two():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.creature("Grizzly Bears", "alice").add_counters("+1/+1", 1)
    angel = scenario.creature("Serra Angel", "bob")

    _cast_flame_discharge(scenario, angel)
    scenario.resolve_top()

    assert angel.zone is Zone.GRAVEYARD  # 2 + 2 = 4 damage on a 4/4


def test_equipment_modifies_too():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Flame Discharge"],
            battlefield=["Mountain", "Mountain", "Mountain", "Grizzly Bears", "Bonesplitter"],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bonesplitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    bonesplitter.attach_to(bears)
    angel = scenario.creature("Serra Angel", "bob")

    _cast_flame_discharge(scenario, angel)
    scenario.resolve_top()

    assert angel.zone is Zone.GRAVEYARD


def test_an_aura_you_control_modifies_but_an_opponents_aura_does_not():
    """CR 700.9: "enchanted by an Aura you control" - the Aura's controller
    must be the creature's controller. Bob's Pacifism on Alice's Bears leaves
    it unmodified."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Flame Discharge"],
            battlefield=["Mountain", "Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Serra Angel", "Pacifism"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    pacifism = scenario.find("Pacifism", Zone.BATTLEFIELD, "bob")
    pacifism.attach_to(bears)
    angel = scenario.creature("Serra Angel", "bob")

    _cast_flame_discharge(scenario, angel)
    scenario.resolve_top()

    assert angel.zone is Zone.BATTLEFIELD
    assert angel.damage == 2


def test_an_opponents_modified_creature_does_not_count():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    angel.add_counters("+1/+1", 1)  # a 5/5 modified creature - bob's, not ours

    _cast_flame_discharge(scenario, angel)
    scenario.resolve_top()

    assert angel.damage == 2


def test_a_counter_put_on_after_casting_does_not_count():
    """ "As you cast this spell": the fact is fixed when the spell is cast."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _cast_flame_discharge(scenario, angel)
    scenario.creature("Grizzly Bears", "alice").add_counters("+1/+1", 1)
    scenario.resolve_top()

    assert angel.zone is Zone.BATTLEFIELD
    assert angel.damage == 2


def test_a_modification_lost_after_casting_still_counts():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters("+1/+1", 1)
    angel = scenario.creature("Serra Angel", "bob")

    _cast_flame_discharge(scenario, angel)
    bears.remove_counters("+1/+1", 1)
    scenario.resolve_top()

    assert angel.zone is Zone.GRAVEYARD


def test_x_is_added_to_not_replaced_by_two():
    """ "X plus 2": with X = 0 and a modified creature the spell still deals 2,
    enough for a 2/2."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.creature("Grizzly Bears", "alice").add_counters("+1/+1", 1)
    their_bears = scenario.creature("Grizzly Bears", "bob")

    _cast_flame_discharge(scenario, their_bears, x=0)
    scenario.resolve_top()

    assert their_bears.zone is Zone.GRAVEYARD  # X(0) plus 2 = 2 on a 2/2


def test_an_aura_you_control_on_your_creature_modifies_it():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Flame Discharge"],
            battlefield=["Mountain", "Mountain", "Mountain", "Grizzly Bears", "Pacifism"],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.find("Pacifism", Zone.BATTLEFIELD, "alice").attach_to(
        scenario.creature("Grizzly Bears", "alice")
    )
    angel = scenario.creature("Serra Angel", "bob")

    _cast_flame_discharge(scenario, angel)
    scenario.resolve_top()

    assert angel.zone is Zone.GRAVEYARD


def test_the_present_tense_modified_reader_is_untouched():
    """ "If you control a modified creature" (no "as you cast") still reads the
    board as it is now - the clause Kami's Flare uses."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    source = scenario.find("Flame Discharge", Zone.HAND, "alice")
    ask = scenario.game.condition_holds
    assert ask("alice", "you control a modified creature", source) is False
    scenario.creature("Grizzly Bears", "alice").add_counters("+1/+1", 1)
    assert ask("alice", "you control a modified creature", source) is True
    assert ask("bob", "you control a modified creature", source) is False
