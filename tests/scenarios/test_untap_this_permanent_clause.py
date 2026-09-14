""" "Untap this <permanent>" read as one clause among an ability's others,
not only as a whole ability's effect - `_parse_untap_self_clause` in the
ordinary clause chain (`_parse_mixed_clause`).

Grinding Station is the pool printing: "Whenever an artifact enters, you may
untap this artifact." Before the clause chain read the untap, the "you may"
wrapper had no instruction to offer and the trigger resolved doing nothing,
with no notice. Leviathan's "If you do, untap this creature." reaches the same
clause (`test_conditional_sacrifice_clauses.py`).

Looked up with `mise run rules:find` in the session that wrote this file:

- CR 701.26b - "To untap a permanent, rotate it back to the upright position
  from a sideways position."
- CR 608.2d - the "you may" is a choice made while the ability resolves;
  declining is legal and does nothing.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone

from .harness import Scenario

STATION = "Grinding Station"


def _station_trigger(scenario: Scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    station = scenario.find(STATION, Zone.BATTLEFIELD, "alice")
    station.tap()
    return station


def test_taking_the_may_untaps_the_station_when_an_artifact_enters():
    scenario = (
        Scenario().player("alice", hand=["Memnite"], battlefield=[STATION]).player("bob").build()
    )
    station = _station_trigger(scenario)
    scenario.will_take_the_may(True, source=STATION)

    scenario.put_onto_battlefield("Memnite", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert not station.tapped
    assert [q.kind for q in scenario.questions_asked()] == [DecisionKind.MAY]


def test_declining_the_may_leaves_the_station_tapped():
    scenario = (
        Scenario().player("alice", hand=["Memnite"], battlefield=[STATION]).player("bob").build()
    )
    station = _station_trigger(scenario)
    scenario.will_take_the_may(False, source=STATION)

    scenario.put_onto_battlefield("Memnite", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert station.tapped
