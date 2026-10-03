"""Scenario: Captive Audience - "At the beginning of your upkeep, choose one
that hasn't been chosen - Your life total becomes 4. / Discard your hand. /
Each opponent creates five 2/2 black Zombie creature tokens."

The third mode's body names its creators by a *group* subject ("Each
opponent creates ..."), where `target player/opponent creates ...` was the only
subject the token-creation reader knew. CR 111.2: the player a token-creating
instruction names creates the token and so owns and controls it - every
opponent, each for themself, never the ability's controller. Party Dude's
"each player creates a Food token" is the same subject family and is proven
alongside (CR 111.10a's predefined Food token, created by each player).

CR 700.2d (looked up with `mise run rules:find 700.2` in the session that
wrote this) bars repeating a mode: the upkeep trigger offers only modes not
chosen on earlier upkeeps, so it runs out after the third.
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

_LIFE = "Your life total becomes 4."
_DISCARD = "Discard your hand."
_ZOMBIES = "Each opponent creates five 2/2 black Zombie creature tokens."


def _zombies(scenario, username):
    return [
        state
        for state in scenario.game.battlefield
        if state.name == "Zombie Token" and state.controller == username
    ]


def _resolve_stack(scenario):
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _advance_into_alices_upkeep(scenario):
    """Step forward until alice's next upkeep begins (its trigger is then on
    the stack, its mode already chosen - CR 603.3c)."""
    first = True
    while first or not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "alice"):
        first = False
        _resolve_stack(scenario)
        scenario.advance()


def _upkeep_choosing(scenario, mode):
    scenario.will_choose_mode(mode)
    _advance_into_alices_upkeep(scenario)
    _resolve_stack(scenario)


def _scenario():
    return (
        Scenario()
        .player(
            "alice",
            life=20,
            battlefield=["Captive Audience"],
            hand=["Forest", "Island", "Swamp"],
            library=["Forest"] * 8,
        )
        .player("bob", library=["Forest"] * 8)
        .build()
    )


def test_each_opponent_creates_five_zombies_they_own_and_control():
    scenario = _scenario()
    _upkeep_choosing(scenario, _ZOMBIES)
    assert len(_zombies(scenario, "bob")) == 5
    assert _zombies(scenario, "alice") == []


def test_life_total_and_discard_modes_hit_the_controller():
    scenario = _scenario()
    _upkeep_choosing(scenario, _LIFE)
    assert scenario.player("alice").life == 4
    assert [s.name for s in scenario.player("alice").hand] != []

    scenario = _scenario()
    _upkeep_choosing(scenario, _DISCARD)
    assert scenario.player("alice").hand == []
    assert scenario.player("alice").life == 20


def test_modes_run_out_across_upkeeps_and_cannot_repeat():
    scenario = _scenario()
    _upkeep_choosing(scenario, _ZOMBIES)
    assert len(_zombies(scenario, "bob")) == 5

    # Already chosen on an earlier upkeep: refused, not merely un-picked.
    scenario.will_choose_mode(_ZOMBIES)
    with pytest.raises(ValueError):
        _advance_into_alices_upkeep(scenario)

    scenario = _scenario()
    for mode in (_ZOMBIES, _LIFE, _DISCARD):
        _upkeep_choosing(scenario, mode)
    assert scenario.player("alice").life == 4
    assert scenario.player("alice").hand == []
    assert len(_zombies(scenario, "bob")) == 5

    # All three modes used: the fourth upkeep's trigger has nothing to choose
    # and changes nothing.
    _advance_into_alices_upkeep(scenario)
    _resolve_stack(scenario)
    assert len(_zombies(scenario, "bob")) == 5
    assert scenario.player("alice").life == 4


def test_each_player_creates_a_food_token():
    scenario = (
        Scenario()
        .player("alice", hand=["Party Dude"], battlefield=["Forest"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Party Dude")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    _resolve_stack(scenario)
    foods = [s for s in scenario.game.battlefield if s.name == "Food Token"]
    assert sorted(f.controller for f in foods) == ["alice", "bob"]
