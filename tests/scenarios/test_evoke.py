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

The triggered half is the rest of CR 702.74a: "When this permanent enters, if
its evoke cost was paid, its controller sacrifices it." It is an ordinary
enters-the-battlefield trigger (CR 603.6a) with an intervening *if* (CR 603.4),
not a replacement effect and not a delayed trigger - so the creature really
arrives, its own enters triggers happen, and only then is it sacrificed
(CR 701.21a). A live game had it stay on the battlefield for ever, because
nothing wrote the keyword out as a trigger at all.

Wistfulness is where all of it meets: its two enters triggers are gated on
which mana was spent (CR 601.2h), its evoke cost is hybrid, and the colours
chosen to pay it decide which of the two happens.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import keyword_ability
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
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
    # CR 601.2a already moved the Grief being cast to the stack, so the hand
    # holds only the other copy - which is the one being exiled to evoke it.
    fodder = scenario.player("alice").hand[0]
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
    casting.use_keyword("Evoke", choosing=[scenario.player("alice").hand[0]])

    with pytest.raises(ValueError, match="only one alternative cost"):
        casting.use_keyword("Evoke")


def test_a_card_without_evoke_has_no_evoke_option():
    scenario = board(hand=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Grizzly Bears")

    with pytest.raises(ValueError, match="no Evoke ability"):
        casting.use_keyword("Evoke")


# -- the sacrifice: CR 702.74a's triggered half ------------------------------


def settle(scenario: Scenario) -> None:
    """Put every waiting trigger on the stack and resolve the lot (CR 603.3)."""
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def test_an_evoked_creature_is_sacrificed_when_it_enters():
    """CR 702.74a's second ability: "When this permanent enters, if its evoke
    cost was paid, its controller sacrifices it."

    The whole point of evoking a creature: it arrives, its enters trigger
    happens, and then it is gone. A live game had it stay on the battlefield.
    """
    scenario = board(hand=["Grief", "Grief"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _, fodder = scenario.player("alice").hand
    casting = scenario.cast("Grief")
    casting.use_keyword("Evoke", choosing=[fodder])
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    grief = scenario.resolve_top()

    assert grief.zone is Zone.BATTLEFIELD  # it enters first (CR 603.6a)
    settle(scenario)

    assert grief.zone is Zone.GRAVEYARD
    assert grief in scenario.player("alice").cards_in(Zone.GRAVEYARD)


def test_the_sacrifice_is_a_trigger_on_the_stack_not_part_of_entering():
    """CR 603.6a's trigger goes on the stack, so the creature is really there.

    This is what separates a trigger from a replacement effect (CR 614): an
    evoked creature exists on the battlefield with its own trigger waiting, and
    a player can respond to it.
    """
    scenario = board(hand=["Grief", "Grief"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Grief")
    casting.use_keyword("Evoke", choosing=[scenario.player("alice").hand[0]])
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    grief = scenario.resolve_top()
    scenario.game.put_triggers_on_stack()

    assert grief.zone is Zone.BATTLEFIELD
    # Two: Grief's own printed enters trigger and CR 702.74a's sacrifice. Both
    # are alice's, so CR 603.3b lets her order them - and either order ends the
    # same way, because the sacrifice does not undo the discard.
    assert scenario.stack_names().count("Grief's triggered ability") == 2


def test_a_hardcast_incarnation_is_not_sacrificed():
    """CR 603.4: the intervening *if* is false, so the ability never triggers.

    Grief's evoke cost was not paid, so nothing about CR 702.74a's second half
    applies - it is a 4/3 that stays.
    """
    scenario = board(hand=["Grief"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")
    casting = scenario.cast("Grief")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *swamps)
    scenario.put_on_stack(casting)
    grief = scenario.resolve_top()
    settle(scenario)

    assert grief.zone is Zone.BATTLEFIELD
    assert not scenario.game.intervening_if_notices


def test_a_creature_that_was_never_cast_is_not_sacrificed():
    """No `CastRecord` at all means its evoke cost was not paid (CR 601.2h).

    A reanimated or put-onto-the-battlefield incarnation has no evoke cost paid
    for it, and the clause is answerable - False - rather than unreadable.
    """
    scenario = board(hand=["Grief"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    grief = scenario.put_onto_battlefield("Grief")
    settle(scenario)

    assert grief.zone is Zone.BATTLEFIELD


def test_the_evoked_creature_dies_so_death_triggers_see_it():
    """CR 701.21a sacrifices it to its owner's graveyard, and CR 700.4 calls
    that dying - so a "whenever a creature dies" trigger fires off an evoke.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Grief", "Grief"], battlefield=["Blood Artist"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Blood Artist", ["bob"])
    scenario.choose_trigger_targets("Grief", ["bob"])

    casting = scenario.cast("Grief")
    casting.use_keyword("Evoke", choosing=[scenario.player("alice").hand[0]])
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    grief = scenario.resolve_top()
    settle(scenario)

    assert grief.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21


# -- Wistfulness: which mana was spent decides which trigger ----------------
#
# The evoke cost is hybrid, `{G/U}{G/U}`, and CR 107.4e lets the payer choose
# which half of each symbol to pay. That choice is what the two enters triggers
# read, so the same cast produces three different boards.


def wistfulness_board(*lands: str) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Wistfulness"],
            battlefield=list(lands),
            library=["Lightning Bolt", "Grizzly Bears", "Forest"],
        )
        .player("bob", battlefield=["Aether Spellbomb"])
        .build()
    )


def evoke_wistfulness(scenario: Scenario, *lands) -> object:
    casting = scenario.cast("Wistfulness")
    casting.use_keyword("Evoke")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *lands)
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_evoking_wistfulness_for_two_green_exiles_and_then_sacrifices():
    """All three of CR 702.74a's and the card's own abilities, in one cast.

    CR 601.2h records green twice, so the {G}{G} intervening *if* holds and the
    {U}{U} one does not; the evoke trigger fires regardless of which colours
    paid it.
    """
    scenario = wistfulness_board("Forest", "Forest")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest")

    wistfulness = evoke_wistfulness(scenario, *forests)
    spellbomb = scenario.find("Aether Spellbomb", Zone.BATTLEFIELD, "bob")
    settle(scenario)

    assert spellbomb.zone is Zone.EXILE
    assert wistfulness.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == 0


def test_evoking_wistfulness_for_two_blue_draws_and_discards_instead():
    """The other half of the same hybrid cost, and the other intervening *if*."""
    scenario = wistfulness_board("Island", "Island")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources("Island", "Island")

    wistfulness = evoke_wistfulness(scenario, *islands)
    spellbomb = scenario.find("Aether Spellbomb", Zone.BATTLEFIELD, "bob")
    drawn = scenario.top_of_library(2)
    scenario.will_discard(drawn[0])
    settle(scenario)

    assert spellbomb.zone is Zone.BATTLEFIELD
    assert drawn[0].zone is Zone.GRAVEYARD
    assert drawn[1].zone is Zone.HAND
    assert wistfulness.zone is Zone.GRAVEYARD


def test_paying_one_of_each_colour_enables_neither_trigger():
    """CR 603.4: neither {G}{G} nor {U}{U} was spent, so neither ability
    triggers - but the evoke sacrifice still does.
    """
    scenario = wistfulness_board("Forest", "Island")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest, island = scenario.untapped_sources("Forest", "Island")

    wistfulness = evoke_wistfulness(scenario, forest, island)
    spellbomb = scenario.find("Aether Spellbomb", Zone.BATTLEFIELD, "bob")
    settle(scenario)

    assert spellbomb.zone is Zone.BATTLEFIELD
    assert len(scenario.player("alice").hand) == 0
    assert wistfulness.zone is Zone.GRAVEYARD


def test_the_mana_spent_is_recorded_against_the_evoke_cost_not_the_mana_cost():
    """CR 601.2h pays the *total* cost, which an alternative cost replaced.

    Wistfulness's printed cost is `{3}{G/U}{G/U}`; evoking it spends two mana,
    and that is what the record holds - the generic {3} is not paid at all.
    """
    scenario = wistfulness_board("Forest", "Forest")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest")

    wistfulness = evoke_wistfulness(scenario, *forests)
    record = scenario.game.cast_record(wistfulness)

    assert record.keyword == "Evoke"
    assert record.mana_of_color_spent(Color.GREEN) == 2
    assert record.mana_of_color_spent(Color.BLUE) == 0
