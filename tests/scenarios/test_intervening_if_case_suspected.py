"""Case of the Stashed Skeleton's "To solve - You control no suspected
Skeletons." (CR 719.3a: "At the beginning of your end step, if [condition]
and this Case is not solved, this Case becomes solved.")

The condition is a count of permanents you control that carry CR 701.60b's
suspected designation and the Skeleton subtype - "no" is a count of zero.
Before this it recorded an `InterveningIfNotice` and the Case never
solved. The condition can turn false between the end-step trigger and its
resolution (a Skeleton becomes suspected in response), and CR 603.4's
recheck then leaves the Case unsolved.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: CR 719.3a, CR 719.3b, CR 701.60a-d, CR 603.4.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import suspect
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

CASE = "Case of the Stashed Skeleton"


def _scenario(*battlefield: str, hand=(CASE,)) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[*battlefield, "Swamp", "Swamp"],
            hand=list(hand),
            library=["Swamp"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_all(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _skeletons(scenario: PlayedScenario):
    return [
        permanent
        for permanent in scenario.game.permanents_controlled_by("alice")
        if "Skeleton" in permanent.subtypes
    ]


def _end_step(scenario: PlayedScenario) -> None:
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    _resolve_all(scenario)


def test_the_suspected_skeleton_it_makes_keeps_the_case_unsolved():
    scenario = _scenario()
    scenario.cast_and_resolve(CASE, *scenario.untapped_sources("Swamp", "Swamp"))
    _resolve_all(scenario)
    (skeleton,) = _skeletons(scenario)
    assert skeleton.suspected

    _end_step(scenario)

    assert scenario.find(CASE, Zone.BATTLEFIELD, "alice").solved is False
    assert scenario.game.intervening_if_notices == []


def test_with_the_skeleton_gone_the_case_solves():
    scenario = _scenario()
    scenario.cast_and_resolve(CASE, *scenario.untapped_sources("Swamp", "Swamp"))
    _resolve_all(scenario)
    (skeleton,) = _skeletons(scenario)
    scenario.game.destroy(skeleton)

    _end_step(scenario)

    assert scenario.find(CASE, Zone.BATTLEFIELD, "alice").solved is True
    assert scenario.game.intervening_if_notices == []


def test_an_unsuspected_skeleton_does_not_stop_it():
    scenario = _scenario(CASE, "Manor Skeleton", hand=())

    _end_step(scenario)

    assert scenario.find(CASE, Zone.BATTLEFIELD, "alice").solved is True


def test_a_suspected_non_skeleton_does_not_stop_it():
    scenario = _scenario(CASE, "Grizzly Bears", hand=())
    suspect(scenario.game, scenario.creature("Grizzly Bears", "alice"))

    _end_step(scenario)

    assert scenario.find(CASE, Zone.BATTLEFIELD, "alice").solved is True


def test_a_skeleton_suspected_before_resolution_leaves_it_unsolved():
    """CR 603.4: true at the beginning of the end step, false by the time
    the trigger resolves - the recheck stops it."""
    scenario = _scenario(CASE, "Manor Skeleton", hand=())
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack
    suspect(scenario.game, scenario.creature("Manor Skeleton", "alice"))

    _resolve_all(scenario)

    assert scenario.find(CASE, Zone.BATTLEFIELD, "alice").solved is False
