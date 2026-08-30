"""Hexproof: a permanent an opponent cannot target (CR 702.11).

CR 702.11a: "Hexproof is a static ability." CR 702.11b: "'Hexproof' on a
permanent means "This permanent can't be the target of spells or abilities your
opponents control.""

The word doing the work is *opponents*. Hexproof is not shroud (CR 702.18a,
"can't be the target of spells or abilities" full stop), so the controller's own
spells target it happily - which is the first corner case here.

The refusal belongs at CR 601.2c, as the targets are announced, so an illegal
target is never chosen and the caster keeps their card. CR 702.11d's "hexproof
from [quality]" and CR 702.11c's hexproof on a player are not modelled; see
`docs/engine-coverage.md`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board(bolt_owner: str = "alice") -> Scenario:
    hands = {"alice": [], "bob": []}
    hands[bolt_owner] = ["Lightning Bolt"]
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hands["alice"],
            battlefield=["Mountain", "Striped Riverwinder"],
        )
        .player("bob", hand=hands["bob"], battlefield=["Mountain"])
    )


def test_an_opponent_cannot_target_a_hexproof_creature():
    """CR 702.11b, the whole rule."""
    scenario = board(bolt_owner="bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="has hexproof"):
        casting.choose_targets([riverwinder])


def test_its_own_controller_can_target_it():
    """Hexproof is not shroud: CR 702.11b only names *your opponents*."""
    scenario = board(bolt_owner="alice").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[riverwinder]
    )
    assert riverwinder.damage == 3


def test_a_refused_target_leaves_the_spell_in_hand():
    """CR 601.2c is an announcement step: a refusal is not a cast."""
    scenario = board(bolt_owner="bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError):
        casting.choose_targets([riverwinder])

    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    assert bolt.zone is Zone.HAND
    assert scenario.game.stack_is_empty


def test_the_opponents_face_is_still_a_legal_target():
    """A hexproof creature on the board changes nothing about other targets."""
    scenario = board(bolt_owner="bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    assert scenario.player("alice").life == 17


def test_hexproof_in_the_graveyard_protects_nothing():
    """CR 702.11b speaks of a *permanent*, and a permanent is on the battlefield.

    The engine has no card in the pool that targets a graveyard, so this asserts
    the shape of the check rather than a whole spell: a hexproof card that is
    not on the battlefield is not refused.
    """
    scenario = board(bolt_owner="bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")
    scenario.game.put_into_graveyard(riverwinder)

    casting = scenario.cast("Lightning Bolt", username="bob")
    assert casting._hexproof_refusal(riverwinder) is None
