"""Scenario: skulk (CR 702.118).

Read with `mise run rules:find 702.118` this session:

- **CR 702.118a** - skulk is an evasion ability.
- **CR 702.118b** - "A creature with skulk can't be blocked by creatures
  with greater power."
- **CR 702.118c** - multiple instances are redundant.

Wharf Infiltrator (1/1, skulk) is the printing. Power is compared as it is
when blockers are declared (CR 509.1b), off the computed board, so a pump on
either creature changes the answer.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import executes
from magic_cards_model.support import ignored_keywords
from tests.cards import card
from tests.scenarios.harness import Scenario

INFILTRATOR = "Wharf Infiltrator"


def _attacking(blocker: str):
    scenario = (
        Scenario()
        .player("alice", battlefield=[INFILTRATOR], library=["Island"] * 3)
        .player("bob", battlefield=[blocker], library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    infiltrator = scenario.creature(INFILTRATOR, "alice")
    scenario.attack_with(infiltrator)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    return scenario, infiltrator, scenario.creature(blocker, "bob")


def test_skulk_is_executed_and_not_reported_as_ignored():
    assert executes("skulk")
    assert "Skulk" not in ignored_keywords(card(INFILTRATOR))


def test_a_creature_with_greater_power_cannot_block_it():
    scenario, infiltrator, bears = _attacking("Grizzly Bears")
    refusal = scenario.game.why_cannot_block(bears, infiltrator)
    assert refusal is not None and "702.118b" in refusal
    with pytest.raises(ValueError, match="skulk"):
        scenario.block(infiltrator, bears)


def test_a_creature_with_equal_power_can_block_it():
    scenario, infiltrator, elves = _attacking("Llanowar Elves")
    assert scenario.game.why_cannot_block(elves, infiltrator) is None
    scenario.block(infiltrator, elves)
