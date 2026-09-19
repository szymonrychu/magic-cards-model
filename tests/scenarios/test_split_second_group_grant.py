"""Scenario: Samut, Tyrant of Naktamun's "Instant and sorcery spells you
control have split second." - the group-grant *reader* half of this
mechanic; CR 702.61a's split second itself (what it does while the spell is
on the stack) is FRA stream S10's own build, tracked separately.

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
Whatever S10 lands for split second's own enforcement combines this with a
spell's card type (instant or sorcery) the same way any other keyword-check
combines a grant with the object it might apply to.

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
