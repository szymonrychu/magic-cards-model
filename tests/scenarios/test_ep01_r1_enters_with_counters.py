"""Scenario: "[This] enters with <counters>" lines that are not gated on a cast
fact - counted ("for each"), typed (-1/-1), and the group replacement "Each
<group> you control enters with an additional <counter>" (EP-01 round 1, T1).

- **CR 614.1c** - "[This permanent] enters with . . . ," is a replacement
  effect; an effect of another permanent can add counters to the entering
  object the same way (the group form).
- **CR 614.12** - the replacement is judged on the permanent as it would exist
  on the battlefield, so the entering creature's own subtypes decide a group.
- **CR 122.6** - counters a permanent "enters with" are put on it as it enters.
- **CR 700.4** - "dies" counts a creature put into a graveyard from the
  battlefield (Bloodcrazed Paladin counts them).

Every number was looked up with `mise run rules:find <n>`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import create_predefined_tokens

from .harness import Scenario


def _board(**kwargs):
    scenario = Scenario().manual_turn_based_actions().player("alice", **kwargs).player("bob")
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    return played


def test_dragonstorm_globe_adds_a_counter_to_a_dragon_entering():
    played = _board(battlefield=["Dragonstorm Globe"], hand=["Hellkite Whelp"])
    whelp = played.put_onto_battlefield("Hellkite Whelp")
    assert whelp.counters[Counter.PLUS_ONE] == 1


def test_dragonstorm_globe_ignores_a_non_dragon():
    played = _board(battlefield=["Dragonstorm Globe"], hand=["Elvish Warrior"])
    warrior = played.put_onto_battlefield("Elvish Warrior")
    assert warrior.counters[Counter.PLUS_ONE] == 0


def test_dragonstorm_globe_does_not_help_an_opponents_dragon():
    scenario = Scenario().manual_turn_based_actions()
    scenario.player("alice", battlefield=["Dragonstorm Globe"]).player(
        "bob", hand=["Hellkite Whelp"]
    )
    opp = scenario.build()
    opp.start_at(Step.PRECOMBAT_MAIN)
    whelp = opp.put_onto_battlefield("Hellkite Whelp", "bob")
    assert whelp.counters[Counter.PLUS_ONE] == 0


def test_bramblewood_paragon_helps_other_warriors_but_not_itself():
    played = _board(hand=["Bramblewood Paragon", "Elvish Warrior"])
    paragon = played.put_onto_battlefield("Bramblewood Paragon")
    assert paragon.counters[Counter.PLUS_ONE] == 0
    warrior = played.put_onto_battlefield("Elvish Warrior")
    assert warrior.counters[Counter.PLUS_ONE] == 1


def test_oath_of_gideon_adds_a_loyalty_counter_to_a_planeswalker():
    played = _board(battlefield=["Oath of Gideon"], hand=["Jace Beleren"])
    jace = played.put_onto_battlefield("Jace Beleren")
    printed = int(jace.card.loyalty)
    assert jace.counters["loyalty"] == printed + 1


def test_squad_captain_counts_each_other_creature_you_control():
    played = _board(battlefield=["Elvish Warrior", "Goblin Piker"], hand=["Squad Captain"])
    captain = played.put_onto_battlefield("Squad Captain")
    assert captain.counters[Counter.PLUS_ONE] == 2


def test_squad_captain_alone_enters_with_no_counters():
    played = _board(hand=["Squad Captain"])
    captain = played.put_onto_battlefield("Squad Captain")
    assert captain.counters[Counter.PLUS_ONE] == 0


def test_hamlet_vanguard_counts_two_per_other_nontoken_human():
    played = _board(battlefield=["Elite Vanguard", "Youthful Knight"], hand=["Hamlet Vanguard"])
    vanguard = played.put_onto_battlefield("Hamlet Vanguard")
    assert vanguard.counters[Counter.PLUS_ONE] == 4


def test_bloodcrazed_paladin_counts_creatures_that_died_this_turn():
    played = _board(hand=["Bloodcrazed Paladin"])
    played.game.creatures_died_this_turn = 3
    paladin = played.put_onto_battlefield("Bloodcrazed Paladin")
    assert paladin.counters[Counter.PLUS_ONE] == 3


def test_patched_plaything_cast_from_hand_enters_with_two_minus_counters():
    played = _board(hand=["Patched Plaything"], battlefield=["Plains", "Forest", "Forest"])
    thing = played.cast_and_resolve("Patched Plaything", auto=True)
    assert thing.zone is Zone.BATTLEFIELD
    assert thing.counters[Counter.MINUS_ONE] == 2


def test_patched_plaything_put_onto_the_battlefield_has_none():
    played = _board(hand=["Patched Plaything"])
    thing = played.put_onto_battlefield("Patched Plaything")
    assert thing.counters[Counter.MINUS_ONE] == 0


# -- "enters tapped with <counters>" (CR 614.1c, CR 614.1d) -------------------


def test_vivid_marsh_enters_tapped_with_two_charge_counters():
    played = _board(hand=["Vivid Marsh"])
    land = played.put_onto_battlefield("Vivid Marsh")
    assert land.tapped
    assert land.counters[Counter.CHARGE] == 2


def test_vivid_crag_enters_tapped_with_two_charge_counters():
    played = _board(hand=["Vivid Crag"])
    land = played.play_land("Vivid Crag")
    assert land.tapped
    assert land.counters[Counter.CHARGE] == 2


def test_steel_dromedary_enters_tapped_with_two_plus_counters():
    played = _board(hand=["Steel Dromedary"])
    camel = played.put_onto_battlefield("Steel Dromedary")
    assert camel.tapped
    assert camel.counters[Counter.PLUS_ONE] == 2


def test_stun_counters_ride_the_tapped_entry():
    for name, count in (
        ("Tonberry", 1),
        ("Sleep-Cursed Faerie", 3),
        ("The Watcher in the Water", 9),
    ):
        played = _board(hand=[name])
        creature = played.put_onto_battlefield(name)
        assert creature.tapped, name
        assert creature.counters[Counter.STUN] == count, name


# -- "enters with your choice of a <kind> counter or a <kind> counter" ---------
# CR 614.12a: the choice is made before the permanent enters.


def _entered_choosing(name, *answers):
    played = _board(hand=[name])
    for answer in answers:
        played.will_choose(answer, source=name)
    return played.put_onto_battlefield(name)


def test_boot_nipper_takes_the_chosen_keyword_counter():
    lifelink = _entered_choosing("Boot Nipper", "lifelink")
    assert lifelink.counters["lifelink"] == 1
    assert lifelink.counters["deathtouch"] == 0
    deathtouch = _entered_choosing("Boot Nipper", "deathtouch")
    assert deathtouch.counters["deathtouch"] == 1
    assert deathtouch.counters["lifelink"] == 0


def test_each_other_choice_card_gives_exactly_the_picked_counter():
    for name, picked, other in (
        ("Ferocious Tigorilla", "menace", "trample"),
        ("Flycatcher Giraffid", "vigilance", "reach"),
        ("Helica Glider", "first strike", "flying"),
        ("Wingfold Pteron", "hexproof", "flying"),
    ):
        creature = _entered_choosing(name, picked)
        assert creature.counters[picked] == 1, name
        assert creature.counters[other] == 0, name


def test_grimdancer_takes_two_different_counters():
    creature = _entered_choosing("Grimdancer", "menace", "lifelink")
    assert creature.counters["menace"] == 1
    assert creature.counters["lifelink"] == 1
    assert creature.counters["deathtouch"] == 0


def test_grimdancer_refuses_the_same_counter_twice():
    played = _board(hand=["Grimdancer"])
    played.will_choose("menace", source="Grimdancer", times=2)
    with pytest.raises(ValueError):
        played.put_onto_battlefield("Grimdancer")


def test_a_choice_answer_outside_the_printed_options_is_refused():
    played = _board(hand=["Boot Nipper"])
    played.will_choose("flying", source="Boot Nipper")
    with pytest.raises(ValueError):
        played.put_onto_battlefield("Boot Nipper")


def test_avatar_of_the_resolute_counts_other_creatures_with_a_plus_counter():
    played = _board(
        battlefield=["Elvish Warrior", "Goblin Piker", "Squad Captain"],
        hand=["Avatar of the Resolute"],
    )
    for name in ("Elvish Warrior", "Goblin Piker"):
        played.game.add_counters(played.creature(name), Counter.PLUS_ONE, 1)
    avatar = played.put_onto_battlefield("Avatar of the Resolute")
    assert avatar.counters[Counter.PLUS_ONE] == 2


def test_avatar_of_the_resolute_alone_enters_bare():
    played = _board(hand=["Avatar of the Resolute"])
    assert played.put_onto_battlefield("Avatar of the Resolute").counters[Counter.PLUS_ONE] == 0


# -- more group replacements (CR 614.1c, CR 614.12) ----------------------------


def test_metallic_mimic_buffs_other_creatures_of_the_chosen_type_only():
    played = _board(hand=["Metallic Mimic", "Elvish Warrior", "Goblin Piker"])
    played.will_choose("Elf", source="Metallic Mimic")
    played.put_onto_battlefield("Metallic Mimic")
    assert played.put_onto_battlefield("Elvish Warrior").counters[Counter.PLUS_ONE] == 1
    assert played.put_onto_battlefield("Goblin Piker").counters[Counter.PLUS_ONE] == 0


def test_thunderous_velocipede_gives_one_counter_at_mana_value_four_or_less():
    played = _board(
        battlefield=["Thunderous Velocipede"], hand=["Grizzly Bears", "Smuggler's Copter"]
    )
    assert played.put_onto_battlefield("Grizzly Bears").counters[Counter.PLUS_ONE] == 1
    assert played.put_onto_battlefield("Smuggler's Copter").counters[Counter.PLUS_ONE] == 1


def test_thunderous_velocipede_gives_three_counters_above_mana_value_four():
    played = _board(battlefield=["Thunderous Velocipede"], hand=["Cultivator Colossus"])
    assert played.put_onto_battlefield("Cultivator Colossus").counters[Counter.PLUS_ONE] == 3


def test_mysterious_pathlighter_buffs_creatures_with_an_adventure_only():
    played = _board(
        battlefield=["Mysterious Pathlighter"], hand=["Bonecrusher Giant", "Grizzly Bears"]
    )
    assert played.put_onto_battlefield("Bonecrusher Giant").counters[Counter.PLUS_ONE] == 1
    assert played.put_onto_battlefield("Grizzly Bears").counters[Counter.PLUS_ONE] == 0


# -- board and zone counts ("for each", "equal to", CR 614.1c) -------------------


def _two_sided(alice, bob=None):
    scenario = Scenario().manual_turn_based_actions().player("alice", **alice)
    scenario.player("bob", **(bob or {}))
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    return played


def test_luxknight_breacher_counts_other_creatures_and_artifacts():
    played = _board(
        battlefield=["Grizzly Bears", "Mishra's Bauble", "Plains"], hand=["Luxknight Breacher"]
    )
    assert played.put_onto_battlefield("Luxknight Breacher").counters[Counter.PLUS_ONE] == 2


def test_sheriff_of_safe_passage_gets_one_plus_one_per_other_creature():
    played = _board(
        battlefield=["Grizzly Bears", "Elvish Warrior"], hand=["Sheriff of Safe Passage"]
    )
    assert played.put_onto_battlefield("Sheriff of Safe Passage").counters[Counter.PLUS_ONE] == 3


def test_ulasht_counts_other_red_creatures_and_other_green_creatures_separately():
    played = _board(battlefield=["Goblin Piker", "Grizzly Bears"], hand=["Ulasht, the Hate Seed"])
    assert played.put_onto_battlefield("Ulasht, the Hate Seed").counters[Counter.PLUS_ONE] == 2


def test_ulasht_alone_enters_bare():
    played = _board(hand=["Ulasht, the Hate Seed"])
    assert played.put_onto_battlefield("Ulasht, the Hate Seed").counters[Counter.PLUS_ONE] == 0


def test_kinsbaile_borderguard_counts_other_kithkin():
    played = _board(
        battlefield=["Kithkin Billyrider", "Zealous Guardian", "Grizzly Bears"],
        hand=["Kinsbaile Borderguard"],
    )
    assert played.put_onto_battlefield("Kinsbaile Borderguard").counters[Counter.PLUS_ONE] == 2


def test_grizzly_ghoul_counts_creatures_that_died_this_turn():
    played = _board(hand=["Grizzly Ghoul"])
    played.game.creatures_died_this_turn = 2
    assert played.put_onto_battlefield("Grizzly Ghoul").counters[Counter.PLUS_ONE] == 2


@pytest.mark.parametrize("name", ["Frilled Sparkshooter", "Mounted Dreadknight"])
def test_an_opponent_losing_life_this_turn_gates_the_counter(name):
    lost = _board(hand=[name])
    lost.game.player("bob").lose_life(1)
    assert lost.put_onto_battlefield(name).counters[Counter.PLUS_ONE] == 1
    bare = _board(hand=[name])
    assert bare.put_onto_battlefield(name).counters[Counter.PLUS_ONE] == 0


def test_heir_of_the_ancient_fang_needs_a_modified_creature():
    played = _board(battlefield=["Grizzly Bears"], hand=["Heir of the Ancient Fang"])
    played.game.add_counters(played.creature("Grizzly Bears"), Counter.PLUS_ONE, 1)
    assert played.put_onto_battlefield("Heir of the Ancient Fang").counters[Counter.PLUS_ONE] == 1
    bare = _board(battlefield=["Grizzly Bears"], hand=["Heir of the Ancient Fang"])
    assert bare.put_onto_battlefield("Heir of the Ancient Fang").counters[Counter.PLUS_ONE] == 0


def test_storm_entity_counts_the_other_spells_cast_this_turn():
    played = _board(hand=["Lightning Bolt", "Storm Entity"], battlefield=["Mountain"] * 3)
    played.cast_and_resolve("Lightning Bolt", targets=["bob"], auto=True)
    assert played.cast_and_resolve("Storm Entity", auto=True).counters[Counter.PLUS_ONE] == 1


def test_embodiment_of_agonies_counts_different_mana_costs_in_the_graveyard():
    played = _board(
        hand=["Embodiment of Agonies"],
        graveyard=["Lightning Bolt", "Shock", "Giant Growth", "Forest"],
    )
    assert played.put_onto_battlefield("Embodiment of Agonies").counters[Counter.PLUS_ONE] == 2


def test_undergrowth_scavenger_counts_creature_cards_in_all_graveyards():
    played = _two_sided(
        {"hand": ["Undergrowth Scavenger"], "graveyard": ["Grizzly Bears", "Elvish Warrior"]},
        {"graveyard": ["Goblin Piker", "Lightning Bolt"]},
    )
    assert played.put_onto_battlefield("Undergrowth Scavenger").counters[Counter.PLUS_ONE] == 3


def test_aeve_counts_the_other_oozes_you_control():
    played = _board(
        battlefield=["Scavenging Ooze", "Corrosive Ooze"], hand=["Aeve, Progenitor Ooze"]
    )
    assert played.put_onto_battlefield("Aeve, Progenitor Ooze").counters[Counter.PLUS_ONE] == 2


def test_dakkon_enters_with_a_loyalty_counter_per_land_you_control():
    played = _board(battlefield=["Plains"] * 4, hand=["Dakkon, Shadow Slayer"])
    assert played.put_onto_battlefield("Dakkon, Shadow Slayer").counters["loyalty"] == 4


def test_investigators_journal_uses_the_greatest_creature_count_of_any_player():
    played = _two_sided(
        {"hand": ["Investigator's Journal"], "battlefield": ["Grizzly Bears"]},
        {"battlefield": ["Grizzly Bears", "Elvish Warrior", "Goblin Piker"]},
    )
    assert played.put_onto_battlefield("Investigator's Journal").counters["suspect"] == 3


def test_bioessence_hydra_counts_loyalty_counters_on_your_planeswalkers():
    played = _board(battlefield=["Jace Beleren"], hand=["Bioessence Hydra"])
    loyalty = played.creature("Jace Beleren").counters["loyalty"] if False else None
    jace = next(
        p for p in played.game.permanents_controlled_by("alice") if p.name == "Jace Beleren"
    )
    hydra = played.put_onto_battlefield("Bioessence Hydra")
    assert hydra.counters[Counter.PLUS_ONE] == jace.counters["loyalty"]
    assert loyalty is None


@pytest.mark.parametrize("name", ["Vivid Creek", "Vivid Grove", "Vivid Meadow"])
def test_every_vivid_land_enters_tapped_with_two_charge_counters(name):
    played = _board(hand=[name])
    land = played.put_onto_battlefield(name)
    assert land.tapped
    assert land.counters[Counter.CHARGE] == 2


def test_banner_of_kinship_counts_creatures_of_the_chosen_type():
    played = _board(battlefield=["Elvish Warrior", "Elvish Warrior"], hand=["Banner of Kinship"])
    played.will_choose("Elf", source="Banner of Kinship")
    assert played.put_onto_battlefield("Banner of Kinship").counters["fellowship"] == 2


def test_canker_abomination_counts_the_chosen_opponents_creatures():
    played = _two_sided(
        {"hand": ["Canker Abomination"]},
        {"battlefield": ["Grizzly Bears", "Elvish Warrior"]},
    )
    played.will_choose("bob", source="Canker Abomination")
    assert played.put_onto_battlefield("Canker Abomination").counters[Counter.MINUS_ONE] == 2


# -- group replacements, one more card for every shape (CR 614.1c, CR 614.12) ---


def test_gev_gives_a_counter_per_opponent_who_lost_life():
    lost = _board(battlefield=["Gev, Scaled Scorch"], hand=["Grizzly Bears"])
    lost.game.player("bob").lose_life(1)
    assert lost.put_onto_battlefield("Grizzly Bears").counters[Counter.PLUS_ONE] == 1
    bare = _board(battlefield=["Gev, Scaled Scorch"], hand=["Grizzly Bears"])
    assert bare.put_onto_battlefield("Grizzly Bears").counters[Counter.PLUS_ONE] == 0


def test_kalain_gives_a_counter_per_treasure_mana_spent_to_cast_the_creature():
    played = _board(battlefield=["Kalain, Reclusive Painter", "Forest"], hand=["Grizzly Bears"])
    (treasure,) = create_predefined_tokens(played.game, "Treasure", "alice")
    played.game.activate_ability(treasure, 0, "alice", color=Color.GREEN)
    bears = played.cast_and_resolve("Grizzly Bears", auto=True)
    assert bears.counters[Counter.PLUS_ONE] == 1


def test_kalain_gives_nothing_for_a_creature_not_paid_with_a_treasure():
    played = _board(
        battlefield=["Kalain, Reclusive Painter", "Forest", "Forest"], hand=["Grizzly Bears"]
    )
    assert played.cast_and_resolve("Grizzly Bears", auto=True).counters[Counter.PLUS_ONE] == 0


def test_giada_counts_the_angels_you_already_control():
    played = _board(battlefield=["Giada, Font of Hope"], hand=["Serra Angel"])
    assert played.put_onto_battlefield("Serra Angel").counters[Counter.PLUS_ONE] == 1


def test_grumgully_helps_a_non_human_and_not_a_human():
    played = _board(
        battlefield=["Grumgully, the Generous"], hand=["Elvish Warrior", "Elite Vanguard"]
    )
    assert played.put_onto_battlefield("Elvish Warrior").counters[Counter.PLUS_ONE] == 1
    assert played.put_onto_battlefield("Elite Vanguard").counters[Counter.PLUS_ONE] == 0


def test_oonas_blackguard_helps_another_rogue_only():
    played = _board(battlefield=["Oona's Blackguard"], hand=["Krovikan Scoundrel", "Grizzly Bears"])
    assert played.put_onto_battlefield("Krovikan Scoundrel").counters[Counter.PLUS_ONE] == 1
    assert played.put_onto_battlefield("Grizzly Bears").counters[Counter.PLUS_ONE] == 0


def test_sage_of_fables_helps_another_wizard_only():
    played = _board(battlefield=["Sage of Fables"], hand=["Fugitive Wizard", "Grizzly Bears"])
    assert played.put_onto_battlefield("Fugitive Wizard").counters[Counter.PLUS_ONE] == 1
    assert played.put_onto_battlefield("Grizzly Bears").counters[Counter.PLUS_ONE] == 0


def test_arlinn_voice_of_the_pack_helps_a_wolf_and_not_a_bear():
    played = _board(battlefield=["Arlinn, Voice of the Pack"], hand=["Watchwolf", "Grizzly Bears"])
    assert played.put_onto_battlefield("Watchwolf").counters[Counter.PLUS_ONE] == 1
    assert played.put_onto_battlefield("Grizzly Bears").counters[Counter.PLUS_ONE] == 0


def test_bard_class_helps_a_legendary_creature_only():
    played = _board(battlefield=["Bard Class"], hand=["Isamaru, Hound of Konda", "Grizzly Bears"])
    assert played.put_onto_battlefield("Isamaru, Hound of Konda").counters[Counter.PLUS_ONE] == 1
    assert played.put_onto_battlefield("Grizzly Bears").counters[Counter.PLUS_ONE] == 0


def test_bioengineered_future_counts_the_lands_that_entered_this_turn():
    played = _board(battlefield=["Bioengineered Future"], hand=["Forest", "Grizzly Bears"])
    played.play_land("Forest")
    assert played.put_onto_battlefield("Grizzly Bears").counters[Counter.PLUS_ONE] == 1


def test_bioengineered_future_with_no_land_this_turn_adds_nothing():
    played = _board(battlefield=["Bioengineered Future"], hand=["Grizzly Bears"])
    assert played.put_onto_battlefield("Grizzly Bears").counters[Counter.PLUS_ONE] == 0


def test_renata_gives_another_creature_a_counter_but_not_herself():
    played = _board(hand=["Renata, Called to the Hunt", "Grizzly Bears"])
    renata = played.put_onto_battlefield("Renata, Called to the Hunt")
    assert renata.counters[Counter.PLUS_ONE] == 0
    assert played.put_onto_battlefield("Grizzly Bears").counters[Counter.PLUS_ONE] == 1


# -- escape: "escapes with <counters>" (CR 702.138, CR 614.1c) -----------------

ESCAPE_ROWS = [
    ("Phoenix of Ash", ["Mountain"] * 4, 3, Counter.PLUS_ONE, 1),
    ("Ox of Agonas", ["Mountain"] * 2, 8, Counter.PLUS_ONE, 1),
    ("Underworld Charger", ["Swamp"] * 5, 3, Counter.PLUS_ONE, 2),
    ("Woe Strider", ["Swamp"] * 5, 4, Counter.PLUS_ONE, 2),
    ("Chainweb Aracnir", ["Forest"] * 5, 4, Counter.PLUS_ONE, 3),
    ("Pharika's Spawn", ["Swamp"] * 6, 3, Counter.PLUS_ONE, 2),
    ("Voracious Typhon", ["Forest"] * 7, 4, Counter.PLUS_ONE, 3),
    ("Loathsome Chimera", ["Forest"] * 5, 3, Counter.PLUS_ONE, 1),
    ("Underworld Rage-Hound", ["Mountain"] * 4, 3, Counter.PLUS_ONE, 1),
]


def _escape(name, lands, fuel, *answers):
    played = _board(graveyard=[name, *["Mishra's Bauble"] * fuel], battlefield=lands, hand=[])
    for answer in answers:
        played.will_choose(answer, source=name)
    exiled = [c for c in played.game.player("alice").graveyard if c.name != name]
    casting = played.cast(name, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=exiled)
    played.auto_pay(casting.begin_paying(), username="alice")
    played.put_on_stack(casting)
    return played.resolve_top()


@pytest.mark.parametrize("name,lands,fuel,kind,expected", ESCAPE_ROWS)
def test_a_card_cast_with_escape_enters_with_its_counters(name, lands, fuel, kind, expected):
    assert _escape(name, lands, fuel).counters[kind] == expected


@pytest.mark.parametrize("name,lands,fuel,kind,expected", ESCAPE_ROWS)
def test_the_same_card_cast_from_hand_enters_without_them(name, lands, fuel, kind, expected):
    played = _board(hand=[name], battlefield=["Mountain", "Swamp", "Forest"] * 4)
    assert played.cast_and_resolve(name, auto=True).counters[kind] == 0


def test_tizerus_charger_escapes_with_the_chosen_plus_counter():
    charger = _escape("Tizerus Charger", ["Swamp"] * 5, 5, "+1/+1")
    assert charger.counters[Counter.PLUS_ONE] == 1
    assert charger.counters["flying"] == 0


def test_tizerus_charger_escapes_with_the_chosen_flying_counter():
    charger = _escape("Tizerus Charger", ["Swamp"] * 5, 5, "flying")
    assert charger.counters["flying"] == 1
    assert charger.counters[Counter.PLUS_ONE] == 0


def test_tizerus_charger_cast_from_hand_has_neither_counter():
    played = _board(hand=["Tizerus Charger"], battlefield=["Swamp"] * 3)
    charger = played.cast_and_resolve("Tizerus Charger", auto=True)
    assert charger.counters["flying"] == 0
    assert charger.counters[Counter.PLUS_ONE] == 0


# -- second printings: the same readers on cards the task did not list ----------
# (Modern/Pioneer/Standard-legal, in no shipped deck), so each reader is
# proven general rather than fitted to one printing.


def _cast_x_spell(played, name, x):
    card = played.find(name, Zone.HAND, "alice")
    lands = [p for p in played.game.permanents_controlled_by("alice") if "Land" in p.card.type_line]
    played.game.cast(card, "alice", x_value=x, mana_sources=lands)
    return played.resolve_top()


def test_ochre_jelly_enters_with_x_counters_like_every_x_creature():
    played = _board(hand=["Ochre Jelly"], battlefield=["Forest"] * 4)
    assert _cast_x_spell(played, "Ochre Jelly", 3).counters[Counter.PLUS_ONE] == 3


def test_slumbering_trudge_stuns_and_taps_at_a_low_x():
    played = _board(hand=["Slumbering Trudge"], battlefield=["Forest"] * 3)
    trudge = _cast_x_spell(played, "Slumbering Trudge", 1)
    assert trudge.counters[Counter.STUN] == 2
    assert trudge.tapped


def test_slumbering_trudge_at_a_high_x_enters_untapped_with_no_stun():
    played = _board(hand=["Slumbering Trudge"], battlefield=["Forest"] * 4)
    trudge = _cast_x_spell(played, "Slumbering Trudge", 3)
    assert trudge.counters[Counter.STUN] == 0
    assert not trudge.tapped


def test_prime_speaker_zegana_takes_the_greatest_power_among_other_creatures():
    played = _board(battlefield=["Grizzly Bears", "Craw Wurm"], hand=["Prime Speaker Zegana"])
    assert played.put_onto_battlefield("Prime Speaker Zegana").counters[Counter.PLUS_ONE] == 6


def test_cryptborn_horror_counts_the_life_opponents_lost_this_turn():
    played = _board(hand=["Cryptborn Horror"])
    played.game.player("bob").lose_life(3)
    assert played.put_onto_battlefield("Cryptborn Horror").counters[Counter.PLUS_ONE] == 3


def test_voracious_wurm_counts_the_life_you_gained_this_turn():
    played = _board(hand=["Voracious Wurm"])
    played.game.life_gained_amount_this_turn["alice"] = 4
    assert played.put_onto_battlefield("Voracious Wurm").counters[Counter.PLUS_ONE] == 4


@pytest.mark.parametrize("name", ["Rhizome Lurcher", "Golgari Raiders"])
def test_undergrowth_counts_creature_cards_in_your_graveyard(name):
    played = _board(hand=[name], graveyard=["Grizzly Bears", "Elvish Warrior", "Lightning Bolt"])
    assert played.put_onto_battlefield(name).counters[Counter.PLUS_ONE] == 2


def test_gatekeeper_gargoyle_counts_the_gates_you_control():
    played = _board(battlefield=["Azorius Guildgate"], hand=["Gatekeeper Gargoyle"])
    assert played.put_onto_battlefield("Gatekeeper Gargoyle").counters[Counter.PLUS_ONE] == 1


def test_springmantle_cleric_counts_the_colours_of_mana_spent():
    played = _board(hand=["Springmantle Cleric"], battlefield=["Forest"] * 4 + ["Plains"])
    assert played.cast_and_resolve("Springmantle Cleric", auto=True).counters[Counter.PLUS_ONE] == 2


def test_callous_sell_sword_counts_creatures_that_died_under_your_control():
    played = _board(
        hand=["Callous Sell-Sword"],
        battlefield=["Grizzly Bears", "Mountain"],
    )
    played.game.destroy(played.creature("Grizzly Bears"))
    assert played.put_onto_battlefield("Callous Sell-Sword").counters[Counter.PLUS_ONE] == 1


def test_polukranos_unchained_enters_with_six_and_escapes_with_twelve():
    plain = _board(hand=["Polukranos, Unchained"])
    assert plain.put_onto_battlefield("Polukranos, Unchained").counters[Counter.PLUS_ONE] == 6
    escaped = _escape("Polukranos, Unchained", ["Swamp"] * 5 + ["Forest"], 6)
    assert escaped.counters[Counter.PLUS_ONE] == 12


def test_callous_sell_sword_ignores_creatures_that_died_under_an_opponents_control():
    played = _two_sided({"hand": ["Callous Sell-Sword"]}, {"battlefield": ["Grizzly Bears"]})
    played.game.destroy(played.game.permanents_controlled_by("bob")[0])
    assert played.put_onto_battlefield("Callous Sell-Sword").counters[Counter.PLUS_ONE] == 0


def test_unbreathing_horde_counts_other_zombies_and_zombie_cards_in_the_graveyard():
    played = _board(
        battlefield=["Rhizome Lurcher"],
        graveyard=["Rhizome Lurcher", "Grizzly Bears"],
        hand=["Unbreathing Horde"],
    )
    assert played.put_onto_battlefield("Unbreathing Horde").counters[Counter.PLUS_ONE] == 2
