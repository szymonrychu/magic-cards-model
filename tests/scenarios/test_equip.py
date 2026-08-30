"""Equip: attaching an Equipment to a creature (CR 702.6).

CR 702.6a: "Equip is an activated ability of Equipment cards. 'Equip [cost]'
means "[Cost]: Attach this permanent to target creature you control. Activate
only as a sorcery.""

CR 301.5b is why this matters at all: "Equipment enter the battlefield like
other artifacts. They don't enter the battlefield attached to a creature. The
equip keyword ability attaches" it. So an Equipment on the battlefield is doing
nothing until equip resolves.

The corner cases are the three restrictions the rule carries and the one
state-based action that undoes it:

- "creature you control" (CR 702.6a), rechecked on resolution by CR 608.2b;
- "Activate only as a sorcery", which is CR 307.5's window;
- CR 301.5: "An Equipment can be attached to a creature. It can't legally be
  attached to anything that isn't a creature";
- CR 704.5n: "If an Equipment or Fortification is attached to an illegal
  permanent or to a player, it becomes unattached from that permanent or player.
  It remains on the battlefield" - the opposite of an Aura, which CR 704.5m puts
  in its owner's graveyard.

What the Equipment *does* once attached - Cori-Steel Cutter's "+1/+1 and has
trample and haste" - is a layer 6/7c continuous effect that nothing generates;
see `docs/engine-coverage.md`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import (
    equip_activation,
    equipment_state_based_actions,
    equipped_creature,
)
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from


def board(*extra: str) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Cori-Steel Cutter", "Grizzly Bears", "Mountain", "Mountain", *extra],
        )
        .player("bob", battlefield=["Watchwolf", "Mountain"])
    )


def equip(scenario, cutter, target, username="alice"):
    activation = equip_activation(scenario.game, cutter, target, username)
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain", username=username):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    return activation


def test_an_equipment_enters_attached_to_nothing():
    """CR 301.5b: it lands like any other artifact, equipping nothing."""
    scenario = board().build()
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")

    assert not cutter.is_attached
    assert equipped_creature(scenario.game, cutter) is None


def test_equip_attaches_it_to_a_creature_you_control():
    """CR 702.6a, the whole ability."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    activation = equip(scenario, cutter, bears)
    assert activation.resolve() is bears
    assert equipped_creature(scenario.game, cutter) is bears


def test_equip_uses_the_stack_so_the_attach_waits_for_resolution():
    """It is an activated ability, not a special action: nothing happens on activation."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    activation = equip(scenario, cutter, bears)
    assert activation.on_stack in scenario.game.stack
    assert not cutter.is_attached

    activation.resolve()
    assert cutter.is_attached


def test_equip_can_only_be_activated_as_a_sorcery():
    """CR 702.6a's "Activate only as a sorcery", which is CR 307.5's window."""
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    activation = equip_activation(scenario.game, cutter, bears, "alice")
    assert "only be activated as a sorcery" in (activation.why_not() or "")
    with pytest.raises(ValueError, match="only be activated as a sorcery"):
        activation.begin_paying()


def test_it_cannot_be_attached_to_a_creature_an_opponent_controls():
    """CR 702.6a targets a creature *you control*, rechecked by CR 608.2b."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    wolf = scenario.creature("Watchwolf", "bob")

    activation = equip(scenario, cutter, wolf)
    assert activation.resolve() is None
    assert not cutter.is_attached


def test_a_target_that_left_the_battlefield_attaches_nothing():
    """CR 608.2b: the target is illegal by the time the ability resolves."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    activation = equip(scenario, cutter, bears)
    scenario.game.destroy(bears)

    assert activation.resolve() is None
    assert not cutter.is_attached


def test_an_equipped_creature_dying_leaves_the_equipment_behind():
    """CR 704.5n: it becomes unattached and *remains on the battlefield*."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    equip(scenario, cutter, bears).resolve()

    scenario.game.destroy(bears)
    unattached = equipment_state_based_actions(scenario.game)

    assert unattached == [cutter]
    assert cutter.zone is Zone.BATTLEFIELD
    assert not cutter.is_attached


def test_a_still_legal_equipment_is_left_alone():
    """CR 704.5n only fires on an *illegal* permanent."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    equip(scenario, cutter, bears).resolve()

    assert equipment_state_based_actions(scenario.game) == []
    assert equipped_creature(scenario.game, cutter) is bears


def test_equipping_a_second_creature_moves_it():
    """CR 701.3a: attaching to something new unattaches it from the old one."""
    scenario = board("Watchwolf").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "alice")

    equip(scenario, cutter, bears).resolve()
    assert equipped_creature(scenario.game, cutter) is bears

    for permanent in scenario.game.battlefield:
        permanent.untap()
    equip(scenario, cutter, wolf).resolve()
    assert equipped_creature(scenario.game, cutter) is wolf
