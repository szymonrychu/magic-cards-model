"""Look at the top N cards of your library, put a printed number of them into
your hand and the rest somewhere else - `_merge_look_top_split_hand_graveyard_
clauses` in `machines/effects.py`, read for any count, not only "one".

Stock Up ("Look at the top five cards of your library. Put two of them into
your hand and the rest on the bottom of your library in any order.") resolved
with no choice at all in a live game: the hand clause only read "one", so
`effect_for` returned nothing and the spell went to the graveyard. Dovin, Grand
Arbiter's -7 ("Look at the top ten cards of your library. Put three of them
into your hand and the rest on the bottom of your library in a random order.")
is in neither deck pool and proves the count is read, not fitted: a different
number, a different rest order, on a loyalty ability rather than a spell. It is
the only printing on Scryfall whose count is neither one nor two
(`o:"put three of them into your hand"`).

Every CR number below was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 401.4** - "If an effect puts two or more cards in a specific position in
  a library at the same time, the owner of those cards may arrange them in any
  order."
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible." Two cards to hand is the only legal size of answer.
- **CR 609.3** - "If an effect attempts to do something impossible, it does
  only as much as possible." A library shorter than the look or the count gives
  what it has.
- **CR 606.4** - a loyalty ability's cost is the loyalty counters removed, so
  Dovin is staged with enough counters to pay -7.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import CardSplit, DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _hand_pick(scenario, *cards, source: str) -> None:
    """The look-and-split question's `moved` pile is the cards for the hand."""
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.SCRY,
            value=CardSplit(moved=tuple(card.id for card in cards)),
            source=source,
        )
    )


def _stock_up_board(library: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice", hand=["Stock Up"], library=library, battlefield=["Island", "Island", "Island"]
        )
        .player("bob")
    )


def _cast_stock_up(scenario) -> None:
    scenario.cast_and_resolve("Stock Up", *scenario.untapped_sources("Island", "Island", "Island"))


def _split_question(scenario, source: str):
    (question,) = [
        d for d in scenario.questions_asked() if d.kind is DecisionKind.SCRY and d.source == source
    ]
    return question


