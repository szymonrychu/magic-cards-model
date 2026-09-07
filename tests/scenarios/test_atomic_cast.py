"""Scenario: `Game.cast` drives CR 601.2's whole announcement atomically.

The mechanic under test is not a card's own rules text but the engine's own
announcement machinery: `Casting`/`CostPayment` are locals inside `Game.cast`
that never outlive the call, so a caller either gets back a spell on the
stack with its cost paid, or an untouched game and an exception - never
anything observable in between. See `Game.cast`'s own docstring for the CR
601.2/601.6/733.1/400.7 argument for why that reversal is safe.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Alice, a Lightning Bolt in hand and exactly one red source."""
    return Scenario().player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"]).build()


def test_game_cast_matches_the_same_spell_driven_step_by_step():
    """`Game.cast` should reach the identical result the harness's own
    step-by-step `cast_onto_stack` reaches for the same spell, same sources,
    same target."""
    direct = board()
    direct.start_at(Step.PRECOMBAT_MAIN)
    bolt = direct.find("Lightning Bolt", Zone.HAND)
    (mountain,) = direct.untapped_sources("Mountain")

    cast_spell = direct.game.cast(bolt, "alice", targets=["alice"], mana_sources=[mountain])

    stepwise = board()
    stepwise.start_at(Step.PRECOMBAT_MAIN)
    (stepwise_mountain,) = stepwise.untapped_sources("Mountain")
    stepwise_spell = stepwise.cast_onto_stack(
        "Lightning Bolt", stepwise_mountain, targets=["alice"]
    )

    assert cast_spell.zone is Zone.STACK
    assert cast_spell.name == stepwise_spell.name == "Lightning Bolt"
    assert mountain.tapped and stepwise_mountain.tapped
    assert [state.name for state in direct.game.stack] == [
        state.name for state in stepwise.game.stack
    ]
    assert direct.player("alice").hand == []
    assert stepwise.player("alice").hand == []
    assert direct.player("alice").mana_pool.floating == {}
    assert stepwise.player("alice").mana_pool.floating == {}
    assert direct.game.open_payment_pools == {}
    direct.game.assert_quiescent()


def test_an_unpayable_cost_leaves_the_game_exactly_as_it_was():
    """Corner case: `Game.cast` raises on a shortfall and leaves no trace -
    the card is back in hand, the tapped-for-nothing sources are untapped
    again, and no mana is left floating (CR 733.1)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Questing Beast"],
            battlefield=["Forest", "Forest"],  # only {G}{G}; Questing Beast needs {2}{G}{G}
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beast = scenario.find("Questing Beast", Zone.HAND)
    sources = scenario.untapped_sources("Forest", "Forest")

    with pytest.raises(ValueError, match="no combination of the available mana sources can pay"):
        scenario.game.cast(beast, "alice", mana_sources=list(sources))

    assert beast.zone is Zone.HAND
    assert all(source.untapped for source in sources)
    assert scenario.player("alice").mana_pool.floating == {}
    assert scenario.game.open_payment_pools == {}
    assert scenario.game.stack_is_empty
    scenario.game.assert_quiescent()


def test_an_illegal_target_leaves_the_game_exactly_as_it_was():
    """Corner case: CR 115.5 refuses a spell targeting itself. The refusal
    happens before any mana is ever tapped, and `Game.cast` still leaves the
    card back where it started rather than half-announced."""
    scenario = board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND)
    (mountain,) = scenario.untapped_sources("Mountain")

    with pytest.raises(ValueError, match="illegal target for itself"):
        scenario.game.cast(bolt, "alice", targets=[bolt], mana_sources=[mountain])

    assert bolt.zone is Zone.HAND
    assert mountain.untapped
    assert scenario.player("alice").mana_pool.floating == {}
    assert scenario.game.open_payment_pools == {}
    assert scenario.game.stack_is_empty
    scenario.game.assert_quiescent()


def test_assert_quiescent_passes_on_an_ordinary_game():
    scenario = board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.assert_quiescent()


def test_assert_quiescent_raises_on_an_open_payment():
    """A `Casting` driven by hand and abandoned mid-payment - the exact shape
    `Game.cast` never lets a caller observe - is exactly what this should
    catch."""
    scenario = board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Lightning Bolt", targets=["alice"])
    casting.begin_paying()

    with pytest.raises(AssertionError, match="open CostPayment"):
        scenario.game.assert_quiescent()

    # Clean up the way a caller who did remember to rewind would.
    casting.cancel()
    scenario.game.assert_quiescent()


def test_assert_quiescent_raises_on_a_stuck_resolving_marker():
    scenario = board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["alice"])
    scenario.game.assert_quiescent()  # on the stack, unresolved, is fine on its own

    scenario.game.resolving = bolt  # simulate a game caught mid-resolve_top

    with pytest.raises(AssertionError, match="mid-resolution"):
        scenario.game.assert_quiescent()

    scenario.game.resolving = None
    scenario.game.assert_quiescent()
