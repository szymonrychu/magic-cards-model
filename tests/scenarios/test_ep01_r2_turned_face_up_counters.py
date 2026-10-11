"""Scenario: "As this creature is turned face up, put N +1/+1 counters on it."
(CR 614.1e: the replacement applies as the permanent turns face up, and the
counters are put on it with it already on the battlefield; CR 708.2: a
face-down permanent has no text, so nothing applies while it is face down;
CR 702.37e / CR 702.168a: the morph or disguise cost turns it face up.)
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _face_down(scenario, name, keyword, *mana):
    casting = scenario.cast(name)
    casting.use_keyword(keyword)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*mana))
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def _board(card, lands, land):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[card], battlefield=[land] * lands)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_hooded_hydra_gets_five_counters_when_turned_face_up():
    scenario = _board("Hooded Hydra", 8, "Forest")
    permanent = _face_down(scenario, "Hooded Hydra", "Morph", "Forest", "Forest", "Forest")
    assert permanent.face_down
    assert permanent.counters == {}
    turned = scenario.turn_face_up(permanent, *scenario.untapped_sources(*["Forest"] * 5))
    assert turned.counters == {"+1/+1": 5}
    assert (turned.power, turned.toughness) == (5, 5)


def test_bubble_smuggler_gets_four_counters_when_turned_face_up():
    scenario = _board("Bubble Smuggler", 9, "Island")
    permanent = _face_down(scenario, "Bubble Smuggler", "Disguise", "Island", "Island", "Island")
    assert permanent.counters == {}
    turned = scenario.turn_face_up(permanent, *scenario.untapped_sources(*["Island"] * 6))
    assert turned.counters == {"+1/+1": 4}


def test_a_creature_that_enters_face_up_gets_no_counters_from_it():
    scenario = _board("Bubble Smuggler", 0, "Island")
    permanent = scenario.put_onto_battlefield("Bubble Smuggler")
    assert permanent.counters == {}
