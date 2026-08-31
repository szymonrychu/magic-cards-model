"""A dies trigger's "it", naming the ability's own source (CR 603.10a's
look-back), read off two different destinations: `_parse_exile_dead_self_
clause`'s "exile it" (Ancient Adamantoise) and `_parse_return_dead_self_to_
hand_clause`'s "return it to its owner's hand" (Rancor).

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 700.4** - "dies" means "is put into a graveyard from the battlefield" -
  naming no card type, so an Aura dies exactly like a creature does.
- **CR 603.10a** - a dies trigger looks back in time at the object as it last
  existed, which is what lets its own ability still find and move "it" once
  the object itself already sits in the graveyard.
- **CR 704.5m** - "If an Aura is attached to an illegal object or player, ...
  that Aura is put into its owner's graveyard" - the state-based action that
  puts Rancor there when its enchanted creature dies out from under it.
- **CR 108.3** - an owner is who a card started the game belonging to, which
  is where Rancor's own "its owner's hand" sends it, not necessarily its
  controller (irrelevant to a mono-controlled scenario, but the rule this
  reads).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_ancient_adamantoise_exiles_itself_and_makes_ten_treasures():
    """ "When this creature dies, exile it and create ten tapped Treasure
    tokens." Both halves of one CR 608.2c instruction."""
    scenario = Scenario().player("alice", battlefield=["Ancient Adamantoise"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    turtle = scenario.creature("Ancient Adamantoise", "alice")

    scenario.game.destroy(turtle)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert turtle.zone is Zone.EXILE
    treasures = [
        state
        for state in scenario.game.battlefield
        if state.name == "Treasure Token" and state.controller == "alice"
    ]
    assert len(treasures) == 10
    assert all(state.tapped for state in treasures)


def test_rancor_returns_to_its_owners_hand_when_it_dies_directly():
    """The plain case: Rancor destroyed on its own, not carried off by its
    enchanted creature."""
    scenario = (
        Scenario()
        .player("alice", hand=["Rancor"], battlefield=["Forest", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest")
    rancor = scenario.cast_and_resolve("Rancor", forest, targets=[bears])
    assert rancor.zone is Zone.BATTLEFIELD

    scenario.game.destroy(rancor)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert rancor.zone is Zone.HAND
    assert rancor in scenario.player("alice").hand


def test_rancor_returns_to_hand_when_its_enchanted_creature_dies_too():
    """CR 704.5m: killing the creature Rancor is attached to leaves Rancor
    attached to nothing, a state-based action puts it into the graveyard for
    that reason alone, and its own dies trigger still fires and returns it -
    the corner case `_parse_return_dead_self_to_hand_clause`'s docstring
    calls out: Rancor never dies "directly" here at all."""
    scenario = (
        Scenario()
        .player("alice", hand=["Rancor"], battlefield=["Forest", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest")
    rancor = scenario.cast_and_resolve("Rancor", forest, targets=[bears])

    scenario.game.destroy(bears)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert rancor.zone is Zone.HAND
    assert rancor in scenario.player("alice").hand
