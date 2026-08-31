"""Scenario: High Noon's "Each player can't cast more than one spell each turn."

CR 601.3: "A player can begin to cast a spell only if a rule or effect allows
that player to cast it and no rule or effect prohibits that player from casting
it." CR 101.2 is why the prohibition beats the ordinary permission CR 117.1a
gives: "when a rule or effect allows or directs something to happen, and
another effect states that it can't happen, the 'can't' effect takes
precedence."

The effect itself is CR 611.1's third kind - a continuous effect that "affects
players or the rules of the game" rather than any characteristic - so it writes
no layer (CR 613.11) and is read directly by
`machines.casting_restrictions.blanket_cant_cast_restriction`, live off the
battlefield on every call (CR 611.3a: a static's effect "isn't 'locked in'").

The count itself is `Game.spells_cast_this_turn`, which the storm scenarios
already prove counts casts and not copies (CR 707.10: "a copy of a spell isn't
cast").

Every test below checks both players, because "each player" includes High
Noon's own controller - a restriction that reads "your opponents" by mistake
passes a single-player scenario perfectly.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(*, high_noon_for: str = "alice") -> Scenario:
    alice_battlefield = ["Mountain"] * 4
    bob_battlefield = ["Mountain"] * 4
    if high_noon_for == "alice":
        alice_battlefield.append("High Noon")
    else:
        bob_battlefield.append("High Noon")
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Lightning Bolt", "Mountain"],
            battlefield=alice_battlefield,
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=bob_battlefield,
            library=["Mountain"] * 5,
        )
        .build()
    )


def _advance_to_bobs_precombat_main(scenario) -> None:
    while scenario.turn.active_player != "bob" or scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()


def _bolt(scenario, username: str, at: str):
    if scenario.priority_holder != username:
        scenario.pass_priority(scenario.priority_holder)
    (mountain,) = scenario.untapped_sources("Mountain", username=username)
    return scenario.cast_and_resolve("Lightning Bolt", mountain, username=username, targets=[at])


# -- the cap itself ---------------------------------------------------------


def test_the_first_spell_of_the_turn_is_cast_normally():
    """ "More than one" is the whole restriction: one is fine."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = _bolt(scenario, "alice", "bob")

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


def test_the_second_spell_of_the_turn_is_refused():
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt(scenario, "alice", "bob")

    with pytest.raises(ValueError, match="High Noon"):
        scenario.cast("Lightning Bolt", username="alice", targets=["bob"])

    assert scenario.player("bob").life == 17, "the refused Bolt never dealt its damage"


def test_the_cap_catches_high_noons_own_controller_and_the_opponent_alike():
    """ "Each player", not "your opponents" - staged from bob's side of the
    board so that swapping the two readings cannot pass."""
    scenario = _board(high_noon_for="bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt(scenario, "alice", "bob")

    with pytest.raises(ValueError, match="High Noon"):
        scenario.cast("Lightning Bolt", username="alice", targets=["bob"])

    _advance_to_bobs_precombat_main(scenario)
    _bolt(scenario, "bob", "alice")

    with pytest.raises(ValueError, match="High Noon"):
        scenario.cast("Lightning Bolt", username="bob", targets=["alice"])


def test_each_player_gets_their_own_one_spell_in_the_same_turn():
    """The count is per player, not per turn: bob's instant on alice's turn is
    his first spell, not her second."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt(scenario, "alice", "bob")

    bobs_bolt = _bolt(scenario, "bob", "alice")

    assert bobs_bolt.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 17

    with pytest.raises(ValueError, match="High Noon"):
        scenario.cast("Lightning Bolt", username="bob", targets=["alice"])


# -- what the cap does not catch --------------------------------------------


def test_the_cap_resets_on_the_next_turn():
    """ "Each turn" - `Game.spells_cast_this_turn` is emptied at the turn
    boundary, so alice's second copy is castable, just not on the same turn."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt(scenario, "alice", "bob")
    _advance_to_bobs_precombat_main(scenario)

    bolt = _bolt(scenario, "alice", "bob")

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 14


def test_playing_a_land_is_not_casting_a_spell():
    """CR 601.3 is about *casting*; a land is a special action that uses no
    stack at all, so the cap never sees it."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt(scenario, "alice", "bob")

    mountain = scenario.play_land("Mountain", username="alice")

    assert mountain.zone is Zone.BATTLEFIELD


def test_the_cap_dies_with_the_permanent():
    """CR 604.2: the continuous effect lasts exactly as long as the permanent
    is on the battlefield, and CR 611.3a keeps it from being locked in - so a
    High Noon that has left mid-turn no longer stops the second spell, even
    though the first was cast while it was out."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt(scenario, "alice", "bob")

    (high_noon,) = [c for c in scenario.game.battlefield if c.name == "High Noon"]
    scenario.game.destroy(high_noon)

    bolt = _bolt(scenario, "alice", "bob")

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 14
