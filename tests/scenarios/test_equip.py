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
    """CR 702.6a targets a creature *you control*. CR 601.2c (via CR 602.2b)
    refuses that target at announcement, before anything is paid; the
    CR 608.2b recheck is the left-the-battlefield test below."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    wolf = scenario.creature("Watchwolf", "bob")

    with pytest.raises(ValueError, match="Watchwolf"):
        equip(scenario, cutter, wolf)
    assert not cutter.is_attached
    assert scenario.game.stack_is_empty


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

    This test used to call `attachment_state_based_actions` by hand and assert
    it returned the Shadowspear, because nothing in `Game` dispatched it.
    `Game._state_based_actions_once` now does, beside
    `equipment_state_based_actions`, so the unattachment has already happened by
    the time anything here could ask for it - CR 704.3 checks "whenever a player
    would get priority", and resolving Karn's ability reaches one. The
    by-hand call is kept only as CR 704.3's repeat check: it must find nothing
    left to do.
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
    # CR 704.3's repeat check: the dispatched sweep already did it.
    assert attachment_state_based_actions(scenario.game) == []

    assert not spear.is_attached
    assert spear.zone is Zone.BATTLEFIELD, "CR 704.5p: it 'remains on the battlefield'"


def test_an_animated_equipment_falls_off_during_an_ordinary_state_based_action_check():
    """CR 704.5p reached the way the game reaches it, with nobody calling the
    sweep by hand.

    CR 704.3: "Whenever a player would get priority, the game checks for any of
    the listed conditions for state-based actions, then performs all applicable
    state-based actions simultaneously as a single event." Karn's +1 resolving
    onto an equipped Shadowspear (CR 301.5c: "An Equipment that's also a
    creature can't equip a creature unless that Equipment has reconfigure")
    creates the condition *during* the resolution, so the very next check has
    to perform it - no scenario should have to know the rule exists to see it
    happen.

    The board is the one above; what differs is that nothing here mentions
    `attachment_state_based_actions`.
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

    assert scenario.game.computed_board().of(spear).is_creature, "Karn's +1 landed"
    assert not spear.is_attached, "CR 704.5p performed by the ordinary check"
    assert spear.zone is Zone.BATTLEFIELD, "CR 704.5p: it 'remains on the battlefield'"
    assert equipped_creature(scenario.game, spear) is None
    assert bears.zone is Zone.BATTLEFIELD, "the host is untouched"


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


# --------------------------------------------------------------------------
# The equip target is read off the computed board (CR 613.5), not the
# printed type line
# --------------------------------------------------------------------------
#
# `_equip_effect`'s own legality recheck (CR 608.2b) used to ask
# `CardState.is_creature`, which is CR 613.1's *starting point* - "the values
# of the characteristics printed on that card" - and not CR 613.5's answer,
# "the application of continuous effects as described by the layer system ...
# continually and automatically". Karn, the Great Creator's own "+1: Until
# your next turn, up to one target noncreature artifact becomes an artifact
# creature with power and toughness each equal to its mana value" is the
# pool's route to a permanent whose printed type line and computed types
# disagree, the same route `test_an_animated_equipment_falls_off_the_creature
# _it_was_equipping` above already uses on the *host* side of an Equipment.
# Aimed at Sol Ring instead of at an Equipment, it proves the *target* side:
# a plain noncreature artifact Karn has animated is CR 301.5's legal creature
# to equip, and one he has not touched still is not.


def _karn_and_a_target_artifact() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Karn, the Great Creator",
                "Sol Ring",
                "Cori-Steel Cutter",
                "Mountain",
                "Mountain",
            ],
            library=["Island"] * 10,
        )
        .player("bob", library=["Island"] * 10)
    )


def test_a_permanent_karn_animated_can_be_equipped():
    """CR 613.1d puts Karn's type-changing effect in layer 4, so by the time
    equip resolves and rechecks its target (CR 608.2b) Sol Ring genuinely is a
    creature - CR 205.1b's "in addition to its other types", not a fiction the
    printed type line ("Artifact", no Creature) ever agrees with.
    """
    scenario = _karn_and_a_target_artifact().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.creature("Karn, the Great Creator", "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    scenario.activate(karn, index=0, targets=[ring])
    scenario.pass_until_resolved()

    assert scenario.game.computed_board().of(ring).is_creature
    assert Type.CREATURE not in ring.types, "the printed type line still says Artifact"

    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    activation = equip(scenario, cutter, ring)

    assert activation.resolve() is ring
    assert equipped_creature(scenario.game, cutter) is ring


def test_an_unanimated_noncreature_artifact_cannot_be_equipped():
    """The inverse of the test above: Sol Ring Karn never touched is still
    only ever an artifact, so "target creature you control" refuses it at
    announcement (CR 601.2c, via CR 602.2b) - nothing is paid and nothing
    goes on the stack.
    """
    scenario = _karn_and_a_target_artifact().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    assert not scenario.game.computed_board().of(ring).is_creature

    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError, match="Sol Ring"):
        equip(scenario, cutter, ring)

    assert scenario.game.stack_is_empty
    assert equipped_creature(scenario.game, cutter) is None
    assert not cutter.is_attached


def test_equipment_state_based_actions_leave_a_karn_animated_host_alone():
    """CR 704.5n's own sweep (`equipment_state_based_actions`) reads the same
    computed board through `_host_is_legal_for`: once Sol Ring is equipped
    while animated, the very next state-based-action check must not treat the
    printed "not a creature" reading as a reason to unattach the Equipment
    that just legally attached to it.
    """
    scenario = _karn_and_a_target_artifact().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.creature("Karn, the Great Creator", "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    scenario.activate(karn, index=0, targets=[ring])
    scenario.pass_until_resolved()

    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    equip(scenario, cutter, ring).resolve()

    assert equipment_state_based_actions(scenario.game) == []
    assert equipped_creature(scenario.game, cutter) is ring
