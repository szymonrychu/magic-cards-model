"""An announced ability's targets carry the requirement each one filled.

CR 601.2c (via CR 602.2b for an activation, CR 603.3d for a trigger): the
announcement places each target into one of the ability's "target ..."
requirements. A spell has always remembered that placement on its `TargetRef`s
(`TargetRef.slot`); an ability's targets did not, so resolution replayed the
first-fit placement on whatever the board looked like by then, which can
misassign a source whose controller changed in response (CR 608.2b judges each
target against the requirement it was announced under).

Real printings: Yoshimaru, Scrappy Stray (a trigger with "another target
creature you control" and "up to one target creature an opponent controls")
and Vivien, Arkbow Ranger (a loyalty ability with two targets).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _yoshimaru_board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Yoshimaru, Scrappy Stray"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Forest"],
            library=["Elder Gargaroth"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Elder Gargaroth", "alice", from_zone=Zone.LIBRARY)
    return scenario


def test_a_trigger_records_which_requirement_each_target_filled():
    scenario = _yoshimaru_board()
    gargaroth = scenario.creature("Elder Gargaroth", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Yoshimaru, Scrappy Stray", [gargaroth, bears])
    sources = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Yoshimaru, Scrappy Stray", *sources)

    trigger = scenario.game.stack[-1]
    assert [ref.slot for ref in trigger.targets] == [0, 1]


def test_an_asked_trigger_records_which_requirement_each_target_filled():
    scenario = _yoshimaru_board()
    gargaroth = scenario.creature("Elder Gargaroth", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.CHOOSE_TARGETS, value=(bears, gargaroth), player="alice")
    )
    sources = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Yoshimaru, Scrappy Stray", *sources)

    trigger = scenario.game.stack[-1]
    assert [ref.slot for ref in trigger.targets] == [1, 0], (
        "the victim named first still fills the opponent's-creature requirement"
    )


def test_an_activation_records_which_requirement_each_target_filled():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Vivien, Arkbow Ranger", "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vivien = scenario.find("Vivien, Arkbow Ranger", Zone.BATTLEFIELD, "alice")
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Hill Giant", "bob")

    ability = scenario.activate(vivien, index=1, targets=[mine, theirs])

    assert [ref.slot for ref in ability.targets] == [0, 1]
