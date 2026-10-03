"""Scenario: "can't block this combat" - a block restriction (CR 509.1b) that
lasts until the end of the combat phase, not until the end of the turn.

- **CR 509.1b** - the defending player checks each creature for restrictions
  ("effects that say a creature can't block"); disobeying one makes the
  declaration illegal.
- **CR 611.2a** - a resolved effect lasts as long as it says.
- **CR 500.5a** / **CR 511.2** - effects that last "until end of combat"
  expire at the end of the combat phase, not at the beginning of the end of
  combat step. "This combat" names the same span: the combat phase the
  effect was created in.
- **CR 603.2c** - "Whenever two or more creatures your opponents control
  attack" is one trigger for the whole declaration, counted over it.

Forgestoker Dragon is the reported card: an activated ability whose second
sentence is an anaphoric rider on its own damage target ("That creature
can't block this combat."). Flummoxed Cyclops is the second printing with
differing wording: a self-reference ("this creature can't block this
combat") as the whole effect of a batched attack trigger with a count
("two or more"), not a rider.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _cant_block(scenario: Scenario, state) -> bool:
    board = scenario.game.continuous_effects.board(scenario.game.battlefield)
    return "This creature can't block." in board.of(state).abilities


def _to_postcombat_main(scenario: Scenario) -> None:
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()


# -- Forgestoker Dragon: "That creature can't block this combat." -------------


def _dragon(*bob: str) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Forgestoker Dragon", "Mountain", "Mountain", "Mountain", "Mountain"],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _ping(scenario: Scenario, target) -> None:
    dragon = scenario.creature("Forgestoker Dragon", "alice")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.activate(dragon, *mountains, targets=[target])
    scenario.pass_until_resolved()


def test_the_damaged_creature_cannot_block_this_combat():
    scenario = _dragon("Serra Angel")
    dragon = scenario.creature("Forgestoker Dragon", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.attack_with(dragon)

    _ping(scenario, angel)

    assert angel.damage == 1
    assert _cant_block(scenario, angel)
    with pytest.raises(ValueError):
        scenario.block(dragon, angel)


def test_an_untouched_creature_still_blocks():
    scenario = _dragon("Serra Angel", "Grizzly Bears")
    dragon = scenario.creature("Forgestoker Dragon", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(dragon)

    _ping(scenario, bears)

    assert _cant_block(scenario, bears)
    assert not _cant_block(scenario, angel)
    scenario.block(dragon, angel)
    assert angel in scenario.blockers()


def test_the_restriction_ends_with_the_combat_phase_not_the_turn():
    scenario = _dragon("Serra Angel")
    dragon = scenario.creature("Forgestoker Dragon", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.attack_with(dragon)
    _ping(scenario, angel)
    scenario.no_blocks()

    _to_postcombat_main(scenario)

    assert angel.zone is Zone.BATTLEFIELD
    assert not _cant_block(scenario, angel)


def test_a_target_that_dies_to_the_damage_restricts_nothing_else():
    """The rider is bound to the one object it was put on; once that object
    is gone (CR 400.7) no other creature inherits the restriction."""
    scenario = _dragon("Memnite", "Serra Angel")
    dragon = scenario.creature("Forgestoker Dragon", "alice")
    memnite = scenario.creature("Memnite", "bob")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.attack_with(dragon)

    _ping(scenario, memnite)

    assert memnite.zone is Zone.GRAVEYARD
    assert not _cant_block(scenario, angel)
    scenario.block(dragon, angel)
    assert angel in scenario.blockers()


def test_the_ability_is_refused_when_the_dragon_is_not_attacking():
    scenario = _dragon("Serra Angel")
    dragon = scenario.creature("Forgestoker Dragon", "alice")
    assert scenario.why_cannot_activate(dragon, 0) is not None


# -- Flummoxed Cyclops: "this creature can't block this combat." ---------------


def _cyclops(*attackers: str) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=list(attackers), library=["Mountain"] * 5)
        .player("bob", battlefield=["Flummoxed Cyclops"], library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_two_attackers_keep_the_cyclops_from_blocking():
    scenario = _cyclops("Grizzly Bears", "Memnite")
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")
    cyclops = scenario.creature("Flummoxed Cyclops", "bob")

    scenario.attack_with(bears, memnite)
    scenario.pass_until_resolved()

    assert _cant_block(scenario, cyclops)
    with pytest.raises(ValueError):
        scenario.block(bears, cyclops)


def test_one_attacker_is_not_enough():
    scenario = _cyclops("Grizzly Bears", "Memnite")
    bears = scenario.creature("Grizzly Bears", "alice")
    cyclops = scenario.creature("Flummoxed Cyclops", "bob")

    scenario.attack_with(bears)
    scenario.pass_until_resolved()

    assert not _cant_block(scenario, cyclops)
    scenario.block(bears, cyclops)
    assert cyclops in scenario.blockers()


def test_the_cyclops_blocks_again_after_combat():
    scenario = _cyclops("Grizzly Bears", "Memnite")
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")
    cyclops = scenario.creature("Flummoxed Cyclops", "bob")
    scenario.attack_with(bears, memnite)
    scenario.pass_until_resolved()
    scenario.no_blocks()

    _to_postcombat_main(scenario)

    assert not _cant_block(scenario, cyclops)
