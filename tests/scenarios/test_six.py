"""Six's attack trigger (CR 701.17a, 701.17c): mill three, then optionally
keep a land from among *those* three cards.

"Whenever Six attacks, mill three cards. You may put a land card from among
them into your hand."

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 701.17a (mill), CR 701.17c ("a milled card can be found in the zone it
moved to, as long as it's public" - the "among them" candidate pool is the
cards this mill just moved, not the whole graveyard).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board(library: list[str]) -> Scenario:
    return Scenario().player("alice", battlefield=["Six"], library=library).player("bob")


def resolve_all(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def test_a_land_among_the_three_milled_may_go_to_hand():
    scenario = board(["Forest", "Lava Dart", "Lava Dart", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    six = scenario.creature("Six", "alice")
    forest = scenario.player("alice").library[0]
    scenario.will_choose_cards(forest, source="Six")

    scenario.attack_with(six)
    resolve_all(scenario)

    assert scenario.find("Forest", Zone.HAND, "alice").zone is Zone.HAND
    graveyard_names = [c.name for c in scenario.player("alice").graveyard]
    assert graveyard_names == ["Lava Dart", "Lava Dart"]
    assert [c.name for c in scenario.player("alice").library] == ["Island"]


def test_no_land_among_the_three_leaves_nothing_to_choose():
    scenario = board(["Lava Dart", "Lava Dart", "Lava Dart", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    six = scenario.creature("Six", "alice")

    scenario.attack_with(six)
    resolve_all(scenario)

    assert scenario.player("alice").hand == []
    graveyard_names = {c.name for c in scenario.player("alice").graveyard}
    assert graveyard_names == {"Lava Dart"}
    assert len(scenario.player("alice").graveyard) == 3
    # The Forest fourth from the top was never milled, so it is not a legal
    # "among them" candidate even though it is a land.
    assert [c.name for c in scenario.player("alice").library] == ["Forest"]


def test_a_land_already_in_the_graveyard_before_this_mill_is_not_a_candidate():
    """The "among them" corner case: only the three cards *this* mill just
    moved are candidates, not a land already sitting in the graveyard from
    something else."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Six"],
            library=["Lava Dart", "Lava Dart", "Lava Dart"],
            graveyard=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    six = scenario.creature("Six", "alice")

    scenario.attack_with(six)
    resolve_all(scenario)

    assert scenario.player("alice").hand == []
