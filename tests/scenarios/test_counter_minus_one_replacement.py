"""Counter-quantity replacement effects (CR 614.1a, 614.5, 122.6, 107.1b).

Vizier of Remedies: "If one or more -1/-1 counters would be put on a creature
you control, that many -1/-1 counters minus one are put on it instead." Kami
of Whispered Hopes (the proof printing - neither a listed card nor in any api
deck, and worded the other way: "a permanent you control", "plus one", "on
that permanent"): "If one or more +1/+1 counters would be put on a permanent
you control, that many plus one +1/+1 counters are put on that permanent
instead." One reader (`read_counter_amount`) reads both.

Every CR number here was read in full with `mise run rules:find`:

- **CR 614.1a** - effects that use the word "instead" are replacement effects.
- **CR 614.5** - a replacement effect gets one opportunity at an event, so two
  Viziers take off one counter each.
- **CR 122.6** - counters put on an object include those it enters with.
- **CR 107.1b** - a calculation that would yield a negative number uses zero.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice: list[str], bob: list[str] | None = None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice)
        .player("bob", battlefield=bob or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Vizier of Remedies ---------------------------------------------------------


def test_vizier_takes_one_off_several_counters():
    scenario = _board(["Vizier of Remedies", "Primeval Titan"])
    titan = scenario.creature("Primeval Titan")

    scenario.game.add_counters(titan, Counter.MINUS_ONE, 3)

    assert titan.counter_count(Counter.MINUS_ONE) == 2


def test_vizier_turns_a_single_counter_into_none():
    """CR 107.1b: one minus one is zero, never fewer."""
    scenario = _board(["Vizier of Remedies", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")

    scenario.game.add_counters(bears, Counter.MINUS_ONE, 1)

    assert bears.counter_count(Counter.MINUS_ONE) == 0
    assert (bears.power, bears.toughness) == (2, 2)


def test_vizier_protects_itself():
    scenario = _board(["Vizier of Remedies"])
    vizier = scenario.creature("Vizier of Remedies")

    scenario.game.add_counters(vizier, Counter.MINUS_ONE, 2)

    assert vizier.counter_count(Counter.MINUS_ONE) == 1


def test_two_viziers_each_take_one_off():
    """CR 614.5: two Viziers are two effects, each applied once - three
    counters become one."""
    scenario = _board(["Vizier of Remedies", "Vizier of Remedies", "Primeval Titan"])
    titan = scenario.creature("Primeval Titan")

    scenario.game.add_counters(titan, Counter.MINUS_ONE, 3)

    assert titan.counter_count(Counter.MINUS_ONE) == 1


def test_vizier_leaves_other_counter_kinds_alone():
    scenario = _board(["Vizier of Remedies", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)

    assert bears.counter_count(Counter.PLUS_ONE) == 2


def test_vizier_leaves_an_opponents_creature_alone():
    scenario = _board(["Vizier of Remedies"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.add_counters(bears, Counter.MINUS_ONE, 1)

    assert bears.counter_count(Counter.MINUS_ONE) == 1


def test_vizier_reduces_a_cost_counter():
    """Devoted Druid's "Put a -1/-1 counter on this creature" cost puts none."""
    scenario = _board(["Vizier of Remedies", "Devoted Druid"])
    druid = scenario.creature("Devoted Druid")
    druid.tap()

    scenario.activate(druid, index=1)
    scenario.pass_until_resolved()

    assert druid.counter_count(Counter.MINUS_ONE) == 0
    assert not druid.tapped


# -- Kami of Whispered Hopes (the proof printing) ---------------------------------


def test_kami_adds_one_to_counters_on_a_permanent_you_control():
    scenario = _board(["Kami of Whispered Hopes", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)

    assert bears.counter_count(Counter.PLUS_ONE) == 2


def test_kami_adds_one_to_an_activated_abilitys_counter():
    """Hangarback Walker's own "{1}, {T}: Put a +1/+1 counter on this
    creature." puts two."""
    scenario = _board(["Kami of Whispered Hopes", "Hangarback Walker", "Forest"])
    walker = scenario.creature("Hangarback Walker")
    scenario.game.add_counters(walker, Counter.PLUS_ONE, 1)  # 1 plus one = 2
    assert walker.counter_count(Counter.PLUS_ONE) == 2

    scenario.activate(walker, *scenario.untapped_sources("Forest"))
    scenario.pass_until_resolved()

    assert walker.counter_count(Counter.PLUS_ONE) == 4


def test_kami_leaves_minus_counters_and_opponents_alone():
    scenario = _board(["Kami of Whispered Hopes", "Primeval Titan"], ["Grizzly Bears"])
    titan = scenario.creature("Primeval Titan")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.add_counters(titan, Counter.MINUS_ONE, 1)
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)

    assert titan.counter_count(Counter.MINUS_ONE) == 1
    assert bears.counter_count(Counter.PLUS_ONE) == 1


# -- the audit ----------------------------------------------------------------


@pytest.mark.parametrize("name", ["Vizier of Remedies", "Kami of Whispered Hopes"])
def test_every_replacement_clause_is_handled(name):
    """Kami's other line is a mana ability (`{T}: Add X mana ...`), not a
    clause this audit reports."""
    outcomes = classify_clauses(card(name))
    assert outcomes
    assert {outcome.category for outcome in outcomes} == {HANDLED}, outcomes
