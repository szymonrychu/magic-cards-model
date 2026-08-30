import pytest

from magic_cards_model.machines import CostPayment, CostStep
from magic_cards_model.machines.cost import (
    ComponentKind,
    TotalCost,
    additional_cost_phrases,
    alternative_cost_phrases,
    apply_modifications,
    increase,
    pay_life_cost,
    reduce,
    remove_counters_cost,
    sacrifice_cost,
    tap_cost,
)
from magic_cards_model.models import CardState, Color, ManaCost, Zone
from tests.cards import card, card_state


def land(name: str = "Mountain") -> CardState:
    """An untapped land on the battlefield."""
    return card_state(name, Zone.BATTLEFIELD)


def test_tapping_for_mana_fills_the_pool():
    payment = CostPayment(cost=ManaCost.parse("{R}"))
    source = land()

    pool = payment.tap_for_mana(source, [Color.RED])

    assert source.tapped
    assert pool.floating == {Color.RED: 1}
    assert payment.step is CostStep.TAPPING


def test_the_full_walk_from_tapping_to_overflow():
    payment = CostPayment(cost=ManaCost.parse("{1}{R}"))
    sources = [land(), land(), land()]

    payment.tap_for_mana(sources[0], [Color.RED])
    payment.tap_for_mana(sources[1], [Color.RED])
    payment.tap_for_mana(sources[2], [Color.GREEN])
    payment.finish_tapping()
    assert payment.step is CostStep.POOLED

    overflow = payment.pay()

    assert payment.step is CostStep.PAID
    # {1}{R} paid from RRG leaves exactly one mana floating.
    assert overflow.total == 1


def test_paying_without_enough_mana_leaves_the_machine_usable():
    payment = CostPayment(cost=ManaCost.parse("{2}{R}"))
    first, second = land(), land()
    payment.tap_for_mana(first, [Color.RED])

    with pytest.raises(ValueError, match="cannot pay"):
        payment.pay()

    assert payment.step is not CostStep.PAID
    assert payment.shortfall

    # Still open, so tap another source and finish the payment.
    payment.tap_for_mana(second, [Color.RED, Color.RED])
    assert payment.pay().is_empty
    assert payment.step is CostStep.PAID


def test_cancelling_untaps_every_source():
    payment = CostPayment(cost=ManaCost.parse("{5}"))
    sources = [land(), land()]
    for source in sources:
        payment.tap_for_mana(source, [Color.RED])

    payment.cancel()

    assert payment.step is CostStep.CANCELLED
    assert all(source.untapped for source in sources)
    assert payment.pool.is_empty


def test_a_settled_payment_is_closed():
    payment = CostPayment(cost=ManaCost.parse("{R}"))
    payment.tap_for_mana(land(), [Color.RED])
    payment.pay()

    with pytest.raises(ValueError, match="already"):
        payment.tap_for_mana(land(), [Color.RED])
    with pytest.raises(ValueError, match="already"):
        payment.cancel()


def test_a_tapped_permanent_cannot_be_tapped_again():
    payment = CostPayment(cost=ManaCost.parse("{2}"))
    source = land()
    payment.tap_for_mana(source, [Color.RED])

    with pytest.raises(ValueError, match="already tapped"):
        payment.tap_for_mana(source, [Color.RED])


# -- the composite cost ----------------------------------------------------


def test_a_total_cost_is_mana_plus_its_components():
    creature = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="alice")
    total = TotalCost.of("{1}{R}", sacrifice_cost(creature, payer="alice"))

    assert total.mana == ManaCost.parse("{1}{R}")
    assert [component.kind for component in total.components] == [ComponentKind.SACRIFICE]
    assert not total.is_free


def test_a_cost_with_no_mana_and_no_components_is_free():
    assert TotalCost.of().is_free
    assert not TotalCost.of("{0}", pay_life_cost(1, payer="alice")).is_free


def test_tapping_a_creature_as_a_cost_taps_it():
    """CR 118.3: the cost is paid by the permanent becoming tapped."""
    creature = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="alice")
    payment = CostPayment.for_total(TotalCost.of("{0}", tap_cost(creature, payer="alice")))

    payment.pay()

    assert creature.tapped
    assert payment.step is CostStep.PAID


def test_a_creature_that_is_already_tapped_cannot_pay_a_tap_cost():
    """CR 118.3 names this case: "a permanent that's already tapped can't be
    tapped to pay a cost"."""
    creature = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="alice", tapped=True)
    payment = CostPayment.for_total(TotalCost.of("{0}", tap_cost(creature, payer="alice")))

    assert payment.unpayable is not None
    with pytest.raises(ValueError, match="already tapped"):
        payment.pay()
    assert payment.step is not CostStep.PAID


def test_cancelling_untaps_a_creature_tapped_as_a_cost():
    creature = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="alice")
    payment = CostPayment.for_total(TotalCost.of("{0}", tap_cost(creature, payer="alice")))
    payment.pay()

    # A paid payment is settled, so the rewind is driven from a fresh one.
    payment.components[0].unpay(None)

    assert creature.untapped


