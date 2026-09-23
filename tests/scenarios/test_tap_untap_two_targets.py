"""Tap or untap two differently-described targets in one sentence.

Kiora, Master of the Depths' +1: "Untap up to one target creature and up to
one target land." One instruction with two instances of the word "target",
each chosen independently (not two clauses): the bare "and" between them is
part of the target phrase, not a clause boundary.

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 115.6** - "up to one" may choose zero targets; the ability still
  resolves, and a +1 loyalty cost is still paid.
- **CR 115.3** - "target" printed twice: the same object can be chosen once
  for each instance, so a Dryad Arbor may fill both the creature and the land
  slot.
- **CR 608.2b** - a target gone from the battlefield is illegal and is left
  alone; the other target is still untapped.
- **CR 701.26b** - to untap is to rotate a tapped permanent upright.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _kiora(*, alice_battlefield: list[str], bob_battlefield: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kiora, Master of the Depths", *alice_battlefield],
            library=["Island"] * 3,
        )
        .player("bob", battlefield=bob_battlefield or [], library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kiora = scenario.find("Kiora, Master of the Depths", Zone.BATTLEFIELD, "alice")
    return scenario, kiora


def _resolve(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def test_plus_one_untaps_a_creature_and_a_land():
    scenario, kiora = _kiora(alice_battlefield=["Grizzly Bears", "Forest"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    bears.tap()
    forest.tap()

    scenario.activate(kiora, index=0, targets=[bears, forest])
    _resolve(scenario)

    assert not bears.tapped
    assert not forest.tapped
    assert kiora.counters[Counter.LOYALTY] == 5


def test_plus_one_may_untap_only_a_land():
    """CR 115.6: the creature slot is left empty."""
    scenario, kiora = _kiora(alice_battlefield=["Grizzly Bears", "Forest"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    bears.tap()
    forest.tap()

    scenario.activate(kiora, index=0, targets=[forest])
    _resolve(scenario)

    assert not forest.tapped
    assert bears.tapped


def test_plus_one_with_no_targets_still_adds_loyalty():
    """CR 115.6: zero targets chosen, the ability is untargeted and resolves."""
    scenario, kiora = _kiora(alice_battlefield=["Forest"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    forest.tap()

    scenario.activate(kiora, index=0, targets=[])
    _resolve(scenario)

    assert forest.tapped
    assert kiora.counters[Counter.LOYALTY] == 5


def test_plus_one_can_untap_an_opponents_creature_and_land():
    scenario, kiora = _kiora(alice_battlefield=[], bob_battlefield=["Grizzly Bears", "Island"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    island = scenario.find("Island", Zone.BATTLEFIELD, "bob")
    bears.tap()
    island.tap()

    scenario.activate(kiora, index=0, targets=[bears, island])
    _resolve(scenario)

    assert not bears.tapped and not island.tapped


def test_a_target_that_left_the_battlefield_does_not_stop_the_other():
    """CR 608.2b: the land is still untapped when the creature is gone."""
    scenario, kiora = _kiora(alice_battlefield=["Grizzly Bears", "Forest"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    bears.tap()
    forest.tap()

    scenario.activate(kiora, index=0, targets=[bears, forest])
    scenario.game.put_into_graveyard(bears)
    _resolve(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert not forest.tapped


def test_dryad_arbor_may_be_both_the_creature_and_the_land():
    """CR 115.3: one object may be chosen once per instance of "target"."""
    scenario, kiora = _kiora(alice_battlefield=["Dryad Arbor"])
    arbor = scenario.find("Dryad Arbor", Zone.BATTLEFIELD, "alice")
    arbor.tap()

    scenario.activate(kiora, index=0, targets=[arbor, arbor])
    _resolve(scenario)

    assert not arbor.tapped


def test_two_lands_are_refused_for_the_creature_and_land_pair():
    """The creature slot takes only a creature: two plain lands do not fit."""
    scenario, kiora = _kiora(alice_battlefield=["Forest", "Island"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError):
        scenario.activate(kiora, index=0, targets=[forest, island])
