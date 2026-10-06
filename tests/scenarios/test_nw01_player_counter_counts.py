"""Scenario: counts of counters on players - "for each poison counter your
opponents have", "the number of <kind> counters you have".

CR 122.1 - a counter is a marker placed on an object *or player*; CR 122.1f
names poison, and energy (CR 107.14) and experience are the other kinds
players carry. The count is read once, as the effect applies (CR 608.2h).

Real printings (all legal in Modern):

- Phyrexian Swarmlord - "create a 1/1 ... Insect token with infect for each
  poison counter your opponents have" (the opponents' total).
- Mycosynth Fiend - "gets +1/+1 for each poison counter your opponents have",
  a static pump re-counted continuously (CR 613.4c).
- Whispering Specter - "that player discards a card for each poison counter
  they have" (the one player the anaphor names).
- Vraska, Betrayal's Sting - "they get a number of poison counters equal to
  the difference" between nine and the poison the target already has.

The reader itself is also exercised for every counter kind a player can hold
(poison, energy, experience, rad, ticket) and every player set the oracle
text uses, straight through `count_expression`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.effects.amounts import count_expression
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _insects(scenario, username: str = "alice") -> list:
    return [
        state
        for state in scenario.game.battlefield
        if state.name == "Phyrexian Insect Token" and state.controller == username
    ]


def _poison(scenario, username: str, amount: int) -> None:
    scenario.game.add_player_counters(scenario.player(username), Counter.POISON, amount)


def _swarmlord_upkeep(poison: dict[str, int], opponents: tuple[str, ...] = ("bob",)):
    scenario = Scenario().player("alice", battlefield=["Phyrexian Swarmlord"])
    for name in opponents:
        scenario = scenario.player(name)
    played = scenario.build()
    for name, amount in poison.items():
        if amount:
            _poison(played, name, amount)
    played.advance()  # untap -> upkeep
    assert played.step is Step.UPKEEP
    played.pass_until_resolved()
    return played


# --------------------------------------------------------------------------
# Phyrexian Swarmlord
# --------------------------------------------------------------------------


def test_swarmlord_makes_one_insect_per_poison_counter_the_opponent_has():
    scenario = _swarmlord_upkeep({"bob": 3})
    assert len(_insects(scenario)) == 3


def test_swarmlord_makes_none_when_no_opponent_has_poison():
    scenario = _swarmlord_upkeep({"bob": 0})
    assert _insects(scenario) == []


def test_swarmlord_sums_every_opponent_and_ignores_its_own_controller():
    scenario = _swarmlord_upkeep({"alice": 4, "bob": 2, "carol": 3}, ("bob", "carol"))
    assert len(_insects(scenario)) == 5


def test_swarmlord_tokens_have_infect():
    scenario = _swarmlord_upkeep({"bob": 1})
    (insect,) = _insects(scenario)
    assert has_keyword(insect, Keyword.INFECT)


# --------------------------------------------------------------------------
# Mycosynth Fiend
# --------------------------------------------------------------------------


def _fiend_power(poison: dict[str, int], opponents=("bob",)) -> int:
    scenario = Scenario().player("alice", battlefield=["Mycosynth Fiend"])
    for name in opponents:
        scenario = scenario.player(name)
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    for name, amount in poison.items():
        if amount:
            _poison(played, name, amount)
    fiend = played.creature("Mycosynth Fiend", "alice")
    return played.game.computed_board().of(fiend).power


def test_mycosynth_fiend_is_a_plain_2_2_against_a_clean_opponent():
    assert _fiend_power({"bob": 0}) == 2


def test_mycosynth_fiend_grows_by_the_opponents_poison():
    assert _fiend_power({"bob": 4}) == 6


def test_mycosynth_fiend_totals_opponents_and_not_its_controller():
    assert _fiend_power({"alice": 5, "bob": 1, "carol": 2}, ("bob", "carol")) == 5


# --------------------------------------------------------------------------
# Whispering Specter
# --------------------------------------------------------------------------


def test_whispering_specter_discards_one_card_per_poison_counter_they_have():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Whispering Specter"])
        .player("bob", hand=["Forest"] * 5, library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    _poison(scenario, "bob", 2)
    specter = scenario.creature("Whispering Specter", "alice")
    hand = list(scenario.game.player("bob").hand)
    scenario.attack_with(specter)
    scenario.no_blocks()
    scenario.will_take_the_may(True, username="alice")
    # 2 poison before + 1 infect damage = 3 poison counters, so 3 discards.
    scenario.will_discard(*hand[:3], username="bob")
    scenario.combat_damage()
    scenario.pass_until_resolved()
    assert scenario.player("bob").poison == 3
    assert specter.zone is Zone.GRAVEYARD
    assert len(scenario.game.player("bob").hand) == 2


# --------------------------------------------------------------------------
# Vraska, Betrayal's Sting: "a number of poison counters equal to the difference"
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("have", "expect"), [(0, 9), (4, 9), (8, 9)])
def test_vraska_ultimate_brings_the_target_up_to_nine_poison(have, expect):
    scenario = (
        Scenario().player("alice", battlefield=["Vraska, Betrayal's Sting"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vraska = scenario.find("Vraska, Betrayal's Sting", Zone.BATTLEFIELD, "alice")
    vraska.counters.add("loyalty", 5)
    if have:
        _poison(scenario, "bob", have)
    scenario.will_choose_targets("bob", username="alice")
    scenario.activate(vraska, index=2)
    scenario.pass_until_resolved()
    assert scenario.player("bob").poison == expect


def test_vraska_ultimate_does_nothing_to_a_player_already_at_nine():
    scenario = (
        Scenario().player("alice", battlefield=["Vraska, Betrayal's Sting"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vraska = scenario.find("Vraska, Betrayal's Sting", Zone.BATTLEFIELD, "alice")
    vraska.counters.add("loyalty", 5)
    _poison(scenario, "bob", 9)
    scenario.will_choose_targets("bob", username="alice")
    scenario.activate(vraska, index=2)
    scenario.pass_until_resolved()
    assert scenario.player("bob").poison == 9


# --------------------------------------------------------------------------
# The reader itself: every counter kind, every player set
# --------------------------------------------------------------------------


def _two_player_game(**counters_by_player):
    scenario = Scenario().player("alice").player("bob").player("carol").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for username, kinds in counters_by_player.items():
        for kind, amount in kinds.items():
            scenario.game.add_player_counters(scenario.player(username), kind, amount)
    return scenario.game


@pytest.mark.parametrize(
    "kind", [Counter.POISON, Counter.ENERGY, Counter.EXPERIENCE, "rad", "ticket"]
)
def test_you_have_reads_the_controllers_own_counters(kind):
    game = _two_player_game(alice={kind: 3}, bob={kind: 5})
    reader = count_expression(f"the number of {kind} counters you have")
    assert reader is not None
    assert reader(game, "alice") == 3
    assert reader(game, "bob") == 5


@pytest.mark.parametrize(
    "kind", [Counter.POISON, Counter.ENERGY, Counter.EXPERIENCE, "rad", "ticket"]
)
def test_your_opponents_total_sums_every_other_player(kind):
    game = _two_player_game(alice={kind: 7}, bob={kind: 2}, carol={kind: 3})
    reader = count_expression(f"{kind} counter your opponents have")
    assert reader is not None
    assert reader(game, "alice") == 5
    assert reader(game, "bob") == 10


def test_total_among_players_counts_everyone():
    game = _two_player_game(alice={"rad": 3}, bob={"rad": 4}, carol={"rad": 1})
    reader = count_expression("the total number of rad counters among players")
    assert reader is not None
    assert reader(game, "alice") == 8
    reader = count_expression("the total number of rad counters among all players")
    assert reader(game, "carol") == 8


def test_a_player_with_no_counters_counts_zero():
    game = _two_player_game()
    reader = count_expression("the number of experience counters you have")
    assert reader(game, "alice") == 0
