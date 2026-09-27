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


# --------------------------------------------------------------------------
# Mystical Dispute: "This spell costs {2} less to cast if it targets a blue
# spell." A different flavour of self-reduction from Emrakul's own row above -
# the condition is not a fact about the board, it is about *this spell's own
# announced target* (CR 601.2c), chosen before CR 601.2f determines the cost.
# `Game.cost_reduction_for` now reads `Casting.targets` for exactly this shape
# via `_COSTS_LESS_IF_TARGETS_COLOR_SPELL_RE`, opted into the same way
# Emrakul's discount is - `Game.determine_total_cost(casting)` instead of
# `casting.determine_cost()`.
# --------------------------------------------------------------------------


def _board_with_mystical_dispute() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Opt", "Lightning Bolt"], battlefield=["Mountain", "Island"])
        .player("bob", hand=["Mystical Dispute"], battlefield=["Island", "Island", "Island"])
    )


def test_targeting_a_blue_spell_reduces_the_cost_by_two():
    """Opt is blue (CR 202.2, its own {U} mana cost) - the printed {2}{U}
    becomes {U}."""
    scenario = _board_with_mystical_dispute().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    casting = scenario.cast("Mystical Dispute", username="bob", targets=[opt])
    payment = scenario.game.determine_total_cost(casting)

    assert str(payment.cost) == "{U}"


def test_targeting_a_non_blue_spell_does_not_reduce_the_cost():
    """The other direction: Lightning Bolt is red, not blue, so Mystical
    Dispute's own condition is false and the printed {2}{U} stands."""
    scenario = _board_with_mystical_dispute().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.pass_priority("alice")

    casting = scenario.cast("Mystical Dispute", username="bob", targets=[bolt])
    payment = scenario.game.determine_total_cost(casting)

    assert str(payment.cost) == "{2}{U}"


# --------------------------------------------------------------------------
# Hearth Elemental: "This spell costs {X} less to cast, where X is the
# number of cards in your graveyard that are instant cards, sorcery cards,
# and/or have an Adventure." A union count over CR 205.2a's card types *and*
# CR 715's own idiom - "have an Adventure" is read off `Card.layout is
# Layout.ADVENTURE`, since "Adventure" prints where a *subtype* would (CR
# 715.2's own back face, "Sorcery — Adventure"), never as a quality of the
# whole card the way this clause needs it.
#
# Frantic Firebolt reads the identical list, off the pool and in a damage
# amount rather than a cost reduction ("X is 2 plus the number of cards in
# your graveyard that are ...") - proof the new `count_expression` term
# generalises past the one position Hearth Elemental prints it in.
# --------------------------------------------------------------------------


def test_hearth_elemental_counts_instant_and_sorcery_cards_in_the_graveyard():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Hearth Elemental"],
            graveyard=["Lightning Bolt", "Counterspell"],
            battlefield=["Mountain"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Hearth Elemental")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{3}{R}", "{5}{R} minus 2 (a Bolt, a Counterspell)"


def test_hearth_elemental_also_counts_a_card_that_has_an_adventure():
    """A second Hearth Elemental, dead in the graveyard, is itself a card
    that "has an Adventure" - CR 715.2, whether or not its Adventure half was
    ever cast."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Hearth Elemental"],
            graveyard=["Lightning Bolt", "Hearth Elemental"],
            battlefield=["Mountain"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Hearth Elemental")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{3}{R}", "{5}{R} minus 2 (a Bolt, an Adventure card)"


def test_a_card_that_is_neither_a_quality_nor_an_adventure_does_not_count():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Hearth Elemental"],
            graveyard=["Grizzly Bears"],
            battlefield=["Mountain"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Hearth Elemental")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{5}{R}", "the printed cost, unreduced"


def test_the_reduction_is_only_generic_mana_cr_118_7a():
    """CR 118.7a: a generic reduction never eats into the coloured part."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Hearth Elemental"],
            graveyard=["Lightning Bolt"] * 6,
            battlefield=["Mountain"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Hearth Elemental")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{R}", "{5}{R} minus 6, floored at the coloured symbol"


def test_frantic_firebolt_reads_the_identical_list_off_pool():
    """Off-pool proof: the same quality-list count, read as a damage amount
    rather than a cost reduction. 4 damage (2 base plus 2 - a Bolt, an
    Adventure card) is lethal to a 2/2, so the state-based check (CR 704.5g)
    is the assertion: a wrong, unread amount would leave Grizzly Bears
    alive."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Frantic Firebolt"],
            graveyard=["Lightning Bolt", "Hearth Elemental"],
            battlefield=["Mountain"] * 3,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve("Frantic Firebolt", auto=True, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD, "4 damage is lethal to a 2/2"
