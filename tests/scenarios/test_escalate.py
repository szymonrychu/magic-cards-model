"""Escalate: an *additional* cost per extra mode (CR 702.120a).

CR 702.120a: "Escalate is a static ability of modal spells (see rule 700.2) that
functions while the spell with escalate is on the stack. 'Escalate [cost]' means
'For each mode you choose beyond the first as you cast this spell, pay [cost].'"

It is here beside evoke and flashback because it is printed in the same em-dash
form - Collective Brutality's `Escalate—Discard a card.` - and it is the case
that proves the form does not imply a kind of cost. Evoke replaces the mana cost
(CR 118.9); escalate is added to it (CR 118.8a). A parser that read the em dash
as "alternative cost" would let Collective Brutality be cast for free.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import keyword_ability
from magic_cards_model.machines.modes import modal_profile
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import Scenario


def board(**kwargs) -> Scenario:
    return Scenario().manual_turn_based_actions().player("alice", **kwargs).player("bob")


BRUTALITY_BOARD = {
    "hand": ["Collective Brutality", "Lightning Bolt", "Grizzly Bears"],
    "battlefield": ["Swamp", "Swamp"],
}


# -- reading the cost -------------------------------------------------------


def test_the_em_dash_escalate_cost_is_read_off_the_card():
    ability = keyword_ability(card("Collective Brutality"), "Escalate")

    assert ability is not None
    assert ability.cost == "Discard a card"
    assert ability.em_dash is True


def test_the_mana_form_of_escalate_still_reads_as_mana():
    """Blessed Alliance prints `Escalate {2}`, with no dash."""
    ability = keyword_ability(card("Blessed Alliance"), "Escalate")

    assert ability is not None
    assert ability.cost == "{2}"
    assert ability.cost_is_mana is True
    assert modal_profile(card("Blessed Alliance")).escalate_cost == "{2}"


# -- paying it --------------------------------------------------------------


def test_one_mode_costs_only_the_printed_mana_cost():
    """ "For each mode you choose beyond the first" - one mode is not beyond it."""
    scenario = board(**BRUTALITY_BOARD).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Collective Brutality")
    casting.choose_modes([2])
    casting.pay_escalate()

    assert casting.total_cost.mana == ManaCost.parse("{1}{B}")
    assert casting.total_cost.components == []


def test_a_second_mode_adds_one_discard():
    """CR 118.8a: an additional cost is paid on top of the mana cost, not instead."""
    scenario = board(**BRUTALITY_BOARD).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = scenario.find("Lightning Bolt", Zone.HAND)
    casting = scenario.cast("Collective Brutality")
    casting.choose_modes([2, 3])
    casting.pay_escalate(choosing=[bolt])

    assert casting.total_cost.mana == ManaCost.parse("{1}{B}")
    assert len(casting.total_cost.components) == 1

    swamps = scenario.untapped_sources("Swamp", "Swamp")
    scenario.pay_with(casting.begin_paying(), *swamps)

    assert bolt.zone is Zone.GRAVEYARD


def test_a_third_mode_adds_a_second_discard():
    scenario = board(**BRUTALITY_BOARD).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = scenario.find("Lightning Bolt", Zone.HAND)
    bears = scenario.find("Grizzly Bears", Zone.HAND)
    casting = scenario.cast("Collective Brutality")
    casting.choose_modes([1, 2, 3])
    casting.pay_escalate(choosing=[bolt, bears])

    assert len(casting.total_cost.components) == 2

    swamps = scenario.untapped_sources("Swamp", "Swamp")
    scenario.pay_with(casting.begin_paying(), *swamps)

    assert bolt.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD


def test_escalating_without_a_card_to_discard_refuses_to_be_paid():
    """CR 118.3: the resources have to be there before anything is spent."""
    scenario = board(hand=["Collective Brutality"], battlefield=["Swamp", "Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Collective Brutality")
    casting.choose_modes([2, 3])
    casting.pay_escalate()
    swamps = scenario.untapped_sources("Swamp", "Swamp")
    payment = casting.begin_paying()
    for swamp in swamps:
        payment.tap_for_mana(swamp, [Color.BLACK])

    with pytest.raises(ValueError, match="needs 1 card"):
        payment.pay()


def test_the_mana_form_escalates_the_mana_cost():
    """Blessed Alliance's `Escalate {2}` is added to `{1}{W}`, giving `{3}{W}`."""
    scenario = board(hand=["Blessed Alliance"], battlefield=["Plains"] * 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Blessed Alliance")
    casting.choose_modes([1, 2])
    casting.pay_escalate()

    assert casting.total_cost.mana == ManaCost.parse("{3}{W}")


# -- what escalate is not ---------------------------------------------------


def test_escalate_is_not_an_alternative_cost():
    """An alternative cost would replace `{1}{B}`; escalate leaves it alone."""
    scenario = board(**BRUTALITY_BOARD).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = scenario.find("Lightning Bolt", Zone.HAND)
    casting = scenario.cast("Collective Brutality")
    casting.choose_modes([1, 2])
    casting.pay_escalate(choosing=[bolt])

    assert casting.alternative_cost is None
    assert casting.total_cost.mana == casting.base_cost


def test_escalate_needs_the_modes_announced_first():
    """CR 601.2b: the modes are chosen there, and the cost follows from them."""
    scenario = board(**BRUTALITY_BOARD).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Collective Brutality")

    with pytest.raises(ValueError, match="announced before escalate"):
        casting.pay_escalate()


def test_a_card_without_escalate_has_no_escalate_cost():
    scenario = board(hand=["Abrade"], battlefield=["Mountain", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Abrade")
    casting.choose_modes([1])

    with pytest.raises(ValueError, match="no escalate cost"):
        casting.pay_escalate()
