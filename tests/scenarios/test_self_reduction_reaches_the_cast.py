"""Scenario: a spell's own cost reduction reaches the cast it is paying for.

`test_cost_reduction_shapes.py` proves `Game.cost_reduction_for` *computes*
Leyline Binding's domain discount; every one of its assertions goes through
`Game.determine_total_cost`, an opt-in call no ordinary cast makes. This file
is about the other half: casting the card the way a player casts it -
`Casting.begin_paying()`, which is what `Scenario.cast_onto_stack`,
`Scenario.cast_and_resolve` and the MCP `cast` tool all reach - and being
charged the reduced cost.

Measured before the fix: Leyline Binding with all five basic land types out
asked for `{5}{W}` through `begin_paying()` while `determine_total_cost`
returned `{W}` on the same board. Cost *increases* already reached the cast
(`Game.static_cost_modifiers_for` is folded into `Casting.total_cost`), so the
asymmetry was reductions only.

CR numbers, each looked up with `knowledge_search(type="rules")` in the session
that wrote this file and quoted from what it returned, never from memory:

- **CR 601.2f** - "The player determines the total cost of the spell. Usually
  this is just the mana cost. Some spells have additional or alternative costs.
  Some effects may increase or reduce the cost to pay, or may provide
  alternative payment methods." That determination is a step of *casting*, so
  it belongs to the casting machine and not to an optional helper.
- **CR 118.7a** - "Effects that reduce a cost by an amount of generic mana
  affect only the generic mana component of that cost. They can't affect the
  colored or colorless mana components of that cost." Leyline Binding's five
  basic land types take its whole `{5}` and leave the `{W}`.
- **CR 118.9d** - "If an alternative cost is being paid to cast a spell, any
  additional costs, cost increases, and cost reductions that affect that spell
  are applied to that alternative cost."
- **CR 601.8** - "Casting a spell that alters costs won't affect spells and
  abilities that are already on the stack."

*Domain* is an ability word (CR 207.2c: ability words "have no special rules
meaning"), so no rule number is cited for the word itself.

Every printing is a real Scryfall fixture and every oracle text quoted was
confirmed with `resolve_cards` in this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

# -- domain, through the ordinary casting path ------------------------------


def _binding_board(*lands: str) -> Scenario:
    """alice holds Leyline Binding with `lands` out, and bob has a creature
    for its enters-the-battlefield trigger to aim at."""
    return (
        Scenario()
        .player("alice", hand=["Leyline Binding"], battlefield=list(lands))
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_begin_paying_charges_the_domain_discounted_cost():
    """Leyline Binding: "Domain - This spell costs {1} less to cast for each
    basic land type among lands you control." Five types is {5} off {5}{W},
    and CR 118.7a leaves the {W} standing.

    This is the assertion that was false before: the opt-in
    `Game.determine_total_cost` said `{W}` while `begin_paying` said `{5}{W}`
    on the same board.
    """
    scenario = _binding_board("Plains", "Island", "Swamp", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Leyline Binding")
    payment = casting.begin_paying()

    assert str(payment.cost) == "{W}"


def test_the_discounted_binding_is_actually_paid_for_with_one_land():
    """The whole cast, not just the price: one white source pays for it and the
    enchantment reaches the battlefield."""
    scenario = _binding_board("Plains", "Island", "Swamp", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (plains,) = scenario.untapped_sources("Plains")
    binding = scenario.cast_and_resolve("Leyline Binding", plains)

    assert binding.zone is Zone.BATTLEFIELD
    assert plains.tapped


def test_a_partial_domain_is_charged_the_partial_discount():
    """Two basic land types is {2} off, not five: {3}{W}."""
    scenario = _binding_board("Plains", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Leyline Binding")

    assert str(casting.begin_paying().cost) == "{3}{W}"


def test_the_reduction_is_not_applied_twice_when_determine_total_cost_is_used():
    """`Game.determine_total_cost` appends the same reduction to
    `Casting.cost_reductions` before locking the cost in. The casting machine
    now computes it for itself, so the two paths have to agree rather than
    stack - CR 601.2f determines *the* total cost, once.
    """
    scenario = _binding_board("Plains", "Island", "Swamp", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Leyline Binding")
    payment = scenario.game.determine_total_cost(casting)

    assert str(payment.cost) == "{W}"
    assert str(casting.total_cost.mana) == "{W}"


# -- Emrakul's card-type count, through the ordinary casting path -----------


def test_emrakuls_graveyard_discount_reaches_begin_paying():
    """Emrakul, the Promised End: "This spell costs {1} less to cast for each
    card type among cards in your graveyard." An instant, a creature and a land
    in the graveyard is three card types, so {13} becomes {10}.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Emrakul, the Promised End"],
            graveyard=["Lightning Bolt", "Grizzly Bears", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emrakul, the Promised End")

    assert str(casting.begin_paying().cost) == "{10}"


# -- Mystical Dispute's target-conditional discount --------------------------


def test_mystical_disputes_discount_reads_the_announced_target():
    """Mystical Dispute: "This spell costs {2} less to cast if it targets a blue
    spell." CR 601.2c announces the target before CR 601.2f prices the spell,
    so the casting machine has the target in hand when it asks.
    """
    scenario = (
        Scenario()
        .player("bob", hand=["Ponder"], battlefield=["Island"])
        .player("alice", hand=["Mystical Dispute"], battlefield=["Island", "Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="bob")
    ponder = scenario.cast_onto_stack("Ponder", island, username="bob")
    scenario.pass_priority("bob")

    casting = scenario.cast("Mystical Dispute", username="alice", targets=[ponder])

    assert str(casting.begin_paying().cost) == "{U}"


def test_the_dispute_pays_full_price_against_a_red_spell():
    """The other side of the same condition: no blue spell targeted, no
    discount, so the printed {2}{U} stands."""
    scenario = (
        Scenario()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("alice", hand=["Mystical Dispute"], battlefield=["Island", "Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")

    casting = scenario.cast("Mystical Dispute", username="alice", targets=[bolt])

    assert str(casting.begin_paying().cost) == "{2}{U}"


# -- the reduction and a board-wide tax meet on the same cast ---------------


def test_a_tax_and_a_self_discount_are_both_applied():
    """Thorn of Amethyst-style increases already reached the cast; the discount
    now does too, and CR 601.2f applies both to the one total cost.

    Sphere of Resistance: "Spells cost {1} more to cast." Leyline Binding with
    two basic land types is {2} off and {1} on: {4}{W}.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Leyline Binding"], battlefield=["Plains", "Island"])
        .player("bob", battlefield=["Sphere of Resistance"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Leyline Binding")

    assert str(casting.begin_paying().cost) == "{4}{W}"


@pytest.mark.xfail(
    strict=True,
    reason="`machines/cost.py` owns `CardRequirement`, which has no mana-value "
    "predicate, so `total_cost_for_phrase('exile a blue card with mana value X "
    "from your hand')` returns None whatever X is announced. `Casting` now "
    "records the announced X for an X-keyed pitch cost (CR 107.3a) and "
    "substitutes it into the phrase, but the substituted phrase is still "
    "unreadable until cost.py can express 'with mana value N'.",
)
def test_disrupting_shoals_x_keyed_pitch_cost_is_payable():
    """CR 107.3a: "If a spell ... has a mana cost, alternative cost, additional
    cost, and/or activation cost with an {X}, [-X], or X in it, and the value of
    X isn't defined by the text of that spell ..., the value ... is chosen by
    the [caster]" - announced at CR 601.2b.

    Disrupting Shoal for X=1 exiles a blue card with mana value 1 (Ponder) and
    pays nothing else.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Disrupting Shoal", "Ponder"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")

    ponder = scenario.find("Ponder", Zone.HAND, "alice")
    casting = scenario.cast("Disrupting Shoal", username="alice", targets=[bolt])
    casting.use_pitch_cost(x_value=1, choosing=[ponder])
    payment = casting.begin_paying()
    payment.pay()

    assert str(payment.cost) == ""
    assert ponder.zone is Zone.EXILE
