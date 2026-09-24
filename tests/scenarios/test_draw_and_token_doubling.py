"""Scenario: Bard, King of Dale - VERIFY ONLY.

"If you would draw a card except the first one you draw in each of your draw
steps, draw two cards instead. If one or more tokens would be created under
your control, twice that many of those tokens are created instead."

Both clauses are templates a prior task already built generically:

- **The draw-quantity replacement** is Alhammarret's Archive's own template,
  word for word (`machines/replacement.py`'s "except the first ... in each
  of your draw steps, draw two ... instead" compiler), already proven
  generic off the deck pool in `test_draw_plus_one_replacement.py`.
- **The token-doubling replacement** is Doubling Season's own template
  (`_compile_token_doubler`), already proven generic in
  `test_token_creation_replacement.py`.

Nothing in either reader needed widening for Bard, King of Dale's own
slightly different phrasing (passive voice, no "an effect" subject) - this
file is the verification the task asked for, not new machinery. Reach for
`mise exec -- uv run python scripts/sweep_pool.py --card "Bard, King of
Dale"` to see both clauses already read `handled` before this file existed.
"""

from magic_cards_model.machines import Step
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card

from .harness import Scenario


def test_the_first_draw_step_draw_is_not_doubled():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bard, King of Dale"], library=["Island"] * 10)
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.DRAW)

    first = scenario.draw(1)

    assert len(first) == 1


def test_a_second_draw_in_the_same_draw_step_is_doubled():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bard, King of Dale"], library=["Island"] * 10)
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.DRAW)
    scenario.draw(1)  # the first draw-step draw, left alone

    second = scenario.draw(1)

    assert len(second) == 2


def test_a_draw_outside_the_draw_step_is_doubled():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Bard, King of Dale"],
            hand=["Island", "Island"],
            library=["Island"] * 10,
        )
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    drawn = scenario.draw(1)

    assert len(drawn) == 2


def test_an_opponents_draw_is_left_alone():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bard, King of Dale"], library=["Island"] * 10)
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    drawn = scenario.draw(1, username="bob")

    assert len(drawn) == 1


def test_creating_one_token_creates_two_instead():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Bard, King of Dale", "Bard's Company"],
            library=["Lightning Bolt", "Shock"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    company = scenario.creature("Bard's Company", "alice")
    company.summoning_sick = False

    scenario.attack_with(company)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()

    tokens = [
        state for state in scenario.game.battlefield if state.token and "Soldier" in state.subtypes
    ]
    assert len(tokens) == 2, "Bard's Company's own recruit makes one; Bard, King of Dale doubles it"


def test_an_opponents_token_creation_is_not_doubled():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Bard's Company"], library=["Lightning Bolt"])
        .player("alice", battlefield=["Bard, King of Dale"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    company = scenario.creature("Bard's Company", "bob")
    company.summoning_sick = False

    scenario.attack_with(company)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()

    tokens = [
        state for state in scenario.game.battlefield if state.token and "Soldier" in state.subtypes
    ]
    assert len(tokens) == 1


def test_every_clause_of_bard_king_of_dale_is_handled():
    """The audit the task's VERIFY ONLY requirement asks for - reach for
    `scripts/sweep_pool.py --card` for the same answer outside pytest."""
    outcomes = classify_clauses(card("Bard, King of Dale"))
    assert outcomes
    assert {outcome.category for outcome in outcomes} == {HANDLED}, outcomes
