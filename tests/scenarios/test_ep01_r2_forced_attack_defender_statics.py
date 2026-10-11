"""Statics that name who must be attacked (EP-01 round 2, T8).

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 508.1d** - a requirement is obeyed as far as possible without
  disobeying a restriction; the number obeyed is maximised.
- **CR 508.1b** - the active player chooses what each attacker attacks.

Printings: Public Enemy ("All creatures attack enchanted creature's controller
each combat if able.") and Trove of Temptation ("Each opponent must attack you
or a planeswalker you control with at least one creature each combat if
able.").
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _public_enemy(*, bob_extra=(), alice_extra=()):
    scenario = (
        Scenario()
        .player("bob", battlefield=["Goblin Guide", *bob_extra])
        .player("alice", battlefield=["Public Enemy", "Grizzly Bears", *alice_extra])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.find("Public Enemy", scenario.game.battlefield[0].zone, "alice").attach_to(
        scenario.creature("Grizzly Bears", "alice")
    )
    scenario.creature("Goblin Guide", "bob").summoning_sick = False
    return scenario


def test_public_enemy_forces_an_attack_on_the_enchanted_creatures_controller():
    scenario = _public_enemy()
    guide = scenario.creature("Goblin Guide", "bob")
    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with()
    scenario.attack_with(guide, defending="alice")
    assert scenario.attackers() == [guide]


def test_public_enemy_refuses_an_attack_on_the_planeswalker_when_the_player_can_be_attacked():
    scenario = _public_enemy(alice_extra=["Ajani Unrelenting"])
    guide = scenario.creature("Goblin Guide", "bob")
    walker = scenario.creature("Ajani Unrelenting", "alice")
    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(guide, defending=walker)
    scenario.attack_with(guide, defending="alice")


def test_a_creature_that_cannot_attack_is_not_forced_by_public_enemy():
    scenario = _public_enemy()
    scenario.creature("Goblin Guide", "bob").tap()
    scenario.attack_with()
    assert scenario.attackers() == []


def test_without_public_enemy_nothing_forces_the_attack():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Goblin Guide"])
        .player("alice", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with()
    assert scenario.attackers() == []


# ---- Trove of Temptation ---------------------------------------------------------


def _trove(*, alice_extra=(), bob=("Goblin Guide",)):
    scenario = (
        Scenario()
        .player("bob", battlefield=list(bob))
        .player("alice", battlefield=["Trove of Temptation", *alice_extra])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    for name in bob:
        scenario.creature(name, "bob").summoning_sick = False
    return scenario


def test_trove_of_temptation_refuses_an_empty_declaration():
    scenario = _trove()
    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with()


def test_trove_of_temptation_is_satisfied_by_one_attacker_at_its_controller():
    scenario = _trove(bob=("Goblin Guide", "Grizzly Bears"))
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.attack_with(guide, defending="alice")
    assert scenario.attackers() == [guide]


def test_trove_of_temptation_is_satisfied_by_an_attack_on_its_controllers_planeswalker():
    scenario = _trove(alice_extra=["Ajani Unrelenting"])
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.attack_with(guide, defending=scenario.creature("Ajani Unrelenting", "alice"))
    assert scenario.attackers() == [guide]


def test_trove_of_temptation_does_not_bind_an_opponent_with_nothing_able_to_attack():
    scenario = _trove()
    scenario.creature("Goblin Guide", "bob").tap()
    scenario.attack_with()
    assert scenario.attackers() == []
