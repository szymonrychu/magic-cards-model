"""Evoke: CR 702.74a, and the `Keyword—cost.` form its cost is printed in.

CR 702.74a: "Evoke represents two abilities: a static ability that functions in
any zone from which the card with evoke can be cast and a triggered ability that
functions on the battlefield."

The static half is an alternative cost (CR 118.9): pay it *rather than* the
spell's mana cost, which is why Grief reaches the battlefield off an empty
board. CR 118.9a allows only one alternative cost per spell, and CR 118.9c
leaves the printed mana cost alone - an evoked Grief is still a four-mana card.

The Modern Horizons incarnation cycle prints its evoke cost after an em dash,
`Evoke—Exile a black card from your hand.`, which is the whole reason this file
exists: that line used to parse as a static ability and do nothing at all, so
evoke silently cost nothing and exiled nothing. Wistfulness prints the ordinary
`Evoke {G/U}{G/U}` form, so both are covered here.

The triggered half - the sacrifice when it enters - is not modelled; the xfail
at the bottom says so.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import keyword_ability
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import Scenario


def board(**kwargs) -> Scenario:
    return Scenario().manual_turn_based_actions().player("alice", **kwargs).player("bob")


# -- the em-dash cost is read at all ---------------------------------------


def test_the_em_dash_cost_is_read_as_the_keywords_cost():
    """`Evoke—Exile a black card from your hand.` is a CR 702 keyword line.

    WOTC prints an ability word with spaces around the dash (CR 207.2c,
    `Landfall — Whenever ...`) and a keyword cost without them. The space is the
    only thing telling the two apart, and getting it wrong turned every
    incarnation's evoke into an unread static ability.
    """
    evoke = keyword_ability(card("Grief"), "Evoke")

    assert evoke is not None
    assert evoke.cost == "Exile a black card from your hand"
    assert evoke.em_dash is True
    assert evoke.cost_is_mana is False


def test_the_mana_form_of_the_same_keyword_still_reads_as_mana():
    """Wistfulness prints `Evoke {G/U}{G/U}`, with no dash and no sentence."""
    evoke = keyword_ability(card("Wistfulness"), "Evoke")

    assert evoke is not None
    assert evoke.cost == "{G/U}{G/U}"
    assert evoke.em_dash is False
    assert evoke.cost_is_mana is True


def test_evoke_offers_a_cast_from_hand_that_replaces_the_mana_cost():
    """CR 702.74a's static half, as an option: hand, and no mana cost paid."""
    (option,) = keyword_cast_options(card("Grief"))

    assert option.keyword == "Evoke"
    assert option.zone is Zone.HAND
    assert option.pays_mana_cost is False
    assert option.understood is True


# -- paying it --------------------------------------------------------------


