"""Scenario: a library search bounded by CR 107.3f's own self-defined X - "up
to X `<quality>` cards, where X is `<expr>`" - Harvest Season's own whole
spell.

`_SEARCH_AND_PUT_RE`'s count slot never matched a bare "X" at all before
this fix, for the reason its own comment (still there) explains: a
cast-announced X (CR 107.3a, Weird Harvest's own `{X}` in its mana cost) is
substituted to a real digit by `effect_for`'s own retry before a second
parse attempt ever reaches this regex, and letting a *literal* "X" match here
would have broken that retry by making the unsubstituted first pass succeed
on a count it could not actually read. Harvest Season's own X is a different
CR paragraph entirely - "where X is `<expr>`" defines it from the sentence's
own words (CR 107.3f), never from the cost - so the fix reads X only when
that "where X is" tail is also present, leaving a bare, undefined X exactly
as unreadable as before and the substitution retry untouched for the cards
that actually need it.

`count_expression` (`machines/effects.py`, already general after the
multi-word-qualifier fix this same wave made) is the reader: the same shared
evaluator `_SCRY_RE`'s and `_SURVEIL_RE`'s own "where X is" tails already
use, now reachable from a search's own count too.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 107.3f** - "Some effects state a value for a variable as part of the
  effect. ... the value of the variable is determined by that phrase" - "X,
  where X is `<expr>`" is exactly this, as opposed to CR 107.3a's cast-
  announced X.
- **CR 701.23b** - "up to N" is a stated-quality search that never has to
  find anything.
- **CR 611.2c** - the magnitude of a resolving effect is fixed once, at the
  moment it is applied - read fresh from the board when the search runs,
  not pinned at parse time.
- **CR 613.5** - "you control" is read off the computed board.
- **CR 701.24a** - the searched library is shuffled afterward.
- **CR 110.5b** - permanents enter the battlefield untapped unless a spell
  or ability says otherwise; Harvest Season's own "onto the battlefield
  tapped" is that override.
- **CR 107.2** - a count of zero is a real, legal answer, not an error.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_harvest_season_finds_a_land_for_each_tapped_creature_alice_controls():
    """Two of alice's three creatures are tapped: X=2, so up to two basic
    land cards come back from the library, tapped, and the rest of the
    library is shuffled. Mana sources (Forest, for {2}{G}) are kept apart
    by name from the library's own basic land cards, so "found" never
    accidentally counts a permanent that was already on the battlefield.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Harvest Season"],
            battlefield=["Grizzly Bears", "Grizzly Bears", "Elvish Mystic"] + ["Forest"] * 3,
            library=["Plains", "Mountain", "Lightning Bolt"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = [c for c in scenario.game.battlefield if c.name == "Grizzly Bears"]
    bears[0].tap()
    bears[1].tap()
    sources = scenario.untapped_sources(*(["Forest"] * 3))
    alice = scenario.player("alice")

    scenario.cast_and_resolve("Harvest Season", *sources)

    found = [state for state in scenario.game.battlefield if state.name in ("Plains", "Mountain")]
    assert len(found) == 2, "X = 2 tapped creatures, both found - the library had only two lands"
    assert all(state.tapped for state in found), "CR 110.5b's own override, printed"
    assert all(state.controller == "alice" for state in found)
    assert "Lightning Bolt" in [c.name for c in alice.library], (
        "not a basic land card, so never a candidate - still in the shuffled library"
    )


def test_harvest_season_finds_fewer_lands_than_x_when_the_library_runs_short():
    """CR 701.23b's "up to" ceiling: X = 3 tapped creatures, but only one
    basic land card exists to find."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Harvest Season"],
            battlefield=["Grizzly Bears", "Grizzly Bears", "Elvish Mystic"] + ["Forest"] * 3,
            library=["Plains", "Lightning Bolt"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for state in scenario.game.battlefield:
        if state.name in ("Grizzly Bears", "Elvish Mystic"):
            state.tap()
    sources = scenario.untapped_sources(*(["Forest"] * 3))

    scenario.cast_and_resolve("Harvest Season", *sources)

    found = [state for state in scenario.game.battlefield if state.name == "Plains"]
    assert len(found) == 1
    assert [c.name for c in scenario.player("alice").library] == ["Lightning Bolt"]


def test_harvest_season_with_no_tapped_creatures_finds_nothing():
    """X = 0: a legal, real search for zero cards (CR 107.2), not an error."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Harvest Season"],
            battlefield=["Grizzly Bears"] + ["Forest"] * 3,
            library=["Plains", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Forest"] * 3))
    alice = scenario.player("alice")
    library_before = {c.name for c in alice.library}

    scenario.cast_and_resolve("Harvest Season", *sources)

    assert not any(state.name in ("Plains", "Mountain") for state in scenario.game.battlefield)
    assert {c.name for c in alice.library} == library_before
