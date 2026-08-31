"""Delve: exiling a graveyard instead of spending mana (CR 702.66).

CR 702.66a: "Delve is a static ability that functions while the spell with
delve is on the stack. 'Delve' means 'For each generic mana in this spell's
total cost, you may exile a card from your graveyard rather than pay that
mana.'" Treasure Cruise prints it as "Each card you exile from your graveyard
while casting this spell pays for {1}."

The wording is narrower than convoke's in exactly one way, and it is the
corner case worth a test of its own: delve reaches **generic mana only**. There
is no "of that color" half, so Treasure Cruise's `{U}` is never delved for, and
a graveyard of seven cards still leaves one blue source needed.

CR 702.66b: "The delve ability isn't an additional or alternative cost and
applies only after the total cost of the spell with delve is determined" - the
same shape as convoke (CR 702.51b), and the reason both go through the same
substitution machinery. CR 702.66c makes multiple instances redundant.

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.objects_as_costs import delve
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def cruise_board(graveyard: int = 7, lands: int = 1) -> Scenario:
    """Treasure Cruise is `{7}{U}` with delve: seven generic symbols' worth in
    one `{7}`, and one `{U}` that delve cannot touch."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Treasure Cruise"],
            library=["Forest", "Forest", "Forest", "Forest"],
            graveyard=["Mountain"] * graveyard,
            battlefield=["Island"] * lands,
        )
        .player("bob")
    )


def graveyard_of(scenario, username="alice"):
    return list(scenario.player(username).graveyard)


def test_seven_exiled_cards_and_one_island_cast_treasure_cruise():
    """The whole point of the keyword: `{7}{U}` for one blue mana."""
    scenario = cruise_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    binned = graveyard_of(scenario)

    casting = scenario.cast("Treasure Cruise")
    payment = casting.begin_paying()
    delve(payment, casting.spell, *binned)

    assert str(payment.mana_owed) == "{U}"
    scenario.pay_with(payment, *scenario.untapped_sources("Island"))
    spell = scenario.put_on_stack(casting)

    assert spell.zone is Zone.STACK
    assert graveyard_of(scenario) == []
    assert all(card.zone is Zone.EXILE for card in binned)


def test_an_empty_graveyard_delves_for_nothing():
    """CR 702.66a offers cards "from your graveyard"; with none there the
    total cost is untouched and the spell simply costs `{7}{U}`."""
    scenario = cruise_board(graveyard=0).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Treasure Cruise")
    payment = casting.begin_paying()
    delve(payment, casting.spell)  # nothing to exile

    assert str(payment.mana_owed) == "{7}{U}"
    with pytest.raises(ValueError, match="cannot pay"):
        payment.pay()


