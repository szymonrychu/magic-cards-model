"""Scenario: corner cases of "the number of differently named lands you control"
(the Star Trek strange new worlds count), read here through Captain Pike,
Fullness of Time's characteristic-defining power and toughness (sublayer 7a).

CR 201.2: names are compared as the board computes them, so a land whose name
an effect changed (CR 612.8, layer 3) counts under its new name. CR 201.2a: an
object with no name doesn't have the same name as any other object.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import (
    ContinuousEffect,
    Duration,
    Layer,
    only_this_incarnation,
)
from magic_cards_model.machines.layers.model import SetName
from magic_cards_model.models import Type
from magic_cards_model.models.token import TokenDefinition, create_tokens
from tests.scenarios.harness import Scenario

PIKE = "Captain Pike, Fullness of Time"
NEW_PLANET = TokenDefinition(
    types=(Type.LAND,), subtypes=("Planet",), name="New Planet", rules_text="{T}: Add {C}."
)


def _pike_scenario(alice_battlefield: list[str], bob_battlefield: list[str] | None = None):
    scenario = (
        Scenario()
        .player("alice", battlefield=[PIKE, *alice_battlefield])
        .player("bob", battlefield=bob_battlefield or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(PIKE, "alice")


def test_duplicate_land_names_count_once() -> None:
    _scenario, pike = _pike_scenario(["Forest"] * 4)
    assert (pike.power, pike.toughness) == (1, 1)


def test_nonland_permanents_and_opposing_lands_are_not_counted() -> None:
    _scenario, pike = _pike_scenario(
        ["Forest", "Island", "Grizzly Bears", "Sol Ring"], ["Swamp", "Mountain"]
    )
    assert (pike.power, pike.toughness) == (2, 2)


def test_new_planet_tokens_count_once_and_apart_from_basic_lands() -> None:
    scenario, pike = _pike_scenario(["Forest"])
    create_tokens(scenario.game, NEW_PLANET, "alice", 3)
    assert (pike.power, pike.toughness) == (2, 2), "Forest plus one name shared by three tokens"
    create_tokens(scenario.game, NEW_PLANET, "bob", 2)
    assert (pike.power, pike.toughness) == (2, 2), "the opponent's tokens are not yours"


def _rename(scenario, land, new_name: str) -> None:
    store = scenario.game.continuous_effects
    # Ids are minted from the game's own allocator so a replay mints the same ones.
    with scenario.game._id_allocator_scope():  # noqa: SLF001
        effect = ContinuousEffect(
            description=f"test: {land.name} is named {new_name}",
            layer=Layer.TEXT,
            timestamp=store.tick(),
            duration=Duration.INDEFINITE,
            selector=only_this_incarnation(land, land.zone_change_stamp),
            modification=SetName(name=new_name),
        )
    store.add(effect, game=scenario.game)


def test_a_land_that_changes_name_counts_under_its_new_name() -> None:
    scenario, pike = _pike_scenario(["Forest", "Forest", "Island"])
    assert (pike.power, pike.toughness) == (2, 2)
    forests = [c for c in scenario.game.permanents_controlled_by("alice") if c.name == "Forest"]
    _rename(scenario, forests[0], "Mountain")
    assert (pike.power, pike.toughness) == (3, 3), "Mountain, Forest, Island"
    _rename(scenario, forests[1], "Mountain")
    assert (pike.power, pike.toughness) == (2, 2), "both renamed Forests share Mountain"
