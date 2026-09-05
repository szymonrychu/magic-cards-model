"""Warp: cast it cheap now, exile it, cast it properly later (CR 702.185).

CR 702.185a: "Warp represents two static abilities that function while the card
with warp is on the stack, one of which may create a delayed triggered ability."
CR 702.185b: "Some effects refer to 'warped' cards in exile. A warped card in
exile is one that was exiled by the delayed triggered ability created by a warp
ability." CR 702.185c defines "a spell was warped this turn" as one cast for its
warp cost.

Bygone Colossus prints the reminder in full: "You may cast this card from your
hand for its warp cost. Exile this creature at the beginning of the next end
step, then you may cast it from exile on a later turn."

So the three pieces are: an alternative cost from hand, a delayed trigger that
exiles the permanent, and permission to cast the exiled card later for its own
mana cost. The middle piece is a delayed triggered ability (CR 603.7), which is
not modelled - `exile_warped` performs it by hand, the way scenarios perform the
combat turn-based actions, and the xfail at the bottom says nothing fires it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import exile_warped, keyword_cast_options
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileMarker
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import Scenario


def board(lands: int = 9) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Bygone Colossus"], battlefield=["Island"] * lands)
        .player("bob", battlefield=["Forest"])
    )


def alices_next_main(scenario) -> None:
    for _ in range(60):
        if scenario.stack_names():
            # `advance` refuses to leave a step while the stack is non-empty
            # (CR 500.2, 117.4) - a real triggered ability parsed off the
            # card's own reminder text lands here at end_step, which the old
            # `advance` used to silently skip past instead of resolving.
            scenario.pass_until_resolved()
            continue
        scenario.advance()
        if scenario.step is Step.UNTAP:
            scenario.game.untap_step()
        if scenario.turn.active_player == "alice" and scenario.step is Step.PRECOMBAT_MAIN:
            return
    raise AssertionError("never got back to alice's main phase")


# -- what the keyword offers ------------------------------------------------


def test_warp_offers_two_options_one_from_hand_and_one_from_exile():
    """CR 702.185a is the cheap cast; CR 702.185b is the warped card in exile."""
    from_hand, from_exile = keyword_cast_options(card("Bygone Colossus"))

    assert from_hand.zone is Zone.HAND
    assert from_hand.pays_mana_cost is False
    assert str(from_hand.cost) == "{3}"

    assert from_exile.zone is Zone.EXILE
    assert from_exile.marker is ExileMarker.WARPED
    assert from_exile.pays_mana_cost is True
    assert from_exile.later_turn is True


# -- casting it for the warp cost -------------------------------------------


def test_a_warped_spell_costs_the_warp_cost_and_not_the_mana_cost():
    """CR 118.9: an alternative cost is paid rather than the mana cost."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Bygone Colossus")
    casting.use_keyword("Warp")

    assert casting.base_cost == ManaCost.parse("{9}")
    assert casting.total_cost.mana == ManaCost.parse("{3}")


def test_a_nine_drop_reaches_the_battlefield_off_three_lands():
    scenario = board(lands=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Island", "Island", "Island")
    casting = scenario.cast("Bygone Colossus")
    casting.use_keyword("Warp")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)

    assert scenario.resolve_top().zone is Zone.BATTLEFIELD
    assert casting.keyword_used == "Warp"


# -- the exile, and the cast that follows it --------------------------------


