"""Scenario: "At the beginning of each player's upkeep, `<this>` deals N damage
to them / to that player [equal to `<count>` they control]."

CR 603.2b: "When a phase or step begins, all abilities that trigger 'at the
beginning of' that phase or step trigger." CR 503.1a puts them on the stack
before the active player gets priority. "Each player's" upkeep is every
upkeep, and "them" / "that player" is the player whose upkeep it is - the
active player (CR 102.1). The source deals the damage (CR 120.1), by last
known information if it has left (CR 113.7a).

Cards: Roiling Vortex's "deals 1 damage to them"; proof printing Karma's
"deals damage to that player equal to the number of Swamps they control"
(the count read for that player, not the controller).

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: 603.2b, 503.1a, 102.1, 120.1, 113.7a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_upkeep_of(scenario, username: str) -> None:
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == username):
        scenario.advance()


def _resolve_all(scenario) -> None:
    while scenario.stack_names() or scenario.pending_triggers:
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()


def _vortex_board() -> Scenario:
    return (
        Scenario()
        .player("alice", library=["Forest"] * 5, battlefield=["Roiling Vortex"])
        .player("bob", library=["Forest"] * 5)
    )


def test_roiling_vortex_hits_its_controller_on_their_own_upkeep():
    scenario = _vortex_board().build()
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    assert scenario.step is Step.UPKEEP
    _resolve_all(scenario)

    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 20


def test_roiling_vortex_hits_the_opponent_on_their_upkeep():
    scenario = _vortex_board().build()
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    _resolve_all(scenario)
    _to_upkeep_of(scenario, "bob")
    _resolve_all(scenario)

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 19


def test_roiling_vortex_triggers_once_per_upkeep():
    scenario = _vortex_board().build()
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    _resolve_all(scenario)
    _to_upkeep_of(scenario, "bob")
    _resolve_all(scenario)
    _to_upkeep_of(scenario, "alice")
    _resolve_all(scenario)

    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 19


def test_roiling_vortex_damage_is_dealt_by_the_vortex():
    """CR 120.1: the enchantment is the source - Artist's Talent's +2 (a source
    *you* control, to an opponent) applies on the opponent's upkeep."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 5, battlefield=["Roiling Vortex", "Artist's Talent"])
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.find("Artist's Talent", Zone.BATTLEFIELD, "alice").class_level = 3
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    _resolve_all(scenario)
    _to_upkeep_of(scenario, "bob")
    _resolve_all(scenario)

    assert scenario.player("alice").life == 19  # its own controller: no +2
    assert scenario.player("bob").life == 17


# -- Karma (proof): "deals damage to that player equal to the number of Swamps
# they control" -----------------------------------------------------------------


def _karma_board() -> Scenario:
    return (
        Scenario()
        .player("alice", library=["Forest"] * 5, battlefield=["Karma", "Swamp"])
        .player("bob", library=["Forest"] * 5, battlefield=["Swamp", "Swamp", "Swamp"])
    )


def test_karma_counts_the_active_players_swamps():
    scenario = _karma_board().build()
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    _resolve_all(scenario)
    assert scenario.player("alice").life == 19

    _to_upkeep_of(scenario, "bob")
    _resolve_all(scenario)

    assert scenario.player("bob").life == 17


def test_karma_deals_nothing_to_a_player_without_swamps():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 5, battlefield=["Karma"])
        .player("bob", library=["Forest"] * 5, battlefield=["Swamp"])
        .build()
    )
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    _resolve_all(scenario)

    assert scenario.player("alice").life == 20
