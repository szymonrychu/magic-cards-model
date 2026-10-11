"""Scenario: conditional statics whose condition reads the board, an
equipped or paired creature, or a graveyard (EP-01 round 2, task 3).

Kolvori ("As long as you control three or more legendary creatures, ~ gets
+4/+2 and has vigilance."), Formation Breaker ("As long as you control a
creature with a counter on it, this creature gets +1/+2."), Villainous Ogre
("As long as you control a Demon, this creature has '{B}: Regenerate this
creature.'"), Oculus Whelp (a transformed permanent), Doc Ock (graveyard
count and "another Villain"), Hundred-Battle Veteran (kinds of counters),
the Human-equipped Equipment trio, Erebos's Titan, Expedition Diviner and
Sedge Sliver's quoted conditional pump.

Verified with `mise run rules:find`: CR 611.3a (not locked in), CR 604.2,
CR 613.1f (layer 6 grants), CR 613.4c (7c pump), CR 613.4b (7b base P/T),
CR 700.9 (modified).
"""

import pytest

from magic_cards_model.machines import Step, soulbond
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _next_turn(scenario) -> None:
    """Run this turn out and begin the next player's upkeep."""
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()


def _board(alice, bob=(), *, alice_graveyard=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=list(alice),
            graveyard=list(alice_graveyard),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _chars(scenario, name, username="alice"):
    return scenario.game.characteristics_of(scenario.find(name, Zone.BATTLEFIELD, username))


def _has(chars, text):
    return any(line.lower() == text.lower() for line in chars.abilities)


# -- Kolvori: N legendary creatures --------------------------------------------


def test_kolvori_with_three_legendary_creatures_gets_the_pump_and_vigilance():
    scenario = _board(["Kolvori, God of Kinship", "Kalitas, Traitor of Ghet", "Six"])
    chars = _chars(scenario, "Kolvori, God of Kinship")
    assert chars.power_toughness == (6, 6)
    assert _has(chars, "Vigilance")


def test_kolvori_with_only_two_legendary_creatures_gets_nothing():
    scenario = _board(["Kolvori, God of Kinship", "Kalitas, Traitor of Ghet"])
    chars = _chars(scenario, "Kolvori, God of Kinship")
    assert not _has(chars, "Vigilance")


def test_kolvori_ignores_nonlegendary_creatures():
    scenario = _board(["Kolvori, God of Kinship", "Grizzly Bears", "Llanowar Elves"])
    assert not _has(_chars(scenario, "Kolvori, God of Kinship"), "Vigilance")


# -- Formation Breaker: a creature with a counter ------------------------------


def test_formation_breaker_pumps_while_you_control_a_creature_with_a_counter():
    scenario = _board(["Formation Breaker", "Grizzly Bears"])
    assert _chars(scenario, "Formation Breaker").power_toughness == (2, 1)
    scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").add_counters("+1/+1")
    assert _chars(scenario, "Formation Breaker").power_toughness == (3, 3)


def test_formation_breaker_ignores_an_opponents_creature_with_a_counter():
    scenario = _board(["Formation Breaker"], ["Grizzly Bears"])
    scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").add_counters("+1/+1")
    assert _chars(scenario, "Formation Breaker").power_toughness == (2, 1)


# -- Villainous Ogre: a Demon grants a quoted ability --------------------------


def test_ogre_without_a_demon_has_no_regenerate_ability():
    scenario = _board(["Villainous Ogre", "Grizzly Bears"])
    assert "{B}: Regenerate this creature." not in _chars(scenario, "Villainous Ogre").abilities


def test_ogre_with_a_demon_gains_and_can_activate_regenerate():
    scenario = _board(["Villainous Ogre", "Razorjaw Oni"])
    ogre = scenario.find("Villainous Ogre", Zone.BATTLEFIELD, "alice")
    assert "Demon" in _chars(scenario, "Razorjaw Oni").subtypes
    assert "{B}: Regenerate this creature." in scenario.game.characteristics_of(ogre).abilities


# -- Heavy Mattock / Silver-Inlaid Dagger / True-Faith Censer: Human equipped --


def _equip(scenario, equipment, creature):
    scenario.find(equipment, Zone.BATTLEFIELD, "alice").attach_to(
        scenario.find(creature, Zone.BATTLEFIELD, "alice")
    )


def test_heavy_mattock_gives_a_human_an_additional_plus_one():
    scenario = _board(["Heavy Mattock", "Fugitive Wizard"])
    _equip(scenario, "Heavy Mattock", "Fugitive Wizard")
    assert _chars(scenario, "Fugitive Wizard").power_toughness == (3, 3)


def test_heavy_mattock_gives_a_nonhuman_only_the_base_bonus():
    scenario = _board(["Heavy Mattock", "Grizzly Bears"])
    _equip(scenario, "Heavy Mattock", "Grizzly Bears")
    assert _chars(scenario, "Grizzly Bears").power_toughness == (3, 3)


def test_silver_inlaid_dagger_and_censer_use_their_own_numbers():
    scenario = _board(["Silver-Inlaid Dagger", "True-Faith Censer", "Fugitive Wizard"])
    _equip(scenario, "Silver-Inlaid Dagger", "Fugitive Wizard")
    assert _chars(scenario, "Fugitive Wizard").power_toughness == (4, 1)


# -- Erebos's Titan --------------------------------------------------------------


def test_erebos_titan_is_indestructible_while_opponents_control_no_creatures():
    scenario = _board(["Erebos's Titan"], ["Mountain"])
    assert _has(_chars(scenario, "Erebos's Titan"), "Indestructible")


def test_erebos_titan_loses_indestructible_when_an_opponent_controls_a_creature():
    scenario = _board(["Erebos's Titan"], ["Grizzly Bears"])
    assert not _has(_chars(scenario, "Erebos's Titan"), "Indestructible")


# -- Hundred-Battle Veteran / Doc Ock --------------------------------------------


def test_doc_ock_graveyard_threshold_sets_base_8_8():
    scenario = _board(["Doc Ock, Sinister Scientist"], alice_graveyard=["Island"] * 8)
    assert _chars(scenario, "Doc Ock, Sinister Scientist").power_toughness == (8, 8)


def test_doc_ock_with_seven_cards_stays_4_5():
    scenario = _board(["Doc Ock, Sinister Scientist"], alice_graveyard=["Island"] * 7)
    assert _chars(scenario, "Doc Ock, Sinister Scientist").power_toughness == (4, 5)


def test_hundred_battle_veteran_needs_three_different_counter_kinds():
    scenario = _board(["Hundred-Battle Veteran", "Grizzly Bears", "Llanowar Elves"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    veteran = scenario.find("Hundred-Battle Veteran", Zone.BATTLEFIELD, "alice")
    bears.add_counters("+1/+1")
    elves.add_counters("flying")
    assert scenario.game.characteristics_of(veteran).power_toughness == (4, 2)
    veteran.add_counters("deathtouch")
    assert scenario.game.characteristics_of(veteran).power_toughness == (6, 6)


# -- Expedition Diviner: another Wizard -------------------------------------------


def test_diviner_with_another_wizard_gains_the_dies_draw_ability():
    scenario = _board(["Expedition Diviner", "Fugitive Wizard"])
    chars = _chars(scenario, "Expedition Diviner")
    assert "When this creature dies, draw a card." in chars.abilities


def test_diviner_alone_is_not_its_own_other_wizard():
    scenario = _board(["Expedition Diviner"])
    assert (
        "When this creature dies, draw a card."
        not in _chars(scenario, "Expedition Diviner").abilities
    )


# -- Deadeye Navigator / Tandem Lookout / Galvanic Alchemist: "As long as ~ is paired" ----


def _paired(partner_name, navigator, *, alice_extra=(), bob=()):
    scenario = _board([navigator, partner_name, *alice_extra], bob)
    soulbond.pair(
        scenario.game,
        scenario.find(navigator, Zone.BATTLEFIELD, "alice"),
        scenario.find(partner_name, Zone.BATTLEFIELD, "alice"),
    )
    return scenario


NAVIGATOR_LINE = "{1}{U}: Exile this creature, then return it to the battlefield under your control."
LOOKOUT_LINE = "Whenever this creature deals damage to an opponent, draw a card."
ALCHEMIST_LINE = "{2}{U}: Untap this creature."


def test_deadeye_navigator_grants_its_ability_to_both_paired_creatures():
    scenario = _paired("Grizzly Bears", "Deadeye Navigator")
    assert NAVIGATOR_LINE in _chars(scenario, "Grizzly Bears").abilities
    assert NAVIGATOR_LINE in _chars(scenario, "Deadeye Navigator").abilities
    assert scenario.game.continuous_effects.layer_notices == []


def test_deadeye_navigator_grants_nothing_while_unpaired():
    scenario = _board(["Deadeye Navigator", "Grizzly Bears"])
    assert NAVIGATOR_LINE not in _chars(scenario, "Grizzly Bears").abilities
    assert NAVIGATOR_LINE not in _chars(scenario, "Deadeye Navigator").abilities


def test_deadeye_navigator_grant_ends_when_the_pair_breaks():
    scenario = _paired("Grizzly Bears", "Deadeye Navigator")
    scenario.game.destroy(scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice"))
    assert NAVIGATOR_LINE not in _chars(scenario, "Deadeye Navigator").abilities


def test_deadeye_navigator_does_not_grant_to_an_unpaired_bystander():
    scenario = _paired("Grizzly Bears", "Deadeye Navigator", alice_extra=["Llanowar Elves"])
    assert NAVIGATOR_LINE not in _chars(scenario, "Llanowar Elves").abilities


def test_a_paired_creature_can_really_blink_itself_with_the_granted_ability():
    scenario = _paired("Grizzly Bears", "Deadeye Navigator", alice_extra=["Island", "Island"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    bears.add_counters("+1/+1")
    sources = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.activate(bears, *sources, index=0)
    scenario.pass_until_resolved()
    again = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert again is not bears or not again.counters, "it left and came back as a new object"
    assert again.counter_count("+1/+1") == 0


def test_galvanic_alchemist_grants_untap_to_both_paired_creatures():
    scenario = _paired("Grizzly Bears", "Galvanic Alchemist")
    assert ALCHEMIST_LINE in _chars(scenario, "Grizzly Bears").abilities
    assert ALCHEMIST_LINE in _chars(scenario, "Galvanic Alchemist").abilities


def test_galvanic_alchemist_untap_ability_works_on_the_partner():
    scenario = _paired("Grizzly Bears", "Galvanic Alchemist", alice_extra=["Island", "Island", "Island"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    bears.tapped = True
    sources = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.activate(bears, *sources, index=0)
    scenario.pass_until_resolved()
    assert not bears.tapped


def test_tandem_lookout_grants_a_damage_draw_trigger_to_the_pair():
    scenario = _paired("Grizzly Bears", "Tandem Lookout")
    assert LOOKOUT_LINE in _chars(scenario, "Grizzly Bears").abilities
    assert LOOKOUT_LINE in _chars(scenario, "Tandem Lookout").abilities


def test_tandem_lookout_partner_draws_when_it_hits_an_opponent():
    scenario = _paired("Grizzly Bears", "Tandem Lookout")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    bears.summoning_sick = False
    hand_before = len(scenario.player("alice").hand)
    scenario.attack_with(bears, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_tandem_lookout_unpaired_bears_draw_nothing():
    scenario = _board(["Tandem Lookout", "Grizzly Bears"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    bears.summoning_sick = False
    hand_before = len(scenario.player("alice").hand)
    scenario.attack_with(bears, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand_before


# -- Auriok Steelshaper: as long as this creature is equipped -------------------------------


def test_steelshaper_pumps_soldiers_and_knights_only_while_it_is_equipped():
    scenario = _board(["Auriok Steelshaper", "Bonesplitter", "Accorder Paladin", "Grizzly Bears"])
    assert _chars(scenario, "Accorder Paladin").power_toughness == (3, 1)
    _equip(scenario, "Bonesplitter", "Auriok Steelshaper")
    assert _chars(scenario, "Auriok Steelshaper").power_toughness == (4, 2)
    assert _chars(scenario, "Grizzly Bears").power_toughness == (2, 2)
    assert scenario.game.continuous_effects.layer_notices == []


def test_steelshaper_is_not_equipped_when_another_creature_wears_the_equipment():
    scenario = _board(["Auriok Steelshaper", "Bonesplitter", "Grizzly Bears"])
    _equip(scenario, "Bonesplitter", "Grizzly Bears")
    assert _chars(scenario, "Auriok Steelshaper").power_toughness == (1, 1)


def test_steelshaper_pump_ends_when_the_equipment_leaves():
    scenario = _board(["Auriok Steelshaper", "Bonesplitter", "Accorder Paladin"])
    _equip(scenario, "Bonesplitter", "Auriok Steelshaper")
    assert _chars(scenario, "Accorder Paladin").power_toughness == (4, 2)
    scenario.game.destroy(scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice"))
    assert _chars(scenario, "Accorder Paladin").power_toughness == (3, 1)


# -- Orochi Merge-Keeper: modified -----------------------------------------------------------


def test_orochi_merge_keeper_gets_the_double_mana_ability_when_modified_by_a_counter():
    scenario = _board(["Orochi Merge-Keeper"])
    keeper = scenario.find("Orochi Merge-Keeper", Zone.BATTLEFIELD, "alice")
    assert "{T}: Add {G}{G}." not in _chars(scenario, "Orochi Merge-Keeper").abilities
    keeper.add_counters("+1/+1")
    assert "{T}: Add {G}{G}." in _chars(scenario, "Orochi Merge-Keeper").abilities
    assert scenario.game.continuous_effects.layer_notices == []


def test_orochi_merge_keeper_is_modified_by_its_own_equipment():
    scenario = _board(["Orochi Merge-Keeper", "Bonesplitter"])
    _equip(scenario, "Bonesplitter", "Orochi Merge-Keeper")
    assert "{T}: Add {G}{G}." in _chars(scenario, "Orochi Merge-Keeper").abilities


def test_orochi_merge_keeper_is_not_modified_by_an_opponents_aura_or_counter_on_another_creature():
    scenario = _board(["Orochi Merge-Keeper", "Grizzly Bears"])
    scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").add_counters("+1/+1")
    assert "{T}: Add {G}{G}." not in _chars(scenario, "Orochi Merge-Keeper").abilities


def test_the_granted_double_mana_ability_is_a_real_activated_ability():
    scenario = _board(["Orochi Merge-Keeper"])
    keeper = scenario.find("Orochi Merge-Keeper", Zone.BATTLEFIELD, "alice")
    keeper.add_counters("+1/+1")
    assert any(
        ability.raw == "{T}: Add {G}{G}." for ability in scenario.game.activated_abilities(keeper)
    )


# -- Sedge Sliver: a quoted conditional pump granted to every Sliver ----------------------

SLIVER_PUMP = "This creature gets +1/+1 as long as you control a Swamp."


def test_sedge_sliver_grants_every_sliver_the_swamp_pump_line():
    scenario = _board(["Sedge Sliver", "Cautery Sliver", "Grizzly Bears"], ["Pulmonic Sliver"])
    for name, who in (("Sedge Sliver", "alice"), ("Cautery Sliver", "alice"), ("Pulmonic Sliver", "bob")):
        assert SLIVER_PUMP in _chars(scenario, name, who).abilities
    assert SLIVER_PUMP not in _chars(scenario, "Grizzly Bears").abilities
    assert scenario.game.continuous_effects.layer_notices == []


def test_the_slivers_pump_applies_only_to_a_sliver_whose_controller_has_a_swamp():
    scenario = _board(["Sedge Sliver", "Swamp"], ["Pulmonic Sliver"])
    assert _chars(scenario, "Sedge Sliver").power_toughness == (3, 3)
    assert _chars(scenario, "Pulmonic Sliver", "bob").power_toughness == (3, 3), "bob has no Swamp"


def test_the_slivers_pump_follows_the_swamp_in_and_out():
    scenario = _board(["Sedge Sliver", "Cautery Sliver", "Swamp"])
    assert _chars(scenario, "Cautery Sliver").power_toughness == (3, 3)
    scenario.game.destroy(scenario.find("Swamp", Zone.BATTLEFIELD, "alice"))
    assert _chars(scenario, "Cautery Sliver").power_toughness == (2, 2)
    assert _chars(scenario, "Sedge Sliver").power_toughness == (2, 2)


def test_each_slivers_pump_reads_its_own_controllers_board():
    scenario = _board(["Sedge Sliver"], ["Pulmonic Sliver", "Swamp"])
    assert _chars(scenario, "Sedge Sliver").power_toughness == (2, 2)
    assert _chars(scenario, "Pulmonic Sliver", "bob").power_toughness == (4, 4)


# -- Sardian Cliffstomper: your turn and four Mountains, +X/+0 for the Mountains ------------

MOUNTAINS = ["Mountain"] * 4


def test_cliffstomper_gets_plus_x_where_x_is_the_mountains_on_its_controllers_turn():
    scenario = _board(["Sardian Cliffstomper", *MOUNTAINS, "Mountain"])
    assert _chars(scenario, "Sardian Cliffstomper").power_toughness == (5, 4)


def test_cliffstomper_needs_four_mountains():
    scenario = _board(["Sardian Cliffstomper", "Mountain", "Mountain", "Mountain"])
    assert _chars(scenario, "Sardian Cliffstomper").power_toughness == (0, 4)


def test_cliffstomper_is_unpumped_on_the_opponents_turn_and_flips_back():
    scenario = _board(["Sardian Cliffstomper", *MOUNTAINS])
    assert _chars(scenario, "Sardian Cliffstomper").power_toughness == (4, 4)
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()
    assert scenario.game.active_player.username == "bob"
    assert _chars(scenario, "Sardian Cliffstomper").power_toughness == (0, 4)
    assert scenario.game.continuous_effects.layer_notices == []


def test_cliffstomper_counts_only_mountains_it_controls():
    scenario = _board(["Sardian Cliffstomper", "Mountain", "Mountain", "Mountain", "Forest"], ["Mountain"])
    assert _chars(scenario, "Sardian Cliffstomper").power_toughness == (0, 4)


# -- Doc Ock: another Villain gives hexproof; Bolg's Company: another Goblin gives haste ----


def test_doc_ock_has_hexproof_only_with_another_villain():
    scenario = _board(["Doc Ock, Sinister Scientist", "Doc Ock's Henchmen"])
    assert any(a.lower() == "hexproof" for a in _chars(scenario, "Doc Ock, Sinister Scientist").abilities)
    alone = _board(["Doc Ock, Sinister Scientist"])
    assert not any(a.lower() == "hexproof" for a in _chars(alone, "Doc Ock, Sinister Scientist").abilities)


def test_doc_ock_does_not_count_an_opponents_villain():
    scenario = _board(["Doc Ock, Sinister Scientist"], ["Doc Ock's Henchmen"])
    assert not any(a.lower() == "hexproof" for a in _chars(scenario, "Doc Ock, Sinister Scientist").abilities)


def test_bolgs_company_has_haste_only_while_another_goblin_is_around():
    with_goblin = _board(["Bolg's Company", "Goblin Artillery"])
    assert any(a.lower() == "haste" for a in _chars(with_goblin, "Bolg's Company").abilities)
    alone = _board(["Bolg's Company"])
    assert not any(a.lower() == "haste" for a in _chars(alone, "Bolg's Company").abilities)


# -- The World Tree: six lands give every land a mana ability -----------------------------


def test_world_tree_grants_any_color_mana_to_all_your_lands_with_six_lands():
    scenario = _board(["The World Tree", *["Forest"] * 5])
    assert "{T}: Add one mana of any color." in _chars(scenario, "The World Tree").abilities
    assert "{T}: Add one mana of any color." in _chars(scenario, "Forest").abilities


def test_world_tree_grants_nothing_with_five_lands():
    scenario = _board(["The World Tree", *["Forest"] * 4])
    assert "{T}: Add one mana of any color." not in _chars(scenario, "Forest").abilities


def test_world_tree_flips_when_a_land_is_lost_and_ignores_the_opponents_lands():
    scenario = _board(["The World Tree", *["Forest"] * 5], ["Forest"])
    assert "{T}: Add one mana of any color." in _chars(scenario, "Forest").abilities
    assert "{T}: Add one mana of any color." not in _chars(scenario, "Forest", "bob").abilities
    scenario.game.destroy(scenario.find("Forest", Zone.BATTLEFIELD, "alice"))
    assert "{T}: Add one mana of any color." not in _chars(scenario, "The World Tree").abilities


def test_world_trees_granted_mana_ability_is_activatable():
    scenario = _board(["The World Tree", *["Forest"] * 5])
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    _chars(scenario, "Forest")
    assert any(
        ability.raw == "{T}: Add one mana of any color."
        for ability in scenario.game.activated_abilities(forest)
    )


# -- Relic Vial and Oculus Whelp: a quoted triggered ability behind a board condition -------


VIAL_LINE = "Whenever a creature you control dies, each opponent loses 1 life and you gain 1 life."


def test_relic_vial_gains_its_drain_trigger_with_a_cleric():
    scenario = _board(["Relic Vial", "Voice of the Blessed"])
    assert VIAL_LINE in _chars(scenario, "Relic Vial").abilities
    alone = _board(["Relic Vial", "Grizzly Bears"])
    assert VIAL_LINE not in _chars(alone, "Relic Vial").abilities


def test_relic_vial_drains_when_a_creature_dies_only_with_a_cleric():
    scenario = _board(["Relic Vial", "Voice of the Blessed", "Grizzly Bears"])
    scenario.game.destroy(scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice"))
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21


def test_relic_vial_drain_is_off_without_a_cleric():
    scenario = _board(["Relic Vial", "Grizzly Bears"])
    scenario.game.destroy(scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice"))
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 20


WHELP_LINE = "When this creature dies, draw a card."


def test_oculus_whelp_draws_when_it_dies_only_with_a_transformed_permanent():
    plain = _board(["Oculus Whelp", "Delver of Secrets"])
    assert WHELP_LINE not in _chars(plain, "Oculus Whelp").abilities
    scenario = _board(["Oculus Whelp", "Delver of Secrets"])
    scenario.find("Delver of Secrets", Zone.BATTLEFIELD, "alice").transform()
    assert WHELP_LINE in _chars(scenario, "Oculus Whelp").abilities
    assert scenario.game.continuous_effects.layer_notices == []


def test_oculus_whelp_death_trigger_really_draws():
    scenario = _board(["Oculus Whelp", "Delver of Secrets"])
    scenario.find("Delver of Secrets", Zone.BATTLEFIELD, "alice").transform()
    hand_before = len(scenario.player("alice").hand)
    scenario.game.destroy(scenario.find("Oculus Whelp", Zone.BATTLEFIELD, "alice"))
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand_before + 1


# -- Flip and negative coverage for the earlier families ----------------------------------


def test_kolvori_loses_its_pump_when_a_legend_leaves():
    scenario = _board(["Kolvori, God of Kinship", "Kalitas, Traitor of Ghet", "Six"])
    assert _chars(scenario, "Kolvori, God of Kinship").power_toughness == (6, 6)
    scenario.game.destroy(scenario.find("Six", Zone.BATTLEFIELD, "alice"))
    assert _chars(scenario, "Kolvori, God of Kinship").power_toughness == (2, 4)
    assert not _has(_chars(scenario, "Kolvori, God of Kinship"), "Vigilance")


def test_kolvori_does_not_count_an_opponents_legends():
    scenario = _board(["Kolvori, God of Kinship"], ["Kalitas, Traitor of Ghet", "Six"])
    assert not _has(_chars(scenario, "Kolvori, God of Kinship"), "Vigilance")


def test_ogre_loses_regenerate_when_the_demon_leaves():
    scenario = _board(["Villainous Ogre", "Razorjaw Oni"])
    assert "{B}: Regenerate this creature." in _chars(scenario, "Villainous Ogre").abilities
    scenario.game.destroy(scenario.find("Razorjaw Oni", Zone.BATTLEFIELD, "alice"))
    assert "{B}: Regenerate this creature." not in _chars(scenario, "Villainous Ogre").abilities


def test_diviner_loses_its_ability_when_the_other_wizard_leaves():
    scenario = _board(["Expedition Diviner", "Fugitive Wizard"])
    assert "When this creature dies, draw a card." in _chars(scenario, "Expedition Diviner").abilities
    scenario.game.destroy(scenario.find("Fugitive Wizard", Zone.BATTLEFIELD, "alice"))
    assert "When this creature dies, draw a card." not in _chars(scenario, "Expedition Diviner").abilities


def test_hundred_battle_veteran_needs_different_kinds_not_more_counters():
    scenario = _board(["Hundred-Battle Veteran", "Grizzly Bears"])
    scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").add_counters("+1/+1", 5)
    scenario.find("Hundred-Battle Veteran", Zone.BATTLEFIELD, "alice").add_counters("+1/+1", 5)
    assert _chars(scenario, "Hundred-Battle Veteran").power_toughness == (9, 7)


def test_hundred_battle_veteran_ignores_an_opponents_counters():
    scenario = _board(["Hundred-Battle Veteran"], ["Grizzly Bears", "Llanowar Elves"])
    scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").add_counters("+1/+1")
    scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "bob").add_counters("flying")
    scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "bob").add_counters("deathtouch")
    assert _chars(scenario, "Hundred-Battle Veteran").power_toughness == (4, 2)


# -- Ray of Frost: as long as enchanted creature is red, it loses all abilities -----------


def _ray(target, *, bob=()):
    scenario = _board(["Ray of Frost", target], bob)
    scenario.find("Ray of Frost", Zone.BATTLEFIELD, "alice").attach_to(
        scenario.find(target, Zone.BATTLEFIELD, "alice")
    )
    return scenario


def test_ray_of_frost_strips_all_abilities_from_a_red_creature():
    scenario = _ray("Goblin Artillery")
    assert not any("2 damage" in line for line in _chars(scenario, "Goblin Artillery").abilities)
    assert scenario.game.activated_abilities(scenario.find("Goblin Artillery", Zone.BATTLEFIELD, "alice")) == []
    assert scenario.game.continuous_effects.layer_notices == []


def test_ray_of_frost_leaves_a_nonred_creature_alone():
    scenario = _ray("Llanowar Elves")
    assert "{T}: Add {G}." in _chars(scenario, "Llanowar Elves").abilities
    assert scenario.game.activated_abilities(scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice"))


def test_ray_of_frost_moving_to_a_nonred_creature_restores_the_red_ones_abilities():
    scenario = _board(["Ray of Frost", "Goblin Artillery", "Llanowar Elves"])
    ray = scenario.find("Ray of Frost", Zone.BATTLEFIELD, "alice")
    artillery = scenario.find("Goblin Artillery", Zone.BATTLEFIELD, "alice")
    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    ray.attach_to(artillery)
    assert scenario.game.activated_abilities(artillery) == []
    ray.attach_to(elves)
    assert scenario.game.activated_abilities(artillery)
    assert "{T}: Add {G}." in _chars(scenario, "Llanowar Elves").abilities


# -- Anax, Hardened in the Forge: a Satyr token with a quoted can't-block line -----------

ANAX = "Anax, Hardened in the Forge"


def _satyrs(scenario, username="alice"):
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if "Satyr" in state.subtypes
    ]


def _die_and_resolve(scenario, name, username="alice"):
    scenario.game.destroy(scenario.find(name, Zone.BATTLEFIELD, username))
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def test_anax_dying_creature_makes_one_satyr_that_cannot_block():
    scenario = _board([ANAX, "Grizzly Bears"])
    _die_and_resolve(scenario, "Grizzly Bears")
    (satyr,) = _satyrs(scenario)
    assert satyr.power == 1 and satyr.toughness == 1
    assert "This token can't block." in scenario.game.characteristics_of(satyr).abilities
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_anax_makes_two_satyrs_when_the_dying_creature_had_power_four_or_more():
    scenario = _board([ANAX, "Craw Wurm"])
    _die_and_resolve(scenario, "Craw Wurm")
    assert len(_satyrs(scenario)) == 2


def test_anax_itself_dying_also_makes_a_satyr():
    scenario = _board([ANAX])
    _die_and_resolve(scenario, ANAX)
    assert len(_satyrs(scenario)) == 1


def test_anax_ignores_an_opponents_creature_dying():
    scenario = _board([ANAX], ["Grizzly Bears"])
    _die_and_resolve(scenario, "Grizzly Bears", "bob")
    assert _satyrs(scenario) == []


def test_a_satyr_token_dying_does_not_make_more_satyrs():
    scenario = _board([ANAX, "Grizzly Bears"])
    _die_and_resolve(scenario, "Grizzly Bears")
    (satyr,) = _satyrs(scenario)
    scenario.game.destroy(satyr)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert _satyrs(scenario) == []


def test_the_satyr_really_cannot_block():
    scenario = _board([ANAX, "Grizzly Bears"], ["Hill Giant"])
    _die_and_resolve(scenario, "Grizzly Bears")
    (satyr,) = _satyrs(scenario)
    _next_turn(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    giant.summoning_sick = False
    scenario.attack_with(giant, defending="alice")
    with pytest.raises(ValueError, match="block"):
        scenario.block(giant, satyr)


# -- Cloud, Midgar Mercenary: equipped, so triggers of Cloud or its Equipment double -------

CLOUD = "Cloud, Midgar Mercenary"


def _attack_trigger_damage(scenario, attacker_name):
    """Attack bob with `attacker_name` and resolve its triggers; return bob's life
    lost before combat damage."""
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attacker = scenario.find(attacker_name, Zone.BATTLEFIELD, "alice")
    attacker.summoning_sick = False
    scenario.attack_with(attacker, defending="bob")
    scenario.game.put_triggers_on_stack()
    triggers = len(scenario.game.stack)
    while scenario.game.stack:
        scenario.resolve_top()
    return triggers, 20 - scenario.player("bob").life


def test_cloud_equipped_triggers_an_equipments_attack_trigger_an_additional_time():
    scenario = _board([CLOUD, "Mage Slayer"])
    _equip(scenario, "Mage Slayer", CLOUD)
    triggers, lost = _attack_trigger_damage(scenario, CLOUD)
    assert triggers == 2
    assert lost == 4
    assert scenario.game.continuous_effects.layer_notices == []


def test_an_unequipped_cloud_multiplies_nothing():
    scenario = _board([CLOUD, "Mage Slayer", "Grizzly Bears"])
    _equip(scenario, "Mage Slayer", "Grizzly Bears")
    triggers, lost = _attack_trigger_damage(scenario, "Grizzly Bears")
    assert triggers == 1
    assert lost == 2


def test_cloud_does_not_multiply_the_triggers_of_equipment_on_another_creature():
    scenario = _board([CLOUD, "Bonesplitter", "Mage Slayer", "Grizzly Bears"])
    _equip(scenario, "Bonesplitter", CLOUD)
    _equip(scenario, "Mage Slayer", "Grizzly Bears")
    triggers, lost = _attack_trigger_damage(scenario, "Grizzly Bears")
    assert triggers == 1
    assert lost == 2


def test_cloud_stops_multiplying_when_the_equipment_moves_to_another_creature():
    scenario = _board([CLOUD, "Mage Slayer", "Grizzly Bears"])
    _equip(scenario, "Mage Slayer", CLOUD)
    _equip(scenario, "Mage Slayer", "Grizzly Bears")
    triggers, _lost = _attack_trigger_damage(scenario, "Grizzly Bears")
    assert triggers == 1
