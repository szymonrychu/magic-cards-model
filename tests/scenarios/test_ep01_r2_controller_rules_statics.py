"""Scenario: Melira, Sylvok Outcast's two other static lines - "You can't get
poison counters." (CR 122.6, CR 101.2, a controller-only, one-kind form of
Solemnity's prohibition) and "Creatures your opponents control lose infect."
(CR 613.1f, a group keyword loss).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def duel(alice, bob):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice))
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_controller_cannot_get_poison_counters():
    scenario = duel(["Melira, Sylvok Outcast"], [])
    scenario.game.add_player_counters("alice", Counter.POISON, 3)
    assert scenario.player("alice").counter_count(Counter.POISON) == 0


def test_the_opponent_still_gets_poison_counters():
    scenario = duel(["Melira, Sylvok Outcast"], [])
    scenario.game.add_player_counters("bob", Counter.POISON, 3)
    assert scenario.player("bob").counter_count(Counter.POISON) == 3


def test_only_poison_is_refused_not_other_player_counters():
    scenario = duel(["Melira, Sylvok Outcast"], [])
    scenario.game.add_player_counters("alice", Counter.ENERGY, 2)
    assert scenario.player("alice").counter_count(Counter.ENERGY) == 2


def test_poison_returns_when_melira_leaves():
    scenario = duel(["Melira, Sylvok Outcast"], [])
    scenario.game.put_into_graveyard(scenario.creature("Melira, Sylvok Outcast"))
    scenario.game.add_player_counters("alice", Counter.POISON, 1)
    assert scenario.player("alice").counter_count(Counter.POISON) == 1


def test_opponents_creatures_lose_infect():
    scenario = duel(["Melira, Sylvok Outcast", "Grizzly Bears"], ["Glistener Elf"])
    elf = scenario.creature("Glistener Elf", "bob")
    assert not has_keyword(elf, "infect", scenario.game)


def test_my_own_infect_creatures_keep_it():
    scenario = duel(["Melira, Sylvok Outcast", "Glistener Elf"], [])
    elf = scenario.creature("Glistener Elf", "alice")
    assert has_keyword(elf, "infect", scenario.game)
