"""Scenario: a search is one choice over every legal candidate (CR 701.23a).

This file exists because of a bug seen in a live game. A seat activated Wooded
Foothills - "{T}, Pay 1 life, Sacrifice this land: Search your library for a
Mountain or Forest card, put it onto the battlefield, then shuffle." (verified
with `resolve_cards`) - intending to fetch Breeding Pool, whose type line is
"Land - Forest Island" (also verified), and got a basic Forest instead.

The engine was asking the search as a *walk*: `Game.search_library` iterated the
zone in order and put a separate yes/no question about each matching card. A
searcher could therefore only decline candidates until the one they wanted came
up, and after CR 701.24b's shuffle the order they come up in is arbitrary. One
decline, and the seat was handed the next matching card rather than the one it
asked for.

Every CR number below was looked up with `knowledge_search(type="rules")` in the
session that wrote this file.

- **CR 701.23a** - "To search for a card in a zone, look at all cards in that
  zone (even if it's a hidden zone) and find a card that matches the given
  description." The searcher sees the whole zone and picks; it is one choice
  among all the legal candidates, not a filtered walk past them.
- **CR 701.23b** - "If a player is searching a hidden zone for cards with a
  stated quality ... that player isn't required to find some or all of those
  cards even if they're present in that zone." That is the declinable search,
  and declining means naming no cards.
- **CR 701.23d** - "If a player is searching a hidden zone simply for a quantity
  of cards, such as 'a card' or 'three cards,' that player must find that many
  cards (or as many as possible, if the zone doesn't contain that many)." That
  search chooses *which*, never *whether*.
- **CR 701.23e** - nothing found is revealed unless the effect says to.
- **CR 701.24a / CR 701.24b** - the shuffle after the search, with the found
  cards kept out of it.
- **CR 400.2** - the public zones are graveyard, battlefield, stack and exile;
  the library and the hand are hidden. That is what decides whether CR 701.23b
  and CR 701.23d apply at all, not whether the find is a choice.
- **CR 608.2d** - the choice is announced while the ability resolves, which is
  why it is a `DecisionKind.CHOOSE_CARDS` question through `Game.ask`.
- **CR 305.6** - a land with a basic land type has that type's mana ability
  intrinsically, which is why a Breeding Pool is a legal find for a card looking
  for a Forest: fetchlands name land *types*, not card names.

`tests/scenarios/test_fetching_a_land.py` covers the fetchland as a card - its
cost, its sacrifice, what arrives untapped. This file covers the search as a
mechanic: who chooses, out of what, and what an unanswered question does.
"""

from uuid import uuid4

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import Decision, DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

#: The reported board: both a basic Forest and a Breeding Pool are legal finds
#: for Wooded Foothills, so the searcher has a real choice to make.
BOTH_FORESTS = ["Forest", "Breeding Pool", "Island"]


