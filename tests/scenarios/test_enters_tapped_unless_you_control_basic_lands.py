"""A land that enters tapped unless its controller controls enough basic lands.

"This land enters tapped unless you control two or more basic lands." is a
self enters-tapped line with a condition about the board: how many lands with
the basic supertype the entering land's controller controls as it enters.

Rules, each read in full with `mise run rules:find` in the session that wrote
this file:

- **CR 614.1d** - "[This permanent] enters . . ." is a replacement effect, and
  its condition is checked as the permanent would enter.
- **CR 614.12** - such an effect comes from the permanent itself and applies
  before it is on the battlefield, so it never counts itself.
- **CR 205.4c** - "Any land with the supertype 'basic' is a basic land. Any
  land that doesn't have this supertype is a nonbasic land, even if it has a
  basic land type." A shockland is an Island and a Swamp and still not basic.
"""

import pytest

from magic_cards_model.machines import EntersState, Step, predict_enters
from magic_cards_model.machines.replacement import unread_self_enters_tapped_lines
from magic_cards_model.models import Zone
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


@pytest.mark.parametrize(
    ("battlefield", "tapped"),
    [
        ([], True),
        (["Forest"], True),
        (["Forest", "Plains"], False),
        (["Forest", "Plains", "Island"], False),
    ],
)
def test_canopy_vista_counts_basic_lands(battlefield, tapped):
    scenario = _board("Canopy Vista", battlefield)

    vista = scenario.play_land("Canopy Vista")

    assert vista.zone is Zone.BATTLEFIELD
    assert vista.tapped is tapped


def test_a_nonbasic_land_with_basic_land_types_does_not_count():
    """CR 205.4c: Watery Grave and Steam Vents are Islands but not basic."""
    scenario = _board("Canopy Vista", ["Watery Grave", "Steam Vents"])

    assert scenario.play_land("Canopy Vista").tapped is True


def test_one_basic_and_one_nonbasic_is_not_two_basics():
    scenario = _board("Canopy Vista", ["Forest", "Watery Grave"])

    assert scenario.play_land("Canopy Vista").tapped is True


def test_an_opponents_basic_lands_do_not_count():
    scenario = _board("Canopy Vista", ["Forest"], bob_battlefield=["Plains", "Island"])

    assert scenario.play_land("Canopy Vista").tapped is True


def test_another_printing_of_the_template_off_pool():
    """Sunken Hollow, a different battle land, reads the same condition."""
    untapped = _board("Sunken Hollow", ["Island", "Swamp"])
    tapped = _board("Sunken Hollow", ["Island"])

    assert untapped.play_land("Sunken Hollow").tapped is False
    assert tapped.play_land("Sunken Hollow").tapped is True


@pytest.mark.parametrize(
    ("battlefield", "expected"),
    [(["Forest"], EntersState.TAPPED), (["Forest", "Plains"], EntersState.UNTAPPED)],
)
def test_the_prediction_agrees_with_the_play(battlefield, expected):
    scenario = _board("Canopy Vista", battlefield)
    vista = scenario.find("Canopy Vista", Zone.HAND, "alice")

    prediction = predict_enters(scenario.game, "alice", vista)

    assert prediction.state is expected
    assert prediction.notices == ()


def test_the_line_is_read_so_nothing_is_reported_unread():
    scenario = _board("Canopy Vista")

    assert unread_self_enters_tapped_lines(scenario.find("Canopy Vista", Zone.HAND, "alice")) == []


# --------------------------------------------------------------------------
# "unless you control a basic land" - the bare, uncounted form
# --------------------------------------------------------------------------
#
# Ba Sing Se's own "This land enters tapped unless you control a basic
# land." is the battle lands' "two or more basic lands" shape with the count
# dropped to one - a different sentence (no "or more", singular "a basic
# land"), read by its own `_YOU_CONTROL_A_BASIC_LAND_RE` rather than
# `_YOU_CONTROL_OTHER_LANDS_RE`'s counted form.


def test_ba_sing_se_enters_tapped_with_no_basic_land():
    scenario = _board("Ba Sing Se")

    assert scenario.play_land("Ba Sing Se").tapped


def test_ba_sing_se_enters_untapped_with_one_basic_land():
    scenario = _board("Ba Sing Se", ["Forest"])

    assert not scenario.play_land("Ba Sing Se").tapped


def test_a_nonbasic_land_with_a_basic_land_type_does_not_satisfy_ba_sing_se():
    """CR 205.4c: Watery Grave is an Island but not a basic land."""
    scenario = _board("Ba Sing Se", ["Watery Grave"])

    assert scenario.play_land("Ba Sing Se").tapped


def test_an_opponents_basic_land_does_not_count_for_ba_sing_se():
    scenario = _board("Ba Sing Se", bob_battlefield=["Forest"])

    assert scenario.play_land("Ba Sing Se").tapped


def test_agna_qel_a_reads_the_same_bare_shape_off_pool():
    """Agna Qel'a, a different printing of the identical sentence."""
    untapped = _board("Agna Qel'a", ["Island"])
    tapped = _board("Agna Qel'a")

    assert not untapped.play_land("Agna Qel'a").tapped
    assert tapped.play_land("Agna Qel'a").tapped
