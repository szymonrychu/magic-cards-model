"""Scenario: Umbra Mystic - "Auras attached to permanents you control have
umbra armor."

CR 702.89a: umbra armor means "If enchanted permanent would be destroyed,
instead remove all damage marked on it and destroy this Aura." CR 613.1f: the
grant is a layer 6 ability-adding effect, so the Aura really has the ability
(and the replacement reads the computed ability list); CR 611.3a: the group
("Auras attached to permanents you control") is asked afresh on every
computation, so it follows the attachment and the Aura's host's controller.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

MYSTIC = "Umbra Mystic"


def _board(mystic_owner, bears_owner):
    players = {
        "alice": {"hand": ["Lightning Bolt"], "battlefield": ["Mountain"]},
        "bob": {"battlefield": []},
    }
    if mystic_owner is not None:
        players[mystic_owner]["battlefield"] = [*players[mystic_owner]["battlefield"], MYSTIC]
    players[bears_owner]["battlefield"] = [
        *players[bears_owner]["battlefield"],
        "Grizzly Bears",
        "Rancor",
    ]
    scenario = (
        Scenario()
        .player("alice", **players["alice"])
        .player("bob", **players["bob"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", bears_owner)
    rancor = scenario.creature("Rancor", bears_owner)
    rancor.attach_to(bears)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, bears, rancor


def _bolt(scenario, bears):
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])


def test_an_aura_on_my_creature_has_umbra_armor_and_eats_the_destruction():
    scenario, bears, rancor = _board("bob", "bob")

    assert "umbra armor" in " ".join(scenario.game.characteristics_of(rancor).abilities).lower()
    _bolt(scenario, bears)

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0
    assert rancor.zone is not Zone.BATTLEFIELD


def test_without_the_mystic_the_creature_dies():
    scenario, bears, rancor = _board(None, "bob")

    assert "umbra armor" not in " ".join(scenario.game.characteristics_of(rancor).abilities).lower()
    _bolt(scenario, bears)

    assert bears.zone is Zone.GRAVEYARD


def test_an_aura_on_an_opponents_creature_does_not_get_it():
    """Mystic is alice's; Rancor sits on bob's creature, so it is not "attached
    to a permanent you control" for alice, nor for bob (who does not control a
    Mystic)."""
    scenario, bears, rancor = _board("alice", "bob")

    assert "umbra armor" not in " ".join(scenario.game.characteristics_of(rancor).abilities).lower()
