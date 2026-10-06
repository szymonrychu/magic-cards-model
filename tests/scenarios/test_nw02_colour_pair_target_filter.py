"""A target phrase's colour pair joined by "and/or" (CR 105.2: an object can be
one or more of the five colours; a creature of either colour - or both -
qualifies).

Ignite Disorder ({1}{R}): "Ignite Disorder deals 3 damage divided as you choose
among one, two, or three target white and/or blue creatures." Each target must
be a white creature, a blue creature, or both (a white-blue Azorius creature
counts once, not twice), and CR 601.2d's division gives each target at least 1.

The same adjective run in an ordinary "destroy" phrase ("Destroy target white
and/or blue creature.") is read by the phrase reader, not a damage reader, so
it is also checked on the targeting profile itself - no printing in the
Modern, Pioneer or Standard pool carries that sentence, so the profile of the
literal phrase is the proof for it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ignite Disorder"], battlefield=["Mountain", "Mountain"])
        .player(
            "bob",
            battlefield=["Serra Angel", "Wind Drake", "Grizzly Bears", "Deepway Navigator"],
        )
    )


def _cast(scenario, targets, division):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Ignite Disorder",
        *scenario.untapped_sources("Mountain", "Mountain"),
        targets=targets,
        division=division,
    )


def test_a_white_and_a_blue_creature_split_three_damage():
    scenario = _board().build()
    angel = scenario.creature("Serra Angel", "bob")
    drake = scenario.creature("Wind Drake", "bob")
    _cast(scenario, [angel, drake], [1, 2])
    assert angel.damage == 1
    assert drake.zone is Zone.GRAVEYARD  # 2 damage on a 2/2


def test_one_target_takes_all_three():
    scenario = _board().build()
    drake = scenario.creature("Wind Drake", "bob")
    _cast(scenario, [drake], [3])
    assert drake.zone is Zone.GRAVEYARD


def test_a_green_creature_is_not_a_legal_target():
    scenario = _board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    with pytest.raises(ValueError):
        _cast(scenario, [bears], [3])


def test_a_creature_of_both_colours_is_one_legal_target():
    scenario = _board().build()
    navigator = scenario.creature("Deepway Navigator", "bob")  # white and blue
    _cast(scenario, [navigator], [3])
    assert navigator.zone is Zone.GRAVEYARD


def test_the_phrase_reader_reads_and_or_between_colours():
    for text in (
        "Destroy target white and/or blue creature.",
        "Destroy target white or blue creature.",
    ):
        profile = profile_for_text(text)
        assert profile.understood
        (requirement,) = profile.requirements
        assert {color.name for color in requirement.required_colors} == {"WHITE", "BLUE"}
