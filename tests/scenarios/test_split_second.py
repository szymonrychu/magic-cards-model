"""Split second: CR 702.61a.

"Split second is a static ability that functions only while the spell with
split second is on the stack. 'Split second' means 'As long as this spell is
on the stack, players can't cast other spells or activate abilities that
aren't mana abilities.'"

Not new to Reality Fracture and not printed on any card in this set - Samut,
Tyrant of Naktamun grants it to "Instant and sorcery spells you control", a
`_permanent_quality`-scoped keyword grant that belongs with S9's own
"group grants" machinery (`Thopters you control have haste`, explicitly on
S9's own missing list in the survey) rather than being duplicated here. This
file covers the base keyword itself - CR 702.61a's stack-wide lock - proved
on Sudden Shock (Time Spiral Remastered), a real printing with split second
on its own front rather than granted.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sudden Shock"],
            battlefield=["Mountain", "Mountain"],
        )
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


def test_no_other_spell_may_be_cast_while_split_second_is_on_the_stack():
    scenario = _board()
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack("Sudden Shock", *mountains, username="alice", targets=["bob"])
    scenario.pass_priority("alice")

    with pytest.raises(ValueError, match="CR 702.61a"):
        scenario.cast("Lightning Bolt", username="bob")


def test_a_non_mana_ability_may_not_be_activated_either():
    scenario = _board()
    bats = scenario.creature("Vampire Bats", "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack("Sudden Shock", *mountains, username="alice", targets=["bob"])
    scenario.pass_priority("alice")

    refusal = scenario.why_cannot_activate(bats, username="bob")
    assert refusal is not None
    assert "CR 702.61a" in refusal
    with pytest.raises(ValueError, match="CR 702.61a"):
        scenario.activate(bats, username="bob")


def test_a_mana_ability_is_unaffected():
    """CR 605.1a: activating a mana ability is never "casting a spell" or
    the other kind of "activating an ability" split second stops."""
    scenario = _board()
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack("Sudden Shock", *mountains, username="alice", targets=["bob"])
    scenario.pass_priority("alice")

    assert scenario.why_cannot_activate(swamp, username="bob") is None
    scenario.activate(swamp, username="bob")
    assert swamp.tapped


def test_casting_resumes_once_split_second_leaves_the_stack():
    scenario = _board()
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack("Sudden Shock", *mountains, username="alice", targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()
    scenario.pass_priority("alice")

    (bolt_source,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", bolt_source, username="bob", targets=["alice"])

    assert scenario.player("alice").life == 17