def test_exiling_the_warped_permanent_marks_it_as_warped():
    """CR 702.185b: the delayed trigger's exile is what makes it a warped card."""
    scenario = board(lands=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Island", "Island", "Island")
    casting = scenario.cast("Bygone Colossus")
    casting.use_keyword("Warp")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    colossus = scenario.resolve_top()

    exile_warped(scenario.game, colossus)

    assert colossus.zone is Zone.EXILE
    assert colossus.exile_annotation is not None
    assert colossus.exile_annotation.marker is ExileMarker.WARPED


def test_a_warped_card_cannot_be_cast_again_the_same_turn():
    """The reminder says "on a later turn", and this is the same one."""
    scenario = board(lands=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Island", "Island", "Island")
    casting = scenario.cast("Bygone Colossus")
    casting.use_keyword("Warp")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    exile_warped(scenario.game, scenario.resolve_top())

    again = scenario.cast("Bygone Colossus", from_zone=Zone.EXILE)

    with pytest.raises(ValueError, match="later turn"):
        again.use_keyword("Warp")


def test_a_warped_card_is_cast_from_exile_later_for_its_full_mana_cost():
    """CR 702.185b hands out permission, not a discount: {9} is still {9}."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Island", "Island", "Island")
    casting = scenario.cast("Bygone Colossus")
    casting.use_keyword("Warp")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    exile_warped(scenario.game, scenario.resolve_top())
    alices_next_main(scenario)

    again = scenario.cast("Bygone Colossus", from_zone=Zone.EXILE)
    again.use_keyword("Warp")

    assert again.total_cost.mana == ManaCost.parse("{9}")

    islands = scenario.untapped_sources(*["Island"] * 9, username="alice")
    scenario.pay_with(again.begin_paying(), *islands)
    scenario.put_on_stack(again)
    colossus = scenario.resolve_top()

    assert colossus.zone is Zone.BATTLEFIELD
    assert colossus not in scenario.game.exile


def test_casting_the_warped_card_from_exile_without_announcing_warp_is_refused():
    """The `test_flashback.py` live-game defect, generalized to warp's own
    second half: CR 702.185b's exile permission is still tied to the warp
    keyword even though `pays_mana_cost=True` there (the printed mana cost
    *is* the right cost, unlike flashback) - a caster who never calls
    `use_keyword("Warp")` must still be refused, because the permission to
    cast from exile at all comes from the keyword, not from the coincidence
    that the cost happens to be right either way.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Island", "Island", "Island")
    casting = scenario.cast("Bygone Colossus")
    casting.use_keyword("Warp")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    exile_warped(scenario.game, scenario.resolve_top())
    alices_next_main(scenario)

    islands = scenario.untapped_sources(*["Island"] * 9, username="alice")
    again = scenario.cast("Bygone Colossus", from_zone=Zone.EXILE)
    assert again.total_cost.mana == ManaCost.parse("{9}")
    scenario.pay_with(again.begin_paying(), *islands)

    with pytest.raises(ValueError, match="Warp"):
        again.cast()
    again.cancel()

    assert scenario.find("Bygone Colossus", Zone.EXILE, "alice").zone is Zone.EXILE
    assert all(island.untapped for island in islands)


def test_an_unwarped_card_in_exile_cannot_be_cast_with_warp():
    """CR 601.3: the pile is what the permission is keyed on (CR 406.4)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", exile=["Bygone Colossus"], battlefield=["Island"] * 9)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Bygone Colossus", from_zone=Zone.EXILE)

    with pytest.raises(ValueError, match="not warped"):
        casting.use_keyword("Warp")


def test_a_card_cast_for_full_price_from_hand_is_not_warped():
    """CR 702.185c: a spell is warped only if it was cast for its warp cost."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    islands = scenario.untapped_sources(*["Island"] * 9, username="alice")
    casting = scenario.cast("Bygone Colossus")
    scenario.pay_with(casting.begin_paying(), *islands)
    scenario.put_on_stack(casting)

    assert casting.keyword_used is None
    assert scenario.resolve_top().zone is Zone.BATTLEFIELD


# -- what is not modelled ---------------------------------------------------


def test_the_end_step_exiles_a_warped_permanent_on_its_own():
    scenario = board(lands=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Island", "Island", "Island")
    casting = scenario.cast("Bygone Colossus")
    casting.use_keyword("Warp")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    colossus = scenario.resolve_top()

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert colossus.zone is Zone.EXILE
