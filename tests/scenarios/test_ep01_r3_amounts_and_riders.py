"""EP-01 R3 T8: variable amounts ("for each counter on it", "equal to ...",
"that much") and the damage / life / destroy riders that read an event.

One section per template; each listed card plus a second printing of a
different wording, so the reader is proven and not the one sentence.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter, TargetRef
from tests.scenarios.harness import Scenario


def _settle(scenario, limit=12):
    """Put triggers on the stack and resolve until the stack is empty."""
    for _ in range(limit):
        scenario.game.put_triggers_on_stack()
        if not scenario.stack_names():
            return
        scenario.pass_until_resolved()
    raise AssertionError(f"stack never emptied: {scenario.stack_names()}")


def _count(scenario, name, username="alice"):
    return len([c for c in scenario.game.permanents_controlled_by(username) if c.card.name == name])


# -- "for each counter on it" (any kind), on the departing / sacrificed source


def test_kinsbaile_borderguard_dies_makes_a_token_per_counter_of_any_kind():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Kinsbaile Borderguard"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guard = scenario.creature("Kinsbaile Borderguard", "alice")
    guard.add_counters(Counter.PLUS_ONE, 2)
    guard.add_counters("charge", 1)
    scenario.game.put_into_graveyard(guard)
    _settle(scenario)
    assert _count(scenario, "Kithkin Soldier Token") == 3


def test_kinsbaile_borderguard_with_no_counters_makes_no_token():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Kinsbaile Borderguard"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.put_into_graveyard(scenario.creature("Kinsbaile Borderguard", "alice"))
    _settle(scenario)
    assert _count(scenario, "Kithkin Soldier Token") == 0


def test_twitching_doll_sacrifice_makes_a_spider_per_nest_counter():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Twitching Doll"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    doll = scenario.creature("Twitching Doll", "alice")
    doll.add_counters("nest", 3)
    scenario.activate(doll, index=1, sacrificing=[doll])
    _settle(scenario)
    assert _count(scenario, "Spider Token") == 3


# -- "equal to the number of other creatures you control named ~"


def _enter_from_hand(names_on_board, name, opponent_board=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[name], battlefield=list(names_on_board))
        .player("bob", battlefield=list(opponent_board))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(name, "alice")
    _settle(scenario)
    return scenario


def test_hare_apparent_makes_a_rabbit_per_other_hare_apparent():
    scenario = _enter_from_hand(["Hare Apparent", "Hare Apparent"], "Hare Apparent")
    assert _count(scenario, "Rabbit Token") == 2


def test_hare_apparent_alone_makes_no_rabbit():
    scenario = _enter_from_hand([], "Hare Apparent")
    assert _count(scenario, "Rabbit Token") == 0


def test_hare_apparent_ignores_an_opponents_hare_and_other_names():
    scenario = _enter_from_hand(
        ["Grizzly Bears", "Hare Apparent"], "Hare Apparent", opponent_board=["Hare Apparent"]
    )
    assert _count(scenario, "Rabbit Token") == 1


# -- "+1/+1 until end of turn for each creature (it's blocking | blocking it)"


def _combat(attacker_names, blocker_names, blocks):
    """alice attacks with `attacker_names`; `blocks` is [(blocker index, attacker index)]."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(attacker_names), library=["Forest"] * 5)
        .player("bob", battlefield=list(blocker_names), library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attackers = [
        scenario.game.permanents_controlled_by("alice")[i] for i in range(len(attacker_names))
    ]
    blockers = [scenario.game.permanents_controlled_by("bob")[i] for i in range(len(blocker_names))]
    scenario.attack_with(*attackers)
    scenario.game.declare_blockers([(blockers[b], attackers[a]) for b, a in blocks])
    return scenario, attackers, blockers


def test_guardian_of_the_gateless_grows_for_each_creature_it_blocks():
    scenario, _attackers, (guardian,) = _combat(
        ["Hill Giant"] * 3, ["Guardian of the Gateless"], [(0, 0), (0, 1), (0, 2)]
    )
    base = guardian.card.power
    _settle(scenario)
    assert (guardian.power, guardian.toughness) == (
        int(base) + 3,
        int(guardian.card.toughness) + 3,
    )


def test_guardian_of_the_gateless_blocking_one_creature_gets_one():
    scenario, _a, (guardian,) = _combat(["Hill Giant"] * 2, ["Guardian of the Gateless"], [(0, 0)])
    base = int(guardian.card.power)
    _settle(scenario)
    assert guardian.power == base + 1


def test_elvish_berserker_gets_a_bonus_for_each_creature_blocking_it():
    scenario, (berserker,), _blockers = _combat(
        ["Elvish Berserker"], ["Grizzly Bears"] * 3, [(0, 0), (1, 0), (2, 0)]
    )
    base = int(berserker.card.power)
    _settle(scenario)
    assert berserker.power == base + 3


def test_elvish_berserker_blocked_by_one_gets_one():
    scenario, (berserker,), _b = _combat(["Elvish Berserker"], ["Grizzly Bears"], [(0, 0)])
    base = int(berserker.card.power)
    _settle(scenario)
    assert berserker.power == base + 1


# -- event referents: "that creature", "destroy that planeswalker"


def test_nessian_boar_blocker_controller_draws_a_card():
    scenario, _a, _b = _combat(["Nessian Boar"], ["Grizzly Bears"], [(0, 0)])
    bob_hand = len(scenario.game.player("bob").hand)
    _settle(scenario)
    assert len(scenario.game.player("bob").hand) == bob_hand + 1
    assert len(scenario.game.player("alice").hand) == 0


def test_nessian_boar_draws_once_per_blocker():
    scenario, _a, _b = _combat(["Nessian Boar"], ["Grizzly Bears"] * 2, [(0, 0), (1, 0)])
    before = len(scenario.game.player("bob").hand)
    _settle(scenario)
    assert len(scenario.game.player("bob").hand) == before + 2


def test_evil_eye_of_urborg_destroys_each_creature_that_blocks_it():
    scenario, _a, (bears,) = _combat(["Evil Eye of Urborg"], ["Grizzly Bears"], [(0, 0)])
    _settle(scenario)
    assert bears.zone is Zone.GRAVEYARD


def test_evil_eye_of_urborg_spares_creatures_that_do_not_block():
    scenario, _a, blockers = _combat(
        ["Evil Eye of Urborg"], ["Grizzly Bears", "Hill Giant"], [(0, 0)]
    )
    _settle(scenario)
    assert blockers[0].zone is Zone.GRAVEYARD
    assert blockers[1].zone is Zone.BATTLEFIELD


# -- damage / life event riders: "that much", "half their life", "destroy that planeswalker"


def _board(alice, bob, *, step=Step.PRECOMBAT_MAIN, bob_life=20, alice_life=20):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), library=["Forest"] * 6, life=alice_life)
        .player("bob", battlefield=list(bob), library=["Forest"] * 6, life=bob_life)
        .build()
    )
    scenario.start_at(step)
    return scenario


