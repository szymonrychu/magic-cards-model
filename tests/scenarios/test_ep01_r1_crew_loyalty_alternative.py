"""CR 702.122a / 118.9: a Vehicle that lets its controller pay its crew cost
another way.

    Heart of Kiran - You may remove a loyalty counter from a planeswalker you
    control rather than pay Heart of Kiran's crew cost.

Only the Vehicle that prints the sentence has the option; a planeswalker with
no loyalty counter or one the crewer does not control cannot pay it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(**alice):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", **alice)
        .player("bob", battlefield=["Jace Beleren"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _crew(scenario, vehicle, *creatures, loyalty_from=None):
    activation = crew_activation(
        scenario.game, vehicle, list(creatures), "alice", loyalty_from=loyalty_from
    )
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()
    return activation


def test_a_loyalty_counter_crews_heart_of_kiran_with_no_creature_tapped():
    scenario = _board(battlefield=["Heart of Kiran", "Jace Beleren", "Grizzly Bears"])
    heart = scenario.find("Heart of Kiran", Zone.BATTLEFIELD, "alice")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "alice")
    before = jace.counters[Counter.LOYALTY]

    _crew(scenario, heart, loyalty_from=jace)

    assert jace.counters[Counter.LOYALTY] == before - 1
    assert scenario.game.characteristics_of(heart).is_creature
    assert not scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").tapped


def test_the_ordinary_crew_cost_still_works_on_heart_of_kiran():
    scenario = _board(battlefield=["Heart of Kiran", "Serra Angel"])
    heart = scenario.find("Heart of Kiran", Zone.BATTLEFIELD, "alice")
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "alice")
    _crew(scenario, heart, angel)
    assert angel.tapped
    assert scenario.game.characteristics_of(heart).is_creature


def test_a_vehicle_without_the_sentence_refuses_the_loyalty_payment():
    scenario = _board(battlefield=["Smuggler's Copter", "Jace Beleren"])
    copter = scenario.find("Smuggler's Copter", Zone.BATTLEFIELD, "alice")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError, match="loyalty"):
        crew_activation(scenario.game, copter, [], "alice", loyalty_from=jace)


def test_an_opponents_planeswalker_cannot_pay():
    scenario = _board(battlefield=["Heart of Kiran"])
    heart = scenario.find("Heart of Kiran", Zone.BATTLEFIELD, "alice")
    theirs = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    with pytest.raises(ValueError, match="control"):
        crew_activation(scenario.game, heart, [], "alice", loyalty_from=theirs)


def test_a_planeswalker_with_no_loyalty_counter_cannot_pay():
    scenario = _board(battlefield=["Heart of Kiran", "Jace Beleren"])
    heart = scenario.find("Heart of Kiran", Zone.BATTLEFIELD, "alice")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "alice")
    jace.remove_counters(Counter.LOYALTY, jace.counters[Counter.LOYALTY])
    with pytest.raises(ValueError, match="loyalty"):
        crew_activation(scenario.game, heart, [], "alice", loyalty_from=jace)


def test_the_object_cost_offer_names_the_planeswalkers_that_could_pay():
    scenario = _board(battlefield=["Heart of Kiran", "Jace Beleren"])
    heart = scenario.find("Heart of Kiran", Zone.BATTLEFIELD, "alice")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "alice")
    offer = scenario.game.object_cost_offers(heart, "alice")["crew"]
    assert [state.id for state in offer.loyalty_candidates] == [jace.id]


def test_a_plain_vehicle_offers_no_loyalty_candidates():
    scenario = _board(battlefield=["Smuggler's Copter", "Jace Beleren"])
    copter = scenario.find("Smuggler's Copter", Zone.BATTLEFIELD, "alice")
    assert scenario.game.object_cost_offers(copter, "alice")["crew"].loyalty_candidates == []
