"""Floodpits Drowner's "{1}{U}, {T}: Shuffle this creature and target
creature with a stun counter on it into their owners' libraries." (R0a T8).

Every CR number here was looked up with `mise run rules:find <number>` against
the 2026-09-25 Comprehensive Rules release in the session that wrote this
file.

- **CR 701.24c** - "If an effect would cause a player to shuffle one or more
  specific objects into a library, that library is shuffled even if none of
  those objects are in the zone they're expected to be in." Two objects, two
  libraries when their owners differ (`machines/effects._parse_shuffle_self_
  and_targets_into_owners_libraries_clause` groups by owner so each library
  shuffles exactly once).
- **CR 122.1** - the stun counter the target must carry to be a legal target
  in the first place; already read generically by `machines/targeting.py`'s
  "with a `<kind>` counter on it" qualifier, not anything new this task adds.
- **CR 113.7a** - Floodpits Drowner is itself part of what moves: no
  triggering event names it (this is a plain activated ability), so the
  same fail-soft id lookup Borborygmos and Fblthp's own untriggered `{1}{U}`
  uses applies.

Generality is proven on Serene Remembrance (legal Modern/Pioneer, not in
`code/magic-cards-model-api/decks/*.txt`): "Shuffle Serene Remembrance and up
to three target cards from a single graveyard into their owners' libraries."
- a *spell* rather than an activated ability (so "self" is the resolving
`CardState` itself, never `_dead_self_found`'s ability-only lookup), up to
three targets instead of one, and a "from a single graveyard" zone
restriction `machines/targeting.py`'s zone-clause reader did not previously
accept at all (widened additively alongside "your"/"an opponent's" rather
than for this card's name).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

DROWNER = "Floodpits Drowner"


def test_floodpits_drowner_shuffles_self_and_target_into_their_own_owners_libraries():
    """The two objects have two different owners - CR 701.24c's own
    per-object owner, not a single shared library."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[DROWNER, "Island", "Island"],
            library=["Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    drowner = scenario.find(DROWNER, Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    bears.add_counters("stun", 1)
    sources = scenario.untapped_sources("Island", "Island", username="alice")

    scenario.activate(drowner, *sources, targets=[bears])
    scenario.resolve_top()

    assert drowner.zone is Zone.LIBRARY
    assert bears.zone is Zone.LIBRARY
    alice_library = [c.name for c in scenario.player("alice").library]
    bob_library = [c.name for c in scenario.player("bob").library]
    assert DROWNER in alice_library and "Forest" in alice_library
    assert "Grizzly Bears" in bob_library and "Mountain" in bob_library


def test_floodpits_drowner_refuses_a_creature_with_no_stun_counter():
    """The targeting restriction is enforced, not merely cosmetic (CR
    115.4a: an illegal target refuses the whole activation)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[DROWNER, "Island", "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    drowner = scenario.find(DROWNER, Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    sources = scenario.untapped_sources("Island", "Island", username="alice")

    import pytest

    with pytest.raises(ValueError):
        scenario.activate(drowner, *sources, targets=[bears])


def test_serene_remembrance_shuffles_itself_and_graveyard_cards_from_a_single_graveyard():
    """Proof of generality: a spell (not an ability), up to three targets
    (not one), and a "from a single graveyard" zone restriction."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Serene Remembrance"],
            battlefield=["Forest"],
            graveyard=["Grizzly Bears", "Island", "Lightning Bolt"],
            library=["Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", username="alice")
    graveyard_cards = list(scenario.player("alice").graveyard)

    scenario.cast_and_resolve(
        "Serene Remembrance", *sources, targets=graveyard_cards, username="alice"
    )

    alice = scenario.player("alice")
    assert not alice.graveyard
    library_names = [c.name for c in alice.library]
    assert "Serene Remembrance" in library_names
    assert "Grizzly Bears" in library_names
    assert "Island" in library_names
    assert "Lightning Bolt" in library_names
    assert "Mountain" in library_names
