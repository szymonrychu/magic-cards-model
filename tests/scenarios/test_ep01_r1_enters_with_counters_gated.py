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

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.objects_as_costs import convoke
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _board(*, hand, battlefield=()):
    scenario = Scenario().manual_turn_based_actions()
    scenario.player("alice", hand=list(hand), battlefield=list(battlefield)).player("bob")
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    return played


def _cast(played, name, *, kicked=False):
    casting = played.cast(name)
    if kicked:
        casting.pay_kicker()
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
    for bear in played.creatures("Grizzly Bears", *["Grizzly Bears"] * (convokers - 1))[
        :convokers
    ] if convokers else []:
        convoke(payment, casting.spell, bear)
    played.auto_pay(payment, username="alice")
    played.put_on_stack(casting)
    return played.resolve_top()


def test_ancient_imperiosaur_gets_two_counters_per_creature_that_convoked_it():
    assert _imperiosaur_convoked_by(2).counters[Counter.PLUS_ONE] == 4


def test_ancient_imperiosaur_cast_without_convoke_enters_bare():
    assert _imperiosaur_convoked_by(0).counters[Counter.PLUS_ONE] == 0
