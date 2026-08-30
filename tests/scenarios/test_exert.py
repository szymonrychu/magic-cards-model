"""Exert: choosing not to untap next turn (CR 701.43).

Exert is a *keyword action*, not a keyword ability - CR 701.43, not CR 702 - and
the difference matters, because there is nothing on a card to expand. What the
card prints is a cost: Arena of Glory's `{R}, {T}, Exert this land: Add {R}{R}.`

CR 701.43a: "To exert a permanent, you choose to have it not untap during your
next untap step."

CR 701.43b is the corner case: "A permanent can be exerted even if it's not
tapped or has already been exerted in a turn. If you exert a permanent more than
once before your next untap step, **each effect causing it not to untap expires
during the same untap step**." So exerting twice is exerting once, and one exert
never costs two untap steps - which is why `CardState.exerted` is a flag that
`untap` clears rather than a count that it decrements.

CR 701.43c: "An object that isn't on the battlefield can't be exerted."

CR 701.43d is the *other* half - "You may exert [this creature] as it attacks"
is an optional cost to attack (CR 508.1g), with a linked "when you do" trigger
(CR 607.2h). No printing in this pool has that shape; Arena of Glory pays exert
as part of an activation cost instead.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import (
    ComponentKind,
    cost_component_for_phrase,
    exert_cost,
)
from magic_cards_model.machines.keywords import exert
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Arena of Glory", "Mountain"])
        .player("bob")
    )


def test_an_exerted_permanent_does_not_untap_in_the_untap_step():
    """CR 701.43a, the whole ability."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    arena = scenario.find("Arena of Glory", Zone.BATTLEFIELD)

    arena.tap()
    exert(arena)
    assert arena.exerted

    scenario.player("alice").untap_all(scenario.game.permanents_controlled_by("alice"))

    assert arena.tapped


def test_the_effect_expires_after_one_untap_step():
    """CR 701.43b: the effect expires *during* that untap step, so one only."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    arena = scenario.find("Arena of Glory", Zone.BATTLEFIELD)

    arena.tap()
    exert(arena)
    permanents = scenario.game.permanents_controlled_by("alice")

    scenario.player("alice").untap_all(permanents)
    assert arena.tapped
    assert not arena.exerted

    scenario.player("alice").untap_all(permanents)
    assert arena.untapped


def test_exerting_twice_costs_only_one_untap_step():
    """CR 701.43b: "each effect causing it not to untap expires during the same
    untap step"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    arena = scenario.find("Arena of Glory", Zone.BATTLEFIELD)

    arena.tap()
    exert(arena)
    exert(arena)
    permanents = scenario.game.permanents_controlled_by("alice")

    scenario.player("alice").untap_all(permanents)
    assert arena.tapped
    scenario.player("alice").untap_all(permanents)

    assert arena.untapped


def test_an_untapped_permanent_can_be_exerted():
    """CR 701.43b: "even if it's not tapped"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    arena = scenario.find("Arena of Glory", Zone.BATTLEFIELD)

    exert(arena)

    assert arena.exerted
    assert arena.untapped


def test_a_card_off_the_battlefield_cannot_be_exerted():
    """CR 701.43c: "An object that isn't on the battlefield can't be exerted"."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Arena of Glory"])
        .player("bob")
        .build()
    )
    arena = scenario.find("Arena of Glory", Zone.HAND, "alice")

    with pytest.raises(ValueError, match="battlefield"):
        exert(arena)


def test_an_effect_that_untaps_it_is_not_the_untap_step():
    """CR 701.43a names one moment: "your next untap step", and nothing else.

    An effect or a `{Q}` cost that untaps the permanent does so regardless, and
    leaves the exert in place for the step it was aimed at.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    arena = scenario.find("Arena of Glory", Zone.BATTLEFIELD)

    arena.tap()
    exert(arena)
    arena.untap(exert_applies=False)

    assert arena.untapped
    assert arena.exerted


def test_leaving_the_battlefield_clears_it():
    """CR 400.7: the permanent that comes back is a new object."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    arena = scenario.find("Arena of Glory", Zone.BATTLEFIELD)

    arena.tap()
    exert(arena)
    scenario.game.destroy(arena)

    assert not arena.exerted


def test_the_printed_cost_phrase_is_read_into_something_payable():
    """CR 602.1a: the activation cost is everything before the colon.

    Arena of Glory prints `{R}, {T}, Exert this land: Add {R}{R}.`, so "Exert
    this land" is a cost piece and has to become payable like any other.
    """
    component = cost_component_for_phrase("Exert this land", payer="alice")
    assert component is not None
    assert component.kind is ComponentKind.EXERT
    assert component.required == 1


def test_paying_an_exert_cost_exerts_the_permanent_and_rewinds_cleanly():
    """CR 118.3 pays it, CR 733.1 puts it back."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    arena = scenario.find("Arena of Glory", Zone.BATTLEFIELD)

    component = exert_cost(arena, payer="alice", description="Exert this land")
    assert component.why_not(scenario.game) is None

    component.pay(scenario.game)
    assert arena.exerted

    component.unpay(scenario.game)
    assert not arena.exerted


def test_an_exert_cost_on_a_card_in_hand_cannot_be_paid():
    """CR 701.43c, reached through CR 118.3."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Arena of Glory"])
        .player("bob")
        .build()
    )
    arena = scenario.find("Arena of Glory", Zone.HAND, "alice")

    component = exert_cost(arena, payer="alice", description="Exert this land")

    refusal = component.why_not(scenario.game)
    assert refusal is not None
    assert "battlefield" in refusal


def test_arena_of_glory_can_activate_its_exert_ability():
    """CR 602.1a: the whole cost is paid on activation, exert included."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    arena = scenario.find("Arena of Glory", Zone.BATTLEFIELD)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)

    scenario.activate(arena, mountain, index=1)

    assert arena.exerted
    assert arena.tapped
