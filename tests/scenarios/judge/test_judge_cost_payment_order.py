"""Judge scenarios: the order the parts of one total cost are paid in.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#955** - Momentous Fall + Omnath, Locus of Mana. Amy taps four Forests
  and casts Momentous Fall sacrificing Omnath. How many cards does she draw?

The ruling turns on CR 601.2h: the mana and the sacrifice are two components of
one total cost, paid "in any order", so Omnath's size at the moment it is
sacrificed depends on whether the green mana is still floating. Sacrifice
first and Omnath is a 5/5; pay the mana first and it is a 1/1. Nothing in
between is available, because CR 601.2h's payment is not divisible and
CR 601.2g's window to make more mana has already closed.

Card text verified with `resolve_cards`; every CR number here was looked up
with `knowledge_search(type="rules")` in this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import additional_cost_phrases
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Alice with four Forests, Omnath, and Momentous Fall in hand."""
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 10,
            hand=["Momentous Fall"],
            battlefield=["Forest"] * 4 + ["Omnath, Locus of Mana"],
        )
        .player("bob")
    )


def test_the_sacrifice_is_an_additional_cost_alongside_the_mana():
    """DDR#955's first step: work out the total cost (CR 601.2f, CR 118.8a).

    Momentous Fall (verified with `resolve_cards`): "As an additional cost to
    cast this spell, sacrifice a creature. You draw cards equal to the
    sacrificed creature's power, then you gain life equal to its toughness."

    CR 118.8a: "Any number of additional costs may be applied to a spell as
    it's being cast ... The controller of the spell or ability announces their
    intentions to pay any or all of those costs". The engine reads the sentence
    off the card and `Casting.total_cost` carries both halves - {2}{G}{G} and
    the sacrifice - as one cost, which is exactly the object CR 601.2h then
    says is paid in any order.
    """
    assert additional_cost_phrases(card("Momentous Fall")) == ["sacrifice a creature"]

    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    omnath = scenario.creature("Omnath, Locus of Mana", "alice")

    casting = scenario.cast("Momentous Fall", sacrificing=[omnath])

    assert str(casting.total_cost) == "{2}{G}{G}, sacrifice a creature"


def test_paying_the_whole_cost_sacrifices_the_creature_and_resolves_the_spell():
    """DDR#955's baseline, with no dependence on Omnath's size.

    CR 601.2h: "The player pays the total cost. First, they pay all costs that
    don't involve random elements or moving objects from the library to a
    public zone, in any order." Both of Momentous Fall's components are of that
    first kind, so both are paid here, and CR 608.2n then puts the resolved
    instant into its owner's graveyard.

    What the resolution *does* is the `xfail` below; that the cost is really
    paid is this test.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    omnath = scenario.creature("Omnath, Locus of Mana", "alice")

    casting = scenario.cast("Momentous Fall", sacrificing=[omnath])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Forest"] * 4, username="alice"))
    fall = scenario.put_on_stack(casting)

    assert omnath.zone is Zone.GRAVEYARD, "the additional cost was paid"

    scenario.resolve_top()

    assert fall.zone is Zone.GRAVEYARD


def test_omnath_is_a_plain_one_one_with_no_mana_floating():
    """DDR#955's other half, as the engine currently sees it.

    Omnath, Locus of Mana (verified with `resolve_cards`): "You don't lose
    unspent green mana as steps and phases end. Omnath gets +1/+1 for each
    unspent green mana you have."

    With nothing floating, the printed 1/1 is the right answer either way -
    which is the honest thing this file can assert about Omnath's size, and the
    reason the episode's own question is `xfail` below.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    omnath = scenario.creature("Omnath, Locus of Mana", "alice")

    assert (omnath.power, omnath.toughness) == (1, 1)


@pytest.mark.xfail(
    reason="the payment order is no longer the gap - CostPayment.components_before_mana "
    "now pays the sacrifice while the four green mana is still floating (CR 601.2h). "
    "Two registry gaps remain, both outside machines/cost.py: Omnath's 'gets +1/+1 for "
    "each unspent green mana you have' has no row in machines/layers.LAYER_EFFECTS, so "
    "Omnath is a 1/1 however much mana is unspent; and Momentous Fall's own two-clause "
    "effect ('You draw cards equal to the sacrificed creature's power, then you gain "
    "life equal to its toughness') is not read by machines/effects.py at all - "
    "effect_for returns None, so the spell resolves and does nothing. A last-known-"
    "information snapshot of the sacrificed creature (CR 608.2h) is what would carry "
    "the power and toughness to that effect once it exists.",
    strict=True,
)
def test_sacrificing_omnath_before_paying_the_mana_draws_five():
    """DDR#955's actual ruling: pay the sacrifice component first, while the
    four green mana is still in the pool, and Omnath is a 5/5.

    CR 601.2g: "If the total cost includes a mana payment, the player then has
    a chance to activate mana abilities ... Mana abilities must be activated
    before costs are paid." So the four Forests are tapped and the mana is
    floating before CR 601.2h's payment starts. Omnath's second ability is a
    static ability generating a continuous effect (CR 604.2), applied
    continuously rather than on the stack, so while that mana is unspent Omnath
    is 5/5. Sacrifice it at that moment and Momentous Fall's effect reads a
    power of 5 and a toughness of 5.

    Two separate pieces are missing. Omnath has no `LAYER_EFFECTS` entry, so it
    is a 1/1 no matter what is floating - the same registry gap DDR#982 and
    DDR#801 already record in this package. And Momentous Fall's own effect is
    unread: `effect_for("Momentous Fall", ...)` is None, so the spell resolves
    and does nothing whatever the sacrificed creature's size was.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    omnath = scenario.creature("Omnath, Locus of Mana", "alice")

    casting = scenario.cast("Momentous Fall", sacrificing=[omnath])
    payment = casting.begin_paying()
    # CR 601.2h's "in any order", exercised: the sacrifice is paid while the
    # four green mana is still in the pool, which is what makes Omnath a 5/5
    # as it is sacrificed rather than the 1/1 it is once the mana is spent.
    payment.components_before_mana = True
    scenario.pay_with(payment, *scenario.untapped_sources(*["Forest"] * 4, username="alice"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert len(alice.hand) == 5, "five cards, off a 5/5 Omnath"
    assert alice.life == 25
