"""Shadow of Mortality: "If your life total is less than your starting life
total, this spell costs {X} less to cast, where X is the difference."

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 601.2f** - "Some effects may increase or reduce the cost to pay ...
  Once the total cost is determined, any effects that directly affect the
  total cost are applied."
- **CR 103.4** - a player's starting life total, `Player.starting_life`.
- **CR 118.7a** - a cost reduction of generic mana affects only the generic
  component.

Read by `Game.cost_reduction_for`'s own `_COSTS_LESS_IF_LIFE_TOTAL_VS_
STARTING_X_IS_DIFFERENCE_RE` - the same "if <condition>, this spell costs
{X} less to cast, where X is <amount>" shape family Wrath of the Bloodmane's
and Sunderflock's own rows already cover in `tests/scenarios/test_cost_
reduction_shapes.py`, generalised here to a life-total-vs-starting-life-total
comparison rather than a board count.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_at_starting_life_the_reduction_is_zero():
    scenario = Scenario().player("alice", life=20, hand=["Shadow of Mortality"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Shadow of Mortality")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{13}{B}{B}"


def test_below_starting_life_the_reduction_is_the_difference():
    scenario = Scenario().player("alice", life=20, hand=["Shadow of Mortality"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.lose_life(scenario.player("alice"), 12)  # 20 -> 8, 12 below starting

    casting = scenario.cast("Shadow of Mortality")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{1}{B}{B}"


def test_the_reduction_never_exceeds_the_generic_component():
    """CR 118.7a: a generic-mana reduction can't touch the colored pips, and
    CR 601.2f's own {0} floor stops it going negative."""
    scenario = Scenario().player("alice", life=20, hand=["Shadow of Mortality"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.lose_life(scenario.player("alice"), 19)  # 20 -> 1, 19 below starting

    casting = scenario.cast("Shadow of Mortality")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{B}{B}"


def test_above_starting_life_gives_no_reduction():
    """The condition only fires below the starting total - gaining life
    above it is not a discount the other way."""
    scenario = Scenario().player("alice", life=20, hand=["Shadow of Mortality"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life(scenario.player("alice"), 10)  # 20 -> 30, above starting

    casting = scenario.cast("Shadow of Mortality")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{13}{B}{B}"
