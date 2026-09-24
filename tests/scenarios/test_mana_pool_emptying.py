"""Mana pools empty as every step and phase ends (CR 500.5, 703.4q).

The user's report: mana floated during upkeep was still spendable in the
precombat main phase. CR 500.5 ends that - "As a step or phase ends ... Then
any unspent mana left in a player's mana pool empties" - so what floats during
a step is spendable until that step ends, and upkeep mana never reaches the
main phase. CR 106.4: the player is said to lose this mana.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.models import Color, Zone

from .harness import PlayedScenario, Scenario


def announce(scenario: PlayedScenario, name: str, username: str = "alice") -> Casting:
    """Begin casting, with the game attached so the payment can be made."""
    casting = scenario.cast(name, username=username)
    casting.game = scenario.game
    return casting


def elves_board(elves: int = 2) -> Scenario:
    """Alice holds Grizzly Bears and can tap Elves for green."""
    return (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Llanowar Elves"] * elves)
        .player("bob")
    )


def float_green(scenario: PlayedScenario, amount: int) -> None:
    """Tap `amount` Elves so that much green is floating."""
    for _ in range(amount):
        (source,) = scenario.untapped_sources("Llanowar Elves")
        scenario.activate(source)
    assert scenario.player("alice").mana_pool.floating.get(Color.GREEN) == amount


def test_upkeep_mana_is_gone_by_the_precombat_main():
    """The user's example: green floated at upkeep cannot cast the Bears in
    the precombat main, because the upkeep's end emptied the pool."""
    scenario = elves_board().build()
    scenario.start_at(Step.UPKEEP)
    float_green(scenario, 2)

    # upkeep ends -> precombat main: alice plays first, so CR 103.8a skips
    # her first draw step.
    scenario.advance()
    assert scenario.step is Step.PRECOMBAT_MAIN
    assert scenario.player("alice").mana_pool.floating == {}

    casting = announce(scenario, "Grizzly Bears")
    payment = casting.begin_paying()
    with pytest.raises(ValueError, match="cannot pay"):
        payment.pay()
    casting.cancel()  # CR 601.6 rewinds the proposal CR 601.2a had begun
    assert scenario.find("Grizzly Bears", Zone.HAND, "alice"), "the cast never happened"


def test_mana_floated_in_a_main_spends_fine_within_that_main():
    """Emptying is a step-END action (CR 500.5): mana floated during the main
    phase is spendable for the rest of that same phase."""
    scenario = elves_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    float_green(scenario, 2)

    bears = scenario.cast_and_resolve("Grizzly Bears")

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").mana_pool.floating == {}


def test_every_step_boundary_empties_the_pool_not_just_phase_lines():
    """CR 500.5 says "step or phase"; the upkeep -> draw boundary inside the
    beginning phase empties the pool just the same. One Elf floats during the
    upkeep, the other during the draw step, and neither mana survives its own
    step's end."""
    scenario = elves_board(2).build()
    scenario.start_at(Step.UPKEEP)

    float_green(scenario, 1)
    scenario.advance()  # -> draw
    assert scenario.player("alice").mana_pool.floating == {}

    float_green(scenario, 1)
    scenario.advance()  # -> precombat main
    assert scenario.player("alice").mana_pool.floating == {}


def test_a_pointer_jump_across_boundaries_empties_the_pool_too():
    """`Game.advance_to` crosses boundaries without the rest of the funnel,
    and each crossed step still ends: CR 500.5 fires at every one."""
    scenario = elves_board().build()
    scenario.start_at(Step.UPKEEP)
    float_green(scenario, 2)

    scenario.game.advance_to(Step.PRECOMBAT_MAIN)

    assert scenario.player("alice").mana_pool.floating == {}


def test_the_pool_empties_as_the_end_step_ends():
    """Mana floated during the end step dies when the end step ends - it does
    not even reach the cleanup step of the same ending phase."""
    scenario = elves_board(1).build()
    scenario.start_at(Step.END_STEP)
    float_green(scenario, 1)

    scenario.advance()  # -> cleanup

    assert scenario.player("alice").mana_pool.floating == {}
