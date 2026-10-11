"""Scenario: a group defined by lacking a counter - "Each other creature you
control without a +1/+1 counter on it has outlast {G/W}." (Arcus Acolyte,
CR 613.1f, CR 702.107a, CR 611.3a): a creature drops out of the group the moment
a counter lands on it and re-enters when it is gone.
"""

from magic_cards_model.machines.keywords import keyword_abilities
from magic_cards_model.machines.zone_grants import effective_card
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def has_outlast(scenario, state):
    return any(
        line.lower().startswith("outlast")
        for line in scenario.game.characteristics_of(state).abilities
    )


def board(alice, bob=()):
    return (
        Scenario()
        .player("alice", battlefield=list(alice))
        .player("bob", battlefield=list(bob))
        .build()
    )


def test_another_creature_without_a_counter_has_outlast():
    scenario = board(["Arcus Acolyte", "Grizzly Bears"], ["Grizzly Bears"])
    assert has_outlast(scenario, scenario.creature("Grizzly Bears", "alice"))
    assert not has_outlast(scenario, scenario.creature("Grizzly Bears", "bob"))


def test_the_acolyte_does_not_grant_itself_a_second_outlast():
    scenario = board(["Arcus Acolyte"])
    lines = scenario.game.characteristics_of(scenario.creature("Arcus Acolyte")).abilities
    assert sum(1 for line in lines if line.lower().startswith("outlast")) == 1


def test_a_counter_removes_the_grant_and_losing_it_restores_it():
    scenario = board(["Arcus Acolyte", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    assert not has_outlast(scenario, bears)
    bears.remove_counters(Counter.PLUS_ONE, 1)
    assert has_outlast(scenario, bears)


def test_a_different_counter_kind_does_not_matter():
    scenario = board(["Arcus Acolyte", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")
    scenario.game.add_counters(bears, Counter.CHARGE if hasattr(Counter, "CHARGE") else "charge", 1)
    assert has_outlast(scenario, bears)


def test_the_granted_outlast_is_read_by_the_keyword_machine():
    scenario = board(["Arcus Acolyte", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")
    card = effective_card(scenario.game, bears)
    assert any(a.canonical.lower() == "outlast" for a in keyword_abilities(card))
