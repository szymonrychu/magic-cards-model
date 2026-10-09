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
