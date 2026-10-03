"""Initiate of Blood // Goka the Unjust: "{T}: This creature deals 1 damage to
target creature that was dealt damage this turn. When that creature dies
this turn, flip this creature."

The second sentence is a CR 603.7 delayed triggered ability watching the
targeted creature for the rest of the turn; its consequence flips the
source (CR 710). A flipped permanent has the alternative name, text box,
type line, power and toughness, but keeps its colour and mana cost.

Rules looked up with `mise run rules:find` in the session that wrote this:

- CR 710.1b - the bottom half's characteristics are used only on the
  battlefield and only while flipped.
- CR 710.1c - "A flip card's color and mana cost don't change if the
  permanent is flipped."
- CR 710.2 - before it flips, and in every other zone, only the normal
  characteristics apply.
- CR 710.4 - flipping is one-way; a flipped permanent that leaves the
  battlefield retains no memory of it.
- CR 603.7c - a delayed triggered ability that refers to a particular object
  still affects it only while it is the same object.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Supertype
from tests.scenarios.harness import Scenario

INITIATE = "Initiate of Blood"
GOKA = "Goka the Unjust"
YETI = "Karplusan Yeti"


def _board(*bob: str, shocks: int = 2) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shock"] * shocks,
            library=["Mountain"] * 3,
            battlefield=[INITIATE, *(["Mountain"] * shocks)],
        )
        .player("bob", library=["Forest"] * 3, battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _bobs(scenario: Scenario, name: str) -> list:
    return [
        state for state in scenario.game.permanents_controlled_by("bob") if state.name == name
    ]


def test_an_undamaged_creature_is_not_a_legal_target():
    scenario = _board(YETI)
    initiate = scenario.creature(INITIATE, "alice")
    (yeti,) = _bobs(scenario, YETI)

    with pytest.raises(ValueError):
        scenario.activate(initiate, targets=[yeti])


def test_the_kill_flips_it_into_goka_and_goka_works():
    scenario = _board(YETI, YETI)
    initiate = scenario.creature(INITIATE, "alice")
    victim, survivor = _bobs(scenario, YETI)
    first, second = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Shock", first, targets=[victim])
    scenario.cast_and_resolve("Shock", second, targets=[survivor])
    assert victim.damage == 2 and survivor.damage == 2

    scenario.activate(initiate, targets=[victim])
    scenario.pass_until_resolved()
    assert victim.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()  # the delayed "when that creature dies" trigger

    assert initiate.zone is Zone.BATTLEFIELD
    assert initiate.name == GOKA
    assert scenario.game.power_of(initiate) == 4
    assert scenario.game.toughness_of(initiate) == 4
    assert Supertype.LEGENDARY in initiate.supertypes
    assert initiate.mana_cost == "{3}{R}", "CR 710.1c: the mana cost does not change"
    assert [color.value for color in initiate.colors] == ["R"]
    assert initiate.tapped, "flipping is not a zone change; it stays tapped"

    initiate.untap()
    scenario.activate(initiate, targets=[survivor])
    scenario.pass_until_resolved()

    assert survivor.zone is Zone.GRAVEYARD, "Goka's 4 damage"
    assert initiate.name == GOKA, "CR 710.4: no flipping back"


def test_no_death_no_flip():
    scenario = _board("Vein Drinker", shocks=1)
    initiate = scenario.creature(INITIATE, "alice")
    (drinker,) = _bobs(scenario, "Vein Drinker")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Shock", mountain, targets=[drinker])

    scenario.activate(initiate, targets=[drinker])
    scenario.pass_until_resolved()

    assert drinker.damage == 3 and drinker.zone is Zone.BATTLEFIELD
    assert initiate.name == INITIATE


def test_a_later_death_the_same_turn_still_flips():
    """"When that creature dies this turn" watches the rest of the turn, not
    only the Initiate's own damage."""
    scenario = _board("Vein Drinker", shocks=2)
    initiate = scenario.creature(INITIATE, "alice")
    (drinker,) = _bobs(scenario, "Vein Drinker")
    first, second = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Shock", first, targets=[drinker])
    scenario.activate(initiate, targets=[drinker])
    scenario.pass_until_resolved()
    assert initiate.name == INITIATE

    scenario.cast_and_resolve("Shock", second, targets=[drinker])
    assert drinker.zone is Zone.GRAVEYARD
    while not scenario.game.stack_is_empty:  # Vein Drinker's own death trigger too
        scenario.pass_until_resolved()

    assert initiate.name == GOKA


def test_a_flipped_permanent_forgets_it_left_the_battlefield():
    """CR 710.4 and 710.2: Goka bounced to hand is Initiate of Blood again."""
    scenario = _board(YETI, shocks=1)
    initiate = scenario.creature(INITIATE, "alice")
    (yeti,) = _bobs(scenario, YETI)
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Shock", mountain, targets=[yeti])
    scenario.activate(initiate, targets=[yeti])
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert initiate.name == GOKA

    scenario.game.return_to_hand(initiate)

    assert initiate.zone is Zone.HAND
    assert initiate.name == INITIATE
    assert not initiate.flipped
