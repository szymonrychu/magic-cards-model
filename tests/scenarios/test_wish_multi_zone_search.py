"""Invasion of Arcavios's Siege ETB: one combined search across three zones
at once, never three independent ones.

Card text, confirmed with `resolve_cards` in the session that wrote this
file:

Invasion of Arcavios (Battle - Siege, defense 7):
    When this Siege enters, search your library, graveyard, and/or outside
    the game for an instant or sorcery card you own, reveal it, and put it
    into your hand. If you search your library this way, shuffle.

A Scryfall search for this exact wording turns up no other real printing,
so the quality is still read generally (`_quality_matcher`, parameterised -
see `machines/effects.py`'s own `_SEARCH_LIBRARY_GRAVEYARD_OUTSIDE_THE_GAME_
RE` docstring) rather than hardcoded to "instant or sorcery".

Every rule below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 701.23a** - "To search for a card in a zone, look at all cards in
  that zone ... and find a card that matches the given description" - one
  search naming three zones is one search, not three, matching `Game.
  search_library`'s own "hand and/or library" precedent
  (`_parse_quest_counter_threshold_sacrifice_search_clause`).
- **CR 400.11a** - "Cards in a player's sideboard are outside the game."
- **CR 108.3b** - "you own", not "you control" - the gate on a card from
  outside the game.
- **CR 701.24a** - the library is shuffled whenever it was searched,
  found there or not; this printing's own rulings (2023-04-14) confirm the
  combined search always looks through the library: "You don't have to
  declare up front where you're going to search. You may search your
  library, pause, sigh, check out your graveyard, frown meaningfully at
  your opponent, then finally grab a game-winning sorcery card from your
  sideboard."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

ARCAVIOS = "Invasion of Arcavios"


def test_finds_the_chosen_card_from_whichever_zone_it_sits_in_and_always_shuffles():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ARCAVIOS],
            library=["Grizzly Bears", "Shock", "Forest", "Llanowar Elves"],
            graveyard=["Opt"],
            sideboard=["Counterspell"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    shock = scenario.find("Shock", Zone.LIBRARY, "alice")
    opt = scenario.find("Opt", Zone.GRAVEYARD, "alice")
    counterspell = scenario.find("Counterspell", Zone.SIDEBOARD, "alice")

    library_before = list(scenario.player("alice").library)

    scenario.put_onto_battlefield(ARCAVIOS, "alice")
    scenario.will_choose_cards(opt, username="alice", source=ARCAVIOS)
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert opt.zone is Zone.HAND, "found from the graveyard, put into hand"
    assert opt in alice.hand
    assert shock.zone is Zone.LIBRARY, "the un-chosen library candidate was left alone"
    assert counterspell.zone is Zone.SIDEBOARD, "the un-chosen outside-the-game candidate too"
    assert list(alice.library) != library_before, (
        "the library was shuffled - it was searched too, even though nothing was taken from it"
    )
    assert {c.id for c in alice.library} == {c.id for c in library_before}, (
        "shuffled, not changed in content"
    )


def test_finds_the_chosen_card_from_outside_the_game():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ARCAVIOS],
            library=["Grizzly Bears", "Forest"],
            sideboard=["Counterspell"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    counterspell = scenario.find("Counterspell", Zone.SIDEBOARD, "alice")

    scenario.put_onto_battlefield(ARCAVIOS, "alice")
    scenario.will_choose_cards(counterspell, username="alice", source=ARCAVIOS)
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert counterspell.zone is Zone.HAND, "brought in from outside the game (CR 400.11b)"
    assert counterspell in alice.hand
    assert counterspell.owner == "alice"


def test_no_matching_card_anywhere_finds_nothing_but_still_shuffles():
    scenario = (
        Scenario()
        .player("alice", hand=[ARCAVIOS], library=["Grizzly Bears", "Forest", "Llanowar Elves"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    library_before = list(scenario.player("alice").library)

    scenario.put_onto_battlefield(ARCAVIOS, "alice")
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert alice.hand == []
    assert len(alice.library) == len(library_before)
    assert {c.id for c in alice.library} == {c.id for c in library_before}
