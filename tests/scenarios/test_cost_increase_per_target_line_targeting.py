"""Scenario: "This spell costs {1} more to cast for each target beyond the
first." (Fireball; Launch the Fleet's identically-worded "Strive —" clause)
poisoned `machines/targeting.py`'s own scan, not just `machines/effects.py`'s
resolution-effect one.

`_TARGET_WORD` scans a card's *whole* oracle text for the literal word
"target" and reads a noun phrase after each occurrence (`_parse`,
`machines/targeting.py`). The cost-increase line's own "for each **target**
beyond the first" is not a noun phrase at all - "beyond the first" is not a
noun `_read_phrase` can read - so the whole card's targeting profile came
back `understood=False`. That is worse than not modelling the line: an
unread restriction is not enforced, so Launch the Fleet's real "any number of
**target creatures**" restriction went unchecked too, and a land was a legal
target for a spell that reads "creatures" in plain English. Fireball's own
"any number of targets" (CR 115.4's bare "any target") happened to mask the
same defect, since it already accepts anything.

`machines/effects.py` already had `_COST_INCREASE_PER_TARGET_LINE_RE` to keep
this exact line from poisoning *its* own resolution-effect parse
(`_strip_non_effect_preamble`); `machines/targeting.py` had no matching
reader at all. Fixed by `_COST_INCREASE_PER_TARGET_LINE`, duplicated rather
than imported for the same circular-import reason `_SELF_COST_REDUCTION_LINE`
already is (see its own docstring).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import spell_profile_for_text
from magic_cards_model.models import Type, Zone

from .harness import Scenario


def test_fireballs_profile_is_understood():
    profile = spell_profile_for_text(
        "This spell costs {1} more to cast for each target beyond the first.\n"
        "Fireball deals X damage divided evenly, rounded down, among any number "
        "of targets."
    )
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.unbounded


def test_launch_the_fleets_profile_is_understood_and_creature_only():
    profile = spell_profile_for_text(
        "Strive — This spell costs {1} more to cast for each target beyond the "
        "first.\nUntil end of turn, any number of target creatures each gain "
        '"Whenever this creature attacks, create a 1/1 white Soldier creature '
        "token that's tapped and attacking.\""
    )
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.card_types == {Type.CREATURE}


def test_launch_the_fleet_cannot_target_a_land():
    """The reported misread: `understood=False` left the real "target
    creatures" restriction unenforced, so a land was a legal target."""
    scenario = (
        Scenario()
        .player("alice", hand=["Launch the Fleet"], battlefield=["Plains"] * 3)
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError, match="creature"):
        scenario.cast("Launch the Fleet", username="alice", targets=[forest])


def test_launch_the_fleet_targets_a_legal_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Launch the Fleet"],
            battlefield=["Plains", "Plains", "Plains", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")

    casting = scenario.cast("Launch the Fleet", username="alice")
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()


def test_fireball_still_announces_two_targets():
    """A basic play-through with the fix in place, off the reported card
    itself - CR 115.4's "any target" still accepts two creatures at once,
    which is all the targeting profile itself is responsible for. Fireball's
    own "divided evenly, rounded down" split is a separate, un-modelled
    mechanic (`machines/targeting.py`'s `_DIVIDED` only reads "divided [as
    you choose] among") and no part of this fix."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fireball"], battlefield=["Mountain"] * 10)
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    casting = scenario.cast("Fireball", username="alice")
    casting.choose_targets([bears, giant])

    assert len(casting.targets) == 2
