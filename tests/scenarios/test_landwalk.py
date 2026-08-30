"""Landwalk: evasion that reads the defending player's lands (CR 702.14).

CR 702.14b: "Landwalk is an evasion ability." CR 702.14c: "A creature with
landwalk can't be blocked as long as the defending player controls at least one
land with the specified land type."

That is a different shape from flying: flying asks what the *blocker* is, and
landwalk asks what the defending player's *lands* are, so the same blocker is
legal or illegal depending on a permanent that is not in combat at all. CR 305.6
names the five basic land types the pool uses.

CR 506.4a is why the third test matters: a creature that was legally declared as
a blocker stays a blocker even if the attacker later gains the evasion, so the
check has to happen at declaration and nowhere else.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def duel(*bob_permanents: str) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Street Wraith"])
        .player("bob", battlefield=list(bob_permanents))
    )


def test_swampwalk_cannot_be_blocked_while_the_defender_has_a_swamp():
    """CR 702.14c, the whole rule."""
    scenario = duel("Swamp", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wraith = scenario.creature("Street Wraith")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(wraith)

    assert not scenario.game.can_block(bears, wraith)
    with pytest.raises(ValueError, match="swampwalk"):
        scenario.block(wraith, bears)


def test_swampwalk_is_blockable_when_the_defender_has_no_swamp():
    """The ability is conditional, so a Forest is not a Swamp."""
    scenario = duel("Forest", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wraith = scenario.creature("Street Wraith")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(wraith)
    scenario.block(wraith, bears)

    assert scenario.blockers() == [bears]


def test_the_attackers_own_swamp_does_not_grant_evasion():
    """CR 702.14c looks at the *defending player's* lands, not everybody's."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Street Wraith", "Swamp"])
        .player("bob", battlefield=["Forest", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wraith = scenario.creature("Street Wraith")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(wraith)
    scenario.block(wraith, bears)

    assert scenario.blockers() == [bears]


def test_a_tapped_swamp_still_stops_the_block():
    """CR 702.14c says "controls", and a tapped land is still controlled."""
    scenario = duel("Swamp", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.creature("Grizzly Bears", "bob")
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "bob")
    swamp.tap()

    wraith = scenario.creature("Street Wraith")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(wraith)

    assert not scenario.game.can_block(bears, wraith)


def test_an_unblockable_swampwalker_reaches_the_player():
    """The evasion is the whole of it: nothing else about combat changes."""
    scenario = duel("Swamp", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wraith = scenario.creature("Street Wraith")
    scenario.attack_with(wraith)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 17
