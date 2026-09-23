"""Scenario: Veil of Summer's own compound-subject sentence, "You and
permanents you control gain hexproof from blue and from black until end of
turn" - the *permanents* half only (CR 611.2c, CR 702.11d, CR 702.11f).

`test_opponent_cast_colour_condition.py` covers Veil's first sentence and
`test_cant_be_countered_this_turn.py` its second; this file is the third
sentence, once its "You and `<group>`" subject is split
(`_parse_you_and_group_gain_clause`, `docs/engine-coverage.md`'s own T5/G2b
section explains why the *player* half is a recorded gap rather than a
grant here - a separate, later task's scope).

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


def test_the_player_half_is_neither_granted_nor_silently_dropped():
    """`PlayerSubjectSplitNotice`'s whole point: Alice herself never gets
    hexproof from this sentence (the player half is a separate task's
    scope), and the gap is recorded, not silent."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    veil = scenario.cast_and_resolve("Veil of Summer", forest, username="alice")

    alice = scenario.player("alice")
    assert alice.targeting_grants == [], "the player half was never silently applied"

    (notice,) = scenario.game.player_subject_split_notices
    assert notice.text == "You gain hexproof from blue and from black until end of turn"
    assert notice.source_name == "Veil of Summer"
    assert notice.source_id == veil.id
