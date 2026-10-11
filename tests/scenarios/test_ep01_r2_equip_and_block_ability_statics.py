"""Equip restrictions, block-as-though statics and planeswalker-ability statics
(EP-01 round 2, T8).

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 301.5 / CR 301.5c** - an Equipment attaches to a creature it can legally
  equip; one attached to an illegal permanent becomes unattached (CR 704.5n).
- **CR 602.5b** - "Activate only once each turn" is a restriction on use.
- **CR 509.1a** - blockers must be untapped; "as though untapped" lifts that.
- **CR 606.3** - one loyalty ability per planeswalker per turn unless an effect
  allows more; **CR 606.4** - a loyalty symbol is the cost.

Printings: Gate Smasher (toughness 4 or greater), O-Naginata (power 3 or
greater), Goblin Brawler (can't be equipped), Leather Armor (once each turn),
Leonin Shikari (equip at instant speed), Masako the Humorless (tapped blockers),
Dragon Hunter (blocks Dragons as though it had reach), Oath of Teferi (loyalty
twice) and Carth the Lion (additional [+1]); Bonesplitter, Shivan Dragon and
Jace Beleren are the plain comparison printings.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario, mana_from


def _board(alice=(), *, bob=(), step=Step.PRECOMBAT_MAIN):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), library=["Plains"] * 8)
        .player("bob", battlefield=list(bob), library=["Plains"] * 8)
        .build()
    )
    scenario.start_at(step)
    return scenario


def _equip(scenario, equipment, creature, *sources, resolve=True):
    activation = equip_activation(scenario.game, equipment, creature, "alice")
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    if resolve:
        scenario.pass_until_resolved()
    return activation


def _attached_to(equipment, creature) -> bool:
    return equipment.attached_to == creature.id


# ---- "can be attached only to a creature with ..." --------------------------


def test_gate_smasher_equips_a_creature_with_toughness_four_or_more():
    scenario = _board(["Gate Smasher", "Serra Angel", "Plains", "Plains", "Plains"])
    smasher = scenario.find("Gate Smasher", Zone.BATTLEFIELD)
    big = scenario.creature("Serra Angel", "alice")
    assert scenario.game.toughness_of(big) >= 4
    _equip(scenario, smasher, big, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    assert _attached_to(smasher, big)


def test_gate_smasher_refuses_a_creature_with_toughness_three_or_less():
    scenario = _board(["Gate Smasher", "Grizzly Bears", "Plains", "Plains", "Plains"])
    smasher = scenario.find("Gate Smasher", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError, match="CR 301.5"):
        _equip(scenario, smasher, bears, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    assert not _attached_to(smasher, bears)


def test_o_naginata_reads_the_power_form():
    scenario = _board(["O-Naginata", "Grizzly Bears", "Shivan Dragon", "Mountain", "Mountain"])
    naginata = scenario.find("O-Naginata", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError, match="power 3 or greater"):
        _equip(scenario, naginata, bears, *scenario.untapped_sources("Mountain", "Mountain"))
    dragon = scenario.creature("Shivan Dragon", "alice")
    _equip(scenario, naginata, dragon, *scenario.untapped_sources("Mountain", "Mountain"))
    assert _attached_to(naginata, dragon)


def test_an_equipped_creature_that_shrinks_below_the_bound_becomes_unequipped():
    """CR 704.5n: the Equipment is on a creature it can no longer legally equip."""
    scenario = _board(["Gate Smasher", "Shivan Dragon"])
    smasher = scenario.find("Gate Smasher", Zone.BATTLEFIELD)
    dragon = scenario.creature("Shivan Dragon", "alice")
    smasher.attach_to(dragon)
    scenario.state_based_actions()
    assert _attached_to(smasher, dragon)
    scenario.game.add_counters(dragon, Counter.MINUS_ONE, 2)
    assert scenario.game.toughness_of(dragon) == 3
    scenario.state_based_actions()
    assert dragon.zone is Zone.BATTLEFIELD
    assert not _attached_to(smasher, dragon)


# ---- "can't be equipped" -------------------------------------------------------


def test_goblin_brawler_can_not_be_equipped_but_another_creature_can():
    scenario = _board(["Bonesplitter", "Goblin Brawler", "Grizzly Bears", "Plains"])
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD)
    brawler = scenario.creature("Goblin Brawler", "alice")
    with pytest.raises(ValueError, match="can't be equipped"):
        _equip(scenario, splitter, brawler, *scenario.untapped_sources("Plains"))
    bears = scenario.creature("Grizzly Bears", "alice")
    _equip(scenario, splitter, bears, *scenario.untapped_sources("Plains"))
    assert _attached_to(splitter, bears)


# ---- once each turn / instant speed ---------------------------------------------


def test_leather_armor_equips_for_free_but_only_once_each_turn():
    scenario = _board(["Leather Armor", "Grizzly Bears", "Memnite"])
    armor = scenario.find("Leather Armor", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")
    _equip(scenario, armor, bears)
    assert _attached_to(armor, bears)
    memnite = scenario.creature("Memnite", "alice")
    with pytest.raises(ValueError, match="only once each turn"):
        _equip(scenario, armor, memnite)
    assert _attached_to(armor, bears)


def test_leather_armor_may_equip_again_the_next_turn():
    scenario = _board(["Leather Armor", "Grizzly Bears", "Memnite"])
    armor = scenario.find("Leather Armor", Zone.BATTLEFIELD)
    _equip(scenario, armor, scenario.creature("Grizzly Bears", "alice"))
    scenario.game.activations.clear()  # a new turn clears the per-turn ledger
    memnite = scenario.creature("Memnite", "alice")
    _equip(scenario, armor, memnite)
    assert _attached_to(armor, memnite)


def test_a_plain_equipment_can_be_re_equipped_any_number_of_times():
    scenario = _board(["Bonesplitter", "Grizzly Bears", "Memnite", "Plains", "Plains"])
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD)
    _equip(
        scenario,
        splitter,
        scenario.creature("Grizzly Bears", "alice"),
        *scenario.untapped_sources("Plains"),
    )
    memnite = scenario.creature("Memnite", "alice")
    _equip(scenario, splitter, memnite, *scenario.untapped_sources("Plains"))
    assert _attached_to(splitter, memnite)


def test_equip_is_sorcery_speed_without_leonin_shikari():
    scenario = _board(["Bonesplitter", "Grizzly Bears", "Plains"], step=Step.BEGINNING_OF_COMBAT)
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")
    activation = equip_activation(scenario.game, splitter, bears, "alice")
    assert activation.why_not() is not None


def test_leonin_shikari_lets_me_equip_at_instant_speed():
    scenario = _board(
        ["Leonin Shikari", "Bonesplitter", "Grizzly Bears", "Plains"], step=Step.BEGINNING_OF_COMBAT
    )
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")
    activation = equip_activation(scenario.game, splitter, bears, "alice")
    assert activation.why_not() is None


# ---- block as though ----------------------------------------------------------------


def _attack_into(scenario, attacker_name):
    attacker = scenario.creature(attacker_name, "alice")
    attacker.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    return attacker


def test_masako_lets_a_tapped_creature_block():
    scenario = _board(["Grizzly Bears"], bob=["Masako the Humorless", "Memnite"])
    attacker = _attack_into(scenario, "Grizzly Bears")
    memnite = scenario.creature("Memnite", "bob")
    memnite.tap()
    assert scenario.game.why_cannot_block(memnite, attacker) is None
    scenario.block(attacker, memnite)
    assert memnite.id in scenario.game.combat.attack_by(attacker.id).blockers


def test_a_tapped_creature_still_cannot_block_without_masako():
    scenario = _board(["Grizzly Bears"], bob=["Memnite"])
    attacker = _attack_into(scenario, "Grizzly Bears")
    memnite = scenario.creature("Memnite", "bob")
    memnite.tap()
    assert "tapped" in scenario.game.why_cannot_block(memnite, attacker)


def test_masako_only_helps_its_controllers_creatures():
    scenario = _board(["Grizzly Bears", "Masako the Humorless"], bob=["Memnite"])
    attacker = _attack_into(scenario, "Grizzly Bears")
    memnite = scenario.creature("Memnite", "bob")
    memnite.tap()
    assert "tapped" in scenario.game.why_cannot_block(memnite, attacker)


def test_dragon_hunter_blocks_a_flying_dragon_but_not_a_flying_non_dragon():
    scenario = _board(["Shivan Dragon", "Serra Angel"], bob=["Dragon Hunter"])
    dragon = scenario.creature("Shivan Dragon", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    dragon.summoning_sick = angel.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dragon, angel)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    hunter = scenario.creature("Dragon Hunter", "bob")
    assert scenario.game.why_cannot_block(hunter, dragon) is None
    assert scenario.game.why_cannot_block(hunter, angel) is not None


def test_a_creature_without_the_line_cannot_block_a_flying_dragon():
    scenario = _board(["Shivan Dragon"], bob=["Grizzly Bears"])
    dragon = _attack_into(scenario, "Shivan Dragon")
    assert scenario.game.why_cannot_block(scenario.creature("Grizzly Bears", "bob"), dragon)


# ---- loyalty abilities ---------------------------------------------------------------


def _jace(scenario):
    return scenario.find("Jace Beleren", Zone.BATTLEFIELD)


def test_a_planeswalker_activates_once_per_turn_without_oath_of_teferi():
    scenario = _board(["Jace Beleren"])
    jace = _jace(scenario)
    scenario.activate(jace, index=0, username="alice")
    scenario.pass_until_resolved()
    assert scenario.why_cannot_activate(jace, 0, "alice") is not None


def test_oath_of_teferi_allows_a_second_loyalty_activation_but_not_a_third():
    scenario = _board(["Jace Beleren", "Oath of Teferi"])
    jace = _jace(scenario)
    scenario.activate(jace, index=0, username="alice")
    scenario.pass_until_resolved()
    assert scenario.why_cannot_activate(jace, 0, "alice") is None
    scenario.activate(jace, index=0, username="alice")
    scenario.pass_until_resolved()
    assert jace.loyalty == 3 + 2 + 2
    assert "already been activated" in scenario.why_cannot_activate(jace, 0, "alice")


def test_carth_the_lion_adds_a_loyalty_counter_to_the_cost():
    scenario = _board(["Jace Beleren", "Carth the Lion"])
    jace = _jace(scenario)
    scenario.activate(jace, index=0, username="alice")
    scenario.pass_until_resolved()
    assert jace.loyalty == 3 + 2 + 1


def test_carth_also_adds_to_a_minus_ability():
    scenario = _board(["Jace Beleren", "Carth the Lion"])
    jace = _jace(scenario)
    scenario.activate(jace, index=1, username="alice", targets=["alice"])
    scenario.pass_until_resolved()
    assert jace.loyalty == 3 - 1 + 1


def test_without_carth_the_cost_is_just_the_printed_symbol():
    scenario = _board(["Jace Beleren"])
    jace = _jace(scenario)
    scenario.activate(jace, index=0, username="alice")
    scenario.pass_until_resolved()
    assert jace.loyalty == 3 + 2
