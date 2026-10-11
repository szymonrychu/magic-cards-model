"""Tomik, Distinguished Advokist's second line, "Your opponents can't play land
cards from graveyards." (EP-01 R2, T2).

Verified with `mise run rules:find`: CR 305.1 ("A player who has priority may
play a land card from their hand during a main phase of their turn ...") and
CR 101.2 ("When a rule or effect allows or directs something to happen, and
another effect states that it can't happen, the 'can't' effect takes
precedence"). Crucible of Worlds' permission to play lands from the graveyard
is the "may" the line beats.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(opponent_battlefield):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", battlefield=["Crucible of Worlds"], graveyard=["Forest"])
        .player("alice", battlefield=opponent_battlefield)
        .build()
    )


def test_without_tomik_the_crucible_lets_the_land_be_played_from_the_graveyard():
    scenario = _board([])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.GRAVEYARD, "bob")
    assert scenario.game.graveyard_land_permission(forest, "bob") is not None


def test_tomik_refuses_the_opponents_graveyard_land_play():
    scenario = _board(["Tomik, Distinguished Advokist"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.GRAVEYARD, "bob")
    assert scenario.game.graveyard_land_permission(forest, "bob") is None


def test_tomiks_own_controller_may_still_play_lands_from_their_graveyard():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Tomik, Distinguished Advokist", "Crucible of Worlds"],
            graveyard=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.GRAVEYARD, "alice")
    assert scenario.game.graveyard_land_permission(forest, "alice") is not None


def test_the_prohibition_ends_when_tomik_leaves():
    scenario = _board(["Tomik, Distinguished Advokist"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.GRAVEYARD, "bob")
    scenario.game.put_into_graveyard(
        scenario.find("Tomik, Distinguished Advokist", Zone.BATTLEFIELD, "alice")
    )
    assert scenario.game.graveyard_land_permission(forest, "bob") is not None


def _land_plays(scenario):
    from magic_cards_model.machines.legal_actions import legal_actions

    return [
        action
        for action in legal_actions(scenario.game, "bob")
        if getattr(action.kind, "value", str(action.kind)) == "play_land"
    ]


def test_the_play_land_action_is_offered_without_tomik_and_gone_under_it():
    free = _board([])
    free.start_at(Step.PRECOMBAT_MAIN)
    assert len(_land_plays(free)) == 1
    blocked = _board(["Tomik, Distinguished Advokist"])
    blocked.start_at(Step.PRECOMBAT_MAIN)
    assert _land_plays(blocked) == []
