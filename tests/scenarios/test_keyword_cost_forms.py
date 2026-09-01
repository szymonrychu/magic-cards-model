"""A keyword cost printed after an em dash: `Keyword—cost.` (CR 702.1a).

CR 702.1a: "If an effect refers to a '[keyword ability] cost,' it refers only to
the variable costs for that keyword." WOTC prints that variable cost two ways: a
space when it is mana (`Flashback {2}{R}`) and an em dash when it is anything
else (`Flashback—Sacrifice a Mountain.`).

The em-dash form used to fall through the keyword parser entirely, because the
line ends in a full stop and a full stop disqualified a keyword line. Every one
of them became an unread `StaticAbility` and did nothing.

The five shapes in the pool are here in one place, because the parse is the same
mechanic even though the keywords are not - CR 702.74a evoke replaces the mana
cost, CR 702.120a escalate is added to it, CR 702.29a cycling is an activated
ability that never casts the card at all. What each one *does* lives in its own
file; this one is about reading the line.

The em dash is also what tells the form apart from a CR 207.2c ability word,
which prints spaces around its dash. Both are checked, because reading `Channel
— {1}{G}, Discard this card: ...` as a keyword cost would be the same bug
pointing the other way.
"""

import pytest

from magic_cards_model.machines.abilities import AbilityKind, keyword_ability, parse_abilities
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.machines.cost import total_cost_for_phrase
from tests.cards import card

# -- the five printed shapes ------------------------------------------------


@pytest.mark.parametrize(
    ("name", "keyword", "cost"),
    [
        ("Grief", "Evoke", "Exile a black card from your hand"),
        ("Solitude", "Evoke", "Exile a white card from your hand"),
        ("Lava Dart", "Flashback", "Sacrifice a Mountain"),
        ("Street Wraith", "Cycling", "Pay 2 life"),
        ("Collective Brutality", "Escalate", "Discard a card"),
    ],
)
def test_every_em_dash_cost_in_the_pool_is_read(name, keyword, cost):
    ability = keyword_ability(card(name), keyword)

    assert ability is not None
    assert ability.kind is AbilityKind.KEYWORD
    assert ability.cost == cost
    assert ability.em_dash is True


def test_a_number_in_front_of_the_dash_is_kept_separately():
    """Living End prints `Suspend 3—{2}{B}{B}`: a count and a mana cost."""
    suspend = keyword_ability(card("Living End"), "Suspend")

    assert suspend is not None
    assert suspend.count == 3
    assert suspend.cost == "{2}{B}{B}"
    assert suspend.cost_is_mana is True


# -- what the dash must not swallow -----------------------------------------


def test_an_ability_word_is_not_read_as_a_keyword_cost():
    """CR 207.2c: `Channel — {1}{G}, Discard this card: ...` is an activated ability.

    Channel is on Boseiju's Scryfall `keywords` list, so only the spaces around
    the dash keep this line from reading as `Channel` costing `{1}{G}, Discard
    this card: Destroy target ...`.
    """
    abilities = parse_abilities(card("Boseiju, Who Endures"))
    channel = next(a for a in abilities if a.ability_word == "Channel")

    assert channel.kind is AbilityKind.ACTIVATED
    assert keyword_ability(card("Boseiju, Who Endures"), "Channel") is None


def test_a_landfall_ability_word_still_parses_as_a_trigger():
    (landfall,) = parse_abilities(card("Steppe Lynx"))

    assert landfall.kind is AbilityKind.TRIGGERED
    assert landfall.ability_word == "Landfall"


def test_a_sentence_starting_with_a_keyword_is_not_a_keyword_line():
    """`Flying creatures you control get +1/+1.` is a static ability."""
    abilities = parse_abilities(card("Dragon's Rage Channeler"))

    assert any(a.kind is AbilityKind.STATIC for a in abilities)


# -- turning the phrase into something payable ------------------------------


@pytest.mark.parametrize(
    ("phrase", "rendered"),
    [
        ("Exile a black card from your hand", "Exile a black card from your hand"),
        ("Sacrifice a Mountain", "Sacrifice a Mountain"),
        ("Pay 2 life", "Pay 2 life"),
        ("Discard a card", "Discard a card"),
        ("{2}{R}", "{2}{R}"),
    ],
)
def test_a_printed_cost_phrase_becomes_a_total_cost(phrase, rendered):
    total = total_cost_for_phrase(phrase, "alice")

    assert total is not None
    assert str(total) == rendered


