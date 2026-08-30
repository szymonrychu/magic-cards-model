"""Scenario: a cost reduction worked out from the board, and when it is locked in.

The mechanic is CR 601.2f - the step of casting where a spell's total cost is
determined:

    "The player determines the total cost of the spell. ... The total cost is
    the mana cost or alternative cost (as determined in rule 601.2b), plus all
    additional costs and cost increases, and minus all cost reductions. ... Once
    the total cost is determined, any effects that directly affect the total cost
    are applied. Then the resulting total cost becomes 'locked in.' If effects
    would change the total cost after this time, they have no effect."

Emrakul, the Promised End is the card that makes the timing visible, because its
discount is not a constant: "This spell costs {1} less to cast for each card type
among cards in your graveyard." What it is worth depends on the graveyard *at the
moment CR 601.2f runs* - not when the card was drawn, not when announcement
began, and not any more once the cost is locked.

`Game.determine_total_cost` is the CR 601.2f step for a self-reducing spell;
`Casting.determine_cost` on its own does not consult the game, so a scenario that
wants the discount goes through the game. See `docs/engine-coverage.md`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario, mana_from


def alice_with(*graveyard: str, rings: int = 7) -> Scenario:
    """Alice, holding Emrakul, with a chosen graveyard and enough mana to matter.

    Sol Ring makes two colourless each, which is what pays a cost of pure
    generic mana without dragging thirteen lands into every board.
    """
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Emrakul, the Promised End"],
            graveyard=list(graveyard),
            battlefield=["Sol Ring"] * rings,
        )
        .player("bob", library=["Island"])
    )


def test_an_empty_graveyard_takes_nothing_off_the_printed_cost():
    scenario = alice_with().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emrakul, the Promised End")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{13}", "the printed cost, undiscounted"


def test_each_card_type_in_the_graveyard_takes_one_off():
    """Three card types - instant, sorcery, creature - is a {3} reduction."""
    scenario = alice_with("Counterspell", "Lava Spike", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emrakul, the Promised End")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{10}"


def test_two_cards_of_the_same_type_still_count_once():
    """It counts card *types*, not cards, so a second instant adds nothing."""
    scenario = alice_with("Counterspell", "Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emrakul, the Promised End")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{12}", "one card type between the two of them"


def test_one_card_with_two_card_types_counts_twice():
    """CR 205.2b: an artifact creature satisfies both criteria.

    Solemn Simulacrum on its own is worth {2} off, where Grizzly Bears is worth
    {1}.
    """
    scenario = alice_with("Solemn Simulacrum").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emrakul, the Promised End")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{11}"


def test_a_land_creature_counts_as_two_card_types_as_well():
    """Dryad Arbor is a Land Creature, so it is land *and* creature (CR 205.2b)."""
    scenario = alice_with("Dryad Arbor").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emrakul, the Promised End")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{11}"


def test_only_the_casters_own_graveyard_is_counted():
    """ "cards in *your* graveyard" - the opponent's pile is not the caster's."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Emrakul, the Promised End"], battlefield=["Sol Ring"] * 7)
        .player("bob", graveyard=["Counterspell", "Lava Spike", "Grizzly Bears", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emrakul, the Promised End")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{13}"


def test_the_reduction_reads_the_graveyard_when_the_cost_is_determined():
    """CR 601.2f runs after announcement, so a card binned in between counts.

    This is the case an eagerly computed reduction gets wrong: the discount is
    not a property of the card in hand, it is a step of casting it.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Emrakul, the Promised End", "Sol Ring"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emrakul, the Promised End")
    assert str(casting.total_cost.mana) == "{13}", "nothing in the graveyard yet"

    alice = scenario.player("alice")
    alice.discard(scenario.find("Sol Ring", Zone.HAND))

    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{12}", "the artifact that arrived mid-announcement"


def test_the_total_cost_is_locked_in_once_it_has_been_determined():
    """CR 601.2f: "If effects would change the total cost after this time, they
    have no effect." Filling the graveyard after the fact is worth nothing."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Emrakul, the Promised End", "Lava Spike", "Grizzly Bears", "Sol Ring"],
            graveyard=["Counterspell"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emrakul, the Promised End")
    payment = scenario.game.determine_total_cost(casting)
    locked = str(payment.cost)
    assert locked == "{12}"

    alice = scenario.player("alice")
    for name in ("Lava Spike", "Grizzly Bears", "Sol Ring"):
        alice.discard(scenario.find(name, Zone.HAND))

    assert str(payment.cost) == locked, "the payment already opened does not move"
    assert str(casting.total_cost.mana) == locked, "and neither does the casting's own total"
    assert str(scenario.game.cost_reduction_for(casting.spell, "alice")) == "{4}", (
        "the graveyard really did grow; it just came too late"
    )


def test_the_reduced_cost_is_the_one_that_actually_gets_paid():
    """The whole path: five Sol Rings pay a {10} Emrakul and it reaches the stack."""
    scenario = alice_with("Counterspell", "Lava Spike", "Grizzly Bears", rings=5).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emrakul, the Promised End")
    payment = scenario.game.determine_total_cost(casting)
    rings = scenario.untapped_sources(*["Sol Ring"] * 5)
    scenario.pay_with(payment, *rings)
    spell = scenario.put_on_stack(casting)

    assert spell.zone is Zone.STACK
    assert all(ring.tapped for ring in rings), "ten mana, exactly spent"
    assert scenario.player("alice").mana_pool.total == 0


def test_five_sol_rings_cannot_pay_the_undiscounted_cost():
    """The contrast: the same board with an empty graveyard is three mana short.

    A failed payment rewinds cleanly (CR 733.1), so the Sol Rings stay untapped
    and Emrakul stays in hand.
    """
    scenario = alice_with(rings=5).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emrakul, the Promised End")
    payment = scenario.game.determine_total_cost(casting)
    rings = scenario.untapped_sources(*["Sol Ring"] * 5)
    for ring in rings:
        payment.tap_for_mana(ring, mana_from(ring))

    with pytest.raises(ValueError):
        payment.pay()

    casting.cancel()
    assert scenario.find("Emrakul, the Promised End", Zone.HAND) is not None


def test_a_spell_with_no_reduction_sentence_is_left_alone():
    """The reader is narrow on purpose: Grizzly Bears costs what it prints."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Grizzly Bears"], graveyard=["Counterspell", "Lava Spike"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.find("Grizzly Bears", Zone.HAND)
    assert str(scenario.game.cost_reduction_for(bears, "alice")) == ""
