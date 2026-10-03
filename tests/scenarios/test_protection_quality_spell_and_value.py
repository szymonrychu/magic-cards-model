"""Protection from a spell subtype ("Arcane"), a supertype ("snow"), a colour
count ("multicolored") and a mana-value comparator ("mana value 3 or
greater") - CR 702.16a, enforced for targeting (CR 702.16b), blocking
(CR 702.16f), damage (CR 702.16e) and attachment (CR 702.16c, CR 702.16d).

A mana value (CR 202.3) is a permanent's computed one, a spell's on the stack
with X as chosen (CR 202.3e), and a card's printed one anywhere else.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import (
    aura_state_based_actions,
    equipment_state_based_actions,
)
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(creature: str, *, alice_hand=(), bob=(), lands=("Mountain", "Mountain", "Mountain")):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=list(alice_hand), battlefield=list(lands))
        .player("bob", battlefield=[creature, *bob])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(creature, "bob")


def _combat(attacker: str, *blockers: str):
    scenario = (
        Scenario()
        .player("alice", battlefield=[attacker])
        .player("bob", battlefield=list(blockers))
        .build()
    )
    protected = scenario.creature(attacker, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(protected)
    scenario.advance()
    return scenario, protected


# -- Arcane (a spell subtype) ------------------------------------------------


def test_an_arcane_spell_cannot_target_protection_from_arcane():
    scenario, riftwalker = _board("Kitsune Riftwalker", alice_hand=["Glacial Ray"])

    casting = scenario.cast("Glacial Ray", username="alice")
    with pytest.raises(ValueError, match="protection"):
        casting.choose_targets([riftwalker])


def test_a_non_arcane_spell_targets_protection_from_arcane():
    scenario, riftwalker = _board("Kitsune Riftwalker", alice_hand=["Lightning Bolt"])
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")[:1]

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[riftwalker])

    assert riftwalker.zone is Zone.GRAVEYARD


def test_the_damage_of_an_arcane_spell_still_on_the_stack_is_prevented():
    scenario, riftwalker = _board("Kitsune Riftwalker", alice_hand=["Glacial Ray"])
    ray = scenario.find("Glacial Ray", Zone.HAND, "alice")

    scenario.game.deal_damage(riftwalker, 2, source=ray)

    assert riftwalker.damage == 0, "CR 702.16a: an Arcane card is a source of that subtype anywhere"


# -- snow (a supertype) ------------------------------------------------------


def test_a_snow_creature_cannot_block_protection_from_snow():
    scenario, hulk = _combat("Ronom Hulk", "Stalking Yeti")

    with pytest.raises(ValueError, match="protection"):
        scenario.block(hulk, scenario.creature("Stalking Yeti", "bob"))


def test_a_nonsnow_creature_blocks_protection_from_snow():
    scenario, hulk = _combat("Ronom Hulk", "Hill Giant")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.block(hulk, giant)

    assert giant in scenario.blockers()


def test_snow_damage_is_prevented_and_nonsnow_damage_is_not():
    scenario, hulk = _board("Ronom Hulk", bob=("Icehide Golem", "Hill Giant"))
    golem = scenario.creature("Icehide Golem", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.game.deal_damage(hulk, 2, source=golem)
    assert hulk.damage == 0
    scenario.game.deal_damage(hulk, 2, source=giant)
    assert hulk.damage == 2


# -- multicolored (a colour count) -------------------------------------------


def test_a_multicolored_creature_cannot_block_protection_from_multicolored():
    scenario, sentinel = _combat("Spectrum Sentinel", "Watchwolf")

    with pytest.raises(ValueError, match="protection"):
        scenario.block(sentinel, scenario.creature("Watchwolf", "bob"))


def test_a_monocolored_creature_blocks_protection_from_multicolored():
    scenario, sentinel = _combat("Spectrum Sentinel", "Hill Giant")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.block(sentinel, giant)

    assert giant in scenario.blockers()


def test_a_multicolored_spell_cannot_target_protection_from_multicolored():
    scenario, sentinel = _board("Spectrum Sentinel", alice_hand=["Lightning Helix"])

    casting = scenario.cast("Lightning Helix", username="alice")
    with pytest.raises(ValueError, match="protection"):
        casting.choose_targets([sentinel])


def test_a_multicolored_aura_falls_off_protection_from_multicolored():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Spectrum Sentinel", "Soul Ransom"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sentinel = scenario.creature("Spectrum Sentinel", "alice")
    ransom = scenario.find("Soul Ransom", Zone.BATTLEFIELD, "alice")
    ransom.attach_to(sentinel)

    doomed = aura_state_based_actions(scenario.game)
    scenario.game.check_state_based_actions()

    assert ransom in doomed
    assert ransom.zone is Zone.GRAVEYARD


# -- mana value 3 or greater -------------------------------------------------


def test_a_creature_of_mana_value_3_cannot_block_but_one_of_2_can():
    scenario, skulk = _combat("Mistmeadow Skulk", "Hill Giant", "Grizzly Bears")

    with pytest.raises(ValueError, match="protection"):
        scenario.block(skulk, scenario.creature("Hill Giant", "bob"))
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.block(skulk, bears)
    assert bears in scenario.blockers()


def test_a_spell_of_mana_value_3_cannot_target_but_one_of_1_can():
    scenario, skulk = _board("Mistmeadow Skulk", alice_hand=["Char", "Lightning Bolt"])

    casting = scenario.cast("Char", username="alice")
    with pytest.raises(ValueError, match="protection"):
        casting.choose_targets([skulk])

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")[:1]
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[skulk])
    assert skulk.zone is Zone.GRAVEYARD


def test_damage_from_a_source_of_mana_value_3_is_prevented_and_2_is_not():
    scenario, skulk = _board("Mistmeadow Skulk", bob=("Hill Giant", "Grizzly Bears"))

    scenario.game.deal_damage(skulk, 1, source=scenario.creature("Hill Giant", "bob"))
    assert skulk.damage == 0
    scenario.game.deal_damage(skulk, 1, source=scenario.creature("Grizzly Bears", "bob"))
    assert skulk.damage == 1


def test_an_x_spell_has_the_x_it_was_cast_with_as_its_mana_value():
    """CR 202.3e: Fireball ({X}{R}) with X = 2 is a mana value 3 spell."""
    scenario, skulk = _board("Mistmeadow Skulk")
    fireball = card("Fireball")

    big = scenario.game.source_has_quality_of_card(
        fireball, "mana value 3 or greater", is_spell=True, source_mana_value=3
    )
    small = scenario.game.source_has_quality_of_card(
        fireball, "mana value 3 or greater", is_spell=True, source_mana_value=2
    )

    assert big and not small


def test_equipment_of_mana_value_3_falls_off_and_one_of_1_stays():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Mistmeadow Skulk", "Sword of Fire and Ice", "Bonesplitter"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    skulk = scenario.creature("Mistmeadow Skulk", "alice")
    sword = scenario.find("Sword of Fire and Ice", Zone.BATTLEFIELD, "alice")
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    sword.attach_to(skulk)
    splitter.attach_to(skulk)

    unattached = equipment_state_based_actions(scenario.game)

    assert sword in unattached and not sword.is_attached
    assert splitter.is_attached and sword.zone is Zone.BATTLEFIELD
    assert aura_state_based_actions(scenario.game) == []
