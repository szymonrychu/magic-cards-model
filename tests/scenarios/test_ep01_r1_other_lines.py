"""EP-01 round 1, task 6 review fix: the non-replacement lines that share a card
with a replacement static.

Each test plays the line through the engine and asserts the outcome, with the
negative (the condition or controller that must not apply) beside it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice, bob=(), **kwargs):
    alice_kwargs = {k[6:]: v for k, v in kwargs.items() if k.startswith("alice_")}
    bob_kwargs = {k[4:]: v for k, v in kwargs.items() if k.startswith("bob_")}
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice), **alice_kwargs)
        .player("bob", battlefield=list(bob), **bob_kwargs)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _clause_handled(name, containing):
    outcomes = [o for o in classify_clauses(card(name)) if containing in o.text]
    assert outcomes, (name, containing)
    assert {o.category for o in outcomes} == {HANDLED}, outcomes


def _next_turn(scenario):
    """Advance step by step (so cleanup really runs) into the next turn."""
    start = scenario.turn.turn_number
    while scenario.turn.turn_number == start:
        scenario.advance()


def _abilities(scenario, permanent):
    return [a.lower() for a in scenario.game.characteristics_of(permanent).abilities]


# -- Living Conundrum: "As long as there are no cards in your library, ..." ----


def test_living_conundrum_is_ten_ten_flying_vigilance_with_an_empty_library():
    scenario = _board(["Living Conundrum"], alice_library=[])
    conundrum = scenario.creature("Living Conundrum", "alice")

    assert (conundrum.power, conundrum.toughness) == (10, 10)
    assert "flying" in _abilities(scenario, conundrum)
    assert "vigilance" in _abilities(scenario, conundrum)
    _clause_handled("Living Conundrum", "As long as there are no cards")


def test_living_conundrum_keeps_its_printed_size_while_the_library_has_a_card():
    scenario = _board(["Living Conundrum"], alice_library=["Island"])
    conundrum = scenario.creature("Living Conundrum", "alice")

    assert (conundrum.power, conundrum.toughness) == (2, 5)
    assert "flying" not in _abilities(scenario, conundrum)


def test_living_conundrum_reads_its_controllers_library_not_the_opponents():
    scenario = _board(["Living Conundrum"], alice_library=["Island"], bob_library=[])
    conundrum = scenario.creature("Living Conundrum", "alice")

    assert conundrum.power != 10


# -- Necromancer's Magemark: "Creatures you control that are enchanted get +1/+1."


def test_magemark_pumps_enchanted_creatures_you_control():
    scenario = _board(["Necromancer's Magemark", "Grizzly Bears", "Llanowar Elves"])
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    base_bears = (bears.power, bears.toughness)
    base_elves = (elves.power, elves.toughness)
    scenario.find("Necromancer's Magemark", Zone.BATTLEFIELD, "alice").attach_to(bears)

    assert (bears.power, bears.toughness) == (base_bears[0] + 1, base_bears[1] + 1)
    assert (elves.power, elves.toughness) == base_elves
    _clause_handled("Necromancer's Magemark", "get +1/+1")


def test_magemark_does_not_pump_an_enchanted_creature_an_opponent_controls():
    scenario = _board(["Necromancer's Magemark"], ["Grizzly Bears"])
    theirs = scenario.creature("Grizzly Bears", "bob")
    base = (theirs.power, theirs.toughness)
    scenario.find("Necromancer's Magemark", Zone.BATTLEFIELD, "alice").attach_to(theirs)

    assert (theirs.power, theirs.toughness) == base


# -- Knight of the Holy Nimbus: "{2}: This creature can't be regenerated this turn."


def _knight_board():
    scenario = _board(
        ["Knight of the Holy Nimbus"],
        ["Mountain", "Mountain"],
        alice_library=["Island"] * 10,
        bob_library=["Island"] * 10,
    )
    knight = scenario.creature("Knight of the Holy Nimbus", "alice")
    return scenario, knight


def test_an_opponents_payment_stops_the_knight_regenerating_this_turn():
    scenario, knight = _knight_board()
    scenario.pass_priority("alice")
    scenario.activate(
        knight, *scenario.untapped_sources("Mountain", "Mountain", username="bob"), username="bob"
    )
    scenario.pass_until_resolved()

    scenario.game.destroy(knight)

    assert knight.zone is Zone.GRAVEYARD
    _clause_handled("Knight of the Holy Nimbus", "can't be regenerated")


def test_the_knight_regenerates_when_nobody_paid():
    scenario, knight = _knight_board()

    scenario.game.destroy(knight)

    assert knight.zone is Zone.BATTLEFIELD


def test_the_knight_regenerates_again_next_turn():
    scenario, knight = _knight_board()
    scenario.pass_priority("alice")
    scenario.activate(
        knight, *scenario.untapped_sources("Mountain", "Mountain", username="bob"), username="bob"
    )
    scenario.pass_until_resolved()
    _next_turn(scenario)

    scenario.game.destroy(knight)

    assert knight.zone is Zone.BATTLEFIELD


# -- Darigaaz Reincarnated: the egg-counter upkeep ----------------------------


def _upkeep_of(scenario, username):
    """Advance step by step until `username`'s upkeep triggers have been put on
    the stack, then resolve them."""
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == username):
        scenario.advance()
    scenario.pass_until_resolved()


def _darigaaz_board():
    scenario = _board(
        ["Darigaaz Reincarnated"], alice_library=["Island"] * 10, bob_library=["Island"] * 10
    )
    darigaaz = scenario.creature("Darigaaz Reincarnated", "alice")
    scenario.game.destroy(darigaaz)
    assert darigaaz.zone is Zone.EXILE
    return scenario, darigaaz


def test_darigaaz_loses_an_egg_counter_each_of_its_owners_upkeeps_and_returns_at_none():
    scenario, darigaaz = _darigaaz_board()

    _upkeep_of(scenario, "bob")  # an opponent's upkeep does nothing
    assert darigaaz.counter_count("egg") == 3

    _upkeep_of(scenario, "alice")
    assert (darigaaz.zone, darigaaz.counter_count("egg")) == (Zone.EXILE, 2)
    _upkeep_of(scenario, "bob")
    _upkeep_of(scenario, "alice")
    assert (darigaaz.zone, darigaaz.counter_count("egg")) == (Zone.EXILE, 1)
    _upkeep_of(scenario, "bob")
    _upkeep_of(scenario, "alice")

    assert darigaaz.zone is Zone.BATTLEFIELD
    _clause_handled("Darigaaz Reincarnated", "egg counter")


def test_a_darigaaz_exiled_without_egg_counters_never_returns():
    scenario = _board(
        [], alice_exile=["Darigaaz Reincarnated"], alice_library=["Island"] * 10,
        bob_library=["Island"] * 10,
    )
    darigaaz = scenario.find("Darigaaz Reincarnated", Zone.EXILE, "alice")

    _upkeep_of(scenario, "bob")
    _upkeep_of(scenario, "alice")

    assert darigaaz.zone is Zone.EXILE


# -- Lisette, Dean of the Root: "Whenever you gain life, you may pay {1}. ..." -


def _lisette_board(**kwargs):
    from magic_cards_model.machines.effects import transform_permanent

    scenario = _board(
        ["Valentin, Dean of the Vein", "Grizzly Bears", "Forest"], ["Llanowar Elves"], **kwargs
    )
    valentin = scenario.creature("Valentin, Dean of the Vein", "alice")
    transform_permanent(scenario.game, valentin)
    assert valentin.name == "Lisette, Dean of the Root"
    return scenario


def test_lisette_pays_one_to_grow_and_trample_every_creature_you_control():
    scenario = _lisette_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.will_pay_the_mana_cost(True, username="alice")

    scenario.game.gain_life("alice", 2)
    scenario.pass_until_resolved()

    assert bears.counter_count("+1/+1") == 1
    assert "trample" in _abilities(scenario, bears)
    assert elves.counter_count("+1/+1") == 0
    assert "trample" not in _abilities(scenario, elves)
    _clause_handled("Valentin, Dean of the Vein // Lisette, Dean of the Root", "Whenever you gain life")


def test_lisette_does_nothing_when_you_decline_to_pay():
    scenario = _lisette_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_pay_the_mana_cost(False, username="alice")

    scenario.game.gain_life("alice", 2)
    scenario.pass_until_resolved()

    assert bears.counter_count("+1/+1") == 0


def test_lisette_ignores_an_opponents_life_gain():
    scenario = _lisette_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_pay_the_mana_cost(True, username="alice")

    scenario.game.gain_life("bob", 2)
    scenario.pass_until_resolved()

    assert bears.counter_count("+1/+1") == 0


# -- Mycoid Maze: look at four, take a creature, the rest to the bottom --------


def test_mycoid_maze_takes_a_creature_from_the_top_four_and_bottoms_the_rest():
    scenario = _board(
        ["Forest", "Forest", "Forest", "Forest"],
        alice_hand=["Twists and Turns"],
        alice_library=["Island", "Grizzly Bears", "Swamp", "Mountain", "Plains", "Forest"],
    )
    maze = scenario.game.put_onto_battlefield(
        scenario.find("Twists and Turns", Zone.HAND, "alice"), "alice", transformed=True
    )
    assert maze.name == "Mycoid Maze"
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.scry_bottoming(bears, username="alice")  # the split's "moved" is "to hand"

    scenario.activate(
        maze, *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest"), index=1
    )
    scenario.pass_until_resolved()

    assert bears in scenario.player("alice").hand
    library = [c.name for c in scenario.player("alice").library]
    assert library[0] == "Plains" and sorted(library[-3:]) == ["Island", "Mountain", "Swamp"]
    assert maze.tapped
    _clause_handled("Twists and Turns", "Look at the top four cards")


def test_mycoid_maze_with_no_creature_among_the_top_four_takes_nothing():
    scenario = _board(
        ["Forest", "Forest", "Forest", "Forest"],
        alice_hand=["Twists and Turns"],
        alice_library=["Island", "Swamp", "Mountain", "Plains", "Grizzly Bears"],
    )
    maze = scenario.game.put_onto_battlefield(
        scenario.find("Twists and Turns", Zone.HAND, "alice"), "alice", transformed=True
    )

    scenario.activate(
        maze, *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest"), index=1
    )
    scenario.pass_until_resolved()

    assert scenario.player("alice").hand == []
    assert scenario.player("alice").library[0].name == "Grizzly Bears"
