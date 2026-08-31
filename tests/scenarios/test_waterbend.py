"""Waterbend: tapping artifacts *or creatures* instead of spending mana.

CR 701.67a: "'Waterbend [cost]' means 'Pay [cost]. For each generic mana in
that cost, you may tap an untapped artifact or creature you control rather than
pay that mana.'"

It is improvise (CR 702.126a) one step wider - the same "for each generic mana
... you may tap an untapped X you control rather than pay that mana", with
creatures allowed alongside artifacts - and it is built out of the same
`ObjectOffer` in `machines/objects_as_costs.py`.

The one thing waterbend does *not* share with the rest of the family: it is an
action word introducing an **ability's** cost ("Waterbend {3}: ..."), not a
static ability of a spell on the stack. So the tests below open the payment for
that cost directly rather than through a `Casting`. Turning the printed phrase
"Waterbend {3}" into a cost is `cost_component_for_phrase` in `machines/cost.py`
and is not this module's work; `tests/scenarios/judge/test_judge_costs.py`
holds the `xfail` for that half.

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import CostPayment, TotalCost
from magic_cards_model.machines.objects_as_costs import waterbend, waterbend_offer
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Flexible Waterbender prints `Waterbend {3}` - three generic symbols, and
    a board with one creature, one artifact, one land to cover them."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Flexible Waterbender", "Grizzly Bears", "Welding Jar", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def open_payment(scenario, cost: str = "{3}") -> CostPayment:
    """The payment for a waterbend cost, opened on a real board state."""
    return CostPayment.for_total(TotalCost.of(cost), game=scenario.game, payer="alice")


def test_the_offer_is_untapped_artifacts_or_creatures_you_control():
    """CR 701.67a's eligibility, read back off the offer."""
    offer = waterbend_offer()

    assert offer.rule == "CR 701.67a"
    assert offer.zone is Zone.BATTLEFIELD
    assert offer.untapped_only and offer.yours_only
    assert offer.pays_generic and not offer.pays_own_colors
    assert offer.noun == "an artifact or creature"


def test_a_creature_and_an_artifact_each_pay_one_generic():
    """The half that separates waterbend from improvise: a Grizzly Bears is not
    an artifact, and CR 701.67a takes it anyway."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")
    jar = scenario.creature("Welding Jar", "alice")

    payment = open_payment(scenario)
    waterbend(payment, bear, jar)

    assert str(payment.cost) == "{3}"
    assert str(payment.mana_owed) == "{1}"

    scenario.pay_with(payment, *scenario.untapped_sources("Island"))

    assert bear.tapped and jar.tapped


def test_nothing_is_tapped_until_the_cost_is_paid():
    """CR 601.2h again: the tapping is part of paying, not of announcing."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")

    payment = open_payment(scenario)
    waterbend(payment, bear)

    assert not bear.tapped
    payment.cancel()
    assert not bear.tapped


def test_a_land_cannot_be_waterbent():
    """CR 701.67a names artifacts and creatures, and an Island is neither."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")

    payment = open_payment(scenario)

    with pytest.raises(ValueError, match="not an artifact or creature"):
        waterbend(payment, island)


def test_an_opponents_creature_cannot_be_waterbent():
    """CR 701.67a: "an untapped artifact or creature **you control**"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")

    payment = open_payment(scenario)

    with pytest.raises(ValueError, match="does not control"):
        waterbend(payment, theirs)


def test_an_already_tapped_permanent_cannot_be_waterbent():
    """ "you may tap an **untapped** artifact or creature" (CR 701.67a)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")
    bear.tap()

    payment = open_payment(scenario)

    with pytest.raises(ValueError, match="already tapped"):
        waterbend(payment, bear)


def test_more_permanents_than_the_cost_has_generic_mana_is_refused():
    """CR 701.67a bounds itself to "each generic mana **in that cost**"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bender = scenario.creature("Flexible Waterbender", "alice")
    bear = scenario.creature("Grizzly Bears", "alice")
    jar = scenario.creature("Welding Jar", "alice")

    payment = open_payment(scenario, "{2}")
    waterbend(payment, bear, jar)

    with pytest.raises(ValueError, match="has no"):
        waterbend(payment, bender)

    assert not bender.tapped
