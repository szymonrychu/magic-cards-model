"""Scenario: a "non`<color>`" leading adjective (CR 105.2's negation) is not
read at all.

Cradle to Grave reads "Destroy target nonblack creature that entered this
turn." - `_Adjectives.take` (`machines/targeting.py`) already reads a "non-"
prefix against card types (`_negated_type`) and against supertypes
(`_negated_supertype`), but had no matching reader for a color word at all.
So "nonblack" was not recognised as an adjective, `_read_adjectives` stopped
before it, and the whole noun phrase - "nonblack creature that entered this
turn" - was read as an unrecognised leading word, failing the phrase closed
(`understood=False`). That silently un-enforced *every* restriction on the
card, "that entered this turn" included, not merely the color one - the same
`understood=False` blast radius `test_cost_increase_per_target_line_
targeting.py` already documents for an unrelated preamble line.

Fixed by `_negated_color` (CR 105.1's five colors), read the identical way
`_negated_type`/`_negated_supertype` already are, plus a new
`TargetRequirement.excluded_colors` field and its own check inside `rejects`
(CR 105.2's "no color" case - `_current_colors`, the same helper
`required_colors`' own check already uses, correctly still lets a colorless
creature through a "non`<color>`" restriction, since it has none of the
excluded color either).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import spell_profile_for_text
from magic_cards_model.models import Color, Zone

from .harness import Scenario


def test_cradle_to_graves_profile_reads_the_excluded_color():
    profile = spell_profile_for_text("Destroy target nonblack creature that entered this turn.")
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.excluded_colors == {Color.BLACK}
    assert requirement.must_have_entered_this_turn


def test_cradle_to_grave_cannot_destroy_a_black_creature():
    """The reported misread: "nonblack" was not read at all, so a black
    creature that entered this turn was a legal target. Both creature and
    removal are cast by the same active player - only alice has priority to
    cast a sorcery-speed spell during her own precombat main phase (CR
    117.1a), and Cradle to Grave's "nonblack" restriction does not care who
    controls its target."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cradle to Grave", "Carrion Feeder"],
            battlefield=["Swamp", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    feeder = scenario.cast_and_resolve(
        "Carrion Feeder", *scenario.untapped_sources("Swamp"), username="alice"
    )

    with pytest.raises(ValueError, match="cannot target"):
        scenario.cast("Cradle to Grave", username="alice", targets=[feeder])


def test_cradle_to_grave_destroys_a_legal_nonblack_creature_that_entered_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cradle to Grave", "Grizzly Bears"],
            battlefield=["Swamp", "Swamp", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.cast_and_resolve(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"), username="alice"
    )
    sources = scenario.untapped_sources("Swamp", "Swamp")

    scenario.cast_and_resolve("Cradle to Grave", *sources, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD


def test_cradle_to_grave_cannot_destroy_a_nonblack_creature_from_a_previous_turn():
    """The other half of the restriction, unrelated to color, still holds -
    this fix must not have loosened "that entered this turn" while fixing
    the color half."""
    scenario = (
        Scenario()
        .player("alice", hand=["Cradle to Grave"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="entered this turn"):
        scenario.cast("Cradle to Grave", username="alice", targets=[bears])


# -- off-set proof: a different card, a different excluded color, and a --
# -- direct-damage verb rather than destroy ------------------------------


def test_sunlances_profile_reads_the_excluded_color():
    profile = spell_profile_for_text("Sunlance deals 3 damage to target nonwhite creature.")
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.excluded_colors == {Color.WHITE}


def test_sunlance_cannot_target_a_white_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Sunlance"], battlefield=["Plains"] * 2)
        .player("bob", battlefield=["Kinsbaile Skirmisher"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    skirmisher = scenario.creature("Kinsbaile Skirmisher", "bob")

    with pytest.raises(ValueError, match="cannot target"):
        scenario.cast("Sunlance", username="alice", targets=[skirmisher])


def test_sunlance_deals_damage_to_a_legal_nonwhite_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Sunlance"], battlefield=["Plains"] * 2)
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    sources = scenario.untapped_sources("Plains", "Plains")

    scenario.cast_and_resolve("Sunlance", *sources, targets=[dreadmaw])

    assert dreadmaw.damage == 3


def test_sunlance_can_target_a_colorless_creature():
    """CR 105.2c: a colorless creature has no color at all, so it has none of
    the excluded color either - the negation must not become an accidental
    "must be colored" restriction."""
    scenario = (
        Scenario()
        .player("alice", hand=["Sunlance"], battlefield=["Plains"] * 2)
        .player("bob", battlefield=["Wurmcoil Engine"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    engine = scenario.creature("Wurmcoil Engine", "bob")
    sources = scenario.untapped_sources("Plains", "Plains")

    scenario.cast_and_resolve("Sunlance", *sources, targets=[engine])

    assert engine.damage == 3
