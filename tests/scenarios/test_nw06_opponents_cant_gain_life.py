"""A permanent's "Your opponents can't gain life." (CR 119.7).

CR 119.7: "If an effect says that a player can't gain life, that player can't
make an exchange such that the player's life total would become higher ..."
- the gain simply does not happen. The static ability is CR 611.1's "affects
players or the rules of the game" kind and lasts while its source is on the
battlefield (CR 604.2, CR 611.3a: not "locked in"), so `Game.life_gain_
prohibited` reads it fresh on every gain, relative to the source's
controller *now*: "your opponents" are the opponents of whoever controls it.

Printings: Quakebringer (the listed card) and Knight of Dusk's Shadow (a
second printing of the same template).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.game._continuous import is_player_rules_static_line
from tests.scenarios.harness import Scenario


def _board(bob_battlefield: list[str], alice_battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice_battlefield or [], hand=["Grizzly Bears"])
        .player("bob", battlefield=bob_battlefield)
    )


def test_quakebringer_stops_its_controllers_opponent_gaining_life():
    scenario = _board(["Quakebringer"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    scenario.game.gain_life("alice", 3)

    assert alice.life == 20
    assert scenario.game.life_gain_prohibited("alice") is not None


def test_its_controller_still_gains_life():
    scenario = _board(["Knight of Dusk's Shadow"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.game.gain_life("bob", 3)

    assert bob.life == 23
    assert scenario.game.life_gain_prohibited("bob") is None


def test_a_life_gain_trigger_gains_nothing_for_the_opponent():
    """Soul Warden's trigger still resolves (CR 603.2), but its gain can't
    happen (CR 119.7)."""
    scenario = _board(["Knight of Dusk's Shadow"], ["Soul Warden", "Forest", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    scenario.cast_and_resolve("Grizzly Bears", auto=True, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert alice.life == 20


def test_the_controllers_own_life_gain_trigger_still_gains():
    """Bob's own Soul Warden sees alice's creature enter and bob gains."""
    scenario = _board(["Knight of Dusk's Shadow", "Soul Warden"], ["Forest", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.cast_and_resolve("Grizzly Bears", auto=True, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bob.life == 21


def test_the_prohibition_ends_when_its_source_leaves():
    """CR 604.2: the effect lasts only while the permanent is there."""
    scenario = _board(["Quakebringer"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.game.destroy(scenario.creature("Quakebringer", "bob"))

    scenario.game.gain_life("alice", 3)

    assert alice.life == 23


def test_your_opponents_follows_a_change_of_control():
    """CR 611.3a: whoever controls the source now - after Act of Treason,
    alice controls the Knight and bob is the opponent who can't gain life."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Mountain", "Mountain", "Mountain"], hand=["Act of Treason"])
        .player("bob", battlefield=["Knight of Dusk's Shadow"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Dusk's Shadow", "bob")
    scenario.cast_and_resolve("Act of Treason", auto=True, username="alice", targets=[knight])

    scenario.game.gain_life("alice", 2)
    scenario.game.gain_life("bob", 2)

    assert scenario.player("alice").life == 22
    assert scenario.player("bob").life == 20


def test_the_line_is_one_the_engine_reads_off_the_battlefield():
    assert is_player_rules_static_line("Your opponents can't gain life.")
    assert is_player_rules_static_line("Players can't gain life.")
    assert not is_player_rules_static_line("Your opponents can't gain life this turn.")