def test_a_component_with_nothing_chosen_cannot_be_paid():
    """ "Sacrifice a creature" with no creature to sacrifice is unpayable."""
    payment = CostPayment.for_total(
        TotalCost.of("{1}{R}", sacrifice_cost(payer="alice", required=1))
    )

    assert "needs 1" in (payment.unpayable or "")
    with pytest.raises(ValueError, match="needs 1"):
        payment.pay()


def test_removing_counters_as_a_cost_is_refused_rather_than_faked():
    """Counters are not modelled anywhere, so the cost cannot be paid at all."""
    creature = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="alice")
    payment = CostPayment.for_total(
        TotalCost.of("{0}", remove_counters_cost(creature, 1, payer="alice"))
    )

    with pytest.raises(ValueError, match="counters are not modelled"):
        payment.pay()


def test_paying_life_needs_a_player_to_pay_it():
    payment = CostPayment.for_total(TotalCost.of("{0}", pay_life_cost(1, payer="alice")))

    with pytest.raises(ValueError, match="needs a game"):
        payment.pay()


def test_paying_zero_life_is_always_allowed():
    """CR 119.4b: players can always pay 0 life, whatever their life total."""
    payment = CostPayment.for_total(TotalCost.of("{0}", pay_life_cost(0)))

    payment.pay()

    assert payment.step is CostStep.PAID


# -- cost increases and reductions (CR 601.2f, 118.7) ----------------------


def test_an_increase_adds_to_both_halves_of_a_cost():
    assert increase(ManaCost.parse("{1}{G}"), ManaCost.parse("{2}{G}")) == ManaCost.parse(
        "{3}{G}{G}"
    )


def test_a_generic_reduction_cannot_touch_coloured_pips():
    """CR 118.7a: a reduction of generic mana affects only the generic part."""
    reduced = reduce(ManaCost.parse("{2}{G}{G}"), ManaCost.parse("{4}"))

    assert reduced == ManaCost.parse("{G}{G}")
    assert reduced.generic == 0
    assert reduced.colored == {Color.GREEN: 2}


def test_a_reduction_of_a_colour_the_cost_does_not_want_reduces_generic():
    """CR 118.7b."""
    assert reduce(ManaCost.parse("{3}{G}"), ManaCost.parse("{U}")) == ManaCost.parse("{2}{G}")


def test_a_colour_reduction_beyond_the_pips_spills_into_generic():
    """CR 118.7c."""
    assert reduce(ManaCost.parse("{3}{G}"), ManaCost.parse("{G}{G}")) == ManaCost.parse("{2}")


def test_a_cost_never_reduces_below_zero():
    assert reduce(ManaCost.parse("{1}"), ManaCost.parse("{9}")) == ManaCost()


def test_increases_are_applied_before_reductions():
    """A {2} increase and a {2} reduction cancel; the other order would too, but
    a reduction bigger than the cost would not, and that is the case that shows
    the ordering. See the note in `apply_modifications` about the citation."""
    total = apply_modifications(
        ManaCost.parse("{1}{U}"),
        increases=[ManaCost.parse("{3}")],
        reductions=[ManaCost.parse("{9}")],
    )
    assert total == ManaCost.parse("{U}")


def test_reducing_a_hybrid_cost_keeps_its_hybrid_symbols():
    """Kitchen Finks is {1}{G/W}{G/W}. CR 118.7a: a generic reduction touches
    only the generic component, so both hybrid symbols survive it."""
    finks = ManaCost.parse(card("Kitchen Finks").mana_cost or "")

    assert reduce(finks, ManaCost.parse("{1}")) == ManaCost.parse("{G/W}{G/W}")


def test_a_colour_reduction_against_a_hybrid_cost_takes_generic():
    """CR 118.7b: {G/W} does not *require* green - CR 107.4e leaves the choice
    until the cost is paid - so a {G} reduction reduces generic instead."""
    finks = ManaCost.parse(card("Kitchen Finks").mana_cost or "")

    assert reduce(finks, ManaCost.parse("{G}")) == ManaCost.parse("{G/W}{G/W}")


def test_reducing_by_a_phyrexian_symbol_takes_one_mana_of_its_colour():
    """CR 118.7f. Dismember is {1}{B/P}{B/P}, so the reduction it names is {B}."""
    assert reduce(ManaCost.parse("{2}{B}{B}"), ManaCost.parse("{B/P}")) == ManaCost.parse("{2}{B}")


def test_reducing_by_a_snow_symbol_takes_generic():
    """CR 118.7g."""
    assert reduce(ManaCost.parse("{2}{B}"), ManaCost.parse("{S}")) == ManaCost.parse("{1}{B}")


def test_reducing_by_a_hybrid_symbol_is_refused_rather_than_guessed():
    """CR 118.7e has the payer choose a half when the reduction is applied, and
    there is nobody to ask, so it raises rather than picking one."""
    with pytest.raises(ValueError, match="nobody to ask"):
        reduce(ManaCost.parse("{2}{G}"), ManaCost.parse("{G/W}"))


