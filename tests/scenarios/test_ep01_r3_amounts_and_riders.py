"""EP-01 R3 T8: variable amounts ("for each counter on it", "equal to ...",
"that much") and the damage / life / destroy riders that read an event.

One section per template; each listed card plus a second printing of a
different wording, so the reader is proven and not the one sentence.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
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
    return len(
        [c for c in scenario.game.permanents_controlled_by(username) if c.card.name == name]
    )


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
    blockers = [
        scenario.game.permanents_controlled_by("bob")[i] for i in range(len(blocker_names))
    ]
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
    scenario = _board(["Zagras, Thief of Heartbeats", *attackers], ["Ajani Unrelenting"],
                      step=Step.DECLARE_ATTACKERS)
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
