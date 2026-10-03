"""'`<Source>` deals N damage to target creature and M damage to that
creature's controller.' (Chandra, Flame's Fury's -2).

One instruction with one target. "That creature's controller" is a CR 400.7
back-reference to the target, not a target of its own, so it is read off the
creature as the ability resolves - and when the only target is illegal by
then, CR 608.2b says the ability does not resolve at all: no damage to the
creature and none to its controller either.

Rules looked up with `mise run rules:find` in the session that wrote this:

- CR 608.2b - "If all its targets, for every instance of the word 'target,'
  are now illegal, the spell or ability doesn't resolve."
- CR 120.3a - damage dealt to a player causes that player to lose that much
  life.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

CHANDRA = "Chandra, Flame's Fury"


def _board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=[CHANDRA, "Mountain"],
        )
        .player("bob", battlefield=["Tarmogoyf", "Grizzly Bears"])
        .build()
    )


def test_minus_two_damages_the_creature_and_its_controller():
    """4 to the creature, 2 to the player controlling it, from one target."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chandra = scenario.find(CHANDRA, Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(chandra, index=1, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD, "4 damage to a 2/2"
    assert scenario.player("bob").life == 18, "2 damage to that creature's controller"
    assert scenario.player("alice").life == 20


def test_an_illegal_target_on_resolution_deals_no_damage_to_its_controller():
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chandra = scenario.find(CHANDRA, Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.activate(chandra, index=1, targets=[bears])
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[bears])
    assert bears.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()  # Chandra's -2, its only target gone

    assert scenario.player("bob").life == 20, "CR 608.2b: the ability does not resolve"
    assert scenario.game.stack_is_empty
