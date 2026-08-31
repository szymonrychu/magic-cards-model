"""Scenario: Voice of Victory's "Your opponents can't cast spells during your
turn."

CR 601.3 is the prohibition - "a player can begin to cast a spell only if a
rule or effect allows that player to cast it and no rule or effect prohibits
that player from casting it" - and CR 101.2 is why it beats CR 117.1a's
ordinary instant-speed permission outright rather than merely competing with
it.

Two conditions ride in one sentence, and each is a separate way to get this
wrong:

- **Who.** "Your opponents", so never the controller. CR 611.1's continuous
  effect "affects players or the rules of the game"; nothing is written to a
  layer (CR 613.11).
- **When.** "During your turn", which is CR 102.1's active player: "the active
  player is the player whose turn it is. The other players are nonactive
  players." The window opens and shuts with the turn while the permanent never
  moves, which is exactly the case CR 611.3a describes - a static's continuous
  effect "isn't 'locked in'; it applies at any given moment to whatever its
  text indicates" - so
  `machines.casting_restrictions.blanket_cant_cast_restriction` re-reads the
  battlefield on every call and caches nothing.

Both players hold instants throughout, because a scenario that only ever asks
about a sorcery cannot tell this restriction apart from ordinary sorcery-speed
timing.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(*, voices_for: tuple[str, ...] = ("alice",)) -> Scenario:
    def battlefield(username: str) -> list[str]:
        lands = ["Mountain"] * 3
        return lands + (["Voice of Victory"] if username in voices_for else [])

    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=battlefield("alice"),
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=battlefield("bob"),
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


def _take_priority(scenario, username: str) -> None:
    if scenario.priority_holder != username:
        scenario.pass_priority(scenario.priority_holder)


# -- the window it closes ---------------------------------------------------


def test_an_opponent_cannot_cast_an_instant_during_the_controllers_turn():
    """The measured gap: three maindeck copies whose defining ability did
    nothing, and the opponent cast freely all game."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _take_priority(scenario, "bob")

    with pytest.raises(ValueError, match="Voice of Victory"):
        scenario.cast("Lightning Bolt", username="bob", targets=["alice"])

    assert scenario.player("alice").life == 20


def test_the_controller_casts_freely_during_their_own_turn():
    """ "Your opponents" - never "each player"; the controller is exempt."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = _bolt(scenario, "alice", "bob")

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


# -- the window it leaves open ----------------------------------------------


def test_the_opponent_casts_freely_during_their_own_turn():
    """ "During your turn" is the whole window: on bob's own turn, alice's
    Voice of Victory stops nothing, even though it never left the
    battlefield."""
    scenario = _board()
    _advance_to_bobs_precombat_main(scenario)

    bolt = _bolt(scenario, "bob", "alice")

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 17


def test_the_controller_is_not_locked_out_on_the_opponents_turn():
    """Alice is nobody's opponent for the purposes of her own Voice, and bob
    controls none - so her instant on his turn is fine."""
    scenario = _board()
    _advance_to_bobs_precombat_main(scenario)

    bolt = _bolt(scenario, "alice", "bob")

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


def test_each_copy_only_closes_its_own_controllers_turn():
    """Both players control one. On alice's turn only bob is locked out; the
    reading "a Voice of Victory anywhere locks out everyone" would catch alice
    here too, and the reading "it locks out its own controller" would catch
    her instead."""
    scenario = _board(voices_for=("alice", "bob"))
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = _bolt(scenario, "alice", "bob")
    assert bolt.zone is Zone.GRAVEYARD

    _take_priority(scenario, "bob")
    with pytest.raises(ValueError, match="Voice of Victory"):
        scenario.cast("Lightning Bolt", username="bob", targets=["alice"])


def test_the_lockout_dies_with_the_permanent():
    """CR 604.2: the effect is active only while the permanent is on the
    battlefield, and CR 611.3a stops it from being locked in for the rest of
    the turn."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _take_priority(scenario, "bob")

    with pytest.raises(ValueError, match="Voice of Victory"):
        scenario.cast("Lightning Bolt", username="bob", targets=["alice"])

    (voice,) = [c for c in scenario.game.battlefield if c.name == "Voice of Victory"]
    scenario.game.destroy(voice)

    bolt = _bolt(scenario, "bob", "alice")

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 17
