"""Scenario: a trailing "that's `<color>` or `<color>`" after a compound noun
(CR 105.1, CR 115.1).

Refute Destiny reads "Exile target creature or planeswalker that's green or
blue." - `machines/targeting.py`'s `_read_phrase` read the compound noun
("creature or planeswalker") and then simply stopped: nothing in the noun
loop or the trailing-clause readers recognised "that's green or blue" the way
`_COLOR_PRESENCE_RE` already recognised "that's one or more colors" for a
single noun, so the whole restriction was silently dropped and the spell
would exile a red creature. Terminal Criticism ("that's blue or red")
misreads the identical way.

Fixed by `_extract_color_disjunction` (`_COLOR_DISJUNCTION_RE`), a new
trailing-clause reader tried alongside `_extract_color_presence`, and unioned
into `required_colors` after the compound-noun-list merge so it survives
whichever of `_read_phrase`'s two branches (uniform list vs Nissa's-Defeat-
style per-item colors) actually ran.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import spell_profile_for_text
from magic_cards_model.models import Color, Type, Zone

from .harness import Scenario


def test_refute_destiny_profile_reads_the_trailing_color_disjunction():
    profile = spell_profile_for_text(
        "Exile target creature or planeswalker that's green or blue. Surveil 1."
    )
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.card_types == {Type.CREATURE, Type.PLANESWALKER}
    assert requirement.required_colors == {Color.GREEN, Color.BLUE}


def test_refute_destiny_cannot_exile_a_red_creature():
    """The reported misread: a red creature used to be a legal target because
    the whole "that's green or blue" clause was dropped on the floor."""
    scenario = (
        Scenario()
        .player("alice", hand=["Refute Destiny"], battlefield=["Plains"] * 2)
        .player("bob", battlefield=["Raging Goblin"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Raging Goblin", "bob")

    with pytest.raises(ValueError, match="needs"):
        scenario.cast("Refute Destiny", username="alice", targets=[goblin])


def test_refute_destiny_exiles_a_legal_blue_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Refute Destiny"], battlefield=["Plains"] * 2)
        .player("bob", battlefield=["Merfolk Looter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    looter = scenario.creature("Merfolk Looter", "bob")
    sources = scenario.untapped_sources("Plains", "Plains")

    scenario.cast_and_resolve("Refute Destiny", *sources, targets=[looter])

    assert looter.zone is Zone.EXILE


def test_terminal_criticism_cannot_destroy_a_green_creature():
    """Terminal Criticism's own "that's blue or red" - the same misread on a
    different color pair and a different resolving verb (destroy, not
    exile)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Terminal Criticism"], battlefield=["Swamp"] * 2)
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    watchwolf = scenario.creature("Watchwolf", "bob")

    with pytest.raises(ValueError, match="needs"):
        scenario.cast("Terminal Criticism", username="alice", targets=[watchwolf])


def test_terminal_criticism_destroys_a_legal_red_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Terminal Criticism"], battlefield=["Swamp"] * 2)
        .player("bob", battlefield=["Raging Goblin"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Raging Goblin", "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp")

    scenario.cast_and_resolve("Terminal Criticism", *sources, targets=[goblin])

    assert goblin.zone is Zone.GRAVEYARD


# -- a parser-level proof that the color-disjunction fix and the         --
# -- `or_any_spell` fix (`test_spell_or_permanent_mixed_target.py`) do    --
# -- not step on each other in the same sentence -------------------------


def test_aether_gusts_profile_reads_both_the_spell_and_the_trailing_colors():
    """Aether Gust: "Choose target spell or permanent that's red or green."
    A profile-only check (this card's own resolution - "its owner puts it on
    their choice of the top or bottom of their library" - is a separate,
    unmodelled effect shape, out of this fix's scope) that both fixes read
    correctly at once: `or_any_spell` for the "spell or permanent" noun pair,
    and the trailing color disjunction for "that's red or green"."""
    profile = spell_profile_for_text(
        "Choose target spell or permanent that's red or green. Its owner puts "
        "it on their choice of the top or bottom of their library."
    )
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.or_any_spell
    assert requirement.required_colors == {Color.RED, Color.GREEN}


# -- off-set proof: a different card, a different color pair, a real -----
# -- cast-and-resolve rather than a profile-only check --------------------


def test_devout_decree_cannot_exile_a_green_creature():
    """Devout Decree: "Exile target creature or planeswalker that's black or
    red. Scry 1." - the same exile-and-look-at-the-top shape Refute Destiny
    itself uses, on a different color pair."""
    scenario = (
        Scenario()
        .player("alice", hand=["Devout Decree"], battlefield=["Plains"] * 2)
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    watchwolf = scenario.creature("Watchwolf", "bob")

    with pytest.raises(ValueError, match="needs"):
        scenario.cast("Devout Decree", username="alice", targets=[watchwolf])


def test_devout_decree_exiles_a_legal_red_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Devout Decree"], battlefield=["Plains"] * 2)
        .player("bob", battlefield=["Raging Goblin"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Raging Goblin", "bob")
    sources = scenario.untapped_sources("Plains", "Plains")

    scenario.cast_and_resolve("Devout Decree", *sources, targets=[goblin])

    assert goblin.zone is Zone.EXILE
