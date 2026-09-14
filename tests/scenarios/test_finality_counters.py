"""A finality counter's replacement effect (CR 122.1h).

Looked up with `mise run rules:find 122.1h` in the session that wrote this
file:

- **CR 122.1h** - "One or more finality counters on a permanent create a
  single replacement effect that stops the permanent from going to the
  graveyard. That effect is 'If this permanent would be put into a graveyard
  from the battlefield, exile it instead.'"
- **CR 700.4** - "The term dies means 'is put into a graveyard from the
  battlefield.'" Exiled instead, it never died.
- **CR 614.1a** - "Effects that use the word 'instead' are replacement
  effects."

Scavenger's Talent's level 3 is the printing that puts one on (see
`test_conditional_sacrifice_clauses.py`); the counter is placed directly here,
the staging this file needs to look at the replacement alone.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _board() -> Scenario:
    return Scenario().player("alice", battlefield=["Grizzly Bears", "Goblin Guide"]).player("bob")


def test_a_destroyed_creature_with_a_finality_counter_is_exiled_instead():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    scenario.game.add_counters(bears, "finality")

    scenario.game.destroy(bears)

    assert bears.zone is Zone.EXILE
    assert bears not in scenario.player("alice").graveyard


def test_a_sacrificed_creature_with_a_finality_counter_is_exiled_instead():
    """Any route to the graveyard from the battlefield, not only destruction."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    scenario.game.add_counters(bears, "finality")

    scenario.game.sacrifice(bears)

    assert bears.zone is Zone.EXILE


def test_a_creature_without_the_counter_still_goes_to_the_graveyard():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    goblin = scenario.creature("Goblin Guide")
    scenario.game.add_counters(bears, "finality")

    scenario.game.destroy(goblin)

    assert goblin.zone is Zone.GRAVEYARD


def test_lethal_damage_with_a_finality_counter_exiles_through_state_based_actions():
    """CR 704.5g destroys it; CR 122.1h still sends it to exile."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Grizzly Bears", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, "finality")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[bears])

    assert bears.zone is Zone.EXILE
