"""Sacrifice-any-number cost reduction: "As an additional cost to cast this
spell, you may sacrifice any number of nonland permanents. This spell costs
{1} less to cast for each permanent sacrificed this way." (Rottenmouth
Viper).

Two mechanisms compose here, both general rather than pinned to this one
card:

- **CR 118.7a**'s own "any number of" object cost (`machines/cost.py`'s
  `_COST_COUNT`, widened this wave to read CR 107.1c's zero-floor quantity
  the same way it already read "one or more" - `numbers.QuantitySource.
  ANY_NUMBER`), and CR 118.7a's own negated card type ("nonland"), which
  `CardRequirement.excluded_types` now reads generally rather than only
  ever matching a bare `permanent`/`creature`/etc.
- **CR 118.7a**'s per-object cost reduction, tied not to a board-state count
  (`Game.cost_reduction_for`'s own four shapes) but to how many objects the
  caster actually chose to sacrifice for *this* announced additional cost
  (CR 601.2b) - `Casting.sacrifice_for_cost_reduction`, reading the linked
  amount off `machines.cost.per_object_sacrifice_cost_reduction`.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 118.7a** - "Some effects allow a spell's controller to reduce its
  cost by an amount of generic mana, or provide a way to pay a cost using
  something other than mana. Such effects don't change the mana cost or the
  converted mana cost of the spell."
- **CR 118.8a/b** - additional costs, some of them optional.
- **CR 107.1c** - "any number of" or "any amount of" means "any non-negative
  number", zero included.
- **CR 601.2h** - the total cost, once determined, is paid in full.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario


def _board(*, battlefield: list[str]) -> Scenario:
    return Scenario().player(
        "alice",
        hand=["Rottenmouth Viper"],
        battlefield=["Swamp"] * 6 + battlefield,
        library=["Swamp"] * 4,
    )


def test_sacrificing_two_nonland_permanents_reduces_the_cost_by_two():
    """{5}{B} down to {3}{B}: {1} less for each of the two permanents."""
    scenario = _board(battlefield=["Memnite", "Ornithopter"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "alice")
    ornithopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")

    casting = scenario.cast("Rottenmouth Viper")
    casting.sacrifice_for_cost_reduction([memnite, ornithopter])

    assert casting.total_cost.mana == ManaCost.parse("{3}{B}")


def test_paying_the_cost_actually_sacrifices_the_named_permanents():
    scenario = _board(battlefield=["Memnite", "Ornithopter"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "alice")
    ornithopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources(*(["Swamp"] * 4))

    casting = scenario.cast("Rottenmouth Viper")
    casting.sacrifice_for_cost_reduction([memnite, ornithopter])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)

    assert memnite.zone is Zone.GRAVEYARD
    assert ornithopter.zone is Zone.GRAVEYARD


def test_declining_the_cost_pays_the_full_mana_cost():
    """CR 107.1c: zero is a legal answer - the caster may sacrifice nothing
    at all and simply pay the printed cost."""
    scenario = _board(battlefield=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Rottenmouth Viper")
    casting.sacrifice_for_cost_reduction([])

    assert casting.total_cost.mana == ManaCost.parse("{5}{B}")


def test_the_cost_may_be_paid_without_ever_announcing_the_optional_cost():
    scenario = _board(battlefield=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Rottenmouth Viper")

    assert casting.total_cost.mana == ManaCost.parse("{5}{B}")


def test_a_land_cannot_be_named_for_the_nonland_sacrifice():
    """CR 118.7a's own "nonland" restriction: a land is a permanent, but not
    a nonland one."""
    scenario = _board(battlefield=["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")

    casting = scenario.cast("Rottenmouth Viper")
    with pytest.raises(ValueError, match="Forest"):
        casting.sacrifice_for_cost_reduction([forest])
