"""Six's attack trigger (CR 701.17a, 701.17c): mill three, then optionally
keep a land from among *those* three cards.

"Whenever Six attacks, mill three cards. You may put a land card from among
them into your hand."

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 701.17a (mill), CR 701.17c ("a milled card can be found in the zone it
moved to, as long as it's public" - the "among them" candidate pool is the
cards this mill just moved, not the whole graveyard).
"""

from uuid import uuid4

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
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


def test_an_illegal_choose_answer_still_leaves_the_mill_and_completes_resolution():
    """CR 608.2c's printed order mills first, then offers the "you may put a
    land ... into your hand" question, then (once accepted, and
    `default_answer`'s own deviation takes it by default) a `CHOOSE_CARDS`
    question naming which land - one ability, one paragraph (CR 113.3). If
    that last question can't be legally answered - `Game.ask`'s own
    `CHOOSE_CARDS` branch refusing a card id that was never offered - CR
    733.1 has nothing to reverse for the mill: it already happened, in full,
    before either question was asked.

    What has to hold regardless is CR 608.2n: the ability comes off the stack
    and CR 704.3's state-based actions run before anything else - the
    bookkeeping `Game._resolve_ability` did not guarantee before this fix.
    """
    scenario = board(["Forest", "Lava Dart", "Lava Dart", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    six = scenario.creature("Six", "alice")
    alice = scenario.player("alice")

    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.CHOOSE_CARDS,
            value=(uuid4(),),  # never among the offered candidates
            player="alice",
            source="Six",
        )
    )

    scenario.attack_with(six)
    assert scenario.stack_names() != []
    with pytest.raises(ValueError, match="cannot choose a card that was not offered"):
        resolve_all(scenario)

    # The mill already happened - CR 608.2c's first clause, unconditional:
    # the Forest is still among the milled cards, since the pick that would
    # have moved it to hand never got a legal answer.
    graveyard_names = {c.name for c in alice.graveyard}
    assert graveyard_names == {"Forest", "Lava Dart"}
    assert len(alice.graveyard) == 3
    assert alice.hand == []
    # CR 608.2n: the ability is off the stack either way.
    assert scenario.game.stack == []
    scenario.assert_in_exactly_one_zone(*scenario.all_card_states())
