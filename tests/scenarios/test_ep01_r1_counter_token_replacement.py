"""EP-01 round 1, task 6: counter and token replacement statics (CR 614.16,
CR 122.6, CR 701.7b).

Counters are raised through a real `Game.add_counters`; tokens through the real
`create_tokens` / `create_predefined_tokens` choke point. Every shape has its
negative: a permanent the subject does not name, another controller, a token or
counter kind it does not read.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models.token import PREDEFINED, TokenDefinition, create_tokens
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice, bob=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice), library=["Island"] * 5)
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _handled(name, containing="would"):
    outcomes = [o for o in classify_clauses(card(name)) if containing in o.text]
    assert outcomes
    assert {o.category for o in outcomes} == {HANDLED}, outcomes


def _on_battlefield(scenario, name):
    return [c for c in scenario.game.battlefield if c.name == name]


# -- "that many plus one +1/+1 counters" ----------------------------------------


def test_caradora_adds_one_counter_to_a_creature_you_control():
    scenario = _board(["Caradora, Heart of Alacria", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, "+1/+1", 2)

    assert bears.counter_count("+1/+1") == 3


def test_caradora_leaves_an_opponents_creature_alone():
    scenario = _board(["Caradora, Heart of Alacria"], ["Grizzly Bears"])
    theirs = scenario.creature("Grizzly Bears", "bob")

    scenario.game.add_counters(theirs, "+1/+1", 2)

    assert theirs.counter_count("+1/+1") == 2


def test_caradora_reads_only_the_named_counter_kind():
    scenario = _board(["Caradora, Heart of Alacria", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, "-1/-1", 2)

    assert bears.counter_count("-1/-1") == 2


def test_mowu_only_affects_itself():
    scenario = _board(["Mowu, Loyal Companion", "Grizzly Bears"])
    mowu = scenario.creature("Mowu, Loyal Companion", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(mowu, "+1/+1", 1)
    scenario.game.add_counters(bears, "+1/+1", 1)

    assert mowu.counter_count("+1/+1") == 2
    assert bears.counter_count("+1/+1") == 1


def test_mauhur_reads_a_subtype_list():
    scenario = _board(["Mauhúr, Uruk-hai Captain", "Goblin Guide", "Grizzly Bears"])
    goblin = scenario.creature("Goblin Guide", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(goblin, "+1/+1", 1)
    scenario.game.add_counters(bears, "+1/+1", 1)

    assert goblin.counter_count("+1/+1") == 2
    assert bears.counter_count("+1/+1") == 1


def test_loading_zone_doubles_every_kind_on_its_listed_permanents():
    scenario = _board(["Loading Zone", "Grizzly Bears"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")

    scenario.game.add_counters(bears, "+1/+1", 2)
    scenario.game.add_counters(bears, "shield", 1)
    scenario.game.add_counters(theirs, "+1/+1", 2)

    assert bears.counter_count("+1/+1") == 4
    assert bears.counter_count("shield") == 2
    assert theirs.counter_count("+1/+1") == 2


# -- tokens --------------------------------------------------------------------


def _make(scenario, definition, who="alice", count=1):
    return create_tokens(scenario.game, definition, who, count)


def test_xorn_adds_a_treasure_to_treasure_creation_only():
    scenario = _board(["Xorn"])
    _make(scenario, PREDEFINED["Treasure"])
    assert len(_on_battlefield(scenario, "Treasure Token")) == 2

    _make(scenario, PREDEFINED["Food"])
    assert len(_on_battlefield(scenario, "Food Token")) == 1


def test_xorn_does_not_help_the_opponent():
    scenario = _board(["Xorn"])
    _make(scenario, PREDEFINED["Treasure"], who="bob")
    assert len(_on_battlefield(scenario, "Treasure Token")) == 1


def test_worldwalker_helm_adds_a_map_to_artifact_tokens():
    scenario = _board(["Worldwalker Helm"])
    _make(scenario, PREDEFINED["Treasure"])
    assert len(_on_battlefield(scenario, "Map Token")) == 1

    _make(scenario, TokenDefinition(power=1, toughness=1, subtypes=("Soldier",)))
    assert len(_on_battlefield(scenario, "Map Token")) == 1  # a creature token: no


def test_peregrin_took_adds_a_food_to_any_token_you_create():
    scenario = _board(["Peregrin Took"])
    _make(scenario, TokenDefinition(power=1, toughness=1, subtypes=("Soldier",)))
    assert len(_on_battlefield(scenario, "Food Token")) == 1


def test_academy_manufactor_makes_one_of_each():
    scenario = _board(["Academy Manufactor"])
    _make(scenario, PREDEFINED["Treasure"])
    assert [len(_on_battlefield(scenario, n)) for n in ("Clue Token", "Food Token", "Treasure Token")] == [1, 1, 1]


def test_academy_manufactor_ignores_other_tokens():
    scenario = _board(["Academy Manufactor"])
    _make(scenario, TokenDefinition(power=1, toughness=1, subtypes=("Soldier",)))
    assert _on_battlefield(scenario, "Clue Token") == []


def test_jinnie_fay_may_swap_for_cats_or_dogs():
    scenario = _board(["Jinnie Fay, Jetmir's Second"])
    scenario.will_choose("Cat Token", username="alice")
    _make(scenario, TokenDefinition(power=1, toughness=1, subtypes=("Soldier",)), count=2)
    assert len([c for c in scenario.game.battlefield if "Cat" in c.name]) == 2

    scenario = _board(["Jinnie Fay, Jetmir's Second"])
    scenario.will_choose("keep", username="alice")
    _make(scenario, TokenDefinition(power=1, toughness=1, subtypes=("Soldier",)))
    assert [c for c in scenario.game.battlefield if "Cat" in c.name] == []


@pytest.mark.parametrize(
    "name",
    [
        "Caradora, Heart of Alacria",
        "Mauhúr, Uruk-hai Captain",
        "Mowu, Loyal Companion",
        "Loading Zone",
        "Xorn",
        "Worldwalker Helm",
        "Peregrin Took",
        "Academy Manufactor",
        "Jinnie Fay, Jetmir's Second",
    ],
)
def test_counter_and_token_lines_are_handled(name):
    _handled(name)
