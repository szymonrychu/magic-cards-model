"""A type added "in addition to its other types" together with a keyword
grant, until end of turn - Stone by Sunlight's second mode: "Until end of
turn, target creature becomes an artifact in addition to its other types and
gains indestructible." - and its first mode, "Destroy target creature with
power 4 or greater."

Layer 4 adds the card type and keeps every other one (CR 613.1d, CR 205.1b);
layer 6 adds indestructible (CR 613.1f). Indestructible permanents are not
destroyed by "destroy" effects or lethal damage (CR 702.12b). Both end at
cleanup (CR 514.2).

Argent Mutation (the off-set proof, not in any deck list): "Target permanent
becomes an artifact in addition to its other types until end of turn. Draw a
card." - the same reader with no keyword grant, a permanent subject, and a
second instruction after it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone

from .harness import Scenario

STONE = "Stone by Sunlight"


def _cast_stone(scenario, mode, target):
    casting = scenario.cast(STONE, username="alice")
    casting.choose_modes([mode])
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Plains", username="alice"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()


def _board(scenario):
    return scenario.game.computed_board()


def test_mode_two_makes_the_creature_an_indestructible_artifact_creature():
    scenario = (
        Scenario()
        .player("alice", hand=[STONE], battlefield=["Plains", "Plains", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast_stone(scenario, 2, bears)

    chars = _board(scenario).of(bears)
    assert Type.ARTIFACT in chars.types
    assert Type.CREATURE in chars.types  # in addition to, not instead of
    assert "Bear" in chars.subtypes
    assert "Indestructible" in chars.abilities


def test_mode_two_survives_a_destroy_effect_and_lethal_damage():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[STONE, "Lightning Bolt"],
            battlefield=["Plains", "Plains", "Mountain", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_stone(scenario, 2, bears)

    scenario.game.destroy(bears)
    assert bears.zone is Zone.BATTLEFIELD

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )
    assert bears.damage == 3
    scenario.state_based_actions()
    assert bears.zone is Zone.BATTLEFIELD  # CR 702.12b: lethal damage does not destroy it


def test_mode_two_ends_at_cleanup():
    scenario = (
        Scenario()
        .player("alice", hand=[STONE], battlefield=["Plains", "Plains", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_stone(scenario, 2, bears)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)

    chars = _board(scenario).of(bears)
    assert Type.ARTIFACT not in chars.types
    assert "Indestructible" not in chars.abilities
    scenario.game.destroy(bears)
    assert bears.zone is Zone.GRAVEYARD


def test_mode_two_can_target_an_opponents_creature():
    """The target is "target creature" - any controller."""
    scenario = (
        Scenario()
        .player("alice", hand=[STONE], battlefield=["Plains", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_stone(scenario, 2, bears)

    assert Type.ARTIFACT in _board(scenario).of(bears).types


def test_mode_one_destroys_a_creature_with_power_four_or_greater():
    scenario = (
        Scenario()
        .player("alice", hand=[STONE], battlefield=["Plains", "Plains"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _cast_stone(scenario, 1, angel)

    assert angel.zone is Zone.GRAVEYARD


def test_mode_one_cannot_target_a_creature_with_power_three():
    scenario = (
        Scenario()
        .player("alice", hand=[STONE], battlefield=["Plains", "Plains"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    casting = scenario.cast(STONE, username="alice")
    casting.choose_modes([1])
    with pytest.raises(ValueError):
        casting.choose_targets([giant])


# -- Argent Mutation (off-set proof) ----------------------------------------


def test_argent_mutation_makes_a_land_an_artifact_and_draws():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Argent Mutation"],
            battlefield=["Island", "Island", "Island"],
            library=["Island"],
        )
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_and_resolve(
        "Argent Mutation",
        *scenario.untapped_sources("Island", "Island", "Island", username="alice"),
        targets=[forest],
    )

    chars = _board(scenario).of(forest)
    assert Type.ARTIFACT in chars.types
    assert Type.LAND in chars.types
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)
    assert Type.ARTIFACT not in _board(scenario).of(forest).types