def _alice(scenario, name):
    return scenario.find(name, Zone.BATTLEFIELD, "alice")


def _bob(scenario, name):
    return scenario.find(name, Zone.BATTLEFIELD, "bob")


def _combat_at_walker(attackers):
    scenario = _board(
        ["Zagras, Thief of Heartbeats", *attackers],
        ["Ajani Unrelenting"],
        step=Step.DECLARE_ATTACKERS,
    )
    return scenario


def test_zagras_destroys_a_planeswalker_dealt_combat_damage_by_your_creature():
    scenario = _combat_at_walker(["Elvish Berserker"])
    ajani = _bob(scenario, "Ajani Unrelenting")
    scenario.attack_with(_alice(scenario, "Elvish Berserker"), defending=ajani)
    scenario.no_blocks()
    scenario.combat_damage()
    _settle(scenario)
    assert ajani.zone is Zone.GRAVEYARD


def test_zagras_ignores_combat_damage_dealt_to_a_player():
    scenario = _combat_at_walker(["Elvish Berserker"])
    scenario.attack_with(_alice(scenario, "Elvish Berserker"))
    scenario.no_blocks()
    scenario.combat_damage()
    _settle(scenario)
    assert _bob(scenario, "Ajani Unrelenting").zone is Zone.BATTLEFIELD