def test_evoking_grief_puts_it_on_the_battlefield_off_an_empty_board():
    """The alternative cost is the whole cost, so no land is needed (CR 118.9)."""
    scenario = board(hand=["Grief", "Grief"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _, fodder = scenario.player("alice").hand

    casting = scenario.cast("Grief")
    casting.use_keyword("Evoke", choosing=[fodder])
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    grief = scenario.resolve_top()

    assert grief.zone is Zone.BATTLEFIELD
    assert fodder.zone is Zone.EXILE
    assert fodder in scenario.game.exile


def test_the_printed_mana_cost_is_untouched_by_the_alternative_cost():
    """CR 118.9c: an alternative cost changes what is paid, not what is printed."""
    scenario = board(hand=["Grief", "Grief"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Grief")
    fodder = scenario.player("alice").hand[1]
    casting.use_keyword("Evoke", choosing=[fodder])

    assert casting.base_cost == ManaCost.parse("{2}{B}{B}")
    assert casting.total_cost.mana == ManaCost()
    assert casting.keyword_used == "Evoke"


def test_a_mana_evoke_cost_is_paid_with_mana():
    """Wistfulness evokes for `{G/U}{G/U}`, which is still an alternative cost."""
    scenario = board(hand=["Wistfulness"], battlefield=["Forest", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest, island = scenario.untapped_sources("Forest", "Island")
    casting = scenario.cast("Wistfulness")
    casting.use_keyword("Evoke")
    payment = casting.begin_paying()
    scenario.pay_with(payment, forest, island)
    scenario.put_on_stack(casting)

    assert scenario.resolve_top().zone is Zone.BATTLEFIELD
    assert casting.total_cost.mana.converted == 2


# -- the cost that cannot be paid -------------------------------------------


def test_a_card_of_the_wrong_colour_cannot_pay_griefs_evoke():
    """CR 118.3: a black card is asked for, so a red one does not pay it."""
    scenario = board(hand=["Grief", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = scenario.find("Lightning Bolt", Zone.HAND)
    casting = scenario.cast("Grief")
    casting.use_keyword("Evoke", choosing=[bolt])
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="not B"):
        payment.pay()
    assert bolt.zone is Zone.HAND


def test_evoke_with_nothing_to_exile_refuses_to_be_paid():
    """CR 118.3: the resources have to be there before anything is spent."""
    scenario = board(hand=["Grief"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Grief")
    casting.use_keyword("Evoke")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="needs 1 card"):
        payment.pay()


def test_a_green_incarnation_wants_a_green_card_not_a_black_one():
    """Each incarnation names its own colour; the parser reads it off the card."""
    scenario = board(hand=["Endurance", "Grief"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    grief = scenario.find("Grief", Zone.HAND)
    casting = scenario.cast("Endurance")
    casting.use_keyword("Evoke", choosing=[grief])
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="not G"):
        payment.pay()


def test_a_card_already_in_the_graveyard_cannot_pay_a_from_your_hand_cost():
    """The cost says "from your hand", so a card anywhere else does not pay it."""
    scenario = board(hand=["Grief"], graveyard=["Grief"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    buried = scenario.find("Grief", Zone.GRAVEYARD)
    casting = scenario.cast("Grief")
    casting.use_keyword("Evoke", choosing=[buried])
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="graveyard"):
        payment.pay()


# -- the rewind -------------------------------------------------------------


def test_cancelling_an_evoked_casting_puts_the_exiled_card_back_in_hand():
    """CR 733.1: the whole announcement is reversed and payments are cancelled."""
    scenario = board(hand=["Grief", "Grief"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    cast, fodder = scenario.player("alice").hand
    casting = scenario.cast("Grief")
    casting.use_keyword("Evoke", choosing=[fodder])
    casting.begin_paying().pay()
    assert fodder.zone is Zone.EXILE

    casting.cancel()

    assert fodder.zone is Zone.HAND
    assert fodder in scenario.player("alice").hand
    assert fodder not in scenario.game.exile
    assert cast.zone is Zone.HAND


# -- what evoke is not ------------------------------------------------------


def test_evoke_does_not_cast_from_the_graveyard():
    """CR 702.74a's static ability functions where the card can be cast from.

    That is the hand for a creature card (CR 302.1). Nothing about evoke lets
    Grief be cast out of a graveyard, so asking says so rather than allowing it.
    """
    scenario = board(graveyard=["Grief", "Grief"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Grief", from_zone=Zone.GRAVEYARD)

    with pytest.raises(ValueError, match="from the hand"):
        casting.use_keyword("Evoke")


def test_only_one_alternative_cost_may_be_applied():
    """CR 118.9a: one alternative cost per spell, so evoking twice is an error."""
    scenario = board(hand=["Grief", "Grief"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Grief")
    casting.use_keyword("Evoke", choosing=[scenario.player("alice").hand[1]])

    with pytest.raises(ValueError, match="only one alternative cost"):
        casting.use_keyword("Evoke")


def test_a_card_without_evoke_has_no_evoke_option():
    scenario = board(hand=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Grizzly Bears")

    with pytest.raises(ValueError, match="no Evoke ability"):
        casting.use_keyword("Evoke")


# -- the half that is not modelled ------------------------------------------


@pytest.mark.xfail(
    reason=(
        "CR 702.74a's second half is a triggered ability - the permanent is "
        "sacrificed when it enters if its evoke cost was paid. Nothing creates "
        "that trigger: machines/triggers.py matches printed trigger text and the "
        "sacrifice is not printed on the card, it comes from the keyword. "
        "Registering it needs machines/triggers.py and machines/effects.py."
    ),
    strict=True,
)
def test_an_evoked_creature_is_sacrificed_when_it_enters():
    scenario = board(hand=["Grief", "Grief"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    cast, fodder = scenario.player("alice").hand
    casting = scenario.cast("Grief")
    casting.use_keyword("Evoke", choosing=[fodder])
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    grief = scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert grief.zone is Zone.GRAVEYARD
