"""EP-01 round 1, task 6 review fix: the non-replacement lines that share a card
with a replacement static.

Each test plays the line through the engine and asserts the outcome, with the
negative (the condition or controller that must not apply) beside it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import ActionKind, legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
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
        [],
        alice_exile=["Darigaaz Reincarnated"],
        alice_library=["Island"] * 10,
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
    _clause_handled(
        "Valentin, Dean of the Vein // Lisette, Dean of the Root", "Whenever you gain life"
    )


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


# -- Kumano Faces Kakkazan, chapter II -----------------------------------------


def _kumano_board():
    scenario = _board(
        ["Forest", "Forest", "Forest"],
        alice_hand=["Kumano Faces Kakkazan", "Grizzly Bears", "Llanowar Elves"],
        alice_library=["Island"] * 5,
    )
    scenario.game.put_onto_battlefield(
        scenario.find("Kumano Faces Kakkazan", Zone.HAND, "alice"), "alice"
    )
    saga = scenario.find("Kumano Faces Kakkazan", Zone.BATTLEFIELD, "alice")
    return scenario, saga


def test_the_next_creature_spell_this_turn_enters_with_an_extra_counter_only_once():
    scenario, saga = _kumano_board()
    scenario.pass_until_resolved()  # chapter I, put on the stack as the Saga entered
    scenario.game.add_counters(saga, "lore", 1)  # chapter II
    scenario.pass_until_resolved()
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.cast_and_resolve("Grizzly Bears", forests[0], forests[1])
    scenario.pass_until_resolved()
    bears = scenario.creature("Grizzly Bears", "alice")
    assert bears.counter_count("+1/+1") == 1

    scenario.cast_and_resolve("Llanowar Elves", forests[2])
    scenario.pass_until_resolved()
    elves = scenario.creature("Llanowar Elves", "alice")
    assert elves.counter_count("+1/+1") == 0
    _clause_handled("Kumano Faces Kakkazan", "When you next cast a creature spell")


# -- Melira, the Living Cure: "Exile Melira: Choose another target creature or artifact. ..."


def _melira_board():
    scenario = _board(
        ["Melira, the Living Cure", "Grizzly Bears"],
        ["Llanowar Elves"],
        alice_library=["Island"] * 10,
        bob_library=["Island"] * 10,
    )
    melira = scenario.creature("Melira, the Living Cure", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(melira, targets=[bears])
    scenario.pass_until_resolved()
    assert melira.zone is Zone.EXILE
    return scenario, bears


def test_the_chosen_creature_returns_to_the_battlefield_when_it_dies_this_turn():
    scenario, bears = _melira_board()

    scenario.game.destroy(bears)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    _clause_handled("Melira, the Living Cure", "Exile")


def test_a_creature_that_was_not_chosen_stays_dead():
    scenario, _ = _melira_board()
    elves = scenario.creature("Llanowar Elves", "bob")

    scenario.game.destroy(elves)

    assert elves.zone is Zone.GRAVEYARD


def test_the_return_happens_once_and_only_this_turn():
    scenario, bears = _melira_board()
    scenario.game.destroy(bears)
    scenario.pass_until_resolved()
    assert bears.zone is Zone.BATTLEFIELD

    scenario.game.destroy(bears)  # the one-shot is spent
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD


def test_the_return_is_gone_next_turn():
    scenario, bears = _melira_board()
    _next_turn(scenario)

    scenario.game.destroy(bears)

    assert bears.zone is Zone.GRAVEYARD


def test_a_chosen_creature_that_is_exiled_instead_does_not_return():
    scenario, bears = _melira_board()

    scenario.game.exile_permanent(bears)

    assert bears.zone is Zone.EXILE


# -- Enduring Renewal: "Whenever a creature is put into your graveyard from the
#    battlefield, return it to your hand." ------------------------------------


def test_enduring_renewal_returns_your_creature_that_dies_to_your_hand():
    scenario = _board(["Enduring Renewal", "Grizzly Bears"], ["Llanowar Elves"])
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)
    scenario.pass_until_resolved()

    assert bears in scenario.player("alice").hand
    _clause_handled("Enduring Renewal", "Whenever a creature is put into your graveyard")


def test_enduring_renewal_ignores_an_opponents_creature_dying():
    scenario = _board(["Enduring Renewal"], ["Llanowar Elves"])
    elves = scenario.creature("Llanowar Elves", "bob")

    scenario.game.destroy(elves)
    scenario.pass_until_resolved()

    assert elves.zone is Zone.GRAVEYARD


def test_enduring_renewal_returns_a_creature_you_own_that_an_opponent_controlled():
    scenario = _board(["Enduring Renewal"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.owner = "alice"

    scenario.game.destroy(bears)
    scenario.pass_until_resolved()

    assert bears in scenario.player("alice").hand


def test_enduring_renewal_does_not_return_a_creature_milled_from_the_library():
    scenario = _board(["Enduring Renewal"], alice_library=["Grizzly Bears", "Island"])
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")

    scenario.game.put_into_graveyard(bears)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD


# -- Enduring Renewal: "Play with your hand revealed." -------------------------


def test_a_revealed_hand_is_known_to_the_opponent_while_the_permanent_stays():
    scenario = _board(["Enduring Renewal"], alice_hand=["Lightning Bolt", "Island"])

    assert scenario.game.hand_is_revealed("alice")
    assert not scenario.game.hand_is_revealed("bob")
    known = {k.card_name for k in scenario.game.known_to("bob") if k.owner == "alice"}
    assert known == {"Lightning Bolt", "Island"}

    scenario.game.destroy(scenario.find("Enduring Renewal", Zone.BATTLEFIELD, "alice"))
    assert not scenario.game.hand_is_revealed("alice")
    assert [k for k in scenario.game.known_to("bob") if k.owner == "alice"] == []
    _clause_handled("Enduring Renewal", "Play with your hand revealed")


# -- Ashiok, Wicked Manipulator ------------------------------------------------


def test_ashiok_plus_one_exiles_one_of_the_top_two_and_takes_the_other():
    scenario = _board(["Ashiok, Wicked Manipulator"], alice_library=["Island", "Forest", "Swamp"])
    ashiok = scenario.find("Ashiok, Wicked Manipulator", Zone.BATTLEFIELD, "alice")
    island, forest = scenario.top_of_library(2, "alice")
    scenario.scry_bottoming(forest, username="alice")

    scenario.activate(ashiok, index=0)
    scenario.pass_until_resolved()

    assert island.zone is Zone.EXILE
    assert forest in scenario.player("alice").hand
    assert ashiok.loyalty == 6
    _clause_handled("Ashiok, Wicked Manipulator", "Look at the top two cards")


def test_ashiok_minus_seven_exiles_x_cards_from_the_targets_library():
    scenario = _board(
        ["Ashiok, Wicked Manipulator"],
        alice_exile=["Serra Angel", "Grizzly Bears"],
        bob_library=["Island"] * 10,
    )
    ashiok = scenario.find("Ashiok, Wicked Manipulator", Zone.BATTLEFIELD, "alice")
    ashiok.add_counters(Counter.LOYALTY, 2)
    before = len(scenario.player("bob").library)

    scenario.activate(ashiok, index=2, targets=[scenario.player("bob")])
    scenario.pass_until_resolved()

    assert len(scenario.player("bob").library) == before - 7  # 5 + 2
    _clause_handled("Ashiok, Wicked Manipulator", "Target player exiles")


def test_ashiok_minus_seven_ignores_cards_an_opponent_owns_in_exile():
    scenario = _board(
        ["Ashiok, Wicked Manipulator"],
        bob_exile=["Serra Angel"],
        bob_library=["Island"] * 10,
    )
    ashiok = scenario.find("Ashiok, Wicked Manipulator", Zone.BATTLEFIELD, "alice")
    ashiok.add_counters(Counter.LOYALTY, 2)

    scenario.activate(ashiok, index=2, targets=[scenario.player("bob")])
    scenario.pass_until_resolved()

    assert len(scenario.player("bob").library) == 10


# -- Asmodeus the Archfiend: "{B}: Return all cards exiled with Asmodeus ..." ---


def test_asmodeus_returns_the_cards_it_exiled_and_costs_that_much_life():
    scenario = _board(
        ["Asmodeus the Archfiend", "Swamp"],
        alice_library=["Grizzly Bears", "Island", "Forest"],
        alice_exile=["Serra Angel"],
    )
    asmodeus = scenario.find("Asmodeus the Archfiend", Zone.BATTLEFIELD, "alice")
    scenario.game.draw_cards("alice", 2)  # Binding Contract exiles both, face down
    assert scenario.player("alice").hand == []

    scenario.activate(asmodeus, *scenario.untapped_sources("Swamp"), index=1)
    scenario.pass_until_resolved()

    assert sorted(c.card.name for c in scenario.player("alice").hand) == [
        "Grizzly Bears",
        "Island",
    ]
    assert [c.card.name for c in scenario.game.exile] == ["Serra Angel"]
    assert scenario.player("alice").life == 18
    _clause_handled("Asmodeus the Archfiend", "Return all cards exiled with Asmodeus")


def test_asmodeus_with_nothing_exiled_costs_no_life():
    scenario = _board(["Asmodeus the Archfiend", "Swamp"], alice_library=["Island"])
    asmodeus = scenario.find("Asmodeus the Archfiend", Zone.BATTLEFIELD, "alice")

    scenario.activate(asmodeus, *scenario.untapped_sources("Swamp"), index=1)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 20


# -- Draugr Necromancer: cast the ice-counter cards, snow mana as any color ----


def _draugr_board(lands):
    scenario = _board(["Draugr Necromancer", *lands], ["Grizzly Bears"])
    theirs = scenario.creature("Grizzly Bears", "bob")
    scenario.game.destroy(theirs)  # exiled with an ice counter instead
    assert theirs.zone is Zone.EXILE
    return scenario, theirs


def test_draugr_lets_you_cast_an_opponents_ice_counter_card_with_snow_mana_of_any_color():
    scenario, theirs = _draugr_board(["Snow-Covered Island", "Snow-Covered Island"])

    casting = scenario.cast("Grizzly Bears", "alice", from_zone=Zone.EXILE)
    casting.use_keyword("Cast permission")
    sources = scenario.untapped_sources("Snow-Covered Island", "Snow-Covered Island")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    bears = scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    _clause_handled("Draugr Necromancer", "You may cast spells from among cards in exile")


def test_draugr_does_not_let_nonsnow_mana_pay_a_color_it_does_not_make():
    scenario, _ = _draugr_board(["Island", "Island"])

    casting = scenario.cast("Grizzly Bears", "alice", from_zone=Zone.EXILE)
    casting.use_keyword("Cast permission")
    sources = scenario.untapped_sources("Island", "Island")
    with pytest.raises(ValueError, match="cannot pay"):
        scenario.pay_with(casting.begin_paying(), *sources)


def _try_to_cast_sol_ring_from_exile(scenario):
    casting = scenario.cast("Sol Ring", "alice", from_zone=Zone.EXILE)
    casting.use_keyword("Cast permission")
    sources = scenario.untapped_sources("Snow-Covered Island")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)


def test_draugr_does_not_open_a_card_without_an_ice_counter():
    scenario = _board(["Draugr Necromancer", "Snow-Covered Island"], [], bob_exile=["Sol Ring"])

    with pytest.raises(ValueError, match="Cast permission"):
        _try_to_cast_sol_ring_from_exile(scenario)


def test_draugr_does_not_open_your_own_ice_counter_card():
    scenario = _board(["Draugr Necromancer", "Snow-Covered Island"], [], alice_exile=["Sol Ring"])
    scenario.find("Sol Ring", Zone.EXILE).add_counters("ice", 1)

    with pytest.raises(ValueError, match="Cast permission"):
        _try_to_cast_sol_ring_from_exile(scenario)


def test_draugr_opens_an_opponents_ice_counter_card_for_ordinary_mana_too():
    scenario = _board(["Draugr Necromancer", "Island"], [], bob_exile=["Sol Ring"])
    scenario.find("Sol Ring", Zone.EXILE).add_counters("ice", 1)

    casting = scenario.cast("Sol Ring", "alice", from_zone=Zone.EXILE)
    casting.use_keyword("Cast permission")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Island"))
    scenario.put_on_stack(casting)
    resolved = scenario.resolve_top()

    assert resolved.zone is Zone.BATTLEFIELD


def test_draugr_offers_the_exiled_card_as_an_affordable_cast_with_snow_mana():
    scenario, _ = _draugr_board(["Snow-Covered Island", "Snow-Covered Island"])

    theirs = scenario.find("Grizzly Bears", Zone.EXILE)
    rows = [
        a
        for a in legal_actions(scenario.game, "alice")
        if a.kind is ActionKind.CAST and a.card_id == theirs.id
    ]

    assert rows, "the exiled Grizzly Bears is offered as a cast"
    assert any(a.affordable for a in rows)
