"""Escape: casting a card out of the graveyard for an alternative cost that
includes exiling other cards from that graveyard (CR 702.138).

CR 702.138a: "Escape represents a static ability that functions while the
card with escape is in a player's graveyard. 'Escape [cost]' means 'You may
cast this card from your graveyard by paying [cost] rather than paying its
mana cost.' Casting a spell using its escape ability follows the rules for
paying alternative costs in rules 601.2b and 601.2f-h."

Structurally identical to flashback (CR 702.34a, `tests/scenarios/
test_flashback.py`), with one difference the parser has to read: the escape
cost itself names an additional non-mana component, "Exile N other cards
from your graveyard" - CR 201.4's self-exclusion "other", read generally by
`machines/cost.py`'s `_requirement`/`_QUALITY_CONNECTORS` rather than as a
special case of Cling to Dust's own printing.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file (CR 702.138 in full, and CR 118.9/601.2b/601.2f-h for
the alternative-cost machinery escape reuses).

Cling to Dust ({3}{B}, exile five other cards) is the assigned card. Uro,
Titan of Nature's Wrath ({G}{G}{U}{U}, exile five other cards) is not in the
deck pool and not named in the brief - a different color pair, a different
card type (a permanent rather than an instant) - and proves the same
`_option_from_keyword`/`total_cost_for_phrase` machinery reads its escape
cost with no code specific to either printing.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import keyword_cast_options, why_cannot_cast_from
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def board(**kwargs) -> Scenario:
    return Scenario().manual_turn_based_actions().player("alice", **kwargs).player("bob")


# -- what the keyword offers ------------------------------------------------


def test_escape_offers_a_cast_from_the_graveyard_for_an_alternative_cost():
    (option,) = keyword_cast_options(card("Cling to Dust"))

    assert option.zone is Zone.GRAVEYARD
    assert option.pays_mana_cost is False
    assert option.understood
    assert str(option.cost) == "{3}{B}, Exile five other cards from your graveyard"


def test_a_card_with_no_escape_offers_nothing_for_it():
    assert keyword_cast_options(card("Lightning Bolt")) == []


# -- casting Cling to Dust ---------------------------------------------------


def _filler(n: int) -> list[str]:
    return ["Mishra's Bauble"] * n


def test_cling_to_dust_is_cast_from_the_graveyard_via_escape():
    # Six fillers: five pay the escape cost's exile, and the sixth is left in
    # the graveyard so Cling to Dust's own "exile target card from a
    # graveyard" has something to target that is not also being spent as
    # fuel - the two are independent choices (CR 702.138a's cost and CR
    # 601.2c's target), and this scenario has to keep them independent too.
    scenario = board(
        graveyard=["Cling to Dust", *_filler(6)],
        battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    others = [c for c in scenario.player("alice").graveyard if c.name != "Cling to Dust"]
    assert len(others) == 6
    fuel, target = others[:5], others[5]

    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")

    casting = scenario.cast("Cling to Dust", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel)
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    spell = scenario.put_on_stack(casting)

    assert spell.zone is Zone.STACK
    assert spell not in scenario.player("alice").graveyard
    # CR 702.138a's cost: five other cards left the graveyard, exiled.
    for card_state in fuel:
        assert card_state.zone is Zone.EXILE


def test_escape_is_refused_without_enough_fuel_in_the_graveyard():
    """CR 702.138a's cost cannot be paid with fewer than five other cards -
    same "not a legal choice" refusal CR 601.2b already gives any additional
    cost this engine cannot fill."""
    scenario = board(
        graveyard=["Cling to Dust", *_filler(2)],
        battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fuel = [c for c in scenario.player("alice").graveyard if c.name != "Cling to Dust"]
    assert len(fuel) == 2

    casting = scenario.cast("Cling to Dust", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel)
    payment = casting.begin_paying()
    with pytest.raises(ValueError):
        payment.pay()


def test_escape_carries_no_sorcery_only_restriction_of_its_own():
    """CR 702.138a prints no "activate/cast only as a sorcery" clause (unlike
    dredge's own graveyard-return special action) - so an instant with escape
    can be cast from the graveyard at instant speed."""
    scenario = board(
        graveyard=["Cling to Dust", *_filler(5)],
        battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
    ).build()
    scenario.start_at(Step.END_STEP)
    reason = why_cannot_cast_from(
        scenario.player("alice").graveyard[0], "alice", Zone.GRAVEYARD, scenario.game
    )
    assert reason is None


# -- generality: a second, un-named escape printing --------------------------


def test_uro_reads_its_own_differently_shaped_escape_cost():
    """A different color pair, a different card type (permanent rather than
    instant), the same five-other-cards template - proves `_option_from_
    keyword`'s "escape" branch is not keyed to Cling to Dust's own printing."""
    (option,) = keyword_cast_options(card("Uro, Titan of Nature's Wrath"))

    assert option.zone is Zone.GRAVEYARD
    assert option.pays_mana_cost is False
    assert option.understood
    assert str(option.cost) == "{G}{G}{U}{U}, Exile five other cards from your graveyard"


def test_uro_is_cast_from_the_graveyard_via_its_own_escape_cost():
    scenario = board(
        graveyard=["Uro, Titan of Nature's Wrath", *_filler(5)],
        battlefield=["Forest", "Forest", "Island", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fuel = [
        c for c in scenario.player("alice").graveyard if c.name != "Uro, Titan of Nature's Wrath"
    ]
    assert len(fuel) == 5
    sources = scenario.untapped_sources("Forest", "Forest", "Island", "Island")

    casting = scenario.cast("Uro, Titan of Nature's Wrath", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    spell = scenario.put_on_stack(casting)

    assert spell.zone is Zone.STACK
    for card_state in fuel:
        assert card_state.zone is Zone.EXILE
