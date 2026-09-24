"""Scenario: CR 701.64's Harness keyword action and CR 702.186's ∞
(Infinity) keyword, on The Mind Stone.

Every rule cited here was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.64a** - "'Harness [this permanent]' means 'If this permanent
  isn't harnessed, it becomes harnessed.'"
- **CR 701.64b** - "Harnessed is a designation ... Only permanents can be or
  become harnessed. Once a permanent becomes harnessed, it stays harnessed
  until it leaves the battlefield."
- **CR 702.186a** - "∞ (the mathematical symbol for infinity) is a keyword
  found on Infinity cards. '∞' is followed by ability text."
- **CR 702.186b** - "'∞ — [Ability]' means 'As long as this permanent is
  harnessed, it has [Ability].'"

`∞ —` is stripped by `machines/abilities.py::_ABILITY_WORD` (widened this
task to accept the bare "∞" symbol alongside the ordinary capitalised-word
shape) and the rest is read as an ordinary "At the beginning of ..."
triggered ability; CR 702.186b's own "as long as harnessed" gate is
`Game._supplement_characteristics`'s business (`models/game.py`) - it adds
or removes the printed "∞ — ..." line from the computed board depending on
`Game.is_harnessed`, and `machines/triggers.py::triggered_abilities_on`
already treats a printed line's absence from the computed board as CR
613.1f removal (verified in the session that wrote this file), so nothing
in `machines/triggers.py` had to change for the gate to hold.

Proof printing: The Soul Stone (Marvel's Spider-Man, Modern/Pioneer/
Standard-legal, not in this task's card list and not in any deck list) -
"{6}{B}, {T}, Exile a creature you control: Harness The Soul Stone." and
"∞ — At the beginning of your upkeep, return target creature card from
your graveyard to the battlefield." - the same two keywords, a different
cost and a differently-worded ∞ ability.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _mind_stone_on_the_battlefield() -> tuple:
    scenario = Scenario().player("alice", battlefield=["The Mind Stone"] + ["Plains"] * 6).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.creature("The Mind Stone", "alice")
    return scenario, stone


# ---------------------------------------------------------------------------
# CR 701.64a: harnessing itself.
# ---------------------------------------------------------------------------


def test_harnessing_the_mind_stone():
    scenario, stone = _mind_stone_on_the_battlefield()
    assert scenario.game.is_harnessed(stone) is False

    sources = scenario.untapped_sources(*["Plains"] * 6)
    scenario.activate(stone, *sources, index=1)
    scenario.pass_until_resolved()

    assert scenario.game.is_harnessed(stone) is True


def test_harnessing_an_already_harnessed_permanent_is_a_no_op():
    """CR 701.64a: "If this permanent isn't harnessed, it becomes
    harnessed." - already harnessed, nothing changes (and nothing raises)."""
    scenario, stone = _mind_stone_on_the_battlefield()
    scenario.game.harness(stone)
    assert scenario.game.is_harnessed(stone) is True

    scenario.game.harness(stone)

    assert scenario.game.is_harnessed(stone) is True


def test_harnessed_designation_ends_when_the_permanent_leaves_the_battlefield():
    """CR 701.64b: "Once a permanent becomes harnessed, it stays harnessed
    until it leaves the battlefield." `CardState`'s own "same id, new
    object" (CR 400.7) is what a bounce-and-return has to defeat -
    `Game._harness_key` folds in `zone_change_stamp`, the same scoping
    `_activation_key` already gives power-up/exhaust."""
    scenario, stone = _mind_stone_on_the_battlefield()
    scenario.game.harness(stone)
    assert scenario.game.is_harnessed(stone) is True

    scenario.game.return_to_hand(stone)
    assert stone.zone is Zone.HAND

    sources = scenario.untapped_sources("Plains", "Plains")
    returned = scenario.cast_and_resolve("The Mind Stone", *sources)

    assert returned is stone  # CR 400.7's own "same id, new object".
    assert scenario.game.is_harnessed(returned) is False


# ---------------------------------------------------------------------------
# CR 702.186b: the ∞ ability is present only while harnessed.
# ---------------------------------------------------------------------------


def test_infinity_ability_exiles_and_returns_a_nonland_permanent_you_control():
    scenario = Scenario().player("alice", battlefield=["The Mind Stone", "Grizzly Bears"]).build()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    stone = scenario.creature("The Mind Stone", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    # `CardState` mutates in place (CR 400.7's "same id, new object" is
    # approximated by reusing the one object) - the stamp is captured now,
    # before the effect runs, the same way `test_power_up.py`'s own bounce-
    # and-recast proof does.
    original_stamp = bears.zone_change_stamp
    scenario.game.harness(stone)
    scenario.will_choose_targets(bears, source="The Mind Stone")

    scenario.advance()  # the end step begins, raising CR 603.2's own event
    assert scenario.game.stack, "∞'s own end-step trigger should be on the stack once harnessed"
    scenario.pass_until_resolved()

    # CR 400.7: exile-then-return is a new object; `bears` is the same
    # `CardState` (this engine's own "same id" reuse), but a fresh stamp.
    new_bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert new_bears.zone is Zone.BATTLEFIELD
    assert new_bears is bears
    assert new_bears.zone_change_stamp != original_stamp


def test_infinity_ability_does_not_trigger_while_unharnessed():
    scenario = Scenario().player("alice", battlefield=["The Mind Stone", "Grizzly Bears"]).build()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    stone = scenario.creature("The Mind Stone", "alice")
    assert scenario.game.is_harnessed(stone) is False

    scenario.advance()  # the end step begins

    assert scenario.game.stack == []


def test_infinity_ability_stops_triggering_once_the_permanent_leaves():
    scenario = Scenario().player("alice", battlefield=["The Mind Stone", "Grizzly Bears"]).build()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    stone = scenario.creature("The Mind Stone", "alice")
    scenario.game.harness(stone)
    # The Mind Stone is indestructible, so `destroy` would not remove it;
    # sacrifice is CR 701.21a's own unconditional zone change.
    scenario.game.sacrifice(stone)
    assert stone.zone is Zone.GRAVEYARD

    scenario.advance()  # the end step begins

    assert scenario.game.stack == []


# ---------------------------------------------------------------------------
# Off-pool proof: The Soul Stone, a different Infinity Stone with Harness.
# ---------------------------------------------------------------------------


def test_off_pool_proof_the_soul_stone_harness_and_infinity():
    """The Soul Stone's own cost, "{6}{B}, {T}, Exile a creature you
    control", pays through a cost-payment reader this task does not own
    (`machines/cost.py`) and does not need to prove Harness/∞'s own
    generality - `Game.harness` is called directly instead, isolating the
    two keywords (CR 701.64, CR 702.186) this task is proving from that
    unrelated cost shape.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Soul Stone"], graveyard=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.UNTAP)
    stone = scenario.creature("The Soul Stone", "alice")
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    assert scenario.game.is_harnessed(stone) is False

    scenario.game.harness(stone)
    assert scenario.game.is_harnessed(stone) is True

    scenario.will_choose_targets(elves, source="The Soul Stone")
    scenario.advance()  # the upkeep begins, raising CR 603.2's own event
    assert scenario.game.stack, "The Soul Stone's own ∞ ability should trigger on your upkeep"
    scenario.pass_until_resolved()

    assert elves.zone is Zone.BATTLEFIELD
