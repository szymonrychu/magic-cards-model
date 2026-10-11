"""Scenario: "During turns other than yours, this artifact is a 2/3 Gargoyle
artifact creature with flying." (Warden of the Wall; CR 613.1d type and subtype,
CR 613.4b set power/toughness, CR 613.1f keyword; CR 611.3a - it applies at any
moment the turn is someone else's, no "locked in").
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario


def go_to_bobs_turn(scenario):
    scenario.start_at(Step.END_OF_COMBAT)
    while scenario.turn.active_player == "alice":
        scenario.advance("alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)


def test_it_is_only_an_artifact_on_its_controllers_turn():
    scenario = Scenario().player("alice", battlefield=["Warden of the Wall"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    warden = scenario.find("Warden of the Wall", Zone.BATTLEFIELD, "alice")
    chars = scenario.game.characteristics_of(warden)
    assert Type.CREATURE not in chars.types


def test_it_is_a_flying_gargoyle_creature_on_an_opponents_turn():
    scenario = Scenario().player("alice", battlefield=["Warden of the Wall"]).player("bob").build()
    go_to_bobs_turn(scenario)
    assert scenario.turn.active_player == "bob"
    warden = scenario.find("Warden of the Wall", Zone.BATTLEFIELD, "alice")
    chars = scenario.game.characteristics_of(warden)
    assert Type.CREATURE in chars.types and Type.ARTIFACT in chars.types
    assert "Gargoyle" in chars.subtypes
    assert (chars.power, chars.toughness) == (2, 3)
    assert any(line.lower().startswith("flying") for line in chars.abilities)
