"""Scenario: cards in a hand / graveyard / library counted as an amount, and
"half" of a zone (EP-02 R2 T2).

One reader family, many sentences: "for each card in your hand", "the number
of cards in their hand", "for each card in your opponents' hands", "for each
<type> card in your opponents' graveyards", "for each card with cycling in
your graveyard", and "half the cards in their hand / half their library /
half the creatures they control, rounded up|down".

CR numbers below were read with `mise run rules:find` in the session that
wrote this file:

- **CR 107.1a** - a fractional amount is rounded the way the card says.
- **CR 402.1** - the hand is a zone like any other; every card in it counts.
- **CR 404.1** - each player has their own graveyard.
- **CR 608.2h** - information is taken once, as the effect applies.
- **CR 613.4c** - a P/T change from a static ability is sublayer 7c and is
  re-evaluated continuously (CR 611.3a).
- **CR 702.29f** - typecycling abilities are cycling abilities, so a card
  with typecycling is "a card with cycling".
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import keyword_abilities
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.machines.zone_grants import effective_card
from magic_cards_model.models import Color, Type, Zone

from .harness import Scenario, mana_from

CARD = "Forest"


def _count_named(scenario, name, username):
    return len([c for c in scenario.game.permanents_controlled_by(username) if c.card.name == name])


def _pt(scenario, card):
    chars = scenario.game.computed_board().of(card)
    return chars.power, chars.toughness


def _on_battlefield(name, *, alice_hand=0, bob_hand=0, alice_gy=(), bob_gy=(), extra=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[name, *extra],
            hand=[CARD] * alice_hand,
            graveyard=list(alice_gy),
        )
        .player("bob", hand=[CARD] * bob_hand, graveyard=list(bob_gy))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(name, "alice") if name else None


# -- static pump per card in a hand ------------------------------------------


def test_dread_slag_shrinks_by_four_per_card_in_your_hand():
    scenario, slag = _on_battlefield("Dread Slag", alice_hand=2)
    assert _pt(scenario, slag) == (1, 1)


def test_dread_slag_is_printed_size_with_an_empty_hand():
    scenario, slag = _on_battlefield("Dread Slag")
    assert _pt(scenario, slag) == (9, 9)


def test_a_hand_pump_follows_the_hand_as_cards_leave_it():
    """CR 611.3a: not locked in - one fewer card, one point smaller shrink."""
    scenario, strider = _on_battlefield("Grim Strider", alice_hand=3)
    assert _pt(scenario, strider) == (3, 3)
    scenario.game.player("alice").hand.pop()
    assert _pt(scenario, strider) == (4, 4)


def test_grim_strider_ignores_the_opponents_hand():
    scenario, strider = _on_battlefield("Grim Strider", alice_hand=1, bob_hand=5)
    assert _pt(scenario, strider) == (5, 5)


def test_geralfs_masterpiece_counts_your_hand_only():
    scenario, masterpiece = _on_battlefield("Geralf's Masterpiece", alice_hand=4, bob_hand=2)
    assert _pt(scenario, masterpiece) == (3, 3)


def test_stingerback_terror_shrinks_per_card_in_your_hand():
    scenario, terror = _on_battlefield("Stingerback Terror", alice_hand=7)
    assert _pt(scenario, terror) == (0, 0)


def test_enemy_of_enlightenment_counts_the_opponents_hand_not_yours():
    scenario, demon = _on_battlefield("Enemy of Enlightenment", alice_hand=6, bob_hand=3)
    assert _pt(scenario, demon) == (2, 2)


def test_enemy_of_enlightenment_sums_every_opponents_hand():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Enemy of Enlightenment"])
        .player("bob", hand=[CARD] * 2)
        .player("carol", hand=[CARD] * 1)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    demon = scenario.creature("Enemy of Enlightenment", "alice")
    assert _pt(scenario, demon) == (2, 2)


def test_empyrial_plate_pumps_the_equipped_creature_per_card_in_your_hand():
    """Second wording of the same count: an Equipment's "equipped creature gets
    +1/+1 for each card in your hand"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grizzly Bears", "Empyrial Plate", "Mountain", "Mountain"],
            hand=[CARD] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    plate = scenario.find("Empyrial Plate", Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, plate, bears, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain", username="alice"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.resolve_top()
    assert _pt(scenario, bears) == (5, 5)


# -- static pump per card in a graveyard --------------------------------------


def test_wight_of_precinct_six_counts_creature_cards_in_opponents_graveyards():
    scenario, wight = _on_battlefield(
        "Wight of Precinct Six",
        alice_gy=["Grizzly Bears"],
        bob_gy=["Grizzly Bears", "Grizzly Bears", "Forest"],
    )
    assert _pt(scenario, wight) == (3, 3)


def test_runaway_trash_bot_counts_artifact_and_enchantment_cards_in_your_graveyard():
    scenario, bot = _on_battlefield(
        "Runaway Trash-Bot",
        alice_gy=["Sol Ring", "Grizzly Bears", "Forest"],
        bob_gy=["Sol Ring"],
    )
    assert _pt(scenario, bot) == (1, 4)


def test_vile_manifestation_counts_cards_with_cycling_in_your_graveyard():
    scenario, manifestation = _on_battlefield(
        "Vile Manifestation",
        alice_gy=["Vile Manifestation", "Forest"],
        bob_gy=["Vile Manifestation"],
    )
    assert _pt(scenario, manifestation) == (1, 4)


def _equipped(equipment, creature, alice_gy=(), hand=0, source_names=(), bob_hand=0):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[creature, equipment, "Mountain", "Mountain", "Mountain"],
            hand=[CARD] * hand if isinstance(hand, int) else list(hand),
            graveyard=list(alice_gy),
            library=[CARD] * 5,
        )
        .player("bob", hand=[CARD] * bob_hand)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    holder = scenario.creature(creature, "alice")
    gear = scenario.find(equipment, Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, gear, holder, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")[
        : len(payment.cost.mana_symbols) if hasattr(payment.cost, "mana_symbols") else 3
    ]:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.resolve_top()
    return scenario, holder


