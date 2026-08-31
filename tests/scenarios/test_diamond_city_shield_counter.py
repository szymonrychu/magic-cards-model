"""Scenario: Diamond City's "{T}: Move a shield counter from this land onto
target creature. Activate only if two or more creatures entered the
battlefield under your control this turn."

CR 122.5: "If an effect says to 'move' a counter, it means to remove that
counter from the object it's currently on and put it onto a second object.
If either of these actions isn't possible, it's not done at all."
`machines/effects.py`'s `_parse_move_counter_clause` reads this shape off the
ability's own printed text.

The timing restriction is CR 602.5b's "Activate only if [board state]" -
`Game._activation_condition_holds` already read two shapes of it (Mox Opal's
Metalcraft, Fanatic of Rhonas's Ferocious); this file's card needed a third,
`_ACTIVATE_ONLY_IF_ENTERED_THIS_TURN`, counting `CardState.turn_entered`
against `Game.turn.turn_number` the same way CR 702.131's ascend already
counts "entered this turn" elsewhere in the engine.

Every rule cited here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 122.5** - the move keyword action itself.
- **CR 602.1b, 602.5b** - "Activate only if" activation instructions.
- **CR 122.1c** - what a shield counter actually does (not exercised here -
  this file is about the counter's *movement*, not its own replacement
  effect).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _scenario() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Elder Gargaroth", "Goblin Guide"],
            battlefield=[
                "Diamond City",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Mountain",
            ],
        )
        .player("bob")
    )


def _with_shield_counter(scenario: Scenario) -> tuple:
    diamond_city = scenario.find("Diamond City", Zone.BATTLEFIELD, "alice")
    diamond_city.add_counters("shield", 1)
    return diamond_city


def test_moving_the_shield_counter_onto_a_creature_that_entered_this_turn():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    diamond_city = _with_shield_counter(scenario)

    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest")
    gargaroth = scenario.cast_and_resolve("Elder Gargaroth", *forests)
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Goblin Guide", mountain)

    scenario.activate(diamond_city, index=1, targets=[gargaroth])
    scenario.resolve_top()

    assert diamond_city.counters["shield"] == 0
    assert gargaroth.counters["shield"] == 1


def test_the_ability_is_refused_with_only_one_creature_entered_this_turn():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    diamond_city = _with_shield_counter(scenario)

    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest")
    gargaroth = scenario.cast_and_resolve("Elder Gargaroth", *forests)

    reason = scenario.why_cannot_activate(diamond_city, index=1)
    assert reason is not None
    assert "activation restriction" in reason

    with pytest.raises(ValueError, match="activation restriction"):
        scenario.activate(diamond_city, index=1, targets=[gargaroth])

    assert diamond_city.counters["shield"] == 1
    assert gargaroth.counters["shield"] == 0
