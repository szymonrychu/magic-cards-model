"""Draw-quantity replacement effects (CR 614.1a, 121.2a, 121.6, 604.2).

Quantum Riddler: "As long as you have one or fewer cards in hand, if you
would draw one or more cards, you draw that many cards plus one instead."
Alhammarret's Archive (the proof printing - neither a listed card nor in any
api deck, and worded differently: a single draw, "two cards", an exception for
the draw step): "If you would draw a card except the first one you draw in
each of your draw steps, draw two cards instead."

Every CR number here was read in full with `mise run rules:find`:

- **CR 614.1a** - effects that use the word "instead" are replacement effects.
- **CR 121.2a** - an instruction to draw multiple cards can be modified by
  replacement effects that refer to the number of cards drawn, before any of
  the individual draws.
- **CR 121.6** - some effects replace card draws.
- **CR 604.2** - a static ability's effect exists while its permanent is on
  the battlefield; the "as long as" condition is checked as the event
  happens.
- **CR 504.1** - the draw step's turn-based draw.
"""

from magic_cards_model.machines import Step
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice: list[str], *, hand: list[str] | None = None, bob: list[str] | None = None):
    scenario = (
        Scenario()
        .player("alice", battlefield=alice, hand=hand or [], library=["Island"] * 10)
        .player("bob", battlefield=bob or [], library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Quantum Riddler ----------------------------------------------------------


def test_riddler_adds_one_with_an_empty_hand():
    scenario = _board(["Quantum Riddler"])

    drawn = scenario.draw(1)

    assert len(drawn) == 2


def test_riddler_adds_one_with_exactly_one_card_in_hand():
    """ "One or fewer": one card in hand still counts."""
    scenario = _board(["Quantum Riddler"], hand=["Island"])

    drawn = scenario.draw(1)

    assert len(drawn) == 2


def test_riddler_does_nothing_with_two_cards_in_hand():
    scenario = _board(["Quantum Riddler"], hand=["Island", "Island"])

    drawn = scenario.draw(1)

    assert len(drawn) == 1


def test_riddler_adds_one_to_a_multi_card_draw_not_one_per_card():
    """CR 121.2a: "that many cards plus one" - drawing two with an empty hand
    is three cards, not four."""
    scenario = _board(["Quantum Riddler"])

    drawn = scenario.draw(2)

    assert len(drawn) == 3


def test_riddler_leaves_an_opponents_draw_alone():
    scenario = _board(["Quantum Riddler"])

    drawn = scenario.draw(1, username="bob")

    assert len(drawn) == 1


def test_riddlers_own_enters_draw_with_an_empty_hand_draws_two():
    """Cast as the last card in hand, the Riddler's "When this creature
    enters, draw a card." draws two - its static ability applies as soon as
    it is on the battlefield (CR 604.2)."""
    scenario = _board(["Island"] * 5, hand=["Quantum Riddler"])

    scenario.cast_and_resolve("Quantum Riddler", auto=True)
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").hand) == 2


# -- Alhammarret's Archive (the proof printing) ---------------------------------


def test_archive_doubles_a_draw_outside_the_draw_step():
    scenario = _board(["Alhammarret's Archive"], hand=["Island", "Island"])

    drawn = scenario.draw(1)

    assert len(drawn) == 2


def test_archive_leaves_the_first_draw_step_draw_alone():
    """ "Except the first one you draw in each of your draw steps" (CR 504.1):
    the first draw-step draw is one card, a second draw in the same step is
    doubled."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Alhammarret's Archive"], library=["Island"] * 10)
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.DRAW)

    first = scenario.draw(1)
    second = scenario.draw(1)

    assert len(first) == 1
    assert len(second) == 2


def test_archive_leaves_an_opponents_draw_alone():
    scenario = _board(["Alhammarret's Archive"])

    drawn = scenario.draw(1, username="bob")

    assert len(drawn) == 1


# -- the audit ----------------------------------------------------------------


def test_every_clause_of_the_riddler_is_handled():
    """Warp is a keyword (its own audit); every other clause is handled."""
    outcomes = classify_clauses(card("Quantum Riddler"))
    assert outcomes
    assert {outcome.category for outcome in outcomes} == {HANDLED}, outcomes


def test_the_archives_draw_line_is_handled():
    """Its life-gain line is a different reader's (life quantity), not this
    task's draw-quantity one."""
    outcomes = classify_clauses(card("Alhammarret's Archive"))
    draw = [outcome for outcome in outcomes if "draw" in outcome.text]
    assert [outcome.category for outcome in draw] == [HANDLED]
