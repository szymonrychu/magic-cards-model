"""Putting cards on the bottom of a library leaves every card already there in
the order it was in, so what a player knew about those cards stays true.

- **CR 401.2** - "Each library must be kept in a single face-down pile.
  Players can't look at or change the order of cards in a library."
- **CR 701.20d** - "If cards in a player's library are shuffled or otherwise
  reordered, any revealed cards that are reordered stop being revealed and
  become new objects." Only the cards *reordered* stop being revealed.
- **CR 701.22a** - scry puts the looked-at cards "on the bottom of your library
  in any order and the rest on top of your library in any order": the cards it
  moves are reordered, the cards below them are not.
- **CR 103.5** - the mulligan "puts a number of those cards ... on the bottom
  of their library in any order".
- **CR 701.24a** - a shuffle randomizes the whole library, so it still ends
  every library record.

A card put on the bottom goes below every card already there, and a card
taken off the top (a draw, or a scry's own cards) leaves the rest in their
order - so a record of a card neither moved nor sitting below an insertion
point survives: its position from the top is still computed live. What ends
records is unchanged: a shuffle, a reordering of the recorded card itself,
and an insertion above it (a card put on top, as Subtlety does).

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario
from tests.scenarios.test_mulligans import match as eldrazi_ramp_match


def known_in_library(game: Game, viewer: str) -> list[tuple[str, int | None]]:
    return sorted(
        (entry.card_name, entry.index_from_top)
        for entry in game.known_to(viewer)
        if entry.zone is Zone.LIBRARY
    )


def _alice_library(*cards: str) -> Scenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=list(cards), battlefield=["Flooded Strand"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_second_scry_bottoming_other_cards_keeps_the_first_bottomed_card_known():
    """The battle report's case (B2-15): Devourer of Destiny scried to the
    bottom, then a later scry bottomed Eldrazi Temple and Urza's Power Plant
    under it. Devourer never moved, and alice still knows where it is."""
    scenario = _alice_library(
        "Devourer of Destiny", "Eldrazi Temple", "Urza's Power Plant", "Forest", "Island"
    )
    game = scenario.game
    (devourer,) = scenario.top_of_library(1)
    scenario.scry_bottoming(devourer)
    game.scry("alice", 1, source="Giant's Boulder")
    assert known_in_library(game, "alice") == [("Devourer of Destiny", 4)]

    temple, plant = scenario.top_of_library(2)
    scenario.scry_bottoming(temple, plant)
    game.scry("alice", 2, source="Giant's Boulder")

    alice = scenario.player("alice")
    assert [state.name for state in alice.library] == [
        "Forest",
        "Island",
        "Devourer of Destiny",
        "Eldrazi Temple",
        "Urza's Power Plant",
    ]
    assert known_in_library(game, "alice") == [
        ("Devourer of Destiny", 2),
        ("Eldrazi Temple", 3),
        ("Urza's Power Plant", 4),
    ]


def test_a_card_put_on_the_bottom_keeps_an_opponent_s_look_at_the_top_card():
    """Mishra's Bauble shows alice bob's top card; a card then put on the bottom
    of bob's library goes under it and changes nothing about the top. The
    Bears came from bob's graveyard, a public zone (CR 400.2), so alice knows
    them at the bottom as well (battle 8, B8-03)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mishra's Bauble"])
        .player("bob", library=["Lightning Bolt", "Island"], graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bauble = scenario.find("Mishra's Bauble", Zone.BATTLEFIELD)
    scenario.activate(bauble, username="alice", targets=["bob"])
    scenario.pass_until_resolved()
    assert known_in_library(scenario.game, "alice") == [("Lightning Bolt", 0)]
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    scenario.game.put_cards_into_library([bears], to_bottom=True)

    bob = scenario.player("bob")
    assert bob.library[-1] is bears
    assert sorted(known_in_library(scenario.game, "alice")) == [
        ("Grizzly Bears", 2),
        ("Lightning Bolt", 0),
    ]


def test_bottoming_cards_for_a_mulligan_keeps_a_record_of_the_card_left_on_top():
    """CR 103.5's bottoming goes under the looked-at top card and does not
    reorder it."""
    match = eldrazi_ramp_match()
    game = match.start_game()
    bob = game.player("bob")
    game.declare_mulligan("alice", False)
    game.declare_mulligan("bob", True)
    top = bob.library[0]
    game.look(top, "alice", source=None)

    game.declare_mulligan("bob", False)

    assert bob.hand_kept
    assert bob.library[0] is top
    assert known_in_library(game, "alice") == [(top.name, 0)]


def test_a_shuffle_after_the_bottom_put_still_ends_every_record():
    scenario = _alice_library("Devourer of Destiny", "Eldrazi Temple", "Forest", "Island")
    game = scenario.game
    (devourer,) = scenario.top_of_library(1)
    scenario.scry_bottoming(devourer)
    game.scry("alice", 1, source="Giant's Boulder")
    (temple,) = scenario.top_of_library(1)
    scenario.scry_bottoming(temple)
    game.scry("alice", 1, source="Giant's Boulder")
    assert [name for name, _ in known_in_library(game, "alice")] == [
        "Devourer of Destiny",
        "Eldrazi Temple",
    ]

    game.shuffle_library("alice")

    assert known_in_library(game, "alice") == []


def test_a_scry_that_moves_the_known_card_itself_ends_its_old_record():
    """CR 701.20d: the recorded card is one of the cards reordered. Bob's
    Bauble look at alice's top card is not the scrier's look, so it ends."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Lightning Bolt", "Forest", "Island"])
        .player("bob", battlefield=["Mishra's Bauble"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bolt,) = scenario.top_of_library(1)
    scenario.game.look(bolt, "bob", source="Mishra's Bauble")
    assert known_in_library(scenario.game, "bob") == [("Lightning Bolt", 0)]

    scenario.scry_bottoming(bolt)
    scenario.game.scry("alice", 1, source="Opt")

    assert known_in_library(scenario.game, "bob") == []
    assert known_in_library(scenario.game, "alice") == [("Lightning Bolt", 2)]
