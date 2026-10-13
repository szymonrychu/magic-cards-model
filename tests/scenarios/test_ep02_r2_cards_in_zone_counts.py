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

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import keyword_abilities
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.machines.zone_grants import effective_card
from magic_cards_model.models import Zone

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
            hand=[CARD] * hand,
            graveyard=list(alice_gy),
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
