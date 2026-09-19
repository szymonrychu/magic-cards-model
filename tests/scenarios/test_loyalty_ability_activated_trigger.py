"""Ajani Unrelenting's own "Whenever you activate a loyalty ability, ..." and
Gideon the Oathless's "Whenever an opponent activates a loyalty ability, ..."
(CR 606.2's loyalty ability, CR 602.2's activation).

Nothing watched a loyalty ability being activated before this: `Game.
activate_ability`'s own CR 606.3 once-per-turn bookkeeping
(`loyalty_activations`) counted it, but raised no event `machines/triggers.py`
could match a condition against.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_ajani_unrelenting_creates_a_cadet_when_its_controller_activates_a_loyalty_ability():
    scenario = Scenario().player("alice", battlefield=["Ajani Unrelenting"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.creature("Ajani Unrelenting", "alice")

    scenario.activate(ajani, index=0, username="alice")  # +1
    scenario.game.put_triggers_on_stack()

    stack = scenario.stack_names()
    assert "Ajani Unrelenting's triggered ability" in stack


def test_gideon_the_oathless_damages_an_opponent_who_activates_a_loyalty_ability():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gideon the Oathless"], life=20, library=["Forest"])
        .player("bob", battlefield=["Ashiok, Dream Render"], life=20, library=["Forest"])
        .build()
    )
    scenario.start_at(Step.CLEANUP)
    scenario.advance()
    # CR 606.3 is a main-phase-of-*your own*-turn ability; one `advance()`
    # only reaches bob's untap (Ashiok's own controller's turn), which
    # grants no priority at all - loop to his first main phase.
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()

    scenario.activate(
        scenario.find("Ashiok, Dream Render", Zone.BATTLEFIELD, username="bob"),
        index=0,
        username="bob",
        targets=["bob"],
    )
    scenario.game.put_triggers_on_stack()

    assert "Gideon the Oathless's triggered ability" in scenario.stack_names()


def test_gideon_the_oathless_does_not_fire_for_its_own_controllers_activation():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Gideon the Oathless", "Ashiok, Dream Render"],
            life=20,
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.activate(
        scenario.find("Ashiok, Dream Render", Zone.BATTLEFIELD, username="alice"),
        index=0,
        username="alice",
        targets=["alice"],
    )
    scenario.game.put_triggers_on_stack()

    assert "Gideon the Oathless's triggered ability" not in scenario.stack_names()
