"""Into the Flood Maw: "Gift a tapped Fish (...) Return target creature an
opponent controls to its owner's hand. If the gift was promised, instead
return target nonland permanent an opponent controls to its owner's hand."

The reported defect: a seat cast this at Ragavan, Nimble Pilferer (an
opponent's creature, no gift promised) and the engine refused the
announcement with "too few targets: 1 chosen where the spell requires 2",
then accepted the same object chosen twice as two "different" targets, then
resolved doing nothing at all (`"resolved": true, "changed": false`).

Two independent defects, both now fixed:

- `machines/targeting.py`'s `_parse` counted the "If the gift was promised,
  instead return target nonland permanent ..." clause as a *second*
  requirement of the spell's own, so the card demanded two targets at once
  when CR 601.2c ("a spell may require alternative targets only if an
  alternative or additional cost ... was chosen for it") - and CR 702.174m
  by name - says it has exactly one, whichever branch applies.
  `TargetRequirement.if_gift_promised` / `TargetingProfile.for_gift_promise`
  is the fix; `tests/test_targeting.py` covers the parser directly.
- `machines/effects.py` had no clause shape for the "If the gift was
  promised, instead ..." sentence, so `_parse_mixed_clauses` failed the
  *whole card* closed and it resolved doing nothing.
  `_parse_gift_promised_return_instead_clause` reads the two sentences as one
  CR 608.2c instruction - `return_ability_targets_to_hand`, unchanged,
  since both branches print the identical verb and only differ in which
  targets were legal to choose in the first place (the targeting layer's
  job, not this one's).

CR 601.2c, CR 702.174a, CR 702.174k, CR 702.174m and CR 115.3 were all looked
up with `mise run rules:find` in the session that wrote this file (the
`knowledge_search` MCP tool was unavailable, so the on-disk `.rules/
MagicCompRules.txt` primary source was used directly, per this repo's
`CLAUDE.md`).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Alice holds Into the Flood Maw and a land; bob holds what it might hit."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Into the Flood Maw"],
            battlefield=["Island"],
            library=["Forest"],
        )
        .player("bob", battlefield=["Ragavan, Nimble Pilferer", "Forest", "Sol Ring"])
    )


def test_bounces_an_opponents_creature_with_no_gift_promised():
    """The reported case, faithfully reproduced: one target, no gift, resolved.

    CR 601.2c: with no gift promised the spell requires exactly one target -
    "target creature an opponent controls" - and Ragavan satisfies it.
    `changed: false` in the original report is a before/after state diff, not
    proof the resolution did nothing (trap 8), so this asserts the actual
    board: Ragavan really moves, and moves exactly once (not twice, which is
    what the old bug's "same object chosen for both slots" would have done
    had `return_ability_targets_to_hand` ever been reached).
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="alice")
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "bob")

    maw = scenario.cast_and_resolve(
        "Into the Flood Maw", island, username="alice", targets=[ragavan]
    )

    assert maw.zone is Zone.GRAVEYARD
    assert ragavan.zone is Zone.HAND
    assert [state.name for state in scenario.player("bob").hand] == ["Ragavan, Nimble Pilferer"]
    # Exactly one copy in bob's hand, not a double-bounced duplicate entry -
    # what defect B's "same object twice" symptom would have produced had it
    # ever reached resolution.
    assert len(scenario.player("bob").hand) == 1
    assert [state.name for state in scenario.game.permanents_controlled_by("bob")] == [
        "Forest",
        "Sol Ring",
    ]


def test_refuses_one_target_chosen_twice():
    """Reproduces the raw log's own seq 210: the engine used to accept the
    *same* Ragavan chosen for both of two counted slots (CR 115.3 correctly
    allows sharing a target across two real instances of the word "target" -
    `_why_not` already gets this right) only because defect A wrongly told it
    there were two slots to begin with. With exactly one slot, offering two
    targets - the same object twice or two different ones - is "too many",
    not a legal double-booking.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "bob")

    with pytest.raises(ValueError, match="too many targets"):
        scenario.cast_onto_stack(
            "Into the Flood Maw", auto=True, username="alice", targets=[ragavan, ragavan]
        )


def test_refuses_a_land():
    """CR 601.2c: "target creature" needs a creature. A land is not one, and
    the engine's own reason says so (trap 4: `understood=False` would instead
    silently wave any object through).
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.creature("Forest", "bob")

    with pytest.raises(ValueError, match="creature"):
        scenario.cast_onto_stack(
            "Into the Flood Maw", auto=True, username="alice", targets=[forest]
        )


def test_refuses_a_creature_alice_controls():
    """ "an opponent controls" (`ControllerRestriction.OPPONENT`) refuses
    alice's own creature, not merely creatures in general (trap 4's second
    half).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Into the Flood Maw"],
            battlefield=["Island", "Grizzly Bears"],
            library=["Forest"],
        )
        .player("bob", battlefield=["Ragavan, Nimble Pilferer"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    with pytest.raises(ValueError, match="controls"):
        scenario.cast_onto_stack("Into the Flood Maw", auto=True, username="alice", targets=[bears])


@pytest.mark.xfail(
    strict=True,
    reason="Gift is deliberately not implemented as a payable additional cost "
    "(machines/casting.py's ADDITIONAL_COST_KEYWORDS, CR 118.8a, has no 'gift' entry - "
    "grep -rni gift --include=*.py src/ finds nothing that lets a caster promise one), "
    "so nothing can ever make TargetingProfile.for_gift_promise(True) the profile a real "
    "cast actually checks. Once gift lands as a real additional cost, this should legally "
    "target bob's Sol Ring - a nonland permanent that is not a creature, the promised "
    "branch's own candidate set - the same way test_targeting.py's "
    "test_into_the_flood_maw_promised_branch_targets_a_nonland_noncreature_permanent "
    "already proves the parser reads it correctly today.",
)
def test_promised_bounces_a_noncreature_nonland_permanent():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="alice")
    sol_ring = scenario.creature("Sol Ring", "bob")

    maw = scenario.cast_and_resolve(
        "Into the Flood Maw", island, username="alice", targets=[sol_ring]
    )

    assert maw.zone is Zone.GRAVEYARD
    assert sol_ring.zone is Zone.HAND
