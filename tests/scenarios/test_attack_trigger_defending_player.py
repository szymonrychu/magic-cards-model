""" "Whenever Ulamog attacks, defending player exiles the top twenty cards of
their library" - an attack trigger whose effect names the *defending*
player, an anaphor bound to the attack itself (CR 508.5, CR 508.6), not a
target Ulamog's controller ever chooses.

Verified this session with `knowledge_search(type="rules")`:

- **CR 508.5** - "If an ability of an attacking creature refers to a
  defending player, or a spell or ability refers to both an attacking
  creature and a defending player, then unless otherwise specified, the
  defending player in question is the player ... that creature is attacking,
  or that's being attacked by the creature the spell or ability refers to."
- **CR 508.6** - "A player is 'attacking [a player]' if the first player
  controls a creature that is attacking the second player." (The general
  two-player case this pool's boards are; CR 802.2a's "one specific
  defending player" multiplayer wrinkle is not exercised here.)

`machines.combat.defending_player` already existed, reading `Attack.defender`
off a *live* combat; this wave generalised it to take a bare `TargetRef`
directly, so a resolving trigger can ask the same question off its own
`GameEvent.defender` (`Game.declare_attacker`'s own field, CR 508.1a) once the
attack itself is long past `game.combat`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(bobs_library: list[str]) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Ulamog, the Ceaseless Hunger"])
        .player("bob", library=bobs_library)
    )


def test_attacking_exiles_the_top_twenty_cards_of_the_defending_players_library():
    library = ["Forest"] * 25
    scenario = _board(library).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ulamog = scenario.creature("Ulamog, the Ceaseless Hunger", "alice")

    scenario.attack_with(ulamog, defending="bob")
    scenario.pass_until_resolved()  # Ulamog's attack trigger

    bob = scenario.player("bob")
    assert len(bob.library) == 5
    assert len(scenario.game.exile) == 20
    assert all(state.zone is Zone.EXILE for state in scenario.game.exile)


def test_a_library_with_fewer_than_twenty_cards_is_exiled_in_full():
    """CR 701.13a's exile has no CR 104.3c-style loss condition of its own -
    unlike drawing, exiling more cards than are left simply exiles what is
    there and stops, without anybody losing the game."""
    library = ["Forest"] * 7
    scenario = _board(library).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ulamog = scenario.creature("Ulamog, the Ceaseless Hunger", "alice")

    scenario.attack_with(ulamog, defending="bob")
    scenario.pass_until_resolved()

    bob = scenario.player("bob")
    assert bob.library == []
    assert len(scenario.game.exile) == 7


def test_an_empty_library_exiles_nothing_and_does_not_error():
    scenario = _board([]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ulamog = scenario.creature("Ulamog, the Ceaseless Hunger", "alice")

    scenario.attack_with(ulamog, defending="bob")
    scenario.pass_until_resolved()

    assert scenario.player("bob").library == []
    assert scenario.game.exile == []


def test_ulamogs_own_controller_does_not_lose_any_cards():
    """The exile is the *defending* player's library - alice's own library is
    untouched, which is what makes this an anaphor bound to the attack
    rather than a plain "you" effect.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ulamog, the Ceaseless Hunger"],
            library=["Forest"] * 25,
        )
        .player("bob", library=["Forest"] * 25)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ulamog = scenario.creature("Ulamog, the Ceaseless Hunger", "alice")

    scenario.attack_with(ulamog, defending="bob")
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").library) == 25
    assert len(scenario.player("bob").library) == 5


# Ulamog's *other* ability - "When you cast this spell, exile two target
# permanents" - already has its own coverage in `test_cast_triggers.py`
# (`test_exiling_two_target_permanents_happens_before_the_creature_arrives`
# and its siblings), predating this wave. Not duplicated here on purpose:
# this file is about the attack trigger only.
