"""Scenario: "[This] enters with <counters>" lines gated on a fact - kicker,
raid, adamant, board state, an opponent losing life, an "unless" (EP-01 round 1,
T1). Each gate is asserted both true and false.

- **CR 614.1c** - "[This permanent] enters with . . ." is a replacement effect.
- **CR 702.33d** - a spell is "kicked" once its kicker cost is declared paid;
  the entering permanent reads it from the cast record, never live.
- **CR 207.2c** - Raid and Ferocious are ability words with no rules meaning;
  the condition after the dash is what is read.
- **CR 601.2h** - the mana spent to cast the spell is fixed when it is paid
  (adamant counts it).

Every number was looked up with `mise run rules:find <n>`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.objects_as_costs import convoke
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _board(*, hand=(), battlefield=(), graveyard=(), opponent=()):
    scenario = Scenario().manual_turn_based_actions()
    scenario.player(
        "alice", hand=list(hand), battlefield=list(battlefield), graveyard=list(graveyard)
    ).player("bob", battlefield=list(opponent))
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    return played


def _cast(played, name, *, kicked=False, which=()):
    casting = played.cast(name)
    if kicked:
        casting.pay_kicker(int(kicked))
    for cost in which:
        casting.pay_kicker(1, which=cost)
    payment = casting.begin_paying()
    played.auto_pay(payment, username="alice")
    played.put_on_stack(casting)
    return played.resolve_top()


def test_a_kicked_academy_drake_enters_with_two_counters():
    played = _board(hand=["Academy Drake"], battlefield=["Island"] * 8)
    assert _cast(played, "Academy Drake", kicked=True).counters[Counter.PLUS_ONE] == 2


def test_an_unkicked_academy_drake_enters_with_none():
    played = _board(hand=["Academy Drake"], battlefield=["Island"] * 8)
    assert _cast(played, "Academy Drake").counters[Counter.PLUS_ONE] == 0


def test_baloth_gorger_kicked_gets_three_and_unkicked_none():
    kicked = _board(hand=["Baloth Gorger"], battlefield=["Forest"] * 8)
    assert _cast(kicked, "Baloth Gorger", kicked=True).counters[Counter.PLUS_ONE] == 3
    plain = _board(hand=["Baloth Gorger"], battlefield=["Forest"] * 8)
    assert _cast(plain, "Baloth Gorger").counters[Counter.PLUS_ONE] == 0


def test_a_kicker_creature_put_onto_the_battlefield_is_not_kicked():
    played = _board(hand=["Academy Drake"])
    assert played.put_onto_battlefield("Academy Drake").counters[Counter.PLUS_ONE] == 0


def test_raid_enters_with_a_counter_after_attacking():
    played = _board(hand=["Goblin Boarders"])
    played.game.record_turn_fact("attacked", "alice")
    assert played.put_onto_battlefield("Goblin Boarders").counters[Counter.PLUS_ONE] == 1


def test_raid_enters_bare_without_an_attack():
    played = _board(hand=["Goblin Boarders"])
    assert played.put_onto_battlefield("Goblin Boarders").counters[Counter.PLUS_ONE] == 0


def test_adamant_needs_three_mana_of_the_colour():
    red = _board(hand=["Embereth Paladin"], battlefield=["Mountain"] * 5)
    assert _cast(red, "Embereth Paladin").counters[Counter.PLUS_ONE] == 1
    mixed = _board(
        hand=["Embereth Paladin"],
        battlefield=["Mountain", "Mountain", "Forest", "Forest", "Forest"],
    )
    assert _cast(mixed, "Embereth Paladin").counters[Counter.PLUS_ONE] == 0


def test_dust_animus_with_five_untapped_lands_gets_counters_and_lifelink():
    played = _board(hand=["Dust Animus"], battlefield=["Mountain"] * 5)
    animus = played.put_onto_battlefield("Dust Animus")
    assert animus.counters[Counter.PLUS_ONE] == 2
    assert animus.counters["lifelink"] == 1


def test_dust_animus_with_four_lands_gets_nothing():
    played = _board(hand=["Dust Animus"], battlefield=["Mountain"] * 4)
    animus = played.put_onto_battlefield("Dust Animus")
    assert animus.counters[Counter.PLUS_ONE] == 0
    assert animus.counters["lifelink"] == 0


def test_cindering_cutthroat_needs_an_opponent_to_have_lost_life():
    played = _board(hand=["Cindering Cutthroat"])
    played.game.player("bob").lose_life(2)
    assert played.put_onto_battlefield("Cindering Cutthroat").counters[Counter.PLUS_ONE] == 1
    bare = _board(hand=["Cindering Cutthroat"])
    assert bare.put_onto_battlefield("Cindering Cutthroat").counters[Counter.PLUS_ONE] == 0


def test_hotheaded_giant_without_another_red_spell_enters_with_minus_counters():
    played = _board(hand=["Hotheaded Giant"], battlefield=["Mountain"] * 4)
    assert _cast(played, "Hotheaded Giant").counters[Counter.MINUS_ONE] == 2


def test_vampire_socialite_group_gate_follows_life_lost():
    lost = _board(battlefield=["Vampire Socialite"], hand=["Child of Night"])
    lost.game.player("bob").lose_life(1)
    assert lost.put_onto_battlefield("Child of Night").counters[Counter.PLUS_ONE] == 1
    bare = _board(battlefield=["Vampire Socialite"], hand=["Child of Night"])
    assert bare.put_onto_battlefield("Child of Night").counters[Counter.PLUS_ONE] == 0


def test_dearly_departed_in_the_graveyard_buffs_entering_humans():
    scenario = Scenario().manual_turn_based_actions()
    scenario.player("alice", hand=["Elite Vanguard"], graveyard=["Dearly Departed"]).player("bob")
    in_yard = scenario.build()
    in_yard.start_at(Step.PRECOMBAT_MAIN)
    assert in_yard.put_onto_battlefield("Elite Vanguard").counters[Counter.PLUS_ONE] == 1
    bare = _board(hand=["Elite Vanguard"])
    assert bare.put_onto_battlefield("Elite Vanguard").counters[Counter.PLUS_ONE] == 0


# -- kicked, plus haste and a second counter kind (CR 702.33d, CR 614.1c) ------


def test_a_kicked_pouncing_wurm_enters_with_counters_and_haste():
    played = _board(hand=["Pouncing Wurm"], battlefield=["Forest"] * 8)
    wurm = _cast(played, "Pouncing Wurm", kicked=True)
    assert wurm.counters[Counter.PLUS_ONE] == 3
    assert has_keyword(wurm, Keyword.HASTE, played.game)


def test_an_unkicked_pouncing_wurm_has_neither():
    played = _board(hand=["Pouncing Wurm"], battlefield=["Forest"] * 8)
    wurm = _cast(played, "Pouncing Wurm")
    assert wurm.counters[Counter.PLUS_ONE] == 0
    assert not has_keyword(wurm, Keyword.HASTE, played.game)


def test_a_kicked_voidpouncer_enters_with_two_kinds_of_counter_and_haste():
    played = _board(
        hand=["Voidpouncer"],
        battlefield=["Mountain", "Mountain", "Mountain", "Wastes", "Wastes", "Wastes"],
    )
    pouncer = _cast(played, "Voidpouncer", kicked=True)
    assert pouncer.counters[Counter.PLUS_ONE] == 2
    assert pouncer.counters["trample"] == 1
    assert has_keyword(pouncer, Keyword.HASTE, played.game)


def test_an_unkicked_voidpouncer_enters_bare():
    played = _board(
        hand=["Voidpouncer"],
        battlefield=["Mountain", "Mountain", "Mountain", "Wastes", "Wastes", "Wastes"],
    )
    pouncer = _cast(played, "Voidpouncer")
    assert pouncer.counters[Counter.PLUS_ONE] == 0
    assert pouncer.counters["trample"] == 0
    assert not has_keyword(pouncer, Keyword.HASTE, played.game)


# -- cast-record gates (CR 601.2h, CR 601.2i) ----------------------------------


def test_steel_exemplar_with_one_colour_spent_keeps_its_counters():
    played = _board(hand=["Steel Exemplar"], battlefield=["Plains"] * 5)
    assert _cast(played, "Steel Exemplar").counters[Counter.PLUS_ONE] == 2


def test_steel_exemplar_with_two_colours_spent_enters_bare():
    played = _board(
        hand=["Steel Exemplar"], battlefield=["Plains", "Plains", "Plains", "Island", "Island"]
    )
    assert _cast(played, "Steel Exemplar").counters[Counter.PLUS_ONE] == 0


def test_freestrider_commando_cast_for_mana_enters_bare():
    played = _board(hand=["Freestrider Commando"], battlefield=["Forest"] * 6)
    assert _cast(played, "Freestrider Commando").counters[Counter.PLUS_ONE] == 0


def test_freestrider_commando_put_onto_the_battlefield_was_not_cast():
    played = _board(hand=["Freestrider Commando"])
    assert played.put_onto_battlefield("Freestrider Commando").counters[Counter.PLUS_ONE] == 2


def test_nine_lives_familiar_cast_gets_eight_revival_counters():
    played = _board(hand=["Nine-Lives Familiar"], battlefield=["Swamp"] * 3)
    assert _cast(played, "Nine-Lives Familiar").counters["revival"] == 8


def test_nine_lives_familiar_put_onto_the_battlefield_gets_none():
    played = _board(hand=["Nine-Lives Familiar"])
    assert played.put_onto_battlefield("Nine-Lives Familiar").counters["revival"] == 0


def _master_after(bolts):
    played = _board(
        hand=["Lightning Bolt"] * bolts + ["Effortless Master"],
        battlefield=["Mountain"] * 5 + ["Island"],
    )
    for _ in range(bolts):
        played.cast_and_resolve("Lightning Bolt", targets=["bob"], auto=True)
    return played.cast_and_resolve("Effortless Master", auto=True)


def test_effortless_master_after_two_other_spells_gets_counters():
    assert _master_after(2).counters[Counter.PLUS_ONE] == 2


def test_effortless_master_as_the_second_spell_cast_this_turn_counts():
    """The master itself is a spell cast this turn (CR 601.2i), so one earlier
    spell is enough."""
    assert _master_after(1).counters[Counter.PLUS_ONE] == 2


def test_effortless_master_cast_first_enters_bare():
    assert _master_after(0).counters[Counter.PLUS_ONE] == 0


def test_ascendant_packleader_needs_a_big_permanent():
    played = _board(hand=["Ascendant Packleader"], battlefield=["Plains"] * 2)
    assert played.put_onto_battlefield("Ascendant Packleader").counters[Counter.PLUS_ONE] == 0


def test_ascendant_packleader_with_a_mana_value_four_permanent_gets_a_counter():
    played = _board(hand=["Ascendant Packleader"], battlefield=["Steel Exemplar"])
    assert played.put_onto_battlefield("Ascendant Packleader").counters[Counter.PLUS_ONE] == 1


# -- "for each creature that convoked it" (CR 702.51c) ------------------------


def _imperiosaur_convoked_by(convokers):
    played = _board(
        hand=["Ancient Imperiosaur"],
        battlefield=["Grizzly Bears"] * convokers + ["Forest"] * (7 - convokers),
    )
    casting = played.cast("Ancient Imperiosaur")
    payment = casting.begin_paying()
    for bear in (
        played.creatures("Grizzly Bears", *["Grizzly Bears"] * (convokers - 1))[:convokers]
        if convokers
        else []
    ):
        convoke(payment, casting.spell, bear)
    played.auto_pay(payment, username="alice")
    played.put_on_stack(casting)
    return played.resolve_top()


def test_ancient_imperiosaur_gets_two_counters_per_creature_that_convoked_it():
    assert _imperiosaur_convoked_by(2).counters[Counter.PLUS_ONE] == 4


def test_ancient_imperiosaur_cast_without_convoke_enters_bare():
    assert _imperiosaur_convoked_by(0).counters[Counter.PLUS_ONE] == 0


# -- "As this enters, you may <action>. ... enters with counters" (CR 614.12a) --


def _hand_cards(played, *names):
    return [card for name in names for card in played.player("alice").hand if card.name == name]


def test_dragons_disciple_revealing_a_dragon_gets_a_counter():
    played = _board(hand=["Dragon's Disciple", "Hellkite Whelp"])
    played.will_choose_cards(*_hand_cards(played, "Hellkite Whelp"), source="Dragon's Disciple")
    assert played.put_onto_battlefield("Dragon's Disciple").counters[Counter.PLUS_ONE] == 1


def test_dragons_disciple_controlling_a_dragon_gets_a_counter_without_revealing():
    played = _board(hand=["Dragon's Disciple"], battlefield=["Hellkite Whelp"])
    assert played.put_onto_battlefield("Dragon's Disciple").counters[Counter.PLUS_ONE] == 1


def test_dragons_disciple_with_neither_enters_bare():
    played = _board(hand=["Dragon's Disciple", "Hellkite Whelp"])
    assert played.put_onto_battlefield("Dragon's Disciple").counters[Counter.PLUS_ONE] == 0


def test_arsenal_thresher_gets_a_counter_for_each_artifact_revealed():
    played = _board(hand=["Arsenal Thresher", "Mishra's Bauble", "Mishra's Bauble"])
    played.will_choose_cards(*_hand_cards(played, "Mishra's Bauble"), source="Arsenal Thresher")
    assert played.put_onto_battlefield("Arsenal Thresher").counters[Counter.PLUS_ONE] == 2


def test_arsenal_thresher_revealing_nothing_enters_bare():
    played = _board(hand=["Arsenal Thresher", "Mishra's Bauble"])
    played.will_choose_cards(source="Arsenal Thresher")
    assert played.put_onto_battlefield("Arsenal Thresher").counters[Counter.PLUS_ONE] == 0


def test_rescuer_sphinx_returning_a_permanent_gets_a_counter():
    played = _board(hand=["Rescuer Sphinx"], battlefield=["Grizzly Bears"])
    bears = played.creature("Grizzly Bears")
    played.will_choose_cards(bears, source="Rescuer Sphinx")
    sphinx = played.put_onto_battlefield("Rescuer Sphinx")
    assert sphinx.counters[Counter.PLUS_ONE] == 1
    assert bears.zone is Zone.HAND


def test_rescuer_sphinx_declining_keeps_the_permanent_and_gets_nothing():
    played = _board(hand=["Rescuer Sphinx"], battlefield=["Grizzly Bears"])
    played.will_choose_cards(source="Rescuer Sphinx")
    sphinx = played.put_onto_battlefield("Rescuer Sphinx")
    assert sphinx.counters[Counter.PLUS_ONE] == 0
    assert played.creature("Grizzly Bears").zone is Zone.BATTLEFIELD


def test_ulamogs_despoiler_putting_two_exiled_cards_into_graveyards_gets_four_counters():
    scenario = Scenario().manual_turn_based_actions()
    scenario.player("alice", hand=["Ulamog's Despoiler"]).player(
        "bob", exile=["Grizzly Bears", "Goblin Piker"]
    )
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    exiled = list(played.game.exile)
    played.will_choose_cards(*exiled, source="Ulamog's Despoiler")
    despoiler = played.put_onto_battlefield("Ulamog's Despoiler")
    assert despoiler.counters[Counter.PLUS_ONE] == 4
    assert all(card.zone is Zone.GRAVEYARD for card in exiled)


def test_ulamogs_despoiler_refuses_a_single_card():
    scenario = Scenario().manual_turn_based_actions()
    scenario.player("alice", hand=["Ulamog's Despoiler"]).player(
        "bob", exile=["Grizzly Bears", "Goblin Piker"]
    )
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    played.will_choose_cards(played.game.exile[0], source="Ulamog's Despoiler")
    with pytest.raises(ValueError):
        played.put_onto_battlefield("Ulamog's Despoiler")


def test_mimeoplasm_exiles_up_to_x_creature_cards_for_three_counters_each():
    scenario = Scenario().manual_turn_based_actions()
    scenario.player(
        "alice",
        hand=["Mimeoplasm, Revered One"],
        graveyard=["Grizzly Bears", "Goblin Piker", "Elvish Warrior"],
        battlefield=["Island", "Swamp", "Forest", "Forest", "Forest"],
    ).player("bob")
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    casting = played.cast("Mimeoplasm, Revered One")
    casting.determine_cost(x_value=2)
    played.will_choose_cards(
        *played.player("alice").graveyard[:2], source="Mimeoplasm, Revered One"
    )
    played.auto_pay(casting.begin_paying(), username="alice")
    played.put_on_stack(casting)
    mimeoplasm = played.resolve_top()
    assert mimeoplasm.counters[Counter.PLUS_ONE] == 6


# -- "You may cast this card from your graveyard. If you do, it enters with
# counters" (CR 601.3, CR 604.6, CR 614.1c) -----------------------------------


def _from_graveyard(played, name):
    casting = played.cast(name, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Cast permission")
    played.auto_pay(casting.begin_paying(), username="alice")
    played.put_on_stack(casting)
    return played.resolve_top()


def test_undead_sprinter_cast_from_the_graveyard_after_a_non_zombie_died():
    played = _board(
        graveyard=["Undead Sprinter"], battlefield=["Grizzly Bears", "Swamp", "Mountain"]
    )
    played.game.sacrifice(played.creature("Grizzly Bears"))
    assert _from_graveyard(played, "Undead Sprinter").counters[Counter.PLUS_ONE] == 1


def test_undead_sprinter_is_not_castable_from_the_graveyard_without_a_death():
    played = _board(graveyard=["Undead Sprinter"], battlefield=["Swamp", "Mountain"])
    with pytest.raises(ValueError):
        _from_graveyard(played, "Undead Sprinter")


def test_undead_sprinter_is_not_castable_after_only_a_zombie_died():
    played = _board(
        graveyard=["Undead Sprinter"], battlefield=["Walking Corpse", "Swamp", "Mountain"]
    )
    played.game.sacrifice(played.creature("Walking Corpse"))
    with pytest.raises(ValueError):
        _from_graveyard(played, "Undead Sprinter")


def test_undead_sprinter_cast_from_hand_enters_bare():
    played = _board(hand=["Undead Sprinter"], battlefield=["Swamp", "Mountain"])
    assert _cast(played, "Undead Sprinter").counters[Counter.PLUS_ONE] == 0


def test_worldheart_phoenix_cast_for_five_colours_from_the_graveyard_gets_two_counters():
    played = _board(
        graveyard=["Worldheart Phoenix"],
        battlefield=["Plains", "Island", "Swamp", "Mountain", "Forest"],
    )
    assert _from_graveyard(played, "Worldheart Phoenix").counters[Counter.PLUS_ONE] == 2


def test_worldheart_phoenix_cast_from_hand_enters_bare():
    played = _board(hand=["Worldheart Phoenix"], battlefield=["Mountain"] * 4)
    assert _cast(played, "Worldheart Phoenix").counters[Counter.PLUS_ONE] == 0


def test_hundred_battle_veteran_cast_from_the_graveyard_gets_a_finality_counter():
    played = _board(graveyard=["Hundred-Battle Veteran"], battlefield=["Swamp"] * 4)
    assert _from_graveyard(played, "Hundred-Battle Veteran").counters["finality"] == 1


def test_hundred_battle_veteran_cast_from_hand_has_no_finality_counter():
    played = _board(hand=["Hundred-Battle Veteran"], battlefield=["Swamp"] * 4)
    assert _cast(played, "Hundred-Battle Veteran").counters["finality"] == 0


# -- web-slinging: "X is the mana value of the returned creature" (CR 702.188a) --


def _scarlet_spider(web_slung):
    played = _board(
        hand=["Scarlet Spider, Ben Reilly"],
        battlefield=["Cultivator Colossus", "Mountain", "Forest", "Mountain", "Forest", "Mountain"],
    )
    colossus = played.creature("Cultivator Colossus")
    casting = played.cast("Scarlet Spider, Ben Reilly")
    if web_slung:
        played.game.tap_permanent(colossus)
        casting.use_keyword("Web-slinging", choosing=[colossus])
    played.auto_pay(casting.begin_paying(), username="alice")
    played.put_on_stack(casting)
    return played.resolve_top()


def test_scarlet_spider_web_slung_enters_with_the_returned_creatures_mana_value():
    assert _scarlet_spider(True).counters[Counter.PLUS_ONE] == 7


def test_scarlet_spider_cast_normally_enters_bare():
    assert _scarlet_spider(False).counters[Counter.PLUS_ONE] == 0


# -- "If you cast a spell this way, that creature enters with a counter"
# (cards exiled with a permanent, CR 607.2a) ----------------------------------


def _paleontologist_board(graveyard):
    scenario = Scenario().manual_turn_based_actions()
    scenario.player(
        "alice",
        battlefield=["Intrepid Paleontologist", *["Forest"] * 7],
        graveyard=list(graveyard),
    ).player("bob")
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    return played


def _exile_and_cast(played, name):
    target = played.find(name, Zone.GRAVEYARD, "alice")
    paleontologist = played.creature("Intrepid Paleontologist")
    played.activate(paleontologist, index=1, targets=[target], username="alice", auto=True)
    played.resolve_top()
    casting = played.cast(name, from_zone=Zone.EXILE)
    casting.use_keyword("Cast permission")
    played.auto_pay(casting.begin_paying(), username="alice")
    played.put_on_stack(casting)
    return played.resolve_top()


def test_a_dinosaur_cast_from_the_paleontologists_pile_enters_with_a_finality_counter():
    played = _paleontologist_board(["Ranging Raptors"])
    assert _exile_and_cast(played, "Ranging Raptors").counters["finality"] == 1


def test_a_dinosaur_not_cast_that_way_has_no_finality_counter():
    played = _board(hand=["Ranging Raptors"], battlefield=["Forest"] * 4)
    assert _cast(played, "Ranging Raptors").counters["finality"] == 0


def _cast_with_extra_mana(played, name, amount):
    casting = played.cast(name)
    casting.pay_extra_mana_for_counters(amount)
    played.auto_pay(casting.begin_paying(), username="alice")
    played.put_on_stack(casting)
    return played.resolve_top()


def test_chorus_of_the_conclave_pays_any_amount_for_that_many_counters():
    played = _board(hand=["Grizzly Bears"], battlefield=["Chorus of the Conclave"] + ["Forest"] * 6)
    bears = _cast_with_extra_mana(played, "Grizzly Bears", 4)
    assert bears.counters[Counter.PLUS_ONE] == 4


def test_chorus_of_the_conclave_charges_the_extra_mana():
    played = _board(hand=["Grizzly Bears"], battlefield=["Chorus of the Conclave", "Forest"] * 1)
    casting = played.cast("Grizzly Bears")
    casting.pay_extra_mana_for_counters(3)
    assert casting.total_cost.mana.converted == 5


def test_chorus_of_the_conclave_paying_nothing_adds_nothing():
    played = _board(hand=["Grizzly Bears"], battlefield=["Chorus of the Conclave"] + ["Forest"] * 2)
    assert _cast_with_extra_mana(played, "Grizzly Bears", 0).counters[Counter.PLUS_ONE] == 0


def test_chorus_of_the_conclave_needs_the_permanent():
    played = _board(hand=["Grizzly Bears"], battlefield=["Forest"] * 6)
    casting = played.cast("Grizzly Bears")
    with pytest.raises(ValueError, match="additional cost"):
        casting.pay_extra_mana_for_counters(2)


def test_chorus_of_the_conclave_only_helps_creature_spells():
    played = _board(hand=["Lightning Bolt"], battlefield=["Chorus of the Conclave", "Mountain"] * 1)
    casting = played.cast("Lightning Bolt")
    with pytest.raises(ValueError, match="creature"):
        casting.pay_extra_mana_for_counters(1)


# -- every kicker line, multikicker "for each time it was kicked" (CR 702.33) --

#: (card, lands, times kicked, counter kind, expected). Each row pays the whole
#: cost (the printed cost plus the kicker cost per kick) from basic lands.
KICKED_ROWS = [
    ("Aether Figment", ["Island"] * 5, 1, Counter.PLUS_ONE, 2),
    ("Cragplate Baloth", ["Forest"] * 10, 1, Counter.PLUS_ONE, 4),
    ("Ghastly Gloomhunter", ["Swamp"] * 6, 1, Counter.PLUS_ONE, 2),
    ("Gnarlid Colony", ["Forest"] * 5, 1, Counter.PLUS_ONE, 2),
    ("Grunn, the Lonely King", ["Forest"] * 9, 1, Counter.PLUS_ONE, 5),
    ("Kavu Primarch", ["Forest"] * 8, 1, Counter.PLUS_ONE, 4),
    ("Moss-Pit Skeleton", ["Swamp"] * 4 + ["Forest"], 1, Counter.PLUS_ONE, 3),
    ("Pixie Illusionist", ["Island"] * 4 + ["Forest"], 1, Counter.PLUS_ONE, 2),
    ("Shalai's Acolyte", ["Plains"] * 6 + ["Forest"], 1, Counter.PLUS_ONE, 2),
    ("Shatterskull Charger", ["Mountain"] * 5, 1, Counter.PLUS_ONE, 1),
    ("Skyclave Sentinel", ["Mountain"] * 7, 1, Counter.PLUS_ONE, 2),
    ("Skyclave Shade", ["Swamp"] * 5, 1, Counter.PLUS_ONE, 2),
    ("Stronghold Confessor", ["Swamp"] * 4, 1, Counter.PLUS_ONE, 2),
    ("Untamed Kavu", ["Forest"] * 5, 1, Counter.PLUS_ONE, 3),
    ("Viashino Branchrider", ["Mountain"] * 3 + ["Forest"], 1, Counter.PLUS_ONE, 2),
    ("Ravaging Riftwurm", ["Forest"] * 7, 1, "time", 5),
    ("Apex Hawks", ["Plains"] * 7, 2, Counter.PLUS_ONE, 2),
    ("Enclave Elite", ["Island"] * 7, 2, Counter.PLUS_ONE, 2),
    ("Gnarlid Pack", ["Forest"] * 6, 2, Counter.PLUS_ONE, 2),
    ("Joraga Warcaller", ["Forest"] * 5, 2, Counter.PLUS_ONE, 2),
    ("Quag Vampires", ["Swamp"] * 5, 2, Counter.PLUS_ONE, 2),
    ("Skitter of Lizards", ["Mountain"] * 7, 3, Counter.PLUS_ONE, 3),
    ("Everflowing Chalice", ["Mountain"] * 4, 2, Counter.CHARGE, 2),
]


@pytest.mark.parametrize("name,lands,kicks,kind,expected", KICKED_ROWS)
def test_a_kicked_card_enters_with_the_counters_its_line_names(name, lands, kicks, kind, expected):
    played = _board(hand=[name], battlefield=lands)
    assert _cast(played, name, kicked=kicks).counters[kind] == expected


@pytest.mark.parametrize("name,lands,kicks,kind,expected", KICKED_ROWS)
def test_the_same_card_unkicked_enters_with_the_printed_amount(name, lands, kicks, kind, expected):
    played = _board(hand=[name], battlefield=lands)
    unkicked = {"Ravaging Riftwurm": 2}.get(name, 0)
    assert _cast(played, name).counters[kind] == unkicked


def test_vodalian_mindsinger_gets_two_counters_for_each_kicker_paid():
    both = _board(
        hand=["Vodalian Mindsinger"], battlefield=["Island"] * 3 + ["Mountain"] * 2 + ["Forest"] * 2
    )
    mindsinger = _cast(both, "Vodalian Mindsinger", which=("{1}{R}", "{1}{G}"))
    assert mindsinger.counters[Counter.PLUS_ONE] == 4
    one = _board(hand=["Vodalian Mindsinger"], battlefield=["Island"] * 3 + ["Mountain"] * 2)
    assert _cast(one, "Vodalian Mindsinger", which=("{1}{R}",)).counters[Counter.PLUS_ONE] == 2


def test_myriad_construct_counts_the_nonbasic_lands_opponents_control():
    played = _board(
        hand=["Myriad Construct"],
        battlefield=["Mountain"] * 7,
        opponent=["Vivid Creek", "Vivid Marsh", "Swamp"],
    )
    assert _cast(played, "Myriad Construct", kicked=True).counters[Counter.PLUS_ONE] == 2


def test_flametongue_yearling_gets_a_counter_for_each_time_it_was_kicked():
    played = _board(hand=["Flametongue Yearling"], battlefield=["Mountain"] * 6)
    yearling = _cast(played, "Flametongue Yearling", kicked=2)
    assert yearling.counters[Counter.PLUS_ONE] == 2


# -- Raid and Ferocious (CR 207.2c ability words, the condition decides) -------

RAID_CARDS = [
    "Cruel Administrator",
    "Rigging Runner",
    "Storm Fleet Aerialist",
    "Swaggering Corsair",
    "War-Name Aspirant",
]


@pytest.mark.parametrize("name", RAID_CARDS)
def test_raid_cards_enter_with_a_counter_after_an_attack(name):
    played = _board(hand=[name])
    played.game.record_turn_fact("attacked", "alice")
    assert played.put_onto_battlefield(name).counters[Counter.PLUS_ONE] == 1


@pytest.mark.parametrize("name", RAID_CARDS)
def test_raid_cards_enter_bare_when_you_did_not_attack(name):
    played = _board(hand=[name])
    assert played.put_onto_battlefield(name).counters[Counter.PLUS_ONE] == 0


def test_raid_ignores_an_attack_the_opponent_made():
    played = _board(hand=["Swaggering Corsair"])
    played.game.record_turn_fact("attacked", "bob")
    assert played.put_onto_battlefield("Swaggering Corsair").counters[Counter.PLUS_ONE] == 0


def test_ferocious_needs_a_creature_with_power_four_or_greater():
    big = _board(hand=["Frontier Mastodon"], battlefield=["Craw Wurm"])
    assert big.put_onto_battlefield("Frontier Mastodon").counters[Counter.PLUS_ONE] == 1
    small = _board(hand=["Frontier Mastodon"], battlefield=["Grizzly Bears"])
    assert small.put_onto_battlefield("Frontier Mastodon").counters[Counter.PLUS_ONE] == 0


# -- Adamant (CR 207.2c, CR 601.2h) ---------------------------------------------

ADAMANT_ROWS = [
    ("Locthwain Paladin", "Swamp", 4),
    ("Vantress Paladin", "Island", 4),
    ("Ardenvale Paladin", "Plains", 4),
    ("Garenbrig Paladin", "Forest", 5),
    ("Henge Walker", "Mountain", 3),
]


@pytest.mark.parametrize("name,land,count", ADAMANT_ROWS)
def test_adamant_with_three_mana_of_the_colour_adds_a_counter(name, land, count):
    played = _board(hand=[name], battlefield=[land] * count)
    assert _cast(played, name).counters[Counter.PLUS_ONE] == 1


@pytest.mark.parametrize("name,land,count", ADAMANT_ROWS[:4])
def test_adamant_with_a_mixed_payment_adds_nothing(name, land, count):
    other = "Mountain" if land != "Mountain" else "Forest"
    played = _board(hand=[name], battlefield=[land] * 2 + [other] * (count - 2))
    assert _cast(played, name).counters[Counter.PLUS_ONE] == 0


def test_henge_walker_needs_three_mana_of_one_colour_not_any_three():
    played = _board(hand=["Henge Walker"], battlefield=["Mountain", "Forest", "Island"])
    assert _cast(played, "Henge Walker").counters[Counter.PLUS_ONE] == 0


# -- Scaleguard Sentinels (CR 702 reveal as an additional cost, CR 601.2b) -----


def test_scaleguard_sentinels_revealing_a_dragon_enters_with_a_counter():
    played = _board(hand=["Scaleguard Sentinels", "Hellkite Whelp"], battlefield=["Forest"] * 2)
    whelp = played.find("Hellkite Whelp", Zone.HAND, "alice")
    casting = played.cast("Scaleguard Sentinels")
    casting.reveal_for_cost(whelp)
    played.auto_pay(casting.begin_paying(), username="alice")
    played.put_on_stack(casting)
    assert played.resolve_top().counters[Counter.PLUS_ONE] == 1


def test_scaleguard_sentinels_controlling_a_dragon_enters_with_a_counter():
    played = _board(hand=["Scaleguard Sentinels"], battlefield=["Forest"] * 2 + ["Hellkite Whelp"])
    assert _cast(played, "Scaleguard Sentinels").counters[Counter.PLUS_ONE] == 1


def test_scaleguard_sentinels_with_no_dragon_enters_bare():
    played = _board(hand=["Scaleguard Sentinels"], battlefield=["Forest"] * 2)
    assert _cast(played, "Scaleguard Sentinels").counters[Counter.PLUS_ONE] == 0


# -- "if you cast it from your hand" and "if you didn't" (CR 614.1c) ------------

MYOJIN_ROWS = [
    ("Myojin of Seeing Winds", "Island", 10),
    ("Myojin of Cleansing Fire", "Plains", 8),
    ("Myojin of Infinite Rage", "Mountain", 10),
    ("Myojin of Life's Web", "Forest", 9),
    ("Myojin of Night's Reach", "Swamp", 8),
]


@pytest.mark.parametrize("name,land,count", MYOJIN_ROWS)
def test_a_myojin_cast_from_hand_enters_with_a_divinity_counter(name, land, count):
    played = _board(hand=[name], battlefield=[land] * count)
    assert _cast(played, name).counters["divinity"] == 1


@pytest.mark.parametrize("name,land,count", MYOJIN_ROWS)
def test_a_myojin_put_onto_the_battlefield_has_no_divinity_counter(name, land, count):
    played = _board(hand=[name])
    assert played.put_onto_battlefield(name).counters["divinity"] == 0


def test_epochrasite_not_cast_from_hand_enters_with_three_counters():
    played = _board(hand=["Epochrasite"], battlefield=["Mountain"] * 2)
    assert played.put_onto_battlefield("Epochrasite").counters[Counter.PLUS_ONE] == 3


def test_epochrasite_cast_from_hand_enters_bare():
    played = _board(hand=["Epochrasite"], battlefield=["Mountain"] * 2)
    assert _cast(played, "Epochrasite").counters[Counter.PLUS_ONE] == 0


# -- X, mana spent and converge (CR 107.3, CR 601.2h) --------------------------


def _cast_x(played, name, x):
    card = played.find(name, Zone.HAND, "alice")
    sources = played.game.permanents_controlled_by("alice")
    lands = [permanent for permanent in sources if "Land" in permanent.card.type_line]
    played.game.cast(card, "alice", x_value=x, mana_sources=lands)
    return played.resolve_top()


def test_apocalypse_hydra_enters_with_x_counters():
    played = _board(hand=["Apocalypse Hydra"], battlefield=["Mountain", "Forest"] + ["Forest"] * 3)
    assert _cast_x(played, "Apocalypse Hydra", 3).counters[Counter.PLUS_ONE] == 3


def test_apocalypse_hydra_with_x_of_five_or_more_doubles_it():
    played = _board(hand=["Apocalypse Hydra"], battlefield=["Mountain", "Forest"] + ["Forest"] * 5)
    assert _cast_x(played, "Apocalypse Hydra", 5).counters[Counter.PLUS_ONE] == 10


def test_morlun_enters_with_x_counters():
    played = _board(hand=["Morlun, Devourer of Spiders"], battlefield=["Swamp"] * 4)
    assert _cast_x(played, "Morlun, Devourer of Spiders", 2).counters[Counter.PLUS_ONE] == 2


def test_dyadrine_counts_all_the_mana_spent_to_cast_it():
    played = _board(
        hand=["Dyadrine, Synthesis Amalgam"], battlefield=["Forest", "Plains"] + ["Forest"] * 2
    )
    assert _cast_x(played, "Dyadrine, Synthesis Amalgam", 2).counters[Counter.PLUS_ONE] == 4


def test_verazol_counts_all_the_mana_spent_to_cast_it():
    played = _board(hand=["Verazol, the Split Current"], battlefield=["Forest", "Island", "Island"])
    assert _cast_x(played, "Verazol, the Split Current", 1).counters[Counter.PLUS_ONE] == 3


def test_glinting_creeper_gets_two_counters_per_colour_of_mana_spent():
    two = _board(hand=["Glinting Creeper"], battlefield=["Forest"] * 4 + ["Plains"])
    assert _cast(two, "Glinting Creeper").counters[Counter.PLUS_ONE] == 4
    one = _board(hand=["Glinting Creeper"], battlefield=["Forest"] * 5)
    assert _cast(one, "Glinting Creeper").counters[Counter.PLUS_ONE] == 2


def test_clay_champion_counts_each_pair_of_green_mana_spent():
    played = _board(hand=["Clay Champion"], battlefield=["Forest"] * 4)
    assert _cast(played, "Clay Champion").counters[Counter.PLUS_ONE] == 6
