"""`PlayedScenario.find`'s `username` parameter, on a shared zone.

CR 110.1: the battlefield is one shared zone, not one per player - exile and
the stack are the same (`Game.shared_zones`). `find(name, zone, username)`
used to read straight off that shared list whenever `zone` was one of them,
with no controller/owner filter applied at all: `username` was accepted and
silently ignored, so `find("Mountain", Zone.BATTLEFIELD, username="bob")` on
a board where alice also controls a Mountain returned whichever of the two
objects the shared list happened to list first - not necessarily bob's own,
tapped state and identity both wrong for a caller with no way to see it
short of checking `is`/`.controller` by hand. `creature()`'s own docstring
already said as much ("`find(name, Zone.BATTLEFIELD)` searches the shared
battlefield, so it cannot tell alice's Grizzly Bears from bob's") and worked
around it with a second helper rather than fixing `find` itself - dozens of
scenario tests across the pool already call `find(..., Zone.BATTLEFIELD,
username=...)` expecting exactly the filter this file proves now actually
happens, via CR 108.4a's own controller-or-owner fallback
(`CardState.controller_or_owner`).

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 110.1** - the battlefield is a shared zone, not a per-player one.
- **CR 108.4a** - "If anything asks for the controller of a card that
  doesn't have one ..., use its owner instead" - what "whose" means for a
  zone (exile) where CR 109.4 gives an object no controller at all.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def test_find_on_the_battlefield_returns_the_named_players_own_copy():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Mountain"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (alice_mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.activate(alice_mountain, color=Color.RED)

    bob_mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")

    assert bob_mountain.controller == "bob"
    assert not bob_mountain.tapped, "alice's own tap must not leak into bob's copy"


def test_find_on_the_battlefield_raises_when_the_named_player_has_none():
    """The filter is real, not a no-op: alice controls no Forest even though
    bob does, so this must fail exactly the way an absent card does."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mountain"])
        .player("bob", battlefield=["Forest"])
        .build()
    )
    try:
        scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    except AssertionError as error:
        assert "Forest is not in battlefield" in str(error)
    else:
        raise AssertionError("expected find() to raise for alice, who controls no Forest")


def test_find_in_exile_returns_the_named_players_own_copy():
    scenario = (
        Scenario()
        .player("alice", exile=["Lightning Bolt"])
        .player("bob", exile=["Lightning Bolt"])
        .build()
    )

    bob_bolt = scenario.find("Lightning Bolt", Zone.EXILE, "bob")
    alice_bolt = scenario.find("Lightning Bolt", Zone.EXILE, "alice")

    assert bob_bolt.owner == "bob"
    assert alice_bolt.owner == "alice"
    assert bob_bolt.id != alice_bolt.id


def test_find_with_no_username_still_reads_the_whole_shared_zone():
    """Unfiltered `find` is unchanged - the first match in shared-zone
    order, whoever controls it - for every existing caller that never named
    a player at all."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mountain"])
        .player("bob", battlefield=["Forest"])
        .build()
    )

    assert scenario.find("Mountain", Zone.BATTLEFIELD).name == "Mountain"
    assert scenario.find("Forest", Zone.BATTLEFIELD).name == "Forest"
