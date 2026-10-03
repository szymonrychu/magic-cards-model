"""R0b-T8 proofs: Seam Rip and Sheltered by Ghosts - "exile target nonland
permanent an opponent controls until this enchantment leaves the battlefield".

- CR 610.3: a one-shot effect that exiles "until" an event is followed by a
  second one-shot effect that returns the object when the event happens.
- CR 610.3b: if the event already happened between the ability triggering and
  the exile, the object is never exiled.
- CR 610.3c: it returns under its owner's control.
- CR 702.21a: ward is a triggered ability (counter unless the cost is paid).
- CR 702.15b: lifelink - damage dealt by the source gains its controller life.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def settle(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# --------------------------------------------------------------------------
# Seam Rip
# --------------------------------------------------------------------------


def _seam_rip_board(**bob) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Seam Rip"], battlefield=["Plains", "Grizzly Bears"])
        .player(
            "bob",
            battlefield=bob.pop("battlefield", ["Memnite", "Serra Angel", "Forest"]),
            **bob,
        )
        .build()
    )


def _cast_seam_rip(scenario, target):
    scenario.choose_trigger_targets("Seam Rip", [target])
    return scenario.cast_and_resolve("Seam Rip", *scenario.untapped_sources("Plains"))


def test_seam_rip_exiles_a_cheap_permanent_until_it_leaves():
    scenario = _seam_rip_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "bob")

    rip = _cast_seam_rip(scenario, memnite)
    settle(scenario)

    assert rip.zone is Zone.BATTLEFIELD
    assert memnite.zone is Zone.EXILE

    scenario.game.destroy(rip)
    settle(scenario)

    assert rip.zone is Zone.GRAVEYARD
    assert memnite.zone is Zone.BATTLEFIELD
    assert memnite.controller == "bob"


def test_seam_rip_returns_the_card_under_its_owners_control():
    """CR 610.3c: the permanent comes back under its owner's control, and it
    is a new object (summoning sick)."""
    scenario = _seam_rip_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "bob")
    rip = _cast_seam_rip(scenario, memnite)
    settle(scenario)

    scenario.game.return_to_hand(rip)
    settle(scenario)

    assert rip.zone is Zone.HAND
    assert memnite.zone is Zone.BATTLEFIELD
    assert memnite.controller == "bob"
    assert memnite.owner == "bob"


def test_seam_rip_cannot_take_a_permanent_with_mana_value_three_or_more():
    scenario = _seam_rip_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.cast_and_resolve("Seam Rip", *scenario.untapped_sources("Plains"))
    with pytest.raises(ValueError, match="mana value 2 or less"):
        scenario.choose_trigger_targets("Seam Rip", [angel])


def test_seam_rip_cannot_take_a_land_or_your_own_permanent():
    scenario = _seam_rip_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    own = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Seam Rip", *scenario.untapped_sources("Plains"))
    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Seam Rip", [forest])
    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Seam Rip", [own])


def test_seam_rip_leaving_before_its_trigger_resolves_exiles_nothing():
    """CR 610.3b: the enchantment is gone before the exile would happen, so
    the target is never exiled at all."""
    scenario = _seam_rip_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "bob")
    rip = _cast_seam_rip(scenario, memnite)
    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 1

    scenario.game.destroy(rip)
    settle(scenario)

    assert rip.zone is Zone.GRAVEYARD
    assert memnite.zone is Zone.BATTLEFIELD


def test_two_seam_rips_each_hold_their_own_permanent():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Seam Rip", "Seam Rip"], battlefield=["Plains", "Plains"])
        .player("bob", battlefield=["Memnite", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    plains_a, plains_b = scenario.untapped_sources("Plains", "Plains")
    scenario.choose_trigger_targets("Seam Rip", [memnite])
    first = scenario.cast_and_resolve("Seam Rip", plains_a)
    settle(scenario)
    scenario.choose_trigger_targets("Seam Rip", [bears])
    scenario.cast_and_resolve("Seam Rip", plains_b)
    settle(scenario)
    assert memnite.zone is Zone.EXILE
    assert bears.zone is Zone.EXILE

    scenario.game.destroy(first)
    settle(scenario)

    assert memnite.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.EXILE


# --------------------------------------------------------------------------
# Sheltered by Ghosts
# --------------------------------------------------------------------------


def _sheltered_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Sheltered by Ghosts"],
            battlefield=["Plains", "Plains", "Grizzly Bears", "Mountain"],
            library=["Forest"] * 3,
        )
        .player(
            "bob",
            hand=["Lightning Bolt"],
            battlefield=["Serra Angel", "Mountain", "Mountain", "Mountain", "Forest"],
            library=["Forest"] * 3,
        )
        .build()
    )


def _cast_sheltered(scenario, enchant, exile_target):
    scenario.choose_trigger_targets("Sheltered by Ghosts", [exile_target])
    aura = scenario.cast_and_resolve(
        "Sheltered by Ghosts",
        *scenario.untapped_sources("Plains", "Plains"),
        targets=[enchant],
    )
    return aura


def test_sheltered_by_ghosts_exiles_any_nonland_permanent_until_the_aura_leaves():
    scenario = _sheltered_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")

    aura = _cast_sheltered(scenario, bears, angel)
    settle(scenario)

    assert aura.zone is Zone.BATTLEFIELD
    assert aura.attached_to == bears.id
    assert angel.zone is Zone.EXILE

    scenario.game.destroy(bears)
    scenario.state_based_actions()
    settle(scenario)

    assert aura.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.BATTLEFIELD
    assert angel.controller == "bob"


def test_sheltered_by_ghosts_can_only_enchant_a_creature_you_control():
    scenario = _sheltered_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    with pytest.raises(ValueError):
        scenario.cast("Sheltered by Ghosts", targets=[angel])


def test_sheltered_by_ghosts_cannot_exile_a_land_or_its_own_controllers_permanent():
    scenario = _sheltered_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Sheltered by Ghosts", *scenario.untapped_sources("Plains", "Plains"), targets=[bears]
    )
    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Sheltered by Ghosts", [mountain])
    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Sheltered by Ghosts", [bears])


def test_the_enchanted_creature_gets_plus_one_power_and_lifelink():
    scenario = _sheltered_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    _cast_sheltered(scenario, bears, angel)
    settle(scenario)

    characteristics = scenario.game.characteristics_of(bears)
    assert (characteristics.power, characteristics.toughness) == (3, 2)
    abilities = [ability.lower() for ability in characteristics.abilities]
    assert "lifelink" in abilities
    assert "ward {2}" in abilities


def test_lifelink_from_the_aura_gains_life_on_combat_damage():
    scenario = _sheltered_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    angel = scenario.creature("Serra Angel", "bob")
    _cast_sheltered(scenario, bears, angel)
    settle(scenario)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 23


def _bob_bolts_the_enchanted_bears(pays_ward: bool):
    scenario = _sheltered_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    _cast_sheltered(scenario, bears, angel)
    settle(scenario)
    scenario.pass_priority("alice")

    scenario.will_pay_the_mana_cost(pays_ward, username="bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountains[0], username="bob", targets=[bears])
    assert len(scenario.stack_names()) == 2, "the ward trigger sits above the Bolt"
    settle(scenario)
    return scenario, bolt, bears


def test_ward_two_counters_a_spell_aimed_at_the_enchanted_creature_unless_paid():
    _, bolt, bears = _bob_bolts_the_enchanted_bears(pays_ward=False)

    assert bolt.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0


def test_a_paid_ward_lets_the_spell_through():
    _, bolt, bears = _bob_bolts_the_enchanted_bears(pays_ward=True)

    assert bolt.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD, "3 damage kills the 3/2"


def test_sheltered_by_ghosts_leaving_before_its_trigger_resolves_exiles_nothing():
    scenario = _sheltered_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    aura = _cast_sheltered(scenario, bears, angel)
    scenario.game.put_triggers_on_stack()

    scenario.game.destroy(bears)
    scenario.state_based_actions()
    settle(scenario)

    assert aura.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# Second printings of the widened reader (CR 610.3b guard): an enchantment and
# an Aura that are neither listed cards nor in any shipped deck.
# --------------------------------------------------------------------------


def test_prayer_of_binding_leaving_before_its_trigger_resolves_exiles_nothing():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Prayer of Binding"], battlefield=["Plains"] * 4)
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.choose_trigger_targets("Prayer of Binding", [angel])
    prayer = scenario.cast_and_resolve(
        "Prayer of Binding", *scenario.untapped_sources(*["Plains"] * 4)
    )
    scenario.game.put_triggers_on_stack()

    scenario.game.destroy(prayer)
    settle(scenario)

    assert prayer.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.BATTLEFIELD


def test_prayer_of_binding_still_holds_the_permanent_when_it_stays():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Prayer of Binding"], battlefield=["Plains"] * 4)
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.choose_trigger_targets("Prayer of Binding", [angel])
    prayer = scenario.cast_and_resolve(
        "Prayer of Binding", *scenario.untapped_sources(*["Plains"] * 4)
    )
    settle(scenario)
    assert angel.zone is Zone.EXILE

    scenario.game.destroy(prayer)
    settle(scenario)
    assert angel.zone is Zone.BATTLEFIELD


def test_dimensional_exile_leaving_before_its_trigger_resolves_exiles_nothing():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Dimensional Exile"], battlefield=["Plains", "Plains", "Forest"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    scenario.choose_trigger_targets("Dimensional Exile", [angel])
    aura = scenario.cast_and_resolve(
        "Dimensional Exile", *scenario.untapped_sources("Plains", "Plains"), targets=[forest]
    )
    scenario.game.put_triggers_on_stack()

    scenario.game.destroy(forest)
    scenario.state_based_actions()
    settle(scenario)

    assert aura.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.BATTLEFIELD
