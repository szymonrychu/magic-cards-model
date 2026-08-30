"""Look at the top N cards and split them between two destinations, general
past `Game.scry`/`Game.surveil`'s own fixed pair - `Game.look_at_top_and_split`
in `models/game.py`, exercised through `_merge_look_top_reveal_to_hand_
clauses` in `machines/effects.py`.

Duskwatch Recruiter's `{2}{G}` ability is the vehicle: "Look at the top three
cards of your library. You may reveal a creature card from among them and
put it into your hand. Put the rest on the bottom of your library in any
order." `Game.scry` always sends its `moved` half to the *bottom* and the
rest back to the *top*; this ability sends its taken half to *hand* and the
rest to the *bottom* - neither of scry's own two destinations - which is
exactly why the general primitive takes both groups off the library and lets
the caller decide, rather than writing to `player.library` itself the way
`scry`/`surveil` do.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 701.22a** - "To 'scry N' means to look at the top N cards of your
  library, then put any number of them on the bottom of your library in any
  order and the rest on top of your library in any order" - the shape
  `look_at_top_and_split` generalises; Duskwatch Recruiter's own ability is
  not itself a scry (it has no reminder text or the word "scry"), so it asks
  the identical CR 608.2d question through `DecisionKind.SCRY` without being
  one.
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible" - taking more than one card, or one that fails the "creature"
  restriction, is exactly such an option, and `_merge_look_top_reveal_to_
  hand_clauses` raises rather than silently allowing it.
- **CR 701.23e/701.20e** - looking at a card is not revealing it to every
  player; nothing about the two cards left unlooked-at on the library
  changes, and the card taken is the only one that actually moves.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import CardSplit, DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone

from .harness import Scenario


def _script_scry_split(scenario: Scenario, *, username: str, moved) -> None:
    """Script the next `DecisionKind.SCRY`-shaped answer with `moved` as the
    taken half - `Scenario` has no dedicated helper for this shape since it
    reuses `SCRY` for a non-scry effect (see `Game.look_at_top_and_split`)."""
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=tuple(moved)), player=username)
    )


def test_revealing_a_creature_among_the_top_three_puts_it_in_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Grizzly Bears", "Forest", "Mountain", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    recruiter = scenario.creature("Duskwatch Recruiter")
    bears, forest, mountain = scenario.top_of_library(3)
    _script_scry_split(scenario, username="alice", moved=[bears.id])

    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    scenario.resolve_top()

    assert bears.zone is Zone.HAND
    assert bears in alice.hand
    assert forest.zone is Zone.LIBRARY
    assert mountain.zone is Zone.LIBRARY
    assert {state.id for state in alice.library[-2:]} == {forest.id, mountain.id}


def test_declining_leaves_all_three_on_the_bottom_in_looked_at_order():
    """The default `CardSplit()` answer - nothing moved, no order named -
    keeps the three looked-at cards in their original relative order, now on
    the bottom rather than the top."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Grizzly Bears", "Forest", "Mountain", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    recruiter = scenario.creature("Duskwatch Recruiter")
    bears, forest, mountain, swamp = alice.library[:4]

    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    scenario.resolve_top()

    assert bears not in alice.hand
    assert alice.library[0] is swamp
    assert alice.library[1:] == [bears, forest, mountain]


def test_no_creature_among_the_top_three_still_puts_all_three_on_the_bottom():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Forest", "Mountain", "Swamp", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    recruiter = scenario.creature("Duskwatch Recruiter")
    forest, mountain, swamp = scenario.top_of_library(3)

    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    scenario.resolve_top()

    assert alice.hand == []
    assert alice.library[-3:] == [forest, mountain, swamp]


def test_fewer_than_three_cards_in_library_looks_at_only_what_is_there():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    recruiter = scenario.creature("Duskwatch Recruiter")
    bears = alice.library[0]

    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    scenario.resolve_top()

    assert alice.hand == []
    assert alice.library == [bears]


def test_taking_more_than_one_card_is_an_illegal_choice():
    """CR 608.2d: "at most one" is not a free-form scry split - a scripted
    answer naming two cards for the taken half is refused, the same way an
    over-large `CHOOSE_TARGETS` answer already is."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Grizzly Bears", "Basking Rootwalla", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    recruiter = scenario.creature("Duskwatch Recruiter")
    bears, rootwalla, _mountain = scenario.top_of_library(3)
    _script_scry_split(scenario, username="alice", moved=[bears.id, rootwalla.id])

    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    with pytest.raises(ValueError, match="CR 608.2d"):
        scenario.resolve_top()


def test_taking_a_non_creature_card_is_an_illegal_choice():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Forest", "Mountain", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    recruiter = scenario.creature("Duskwatch Recruiter")
    forest, _mountain, _swamp = scenario.top_of_library(3)
    _script_scry_split(scenario, username="alice", moved=[forest.id])

    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    with pytest.raises(ValueError, match="CR 608.2d"):
        scenario.resolve_top()
