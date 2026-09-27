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


# -- a named counter kind (Chevill, Bane of Monsters) -------------------------
#
# "Whenever a permanent an opponent controls with a bounty counter on it dies,
# you gain 3 life and draw a card." The qualifier names a kind (CR 122.1), and
# the dying permanent must be an opponent's.

CHEVILL = "Chevill, Bane of Monsters"


def _chevill_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[CHEVILL, "Grizzly Bears"], library=["Forest"] * 5)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_an_opponents_permanent_with_a_bounty_counter_dying_triggers():
    scenario = _chevill_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.counters.add("bounty")
    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.player("alice").life == 23
    assert len(scenario.player("alice").hand) == 1


def test_an_opponents_permanent_without_a_bounty_counter_does_not_trigger():
    scenario = _chevill_board()
    scenario.game.destroy(scenario.creature("Grizzly Bears", "bob"))
    scenario.game.put_triggers_on_stack()

    assert not scenario.game.stack


def test_a_permanent_of_your_own_with_a_bounty_counter_does_not_trigger():
    scenario = _chevill_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.counters.add("bounty")
    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert not scenario.game.stack
