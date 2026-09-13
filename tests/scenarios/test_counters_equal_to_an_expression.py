"""Counters whose number is an expression: "counters ... equal to <expr>".

Battle report B4-01: Slumbering Trudge cast for X=2 entered tapped with no
counters at all, untapped next turn, and attacked three turns early. "This
creature enters with a number of stun counters on it equal to three minus X"
was parsed into an expression ("three minus x") that no reader evaluated, and
the counters were skipped with no notice.

Rules read in full with `mise run rules:find` this session:

- **CR 614.1c** - "Effects that read '[This permanent] enters with . . . ,'
  ... are replacement effects."
- **CR 107.3m** - "If an object's enters-the-battlefield triggered ability or
  replacement effect refers to X, and the spell that became that object as it
  resolved had a value of X chosen for any of its costs, the value of X for
  that ability is the same as the value of X for that spell".
- **CR 107.2** - "If anything needs to use a number that can't be determined,
  either as a result or in a calculation, it uses 0 instead." An X with no
  spell behind it (the permanent was put onto the battlefield) is that number.
- **CR 107.1b** - "If a calculation that would determine the result of an
  effect yields a negative number, zero is used instead". Three minus X for
  X=5 places zero counters, not minus two.
- **CR 122.1d** - "One or more stun counters on a permanent create a single
  replacement effect that stops the permanent from untapping. That effect is
  'If a permanent with a stun counter on it would become untapped, instead
  remove a stun counter from it.'"
- **CR 502.3** - the untap step untaps the active player's permanents; a stun
  counter replaces that untap.

The reader is the template, not the card: an off-pool enters-with count over
a game value (Rhizome Lurcher, "equal to the number of creature cards in your
graveyard"), and an off-pool resolving effect with the same "equal to"
(Reverent Hunter, "put a number of +1/+1 counters on it equal to your devotion
to green") are read by the same expression reader. An expression it cannot
read fails closed with a notice instead of placing a wrong number silently.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import UnreadableCounterAmountNotice, amount_expression
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _cast_trudge(scenario, x: int):
    sources = scenario.untapped_sources(*(["Forest"] * (x + 1)))
    casting = scenario.cast("Slumbering Trudge")
    casting.determine_cost(x_value=x)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def _trudge_board(forests: int):
    scenario = (
        Scenario()
        .player("alice", hand=["Slumbering Trudge"], battlefield=["Forest"] * forests)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_reported_case_x_two_enters_tapped_with_one_stun_counter():
    scenario = _trudge_board(3)
    trudge = _cast_trudge(scenario, 2)

    assert trudge.zone is Zone.BATTLEFIELD
    assert trudge.counters[Counter.STUN] == 1, "three minus X, with X=2 (CR 107.3m)"
    assert trudge.tapped, "If X is 2 or less, it enters tapped."
    assert scenario.game.unreadable_counter_amount_notices == []


def test_x_zero_places_three_stun_counters():
    scenario = _trudge_board(1)
    trudge = _cast_trudge(scenario, 0)

    assert trudge.counters[Counter.STUN] == 3
    assert trudge.tapped


def test_x_three_places_no_counters_and_enters_untapped():
    scenario = _trudge_board(4)
    trudge = _cast_trudge(scenario, 3)

    assert trudge.counters[Counter.STUN] == 0
    assert not trudge.tapped


def test_a_negative_result_is_clamped_to_zero():
    """CR 107.1b: three minus five places zero counters, never minus two."""
    scenario = _trudge_board(6)
    trudge = _cast_trudge(scenario, 5)

    assert trudge.counters[Counter.STUN] == 0
    assert not trudge.tapped
    assert trudge.power == 6


def test_the_stun_counter_replaces_the_next_untap_step():
    """CR 122.1d, CR 502.3: the first untap step removes the counter instead;
    the one after that untaps it."""
    scenario = _trudge_board(3)
    trudge = _cast_trudge(scenario, 2)

    scenario.game.untap_step()
    assert trudge.tapped
    assert trudge.counters[Counter.STUN] == 0

    scenario.game.untap_step()
    assert not trudge.tapped


def test_put_onto_the_battlefield_with_no_spell_x_is_zero():
    """CR 107.2: with no spell behind the permanent, X cannot be determined and
    is 0, so three minus X is three."""
    scenario = _trudge_board(0)

    trudge = scenario.put_onto_battlefield("Slumbering Trudge", "alice")

    assert trudge.counters[Counter.STUN] == 3


def test_an_off_pool_enters_with_count_over_a_game_value():
    """Rhizome Lurcher: "enters with a number of +1/+1 counters on it equal to
    the number of creature cards in your graveyard" - no X, a board count."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rhizome Lurcher"],
            battlefield=["Forest", "Swamp", "Forest", "Forest"],
            graveyard=["Grizzly Bears", "Hill Giant", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    lurcher = scenario.cast_and_resolve("Rhizome Lurcher", auto=True)

    assert lurcher.counters[Counter.PLUS_ONE] == 2
    assert lurcher.power == 4


def test_an_off_pool_resolving_effect_places_counters_equal_to_an_expression():
    """Reverent Hunter's enters trigger: "put a number of +1/+1 counters on it
    equal to your devotion to green" - the effect-side template."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Reverent Hunter"],
            battlefield=["Forest", "Forest", "Forest", "Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hunter = scenario.cast_and_resolve("Reverent Hunter", auto=True)
    scenario.resolve_top()  # its enters trigger

    # Devotion to green: Llanowar Elves' {G} and Reverent Hunter's own {G}.
    assert hunter.counters[Counter.PLUS_ONE] == 2


@pytest.mark.parametrize(
    ("phrase", "x", "expected"),
    [
        ("three minus x", 2, 1),
        ("three minus x", 7, 0),
        ("x", 4, 4),
        ("two plus x", 1, 3),
        ("twice x", 3, 6),
        ("3", 0, 3),
    ],
)
def test_the_expression_reader_evaluates_arithmetic_over_x(phrase, x, expected):
    scenario = Scenario().player("alice", battlefield=["Forest"]).player("bob").build()
    forest = scenario.find("Forest", Zone.BATTLEFIELD)

    reader = amount_expression(phrase)

    assert reader is not None
    assert reader(scenario.game, "alice", forest, x) == expected


def test_an_unreadable_expression_is_not_claimed():
    assert amount_expression("the number of dreams you had last night") is None


def test_an_unreadable_enters_with_count_fails_closed_with_a_notice():
    """No silent skip. Investigator's Journal (off-pool): "enters with a number
    of suspect counters on it equal to the greatest number of creatures a player
    controls" - an expression this reader does not evaluate, so the permanent
    enters with no counters and a notice names the unread expression."""
    scenario = (
        Scenario()
        .player("alice", hand=["Investigator's Journal"], battlefield=["Wastes", "Wastes"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    journal = scenario.cast_and_resolve("Investigator's Journal", auto=True)

    assert journal.zone is Zone.BATTLEFIELD
    assert journal.counters["suspect"] == 0
    (notice,) = scenario.game.unreadable_counter_amount_notices
    assert notice.source_name == "Investigator's Journal"
    assert notice.expression == "the greatest number of creatures a player controls"
    assert isinstance(notice, UnreadableCounterAmountNotice)
