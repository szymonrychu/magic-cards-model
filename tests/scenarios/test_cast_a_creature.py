"""Scenario: draw a creature and cast it off lands and an artifact.

The mechanic under test is the full path a permanent spell takes from the
library to the battlefield, and the corner cases around paying for it.
"""

import pytest

from magic_cards_model.machines import CastingStep, CostStep, Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Alice, with Questing Beast on top and exactly four mana on board.

    Two Forests make {G}{G}, Sol Ring makes {C}{C}. Questing Beast costs
    {2}{G}{G}, so this is the exact mana, with nothing spare.
    """
    return Scenario().player(
        "alice",
        library=["Questing Beast", "Forest"],
        battlefield=["Forest", "Forest", "Sol Ring"],
    )


def test_a_creature_goes_from_library_to_battlefield():
    scenario = board().build()

    # Start the turn at upkeep, the way the scenario asks for.
    scenario.start_at(Step.UPKEEP)
    assert scenario.step is Step.UPKEEP

    # Draw step: the engine draws for us (CR 703.4d), and Questing Beast was
    # on top, so it arrives in hand without the scenario asking.
    scenario.advance()
    assert scenario.step is Step.DRAW
    assert scenario.find("Questing Beast", Zone.HAND)

    # Creatures are sorcery-speed, so cast it in the precombat main phase.
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.can_cast_sorcery("alice")

    casting = scenario.cast("Questing Beast")
    payment = casting.begin_paying()
    assert str(payment.cost) == "{2}{G}{G}"

    # Pay from two Forests and Sol Ring: {G}{G} plus {C}{C}.
    sources = scenario.untapped_sources("Forest", "Forest", "Sol Ring")
    scenario.pay_with(payment, *sources)

    assert payment.step is CostStep.PAID
    assert payment.overflow is not None
    assert payment.overflow.is_empty  # exact mana, nothing floating
    assert all(source.tapped for source in sources)

    # The spell goes on the stack, then resolves onto the battlefield.
    scenario.put_on_stack(casting)
    assert casting.step is CastingStep.CAST
    assert [state.name for state in scenario.game.stack] == ["Questing Beast"]

    beast = scenario.resolve_top()

    assert beast.zone is Zone.BATTLEFIELD
    assert beast.name in scenario.battlefield_names()
    assert scenario.game.stack_is_empty
    assert beast.untapped  # it has haste, but nothing here taps it


def test_the_creature_is_no_longer_in_the_library_or_hand():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.draw()

    sources = scenario.untapped_sources("Forest", "Forest", "Sol Ring")
    scenario.cast_and_resolve("Questing Beast", *sources)

    alice = scenario.player("alice")
    assert [state.name for state in alice.hand] == []
    assert [state.name for state in alice.library] == ["Forest"]
    assert scenario.battlefield_names().count("Questing Beast") == 1


def test_one_land_short_leaves_the_spell_in_hand():
    """Corner case: an unpayable cost rewinds, it does not half-cast."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Questing Beast"],
            battlefield=["Forest", "Forest"],  # only {G}{G}, need {2} more
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.draw()

    casting = scenario.cast("Questing Beast")
    payment = casting.begin_paying()
    sources = scenario.untapped_sources("Forest", "Forest")

    with pytest.raises(ValueError, match="cannot pay"):
        scenario.pay_with(payment, *sources)

    casting.cancel()

    assert scenario.find("Questing Beast", Zone.HAND)
    assert all(source.untapped for source in sources), "cancelling untaps the sources"
    assert scenario.game.stack_is_empty


def test_overflow_mana_stays_floating_after_the_spell_is_paid_for():
    """Corner case: Sol Ring makes two, so a one-drop leaves mana behind."""
    scenario = (
        Scenario()
        .player("alice", hand=["Llanowar Elves"], battlefield=["Forest", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Llanowar Elves")
    payment = casting.begin_paying()
    forest, sol_ring = scenario.untapped_sources("Forest", "Sol Ring")
    scenario.pay_with(payment, forest, sol_ring)

    # {G} paid out of {G}{C}{C} leaves two colourless floating.
    assert payment.overflow is not None
    assert payment.overflow.floating == {Color.COLORLESS: 2}


def test_an_instant_resolves_to_the_graveyard_not_the_battlefield():
    """Corner case: only permanents stay on the table."""
    scenario = Scenario().player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_and_resolve("Lightning Bolt", mountain)

    assert bolt.zone is Zone.GRAVEYARD
    assert "Lightning Bolt" not in scenario.battlefield_names()
    assert [state.name for state in scenario.player("alice").graveyard] == ["Lightning Bolt"]


def test_a_tapped_land_cannot_pay():
    """Corner case: a source already tapped is not available for mana."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.draw()

    forest, *_ = scenario.untapped_sources("Forest", "Forest")
    forest.tap()

    with pytest.raises(AssertionError, match="no untapped Forest"):
        scenario.untapped_sources("Forest", "Forest")


def test_the_untap_step_frees_the_lands_for_next_turn():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.draw()
    sources = scenario.untapped_sources("Forest", "Forest", "Sol Ring")
    scenario.cast_and_resolve("Questing Beast", *sources)
    assert all(source.tapped for source in sources)

    # Round the turn back to alice and untap.
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    assert scenario.step is Step.UNTAP
    scenario.game.untap_step()

    assert all(source.untapped for source in sources)
