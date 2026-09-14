"""Predicting how a land would enter the battlefield, without it entering.

`predict_enters(game, player, card)` answers, for a land in `player`'s hand or
library, whether it would enter `untapped`, `tapped`, or `untapped_if_paid`
if it were played or put onto the battlefield right now. It answers by running
the engine's own entering event (`Game.enter_the_battlefield`, which applies
CR 614.12's replacement effects) on a decoded copy of the game, so the answer
and the real play can never disagree, and the real game is left untouched.

Rules, each read in full with `mise run rules:find` in the session that wrote
this file:

- **CR 614.1c** - "As [this permanent] enters . . ." is a replacement effect:
  the shockland's "As this land enters, you may pay 2 life".
- **CR 614.1d** - "[This permanent] enters . . ." is a replacement effect:
  "This land enters tapped", with or without an "unless" condition.
- **CR 614.12** - such an effect may come from the permanent itself, and
  "continuous effects that already exist and would apply" are taken into
  account, which is why a Yavimaya-made Forest counts for Shifting Woodland.
- **CR 614.12a** - the choice (pay life or not) "is made before the permanent
  enters the battlefield", so it is part of the prediction, not a later step.
- **CR 119.4** - life can be paid only if the life total is at least the
  payment, so a shockland at 1 life has no untapped option at all.
- **CR 712.12** - an MDFC played as a land enters with its land face up.
"""

import pytest

from magic_cards_model.machines import EntersState, Step, predict_enters
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(hand=(), battlefield=(), library=(), life=20):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=list(battlefield),
            library=list(library),
            life=life,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _predict(scenario, name, zone=Zone.HAND):
    return predict_enters(scenario.game, "alice", scenario.find(name, zone, "alice"))


# --------------------------------------------------------------------------
# No enters-tapped text at all
# --------------------------------------------------------------------------


def test_a_basic_land_enters_untapped():
    scenario = _board(hand=["Island"])

    prediction = _predict(scenario, "Island")

    assert prediction.state is EntersState.UNTAPPED
    assert prediction.optional_costs == ()
    assert prediction.notices == ()


# --------------------------------------------------------------------------
# CR 614.1d, unconditional
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Meticulous Archive", "Undercity Sewers", "Bojuka Bog"])
def test_an_unconditional_enters_tapped_land_enters_tapped(name):
    """Two surveil lands and a land with a different enters trigger."""
    scenario = _board(hand=[name])

    assert _predict(scenario, name).state is EntersState.TAPPED


# --------------------------------------------------------------------------
# CR 614.1c + 614.12a: the shockland's optional life payment
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Watery Grave", "Steam Vents"])
def test_a_shockland_enters_untapped_if_the_life_is_paid(name):
    scenario = _board(hand=[name])

    prediction = _predict(scenario, name)

    assert prediction.state is EntersState.UNTAPPED_IF_PAID
    assert prediction.optional_costs == ("pay 2 life",)


def test_a_shockland_at_one_life_can_only_enter_tapped():
    """CR 119.4: paying 2 life at 1 life is illegal, so nobody decides anything."""
    scenario = _board(hand=["Watery Grave"], life=1)

    assert _predict(scenario, "Watery Grave").state is EntersState.TAPPED


def test_an_mdfc_land_face_is_the_face_predicted():
    """CR 712.12: Sink into Stupor is played as Soporific Springs, which carries
    the "pay 3 life" line; the front face carries none."""
    scenario = _board(hand=["Sink into Stupor"])

    prediction = _predict(scenario, "Sink into Stupor")

    assert prediction.state is EntersState.UNTAPPED_IF_PAID
    assert prediction.optional_costs == ("pay 3 life",)


# --------------------------------------------------------------------------
# CR 614.1d with a board condition: "two or fewer other lands"
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("others", "expected"),
    [
        ([], EntersState.UNTAPPED),
        (["Island", "Mountain"], EntersState.UNTAPPED),
        (["Island", "Mountain", "Swamp"], EntersState.TAPPED),
    ],
)
def test_a_fastland_counts_the_other_lands(others, expected):
    scenario = _board(hand=["Spirebluff Canal"], battlefield=others)

    assert _predict(scenario, "Spirebluff Canal").state is expected


def test_a_second_fastland_printing_reads_the_same_condition():
    """Generality: a different printing of the same template."""
    scenario = _board(hand=["Darkslick Shores"], battlefield=["Island", "Swamp", "Swamp"])

    assert _predict(scenario, "Darkslick Shores").state is EntersState.TAPPED


