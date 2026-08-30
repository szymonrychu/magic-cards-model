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


@pytest.mark.xfail(
    reason=(
        "CR 702.29a: 'Cycling [cost]' means '[Cost], Discard this card: Draw a "
        "card.' - an activated ability that functions only in the hand. Nothing "
        "expands the keyword into that ability, and Game.begin_activating only "
        "activates abilities of battlefield permanents, so a card with cycling "
        "cannot be cycled. Needs models/game.py, which this change does not own."
    ),
    strict=True,
)
def test_a_card_with_cycling_can_be_cycled():
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

    scenario.activate(wraith)

    assert wraith.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 18


@pytest.mark.xfail(
    reason=(
        "Suspend is listed as not modelled in docs/engine-coverage.md. The cost "
        "and the count are parsed off `Suspend 3—{2}{B}{B}`, but CR 702.62a "
        "makes suspend a static ability plus two triggered abilities, and "
        "CR 116.2f exiles the card with time counters through a special action. "
        "The annotated exile would carry it; the upkeep triggers that count the "
        "time counters down and then cast it do not exist."
    ),
    strict=True,
)
def test_a_card_with_suspend_offers_a_way_to_cast_it():
    assert keyword_cast_options(card("Living End"))