def test_a_phrase_the_parser_cannot_read_is_refused_rather_than_guessed():
    """A cost that cannot be read has to say so, not charge nothing."""
    assert total_cost_for_phrase("Sacrifice a permanent with the highest mana value") is None


# -- the ones that parse and still have nowhere to go -----------------------


def test_a_card_with_cycling_can_be_cycled():
    """CR 702.29a, played for real: the keyword line becomes an ability that runs.

    "Cycling is an activated ability that functions only while the card with
    cycling is in a player's hand. 'Cycling [cost]' means '[Cost], Discard this
    card: Draw a card.'" Street Wraith's cost is "Pay 2 life", so the whole
    activation is: pay 2 life, discard the Wraith, draw the Mountain.

    `scenario.cycle` is the door rather than `scenario.activate`, because
    `Game.begin_activating` reads the abilities of a *battlefield permanent*
    and a card in hand has none of those. CR 702.29b is the reason that is not
    a contradiction: the ability "continues to exist while the object is on the
    battlefield and in all other zones", so the zone gates when it may be
    activated, not whether it exists.
    """
    from magic_cards_model.machines import Step
    from magic_cards_model.models import Zone
    from tests.scenarios.harness import Scenario

    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Street Wraith"], library=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wraith = scenario.find("Street Wraith", Zone.HAND)

    scenario.cycle(wraith)

    assert wraith.zone is Zone.GRAVEYARD, "discarding it is part of the cost"
    assert scenario.player("alice").life == 18
    assert [state.name for state in scenario.player("alice").hand] == ["Mountain"]


def test_a_card_with_suspend_offers_a_way_to_cast_it():
    """The parsed `Suspend 3—{2}{B}{B}` line becomes a real, payable offer.

    Not through `keyword_cast_options`, which is empty for Living End on
    purpose. CR 702.62a: "Suspend is a keyword that represents three
    abilities. The first is a static ability that functions while the card
    with suspend is in a player's hand. The second and third are triggered
    abilities that function in the exile zone." Only the *first* of the three
    is the hand-side offer, and it is not a permission to cast - it is
    CR 116.2f's special action: "A player who has a card with suspend in their
    hand may exile that card. This is a special action." The cast comes later,
    out of the third ability, once the last time counter comes off a card
    CR 702.62b calls suspended.

    So the two things this file's parse actually feeds are
    `MarkedExile.suspend` - which charges exactly the `{2}{B}{B}` read off the
    line and hands out exactly the N=3 time counters read off it - and
    `finish_suspend`, which is where the cast permission is minted when that
    third ability fires. Putting suspend in the static `KeywordCastOption`
    table instead would mint the permission twice and hold CR 702.62a's window
    open far wider than the rule does; `docs/engine-coverage.md` records the
    choice. `tests/scenarios/test_suspend.py` plays the whole keyword out.
    """
    from magic_cards_model.machines import Step
    from magic_cards_model.machines.casting import (
        MarkedExile,
        finish_suspend,
        remove_suspend_time_counter,
    )
    from magic_cards_model.models import Zone
    from magic_cards_model.models.card_state import Counter, ExileMarker
    from tests.scenarios.harness import Scenario

    assert keyword_cast_options(card("Living End")) == []

    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Living End"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    living_end = scenario.find("Living End", Zone.HAND)

    action = MarkedExile.suspend(scenario.game, living_end, "alice")

    # The count and the cost are the ones this file proved were read off the
    # printed line, now carried into the special action itself (CR 116.2f).
    assert action.time_counters == 3
    assert str(action.cost) == "{2}{B}{B}"
    assert action.marker is ExileMarker.SUSPENDED

    payment = action.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"))
    action.take()

    suspended = scenario.find("Living End", Zone.EXILE)
    assert suspended.counter_count(Counter.TIME) == 3

    for _ in range(3):
        remove_suspend_time_counter(scenario.game, suspended)

    # CR 702.62a's third ability: "you may play it without paying its mana
    # cost if able" - the offer this card has no other route to, since its
    # printed mana cost is blank (CR 118.6's unpayable cost).
    permission = finish_suspend(scenario.game, suspended)
    assert permission is not None
    assert permission.pays_mana_cost is False
