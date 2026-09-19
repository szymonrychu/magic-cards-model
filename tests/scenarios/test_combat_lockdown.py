"""Yuriko, Blade of the Mighty: "During combat, players can't cast spells or
activate abilities that aren't mana abilities."

Split second's own equivalent (`test_split_second.py`) is a spell's own
"while this spell is on the stack" window; this is the same board-wide lock
with a turn-structure window instead (CR 506.1's five combat steps), so it
lives as its own reader (`combat_lockdown_restriction_source`) rather than
folded into split second's, and is wired through the same two refusal
points: `Casting.why_cannot_cast_restriction` and `Game.why_cannot_activate`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board() -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Yuriko, Blade of the Mighty"])
        .player(
            "bob",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Vampire Bats", "Swamp"],
            life=20,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_no_spell_may_be_cast_during_combat():
    scenario = _board()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    with pytest.raises(ValueError, match="CR 506.1"):
        scenario.cast("Lightning Bolt", username="bob")


def test_a_non_mana_ability_may_not_be_activated_during_combat_either():
    scenario = _board()
    bats = scenario.creature("Vampire Bats", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    refusal = scenario.why_cannot_activate(bats, username="bob")
    assert refusal is not None
    assert "CR 506.1" in refusal
    with pytest.raises(ValueError, match="CR 506.1"):
        scenario.activate(bats, username="bob")


def test_a_mana_ability_is_unaffected_during_combat():
    scenario = _board()
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.pass_priority("alice")

    assert scenario.why_cannot_activate(swamp, username="bob") is None
    scenario.activate(swamp, username="bob")
    assert swamp.tapped


def test_casting_is_unaffected_outside_combat():
    scenario = _board()
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=["alice"])

    assert scenario.player("alice").life == 17
