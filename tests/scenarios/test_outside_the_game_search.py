"""Scenario: searching the library *and* the sideboard in one instruction,
then letting an opponent choose which finds are kept.

Turtles Forever: "Search your library and/or outside the game for exactly
four legendary creature cards you own with different names, then reveal
those cards. An opponent chooses two of them. Put the chosen cards into your
hand and shuffle the rest into your library."

- **CR 400.11a** - "Cards in a player's sideboard are outside the game."
- **CR 400.11c** - the narrow exception: "spells and abilities that allow
  those cards to be brought into the game" may reach outside-the-game cards
  at all; this ability is one, so both pools (library and sideboard) are
  fair game for the same search.
- **CR 108.3b** - only cards this player **owns** may be brought in from
  outside the game.
- **CR 701.23a** - the search finds cards matching the description; "with
  different names" narrows the candidate pool to one representative per name
  before any choice is offered, the same convention `_parse_search_
  distinct_names_clause` already uses for a library-only search.
- **CR 701.20a** - revealing shows the four found cards to all players
  without moving them.
- **CR 608.2d** - the opponent's own choice of which two to keep is made as
  the ability resolves.
- **CR 701.24a** - the two cards the opponent did not choose are shuffled
  into the searching player's library; a sideboard-origin card among them is
  brought in first (`Player.bring_into_the_game`, CR 400.11b) so there is a
  library for it to be shuffled into at all.

No second legal printing carries this exact combined template (verified: a
live Scryfall search for `o:"library and/or outside the game"` returns only
Turtles Forever - see the dated MEMORY.md line). Generality is instead
carried by the sub-mechanisms this reader reuses rather than reinvents:
`Player.owned_outside_the_game` (CR 400.11a's own reach, already proven by
Karn, the Great Creator's `-2` in `test_outside_the_game.py`, which this
change does not touch) and the distinct-names/opponent-chooses conventions
`_parse_search_distinct_names_clause`/`_parse_reveal_two_outside_opponent_
chooses_clause` already prove elsewhere in this pool.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

_LEGENDS = [
    "Leonardo, Big Brother",
    "Leonardo, Leader in Blue",
    "Raph & Leo, Sibling Rivals",
    "Tokka & Rahzar, Terrible Twos",
]


def test_search_pools_library_and_sideboard_and_the_opponent_chooses_two():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Turtles Forever"],
            battlefield=["Plains", "Plains", "Plains", "Plains"],
            library=["Leonardo, Big Brother", "Leonardo, Leader in Blue", "Forest"] * 3,
            sideboard=["Raph & Leo, Sibling Rivals", "Tokka & Rahzar, Terrible Twos"],
        )
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    # `by_name.setdefault` in the engine keeps the first-encountered copy of
    # each name, library before sideboard - mirrored here so the scripted
    # answer names the exact objects the ability itself will offer.
    first_of_name: dict[str, object] = {}
    for state in list(alice.library) + list(alice.outside_the_game):
        if state.name in _LEGENDS:
            first_of_name.setdefault(state.name, state)
    candidates = [first_of_name[name] for name in _LEGENDS]
    assert {state.name for state in candidates} == set(_LEGENDS)
    library_before = len(alice.library)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")

    scenario.will_choose_cards(*candidates, username="alice", source="Turtles Forever")
    kept = [
        state
        for state in candidates
        if state.name in {"Raph & Leo, Sibling Rivals", "Tokka & Rahzar, Terrible Twos"}
    ]
    scenario.will_choose_cards(*kept, username="bob", source="Turtles Forever")

    scenario.cast_and_resolve("Turtles Forever", *sources, username="alice")

    # CR 608.2d: the opponent's own two are in alice's hand ...
    hand_names = {state.name for state in scenario.player("alice").hand}
    assert hand_names == {"Raph & Leo, Sibling Rivals", "Tokka & Rahzar, Terrible Twos"}
    for state in kept:
        assert state.zone is Zone.HAND
    # ... and the rest (both from the library search) are back in the
    # library rather than left in hand, graveyard, or the sideboard.
    rest = [state for state in candidates if state not in kept]
    assert {state.name for state in rest} == {
        "Leonardo, Big Brother",
        "Leonardo, Leader in Blue",
    }
    for state in rest:
        assert state.zone is Zone.LIBRARY
    # Every card revealed is public (CR 701.20a).
    assert len(scenario.game.reveals) == 4
    # The two library-origin finds were never removed from the library to
    # begin with (revealing does not move a card, CR 701.20b) and neither was
    # chosen, so the library ends exactly where it started; only the two
    # sideboard-origin cards left their zone at all, straight into hand.
    assert len(scenario.player("alice").library) == library_before


def test_a_pool_short_of_four_distinct_names_never_asks_the_question():
    """CR 608.2d: "exactly four" with only three distinct legendary names
    available anywhere is impossible, so the ability does nothing rather than
    searching for as many as it can."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Turtles Forever"],
            battlefield=["Plains", "Plains", "Plains", "Plains"],
            library=["Leonardo, Big Brother", "Leonardo, Leader in Blue", "Forest"] * 3,
            sideboard=["Raph & Leo, Sibling Rivals"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")

    scenario.cast_and_resolve("Turtles Forever", *sources, username="alice")

    assert scenario.player("alice").hand == []
    assert scenario.player("alice").outside_the_game != []
