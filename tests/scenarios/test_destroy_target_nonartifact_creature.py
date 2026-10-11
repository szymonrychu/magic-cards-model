"""CR 701.8a, 601.2c: "Destroy target nonartifact creature." (Go for the Throat)

The restriction is part of the target (CR 601.2c: the player announces an
appropriate object for each target), so an artifact creature is refused at
announcement with the engine's own wording rather than being destroyed. The
destroy itself is CR 701.8a - battlefield to the owner's graveyard - and so
is stopped by indestructible (CR 702.12b) and replaced by a regeneration
shield (CR 701.19a), while exile and bounce are not "destroy".

CR numbers used, read with `mise run rules:find` in this session: CR 701.8a,
CR 701.19a, CR 702.12b, CR 601.2c, CR 608.2b.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

GFTT = "Go for the Throat"


def _board(*, bob: list[str], alice: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=[GFTT], battlefield=["Swamp", "Swamp", *(alice or [])])
        .player("bob", battlefield=bob)
    )


def _kill(scenario, target):
    swamps = scenario.untapped_sources("Swamp", "Swamp")
    scenario.cast_and_resolve(GFTT, *swamps, targets=[target])


def test_destroys_a_nonartifact_creature():
    scenario = _board(bob=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    _kill(scenario, bears)

    assert bears.zone is Zone.GRAVEYARD


def test_refuses_an_artifact_creature_in_the_engines_words():
    scenario = _board(bob=["Wurmcoil Engine"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.find("Wurmcoil Engine", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError, match="artifact"):
        scenario.cast(GFTT, targets=[wurm])

    assert wurm.zone is Zone.BATTLEFIELD


def test_refuses_a_noncreature_permanent():
    scenario = _board(bob=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError):
        scenario.cast(GFTT, targets=[mountain])


def test_refuses_a_player_as_the_target():
    scenario = _board(bob=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError):
        scenario.cast(GFTT, targets=["bob"])


def test_may_target_my_own_nonartifact_creature():
    scenario = _board(bob=[], alice=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    _kill(scenario, mine)

    assert mine.zone is Zone.GRAVEYARD


def test_an_enchantment_that_is_not_currently_a_creature_is_refused():
    """A God below its devotion threshold is an enchantment, not a creature,
    so "creature" in the target is not satisfied."""
    scenario = _board(bob=["Iroas, God of Victory"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    god = scenario.find("Iroas, God of Victory", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError, match="needs a creature"):
        scenario.cast(GFTT, targets=[god])


def test_indestructible_creature_survives():
    """CR 702.12b: an indestructible permanent can't be destroyed."""
    scenario = _board(bob=["Hazoret, Godseeker"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hazoret = scenario.find("Hazoret, Godseeker", Zone.BATTLEFIELD, "bob")

    _kill(scenario, hazoret)

    assert hazoret.zone is Zone.BATTLEFIELD


def test_a_regeneration_shield_replaces_the_destroy():
    """CR 701.19a: the next time it would be destroyed this turn, instead
    remove damage and tap it - it stays on the battlefield."""
    scenario = _board(bob=[], alice=["Manor Skeleton", "Swamp", "Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    skeleton = scenario.find("Manor Skeleton", Zone.BATTLEFIELD, "alice")
    scenario.activate(skeleton, *scenario.untapped_sources("Swamp", "Swamp"), index=0)
    scenario.pass_until_resolved()
    assert not skeleton.tapped

    _kill(scenario, skeleton)

    assert skeleton.zone is Zone.BATTLEFIELD
    assert skeleton.tapped


def test_without_a_shield_the_same_creature_dies():
    scenario = _board(bob=["Manor Skeleton"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    skeleton = scenario.find("Manor Skeleton", Zone.BATTLEFIELD, "bob")

    _kill(scenario, skeleton)

    assert skeleton.zone is Zone.GRAVEYARD


def test_target_gone_before_resolution_means_no_destruction():
    """CR 608.2b: the only target left the battlefield, so the spell does not
    resolve and the other creature is untouched."""
    scenario = _board(bob=["Grizzly Bears", "Llanowar Elves"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    swamps = scenario.untapped_sources("Swamp", "Swamp")
    scenario.cast_onto_stack(GFTT, *swamps, targets=[bears])
    scenario.game.return_to_hand(bears)
    scenario.resolve_top()

    assert scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "bob")
    assert scenario.find(GFTT, Zone.GRAVEYARD, "alice")
