"""A DIES condition whose subject is a subtype followed by a card type -
Boggart Mischief's "Whenever a Goblin creature you control dies, each
opponent loses 1 life and you gain 1 life." CR 205.3m: Goblin is a creature
type, and only an object with that subtype satisfies the subject (CR 603.2:
an ability triggers only when its trigger event occurs). The card-type word
after the subtype narrows the object further; it does not replace the
subtype requirement.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

MISCHIEF = "Boggart Mischief"


def _board(creature: str):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[MISCHIEF, creature])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_goblin_creature_dying_triggers():
    scenario = _board("Goblin Guide")
    scenario.game.destroy(scenario.creature("Goblin Guide", "alice"))
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.player("alice").life == 21
    assert scenario.player("bob").life == 19


def test_a_non_goblin_creature_dying_does_not_trigger():
    scenario = _board("Grizzly Bears")
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    scenario.game.put_triggers_on_stack()

    assert not scenario.game.stack
    assert scenario.player("alice").life == 20
