"""Sorin, Vengeful Bloodlord's own static ability: "During your turn,
creatures and planeswalkers you control have lifelink." (CR 702.15a, CR
613.1f) - a keyword grant to a *compound* subject naming two different card
types at once, active only during the source's own controller's turn.

`LayerContext.active_player` (CR 500.1) exists for exactly this: the
condition is checked once, at build time, the same way `machines.layers.
_graveyard_count_gated_self_static_builder`'s graveyard count already is -
`effects_for` reruns on every `computed_board()` call (CR 613.5), so the
grant disappears the instant the turn passes, with nothing stored or
cleared. `PermanentsOfTypesControlledBy` is the compound-subject selector:
`PermanentsControlledBy` only ever names one card type.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Sorin, Vengeful Bloodlord", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Watchwolf"])
    )


def test_alices_creature_has_lifelink_during_her_own_turn():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    chars = scenario.game.computed_board().of(bears)
    assert "Lifelink" in chars.abilities


def test_sorin_himself_has_lifelink_during_alices_turn_too():
    """ "Creatures **and planeswalkers** you control" - Sorin is a
    planeswalker and grants the ability to himself."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sorin = scenario.find("Sorin, Vengeful Bloodlord", Zone.BATTLEFIELD, "alice")

    chars = scenario.game.computed_board().of(sorin)
    assert "Lifelink" in chars.abilities


def test_bobs_creature_never_gets_lifelink_from_alices_sorin():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Watchwolf", "bob")

    chars = scenario.game.computed_board().of(wolf)
    assert "Lifelink" not in chars.abilities


def test_alices_creature_loses_lifelink_on_bobs_turn():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    while scenario.turn.active_player != "bob":
        scenario.advance()

    chars = scenario.game.computed_board().of(bears)
    assert "Lifelink" not in chars.abilities