def _fetch_board(library: list[str] | None = None) -> PlayedScenario:
    """Alice with a Wooded Foothills in play and a library to search."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=list(BOTH_FORESTS if library is None else library),
            battlefield=["Wooded Foothills"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _fetch(scenario: PlayedScenario) -> None:
    """Activate the Wooded Foothills and let its ability resolve."""
    foothills = scenario.find("Wooded Foothills", Zone.BATTLEFIELD)
    scenario.activate(foothills, sacrificing=[foothills])
    scenario.pass_until_resolved()


def _search_questions(scenario: PlayedScenario) -> list[Decision]:
    return [
        decision
        for decision in scenario.game.decisions.asked
        if decision.kind is DecisionKind.CHOOSE_CARDS and "searching your" in decision.prompt
    ]


# -- the reported bug ------------------------------------------------------


def test_the_searcher_gets_the_card_they_named():
    """The headline. CR 701.23a: the searcher looks at the whole library and
    finds the card matching the description that they want - here Breeding Pool,
    with a basic Forest sitting in the same library as the other legal find.

    Against the walk this replaces, this test found a Forest: the searcher's
    only vocabulary was "no" to whichever card came up first.
    """
    scenario = _fetch_board()
    scenario.will_choose_cards(scenario.find("Breeding Pool", Zone.LIBRARY, "alice"))

    _fetch(scenario)

    assert scenario.find("Breeding Pool", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert "Breeding Pool" not in [state.name for state in scenario.player("alice").library], (
        "the found card left the library (CR 701.24b)"
    )
    assert "Forest" in [state.name for state in scenario.player("alice").library], (
        "the card the searcher did not name stays where it was"
    )


def test_the_searcher_can_name_the_basic_instead():
    """The same board, the other answer. Nothing about the choice favours the
    dual over the basic - it is the searcher's pick, both ways round.
    """
    scenario = _fetch_board()
    scenario.will_choose_cards(scenario.find("Forest", Zone.LIBRARY, "alice"))

    _fetch(scenario)

    assert scenario.find("Forest", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert "Breeding Pool" in [state.name for state in scenario.player("alice").library]


def test_a_later_candidate_is_reached_in_one_decision():
    """The second live sighting, and it pins the *shape* rather than the
    outcome. A seat fetching with Wooded Foothills declined Hedge Maze ("Land -
    Forest Island", enters tapped - verified with `resolve_cards`, so a legal
    find it had a real reason to refuse) and was asked again about the next
    candidate: two questions for what CR 701.23a calls one act of finding.

    One question, whichever candidate the searcher wants, however far down the
    zone it sits. The walk this replaces asked one per unwanted candidate and
    left a seat that refused them all with nothing found rather than a choice.
    """
    scenario = _fetch_board(library=["Forest", "Island", "Hedge Maze"])
    scenario.will_choose_cards(scenario.find("Hedge Maze", Zone.LIBRARY, "alice"))

    _fetch(scenario)

    asked = [
        decision
        for decision in scenario.game.decisions.asked
        if decision.source == "Wooded Foothills"
    ]
    assert [decision.kind for decision in asked] == [DecisionKind.CHOOSE_CARDS], (
        "one search, one question - not one per candidate"
    )
    assert scenario.find("Hedge Maze", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert "Forest" in [state.name for state in scenario.player("alice").library]


# -- the shape of the question a client is handed --------------------------


def test_the_question_offers_every_legal_candidate_at_once():
    """CR 701.23a is one question over all of them, so the decision carries all
    of them - not the first one, and not one question per candidate.

    `card_labels` is positionally aligned with `cards` so a client can render a
    hidden zone's cards by name: the library is a hidden zone (CR 400.2) and the
    ids in `cards` name nothing a client can otherwise look up.
    """
    scenario = _fetch_board()

    _fetch(scenario)

    (question,) = _search_questions(scenario)
    assert question.player == "alice"
    assert question.source == "Wooded Foothills"
    assert sorted(question.card_labels) == ["Breeding Pool", "Forest"]
    assert len(question.cards) == len(question.card_labels)
    assert question.amount == 1
    assert question.exact is False, "CR 701.23b: a stated-quality find is declinable"


def test_an_unanswered_search_still_finds_in_zone_order():
    """The default, with nobody scripted and no provider: find, taking the
    candidates in zone order. CR 701.23b would let an unscripted seat find
    nothing, but defaulting a fetchland to paying the life, sacrificing itself
    and finding nothing is not a sane thing to do on a player's behalf - and it
    is not what this engine did before searching became one choice.
    """
    scenario = _fetch_board()

    _fetch(scenario)

    assert scenario.find("Forest", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert "Breeding Pool" in [state.name for state in scenario.player("alice").library]


# -- optional (CR 701.23b) versus mandatory (CR 701.23d) -------------------


def test_a_declinable_search_may_find_nothing():
    """CR 701.23b: a search of a hidden zone for a stated quality - "a Mountain
    or Forest card" is one - never has to find. Declining is one answer naming
    no cards, and it costs the life and the land all the same.
    """
    scenario = _fetch_board()
    scenario.will_choose_cards()
    before = len(scenario.player("alice").library)

    _fetch(scenario)

    assert scenario.battlefield_names() == [], "nothing was found, so nothing arrived"
    assert len(scenario.player("alice").library) == before
    assert scenario.player("alice").life == 19, "the cost was still paid (CR 602.1a)"
    assert scenario.find("Wooded Foothills", Zone.GRAVEYARD).zone is Zone.GRAVEYARD


def test_a_search_for_a_quantity_must_find_as_many_as_possible():
    """CR 701.23d, the other branch, and the one that must not blur into
    CR 701.23b: a search that names no quality has no "isn't required to find"
    escape, so an answer that finds nothing is refused with the count it owed.
    """
    scenario = _fetch_board()
    scenario.will_choose_cards()

    with pytest.raises(ValueError, match="needs 1 card"):
        scenario.game.search_library("alice", lambda state: state.card.is_land, count=1)


def test_a_quantity_search_still_chooses_which():
    """CR 701.23d fixes *how many*, never *which*. Three lands in the library, a
    search for one, and the searcher names the one they want.
    """
    scenario = _fetch_board()
    scenario.will_choose_cards(scenario.find("Island", Zone.LIBRARY, "alice"))

    (found,) = scenario.game.search_library("alice", lambda state: state.card.is_land, count=1)

    assert found.name == "Island"


def test_a_search_for_more_than_one_card_takes_up_to_that_many():
    """`count` is honoured as a ceiling over the one choice: two of the three
    lands, named together in a single answer.
    """
    scenario = _fetch_board()
    library = scenario.player("alice").library
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    island = scenario.find("Island", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(forest, island)

    found = scenario.game.search_library("alice", lambda state: state.card.is_land, count=2)

    assert sorted(state.name for state in found) == ["Forest", "Island"]
    assert [state.name for state in library] == ["Breeding Pool"]


def test_a_search_cannot_find_a_card_that_was_not_offered():
    """CR 608.2d: "The player can't choose an option that's illegal." A card
    that does not match the description is not a candidate, and naming it is
    refused rather than quietly found.
    """
    scenario = _fetch_board(library=["Forest", "Grizzly Bears"])
    scenario.will_choose_cards(scenario.find("Grizzly Bears", Zone.LIBRARY, "alice"))

    with pytest.raises(ValueError, match="not offered"):
        _fetch(scenario)


def test_the_same_card_cannot_be_found_twice():
    """One card is one object (CR 109.1). A search for two that names the same
    card twice would take it out of the library twice, so it is refused.
    """
    scenario = _fetch_board()
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")

    scenario.will_choose_cards(forest, forest)

    with pytest.raises(ValueError, match="cannot be chosen twice"):
        scenario.game.search_library("alice", lambda state: state.card.is_land, count=2)


# -- nothing to find, and nothing to decide --------------------------------


def test_a_search_that_matches_nothing_asks_nothing_and_finds_nothing():
    """No candidate is not a choice, so no question is put - and the search
    still costs what it cost. CR 701.23a has nothing to find in a library with
    no card matching the description.
    """
    scenario = _fetch_board(library=["Island", "Grizzly Bears"])

    _fetch(scenario)

    assert _search_questions(scenario) == []
    assert scenario.battlefield_names() == []
    assert [state.name for state in scenario.player("alice").library] != []


def test_a_forced_find_is_not_asked():
    """A question with exactly one legal answer is answered without asking, the
    same way `Game.ask` forces a boolean whose affirmative is illegal. A
    mandatory search whose candidates do not outnumber `count` has nothing to
    decide: CR 701.23d already fixed the answer at "as many as possible".
    """
    scenario = _fetch_board()

    found = scenario.game.search_library(
        "alice", lambda state: state.card.name == "Island", count=1
    )

    assert [state.name for state in found] == ["Island"]
    assert _search_questions(scenario) == []


# -- the shuffle that follows (CR 701.24a, CR 701.24b) ---------------------


def test_the_library_is_shuffled_after_the_search():
    """CR 701.24a randomizes the library and CR 701.24b keeps the found cards
    out of it. The choice being a choice changes nothing about that: the shuffle
    still happens, once, after the find.
    """
    scenario = _fetch_board(library=["Forest", "Island", "Mountain", "Swamp", "Plains", "Wastes"])
    before = [state.name for state in scenario.player("alice").library]
    scenario.will_choose_cards(scenario.find("Mountain", Zone.LIBRARY, "alice"))

    _fetch(scenario)

    after = [state.name for state in scenario.player("alice").library]
    assert scenario.game.shuffles_performed == 1
    assert "Mountain" not in after
    assert after != [name for name in before if name != "Mountain"], "and it was randomized"


def test_a_declined_search_shuffles_too():
    """CR 701.24b's shuffle is printed after the search and is not conditional
    on finding anything - the difference between a search being free information
    and being a real cost.
    """
    scenario = _fetch_board(library=["Forest", "Island", "Mountain", "Swamp", "Plains", "Wastes"])
    before = [state.name for state in scenario.player("alice").library]
    scenario.will_choose_cards()

    _fetch(scenario)

    assert scenario.game.shuffles_performed == 1
    assert [state.name for state in scenario.player("alice").library] != before


# -- a search of a public zone (CR 400.2) ----------------------------------


def test_a_public_zone_search_is_the_same_question():
    """CR 400.2 makes the graveyard a public zone, which changes whether
    CR 701.23b's "isn't required to find" applies - both that rule and
    CR 701.23d are written about hidden zones - not whether CR 701.23a's find is
    a choice. A graveyard search that matches more cards than it takes is still
    the searcher picking which, so it is asked the same way, with the same kind
    and the same candidate list.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Island"], graveyard=["Forest", "Mountain", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(scenario.find("Mountain", Zone.GRAVEYARD, "alice"))

    found = scenario.game.search_library(
        "alice", lambda state: state.card.is_land, count=1, zone=Zone.GRAVEYARD
    )

    assert [state.name for state in found] == ["Mountain"]
    assert [state.name for state in scenario.player("alice").graveyard] == [
        "Forest",
        "Grizzly Bears",
    ]
    assert scenario.game.shuffles_performed == 0, "CR 701.24b's shuffle is library-only"
    (question,) = _search_questions(scenario)
    assert sorted(question.card_labels) == ["Forest", "Mountain"]


def test_a_stray_id_is_refused_wherever_it_comes_from():
    """A client answering with an id that is in no zone at all - a stale card,
    a typo - is refused by CR 608.2d's legality check rather than silently
    finding nothing.
    """
    scenario = _fetch_board()
    scenario.game.decisions.add(ScriptedAnswer(kind=DecisionKind.CHOOSE_CARDS, value=(uuid4(),)))

    with pytest.raises(ValueError, match="not offered"):
        _fetch(scenario)
