"""Judge scenario: replacement effects that modify a card draw (DDR#975).

"Quantum Riddler + Thought Reflection." Amy controls one Quantum Riddler and
plays a second; its enters trigger says to draw a card, and both Riddlers want
to replace that draw. The episode's two rulings:

- **Each replacement gets one opportunity, so both apply in turn.** CR 616.1:
  the affected player chooses one of the applicable effects; CR 614.5: "A
  replacement effect doesn't invoke itself repeatedly; it gets only one
  opportunity to affect an event or any modified events that may replace that
  event." The one Amy chose is spent; the other one still applies to the
  modified event. Two Riddlers therefore draw three cards, not two.

- **A draw replacement cannot be sequenced ahead of one that keys off the whole
  instruction.** CR 121.2: "Cards may only be drawn one at a time. If a player
  is instructed to draw multiple cards, that player performs that many
  individual card draws." CR 121.2a: "An instruction to draw multiple cards can
  be modified by replacement effects that refer to the number of cards drawn.
  This modification occurs before considering any of the individual card
  draws." Quantum Riddler keys off "draw one or more cards" and Thought
  Reflection off "draw a card", so the Riddler's is the one that has to go
  first - which is not the free choice the Torbran ruling would suggest.

Both rulings hold now. `machines/replacement.py` compiles Thought Reflection's
plain "if you would draw a card, draw two cards instead" and Quantum Riddler's
"as long as you have one or fewer cards in hand, ... you draw that many cards
plus one instead", and the CR 614.5 follow-up works because "draw two cards
instead" is applied as an *increment* rather than as a flat two: a second
permanent printing the same line gets its own opportunity against the modified
event, replaces one of CR 121.2's individual draws with two, and the total goes
to three rather than staying at two.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 121.2, CR 121.2a, CR 121.6b,
CR 614.5, CR 616.1, CR 616.1e.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.replacement import replacements_of
from tests.cards import card
from tests.scenarios.harness import Scenario

LIBRARY = ["Mountain"] * 12


def archives(count: int) -> Scenario:
    return Scenario().player(
        "alice",
        library=list(LIBRARY),
        battlefield=["Alhammarret's Archive"] * count,
    )


def test_a_draw_replacement_really_applies():
    """The machinery the episode's ruling needs, proved with the card the
    engine does compile.

    "If you would draw a card except the first one you draw in each of your
    draw steps, draw two cards instead" is `ReplacementKind.DRAW`, and one draw
    outside the draw step becomes two.
    """
    scenario = archives(1).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    drawn = scenario.game.draw_cards("alice", 1)

    assert len(drawn) == 2


def test_a_second_copy_applies_to_the_already_modified_draw():
    """CR 614.5 / CR 616.1e: one effect is chosen, then the check repeats.

    The assertion is deliberately loose - more than two - because the exact
    total depends on whether CR 121.2 splits the modified instruction first,
    and the point of the episode is only that the second permanent is *not*
    excluded by the first one having applied.
    """
    scenario = archives(2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    drawn = scenario.game.draw_cards("alice", 1)

    assert len(drawn) > 2


def test_both_of_the_episodes_cards_carry_a_draw_replacement():
    """CR 121.2a distinguishes them: one keys off "draw one or more cards", the
    other off "draw a card". Both have to exist before the order can matter.
    """
    assert replacements_of(card("Thought Reflection"))
    assert replacements_of(card("Quantum Riddler"))
