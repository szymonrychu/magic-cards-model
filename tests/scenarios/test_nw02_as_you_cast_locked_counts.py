"""Scenario: a count fixed "as you cast this spell" - X is determined while the
spell is being cast, before the division of damage is announced, and is not
recomputed when the spell resolves.

Jaws of Stone: "Jaws of Stone deals X damage divided as you choose among any
number of targets, where X is the number of Mountains you control as you cast
this spell." Monstrous Onslaught: "... among any number of target creatures,
where X is the greatest power among creatures you control as you cast this
spell." CR 601.2d needs the total to announce the division, so the count is
recorded on the cast (`CastRecord.x_value`) and the announced division must add
up to it. The division itself is what resolution pays out; a caster who
announces none gets the whole locked X on a single target, and a response that
changes the board afterwards (Boomerang on a Mountain or on the biggest
creature) does not move it.

Every CR number here was verified with `mise run rules:find` in the session
that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone

from .harness import Scenario


def _jaws_board(*, bob_bf=("Colossal Dreadmaw",), bob_hand=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=["Jaws of Stone"],
            battlefield=["Mountain"] * 4 + ["Forest"] * 2,
        )
        .player("bob", battlefield=[*bob_bf, "Island", "Island"], hand=list(bob_hand))
        .build()
    )


def _cast_jaws(scenario, targets, division=None):
    sources = scenario.untapped_sources(
        "Mountain", "Mountain", "Mountain", "Mountain", "Forest", "Forest"
    )
    return scenario.cast_onto_stack(
        "Jaws of Stone", *sources, username="alice", targets=targets, division=division
    )


def test_jaws_of_stone_divides_the_mountain_count_among_its_targets():
    scenario = _jaws_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    _cast_jaws(scenario, [dreadmaw, "bob"], division=[3, 1])
    scenario.resolve_top()

    assert dreadmaw.damage == 3
    assert scenario.player("bob").life == 19


def test_the_mountains_tapped_to_cast_it_still_count():
    """Four Mountains are tapped for mana during casting; being tapped does not
    stop them being Mountains you control."""
    scenario = _jaws_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    _cast_jaws(scenario, [dreadmaw], division=[4])
    scenario.resolve_top()

    assert dreadmaw.damage == 4


@pytest.mark.parametrize("division", [[2, 1], [3, 2]])
def test_the_announced_division_must_add_up_to_the_locked_count(division):
    scenario = _jaws_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    with pytest.raises(ValueError, match="must use all 4"):
        scenario.cast("Jaws of Stone", targets=[dreadmaw, "bob"], division=division)


def test_an_opponents_mountains_and_other_lands_do_not_count():
    scenario = _jaws_board(bob_bf=("Colossal Dreadmaw", "Mountain", "Mountain"))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    _cast_jaws(scenario, [dreadmaw], division=[4])
    scenario.resolve_top()

    assert dreadmaw.damage == 4


def test_the_count_is_locked_when_a_mountain_leaves_in_response():
    """No division announced, so the whole X goes on the lone target: it is the
    X counted as the spell was cast (4), not the 3 Mountains left at resolution."""
    scenario = _jaws_board(bob_hand=["Boomerang"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    jaws = _cast_jaws(scenario, [dreadmaw])

    scenario.pass_priority("alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    blue = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Boomerang", *blue, username="bob", targets=[mountain])
    scenario.resolve_top()  # Boomerang
    assert mountain.zone is Zone.HAND
    scenario.resolve_top()  # Jaws of Stone

    assert jaws.zone is Zone.GRAVEYARD
    assert dreadmaw.damage == 4


def test_jaws_of_stone_with_no_targets_does_nothing():
    scenario = _jaws_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    life = scenario.player("bob").life

    _cast_jaws(scenario, [])
    scenario.resolve_top()

    assert scenario.player("bob").life == life


# --------------------------------------------------------------------------
# Monstrous Onslaught: "the greatest power among creatures you control"
# --------------------------------------------------------------------------


def _onslaught_board(*, bob_bf, bob_hand=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=["Monstrous Onslaught"],
            battlefield=["Forest"] * 5 + ["Colossal Dreadmaw", "Memnite"],
        )
        .player("bob", battlefield=[*bob_bf, "Island", "Island"], hand=list(bob_hand))
        .build()
    )


def _cast_onslaught(scenario, targets, division=None):
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest")
    return scenario.cast_onto_stack(
        "Monstrous Onslaught", *sources, username="alice", targets=targets, division=division
    )


def test_monstrous_onslaught_divides_the_greatest_power_among_target_creatures():
    scenario = _onslaught_board(bob_bf=("Colossal Dreadmaw", "Colossal Dreadmaw"))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Colossal Dreadmaw", "Colossal Dreadmaw", username="bob")

    _cast_onslaught(scenario, [first, second], division=[4, 2])
    scenario.resolve_top()

    assert (first.damage, second.damage) == (4, 2)


def test_monstrous_onslaught_division_must_add_up_to_the_greatest_power():
    scenario = _onslaught_board(bob_bf=("Colossal Dreadmaw", "Colossal Dreadmaw"))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Colossal Dreadmaw", "Colossal Dreadmaw", username="bob")

    with pytest.raises(ValueError, match="must use all 6"):
        scenario.cast("Monstrous Onslaught", targets=[first, second], division=[3, 2])


def test_monstrous_onslaught_is_locked_when_the_biggest_creature_leaves():
    """Alice's Dreadmaw (6 power) is bounced in response, leaving a Memnite
    (power 1) - the damage is still the 6 counted as the spell was cast."""
    scenario = _onslaught_board(bob_bf=("Colossal Dreadmaw",), bob_hand=["Boomerang"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature("Colossal Dreadmaw", "bob")
    mine = scenario.creature("Colossal Dreadmaw", "alice")
    _cast_onslaught(scenario, [target])

    scenario.pass_priority("alice")
    blue = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Boomerang", *blue, username="bob", targets=[mine])
    scenario.resolve_top()
    assert mine.zone is Zone.HAND
    scenario.resolve_top()

    assert target.zone is Zone.GRAVEYARD  # six damage on a 6/6


def test_monstrous_onslaught_ignores_an_opponents_bigger_creature():
    scenario = _onslaught_board(bob_bf=("Blightsteel Colossus",))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    colossus = scenario.creature("Blightsteel Colossus", "bob")

    _cast_onslaught(scenario, [colossus], division=[6])
    scenario.resolve_top()

    assert colossus.damage == 6


# --------------------------------------------------------------------------
# Off-set proof: Undercity Upheaval - the same locked count on a divided
# "distribute counters" instruction.
# --------------------------------------------------------------------------


def _upheaval_board(graveyard):
    return (
        Scenario()
        .player(
            "alice",
            hand=["Undercity Upheaval"],
            battlefield=["Forest"] * 3 + ["Grizzly Bears", "Memnite"],
            graveyard=list(graveyard),
        )
        .player("bob")
        .build()
    )


def _cast_upheaval(scenario, targets, division=None):
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    return scenario.cast_onto_stack(
        "Undercity Upheaval", *sources, username="alice", targets=targets, division=division
    )


def test_undercity_upheaval_distributes_one_counter_per_creature_card_in_the_graveyard():
    scenario = _upheaval_board(["Grizzly Bears", "Grizzly Bears", "Memnite", "Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")

    _cast_upheaval(scenario, [bears, memnite], division=[2, 1])
    scenario.resolve_top()

    assert (bears.power, bears.toughness) == (4, 4)
    assert (memnite.power, memnite.toughness) == (2, 2)
    assert has_keyword(bears, "vigilance", scenario.game)
    assert has_keyword(memnite, "vigilance", scenario.game)


def test_undercity_upheaval_division_must_match_the_creature_cards_in_the_graveyard():
    scenario = _upheaval_board(["Grizzly Bears", "Memnite", "Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")

    with pytest.raises(ValueError, match="must use all 2"):
        scenario.cast("Undercity Upheaval", targets=[bears, memnite], division=[2, 1])
