"""Enchant: what an Aura may be aimed at (CR 702.5).

CR 702.5a: "Enchant is a static ability, written 'Enchant [object or player].'
The enchant ability restricts **what an Aura spell can target and what an Aura
can enchant**."

Two restrictions in one sentence, and they are checked at two different moments:
the announcement (CR 601.2c, because an Aura spell targets what it will enchant)
and the attachment (CR 701.3a). `machines/keywords.why_cannot_enchant` answers
both, so they cannot drift apart.

CR 702.5c: "If an Aura has multiple instances of enchant, all of them apply."
CR 702.5d is the one that reads backwards: "Auras that can enchant a player can
target and be attached to players. Such Auras **can't target permanents and
can't be attached to permanents**" - an exclusive restriction, not a floor.

Hyena Umbra is the printing in this pool: `Enchant creature`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import (
    aura_state_based_actions,
    enchant_restrictions,
    why_cannot_enchant,
)
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Hyena Umbra"],
            battlefield=["Grizzly Bears", "Plains", "Plains"],
        )
        .player("bob", battlefield=["Colossal Dreadmaw"])
    )


def test_the_restriction_is_read_off_the_printing():
    """CR 702.5a: "written 'Enchant [object or player]'"."""
    assert enchant_restrictions(card("Hyena Umbra")) == ["creature"]
    assert enchant_restrictions(card("Grizzly Bears")) == []


def test_an_aura_can_be_cast_at_a_creature():
    """The happy path: `Enchant creature`, aimed at a creature."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")

    casting = scenario.cast("Hyena Umbra", targets=[bears])

    assert casting.targets[0].card_id == bears.id


def test_an_aura_cannot_be_cast_at_a_player():
    """CR 702.5a: `Enchant creature` says creature, and a player is not one.

    CR 702.5d is the general form: an Aura that can enchant a player can't
    target permanents, and one that can't, can't target players.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError):
        scenario.cast("Hyena Umbra", targets=["bob"])


def test_an_aura_cannot_be_cast_at_a_noncreature_permanent():
    """A land is a permanent and is not a creature (CR 110.4a, CR 302.1)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.find("Plains", Zone.BATTLEFIELD)

    with pytest.raises(ValueError):
        scenario.cast("Hyena Umbra", targets=[plains])


def test_the_restriction_does_not_care_who_controls_the_creature():
    """ "Enchant creature" and not "Enchant creature you control"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    casting = scenario.cast("Hyena Umbra", targets=[dreadmaw])

    assert casting.targets[0].card_id == dreadmaw.id


def test_the_same_restriction_answers_for_the_attachment():
    """CR 702.5a restricts "what an Aura can enchant" as well as what it targets."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    plains = scenario.find("Plains", Zone.BATTLEFIELD)
    umbra = scenario.find("Hyena Umbra", Zone.HAND, "alice")

    assert why_cannot_enchant(umbra, bears, "alice", scenario.game) is None
    refusal = why_cannot_enchant(umbra, plains, "alice", scenario.game)
    assert refusal is not None
    assert "Enchant creature" in refusal


def test_an_aura_on_nothing_is_a_state_based_action():
    """CR 704.5m: "If an Aura is attached to an illegal object or player, or is
    not attached to an object or player, that Aura is put into its owner's
    graveyard."

    The opposite of an Equipment, which CR 704.5n merely unattaches - which is
    why `aura_state_based_actions` and `equipment_state_based_actions` are two
    functions and not one.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    umbra = scenario.find("Hyena Umbra", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(umbra, "alice")

    assert aura_state_based_actions(scenario.game) == [umbra]


def test_an_aura_whose_creature_died_is_illegal_too():
    """CR 704.5m again: the host has to still be there, and still be legal."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    umbra = scenario.find("Hyena Umbra", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(umbra, "alice")
    umbra.attach_to(bears)

    assert aura_state_based_actions(scenario.game) == []

    scenario.game.destroy(bears)

    assert aura_state_based_actions(scenario.game) == [umbra]