def test_stock_up_puts_two_into_hand_and_three_on_the_bottom_in_the_chosen_order():
    scenario = _stock_up_board(
        ["Mountain", "Forest", "Lightning Bolt", "Swamp", "Counterspell", "Plains"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountain, forest, bolt, swamp, counterspell = scenario.top_of_library(5, "alice")
    _hand_pick(scenario, bolt, counterspell, source="Stock Up")
    scenario.will_choose_cards(swamp, mountain, forest, source="Stock Up")

    _cast_stock_up(scenario)

    question = _split_question(scenario, "Stock Up")
    assert len(question.cards) == 5
    assert question.amount == 2
    assert question.exact is True
    assert question.moved_label == "your hand"
    assert bolt.zone is Zone.HAND and counterspell.zone is Zone.HAND
    assert [state.name for state in alice.library] == ["Plains", "Swamp", "Mountain", "Forest"]
    scenario.assert_in_exactly_one_zone(mountain, forest, bolt, swamp, counterspell)


def test_stock_up_with_four_cards_left_looks_at_four_and_still_takes_two():
    scenario = _stock_up_board(["Mountain", "Forest", "Lightning Bolt", "Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountain, forest, bolt, swamp = scenario.top_of_library(4, "alice")
    _hand_pick(scenario, forest, swamp, source="Stock Up")
    scenario.will_choose_cards(bolt, mountain, source="Stock Up")

    _cast_stock_up(scenario)

    question = _split_question(scenario, "Stock Up")
    assert len(question.cards) == 4
    assert question.amount == 2
    assert forest.zone is Zone.HAND and swamp.zone is Zone.HAND
    assert [state.name for state in alice.library] == ["Lightning Bolt", "Mountain"]


def test_stock_up_with_one_card_left_puts_that_card_into_hand():
    """CR 609.3: two cannot be taken from one, so the one is - and CR 608.2d:
    the one card is the only legal answer, so nothing is asked about it."""
    scenario = _stock_up_board(["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (bolt,) = scenario.top_of_library(1, "alice")

    _cast_stock_up(scenario)

    assert bolt.zone is Zone.HAND
    assert alice.library == []
    assert [q for q in scenario.questions_asked() if q.source == "Stock Up"] == []


def test_stock_up_with_an_empty_library_moves_nothing_and_is_not_refused():
    """CR 609.3: nothing to look at, nothing to take."""
    scenario = _stock_up_board([]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_stock_up(scenario)

    alice = scenario.player("alice")
    assert alice.hand == []
    assert alice.library == []
    assert scenario.find("Stock Up", Zone.GRAVEYARD, "alice") is not None


def test_stock_up_with_an_empty_library_asks_no_question():
    """CR 608.2d: there is nothing to choose among when nothing was looked
    at, so no question is put to the controller (compare CR 701.22b's "scry
    0" - no event). A human handed this question would see an empty prompt
    with nothing to answer."""
    scenario = _stock_up_board([]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_stock_up(scenario)

    assert [q for q in scenario.questions_asked() if q.source == "Stock Up"] == []


def test_stock_up_with_exactly_two_cards_takes_both_and_asks_no_question():
    """Library holds exactly the printed number (two): both are forced into
    hand, nothing is left to order on the bottom, so neither the split
    question nor the bottom-order question is asked."""
    scenario = _stock_up_board(["Lightning Bolt", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt, mountain = scenario.top_of_library(2, "alice")

    _cast_stock_up(scenario)

    assert bolt.zone is Zone.HAND and mountain.zone is Zone.HAND
    assert scenario.player("alice").library == []
    assert [q for q in scenario.questions_asked() if q.source == "Stock Up"] == []


def test_stock_up_refuses_one_card_for_hand():
    scenario = _stock_up_board(
        ["Mountain", "Forest", "Lightning Bolt", "Swamp", "Counterspell"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.top_of_library(1, "alice")
    _hand_pick(scenario, mountain, source="Stock Up")

    with pytest.raises(ValueError, match=r"exactly 2 card\(s\) must be chosen.*\(CR 608\.2d\)"):
        _cast_stock_up(scenario)


def test_stock_up_refuses_three_cards_for_hand():
    scenario = _stock_up_board(
        ["Mountain", "Forest", "Lightning Bolt", "Swamp", "Counterspell"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain, forest, bolt = scenario.top_of_library(3, "alice")
    _hand_pick(scenario, mountain, forest, bolt, source="Stock Up")

    with pytest.raises(ValueError, match=r"exactly 2 card\(s\) must be chosen.*\(CR 608\.2d\)"):
        _cast_stock_up(scenario)


def test_an_unscripted_stock_up_still_takes_exactly_two():
    """Not optional, so the default answer is a legal split."""
    scenario = _stock_up_board(["Mountain", "Forest", "Lightning Bolt", "Swamp", "Plains"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_stock_up(scenario)

    assert len(scenario.player("alice").hand) == 2
    assert len(scenario.player("alice").library) == 3


def test_anticipate_still_asks_for_exactly_one():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Anticipate"],
            library=["Mountain", "Forest", "Lightning Bolt", "Island"],
            battlefield=["Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountain, forest, bolt = scenario.top_of_library(3, "alice")
    _hand_pick(scenario, bolt, source="Anticipate")
    scenario.will_choose_cards(forest, mountain, source="Anticipate")

    scenario.cast_and_resolve("Anticipate", *scenario.untapped_sources("Island", "Island"))

    question = _split_question(scenario, "Anticipate")
    assert question.amount == 1
    assert question.exact is True
    assert bolt.zone is Zone.HAND
    assert [state.name for state in alice.library] == ["Island", "Forest", "Mountain"]


def test_anticipate_with_an_empty_library_asks_no_question():
    """CR 608.2d/701.22b: nothing was looked at, so nothing is asked."""
    scenario = (
        Scenario()
        .player("alice", hand=["Anticipate"], library=[], battlefield=["Island", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Anticipate", *scenario.untapped_sources("Island", "Island"))

    alice = scenario.player("alice")
    assert alice.hand == []
    assert alice.library == []
    assert [q for q in scenario.questions_asked() if q.source == "Anticipate"] == []


def test_anticipate_with_one_card_left_asks_no_question():
    """CR 609.3/608.2d: the one card left can only go to hand - the only
    legal answer - so it is put there without asking."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Anticipate"],
            library=["Lightning Bolt"],
            battlefield=["Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bolt,) = scenario.top_of_library(1, "alice")

    scenario.cast_and_resolve("Anticipate", *scenario.untapped_sources("Island", "Island"))

    assert bolt.zone is Zone.HAND
    assert scenario.player("alice").library == []
    assert [q for q in scenario.questions_asked() if q.source == "Anticipate"] == []


def _dovin_board(library: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dovin, Grand Arbiter"], library=library)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dovin = scenario.find("Dovin, Grand Arbiter", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(dovin, Counter.LOYALTY, 4)  # 3 printed -> 7, pays -7
    return scenario, dovin


_TEN = [
    "Mountain",
    "Forest",
    "Lightning Bolt",
    "Swamp",
    "Counterspell",
    "Plains",
    "Island",
    "Mountain",
    "Forest",
    "Swamp",
    "Plains",
]


def test_dovin_minus_seven_puts_three_into_hand_and_seven_on_the_bottom():
    scenario, dovin = _dovin_board(_TEN)
    alice = scenario.player("alice")
    looked = scenario.top_of_library(10, "alice")
    _hand_pick(scenario, looked[2], looked[4], looked[6], source="Dovin, Grand Arbiter")

    scenario.activate(dovin, index=2)
    scenario.pass_until_resolved()

    question = _split_question(scenario, "Dovin, Grand Arbiter")
    assert len(question.cards) == 10
    assert question.amount == 3
    assert question.exact is True
    assert [state.zone for state in (looked[2], looked[4], looked[6])] == [Zone.HAND] * 3
    assert alice.library[0].name == "Plains", "the eleventh card stays on top"
    assert len(alice.library) == 8
    assert DecisionKind.CHOOSE_CARDS not in [
        q.kind for q in scenario.questions_asked() if q.source == "Dovin, Grand Arbiter"
    ], "a random order is nobody's arrangement"
    scenario.assert_in_exactly_one_zone(*looked)


def test_dovin_refuses_two_cards_for_hand():
    scenario, dovin = _dovin_board(_TEN)
    looked = scenario.top_of_library(2, "alice")
    _hand_pick(scenario, *looked, source="Dovin, Grand Arbiter")

    scenario.activate(dovin, index=2)
    with pytest.raises(ValueError, match=r"exactly 3 card\(s\) must be chosen.*\(CR 608\.2d\)"):
        scenario.pass_until_resolved()
