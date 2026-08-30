"""Scenario: three or more players (CR 800).

The mechanic is everything that stops being trivial once "the opponent" is not
a single person: turn order round the table, a round of priority passes with
three seats in it, and what happens to the game when one player leaves but the
game carries on (CR 800.4).

The variant modelled is Free-for-All (CR 806) with its defaults: no limited
range of influence (CR 806.2a), which is why nothing here tests CR 801.
"""

import pytest

from magic_cards_model.machines import PriorityOutcome, Step
from magic_cards_model.models import Zone

from .harness import Scenario


def three_players() -> Scenario:
    """Alice, bob, and carol, each with a Bolt and a Mountain to cast it with."""
    return (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("carol", hand=["Lightning Bolt"], battlefield=["Mountain"])
    )


# -- turn order (CR 800.5, 806.3) -------------------------------------------


def test_the_turn_passes_round_the_whole_table():
    """Turn order is seating order, so it takes three turns to come back."""
    scenario = three_players().build()
    seen = [scenario.turn.active_player]

    for _ in range(3):
        scenario.turn.advance_to(Step.CLEANUP)
        scenario.advance()
        seen.append(scenario.turn.active_player)

    assert seen == ["alice", "bob", "carol", "alice"]


def test_the_turn_number_counts_rounds_of_the_table():
    """One turn each is still turn one; the number goes up when it wraps."""
    scenario = three_players().build()

    for _ in range(2):
        scenario.turn.advance_to(Step.CLEANUP)
        scenario.advance()
    assert scenario.turn.turn_number == 1, "carol's first turn is still turn one"

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()

    assert scenario.turn.active_player == "alice"
    assert scenario.turn.turn_number == 2


# -- priority with three seats (CR 117.4) -----------------------------------


def test_a_spell_needs_all_three_players_to_pass_before_it_resolves():
    """CR 117.4: the top of the stack resolves when every player passes in
    succession - which is three passes here, not two.
    """
    scenario = three_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["carol"])

    assert scenario.pass_priority("alice") is PriorityOutcome.PASSED
    assert scenario.pass_priority("bob") is PriorityOutcome.PASSED
    assert scenario.game.stack == [bolt], "still waiting on carol"

    assert scenario.pass_priority("carol") is PriorityOutcome.RESOLVE_TOP

    assert scenario.player("carol").life == 17
    assert bolt.zone is Zone.GRAVEYARD


def test_priority_passes_in_turn_order_from_the_active_player():
    """CR 117.3d: it goes to the next player in turn order, not back and forth."""
    scenario = three_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.priority_holder == "alice"
    scenario.pass_priority("alice")
    assert scenario.priority_holder == "bob"
    scenario.pass_priority("bob")
    assert scenario.priority_holder == "carol"


def test_an_empty_stack_and_three_passes_ends_the_step():
    scenario = three_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.pass_priority("alice")
    scenario.pass_priority("bob")

    assert scenario.pass_priority("carol") is PriorityOutcome.END_STEP


# -- a player leaving (CR 800.4) --------------------------------------------


def test_the_game_carries_on_when_one_of_three_players_leaves():
    """CR 800.4: unlike a two-player game, a multiplayer game continues."""
    scenario = three_players().build()
    scenario.game.concede("carol")

    assert not scenario.game.is_over
    assert [player.username for player in scenario.game.players_in_game] == ["alice", "bob"]


def test_the_last_player_standing_wins():
    """CR 104.2a: "A player still in the game wins the game if that player's
    opponents have all left the game."
    """
    scenario = three_players().build()
    scenario.game.concede("carol")
    scenario.game.concede("bob")

    assert scenario.game.winner == "alice"


def test_a_departed_player_is_skipped_by_priority():
    """CR 800.4: a round of passes waits only for the players still in the game.

    With carol gone, two passes are a full round and the Bolt resolves - the
    engine must not sit waiting for a pass that can never come.
    """
    scenario = three_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.concede("carol")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.pass_priority("alice") is PriorityOutcome.PASSED
    assert scenario.priority_holder == "bob", "carol is skipped over"

    assert scenario.pass_priority("bob") is PriorityOutcome.RESOLVE_TOP
    assert scenario.player("bob").life == 17


def test_a_departed_player_cannot_be_given_priority():
    scenario = three_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.concede("bob")

    with pytest.raises(ValueError, match="bob has left the game"):
        scenario.pass_priority("bob")


def test_a_departed_player_is_skipped_by_turn_order():
    """CR 800.4: the turn passes to the next player still in the game.

    Bob leaves during alice's turn, so the turn goes straight to carol.
    """
    scenario = three_players().build()
    scenario.game.concede("bob")

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()

    assert scenario.turn.active_player == "carol"


def test_a_players_objects_leave_the_game_with_them():
    """CR 800.4a: "all objects owned by that player leave the game".

    Carol's Mountain is not left behind on the battlefield for the others to
    look at - and nothing on the battlefield is hers any more.
    """
    scenario = three_players().build()
    assert scenario.battlefield_names().count("Mountain") == 3

    scenario.game.concede("carol")

    assert scenario.battlefield_names().count("Mountain") == 2
    assert scenario.game.permanents_controlled_by("carol") == []


def test_a_player_removed_by_a_state_based_action_leaves_the_same_way():
    """The other route out: losing (CR 704.5a) is leaving (CR 104.5).

    Carol dies to a Bolt at three life, and her board goes with her rather than
    lingering.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob")
        .player("carol", life=3, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["carol"])

    assert not scenario.game.is_in_game("carol")
    assert "Grizzly Bears" not in scenario.battlefield_names()
    assert not scenario.game.is_over, "bob is still playing"


def test_a_spell_aimed_at_a_departed_player_fizzles():
    """CR 608.2b meets CR 800.4: the target is not a player in the game.

    Aiming at a player who then leaves is the cleanest way to make every target
    of a spell illegal, and the Helix's untargeted life gain is what proves it
    did not resolve.
    """
    scenario = (
        Scenario()
        .player("alice", life=15, hand=["Lightning Helix"], battlefield=["Mountain", "Plains"])
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Plains", username="alice")
    helix = scenario.cast_onto_stack(
        "Lightning Helix", *sources, username="alice", targets=["carol"]
    )

    scenario.game.concede("carol")
    assert scenario.game.spell_fizzles(helix)

    scenario.pass_until_resolved()

    assert helix.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 15


# -- what multiplayer still does not have -----------------------------------


def test_attacking_needs_a_defender_named_once_there_are_two_opponents():
    """CR 802/803: which opponents may be attacked is a variant option, and the
    harness will not guess. The scenario has to say who is being attacked.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", username="alice")

    with pytest.raises(AssertionError, match="say who is being attacked"):
        scenario.attack_with(bears)

    scenario.attack_with(bears, defending="carol")
    assert scenario.attackers() == [bears]
