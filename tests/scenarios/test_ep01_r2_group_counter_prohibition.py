"""Scenario: a static ability that stops a group of creatures from having one
kind of counter put on them - "Creatures your opponents control can't have
+1/+1 counters put on them." (Blightbeetle) and "Creatures you control can't
have -1/-1 counters put on them." (Melira, Sylvok Outcast).

CR 122.6 routes every counter placement through one event; CR 101.2 makes the
"can't" win; CR 604.2 / CR 611.3a keep the group live. Only the named kind and
only the named controller's creatures are protected, and the effect ends with
its source.
"""

from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def board(alice, bob):
    return (
        Scenario()
        .player("alice", battlefield=list(alice))
        .player("bob", battlefield=list(bob))
        .build()
    )


def put(scenario, state, kind, amount=1):
    scenario.game.add_counters(state, kind, amount)
    return state.counter_count(kind)


def test_an_opponents_creature_cannot_get_a_plus_one_counter():
    scenario = board(["Blightbeetle", "Grizzly Bears"], ["Grizzly Bears"])
    mine, theirs = (scenario.creature("Grizzly Bears", u) for u in ("alice", "bob"))
    assert put(scenario, theirs, Counter.PLUS_ONE) == 0
    assert put(scenario, mine, Counter.PLUS_ONE) == 1


def test_only_the_named_kind_is_blocked():
    scenario = board(["Blightbeetle"], ["Grizzly Bears"])
    theirs = scenario.creature("Grizzly Bears", "bob")
    assert put(scenario, theirs, Counter.MINUS_ONE) == 1


def test_the_prohibition_ends_when_the_source_leaves():
    scenario = board(["Blightbeetle"], ["Grizzly Bears"])
    theirs = scenario.creature("Grizzly Bears", "bob")
    assert put(scenario, theirs, Counter.PLUS_ONE) == 0
    scenario.game.put_into_graveyard(scenario.creature("Blightbeetle"))
    assert put(scenario, theirs, Counter.PLUS_ONE) == 1


def test_melira_protects_her_controllers_creatures_from_minus_one_counters():
    scenario = board(["Melira, Sylvok Outcast", "Grizzly Bears"], ["Grizzly Bears"])
    mine, theirs = (scenario.creature("Grizzly Bears", u) for u in ("alice", "bob"))
    assert put(scenario, mine, Counter.MINUS_ONE) == 0
    assert put(scenario, theirs, Counter.MINUS_ONE) == 1
    assert put(scenario, mine, Counter.PLUS_ONE) == 1
