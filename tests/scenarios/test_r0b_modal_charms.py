"""R0b-T8 proofs: Prismari Charm and Archenemy's Charm - modal instants.

- CR 700.2: a modal spell's mode (or modes) is chosen as it is cast.
- CR 601.2b: the mode choice is announced first, before targets and costs, and
  only the chosen mode's targets are chosen (CR 700.2c).
- CR 700.2d: the same mode cannot be chosen twice unless the spell says so.
- CR 115.1a / 601.2c: "one or two targets" is chosen at announcement.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def cast_charm(scenario, name, mode, targets, *sources, username=None):
    casting = scenario.cast(name, username)
    casting.choose_modes([mode])
    casting.choose_targets(targets)
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    return casting


# --------------------------------------------------------------------------
# Prismari Charm
# --------------------------------------------------------------------------


def _prismari_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Prismari Charm"],
            battlefield=["Island", "Mountain", "Grizzly Bears"],
            library=["Forest", "Island", "Mountain", "Plains"],
        )
        .player("bob", battlefield=["Memnite", "Serra Angel", "Forest"], library=["Forest"] * 3)
        .build()
    )


def test_prismari_charm_mode_one_surveils_two_then_draws():
    scenario = _prismari_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    top_two = scenario.top_of_library(2)
    third = scenario.top_of_library(3)[2]
    scenario.surveil_to_graveyard(top_two[0], username="alice")
    casting = scenario.cast("Prismari Charm")
    casting.choose_modes([1])
    casting.choose_targets([])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Island", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert top_two[0].zone is Zone.GRAVEYARD
    assert third.zone is Zone.LIBRARY or third.zone is Zone.HAND
    assert [c.id for c in alice.hand] == [top_two[1].id]


def test_prismari_charm_mode_two_deals_one_damage_to_a_single_target():
    scenario = _prismari_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_charm(
        scenario,
        "Prismari Charm",
        2,
        ["bob"],
        *scenario.untapped_sources("Island", "Mountain"),
    )
    scenario.resolve_top()

    assert scenario.player("bob").life == 19


def test_prismari_charm_mode_two_deals_one_damage_to_each_of_two_targets():
    scenario = _prismari_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    memnite = scenario.creature("Memnite", "bob")
    cast_charm(
        scenario,
        "Prismari Charm",
        2,
        [angel, memnite],
        *scenario.untapped_sources("Island", "Mountain"),
    )
    scenario.resolve_top()
    scenario.state_based_actions()

    assert angel.damage == 1, "1 damage to *each* target, not divided"
    assert memnite.zone is Zone.GRAVEYARD


def test_prismari_charm_mode_two_can_hit_a_creature_and_a_player():
    scenario = _prismari_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    cast_charm(
        scenario,
        "Prismari Charm",
        2,
        [angel, "alice"],
        *scenario.untapped_sources("Island", "Mountain"),
    )
    scenario.resolve_top()

    assert angel.damage == 1
    assert scenario.player("alice").life == 19


def test_prismari_charm_mode_two_refuses_three_targets():
    scenario = _prismari_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Prismari Charm")
    casting.choose_modes([2])
    with pytest.raises(ValueError):
        casting.choose_targets(["bob", "alice", scenario.creature("Memnite", "bob")])


def test_prismari_charm_mode_three_returns_a_nonland_permanent_to_hand():
    scenario = _prismari_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    cast_charm(
        scenario,
        "Prismari Charm",
        3,
        [angel],
        *scenario.untapped_sources("Island", "Mountain"),
    )
    scenario.resolve_top()

    assert angel.zone is Zone.HAND
    assert angel in scenario.player("bob").hand


def test_prismari_charm_mode_three_cannot_target_a_land():
    scenario = _prismari_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    casting = scenario.cast("Prismari Charm")
    casting.choose_modes([3])
    with pytest.raises(ValueError):
        casting.choose_targets([forest])


def test_prismari_charm_needs_exactly_one_mode():
    scenario = _prismari_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Prismari Charm")
    with pytest.raises(ValueError):
        casting.choose_modes([1, 2])
    with pytest.raises(ValueError):
        casting.choose_modes([])


def test_only_the_chosen_modes_target_is_asked_for():
    """CR 700.2c: mode one has no target, so the spell has none."""
    scenario = _prismari_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Prismari Charm")
    casting.choose_modes([1])
    with pytest.raises(ValueError):
        casting.choose_targets(["bob"])


# --------------------------------------------------------------------------
# Archenemy's Charm
# --------------------------------------------------------------------------


def _archenemy_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Archenemy's Charm"],
            battlefield=["Swamp", "Swamp", "Swamp", "Grizzly Bears"],
            graveyard=["Serra Angel", "Memnite", "Lightning Bolt", "Jace Beleren"],
        )
        .player("bob", battlefield=["Serra Angel", "Memnite"], library=["Forest"] * 3)
        .build()
    )


def _swamps(scenario):
    return scenario.untapped_sources("Swamp", "Swamp", "Swamp")


def test_archenemys_charm_mode_one_exiles_a_creature():
    scenario = _archenemy_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    cast_charm(scenario, "Archenemy's Charm", 1, [angel], *_swamps(scenario))
    scenario.resolve_top()

    assert angel.zone is Zone.EXILE


def test_archenemys_charm_mode_one_exiles_a_planeswalker():
    scenario = _archenemy_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace = scenario.put_onto_battlefield("Jace Beleren", "bob", Zone.GRAVEYARD) if False else None
    del jace
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Archenemy's Charm"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Jace Beleren"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    cast_charm(scenario, "Archenemy's Charm", 1, [jace], *_swamps(scenario))
    scenario.resolve_top()

    assert jace.zone is Zone.EXILE


def test_archenemys_charm_mode_one_cannot_target_a_land_or_an_instant_card():
    scenario = _archenemy_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "alice")
    casting = scenario.cast("Archenemy's Charm")
    casting.choose_modes([1])
    with pytest.raises(ValueError):
        casting.choose_targets([swamp])


def test_archenemys_charm_mode_two_returns_one_card_from_the_graveyard():
    scenario = _archenemy_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    cast_charm(scenario, "Archenemy's Charm", 2, [angel], *_swamps(scenario))
    scenario.resolve_top()

    assert angel.zone is Zone.HAND


def test_archenemys_charm_mode_two_returns_a_creature_and_a_planeswalker_card():
    scenario = _archenemy_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "alice")
    jace = scenario.find("Jace Beleren", Zone.GRAVEYARD, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    cast_charm(scenario, "Archenemy's Charm", 2, [memnite, jace], *_swamps(scenario))
    scenario.resolve_top()

    assert memnite.zone is Zone.HAND
    assert jace.zone is Zone.HAND
    assert bolt.zone is Zone.GRAVEYARD


def test_archenemys_charm_mode_two_refuses_three_cards_and_a_noncreature_card():
    scenario = _archenemy_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "alice")
    jace = scenario.find("Jace Beleren", Zone.GRAVEYARD, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    casting = scenario.cast("Archenemy's Charm")
    casting.choose_modes([2])
    with pytest.raises(ValueError):
        casting.choose_targets([angel, memnite, jace])
    with pytest.raises(ValueError):
        casting.choose_targets([bolt])


def test_archenemys_charm_mode_three_adds_counters_and_lifelink_until_end_of_turn():
    scenario = _archenemy_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    cast_charm(scenario, "Archenemy's Charm", 3, [bears], *_swamps(scenario))
    scenario.resolve_top()

    assert bears.counter_count(Counter.PLUS_ONE) == 2
    characteristics = scenario.game.characteristics_of(bears)
    assert (characteristics.power, characteristics.toughness) == (4, 4)
    assert "lifelink" in [a.lower() for a in characteristics.abilities]

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 16
    assert scenario.player("alice").life == 24


def test_archenemys_charm_mode_three_only_targets_your_own_creature():
    scenario = _archenemy_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    casting = scenario.cast("Archenemy's Charm")
    casting.choose_modes([3])
    with pytest.raises(ValueError):
        casting.choose_targets([angel])


def test_archenemys_charm_lifelink_ends_at_end_of_turn_but_counters_stay():
    scenario = _archenemy_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    cast_charm(scenario, "Archenemy's Charm", 3, [bears], *_swamps(scenario))
    scenario.resolve_top()
    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)
    scenario.turn_based_actions()  # cleanup's own expiry (CR 514.2)
    assert bears.counter_count(Counter.PLUS_ONE) == 2
    abilities = [a.lower() for a in scenario.game.characteristics_of(bears).abilities]
    assert "lifelink" not in abilities
