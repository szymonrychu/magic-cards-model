"""A dies trigger conditioned on "a creature you control with one or more
counters on it" whose effect then says "that many" (Shadow Urchin: "Whenever
a creature you control with one or more counters on it dies, exile that many
cards from the top of your library. Until your next end step, you may play
those cards.").

The only number the trigger condition names is the dying creature's counters,
so "that many" is the number of counters it had as it last existed on the
battlefield (CR 603.10a's look-back for a leaves-the-battlefield trigger;
CR 608.2h: the number is determined as the effect is applied).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

URCHIN = "Shadow Urchin"


def _board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[URCHIN, "Grizzly Bears"],
            library=["Forest", "Island", "Swamp", "Mountain", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_that_many_is_the_dying_creatures_counters():
    scenario = _board()
    bears = scenario.creature("Grizzly Bears")
    bears.counters.add(Counter.PLUS_ONE)
    bears.counters.add(Counter.PLUS_ONE)
    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    alice = scenario.player("alice")
    assert len(alice.library) == 3
    assert not scenario.game.unmodeled_trigger_effect_notices


def test_counters_of_different_kinds_all_count():
    scenario = _board()
    bears = scenario.creature("Grizzly Bears")
    bears.counters.add(Counter.PLUS_ONE)
    bears.counters.add(Counter.PLUS_ONE)
    bears.counters.add("stun")
    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert len(scenario.player("alice").library) == 2
    assert not scenario.game.unmodeled_trigger_effect_notices


def test_a_creature_without_counters_dying_does_not_trigger():
    scenario = _board()
    scenario.game.destroy(scenario.creature("Grizzly Bears"))
    scenario.game.put_triggers_on_stack()

    assert not scenario.game.stack
    assert len(scenario.player("alice").library) == 5
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice") is not None
