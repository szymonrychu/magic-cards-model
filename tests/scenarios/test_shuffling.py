"""Scenario: shuffling a library, and the search that usually precedes it.

Until now every search effect in the engine carried the same deviation: the card
was found and the library kept its exact order, so a fetchland told the truth
about what it found and a lie about everything under it. This file is that
deviation closed.

A seeded shuffle is not a mock. CR 701.24a asks that "no player knows their
order", not that the program cannot know it, and a rigged library is already how
this project stages a scenario (see CLAUDE.md). `Game.shuffle_seed` is what makes
the randomization reproducible, which is what lets a test assert on it at all.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file, and read in full from the
`2026-08-19` Comprehensive Rules release that
`knowledge_search(type="cr_versions")` names as current, downloaded from its
`source_url` and verified against its published sha256.

- **CR 701.24a** - "To shuffle a library or a face-down pile of cards, randomize
  the cards within it so that no player knows their order."
- **CR 701.24b** - "Some effects cause a player to search a library for a card
  or cards, shuffle that library, then put some or all of the found cards into a
  different zone or in a certain position in that library. In such cases, the
  found cards aren't included in the shuffle, even though they remain in the
  library at that time."
- **CR 701.24d / 701.24e** - the shuffle happens even when there is nothing to
  shuffle in, and even with zero or one cards in the library.
- **CR 701.23a** - "To search for a card in a zone, look at all cards in that
  zone (even if it's a hidden zone) and find a card that matches the given
  description."
- **CR 701.23b** - searching a *hidden* zone for cards with a stated quality,
  "that player isn't required to find some or all of those cards even if they're
  present in that zone". This is the rule that makes a search a decision.
- **CR 701.23d** - searching "simply for a quantity of cards" *must* find that
  many, or as many as possible.
- **CR 701.23e** - nothing found is revealed unless the effect says so.
- **CR 400.2** - the public zones are listed, and the library is not among them,
  which is what makes CR 701.23b apply to it.

The engine side is `Game.shuffle_library` and `Game.search_library`. The search
effects registered in `machines/effects.py` do not call them yet - see the xfail
at the bottom and `docs/engine-coverage.md`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

#: Eight distinct real printings. Enough that a shuffle leaving the order
#: untouched is a 1-in-40320 coincidence rather than a coin flip.
DECK = [
    "Island",
    "Mountain",
    "Forest",
    "Swamp",
    "Plains",
    "Sacred Foundry",
    "Steam Vents",
    "Breeding Pool",
]


def _board(*, library: list[str] | None = None, seed: int = 7) -> Scenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=list(DECK if library is None else library))
        .build()
    )
    scenario.game.shuffle_seed = seed
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _library(scenario) -> list[str]:
    return [state.card.name for state in scenario.player("alice").library]


# -- shuffling ------------------------------------------------------------


def test_a_shuffle_changes_the_order_and_keeps_every_card():
    """CR 701.24a: "randomize the cards within it".

    Randomize, not replace: the same cards are all still there afterwards, which
    is the half of the rule an over-eager implementation would break.
    """
    scenario = _board()
    before = _library(scenario)

    scenario.game.shuffle_library("alice")

    after = _library(scenario)
    assert sorted(after) == sorted(before)
    assert after != before


def test_the_same_seed_shuffles_the_same_way():
    """A seeded shuffle satisfies CR 701.24a and keeps a scenario reproducible.

    "So that no player knows their order" is a statement about the players at
    the table, not about the program. Without this property no test could assert
    anything at all about a shuffled library, which is why the shuffle went
    unmodelled for so long.
    """
    first = _board(seed=1234)
    second = _board(seed=1234)

    first.game.shuffle_library("alice")
    second.game.shuffle_library("alice")

    assert _library(first) == _library(second)


def test_different_seeds_shuffle_differently():
    """The other half of the same property: the seed is doing real work."""
    first = _board(seed=1)
    second = _board(seed=99)

    first.game.shuffle_library("alice")
    second.game.shuffle_library("alice")

    assert _library(first) != _library(second)


def test_two_shuffles_in_one_game_do_not_repeat_themselves():
    """A game that shuffles twice must not put the library back the way it was.

    The seed is per game and the count is per shuffle, so the second shuffle
    draws from a different stream than the first. A naive implementation that
    reseeded from `shuffle_seed` alone would make shuffling twice a no-op.
    """
    scenario = _board()

    scenario.game.shuffle_library("alice")
    once = _library(scenario)
    scenario.game.shuffle_library("alice")

    assert _library(scenario) != once
    assert scenario.game.shuffles_performed == 2


def test_a_library_of_one_card_still_counts_as_shuffled():
    """CR 701.24e: "If an effect causes a player to shuffle a library containing
    zero or one cards, abilities that trigger when a library is shuffled will
    still trigger."

    Nothing can move, so the only observable consequence is that the shuffle
    happened. `shuffles_performed` is where that lives until a trigger watches
    for it.
    """
    scenario = _board(library=["Island"])

    scenario.game.shuffle_library("alice")

    assert _library(scenario) == ["Island"]
    assert scenario.game.shuffles_performed == 1


def test_an_empty_library_still_counts_as_shuffled():
    """CR 701.24d and CR 701.24e together: the shuffle is not conditional on
    there being anything to shuffle."""
    scenario = _board(library=[])

    scenario.game.shuffle_library("alice")

    assert scenario.game.shuffles_performed == 1


def test_a_kept_card_is_not_included_in_the_shuffle():
    """CR 701.24b: "the found cards aren't included in the shuffle, even though
    they remain in the library at that time. Rather, all the cards in that
    library except those are shuffled."

    The rule exists for effects like Green Sun's Zenith that shuffle and *then*
    place. Here the kept card stays exactly where it was put while everything
    else moves around it.
    """
    scenario = _board()
    kept = scenario.player("alice").library[0]

    scenario.game.shuffle_library("alice", keep=[kept])

    library = _library(scenario)
    assert library[0] == kept.card.name
    assert library[1:] != DECK[1:]


def test_shuffling_one_players_library_leaves_the_other_alone():
    """A shuffle is of *a* library. Nothing here reaches across the table."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=list(DECK))
        .player("bob", library=list(DECK))
        .build()
    )
    scenario.game.shuffle_seed = 5
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.shuffle_library("alice")

    assert [state.card.name for state in scenario.player("bob").library] == DECK