def test_glamdring_counts_instant_and_sorcery_cards_in_your_graveyard():
    scenario, bears = _equipped(
        "Glamdring", "Grizzly Bears", alice_gy=["Lightning Bolt", "Divination", "Forest"]
    )
    assert _pt(scenario, bears) == (4, 2)
    assert "First strike" in scenario.game.computed_board().of(bears).abilities


def test_glamdring_with_an_empty_graveyard_only_grants_first_strike():
    scenario, bears = _equipped("Glamdring", "Grizzly Bears")
    assert _pt(scenario, bears) == (2, 2)


def test_avatar_destiny_counts_creature_cards_in_your_graveyard_and_adds_avatar():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Avatar Destiny"],
            battlefield=["Grizzly Bears", "Forest", "Forest", "Forest", "Forest"],
            graveyard=["Grizzly Bears", "Grizzly Bears", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Avatar Destiny",
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest"),
        targets=[bears],
    )
    assert _pt(scenario, bears) == (4, 4)
    assert "avatar" in scenario.game.computed_board().of(bears).subtypes


# -- amounts driven by the hand: life, mana, upkeep triggers, mill ------------


def _settle(scenario, limit=12):
    for _ in range(limit):
        scenario.game.put_triggers_on_stack()
        if not scenario.stack_names():
            return
        scenario.pass_until_resolved()
    raise AssertionError(f"stack never emptied: {scenario.stack_names()}")


def _advance_to_upkeep_of(scenario, username):
    scenario.advance()
    while not (scenario.step is Step.UPKEEP and scenario.game.active_player.username == username):
        scenario.advance()


