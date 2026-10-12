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
        .player("alice", battlefield=list(attacker_names))
        .player("bob", battlefield=list(blocker_names))
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