# -- searching, and the shuffle that follows -------------------------------


def test_a_search_takes_the_card_out_and_shuffles_the_rest():
    """CR 701.23a then CR 701.24b, which is the shape every fetch effect prints.

    The found card leaves the library and the remainder is randomized. Both
    halves matter: a search that found the card and left the order alone is the
    deviation this file closes.
    """
    scenario = _board()

    (found,) = scenario.game.search_library(
        "alice", lambda state: state.card.name == "Sacred Foundry"
    )

    assert found.card.name == "Sacred Foundry"
    assert "Sacred Foundry" not in _library(scenario)
    assert len(_library(scenario)) == len(DECK) - 1
    assert _library(scenario) != [name for name in DECK if name != "Sacred Foundry"]


def test_a_search_looks_at_the_whole_library_not_just_the_top():
    """CR 701.23a: "look at all cards in that zone (even if it's a hidden zone)".

    The card is put last on purpose. A search that only reached the top of the
    library would miss it, and would still pass a test whose fixture happened to
    stack the target first.
    """
    scenario = _board(library=[*DECK, "Grizzly Bears"])

    (found,) = scenario.game.search_library(
        "alice", lambda state: state.card.name == "Grizzly Bears"
    )

    assert found.card.name == "Grizzly Bears"


def test_a_search_that_finds_nothing_still_shuffles():
    """CR 701.24d: the shuffle is printed after the search and happens regardless.

    "That library is shuffled even if there are no objects in that set." A
    failed fetch still randomizes, which is the difference between a search
    being free information and being a real cost.
    """
    scenario = _board()
    before = _library(scenario)

    found = scenario.game.search_library("alice", lambda state: state.card.name == "Black Lotus")

    assert found == []
    assert scenario.game.shuffles_performed == 1
    assert _library(scenario) != before


