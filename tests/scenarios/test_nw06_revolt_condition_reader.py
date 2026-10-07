"""Revolt as a shared condition: "a permanent left the battlefield under your
control this turn" (CR 207.2c names revolt an ability word - no rules meaning
of its own, so the sentence is the condition).

`machines/conditions/history.py` reads both printed phrasings off
`Game.revolt_active_for` (the count kept by the controller each permanent had
as it left), so every caller of `Game.condition_holds` gets it: Aether
Revolt's "As long as ..." damage modifier (`test_nw06_hellbent_damage_
doubling.py`) and Decommission's "Revolt - If a permanent left the
battlefield under your control this turn, you gain 3 life."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice_battlefield: list[str], bob_battlefield: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Decommission"], battlefield=alice_battlefield)
        .player("bob", battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_no_revolt_no_life():
    scenario = _board(["Plains", "Plains", "Plains"], ["Bonesplitter"])
    alice = scenario.player("alice")
    target = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve("Decommission", auto=True, username="alice", targets=[target])

    assert target not in scenario.game.battlefield
    assert alice.life == 20


def test_revolt_gains_three_life():
    scenario = _board(["Plains", "Plains", "Plains", "Plains"], ["Bonesplitter"])
    alice = scenario.player("alice")
    plains = scenario.untapped_sources("Plains")[0]
    scenario.game.destroy(plains)
    target = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve("Decommission", auto=True, username="alice", targets=[target])

    assert alice.life == 23


def test_destroying_your_own_enchantment_is_revolt():
    """The destroyed permanent itself left the battlefield under alice's
    control before the "if" is asked."""
    scenario = _board(["Plains", "Plains", "Plains", "Furnace of Rath"], [])
    alice = scenario.player("alice")
    furnace = scenario.find("Furnace of Rath", Zone.BATTLEFIELD, "alice")

    scenario.cast_and_resolve("Decommission", auto=True, username="alice", targets=[furnace])

    assert alice.life == 23


def test_an_opponents_permanent_leaving_is_not_your_revolt():
    scenario = _board(["Plains", "Plains", "Plains"], ["Bonesplitter", "Grizzly Bears"])
    alice = scenario.player("alice")
    scenario.game.destroy(scenario.creature("Grizzly Bears", "bob"))
    target = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve("Decommission", auto=True, username="alice", targets=[target])

    assert alice.life == 20
