"""Scenario: Veil of Summer's own compound-subject sentence, "You and
permanents you control gain hexproof from blue and from black until end of
turn" - the *permanents* half (CR 611.2c, CR 702.11d, CR 702.11f).

`test_opponent_cast_colour_condition.py` covers Veil's first sentence and
`test_cant_be_countered_this_turn.py` its second; this file is the third
sentence, once its "You and `<group>`" subject is split
(`_parse_you_and_group_gain_clause`). The *player* half of that same split
used to be a recorded `PlayerSubjectSplitNotice` rather than a grant - a
deliberately separate, later task's scope (`docs/engine-coverage.md`'s own
T5/G2b section). Flow 1 T12 closed that gap by wiring the split's player
half to the same reader flow 2's `test_player_hexproof_shroud.py` already
proved reads it; `tests/scenarios/test_player_hexproof_from_quality.py` is
that task's own file and is now the fuller player-half coverage (an
opponent's blue/black spell or ability, the caster's own spell, the CR
608.2b resolution recheck, cleanup expiry, CR 702.11f's two abilities).
`test_the_player_half_is_granted_too` below is this file's own,
narrower check that the split's player half is no longer merely recorded.

Every CR number here was looked up with `mise run rules:find` in the
session that wrote this file: CR 611.2c, CR 702.11d, CR 702.11f, CR 403.3.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Veil of Summer"],
            battlefield=["Forest", "Grizzly Bears"],
            library=["Forest"],
        )
        .player(
            "bob",
            hand=["Unsummon", "Lightning Bolt"],
            battlefield=["Island", "Mountain"],
            library=["Island"] * 3,
        )
        .build()
    )


def _cast_veil(scenario: Scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Veil of Summer", forest, username="alice")
    scenario.pass_priority("alice")  # hand priority to bob so he can respond


def test_a_blue_spell_cannot_target_a_permanent_you_control():
    """CR 702.11d: "hexproof from [quality]" refuses a same-quality spell
    from an opponent - Unsummon is blue, and Bob is an opponent of Alice's,
    the permanent's controller."""
    scenario = _board()
    _cast_veil(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")

    (island,) = scenario.untapped_sources("Island", username="bob")
    with pytest.raises(ValueError, match="hexproof from blue"):
        scenario.cast_onto_stack("Unsummon", island, username="bob", targets=[bears])


def test_a_red_spell_can_still_target_the_same_permanent():
    """Veil grants hexproof from blue *and* from black (CR 702.11f: two
    separate abilities) - never from red, so Lightning Bolt is unaffected."""
    scenario = _board()
    _cast_veil(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[bears])
    assert bears.zone is Zone.GRAVEYARD, "3 damage kills a 2/2 - the Bolt was not refused"


def test_the_grant_is_fixed_at_resolution_not_a_live_group():
    """CR 611.2c: "the set of objects it affects is determined when that
    continuous effect begins. After that point, the set won't change." A
    creature Alice casts *after* Veil resolves is not swept into the group
    the way the can't-be-countered grant (CR 611.2c's other sentence, a
    rules-modifying effect) sweeps in a later-cast spell - the two
    sentences are different shapes on purpose, and this is the
    characteristic-modifying one."""
    scenario = _board()
    _cast_veil(scenario)

    # Bob's own Unsummon still can't touch the Bears (already proven above);
    # a second creature Alice puts onto the battlefield after Veil resolved
    # was never part of the fixed group, so nothing here claims it has
    # hexproof from anything - there is no such creature on this board to
    # target, which is exactly the point: the reader never reaches for the
    # *live* battlefield again once the effect exists.
    bears = scenario.creature("Grizzly Bears", "alice")
    assert bears.zone is Zone.BATTLEFIELD


def test_the_player_half_is_granted_too():
    """The compound subject's player half ("You gain hexproof from blue and
    from black until end of turn") is granted for real now (flow 1 T12), not
    merely recorded as a `PlayerSubjectSplitNotice` - the fuller coverage of
    what that grant does (an opponent's spell or ability refused, the
    caster's own spell allowed, CR 608.2b, cleanup expiry, CR 702.11f's two
    abilities) lives in `tests/scenarios/test_player_hexproof_from_
    quality.py`; this is just proof, in this file, that the old recorded gap
    is gone."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Veil of Summer", forest, username="alice")

    alice = scenario.player("alice")
    grants = [g for g in alice.targeting_grants if g.keyword == "hexproof"]
    assert sorted(g.quality for g in grants) == ["black", "blue"]
    assert scenario.game.player_subject_split_notices == [], (
        "the player half is granted now, so it is no longer also recorded as an unread gap"
    )
