"""Scenario: "Each opponent loses life equal to the number of creature cards
in your graveyard." (Grist, the Hunger Tide's -5) - CR 119.3's life loss dealt
to CR 102.2's "each opponent" (no target at all), with the amount read through
`machines/effects.py`'s shared `count_expression` - the same evaluator
Craterhoof Behemoth's own "where X is the number of creatures you control"
uses (`test_computed_magnitude_team_pump.py`), applied here to "creature
cards in your graveyard" instead of "creatures you control".

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def grist_board(*, graveyard: list[str] | None = None) -> Scenario:
    """Alice with Grist already in play, bumped to 6 loyalty for the -5, and
    whatever graveyard the test wants. Bob is the one opponent."""
    return (
        Scenario()
        .player("alice", battlefield=["Grist, the Hunger Tide"], graveyard=graveyard or [])
        .player("bob")
    )


def _activate_minus_five(scenario: Scenario):
    grist = scenario.find("Grist, the Hunger Tide", Zone.BATTLEFIELD)
    # 3 printed -> 6: Grist survives its own -5. From 5 it would drop to 0
    # and go to the graveyard first (CR 704.5i), where it is a creature
    # card too (CR 113.6c) and would count itself.
    scenario.game.add_counters(grist, Counter.LOYALTY, 3)
    scenario.activate(grist, index=2)
    scenario.resolve_top()


def test_grists_minus_five_costs_bob_life_equal_to_creature_cards_in_alices_graveyard():
    """Two creature cards and one non-creature card in the graveyard - only
    the two creature cards count (CR 205.2a)."""
    scenario = grist_board(graveyard=["Grizzly Bears", "Grizzly Bears", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    assert bob.life == 20

    _activate_minus_five(scenario)

    assert bob.life == 18


def test_grists_minus_five_with_an_empty_graveyard_costs_nothing():
    """CR 119.3 still "adjusts" life by zero, which is the same as not
    touching it - `count_expression`'s own zero floor, not a refusal to
    resolve at all."""
    scenario = grist_board(graveyard=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    _activate_minus_five(scenario)

    assert bob.life == 20


def test_grists_minus_five_ignores_noncreature_cards_in_the_graveyard():
    """A graveyard full of noncreature cards counts zero (CR 205.2a: an
    instant is never a creature card)."""
    scenario = grist_board(graveyard=["Lightning Bolt", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    _activate_minus_five(scenario)

    assert bob.life == 20
