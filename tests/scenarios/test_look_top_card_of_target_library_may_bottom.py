"""Jace, the Mind Sculptor's +2: "Look at the top card of target player's
library. You may put that card on the bottom of that player's library."
(`_parse_look_top_of_target_library_may_move_clause` in
`machines/effects/library.py`), and the same instruction with a different
destination - Lurking Informant's "{2}, {T}: Look at the top card of target
player's library. You may put that card into that player's graveyard." and
Draugr Thought-Thief's enters trigger ("... into their graveyard").

- **CR 701.20e** - looking at a card follows the reveal rules except the card
  is shown only to the specified player: the controller learns it, nobody
  else does.
- **CR 701.20b** - looking does not move the card; declining the "may" leaves
  it on top.
- **CR 608.2d** - the "may" is the controller's choice, never the library
  owner's.
- **CR 609.3** - an empty library has no top card: nothing is looked at or
  moved.
- **CR 606.3** - a loyalty ability is activated once per permanent per turn.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

JACE = "Jace, the Mind Sculptor"
LIBRARY = ["Forest", "Island", "Mountain", "Swamp"]


def _known_library(scenario, viewer: str) -> set[str]:
    return {
        entry.card_name for entry in scenario.game.known_to(viewer) if entry.zone is Zone.LIBRARY
    }


def _jace_scenario(*, alice_library=(), bob_library=LIBRARY) -> Scenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[JACE], library=list(alice_library))
        .player("bob", library=list(bob_library))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_plus_two_bottoming_the_opponents_top_card_when_the_controller_agrees():
    scenario = _jace_scenario()
    jace = scenario.find(JACE, Zone.BATTLEFIELD, "alice")
    bob = scenario.player("bob")
    assert jace.loyalty == 3

    scenario.will_take_the_may(True, username="alice")
    scenario.activate(jace, index=0, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert [state.name for state in bob.library] == ["Island", "Mountain", "Swamp", "Forest"]
    assert jace.counter_count(Counter.LOYALTY) == 5  # CR 606.6's cost is +2, paid up


def test_plus_two_declining_leaves_the_card_on_top_and_still_looked_at():
    scenario = _jace_scenario()
    jace = scenario.find(JACE, Zone.BATTLEFIELD, "alice")
    bob = scenario.player("bob")

    scenario.will_take_the_may(False, username="alice")
    scenario.activate(jace, index=0, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert [state.name for state in bob.library] == LIBRARY  # CR 701.20b
    assert _known_library(scenario, "alice") == {"Forest"}


def test_the_look_is_private_to_the_controller_cr_701_20e():
    scenario = _jace_scenario()
    jace = scenario.find(JACE, Zone.BATTLEFIELD, "alice")

    scenario.will_take_the_may(False, username="alice")
    scenario.activate(jace, index=0, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert "Forest" in _known_library(scenario, "alice")
    assert _known_library(scenario, "bob") == set()  # the library's owner learns nothing


def test_the_controller_not_the_library_owner_makes_the_choice():
    scenario = _jace_scenario()
    jace = scenario.find(JACE, Zone.BATTLEFIELD, "alice")
    bob = scenario.player("bob")

    scenario.will_take_the_may(True, username="alice")
    scenario.will_take_the_may(False, username="bob")  # never asked
    scenario.activate(jace, index=0, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert bob.library[-1].name == "Forest"


def test_plus_two_targeting_yourself_bottoms_your_own_top_card():
    scenario = _jace_scenario(alice_library=["Plains", "Island", "Swamp"])
    jace = scenario.find(JACE, Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")

    scenario.will_take_the_may(True, username="alice")
    scenario.activate(jace, index=0, username="alice", targets=["alice"])
    scenario.pass_until_resolved()

    assert [state.name for state in alice.library] == ["Island", "Swamp", "Plains"]


def test_an_empty_library_has_nothing_to_look_at_cr_609_3():
    scenario = _jace_scenario(bob_library=[])
    jace = scenario.find(JACE, Zone.BATTLEFIELD, "alice")
    bob = scenario.player("bob")

    scenario.activate(jace, index=0, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert bob.library == []
    assert scenario.questions_asked() == [] or all(
        question.kind.name != "MAY" for question in scenario.questions_asked()
    )
    assert jace.counter_count(Counter.LOYALTY) == 5  # the cost was paid regardless


def test_a_one_card_library_keeps_the_same_card_after_bottoming():
    scenario = _jace_scenario(bob_library=["Forest"])
    jace = scenario.find(JACE, Zone.BATTLEFIELD, "alice")
    bob = scenario.player("bob")

    scenario.will_take_the_may(True, username="alice")
    scenario.activate(jace, index=0, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert [state.name for state in bob.library] == ["Forest"]


def test_a_loyalty_ability_is_once_per_turn_cr_606_3():
    scenario = _jace_scenario()
    jace = scenario.find(JACE, Zone.BATTLEFIELD, "alice")

    scenario.will_take_the_may(False, username="alice")
    scenario.activate(jace, index=0, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert scenario.why_cannot_activate(jace, index=0, username="alice") is not None


# --- generality: the same instruction, a different destination ---------------


def test_lurking_informant_may_put_the_top_card_into_that_players_graveyard():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Lurking Informant", "Plains", "Plains"])
        .player("bob", library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    informant = scenario.find("Lurking Informant", Zone.BATTLEFIELD, "alice")
    informant.summoning_sick = False
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Plains", "Plains", username="alice")

    scenario.will_take_the_may(True, username="alice")
    scenario.activate(informant, *sources, index=0, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert [state.name for state in bob.library] == ["Island", "Mountain", "Swamp"]
    assert [state.name for state in bob.graveyard] == ["Forest"]


def test_lurking_informant_declining_leaves_the_card_on_top():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Lurking Informant", "Plains", "Plains"])
        .player("bob", library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    informant = scenario.find("Lurking Informant", Zone.BATTLEFIELD, "alice")
    informant.summoning_sick = False
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Plains", "Plains", username="alice")

    scenario.will_take_the_may(False, username="alice")
    scenario.activate(informant, *sources, index=0, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert [state.name for state in bob.library] == LIBRARY
    assert bob.graveyard == []


def test_draugr_thought_thief_enters_and_may_put_the_top_card_into_their_graveyard():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Draugr Thought-Thief"], battlefield=["Island", "Island", "Island"])
        .player("bob", library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Island", "Island", "Island", username="alice")

    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets("bob", username="alice")
    scenario.cast_and_resolve("Draugr Thought-Thief", *sources, username="alice")
    scenario.pass_until_resolved()

    assert [state.name for state in bob.graveyard] == ["Forest"]