def test_presence_of_the_wise_gains_two_life_per_card_left_in_hand():
    """CR 608.2h: counted as it resolves - the spell itself has left the hand."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Presence of the Wise", CARD, CARD, CARD],
            battlefield=["Plains"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Presence of the Wise", *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    )
    assert scenario.player("alice").life == 20 + 2 * 3


def test_presence_of_the_wise_with_an_empty_hand_gains_nothing():
    scenario = (
        Scenario()
        .player("alice", hand=["Presence of the Wise"], battlefield=["Plains"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Presence of the Wise", *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    )
    assert scenario.player("alice").life == 20


def test_inner_fire_adds_red_for_each_card_left_in_hand():
    scenario = (
        Scenario()
        .player("alice", hand=["Inner Fire", CARD, CARD], battlefield=["Mountain"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Inner Fire", *scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    )
    floating = scenario.game.unspent_mana_of(scenario.player("alice")).floating
    assert sum(floating.values()) == 2


def test_sophic_centaur_counts_the_hand_after_paying_its_discard_cost():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[CARD, CARD, CARD],
            battlefield=["Sophic Centaur", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    centaur = scenario.creature("Sophic Centaur", "alice")
    discarded = scenario.player("alice").hand[0]
    scenario.activate(
        centaur,
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest"),
        discarding=[discarded],
    )
    scenario.resolve_top()
    assert scenario.player("alice").life == 20 + 2 * 2


def test_venser_s_journal_gains_one_life_per_card_in_hand_at_your_upkeep():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Venser's Journal"], hand=[CARD] * 3, library=[CARD] * 5)
        .player("bob", library=[CARD] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _advance_to_upkeep_of(scenario, "bob")
    _advance_to_upkeep_of(scenario, "alice")
    _settle(scenario)
    assert scenario.player("alice").life == 20 + 3


def test_dreamborn_muse_mills_each_player_for_their_own_hand_size():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Dreamborn Muse"], hand=[CARD] * 2, library=[CARD] * 9)
        .player("bob", hand=[CARD] * 4, library=[CARD] * 9)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _advance_to_upkeep_of(scenario, "bob")
    _settle(scenario)
    assert len(scenario.player("bob").library) == 9 - 4
    assert len(scenario.player("alice").library) == 9
    _advance_to_upkeep_of(scenario, "alice")
    _settle(scenario)
    assert len(scenario.player("alice").library) == 9 - 2


# -- half of a zone, rounded as the card says (CR 107.1a) --------------------


def _xander(*, bob_hand=0, bob_library=0, bob_battlefield=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lord Xander, the Collector"], library=[CARD] * 3)
        .player(
            "bob",
            hand=[CARD] * bob_hand,
            library=[CARD] * bob_library,
            battlefield=list(bob_battlefield),
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_lord_xander_enters_and_the_opponent_discards_half_their_hand_rounded_down():
    scenario = _xander(bob_hand=5)
    scenario.will_choose_targets("bob", username="alice", source="Lord Xander, the Collector")
    scenario.put_onto_battlefield("Lord Xander, the Collector")
    _settle(scenario)
    assert len(scenario.player("bob").hand) == 5 - 2
    assert len(scenario.player("bob").graveyard) == 2


def test_half_a_single_card_hand_rounded_down_discards_nothing():
    scenario = _xander(bob_hand=1)
    scenario.will_choose_targets("bob", username="alice", source="Lord Xander, the Collector")
    scenario.put_onto_battlefield("Lord Xander, the Collector")
    _settle(scenario)
    assert len(scenario.player("bob").hand) == 1


def test_lord_xander_attack_mills_half_the_defenders_library_rounded_down():
    scenario = _xander(bob_library=7)
    xander = scenario.put_onto_battlefield("Lord Xander, the Collector")
    xander.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(xander)
    _settle(scenario)
    assert len(scenario.player("bob").library) == 7 - 3


def test_lord_xander_dying_makes_the_opponent_sacrifice_half_their_nonland_permanents():
    scenario = _xander(bob_battlefield=["Grizzly Bears"] * 3 + ["Forest"] * 2)
    xander = scenario.put_onto_battlefield("Lord Xander, the Collector")
    scenario.will_choose_targets("bob", username="alice", source="Lord Xander, the Collector")
    _settle(scenario)
    scenario.game.destroy(xander)
    scenario.will_choose_targets("bob", username="alice", source="Lord Xander, the Collector")
    _settle(scenario)
    assert _count_named(scenario, "Grizzly Bears", "bob") == 2
    assert _count_named(scenario, "Forest", "bob") == 2


def test_terisian_mindbreaker_attack_mills_half_the_library_rounded_up():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Terisian Mindbreaker"])
        .player("bob", library=[CARD] * 7)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mindbreaker = scenario.creature("Terisian Mindbreaker", "alice")
    mindbreaker.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(mindbreaker)
    _settle(scenario)
    assert len(scenario.player("bob").library) == 7 - 4


def test_rush_of_dread_spree_modes_halve_creatures_hand_and_life_rounded_up():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Rush of Dread"], battlefield=["Swamp"] * 8)
        .player(
            "bob",
            hand=[CARD] * 3,
            life=15,
            battlefield=["Grizzly Bears"] * 3,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Rush of Dread")
    casting.choose_modes([1, 2, 3])
    casting.choose_targets(["bob", "bob", "bob"])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*(["Swamp"] * 8)))
    scenario.put_on_stack(casting)
    while scenario.game.stack:
        scenario.resolve_top()
    assert _count_named(scenario, "Grizzly Bears", "bob") == 1
    assert len(scenario.player("bob").hand) == 1
    assert scenario.player("bob").life == 15 - 8


# -- difference between two hand sizes ------------------------------------------


def _balance_of_power(alice_extra, bob_hand):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Balance of Power", *[CARD] * alice_extra],
            battlefield=["Island"] * 5,
            library=[CARD] * 8,
        )
        .player("bob", hand=[CARD] * bob_hand)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Balance of Power", *scenario.untapped_sources(*(["Island"] * 5)), targets=["bob"]
    )
    return scenario


def test_balance_of_power_draws_the_difference_when_the_opponent_has_more():
    scenario = _balance_of_power(alice_extra=1, bob_hand=5)
    assert len(scenario.player("alice").hand) == 1 + 4


def test_balance_of_power_draws_nothing_on_a_tie():
    scenario = _balance_of_power(alice_extra=2, bob_hand=2)
    assert len(scenario.player("alice").hand) == 2


def test_balance_of_power_draws_nothing_when_you_have_more():
    scenario = _balance_of_power(alice_extra=4, bob_hand=1)
    assert len(scenario.player("alice").hand) == 4


# -- an attack trigger pump counted per card in hand ----------------------------


def _staticaster(*, with_ral, hand):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ral's Staticaster", *(["Ral, Izzet Viceroy"] if with_ral else [])],
            hand=[CARD] * hand,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    staticaster = scenario.creature("Ral's Staticaster", "alice")
    staticaster.summoning_sick = False
    scenario.attack_with(staticaster)
    _settle(scenario)
    return scenario, staticaster


def test_rals_staticaster_gets_plus_one_power_per_card_in_hand_with_a_ral():
    scenario, staticaster = _staticaster(with_ral=True, hand=3)
    assert _pt(scenario, staticaster) == (3 + 3, 3)


def test_rals_staticaster_gets_nothing_without_a_ral_planeswalker():
    scenario, staticaster = _staticaster(with_ral=False, hand=3)
    assert _pt(scenario, staticaster) == (3, 3)


# -- a kicked rider scaled by a graveyard count ---------------------------------


def _tribute_to_urborg(*, kicked):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Tribute to Urborg"],
            battlefield=["Swamp", "Swamp", "Island", "Island"],
            graveyard=["Lightning Bolt", "Divination", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    casting = scenario.cast("Tribute to Urborg")
    if kicked:
        casting.pay_kicker()
    casting.choose_targets([dreadmaw])
    payment = casting.begin_paying()
    lands = ["Swamp", "Swamp", "Island", "Island"] if kicked else ["Swamp", "Swamp"]
    for source in scenario.untapped_sources(*lands):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario, dreadmaw


def test_tribute_to_urborg_unkicked_gives_only_the_flat_minus_two():
    scenario, dreadmaw = _tribute_to_urborg(kicked=False)
    assert _pt(scenario, dreadmaw) == (6 - 2, 6 - 2)


def test_tribute_to_urborg_kicked_adds_minus_one_per_instant_and_sorcery_in_the_graveyard():
    """The two spells in the graveyard count, the creature card does not, and
    the resolving spell is still on the stack so it is not counted."""
    scenario, dreadmaw = _tribute_to_urborg(kicked=True)
    assert _pt(scenario, dreadmaw) == (6 - 2 - 2, 6 - 2 - 2)


# -- a pair of clauses counting different players' hands ----------------------


def test_sword_of_war_and_peace_damages_per_their_hand_and_gains_per_your_hand():
    scenario, bears = _equipped("Sword of War and Peace", "Grizzly Bears", hand=2, bob_hand=5)
    bears.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()
    _settle(scenario)
    # 4 combat damage (2/2 plus the sword's +2/+2), then 5 from the sword
    assert scenario.player("bob").life == 20 - 4 - 5
    assert scenario.player("alice").life == 20 + 2


# -- look at the top X cards, X the cards in your hand --------------------------


def _soramaro(hand):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Descendant of Soramaro", "Island", "Island"],
            hand=[CARD] * hand,
            library=["Plains", "Swamp", "Mountain", "Island", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    descendant = scenario.creature("Descendant of Soramaro", "alice")
    scenario.activate(descendant, *scenario.untapped_sources("Island", "Island"))
    _settle(scenario)
    return scenario


def test_descendant_of_soramaro_looks_at_as_many_cards_as_are_in_your_hand():
    scenario = _soramaro(hand=3)
    asked = [q for q in scenario.questions_asked() if q.player == "alice"]
    assert len(asked[-1].cards) == 3
    assert [c.card.name for c in scenario.top_of_library(3)] == ["Plains", "Swamp", "Mountain"]


def test_descendant_of_soramaro_with_an_empty_hand_looks_at_nothing():
    scenario = _soramaro(hand=0)
    assert [c.card.name for c in scenario.top_of_library(2)] == ["Plains", "Swamp"]


# -- an equip cost scaled by the hand, and a combat pump scaled by it ---------------


def _vecna(*, hand, named_vecna=False):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grizzly Bears", "Hand of Vecna", *(["Vecna"] if named_vecna else [])],
            hand=[CARD] * hand,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    hand_of_vecna = scenario.find("Hand of Vecna", Zone.BATTLEFIELD, "alice")
    return scenario, bears, hand_of_vecna


def _life_equip(scenario, bears, hand_of_vecna):
    ability = next(
        a
        for a in keyword_abilities(effective_card(scenario.game, hand_of_vecna))
        if a.canonical == "Equip" and not a.cost_is_mana
    )
    activation = equip_activation(scenario.game, hand_of_vecna, bears, "alice", ability=ability)
    activation.begin_paying().pay()
    activation.activate()
    scenario.resolve_top()


def test_hand_of_vecna_life_equip_costs_one_life_per_card_in_your_hand():
    scenario, bears, hand_of_vecna = _vecna(hand=3)
    _life_equip(scenario, bears, hand_of_vecna)
    assert scenario.player("alice").life == 20 - 3
    assert hand_of_vecna.attached_to == bears.id


def test_hand_of_vecna_life_equip_with_an_empty_hand_is_free():
    scenario, bears, hand_of_vecna = _vecna(hand=0)
    _life_equip(scenario, bears, hand_of_vecna)
    assert scenario.player("alice").life == 20
    assert hand_of_vecna.attached_to == bears.id


def test_hand_of_vecna_pumps_the_equipped_creature_at_the_beginning_of_combat():
    scenario, bears, hand_of_vecna = _vecna(hand=3)
    _life_equip(scenario, bears, hand_of_vecna)
    scenario.advance()
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    _settle(scenario)
    assert _pt(scenario, bears) == (2 + 3, 2 + 3)


def test_hand_of_vecna_also_pumps_a_creature_named_vecna():
    scenario, bears, hand_of_vecna = _vecna(hand=2, named_vecna=True)
    _life_equip(scenario, bears, hand_of_vecna)
    base = _pt(scenario, scenario.creature("Vecna", "alice"))
    scenario.advance()
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    _settle(scenario)
    vecna = scenario.creature("Vecna", "alice")
    assert _pt(scenario, bears) == (2 + 2, 2 + 2)
    assert _pt(scenario, vecna) == (base[0] + 2, base[1] + 2)


# -- cast a spell free from hand, bounded by the damage dealt ---------------------


def _glamdring_hit(creature, hand):
    scenario, holder = _equipped("Glamdring", creature, hand=hand)
    holder.summoning_sick = False
    scenario.will_take_the_may(True, username="alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(holder)
    scenario.no_blocks()
    scenario.combat_damage()
    _settle(scenario)
    return scenario


def test_glamdring_casts_an_instant_or_sorcery_with_mana_value_up_to_the_damage_for_free():
    scenario = _glamdring_hit("Craw Wurm", ["Divination", "Grizzly Bears"])
    assert scenario.player("bob").life == 20 - 6
    names = [card.name for card in scenario.player("alice").hand]
    assert "Divination" not in names and len(names) == 1 + 2  # bears stays, drew two
    assert [c.name for c in scenario.player("alice").graveyard] == ["Divination"]


def test_glamdring_does_not_offer_a_spell_costing_more_than_the_damage():
    scenario = _glamdring_hit("Grizzly Bears", ["Divination"])
    assert [card.name for card in scenario.player("alice").hand] == ["Divination"]


# -- an animated land whose stats are a quoted count ---------------------------------


def _svogthos(graveyard, library=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Svogthos, the Restless Tomb",
                "Swamp",
                "Swamp",
                "Swamp",
                "Forest",
                "Forest",
            ],
            graveyard=list(graveyard),
            library=list(library),
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    land = scenario.find("Svogthos, the Restless Tomb", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        land,
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Forest", "Forest"),
        index=1,
    )
    scenario.resolve_top()
    return scenario, land


def test_svogthos_becomes_a_creature_sized_by_creature_cards_in_your_graveyard():
    scenario, land = _svogthos(["Grizzly Bears", "Grizzly Bears", "Lightning Bolt"])
    chars = scenario.game.computed_board().of(land)
    assert Type.CREATURE in chars.types and Type.LAND in chars.types
    assert (chars.power, chars.toughness) == (2, 2)
    assert set(chars.colors) == {Color.BLACK, Color.GREEN}
    assert {"Plant", "Zombie"} <= set(chars.subtypes)


def test_svogthos_follows_the_graveyard_as_it_changes():
    scenario, land = _svogthos(["Grizzly Bears"], library=["Grizzly Bears"])
    assert _pt(scenario, land) == (1, 1)
    scenario.game.put_into_graveyard(scenario.top_of_library(1)[0])
    assert _pt(scenario, land) == (2, 2)


# -- an "instead create X of those tokens" rider keyed to the cast zone ----------------


def _final_days(*, from_graveyard):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[] if from_graveyard else ["The Final Days"],
            graveyard=["The Final Days", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"]
            if from_graveyard
            else ["Grizzly Bears"],
            battlefield=["Swamp"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if not from_graveyard:
        scenario.cast_and_resolve("The Final Days", *scenario.untapped_sources(*(["Swamp"] * 4)))
        return scenario
    casting = scenario.cast("The Final Days", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*(["Swamp"] * 6)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario


def test_the_final_days_cast_from_hand_makes_two_tapped_horrors():
    scenario = _final_days(from_graveyard=False)
    horrors = [
        c for c in scenario.game.permanents_controlled_by("alice") if c.name == "Horror Token"
    ]
    assert len(horrors) == 2 and all(c.tapped for c in horrors)


def test_the_final_days_flashed_back_makes_one_horror_per_creature_card_in_your_graveyard():
    scenario = _final_days(from_graveyard=True)
    horrors = [
        c for c in scenario.game.permanents_controlled_by("alice") if c.name == "Horror Token"
    ]
    assert len(horrors) == 3 and all(c.tapped for c in horrors)


# -- an Aura's dies trigger: mill by the power, return itself and a milled creature ----


def _avatar_destiny_dies(*, take):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Avatar Destiny"],
            battlefield=["Grizzly Bears", "Forest", "Forest", "Forest", "Forest"],
            graveyard=["Grizzly Bears"],
            library=["Hill Giant", "Forest", "Craw Wurm", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Avatar Destiny",
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest"),
        targets=[bears],
    )
    # 2/2 plus one for the creature card in the graveyard: power 3
    giant, _, wurm = scenario.top_of_library(3)
    scenario.will_choose_cards(*([wurm] if take else []), username="alice")
    scenario.game.destroy(bears)
    _settle(scenario)
    return scenario, giant, wurm


def test_avatar_destiny_mills_by_the_creatures_power_returns_itself_and_a_milled_creature():
    scenario, giant, wurm = _avatar_destiny_dies(take=True)
    assert [c.name for c in scenario.player("alice").hand] == ["Avatar Destiny"]
    assert wurm.zone is Zone.BATTLEFIELD and wurm.controller == "alice"
    assert giant.zone is Zone.GRAVEYARD
    assert [c.name for c in scenario.top_of_library(2)] == ["Mountain", "Mountain"]


def test_avatar_destiny_may_take_no_milled_creature():
    scenario, giant, wurm = _avatar_destiny_dies(take=False)
    assert [c.name for c in scenario.player("alice").hand] == ["Avatar Destiny"]
    assert wurm.zone is Zone.GRAVEYARD and giant.zone is Zone.GRAVEYARD


# -- pawprint modes (CR 700.2i) ----------------------------------------------------


def _season_of_loss(modes):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Season of Loss"],
            battlefield=["Swamp"] * 5 + ["Grizzly Bears"],
            graveyard=["Grizzly Bears"],
            library=[CARD] * 6,
        )
        .player("bob", battlefield=["Hill Giant"], library=[CARD] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Season of Loss")
    casting.choose_modes(modes)
    return scenario, casting


def _resolve_season(scenario, casting):
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*(["Swamp"] * 5)))
    scenario.put_on_stack(casting)
    while scenario.game.stack:
        scenario.resolve_top()


def test_season_of_loss_sacrifice_then_drain_by_creature_cards_in_your_graveyard():
    scenario, casting = _season_of_loss([1, 3])
    _resolve_season(scenario, casting)
    assert _count_named(scenario, "Grizzly Bears", "alice") == 0
    assert _count_named(scenario, "Hill Giant", "bob") == 0
    # the creature already there plus the one just sacrificed
    assert scenario.player("bob").life == 20 - 2


def test_season_of_loss_draws_per_creature_that_died_under_your_control():
    scenario, casting = _season_of_loss([1, 2])
    _resolve_season(scenario, casting)
    assert len(scenario.player("alice").hand) == 1


def test_season_of_loss_may_repeat_a_mode_within_five_pawprints():
    scenario, casting = _season_of_loss([3, 1, 1])
    _resolve_season(scenario, casting)
    assert scenario.player("bob").life == 20 - 2


def test_season_of_loss_refuses_more_than_five_pawprints():
    scenario, casting = _season_of_loss([])
    with pytest.raises(ValueError, match="pawprint"):
        casting.choose_modes([3, 3])


def test_season_of_loss_refuses_a_repeat_total_over_budget():
    scenario, casting = _season_of_loss([])
    with pytest.raises(ValueError, match="pawprint"):
        casting.choose_modes([2, 2, 2])


# -- a Saga counting the hand, dropping the hand limit, then casting for free ----------


def _great_synthesis():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jin-Gitaxias", "Island", "Island", "Island", "Island", "Grizzly Bears"],
            hand=[CARD] * 5 + ["Divination"] * 2,
            library=[CARD] * 30,
        )
        .player("bob", battlefield=["Hill Giant"], library=[CARD] * 30)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jin = scenario.creature("Jin-Gitaxias", "alice")
    scenario.activate(jin, *scenario.untapped_sources("Island", "Island", "Island", "Island"))
    scenario.resolve_top()
    return scenario


def _to_main_of(scenario, username):
    scenario.advance()
    while not (
        scenario.step is Step.PRECOMBAT_MAIN and scenario.game.active_player.username == username
    ):
        scenario.advance()
        scenario.game.put_triggers_on_stack()
        while scenario.stack_names():
            scenario.pass_until_resolved()


def test_jin_gitaxias_transforms_into_a_saga_whose_first_chapter_draws_a_hand_and_lifts_the_limit():
    scenario = _great_synthesis()
    _settle(scenario)
    names = [c.name for c in scenario.game.permanents_controlled_by("alice")]
    assert "The Great Synthesis" in names
    assert len(scenario.player("alice").hand) == 14
    assert scenario.player("alice").has_no_maximum_hand_size


def test_the_great_synthesis_second_chapter_returns_every_non_phyrexian_creature():
    scenario = _great_synthesis()
    _settle(scenario)
    _to_main_of(scenario, "bob")
    _to_main_of(scenario, "alice")
    _settle(scenario)
    assert _count_named(scenario, "Grizzly Bears", "alice") == 0
    assert _count_named(scenario, "Hill Giant", "bob") == 0
    assert "Hill Giant" in [c.name for c in scenario.player("bob").hand]


def test_the_great_synthesis_third_chapter_casts_spells_free_and_returns_front_face_up():
    scenario = _great_synthesis()
    _settle(scenario)
    _to_main_of(scenario, "bob")
    _to_main_of(scenario, "alice")
    _settle(scenario)
    _to_main_of(scenario, "bob")
    divinations = [c for c in scenario.player("alice").hand if c.name == "Divination"]
    scenario.will_choose_cards(divinations[0], username="alice")
    scenario.will_choose_cards(divinations[1], username="alice")
    scenario.will_choose_cards(username="alice")
    hand_before = len(scenario.player("alice").hand)
    _to_main_of(scenario, "alice")
    _settle(scenario)
    # two Divinations cast free: out of the hand, each drawing two (plus the turn's draw)
    assert len([c for c in scenario.player("alice").hand if c.name == "Divination"]) == 0
    assert len(scenario.player("alice").hand) == hand_before + 1 - 2 + 4
    names = [c.name for c in scenario.game.permanents_controlled_by("alice")]
    assert "Jin-Gitaxias" in names and "The Great Synthesis" not in names


# -- Epic (CR 702.50) -----------------------------------------------------------------
#
# CR 702.50a, read with `mise run rules:find 702.50` in this session: epic is
# two spell abilities. "For the rest of the game, you can't cast spells", and
# "at the beginning of each of your upkeeps for the rest of the game, copy this
# spell except for its epic ability. If the spell has any targets, you may
# choose new targets for the copy." CR 702.50b: a player can't cast spells once
# a spell with epic they control resolves, but effects can still put copies of
# spells onto the stack.


def _snakes(scenario, username="alice"):
    return len(
        [c for c in scenario.game.permanents_controlled_by(username) if c.name == "Snake Token"]
    )


def _epic_swarm(hand=3):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Endless Swarm", "Grizzly Bears", *[CARD] * (hand - 1)],
            battlefield=["Forest"] * 8,
            library=[CARD] * 12,
        )
        .player("bob", library=[CARD] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Endless Swarm", *scenario.untapped_sources(*(["Forest"] * 8)))
    return scenario


def test_endless_swarm_makes_a_snake_per_card_in_hand_when_cast():
    scenario = _epic_swarm(hand=3)
    assert _snakes(scenario) == 3


def test_a_resolved_epic_spell_stops_its_controller_casting_spells():
    scenario = _epic_swarm()
    with pytest.raises(ValueError, match="epic"):
        scenario.cast("Grizzly Bears")


def test_epic_copies_the_spell_at_each_of_your_upkeeps_without_epic_itself():
    scenario = _epic_swarm(hand=3)
    _advance_to_upkeep_of(scenario, "bob")
    _settle(scenario)
    assert _snakes(scenario) == 3  # not an upkeep of alice's
    _advance_to_upkeep_of(scenario, "alice")
    _settle(scenario)
    assert _snakes(scenario) == 3 + 3  # the copy counts the hand again
    scenario.game.player("alice").hand.pop()
    _advance_to_upkeep_of(scenario, "bob")
    _advance_to_upkeep_of(scenario, "alice")
    _settle(scenario)
    # one copy a turn: the first copy made no delayed trigger of its own (CR 702.50a)
    # (hand: 3 cards, plus the turn's draw, less the one just removed)
    assert _snakes(scenario) == 6 + len(scenario.player("alice").hand)


def test_a_copy_of_an_epic_spell_keeps_copying_after_it_ceases_to_exist():
    """CR 702.50a, CR 707.10a: a copy of an epic spell (Reverberate on it) has
    epic too, so when it resolves it makes its own upkeep trigger, and that
    trigger outlives the copy, which ceases to exist as it leaves the stack."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Endless Swarm", CARD, CARD],
            battlefield=["Forest"] * 8,
            library=[CARD] * 12,
        )
        .player("bob", library=[CARD] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swarm = scenario.cast_onto_stack(
        "Endless Swarm", *scenario.untapped_sources(*(["Forest"] * 8)), username="alice"
    )
    copy = scenario.game.copy_spell(swarm, controller="alice")
    scenario.resolve_top()  # the copy: two cards in hand, two snakes
    scenario.resolve_top()  # the original
    assert _snakes(scenario) == 4
    assert copy not in scenario.game.stack
    hand_before = len(scenario.player("alice").hand)
    _advance_to_upkeep_of(scenario, "bob")
    _advance_to_upkeep_of(scenario, "alice")
    _settle(scenario)
    # two delayed triggers (one per resolved epic spell), each copy counting the hand
    assert _snakes(scenario) == 4 + 2 * hand_before  # upkeep is before the draw


def _epic_torment():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Neverending Torment", CARD, CARD],
            battlefield=["Swamp"] * 6,
            library=[CARD] * 12,
        )
        .player("bob", library=["Plains"] * 3 + ["Island"] * 3 + ["Swamp"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Neverending Torment", *scenario.untapped_sources(*(["Swamp"] * 6)), targets=["bob"]
    )
    return scenario


def test_neverending_torment_exiles_a_card_per_card_in_hand_from_the_targets_library():
    scenario = _epic_torment()
    assert len(scenario.player("bob").library) == 10 - 2
    assert len(scenario.game.exile) == 2


def test_neverending_torment_copy_at_upkeep_searches_again_with_a_new_hand_count():
    scenario = _epic_torment()
    _advance_to_upkeep_of(scenario, "bob")
    _advance_to_upkeep_of(scenario, "alice")
    _settle(scenario)
    assert len(scenario.game.exile) == 4
    assert len(scenario.player("bob").library) == 10 - 2 - 2 - 1  # bob drew a card in between


def test_neverending_torment_copy_may_take_a_new_target():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Neverending Torment", CARD, CARD],
            battlefield=["Swamp"] * 6,
            library=[CARD] * 12,
        )
        .player("bob", library=["Plains"] * 6)
        .player("carol", library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Neverending Torment", *scenario.untapped_sources(*(["Swamp"] * 6)), targets=["bob"]
    )
    assert len(scenario.player("bob").library) == 6 - 2
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets("carol", username="alice")
    _advance_to_upkeep_of(scenario, "alice")
    _settle(scenario)
    # each opponent drew a card on the way round; the copy exiled two from carol only
    assert len(scenario.player("carol").library) == 6 - 1 - 2
    assert len(scenario.player("bob").library) == 6 - 2 - 1