def test_zagras_ignores_noncombat_damage_to_a_planeswalker():
    scenario = _combat_at_walker([])
    ajani = _bob(scenario, "Ajani Unrelenting")
    scenario.game.deal_damage(ajani, 1, source=_alice(scenario, "Zagras, Thief of Heartbeats"))
    _settle(scenario)
    assert ajani.zone is Zone.BATTLEFIELD


def test_zagras_ignores_a_planeswalker_hit_by_an_opponents_creature():
    scenario = _board(["Ajani Unrelenting", "Zagras, Thief of Heartbeats"], ["Elvish Berserker"])
    ajani = _alice(scenario, "Ajani Unrelenting")
    scenario.game.deal_damage(ajani, 1, source=_bob(scenario, "Elvish Berserker"))
    _settle(scenario)
    assert ajani.zone is Zone.BATTLEFIELD


def test_visions_of_brutality_costs_the_enchanted_creatures_controller_that_much_life():
    scenario = _board(["Visions of Brutality"], ["Grizzly Bears"])
    bears = _bob(scenario, "Grizzly Bears")
    _alice(scenario, "Visions of Brutality").attach_to(bears)
    scenario.game.deal_damage(scenario.player("alice"), 2, source=bears)
    _settle(scenario)
    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 18


def test_visions_of_brutality_counts_damage_to_creatures_too():
    scenario = _board(["Visions of Brutality", "Hill Giant"], ["Grizzly Bears"])
    bears = _bob(scenario, "Grizzly Bears")
    _alice(scenario, "Visions of Brutality").attach_to(bears)
    scenario.game.deal_damage(_alice(scenario, "Hill Giant"), 2, source=bears)
    _settle(scenario)
    assert scenario.player("bob").life == 18


def test_visions_of_brutality_ignores_other_creatures():
    scenario = _board(["Visions of Brutality", "Hill Giant"], ["Grizzly Bears", "Elvish Berserker"])
    _alice(scenario, "Visions of Brutality").attach_to(_bob(scenario, "Grizzly Bears"))
    scenario.game.deal_damage(
        scenario.player("alice"), 2, source=_bob(scenario, "Elvish Berserker")
    )
    _settle(scenario)
    assert scenario.player("bob").life == 20


def test_grievous_wound_enchanted_player_loses_half_their_remaining_life_rounded_up():
    scenario = _board(["Grievous Wound", "Hill Giant"], [])
    _alice(scenario, "Grievous Wound").attach_to(scenario.player("bob"))
    scenario.game.deal_damage(scenario.player("bob"), 3, source=_alice(scenario, "Hill Giant"))
    _settle(scenario)
    assert scenario.player("bob").life == 8  # 17, then half of 17 rounded up (9) lost


def test_grievous_wound_ignores_damage_to_other_players():
    scenario = _board(["Grievous Wound", "Hill Giant"], [])
    _alice(scenario, "Grievous Wound").attach_to(scenario.player("bob"))
    scenario.game.deal_damage(scenario.player("alice"), 3, source=_alice(scenario, "Hill Giant"))
    _settle(scenario)
    assert scenario.player("alice").life == 17


def test_grievous_wound_enchanted_player_cannot_gain_life():
    scenario = _board(["Grievous Wound"], [])
    wound = _alice(scenario, "Grievous Wound")
    wound.attach_to(scenario.player("bob"))
    scenario.game.gain_life(scenario.player("bob"), 5)
    assert scenario.player("bob").life == 20
    scenario.game.gain_life(scenario.player("alice"), 5)
    assert scenario.player("alice").life == 25


def test_lich_s_tomb_sacrifices_a_permanent_for_each_life_lost():
    scenario = _board(["Lich's Tomb", "Forest", "Forest", "Grizzly Bears"], [])
    forests = [c for c in scenario.game.permanents_controlled_by("alice") if c.name == "Forest"]
    scenario.will_choose_cards(*forests, username="alice")
    scenario.game.lose_life(scenario.player("alice"), 2)
    _settle(scenario)
    assert [c.name for c in scenario.game.permanents_controlled_by("alice")] == [
        "Lich's Tomb",
        "Grizzly Bears",
    ]


