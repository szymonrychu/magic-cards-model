"""Scenario: a mass pump followed by a second, filtered group grant in the same
resolution - "<Kithkin|Warrior|White|Colorless> creatures you control (also)
gain <keyword> until end of turn."

Cards: Gallant Fowlknight (Kithkin, first strike; an ETB trigger), Rush of
Battle (Warriors, lifelink), Sanctified Charge (white creatures, first
strike), Swarm Surge (colorless creatures, first strike).

Rules verified with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 611.2c** - each group is fixed when its effect begins: a creature that
  enters afterwards gets neither the pump nor the grant.
- **CR 608.2c** - the second sentence is a further instruction, not a
  replacement of the first.
- **CR 105.2c** - an object with no colour is colourless (Swarm Surge's
  subset; Devoid makes a coloured-cost card colourless).
- **CR 205.3m** - Kithkin and Warrior are creature types.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def computed(scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _board(hand, lands, mine, theirs=("Goldmeadow Harrier", "Savannah Lions")):
    scenario = (
        Scenario()
        .player("alice", hand=hand, battlefield=[*mine, *lands])
        .player("bob", battlefield=list(theirs))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


@pytest.mark.parametrize(
    "name", ["Gallant Fowlknight", "Rush of Battle", "Sanctified Charge", "Swarm Surge"]
)
def test_subset_clause_is_handled(name):
    clauses = classify_clauses(card(name))
    assert all(c.category == HANDLED for c in clauses), [(c.text, c.category) for c in clauses]


def test_rush_of_battle_grants_lifelink_to_warriors_only():
    scenario = _board(
        ["Rush of Battle"],
        ["Plains"] * 4,
        ["Bloodstone Goblin", "Grizzly Bears"],
        theirs=["Bloodstone Goblin"],
    )
    goblin = scenario.creature("Bloodstone Goblin", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    foe = scenario.creature("Bloodstone Goblin", "bob")
    scenario.cast_and_resolve("Rush of Battle", *scenario.untapped_sources(*["Plains"] * 4))

    assert has_keyword(goblin, "lifelink", scenario.game)
    assert not has_keyword(bears, "lifelink", scenario.game), "subset filter false"
    assert not has_keyword(foe, "lifelink", scenario.game), "opponent untouched"
    assert computed(scenario).of(bears).power_toughness == (4, 3), "the plain +2/+1 still applies"
    assert computed(scenario).of(goblin).power_toughness == (4, 3)


def test_sanctified_charge_grants_first_strike_to_white_creatures_only():
    scenario = _board(["Sanctified Charge"], ["Plains"] * 5, ["Savannah Lions", "Grizzly Bears"])
    lions = scenario.creature("Savannah Lions", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    foe = scenario.creature("Savannah Lions", "bob")
    scenario.cast_and_resolve("Sanctified Charge", *scenario.untapped_sources(*["Plains"] * 5))

    assert has_keyword(lions, "first strike", scenario.game)
    assert not has_keyword(bears, "first strike", scenario.game)
    assert not has_keyword(foe, "first strike", scenario.game)
    assert computed(scenario).of(lions).power_toughness == (4, 2)
    assert computed(scenario).of(bears).power_toughness == (4, 3)
    assert computed(scenario).of(foe).power_toughness == (2, 1)


def test_swarm_surge_grants_first_strike_to_colorless_creatures_only():
    scenario = _board(["Swarm Surge"], ["Swamp"] * 3, ["Ornithopter", "Grizzly Bears"])
    thopter = scenario.creature("Ornithopter", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Swarm Surge", *scenario.untapped_sources(*["Swamp"] * 3))

    assert has_keyword(thopter, "first strike", scenario.game)
    assert not has_keyword(bears, "first strike", scenario.game)
    assert computed(scenario).of(thopter).power_toughness == (2, 2)
    assert computed(scenario).of(bears).power_toughness == (4, 2)


def test_creature_entering_after_resolution_gets_neither_pump_nor_grant():
    scenario = _board(["Sanctified Charge", "Savannah Lions"], ["Plains"] * 5, ["Savannah Lions"])
    scenario.cast_and_resolve("Sanctified Charge", *scenario.untapped_sources(*["Plains"] * 5))
    late = scenario.put_onto_battlefield("Savannah Lions", "alice")

    assert not has_keyword(late, "first strike", scenario.game)
    assert computed(scenario).of(late).power_toughness == (2, 1)


def test_gallant_fowlknight_enters_pumping_everyone_and_granting_kithkin():
    scenario = _board(
        ["Gallant Fowlknight"],
        ["Plains"] * 4,
        ["Goldmeadow Harrier", "Grizzly Bears"],
        theirs=["Goldmeadow Harrier"],
    )
    harrier = scenario.creature("Goldmeadow Harrier", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    foe = scenario.creature("Goldmeadow Harrier", "bob")
    scenario.cast_and_resolve("Gallant Fowlknight", *scenario.untapped_sources(*["Plains"] * 4))
    _resolve_everything(scenario)
    fowlknight = scenario.creature("Gallant Fowlknight", "alice")

    assert has_keyword(harrier, "first strike", scenario.game)
    assert has_keyword(fowlknight, "first strike", scenario.game), "it is a Kithkin itself"
    assert not has_keyword(bears, "first strike", scenario.game)
    assert not has_keyword(foe, "first strike", scenario.game)
    assert computed(scenario).of(bears).power_toughness == (3, 2)
    assert computed(scenario).of(foe).power_toughness == (1, 1)
