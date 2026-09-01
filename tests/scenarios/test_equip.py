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
    attachment_state_based_actions,
    equip_activation,
    equipment_state_based_actions,
    equipped_creature,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
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


# --------------------------------------------------------------------------
# CR 704.5p - the *other* unattachment state-based action
# --------------------------------------------------------------------------


def test_an_animated_equipment_falls_off_the_creature_it_was_equipping():
    """CR 704.5p, the rule CR 704.5n above is deliberately not: "If a battle or
    creature is attached to an object or player, it becomes unattached and
    remains on the battlefield."

    CR 301.5c is what makes it matter: "An Equipment that's also a creature
    can't equip a creature unless that Equipment has reconfigure." Karn, the
    Great Creator's "+1: Until your next turn, up to one target noncreature
    artifact becomes an artifact creature with power and toughness each equal to
    its mana value" aimed at an equipped Shadowspear is the pool's one route to
    that state, and it is CR 704.5p - not CR 704.5n - that resolves it: the
    *host* is a perfectly legal creature the whole time, so
    `equipment_state_based_actions` correctly finds nothing.

    What was silently wrong: `attachment_state_based_actions` read
    `CardState.types`, which is the printed type line (CR 613.5 puts the layer
    system's answer somewhere else entirely). Shadowspear prints "Legendary
    Artifact - Equipment", so the sweep saw a plain Equipment and left it
    equipping a creature it may not legally equip.

    The sweep is still called by hand here, as every CR 704.5n test above calls
    its own: `Game.check_state_based_actions` dispatches
    `equipment_state_based_actions` and not this one - see
    `docs/engine-coverage.md`.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Karn, the Great Creator",
                "Shadowspear",
                "Grizzly Bears",
                "Mountain",
                "Mountain",
            ],
            library=["Island"] * 10,
        )
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spear = scenario.find("Shadowspear", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    equip(scenario, spear, bears).resolve()
    assert equipped_creature(scenario.game, spear) is bears

    karn = scenario.creature("Karn, the Great Creator", "alice")
    scenario.activate(karn, index=0, targets=[spear])
    scenario.pass_until_resolved()
    assert scenario.game.computed_board().of(spear).is_creature
    assert Type.CREATURE not in spear.types, "the printed type line still says Artifact"

    # CR 704.5n's own sweep has nothing to say: the host is a legal creature.
    assert equipment_state_based_actions(scenario.game) == []

    unattached = attachment_state_based_actions(scenario.game)

    assert unattached == [spear]
    assert not spear.is_attached
    assert spear.zone is Zone.BATTLEFIELD, "CR 704.5p: it 'remains on the battlefield'"


def test_an_equipment_that_is_not_a_creature_is_left_attached():
    """The negative half of CR 704.5p, and the reason it may not simply
    unattach everything it finds: an ordinary Equipment on an ordinary creature
    is exactly the state the rule excuses by name ("neither an Aura, an
    Equipment, nor a Fortification")."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    equip(scenario, cutter, bears).resolve()

    assert attachment_state_based_actions(scenario.game) == []
    assert equipped_creature(scenario.game, cutter) is bears
