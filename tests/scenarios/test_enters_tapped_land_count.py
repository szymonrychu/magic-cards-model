"""A land that enters tapped depending on how many *other* lands its
controller already controls - CR 614.1d's bare "[This land] enters . . ."
replacement, conditioned on the board, in both printed polarities:

- Darkslick Shores / Spirebluff Canal: "This land enters tapped **unless**
  you control two or fewer other lands." Untapped while the board is small,
  tapped once it grows - the fastland cycle's own shape.
- Hall of Storm Giants: "**If** you control two or more other lands, this
  land enters tapped." The leading-`If` polarity instead of the trailing-
  `unless` one, over the same count and the same threshold, which is what
  tells `machines/replacement._ENTERS_TAPPED` the two apart (its own module
  docstring: a leading "If <cond>," taps when the condition *holds*, a
  trailing "unless <cond>" taps when it does *not*).

Both read the identical count - "other" lands, excluding the entering land
itself, off the *computed* board (CR 613.5) - through the same
`machines.replacement._controls_other_lands`/`_YOU_CONTROL_OTHER_LANDS_RE`
this file does not modify; the two land shapes are proven here as coverage of
an already-built reader, not as a new one.

Every CR number below was looked up with `mise run rules:find <n>` in the
session that wrote this file.

- **CR 614.1d** - "[This permanent] enters . . ." or "[Objects] enter [the
  battlefield] . . ." are replacement effects.
- **CR 614.12** - such an effect may come from the permanent itself if it
  affects only that permanent, and is judged on the board as the permanent
  would exist on the battlefield, before it is actually there - so a land
  never counts itself among the "other lands" it is asking about.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def _board(land, battlefield=(), bob_battlefield=()):
    scenario = (
        Scenario()
        .player("alice", hand=[land], battlefield=list(battlefield))
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Darkslick Shores / Spirebluff Canal: "unless you control two or fewer
# other lands" ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("other_lands", "tapped"),
    [
        ([], False),
        (["Forest"], False),
        (["Forest", "Island"], False),
        (["Forest", "Island", "Swamp"], True),
        (["Forest", "Island", "Swamp", "Mountain"], True),
    ],
)
def test_darkslick_shores_enters_tapped_once_three_other_lands_are_out(other_lands, tapped):
    scenario = _board("Darkslick Shores", other_lands)

    shores = scenario.play_land("Darkslick Shores")

    assert shores.zone is Zone.BATTLEFIELD
    assert shores.tapped is tapped


def test_spirebluff_canal_reads_the_identical_condition_on_a_different_printing():
    """Same template, a different card and a different pair of colours -
    proof this is the shared reader, not a Darkslick-only patch."""
    untapped = _board("Spirebluff Canal", ["Forest", "Island"])
    assert untapped.play_land("Spirebluff Canal").tapped is False

    tapped = _board("Spirebluff Canal", ["Forest", "Island", "Swamp"])
    assert tapped.play_land("Spirebluff Canal").tapped is True


def test_darkslick_shores_does_not_count_an_opponents_lands():
    """ "You control" (CR 109.5) - only alice's own lands are "other lands"
    for her own entering fastland; bob's board is irrelevant."""
    scenario = _board(
        "Darkslick Shores",
        battlefield=["Forest", "Island"],
        bob_battlefield=["Swamp", "Mountain", "Plains", "Plains"],
    )

    shores = scenario.play_land("Darkslick Shores")

    assert shores.tapped is False


# -- Hall of Storm Giants: "If you control two or more other lands, this land
# enters tapped" - the opposite polarity, same threshold ---------------------


@pytest.mark.parametrize(
    ("other_lands", "tapped"),
    [
        ([], False),
        (["Island"], False),
        (["Island", "Forest"], True),
        (["Island", "Forest", "Swamp"], True),
    ],
)
def test_hall_of_storm_giants_enters_tapped_once_two_other_lands_are_out(other_lands, tapped):
    scenario = _board("Hall of Storm Giants", other_lands)

    hall = scenario.play_land("Hall of Storm Giants")

    assert hall.zone is Zone.BATTLEFIELD
    assert hall.tapped is tapped


def test_hall_of_storm_giants_untapped_land_still_taps_for_its_own_mana():
    """No summoning-sickness restriction on a land's mana ability (CR 302.6
    only reaches creatures) - an untapped Hall of Storm Giants can tap for
    {U} the same turn it enters."""
    scenario = _board("Hall of Storm Giants", ["Island"])

    hall = scenario.play_land("Hall of Storm Giants")
    assert hall.untapped

    scenario.activate(hall)
    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 1}