def test_a_search_can_be_told_not_to_shuffle():
    """CR 701.23h: an effect may search a library more than once before shuffling.

    "This is the same as a single instruction for that player to search that
    library for all those cards. The player searches that library only once." An
    effect assembling several finds needs the shuffle held back until the end,
    which is what `shuffle=False` is for.
    """
    scenario = _board()
    before = _library(scenario)

    scenario.game.search_library("alice", lambda state: state.card.name == "Island", shuffle=False)

    assert scenario.game.shuffles_performed == 0
    assert _library(scenario) == [name for name in before if name != "Island"]


def test_a_search_for_several_cards_finds_that_many():
    """CR 701.23d: searching "simply for a quantity of cards ... must find that
    many (or as many as possible, if the zone doesn't contain enough cards)."

    Two basic lands out of a library that holds five: the count is a ceiling the
    search fills, not a suggestion.
    """
    scenario = _board()

    found = scenario.game.search_library(
        "alice", lambda state: state.card.is_land and "Basic" in state.card.type_line, count=2
    )

    assert len(found) == 2


def test_an_optional_search_may_decline_to_find_a_card_that_is_there():
    """CR 701.23b, the rule that makes searching a hidden zone a decision.

    "If a player is searching a hidden zone for cards with a stated quality ...
    that player isn't required to find some or all of those cards even if
    they're present in that zone." CR 400.2 lists the public zones and the
    library is not one, so this applies to every library search.

    Declining is answered through the same CR 608.2d machinery as a scry.
    """
    scenario = _board()
    scenario.will_take_the_may(False, times=None)

    found = scenario.game.search_library(
        "alice", lambda state: state.card.name == "Island", optional=True
    )

    assert found == []
    assert "Island" in _library(scenario), "declining to find leaves the card there"
    assert scenario.game.shuffles_performed == 1, "the shuffle happens anyway (CR 701.24d)"


def test_a_search_that_is_not_optional_finds_what_is_there():
    """CR 701.23d is the exception to CR 701.23b, and the two must not blur.

    A search with no stated quality has no "isn't required to find" escape, so
    the same board that declined above finds the card here.
    """
    scenario = _board()
    scenario.will_take_the_may(False, times=None)

    found = scenario.game.search_library("alice", lambda state: state.card.name == "Island")

    assert [state.card.name for state in found] == ["Island"]


def test_nothing_found_by_a_search_is_revealed():
    """CR 701.23e: "If the effect that contains the search instruction doesn't
    also contain instructions to reveal the found card(s), then they're not
    revealed."

    The found card is handed back to the caller and left in no zone at all until
    the caller puts it somewhere - it is not routed through a public zone on the
    way.
    """
    scenario = _board()

    (found,) = scenario.game.search_library("alice", lambda state: state.card.name == "Island")

    assert found.zone is Zone.LIBRARY, "still nominally a library card until it is moved"
    assert found not in scenario.player("alice").library
    assert found not in scenario.player("alice").graveyard
    assert found not in scenario.game.battlefield


# -- what the registered search effects still do not do --------------------


def test_a_fetchland_shuffles_the_library_it_searched():
    """ "...then shuffle." CR 701.24b makes the shuffle part of the same action.

    Driven through the real activated ability rather than through
    `Game.search_library`, so it exercises the whole path: `machines/effects.py`'s
    `_search_library` helper calls `Game.search_library`, which takes the found
    card out and shuffles what is left (CR 701.24b).
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Sacred Foundry", "Forest", "Island", "Swamp", "Plains"],
            battlefield=["Arid Mesa"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.game.shuffle_seed = 3
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mesa = scenario.find("Arid Mesa", Zone.BATTLEFIELD)

    scenario.activate(mesa, sacrificing=[mesa])
    scenario.pass_until_resolved()

    assert _library(scenario) != ["Forest", "Island", "Swamp", "Plains"]