def test_an_additional_cost_on_a_hybrid_spell_keeps_its_symbols():
    """CR 601.2f: the total cost combines symbol for symbol, so a kicker on
    Kitchen Finks is {3}{G/W}{G/W} and not {3}."""
    finks = ManaCost.parse(card("Kitchen Finks").mana_cost or "")

    assert increase(finks, ManaCost.parse("{2}")) == ManaCost.parse("{3}{G/W}{G/W}")


def test_an_unmodified_hybrid_cost_passes_through_untouched():
    finks = ManaCost.parse(card("Kitchen Finks").mana_cost or "")

    assert apply_modifications(finks) == finks


def test_reductions_stack():
    total = apply_modifications(
        ManaCost.parse("{4}{W}"),
        reductions=[ManaCost.parse("{1}"), ManaCost.parse("{2}")],
    )
    assert total == ManaCost.parse("{1}{W}")


# -- reading the printed cost text -----------------------------------------


def test_additional_cost_text_is_read_off_the_real_card():
    assert additional_cost_phrases(card("Fling")) == ["sacrifice a creature"]
    assert additional_cost_phrases(card("Cathartic Reunion")) == ["discard two cards"]
    assert additional_cost_phrases(card("Fumarole")) == ["pay 3 life"]
    assert additional_cost_phrases(card("Lightning Bolt")) == []


def test_alternative_cost_text_is_read_off_the_real_card():
    assert alternative_cost_phrases(card("Fireblast")) == ["sacrifice two Mountains"]
    assert alternative_cost_phrases(card("Force of Will")) == [
        "pay 1 life and exile a blue card from your hand"
    ]
    assert alternative_cost_phrases(card("Lightning Bolt")) == []


# -- snow mana and summoning sickness at the payment machine ---------------


def test_tapping_a_snow_permanent_produces_snow_mana():
    """CR 205.4g, 106.3: a Snow-Covered Forest is a snow source, so its green
    can pay Icehide Golem's {S} (CR 107.4h)."""
    payment = CostPayment(cost=ManaCost.parse("{S}"))
    forest = card_state("Snow-Covered Forest", Zone.BATTLEFIELD, controller="alice")

    pool = payment.tap_for_mana(forest, [Color.GREEN])

    assert pool.snow == {Color.GREEN: 1}
    assert payment.pay().is_empty


def test_tapping_an_ordinary_permanent_produces_no_snow_mana():
    payment = CostPayment(cost=ManaCost.parse("{S}"))

    pool = payment.tap_for_mana(land("Forest"), [Color.GREEN])

    assert pool.snow == {}
    with pytest.raises(ValueError, match="cannot pay"):
        payment.pay()


def test_a_summoning_sick_creature_cannot_be_tapped_for_mana():
    """CR 302.6, 602.5a. A payment with no game answers this off the permanent,
    since summoning sickness is a flag on `CardState`."""
    payment = CostPayment(cost=ManaCost.parse("{G}"))
    elves = card_state("Llanowar Elves", Zone.BATTLEFIELD, controller="alice")
    assert elves.summoning_sick

    with pytest.raises(ValueError, match="most recent turn began"):
        payment.tap_for_mana(elves, [Color.GREEN])

    assert elves.untapped
    assert payment.pool.is_empty


def test_a_creature_that_has_been_around_can_be_tapped_for_mana():
    payment = CostPayment(cost=ManaCost.parse("{G}"))
    elves = card_state("Llanowar Elves", Zone.BATTLEFIELD, controller="alice")
    elves.summoning_sick = False

    assert payment.tap_for_mana(elves, [Color.GREEN]).floating == {Color.GREEN: 1}


def test_haste_lets_a_creature_be_tapped_for_mana_at_once():
    """CR 702.10c covers activated abilities, not only attacking."""
    payment = CostPayment(cost=ManaCost.parse("{R}"))
    prospector = card_state("Skirk Prospector", Zone.BATTLEFIELD, controller="alice")
    assert prospector.summoning_sick

    with pytest.raises(ValueError, match="most recent turn began"):
        payment.tap_for_mana(prospector, [Color.RED])

    goblin = card_state("Raging Goblin", Zone.BATTLEFIELD, controller="alice")
    assert "Haste" in goblin.card.keywords
    assert payment.tap_for_mana(goblin, [Color.RED]).floating == {Color.RED: 1}


def test_a_land_taps_for_mana_the_turn_it_arrives():
    """CR 302.6 holds back creatures only; a land is not one."""
    payment = CostPayment(cost=ManaCost.parse("{R}"))
    mountain = land()
    assert mountain.summoning_sick

    assert payment.tap_for_mana(mountain, [Color.RED]).floating == {Color.RED: 1}


def test_life_is_not_on_the_table_without_a_payer():
    """CR 107.4f: paying a Phyrexian symbol with life needs a real life total."""
    payment = CostPayment(cost=ManaCost.parse("{U/P}"))

    assert payment.life_available == 0
    assert payment.shortfall
    with pytest.raises(ValueError, match="cannot pay"):
        payment.pay()


def test_choices_must_line_up_with_the_symbols():
    payment = CostPayment(cost=ManaCost.parse("{1}{B/P}{B/P}"))

    with pytest.raises(ValueError, match="expected 3 choices"):
        payment.choose([0])