def test_a_partial_graveyard_delves_only_as_far_as_it_goes():
    """Three cards take `{7}{U}` down to `{4}{U}` - and no further."""
    scenario = cruise_board(graveyard=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    binned = graveyard_of(scenario)

    casting = scenario.cast("Treasure Cruise")
    payment = casting.begin_paying()
    delve(payment, casting.spell, *binned)

    assert str(payment.mana_owed) == "{4}{U}"


def test_delve_is_not_a_cost_reduction():
    """CR 702.66b: the total cost stays `{7}{U}`; only what pays part of it
    changes. Anything reading the spell's cost sees the printed number."""
    scenario = cruise_board(graveyard=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    binned = graveyard_of(scenario)

    casting = scenario.cast("Treasure Cruise")
    payment = casting.begin_paying()
    delve(payment, casting.spell, *binned)

    assert str(payment.cost) == "{7}{U}"
    assert str(payment.mana_owed) == "{4}{U}"


def test_delve_cannot_pay_the_coloured_symbol():
    """CR 702.66a is generic-only: unlike convoke (CR 702.51a) it has no
    "of that color" half, so a full graveyard never pays Treasure Cruise's
    `{U}` and a player with no blue source cannot cast it at all."""
    scenario = cruise_board(graveyard=9, lands=0).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    binned = graveyard_of(scenario)

    casting = scenario.cast("Treasure Cruise")
    payment = casting.begin_paying()
    delve(payment, casting.spell, *binned[:7])

    assert str(payment.mana_owed) == "{U}"
    with pytest.raises(ValueError, match="cannot pay"):
        payment.pay()


def test_more_cards_than_the_cost_has_generic_mana_is_refused():
    """CR 702.66a bounds itself to "each generic mana **in this spell's total
    cost**". An eighth card offered to `{7}{U}` has nothing to pay, so it is
    turned away rather than exiled for nothing."""
    scenario = cruise_board(graveyard=9).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    binned = graveyard_of(scenario)

    casting = scenario.cast("Treasure Cruise")
    payment = casting.begin_paying()
    delve(payment, casting.spell, *binned[:7])

    with pytest.raises(ValueError, match="has no"):
        delve(payment, casting.spell, binned[7])

    assert binned[7].zone is Zone.GRAVEYARD


def test_the_same_card_cannot_delve_twice():
    """One card, one generic symbol."""
    scenario = cruise_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    binned = graveyard_of(scenario)

    casting = scenario.cast("Treasure Cruise")
    payment = casting.begin_paying()
    delve(payment, casting.spell, binned[0])

    with pytest.raises(ValueError, match="already paying"):
        delve(payment, casting.spell, binned[0])


def test_an_opponents_graveyard_cannot_be_delved():
    """CR 702.66a: "a card from **your** graveyard"."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Treasure Cruise"], battlefield=["Island"])
        .player("bob", graveyard=["Mountain", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = list(scenario.player("bob").graveyard)

    casting = scenario.cast("Treasure Cruise")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="does not control"):
        delve(payment, casting.spell, theirs[0])

    assert theirs[0].zone is Zone.GRAVEYARD


def test_a_card_on_the_battlefield_cannot_be_delved():
    """The offer names the graveyard, and nothing else is in it."""
    scenario = cruise_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")

    casting = scenario.cast("Treasure Cruise")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="delve spends objects in the graveyard"):
        delve(payment, casting.spell, island)


def test_nothing_is_exiled_until_the_cost_is_paid():
    """CR 601.2h: the exiling happens as the total cost is paid, not as delve
    is announced - so an open payment has moved nothing."""
    scenario = cruise_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    binned = graveyard_of(scenario)

    casting = scenario.cast("Treasure Cruise")
    payment = casting.begin_paying()
    delve(payment, casting.spell, *binned)

    assert all(card.zone is Zone.GRAVEYARD for card in binned)


def test_cancelling_the_cast_returns_the_delved_cards_to_the_graveyard():
    """CR 733.1: "the entire action is reversed and any payments already made
    are canceled"."""
    scenario = cruise_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    binned = graveyard_of(scenario)

    casting = scenario.cast("Treasure Cruise")
    payment = casting.begin_paying()
    delve(payment, casting.spell, *binned)
    scenario.pay_with(payment, *scenario.untapped_sources("Island"))
    assert all(card.zone is Zone.EXILE for card in binned)

    casting.cancel()

    assert all(card.zone is Zone.GRAVEYARD for card in binned)
    assert len(graveyard_of(scenario)) == 7


def test_delve_pays_the_generic_mana_that_x_became():
    """Logic Knot is `{X}{U}{U}`. CR 107.3a fixes X as the spell is announced
    and it becomes part of the total cost before CR 702.66a looks at it, so
    delve pays for X the same as for any other generic mana."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Logic Knot"],
            graveyard=["Mountain", "Mountain", "Mountain"],
            battlefield=["Island", "Island"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    binned = graveyard_of(scenario)

    casting = scenario.cast("Logic Knot", targets=[bolt])
    casting.determine_cost(x_value=3)
    payment = casting.begin_paying()

    assert str(payment.cost) == "{3}{U}{U}"
    delve(payment, casting.spell, *binned)
    assert str(payment.mana_owed) == "{U}{U}"

    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island"))
    scenario.put_on_stack(casting)

    assert all(card.zone is Zone.EXILE for card in binned)


def test_delve_with_x_at_zero_has_only_the_printed_generic_to_pay():
    """Logic Knot at X=0 is `{U}{U}` - all coloured, and CR 702.66a's
    generic-only offer has nothing at all to take."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Logic Knot"],
            graveyard=["Mountain", "Mountain"],
            battlefield=["Island", "Island"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    binned = graveyard_of(scenario)

    casting = scenario.cast("Logic Knot", targets=[bolt])
    casting.determine_cost(x_value=0)
    payment = casting.begin_paying()

    assert str(payment.cost) == "{U}{U}"
    with pytest.raises(ValueError, match="has no"):
        delve(payment, casting.spell, binned[0])


def test_a_spell_without_delve_refuses_the_offer():
    """CR 702.66a functions "while the spell **with delve**" is on the stack."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], graveyard=["Mountain"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    binned = graveyard_of(scenario)

    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="does not have delve"):
        delve(payment, casting.spell, binned[0])


def test_treasure_cruise_resolves_and_draws_three_after_delving():
    """The keyword is only useful if the spell still works: `{7}{U}` cast off a
    graveyard and one Island, resolving into three cards."""
    scenario = cruise_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    binned = graveyard_of(scenario)
    before = len(scenario.player("alice").hand)

    casting = scenario.cast("Treasure Cruise")
    payment = casting.begin_paying()
    delve(payment, casting.spell, *binned)
    scenario.pay_with(payment, *scenario.untapped_sources("Island"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    # The Cruise left the hand, and three cards came in.
    assert len(scenario.player("alice").hand) == before - 1 + 3
