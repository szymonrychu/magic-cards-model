"""Scenario: Samut, Tyrant of Naktamun's "Instant and sorcery spells you
control have split second." - both the group-grant *reader* (does a
controller have the grant right now) and, since the fra-s9/int-engine-dsl
merge that reconciled the two, its actual enforcement on the stack
(CR 702.61a), wired onto the same `split_second_restriction_source` FRA
stream S10 built for a printed split second card (`test_split_second.py`'s
Sudden Shock).

CR 702.61a: "Split second is a static ability that functions only while the
spell with split second is on the stack. 'Split second' means 'As long as
this spell is on the stack, players can't cast other spells or activate
abilities that aren't mana abilities.'" That is a property of a *spell*, not
of a battlefield permanent - nothing `machines/layers.py`'s board ever
computes reaches a spell on the stack - so Samut's own grant cannot be read
the way every other keyword grant in this codebase is (a `ContinuousEffect`
applied to the spell's characteristics). Instead the grant lands on Samut's
own characteristics as a fixed marker (`SPELLS_HAVE_SPLIT_SECOND_TEXT`), and
`Game.controls_split_second_grant` is the one place that asks for it: "does
this player have a permanent granting the group split second right now" -
CR 613.5's live re-ask, the same as every other static grant in this stream.

Before the merge, `split_second_restriction_source` (`machines/casting.py`,
S10's build) checked only `has_split_second` - a spell's own printed
Scryfall keyword - so a spell that only had split second through Samut's
grant was never locked. It now also asks, for an instant or sorcery spell on
the stack, whether its controller currently holds the group grant
(`Game.controls_split_second_grant`) - one keyword model, not two, exactly
as that method's own docstring already named as its intended caller.

No other real Magic card was found (Scryfall `o:"spells you control have
split second"`) printing this exact group-grant sentence, so there is no
off-set FRA-CLAUDE.md card to add for it; the reader is still built to the
same general "self-only grant plus a board-wide checker" shape this stream
already used for Torpor Orb/Karn's trigger suppression and Traxos/Infinite
Coursework's "doesn't untap", proven generic by both of those, not
special-cased for Samut's name.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and the card's text with
`resolve_cards` or straight off its fixture.
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_samut_grants_the_group_split_second_marker_to_her_own_controller():
    scenario = (
        Scenario().player("alice", battlefield=["Samut, Tyrant of Naktamun"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.game.controls_split_second_grant("alice")
    assert not scenario.game.controls_split_second_grant("bob")


def test_the_grant_goes_away_once_samut_leaves():
    scenario = (
        Scenario().player("alice", battlefield=["Samut, Tyrant of Naktamun"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    samut = scenario.creature("Samut, Tyrant of Naktamun", "alice")

    scenario.game.destroy(samut)

    assert not scenario.game.controls_split_second_grant("alice")


def test_no_grant_at_all_with_no_samut_on_the_battlefield():
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert not scenario.game.controls_split_second_grant("alice")
    assert not scenario.game.controls_split_second_grant("bob")


# -- CR 702.61a's own enforcement, reached through the granted split second --


def _enforcement_board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Samut, Tyrant of Naktamun", "Mountain"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_spell_that_only_has_split_second_through_the_grant_locks_the_stack():
    """The gap the merge closed: before it, `split_second_restriction_source`
    read only a spell's own printed keyword, so a Lightning Bolt that only
    has split second through Samut's grant never locked anything."""
    scenario = _enforcement_board()
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.pass_priority("alice")

    with pytest.raises(ValueError, match="CR 702.61a"):
        scenario.cast("Lightning Bolt", username="bob")


def test_the_grant_does_not_reach_an_opponents_spell():
    """CR 702.61a's "spells you control" - alice's grant says nothing about
    a spell bob controls, so bob's own Lightning Bolt never locks anything on
    its own way to the stack, and only alice's granted one does."""
    scenario = _enforcement_board()
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=["alice"])

    assert scenario.player("alice").life == 17


def test_with_no_samut_the_same_spell_locks_nothing():
    """Control: the identical Lightning Bolt, with no Samut on the
    battlefield, has no split second at all and locks nothing."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (alice_mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", alice_mountain, username="alice", targets=["bob"])
    scenario.pass_priority("alice")

    (bob_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", bob_mountain, username="bob", targets=["alice"])
    assert scenario.stack_names() == ["Lightning Bolt", "Lightning Bolt"]
