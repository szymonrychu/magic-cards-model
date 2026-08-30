"""Flash, and the casting timing it is an exception to (CR 702.8, CR 117.1a).

CR 117.1a is the rule flash bends: "A player may cast an instant spell any time
they have priority. A player may cast a noninstant spell during their main phase
any time they have priority and the stack is empty." The per-type rules restate
it - CR 304.1 for instants, CR 307.1 for sorceries, CR 302.1 for creatures - and
CR 505.6a adds that the main phase is the only phase those go in.

CR 702.8a: "Flash is a static ability that functions in any zone from which you
could play the card it's on. 'Flash' means "You may play this card any time you
could cast an instant.""

So the interesting cases are all timing: a creature in the wrong step, a
creature with a spell on the stack, and the same two with flash - where they are
suddenly fine.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import has_flash, why_cannot_cast_now
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Containment Priest", "Watchwolf", "Lightning Bolt"],
            battlefield=["Plains", "Plains", "Plains", "Mountain"],
        )
        .player("bob", battlefield=["Mountain"])
    )


def test_the_printing_is_where_flash_is_read_from():
    """CR 702.8a, read off Scryfall's `keywords` like every other keyword here."""
    assert has_flash(card("Containment Priest"))
    assert not has_flash(card("Watchwolf"))


def test_a_creature_cannot_be_cast_in_the_declare_attackers_step():
    """CR 117.1a: a noninstant spell needs a main phase."""
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    with pytest.raises(ValueError, match="only cast it during their own main phase"):
        scenario.cast("Watchwolf")


def test_a_creature_with_flash_can_be_cast_in_the_declare_attackers_step():
    """CR 702.8a: "any time you could cast an instant" - which is CR 304.5's rule."""
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    priest = scenario.cast_and_resolve(
        "Containment Priest", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    assert priest.zone is Zone.BATTLEFIELD


def test_a_creature_cannot_be_cast_with_something_on_the_stack():
    """CR 117.1a's other half: the stack has to be empty."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )

    with pytest.raises(ValueError, match="with the stack empty"):
        scenario.cast("Watchwolf")


def test_flash_lets_a_creature_be_cast_in_response():
    """The whole point of flash: a creature can answer a spell on the stack."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )

    priest = scenario.cast_onto_stack(
        "Containment Priest", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    assert scenario.stack_names() == [bolt.name, priest.name]


def test_a_creature_cannot_be_cast_during_an_opponents_turn():
    """CR 302.1 says "a main phase of their turn", and bob's turn is not alice's."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.turn.active_player == "alice":
        scenario.advance()
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()

    with pytest.raises(ValueError, match="only cast it during their own main phase"):
        scenario.cast("Watchwolf", username="alice")


def test_an_instant_needs_no_flash_to_be_cast_at_instant_speed():
    """CR 304.1: an instant is already allowed, so flash adds nothing to it."""
    scenario = board().build()
    scenario.start_at(Step.END_STEP)

    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    assert why_cannot_cast_now(bolt, "alice", scenario.game) is None
    assert not has_flash(bolt.card)
