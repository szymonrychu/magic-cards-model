"""Scenario: priority.

The mechanic is CR 117 - who may act, when the non-active player gets a window,
and what a round of passes causes.
"""

import pytest

from magic_cards_model.machines import PriorityOutcome, Step
from magic_cards_model.models import Zone

from .harness import Scenario


def board() -> Scenario:
    """Alice is active with a creature to cast; Bob holds an instant."""
    return (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
    )


def test_the_active_player_gets_priority_first():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.priority_holder == "alice"


def test_the_other_player_may_cast_an_instant_in_their_window():
    """The whole point of priority: bob acts on alice's turn."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.pass_priority("alice")
    assert scenario.priority_holder == "bob"

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bears = None
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])

    assert bolt.zone is Zone.STACK
    assert bears is None
    assert scenario.priority_holder == "bob", "the caster keeps priority"


def test_casting_resets_the_round_of_passes():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])

    # Bob's own pass is now the first of a fresh round, not the second of the old one.
    assert scenario.pass_priority("bob") is PriorityOutcome.PASSED
    assert scenario.priority_holder == "alice"


def test_everyone_passing_on_a_full_stack_resolves_the_top():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])

    scenario.pass_priority("bob")
    outcome = scenario.pass_priority("alice")

    assert outcome is PriorityOutcome.RESOLVE_TOP
    assert scenario.game.stack_is_empty


def test_everyone_passing_on_an_empty_stack_ends_the_step():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.pass_priority("alice")
    outcome = scenario.pass_priority("bob")

    assert outcome is PriorityOutcome.END_STEP


def test_a_player_without_priority_cannot_pass_it():
    """Corner case: acting out of turn is an error, not a no-op."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError, match="bob does not have priority"):
        scenario.pass_priority("bob")


def test_priority_returns_to_the_active_player_after_something_resolves():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    scenario.pass_priority("alice")

    assert scenario.priority_holder == "alice"


def test_an_unknown_player_is_rejected():
    scenario = board().build()

    with pytest.raises(KeyError):
        scenario.pass_priority("carol")


def test_everyone_passing_rolls_the_game_forward_on_its_own():
    """CR 117.4 and 405.5: when all players pass with the stack empty, the
    step or phase ends *and the next begins* - automatically. Nobody has to
    move the game on; passing is "I am done for now"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.pass_priority("alice") is PriorityOutcome.PASSED
    assert scenario.pass_priority("bob") is PriorityOutcome.END_STEP

    assert scenario.step is Step.BEGINNING_OF_COMBAT
    assert scenario.priority_holder == "alice", (
        "the new step's first priority round starts with the active player"
    )


def test_the_non_active_player_gets_priority_only_in_a_window():
    """The non-active player never holds priority unprompted: only once the
    active player passes (a response window, or the step ending)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.priority_holder == "alice"
    with pytest.raises(ValueError, match="bob does not have priority"):
        scenario.pass_priority("bob")

    # Alice casts and keeps priority (CR 117.3c): still no window for bob.
    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_onto_stack("Grizzly Bears", *forests)
    assert scenario.priority_holder == "alice"

    # Alice passes: now the window is bob's, with the Bears on the stack.
    scenario.pass_priority("alice")
    assert scenario.priority_holder == "bob"
    assert scenario.stack_names() == ["Grizzly Bears"]