def test_lich_s_tomb_sacrifices_everything_when_the_loss_exceeds_the_board():
    scenario = _board(["Lich's Tomb", "Forest"], [])
    scenario.game.lose_life(scenario.player("alice"), 5)
    _settle(scenario)
    assert scenario.game.permanents_controlled_by("alice") == []


# -- group pumps over a state: "attacking creatures", "other modified creatures"


def test_thunderstaff_pumps_every_attacking_creature_and_nothing_else():
    scenario = _board(
        ["Thunderstaff", "Elvish Berserker", "Hill Giant", "Forest", "Forest"],
        ["Grizzly Bears"],
        step=Step.DECLARE_ATTACKERS,
    )
    berserker = _alice(scenario, "Elvish Berserker")
    giant = _alice(scenario, "Hill Giant")
    scenario.attack_with(berserker)
    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.activate(_alice(scenario, "Thunderstaff"), *forests)
    scenario.pass_until_resolved()
    assert berserker.power == int(berserker.card.power) + 1
    assert giant.power == int(giant.card.power)
    assert _bob(scenario, "Grizzly Bears").power == int(_bob(scenario, "Grizzly Bears").card.power)


def test_thunderstaff_pumps_an_opponents_attackers_too():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", battlefield=["Elvish Berserker"], library=["Forest"] * 6)
        .player("alice", battlefield=["Thunderstaff", "Forest", "Forest"], library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    berserker = _bob(scenario, "Elvish Berserker")
    scenario.attack_with(berserker, defending="alice")
    scenario.pass_priority("bob")
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.activate(_alice(scenario, "Thunderstaff"), *forests, username="alice")
    scenario.pass_until_resolved()
    assert berserker.power == int(berserker.card.power) + 1


# -- "destroy all other creatures that were dealt damage this turn"


def test_death_rattle_oni_destroys_only_creatures_dealt_damage_this_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Death-Rattle Oni"], battlefield=["Hill Giant"], library=["Forest"])
        .player("bob", battlefield=["Grizzly Bears", "Elvish Berserker"], library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hurt_mine, hurt_theirs = _alice(scenario, "Hill Giant"), _bob(scenario, "Grizzly Bears")
    unhurt = _bob(scenario, "Elvish Berserker")
    scenario.game.deal_damage(hurt_mine, 1, source=unhurt)
    scenario.game.deal_damage(hurt_theirs, 1, source=hurt_mine)
    scenario.put_onto_battlefield("Death-Rattle Oni", "alice")
    _settle(scenario)
    assert hurt_mine.zone is Zone.GRAVEYARD  # "all other", whoever controls it
    assert hurt_theirs.zone is Zone.GRAVEYARD
    assert unhurt.zone is Zone.BATTLEFIELD
    oni = _alice(scenario, "Death-Rattle Oni")
    assert oni.zone is Zone.BATTLEFIELD  # "other"


def test_golden_tail_trainer_pumps_other_modified_creatures_by_its_power():
    scenario = _board(
        ["Golden-Tail Trainer", "Hill Giant", "Grizzly Bears"],
        ["Elvish Berserker"],
        step=Step.DECLARE_ATTACKERS,
    )
    trainer = _alice(scenario, "Golden-Tail Trainer")
    modified = _alice(scenario, "Hill Giant")
    modified.add_counters(Counter.PLUS_ONE, 1)
    plain = _alice(scenario, "Grizzly Bears")
    opposing = _bob(scenario, "Elvish Berserker")
    opposing.add_counters(Counter.PLUS_ONE, 1)
    before = (modified.power, plain.power, opposing.power, trainer.power)
    scenario.attack_with(trainer)
    _settle(scenario)
    x = trainer.power
    assert modified.power == before[0] + x
    assert modified.toughness == int(modified.card.toughness) + 1 + x
    assert plain.power == before[1]
    assert opposing.power == before[2]
    assert trainer.power == before[3]


# -- amounts read off the trigger's event: "that creature's power", "its mana value"


def test_terror_of_the_peaks_deals_damage_equal_to_the_entering_creatures_power():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Hill Giant"],
            battlefield=["Terror of the Peaks"],
            library=["Forest"] * 3,
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_targets(scenario.player("bob"), username="alice")
    scenario.put_onto_battlefield("Hill Giant", "alice")
    _settle(scenario)
    assert scenario.player("bob").life == 20 - 3


def test_terror_of_the_peaks_ignores_an_opponents_creature_entering():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Terror of the Peaks"], library=["Forest"] * 3)
        .player("bob", hand=["Hill Giant"], library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Hill Giant", "bob")
    _settle(scenario)
    assert scenario.player("bob").life == 20


def test_teval_cast_trigger_costs_life_equal_to_the_spells_mana_value():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Serra Angel"],
            battlefield=["Teval, Arbiter of Virtue"] + ["Plains"] * 5,
            library=["Forest"] * 3,
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Plains"] * 5))
    scenario.cast_onto_stack("Serra Angel", *sources)
    _settle(scenario)
    assert scenario.player("alice").life == 20 - 5


# -- Folio of Fancies: no maximum hand size for anyone; mill equal to a hand


def test_folio_of_fancies_each_opponent_mills_cards_equal_to_their_hand():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Folio of Fancies", "Island", "Island", "Island"],
            library=["Forest"] * 3,
        )
        .player("bob", hand=["Forest"] * 4, library=["Mountain"] * 9)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Island", "Island", "Island")
    scenario.activate(_alice(scenario, "Folio of Fancies"), *lands, index=1)
    scenario.pass_until_resolved()
    assert len(scenario.game.player("bob").library) == 9 - 4
    assert len(scenario.game.player("alice").library) == 3


def test_folio_of_fancies_removes_every_players_maximum_hand_size():
    scenario = _board(["Folio of Fancies"], [])
    for name in ("alice", "bob"):
        assert scenario.game.player(name).has_no_maximum_hand_size


def test_without_folio_of_fancies_the_maximum_stays():
    scenario = _board([], [])
    assert not scenario.game.player("bob").has_no_maximum_hand_size


# -- "Put a <kind> counter on target creature ... Its controller draws a card"


def test_gwafa_hazid_bribes_a_creature_and_its_controller_draws():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Gwafa Hazid, Profiteer", "Plains", "Island"])
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gwafa = scenario.creature("Gwafa Hazid, Profiteer", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    hand_before = len(scenario.player("bob").hand)
    scenario.activate(gwafa, auto=True, targets=[bears])
    _settle(scenario)
    assert bears.counter_count("bribery") == 1
    assert len(scenario.player("bob").hand) == hand_before + 1
    assert len(scenario.player("alice").hand) == 0


# -- "Draw a card, then you may return a land you control to its owner's hand"


def _kefnet_scenario():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Kefnet the Mindful", "Island", "Island", "Island", "Island", "Forest"],
            library=["Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_kefnet_draws_then_may_return_a_land():
    scenario = _kefnet_scenario()
    kefnet = scenario.creature("Kefnet the Mindful", "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(forest)
    scenario.activate(kefnet, auto=True)
    _settle(scenario)
    assert scenario.find("Forest", Zone.HAND, "alice")
    assert len(scenario.player("alice").hand) == 2


def test_kefnet_may_decline_to_return_a_land():
    scenario = _kefnet_scenario()
    kefnet = scenario.creature("Kefnet the Mindful", "alice")
    scenario.will_choose_cards()
    scenario.activate(kefnet, auto=True)
    _settle(scenario)
    assert len(scenario.player("alice").hand) == 1
    assert scenario.find("Forest", Zone.BATTLEFIELD, "alice")


# -- "Mill seven cards. Then put all cards that have an Adventure from among
# -- the milled cards into your hand" (Seek Thrills)


def test_seek_thrills_mills_seven_and_takes_every_adventure_card():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Beluna Grandsquall // Seek Thrills"],
            battlefield=["Forest"] * 3 + ["Island"] * 2 + ["Mountain"] * 2,
            library=[
                "Bonecrusher Giant // Stomp",
                "Forest",
                "Brazen Borrower // Petty Theft",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Murderous Rider",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Beluna Grandsquall // Seek Thrills")
    casting.cast_as_adventure()
    payment = casting.begin_paying()
    payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    hand = {c.card.name for c in scenario.player("alice").hand}
    assert hand == {"Bonecrusher Giant // Stomp", "Brazen Borrower // Petty Theft"}
    assert len(scenario.player("alice").library) == 1
    assert scenario.find("Murderous Rider", Zone.LIBRARY, "alice")


# -- "Draw a card, then discard a card. When you discard a card this way,
# -- target player mills cards equal to its mana value" (The Ancient One)


def _ancient_one_scenario(hand):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hand,
            battlefield=["The Ancient One", "Island", "Island", "Swamp", "Swamp"],
            library=["Forest"],
        )
        .player("bob", library=["Plains"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_ancient_one_mills_the_target_by_the_discarded_cards_mana_value():
    scenario = _ancient_one_scenario(["Serra Angel"])
    one = scenario.find("The Ancient One", Zone.BATTLEFIELD, "alice")
    scenario.will_discard(scenario.find("Serra Angel", Zone.HAND, "alice"))
    scenario.will_choose_targets("bob")
    scenario.activate(one, auto=True)
    _settle(scenario)
    assert len(scenario.player("bob").library) == 10 - 5
    assert scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")


def test_the_ancient_one_with_a_land_discard_mills_nothing():
    scenario = _ancient_one_scenario(["Forest"])
    one = scenario.find("The Ancient One", Zone.BATTLEFIELD, "alice")
    scenario.will_discard(scenario.find("Forest", Zone.HAND, "alice"))
    scenario.will_choose_targets("bob")
    scenario.activate(one, auto=True)
    _settle(scenario)
    assert len(scenario.player("bob").library) == 10


# -- "Until end of turn, target creature you control gets +1/+0, gains "...",
# -- and can attack as though it didn't have defender" (The Pride of Hull Clade)


def test_the_pride_of_hull_clade_attacks_despite_defender_and_draws_by_toughness():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["The Pride of Hull Clade", "Island", "Island", "Island", "Island"],
            library=["Forest"] * 40,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hull = scenario.creature("The Pride of Hull Clade", "alice")
    assert not scenario.can_attack(hull)
    scenario.activate(hull, auto=True, targets=[hull])
    _settle(scenario)
    assert scenario.can_attack(hull)
    power, toughness = scenario.game.power_of(hull), scenario.game.toughness_of(hull)
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(hull)
    scenario.no_blocks()
    scenario.combat_damage()
    _settle(scenario)
    assert scenario.player("bob").life == 20 - power
    assert len(scenario.player("alice").hand) == toughness


# -- "At the beginning of the chosen player's upkeep, this artifact deals X
# -- damage to that player, where X is 3 minus the number of cards in their hand"


def _rack_at_bobs_upkeep(bob_hand):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["The Rack"])
        .player("bob", hand=bob_hand, library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("bob", username="alice", source="The Rack")
    scenario.put_onto_battlefield("The Rack")
    while not (scenario.step is Step.UPKEEP and scenario.game.active_player.username == "bob"):
        scenario.advance()
    return scenario


def test_the_rack_deals_three_minus_hand_size_at_the_chosen_players_upkeep():
    scenario = _rack_at_bobs_upkeep(["Forest", "Forest"])
    _settle(scenario)
    assert scenario.player("bob").life == 20 - 1


def test_the_rack_deals_nothing_to_a_full_hand_and_not_at_its_controllers_upkeep():
    scenario = _rack_at_bobs_upkeep(["Forest"] * 3)
    _settle(scenario)
    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20


# -- "Crew 1. Activate only once each turn." and "create a Treasure token for
# -- each creature that crewed it this turn" (Luxurious Locomotive)


def _crew(scenario, vehicle, *creatures):
    from magic_cards_model.machines.keywords import crew_activation

    activation = crew_activation(scenario.game, vehicle, list(creatures), "alice")
    refusal = activation.why_not()
    if refusal is not None:
        raise ValueError(refusal)
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()


def _locomotive_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Luxurious Locomotive", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_luxurious_locomotive_makes_a_treasure_per_creature_that_crewed_it():
    scenario = _locomotive_board()
    train = scenario.find("Luxurious Locomotive", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    _crew(scenario, train, *bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(train)
    _settle(scenario)
    assert _count(scenario, "Treasure Token") == 2


def test_luxurious_locomotive_crews_only_once_each_turn():
    scenario = _locomotive_board()
    train = scenario.find("Luxurious Locomotive", Zone.BATTLEFIELD)
    first, second, _third = scenario.creatures(
        "Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice"
    )
    _crew(scenario, train, first)
    with pytest.raises(ValueError, match="only once each turn"):
        _crew(scenario, train, second)


# -- "For each {W}{W} spent to cast this creature, put a +1/+1 counter on each
# -- of them" (Clay Champion) and "for each {U}{U} spent to cast it, ..."
# -- (Bladecoil Serpent)


def _cast_with_x(scenario, name, x_value, lands):
    casting = scenario.cast(name, "alice")
    casting.x_value = x_value
    payment = casting.begin_paying()
    scenario.pay_with(payment, *lands)
    scenario.put_on_stack(casting)


def test_clay_champion_counts_each_ww_and_gg_spent_to_cast_it():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Clay Champion"],
            battlefield=["Plains"] * 4 + ["Forest"] * 2 + ["Grizzly Bears", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", "Forest", "Forest")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    scenario.will_choose_targets(*bears, source="Clay Champion")
    _cast_with_x(scenario, "Clay Champion", 2, lands)
    scenario.resolve_top()
    _settle(scenario)
    champion = scenario.creature("Clay Champion", "alice")
    assert champion.counter_count(Counter.PLUS_ONE) == 3  # one {G}{G}, three each
    assert [bear.counter_count(Counter.PLUS_ONE) for bear in bears] == [2, 2]  # two {W}{W}


def test_clay_champion_with_no_ww_spent_adds_no_counters_to_the_targets():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Clay Champion"],
            battlefield=["Forest"] * 6 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources(*["Forest"] * 6)
    (bear,) = scenario.creatures("Grizzly Bears", username="alice")
    scenario.will_choose_targets(bear, source="Clay Champion")
    _cast_with_x(scenario, "Clay Champion", 2, lands)
    scenario.resolve_top()
    _settle(scenario)
    assert bear.counter_count(Counter.PLUS_ONE) == 0
    assert scenario.creature("Clay Champion", "alice").counter_count(Counter.PLUS_ONE) == 9


def test_bladecoil_serpent_draws_discards_and_pumps_per_mana_pair():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bladecoil Serpent"],
            battlefield=["Island"] * 2 + ["Swamp"] * 2 + ["Mountain"] * 2,
            library=["Forest", "Forest"],
        )
        .player("bob", hand=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Island", "Island", "Swamp", "Swamp", "Mountain", "Mountain")
    _cast_with_x(scenario, "Bladecoil Serpent", 0, lands)
    scenario.resolve_top()
    _settle(scenario)
    serpent = scenario.creature("Bladecoil Serpent", "alice")
    assert len(scenario.player("alice").hand) == 1
    assert len(scenario.player("bob").hand) == 1
    assert scenario.game.power_of(serpent) == 6


# -- "Whenever a source you control deals noncombat damage to an opponent, this
# -- creature deals that much damage to target creature or planeswalker that
# -- player controls" (Chandra's Incinerator)


def _incinerator_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Chandra's Incinerator", "Grizzly Bears"])
        .player("bob", battlefield=["Serra Angel", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_chandras_incinerator_repeats_noncombat_damage_to_an_opponents_creature():
    scenario = _incinerator_board()
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets(angel, source="Chandra's Incinerator")
    scenario.game.deal_damage(scenario.player("bob"), 3, source=bears)
    _settle(scenario)
    assert angel.damage == 3
    assert scenario.player("bob").life == 17


def test_chandras_incinerator_ignores_combat_damage_and_damage_to_its_controller():
    scenario = _incinerator_board()
    angel = scenario.creature("Serra Angel", "bob")
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.deal_damage(scenario.player("alice"), 2, source=bob_bears)
    _settle(scenario)
    assert angel.damage == 0
    assert scenario.player("alice").life == 18


# -- "Spells you cast have delve" (Teval, Arbiter of Virtue)


def _teval_board(with_teval):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            graveyard=["Mountain", "Mountain"],
            battlefield=["Forest", *(["Teval, Arbiter of Virtue"] if with_teval else [])],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_teval_lets_the_spells_you_cast_delve():
    from magic_cards_model.machines.objects_as_costs import delve

    scenario = _teval_board(with_teval=True)
    casting = scenario.cast("Grizzly Bears")
    payment = casting.begin_paying()
    delve(payment, casting.spell, scenario.player("alice").graveyard[0])
    scenario.pay_with(payment, *scenario.untapped_sources("Forest"))
    scenario.put_on_stack(casting)
    _settle(scenario)
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD
    assert len(scenario.player("alice").graveyard) == 1


def test_without_teval_a_plain_spell_cannot_delve():
    from magic_cards_model.machines.objects_as_costs import delve

    scenario = _teval_board(with_teval=False)
    casting = scenario.cast("Grizzly Bears")
    payment = casting.begin_paying()
    with pytest.raises(ValueError, match="delve"):
        delve(payment, casting.spell, scenario.player("alice").graveyard[0])


# -- "Spells your opponents cast that target this creature cost an additional 3
# -- life to cast" (Terror of the Peaks)


def _terror_board(alice_life=20):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            life=alice_life,
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Terror of the Peaks", "Grizzly Bears"], hand=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_terror_of_the_peaks_makes_an_opponents_targeting_spell_cost_three_life():
    scenario = _terror_board()
    terror = scenario.creature("Terror of the Peaks", "bob")
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[terror]
    )
    assert scenario.player("alice").life == 17


def test_terror_of_the_peaks_does_not_tax_a_spell_aimed_elsewhere():
    scenario = _terror_board()
    other = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[other]
    )
    assert scenario.player("alice").life == 20


def test_terror_of_the_peaks_taxed_spell_cannot_be_cast_without_the_life():
    scenario = _terror_board(alice_life=2)
    terror = scenario.creature("Terror of the Peaks", "bob")
    with pytest.raises(ValueError):
        scenario.cast_onto_stack(
            "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[terror]
        )


def test_terror_of_the_peaks_does_not_tax_its_own_controllers_spells():
    scenario = _terror_board()
    terror = scenario.creature("Terror of the Peaks", "bob")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    taxed = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    aimed = [TargetRef.coerce(terror)]
    assert scenario.game.static_life_costs_for(bolt, "bob", aimed) == []
    assert [life for life, _source in scenario.game.static_life_costs_for(taxed, "alice", aimed)] == [3]


# -- "As this enchantment enters, note your life total. At the beginning of your
# -- upkeep, draw a card if your life total is greater than or equal to the last
# -- noted life total for this enchantment. Then note your life total."
# -- (Sigarda's Splendor)


def _splendor_upkeep(life_after_entering):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Sigarda's Splendor"], library=["Forest"] * 6)
        .player("bob", library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    splendor = scenario.put_onto_battlefield("Sigarda's Splendor")
    scenario.player("alice").life = life_after_entering
    return scenario, splendor


def _advance_to_alices_upkeep(scenario):
    scenario.advance()
    while not (scenario.step is Step.UPKEEP and scenario.game.active_player.username == "alice"):
        scenario.advance()


def test_sigardas_splendor_draws_when_life_is_not_below_the_noted_total_and_renotes():
    scenario, splendor = _splendor_upkeep(life_after_entering=23)
    assert splendor.choice.value == "20"
    hand_before = len(scenario.player("alice").hand)
    _advance_to_alices_upkeep(scenario)
    _settle(scenario)
    assert len(scenario.player("alice").hand) == hand_before + 1
    assert splendor.choice.value == "23"


def test_sigardas_splendor_does_not_draw_when_life_fell_below_the_noted_total():
    scenario, splendor = _splendor_upkeep(life_after_entering=17)
    hand_before = len(scenario.player("alice").hand)
    _advance_to_alices_upkeep(scenario)
    _settle(scenario)
    assert len(scenario.player("alice").hand) == hand_before
    assert splendor.choice.value == "17"
