"""Scenario: "deals N damage to target player or planeswalker and N damage to
target creature that player or that planeswalker's controller controls" -
plus Searing Blaze's landfall-conditioned amount.

Two instances of the word "target" (CR 115.3), the second restricted by the
first: the creature must be controlled by the chosen player, or by the chosen
planeswalker's controller. That is checked as the targets are announced (CR
601.2c) and again on resolution (CR 608.2b: a creature that changed control
since is an illegal target and is not dealt damage, while the player still
is).

Landfall is an ability word (CR 207.2c); the condition is "If you had a land
enter the battlefield under your control this turn" - any land, however it
entered (a land played is CR 305.1's special action; one put onto the
battlefield by an effect entered all the same) - and "instead" replaces the
amounts (CR 614.1a).

Cards: Searing Blaze; proof printing Soul of Shandalar's activated ability
(the same template with "up to one target creature").

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: 115.3, 601.2c, 608.2b, 207.2c, 305.1, 614.1a.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _blaze_board(**extra) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Searing Blaze", "Mountain", *extra.get("alice_hand", [])],
            battlefield=["Mountain", "Mountain", *extra.get("alice_battlefield", [])],
        )
        .player(
            "bob",
            library=["Forest"],
            hand=extra.get("bob_hand", []),
            battlefield=["Serra Angel", *extra.get("bob_battlefield", [])],
        )
    )


def _blaze(scenario, targets) -> None:
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Searing Blaze", *mountains, username="alice", targets=targets)


# -- the base amounts --------------------------------------------------------


def test_without_landfall_it_deals_one_to_each():
    scenario = _blaze_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _blaze(scenario, ["bob", angel])

    assert scenario.player("bob").life == 19
    assert angel.damage == 1


def test_with_a_land_played_this_turn_it_deals_three_to_each():
    scenario = _blaze_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.play_land("Mountain", username="alice")

    _blaze(scenario, ["bob", angel])

    assert scenario.player("bob").life == 17
    assert angel.damage == 3


def test_a_land_put_onto_the_battlefield_by_an_effect_counts_too():
    scenario = _blaze_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.put_onto_battlefield("Mountain", "alice")

    _blaze(scenario, ["bob", angel])

    assert angel.damage == 3


def test_a_land_that_entered_and_left_still_counts():
    """A fetch land sacrificed on the way still "entered the battlefield
    under your control this turn"."""
    scenario = _blaze_board(alice_hand=["Wooded Foothills"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    foothills = scenario.play_land("Wooded Foothills", username="alice")
    scenario.game.sacrifice(foothills)  # its own cost, CR 701.21a
    assert foothills.zone is not Zone.BATTLEFIELD

    _blaze(scenario, ["bob", angel])

    assert angel.damage == 3


def test_an_opponents_land_entering_does_not_count():
    scenario = _blaze_board(bob_hand=["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.put_onto_battlefield("Forest", "bob")

    _blaze(scenario, ["bob", angel])

    assert angel.damage == 1


# -- the dependent target ----------------------------------------------------


def test_the_creature_must_be_controlled_by_the_targeted_player():
    scenario = _blaze_board(alice_battlefield=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    with pytest.raises(ValueError, match="controls"):
        scenario.cast("Searing Blaze", "alice", targets=["bob", bears])


def test_a_planeswalker_target_lets_its_controllers_creature_be_chosen():
    scenario = _blaze_board(bob_battlefield=["Archangel Elspeth"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    elspeth = scenario.find("Archangel Elspeth", Zone.BATTLEFIELD, "bob")
    loyalty = elspeth.loyalty

    _blaze(scenario, [elspeth, angel])

    assert elspeth.loyalty == loyalty - 1
    assert angel.damage == 1
    assert scenario.player("bob").life == 20


def test_a_planeswalker_target_refuses_another_players_creature():
    scenario = _blaze_board(
        bob_battlefield=["Archangel Elspeth"], alice_battlefield=["Grizzly Bears"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elspeth = scenario.find("Archangel Elspeth", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "alice")

    with pytest.raises(ValueError, match="controls"):
        scenario.cast("Searing Blaze", "alice", targets=[elspeth, bears])


def test_targeting_yourself_and_your_own_creature_is_legal():
    scenario = _blaze_board(alice_battlefield=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _blaze(scenario, ["alice", bears])

    assert scenario.player("alice").life == 19
    assert bears.damage == 1


def test_a_creature_that_changed_control_is_not_dealt_damage():
    """CR 608.2b: once bob's Angel is alice's, it is no longer "a creature
    that player controls" - illegal - and only bob is hit."""
    scenario = _blaze_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack("Searing Blaze", *mountains, username="alice", targets=["bob", angel])
    angel.controller = "alice"  # staging a control change in response
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 19
    assert angel.damage == 0


def test_a_creature_that_left_still_lets_the_player_be_hit():
    scenario = _blaze_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack("Searing Blaze", *mountains, username="alice", targets=["bob", angel])
    scenario.game.destroy(angel)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 19


# -- Soul of Shandalar (proof): "up to one target creature" -------------------


def _soul_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Soul of Shandalar", "Grizzly Bears", *["Mountain"] * 5],
        )
        .player("bob", library=["Forest"], battlefield=["Serra Angel"])
    )


def test_soul_of_shandalar_hits_the_player_and_their_creature():
    scenario = _soul_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    soul = scenario.creature("Soul of Shandalar", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    mountains = scenario.untapped_sources(*["Mountain"] * 5, username="alice")

    scenario.activate(soul, *mountains, username="alice", targets=["bob", angel])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17
    assert angel.damage == 3


def test_soul_of_shandalar_may_choose_no_creature():
    scenario = _soul_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    soul = scenario.creature("Soul of Shandalar", "alice")
    mountains = scenario.untapped_sources(*["Mountain"] * 5, username="alice")

    scenario.activate(soul, *mountains, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17


def test_soul_of_shandalar_refuses_a_creature_of_another_player():
    scenario = _soul_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    soul = scenario.creature("Soul of Shandalar", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    mountains = scenario.untapped_sources(*["Mountain"] * 5, username="alice")

    with pytest.raises(ValueError, match="controls"):
        scenario.activate(soul, *mountains, username="alice", targets=["bob", bears])
