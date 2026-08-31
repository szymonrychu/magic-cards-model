"""Necrodominance's end-step trigger (CR 119.4, CR 608.2d).

"At the beginning of your end step, you may pay any amount of life. If you
do, draw that many cards."

A genuinely new primitive: `DecisionKind.PAY_LIFE_AMOUNT` (mirroring the
existing `PAY_ENERGY_AMOUNT`) and `Game.pay_any_amount_of_life`, which asks
for a real *amount* rather than a yes/no the way `DecisionKind.PAY_LIFE`
(Necrodominance's own fixed-N cousin) does. **New `DecisionKind` - flagged
in this wave's report**: a live game's decision-answering side needs to be
able to answer this one.

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 119.4 ("only if their life total is greater than or equal to the amount
of the payment"), CR 119.4b ("players can always pay 0 life"), CR 118.12
("if you do").
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def board(library: list[str]) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Necrodominance"], life=10, library=library)
        .player("bob")
        .manual_turn_based_actions()
    )


def test_paying_five_life_draws_five_cards():
    scenario = board(["Forest"] * 6).build()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.will_pay_life_amount(5, source="Necrodominance")

    scenario.advance()  # the end step begins
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("alice").life == 5
    assert len(scenario.player("alice").hand) == 5


def test_declining_pays_nothing_and_draws_nothing():
    scenario = board(["Forest"] * 6).build()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.will_pay_life_amount(0, source="Necrodominance")

    scenario.advance()
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("alice").life == 10
    assert scenario.player("alice").hand == []


def test_paying_down_to_exactly_zero_life_is_legal():
    """CR 119.4: legal "only if their life total is greater than or equal
    to the amount of the payment" - paying all 10 of 10 life is exactly at
    the boundary, not over it."""
    scenario = board(["Forest"] * 10).build()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.will_pay_life_amount(10, source="Necrodominance")

    scenario.advance()
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("alice").life == 0
    assert len(scenario.player("alice").hand) == 10


def test_paying_more_life_than_you_have_is_refused():
    scenario = board(["Forest"] * 6).build()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.will_pay_life_amount(11, source="Necrodominance")

    scenario.advance()
    try:
        while scenario.game.stack:
            scenario.resolve_top()
    except ValueError as error:
        assert "119.4" in str(error)
    else:
        raise AssertionError("paying more life than available should have raised")
