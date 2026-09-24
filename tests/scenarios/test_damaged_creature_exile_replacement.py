"""The resolution-created "If a creature dealt damage this way would die this
turn, exile it instead" (CR 614.1a, 700.4, 514.2).

Anger of the Gods: "Anger of the Gods deals 3 damage to each creature. If a
creature dealt damage this way would die this turn, exile it instead."
Underworld Fires (the proof printing - neither a listed card nor in any api
deck, and worded differently: "each creature and each planeswalker", "a
permanent dealt damage this way").

Every CR number here was read in full with `mise run rules:find`:

- **CR 614.1a** - effects that use the word "instead" are replacement effects.
- **CR 700.4** - "dies" means "is put into a graveyard from the battlefield".
- **CR 603.2g** - an event that's replaced won't trigger anything.
- **CR 514.2** - at cleanup all "this turn" effects end.
- **CR 120.3** - what damage does; damage a protection prevents is never dealt.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(spell: str, bob: list[str], *, lands: int = 4, alice: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[spell, "Lightning Bolt"],
            battlefield=["Mountain"] * lands + (alice or []),
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=bob, library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, spell: str) -> None:
    scenario.cast_and_resolve(spell, auto=True)
    scenario.state_based_actions()


def test_anger_exiles_the_creatures_it_kills():
    scenario = _board("Anger of the Gods", ["Grizzly Bears", "Memnite"])
    bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "bob")

    _cast(scenario, "Anger of the Gods")

    assert bears.zone is Zone.EXILE
    assert memnite.zone is Zone.EXILE
    assert scenario.player("bob").graveyard == []


def test_the_spell_itself_still_goes_to_the_graveyard():
    """The replacement names creatures dealt damage; the sorcery resolving is
    not one of them."""
    scenario = _board("Anger of the Gods", ["Grizzly Bears"])

    _cast(scenario, "Anger of the Gods")

    assert [state.name for state in scenario.player("alice").graveyard] == ["Anger of the Gods"]


def test_a_survivor_that_dies_later_this_turn_is_exiled():
    """ "Would die this turn": Primeval Titan survives 3 damage, then a
    Lightning Bolt the same turn finishes it - it is exiled all the same."""
    scenario = _board("Anger of the Gods", ["Primeval Titan"], lands=5)
    titan = scenario.creature("Primeval Titan", "bob")

    _cast(scenario, "Anger of the Gods")
    assert titan.zone is Zone.BATTLEFIELD

    scenario.cast_and_resolve("Lightning Bolt", auto=True, targets=[titan])
    scenario.state_based_actions()

    assert titan.zone is Zone.EXILE


def test_a_survivor_destroyed_this_turn_is_exiled_too():
    """Any way of dying counts (CR 700.4), not only lethal damage."""
    scenario = _board("Anger of the Gods", ["Primeval Titan"])
    titan = scenario.creature("Primeval Titan", "bob")

    _cast(scenario, "Anger of the Gods")
    scenario.game.destroy(titan)

    assert titan.zone is Zone.EXILE


def test_the_replacement_ends_with_the_turn():
    """CR 514.2: the effect ends at cleanup, so the survivor dying on a later
    turn goes to its owner's graveyard."""
    scenario = _board("Anger of the Gods", ["Primeval Titan"])
    titan = scenario.creature("Primeval Titan", "bob")
    _cast(scenario, "Anger of the Gods")

    while scenario.turn.active_player == "alice":
        scenario.advance()
    scenario.game.destroy(titan)

    assert titan.zone is Zone.GRAVEYARD


def test_a_creature_dealt_no_damage_is_not_marked():
    """Sanctifier en-Vec's protection from red prevents Anger's damage, so it
    was not "dealt damage this way" and dies normally afterwards."""
    scenario = _board("Anger of the Gods", ["Sanctifier en-Vec"])
    sanctifier = scenario.creature("Sanctifier en-Vec", "bob")

    _cast(scenario, "Anger of the Gods")
    assert sanctifier.zone is Zone.BATTLEFIELD
    scenario.game.destroy(sanctifier)

    assert sanctifier.zone is Zone.GRAVEYARD


def test_a_creature_arriving_afterwards_is_not_marked():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Anger of the Gods", "Grizzly Bears"],
            battlefield=["Mountain"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast(scenario, "Anger of the Gods")
    bears = scenario.put_onto_battlefield("Grizzly Bears")

    scenario.game.destroy(bears)

    assert bears.zone is Zone.GRAVEYARD


def test_an_exiled_creature_never_died_so_its_dies_trigger_never_fires():
    """CR 603.2g: Hangarback Walker's "When this creature dies" watches an
    event that was replaced - no Thopters."""
    scenario = _board("Anger of the Gods", ["Hangarback Walker"])
    walker = scenario.creature("Hangarback Walker", "bob")
    scenario.game.add_counters(walker, Counter.PLUS_ONE, 2)

    _cast(scenario, "Anger of the Gods")

    assert walker.zone is Zone.EXILE
    assert scenario.pending_triggers == []
    assert scenario.game.permanents_controlled_by("bob") == []


def test_casters_own_creatures_are_exiled_as_well():
    """ "Each creature" includes the caster's."""
    scenario = _board("Anger of the Gods", [], alice=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast(scenario, "Anger of the Gods")

    assert bears.zone is Zone.EXILE


# -- Underworld Fires (the proof printing) -------------------------------------


def test_underworld_fires_exiles_a_creature_it_kills():
    scenario = _board("Underworld Fires", ["Memnite", "Grizzly Bears"], lands=3)
    memnite = scenario.creature("Memnite", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast(scenario, "Underworld Fires")

    assert memnite.zone is Zone.EXILE
    assert bears.zone is Zone.BATTLEFIELD


def test_underworld_fires_exiles_a_planeswalker_it_kills():
    """ "A permanent dealt damage this way": the planeswalker losing its last
    loyalty counter to the damage (CR 120.3c) is put into the graveyard from
    the battlefield - it dies (CR 700.4) and is exiled instead."""
    scenario = _board("Underworld Fires", ["Wrenn and Six"], lands=3)
    wrenn = scenario.find("Wrenn and Six", Zone.BATTLEFIELD, "bob")
    wrenn.remove_counters(Counter.LOYALTY, wrenn.counter_count(Counter.LOYALTY) - 1)

    _cast(scenario, "Underworld Fires")

    assert wrenn.zone is Zone.EXILE


# -- the audit ----------------------------------------------------------------


@pytest.mark.parametrize("name", ["Anger of the Gods", "Underworld Fires"])
def test_every_clause_is_handled(name):
    outcomes = classify_clauses(card(name))
    assert outcomes
    assert {outcome.category for outcome in outcomes} == {HANDLED}, outcomes