# -- proof printings (not task cards): a graveyard count with an "if you do" self-exile ------


def _spider_dies(*, take):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Skyfisher Spider"],
            graveyard=["Grizzly Bears", "Hill Giant", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spider = scenario.creature("Skyfisher Spider", "alice")
    scenario.will_take_the_may(take, username="alice")
    scenario.game.destroy(spider)
    _settle(scenario)
    return scenario, spider


def test_skyfisher_spider_dies_gains_life_per_creature_card_in_graveyard_and_exiles_itself():
    scenario, spider = _spider_dies(take=True)
    # two creature cards already there, plus the Spider itself
    assert scenario.player("alice").life == 20 + 3
    assert spider.zone is Zone.EXILE


def test_skyfisher_spider_declined_leaves_itself_in_the_graveyard():
    scenario, spider = _spider_dies(take=False)
    assert scenario.player("alice").life == 20
    assert spider.zone is Zone.GRAVEYARD


# -- proof printing (not a task card): half of a player's creatures returned, rounded up ---


def _split_the_party(*, bob_creatures):
    scenario = (
        Scenario()
        .player("alice", hand=["Split the Party"], battlefield=["Island"] * 5)
        .player("bob", battlefield=list(bob_creatures))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_split_the_party_returns_half_the_targets_creatures_rounded_up_your_choice():
    scenario = _split_the_party(bob_creatures=["Grizzly Bears", "Hill Giant", "Craw Wurm"])
    giant = scenario.creature("Hill Giant", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.will_choose_cards(giant, wurm, username="alice")
    scenario.cast_and_resolve(
        "Split the Party", *scenario.untapped_sources(*(["Island"] * 5)), targets=["bob"]
    )
    assert sorted(card.name for card in scenario.player("bob").hand) == ["Craw Wurm", "Hill Giant"]
    assert [c.name for c in scenario.game.permanents_controlled_by("bob")] == ["Grizzly Bears"]


def test_split_the_party_with_one_creature_returns_it_and_with_none_does_nothing():
    scenario = _split_the_party(bob_creatures=["Grizzly Bears"])
    scenario.cast_and_resolve(
        "Split the Party", *scenario.untapped_sources(*(["Island"] * 5)), targets=["bob"]
    )
    assert [card.name for card in scenario.player("bob").hand] == ["Grizzly Bears"]
    scenario = _split_the_party(bob_creatures=[])
    scenario.cast_and_resolve(
        "Split the Party", *scenario.untapped_sources(*(["Island"] * 5)), targets=["bob"]
    )
    assert scenario.player("bob").hand == []