def test_the_leading_if_polarity_is_predicted_too():
    """ "If you control two or more other lands, this land enters tapped." """
    scenario = _board(hand=["Hall of Storm Giants"], battlefield=["Island", "Island"])

    assert _predict(scenario, "Hall of Storm Giants").state is EntersState.TAPPED


# --------------------------------------------------------------------------
# CR 614.1d with a subtype condition: "unless you control a Mountain"
# --------------------------------------------------------------------------


def test_arena_of_glory_without_a_mountain_enters_tapped():
    scenario = _board(hand=["Arena of Glory"])

    assert _predict(scenario, "Arena of Glory").state is EntersState.TAPPED


def test_arena_of_glory_with_a_mountain_enters_untapped():
    scenario = _board(hand=["Arena of Glory"], battlefield=["Mountain"])

    assert _predict(scenario, "Arena of Glory").state is EntersState.UNTAPPED


def test_an_opponents_mountain_does_not_count():
    scenario = (
        Scenario()
        .player("alice", hand=["Arena of Glory"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _predict(scenario, "Arena of Glory").state is EntersState.TAPPED


def test_shifting_woodland_without_a_forest_enters_tapped():
    scenario = _board(hand=["Shifting Woodland"], battlefield=["Island"])

    assert _predict(scenario, "Shifting Woodland").state is EntersState.TAPPED


def test_a_type_changing_effect_supplies_the_forest():
    """CR 614.12: continuous effects that already exist count. Yavimaya makes
    each land a Forest (layer 4), and Yavimaya is itself a land alice controls."""
    scenario = _board(hand=["Shifting Woodland"], battlefield=["Yavimaya, Cradle of Growth"])

    assert _predict(scenario, "Shifting Woodland").state is EntersState.UNTAPPED


def test_a_type_changing_effect_an_opponent_controls_still_applies():
    """Yavimaya says "each land", so bob's Yavimaya makes alice's Island a Forest."""
    scenario = (
        Scenario()
        .player("alice", hand=["Shifting Woodland"], battlefield=["Island"])
        .player("bob", battlefield=["Yavimaya, Cradle of Growth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _predict(scenario, "Shifting Woodland").state is EntersState.UNTAPPED


# --------------------------------------------------------------------------
# A land in the library (the fetch target)
# --------------------------------------------------------------------------


def test_a_library_shockland_is_predicted_the_same_way():
    scenario = _board(hand=["Polluted Delta"], library=["Watery Grave"])

    prediction = _predict(scenario, "Watery Grave", Zone.LIBRARY)

    assert prediction.state is EntersState.UNTAPPED_IF_PAID


# --------------------------------------------------------------------------
# Failing closed on an enters-tapped line the engine does not read
# --------------------------------------------------------------------------


def test_an_unread_condition_is_reported_tapped_with_a_notice():
    """Canopy Vista's "two or more basic lands" is not one of the conditions
    `machines/replacement.py` reads, so the prediction refuses to guess and
    says so - even on a board where the condition would hold."""
    scenario = _board(hand=["Canopy Vista"], battlefield=["Forest", "Plains"])

    prediction = _predict(scenario, "Canopy Vista")

    assert prediction.state is EntersState.TAPPED
    assert len(prediction.notices) == 1
    assert "two or more basic lands" in prediction.notices[0]


def test_an_unpaired_if_you_dont_is_reported_tapped_with_a_notice():
    """Port Town's optional cost is a reveal, not life, so its "If you don't"
    has nothing the engine pairs it with."""
    scenario = _board(hand=["Port Town", "Island"])

    prediction = _predict(scenario, "Port Town")

    assert prediction.state is EntersState.TAPPED
    assert len(prediction.notices) == 1
    assert "If you don't" in prediction.notices[0]


# --------------------------------------------------------------------------
# Side-effect free, and refusing what is not a question about a land
# --------------------------------------------------------------------------


def test_predicting_mutates_nothing():
    scenario = _board(hand=["Watery Grave", "Spirebluff Canal"], battlefield=["Island"])
    before = scenario.game.model_dump_json()

    _predict(scenario, "Watery Grave")
    _predict(scenario, "Spirebluff Canal")

    assert scenario.game.model_dump_json() == before
    assert scenario.find("Watery Grave", Zone.HAND, "alice").zone is Zone.HAND


def test_a_nonland_is_refused():
    scenario = _board(hand=["Preordain"])

    with pytest.raises(ValueError, match="not a land"):
        _predict(scenario, "Preordain")


def test_a_land_outside_hand_and_library_is_refused():
    scenario = _board(battlefield=["Island"])
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError, match="hand or library"):
        predict_enters(scenario.game, "alice", island)
