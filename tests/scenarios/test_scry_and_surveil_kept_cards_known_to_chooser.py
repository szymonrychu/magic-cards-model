"""A player who scries, surveils, or looks at the top of their library and
splits it knows where every card they put back into that library went.

- **CR 701.22a** - "To 'scry N' means to look at the top N cards of your
  library, then put any number of them on the bottom of your library in any
  order and the rest on top of your library in any order."
- **CR 701.25a** - "To 'surveil N' means to look at the top N cards of your
  library, then put any number of them into your graveyard and the rest on top
  of your library in any order."
- **CR 701.20e** - "Looking at a card follows the same rules as revealing a
  card, except that the card is shown only to the specified player."
- **CR 701.20d** - "If cards in a player's library are shuffled or otherwise
  reordered, any revealed cards that are reordered stop being revealed and
  become new objects."

Putting the cards back is itself the reordering CR 701.20d names, so the look
that picked them up ends as they go back. What the chooser still knows is
where they put each one, which is why the record is made *after* the put-back,
against the library epoch that put-back produced: the chooser's knowledge
lasts exactly as long as the order they chose, and the next reordering - a
shuffle, CR 701.24a: "randomize the cards within it so that no player knows
their order" - ends it. A surveilled card put into a graveyard needs no record
at all: CR 400.2 makes the graveyard a public zone.

The look itself comes first: "look at the top N cards ..., then put" -
so while the choice of where each card goes is pending, the chooser
already knows the looked-at cards where they sit. That record is made
before the question is asked and ends at the put-back (CR 701.20d), where
the record of the chooser's own order replaces it.

A kept top card the chooser then draws stays known to them in hand - the
known-draw carry `tests/scenarios/test_known_card_drawn_stays_known.py` pins.

Opt (scry), Umbral Collar Zealot (surveil) and Commune with Nature (look at
the top and split to hand) are in neither deck pool; Preordain and Duskwatch
Recruiter are, and each is here beside the card that proves the reading is not
fitted to it.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import (
    CardSplit,
    DecisionKind,
    DecisionPending,
    ScriptedAnswer,
)
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario


def known(game: Game, viewer: str) -> list[tuple[str, Zone, int | None, bool]]:
    return [
        (entry.card_name, entry.zone, entry.index_from_top, entry.carried)
        for entry in game.known_to(viewer)
    ]


def known_in_library(game: Game, viewer: str) -> list[tuple[str, int | None]]:
    return [
        (entry.card_name, entry.index_from_top)
        for entry in game.known_to(viewer)
        if entry.zone is Zone.LIBRARY
    ]


def _script_split(scenario: Scenario, *, username: str, moved) -> None:
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=tuple(moved)), player=username)
    )


# -- scry (CR 701.22a) ---------------------------------------------------------


def test_a_scry_split_is_known_to_the_scrier_at_both_ends_of_the_library():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island", "Mountain", "Forest", "Swamp", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island, mountain, forest = scenario.top_of_library(3)
    scenario.scry_bottoming(island, top_order=[forest, mountain])

    scenario.game.scry("alice", 3, source="Preordain")

    alice = scenario.player("alice")
    assert [state.name for state in alice.library] == [
        "Forest",
        "Mountain",
        "Swamp",
        "Plains",
        "Island",
    ]
    assert known(scenario.game, "alice") == [
        ("Forest", Zone.LIBRARY, 0, False),
        ("Mountain", Zone.LIBRARY, 1, False),
        ("Island", Zone.LIBRARY, 4, False),
    ]
    assert known(scenario.game, "bob") == []
    for look in scenario.game.reveals:
        assert look.viewers == ["alice"], "CR 701.20e: a look, not a reveal"
        assert look.zone is Zone.LIBRARY
        assert look.source == "Preordain"
        assert look.library_epoch == alice.library_epoch, "recorded after the put-back"


def test_preordain_bottoms_one_and_draws_the_kept_card_which_stays_known():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Preordain"],
            library=["Island", "Mountain", "Forest", "Swamp"],
            battlefield=["Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    island, mountain = scenario.top_of_library(2)
    scenario.scry_bottoming(mountain)
    (source,) = scenario.untapped_sources("Island")

    scenario.cast_and_resolve("Preordain", source)

    assert island.zone is Zone.HAND
    assert [state.name for state in alice.library] == ["Forest", "Swamp", "Mountain"]
    assert known(scenario.game, "alice") == [
        ("Island", Zone.HAND, None, True),
        ("Mountain", Zone.LIBRARY, 2, False),
    ]
    assert known(scenario.game, "bob") == []


def test_opt_keeping_the_top_card_and_drawing_it_carries_it_into_hand():
    scenario = (
        Scenario()
        .player("alice", hand=["Opt"], library=["Lightning Bolt", "Plains"], battlefield=["Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island")
    scenario.scry_keeping_everything_on_top()

    scenario.cast_and_resolve("Opt", island)

    assert scenario.find("Lightning Bolt", Zone.HAND, "alice").zone is Zone.HAND
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.HAND, None, True)]
    assert known(scenario.game, "bob") == []


def test_opt_bottoming_a_card_keeps_it_known_until_a_shuffle_voids_it():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Opt"],
            library=["Lightning Bolt", "Island", "Plains"],
            battlefield=["Island", "Flooded Strand"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "alice")
    (island,) = scenario.untapped_sources("Island")
    scenario.scry_bottoming(bolt)

    scenario.cast_and_resolve("Opt", island)

    alice = scenario.player("alice")
    assert [state.name for state in alice.library] == ["Plains", "Lightning Bolt"]
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 1, False)]
    assert known(scenario.game, "bob") == []

    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)
    scenario.activate(strand)
    scenario.pass_until_resolved()

    assert [state.name for state in alice.library] == ["Lightning Bolt"]
    assert bolt.zone is Zone.LIBRARY, "the Bolt never moved - only the order did"
    assert known(scenario.game, "alice") == [], "CR 701.24a: no player knows the order"


# -- surveil (CR 701.25a) ------------------------------------------------------


def test_umbral_collar_zealot_surveil_keeping_the_card_makes_it_known_to_its_controller():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt", "Island"],
            battlefield=["Umbral Collar Zealot", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    zealot = scenario.creature("Umbral Collar Zealot", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.surveil_keeping_everything_on_top()

    scenario.activate(zealot, sacrificing=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]
    assert known(scenario.game, "bob") == []
    (look,) = scenario.game.reveals
    assert look.viewers == ["alice"]
    assert look.source == "Umbral Collar Zealot"


def test_a_surveilled_card_put_into_the_graveyard_gets_no_record():
    """CR 400.2: the graveyard is public, so there is nothing hidden to know."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island", "Mountain", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island, mountain = scenario.top_of_library(2)
    scenario.surveil_to_graveyard(island)

    scenario.game.surveil("alice", 2, source="Umbral Collar Zealot")

    assert island.zone is Zone.GRAVEYARD
    assert [look.card_name for look in scenario.game.reveals] == ["Mountain"]
    assert known(scenario.game, "alice") == [("Mountain", Zone.LIBRARY, 0, False)]
    assert known(scenario.game, "bob") == []


def test_a_surveil_that_puts_everything_into_the_graveyard_records_nothing():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island", "Mountain", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island, mountain = scenario.top_of_library(2)
    scenario.surveil_to_graveyard(island, mountain)

    scenario.game.surveil("alice", 2, source="Umbral Collar Zealot")

    assert scenario.game.reveals == []
    assert known(scenario.game, "alice") == []


# -- look at the top and split (Game.look_at_top_and_split) --------------------


def test_commune_with_nature_rest_on_the_bottom_is_known_to_the_caster_only():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Commune with Nature"],
            library=["Grizzly Bears", "Forest", "Mountain", "Swamp", "Island", "Plains"],
            battlefield=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    _script_split(scenario, username="alice", moved=[bears.id])
    (forest,) = scenario.untapped_sources("Forest")

    scenario.cast_and_resolve("Commune with Nature", forest)

    alice = scenario.player("alice")
    assert bears.zone is Zone.HAND
    assert [state.name for state in alice.library] == [
        "Plains",
        "Forest",
        "Mountain",
        "Swamp",
        "Island",
    ]
    assert known_in_library(scenario.game, "alice") == [
        ("Forest", 1),
        ("Mountain", 2),
        ("Swamp", 3),
        ("Island", 4),
    ]
    assert known_in_library(scenario.game, "bob") == []
    # The creature taken was revealed to everyone (CR 701.20a); every other
    # card was only looked at, by alice (CR 701.20e).
    shown = [look for look in scenario.game.reveals if look.zone is Zone.LIBRARY]
    assert [r.card_id for r in shown if r.viewers is None] == [bears.id]
    looks = [look for look in shown if look.viewers is not None]
    assert looks and all(look.viewers == ["alice"] for look in looks)
    assert len(looks) == len({look.card_id for look in looks}), "one look per card"


def test_duskwatch_recruiter_rest_on_the_bottom_is_known_until_a_shuffle():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest", "Flooded Strand"],
            library=["Grizzly Bears", "Forest", "Mountain", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    recruiter = scenario.creature("Duskwatch Recruiter")
    bears, _forest, _mountain = scenario.top_of_library(3)
    _script_split(scenario, username="alice", moved=[bears.id])

    scenario.activate(recruiter, *scenario.untapped_sources("Forest", "Forest", "Forest"))
    scenario.resolve_top()

    assert [state.name for state in scenario.player("alice").library] == [
        "Plains",
        "Forest",
        "Mountain",
    ]
    assert known_in_library(scenario.game, "alice") == [("Forest", 1), ("Mountain", 2)]
    assert known_in_library(scenario.game, "bob") == []

    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)
    scenario.activate(strand)
    scenario.pass_until_resolved()

    assert known_in_library(scenario.game, "alice") == []


def test_a_split_that_puts_nothing_back_leaves_no_library_knowledge_behind():
    """Every looked-at card left the library, so a later reordering of that
    library - the very next put - must not bring any of them back to life."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island", "Mountain", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island, mountain = scenario.top_of_library(2)
    game = scenario.game
    _script_split(scenario, username="alice", moved=[island.id])

    moved, rest = game.look_at_top_and_split(
        "alice", 2, moved_label="your graveyard", kept_label="exiled", source="Waker of Waves"
    )
    for state in moved:
        game.put_into_graveyard(state)
    game.exile_cards(rest)
    game.shuffle_library("alice")  # exactly one reordering after the split

    assert island.zone is Zone.GRAVEYARD and mountain.zone is Zone.EXILE
    assert known(game, "alice") == []


# -- while the choice is pending (the look comes before the put-back) ----------


def _paused_board() -> Scenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island", "Mountain", "Forest", "Swamp", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.decisions.pause_when_unanswered = True
    return scenario


@pytest.mark.parametrize(
    ("kind", "source"),
    [(DecisionKind.SCRY, "Preordain"), (DecisionKind.SURVEIL, "Otherworldly Gaze")],
)
def test_a_pending_scry_or_surveil_already_shows_the_chooser_the_cards_where_they_sit(kind, source):
    scenario = _paused_board()
    game = scenario.game
    ask = game.scry if kind is DecisionKind.SCRY else game.surveil

    with pytest.raises(DecisionPending) as excinfo:
        ask("alice", 3, source=source)

    assert excinfo.value.pending.decision.kind is kind
    assert known(game, "alice") == [
        ("Island", Zone.LIBRARY, 0, False),
        ("Mountain", Zone.LIBRARY, 1, False),
        ("Forest", Zone.LIBRARY, 2, False),
    ]
    assert known(game, "bob") == [], "CR 701.20e: a look is the chooser's alone"
    assert all(look.source == source and look.viewers == ["alice"] for look in game.reveals)


def test_a_pending_look_at_the_top_and_split_already_shows_the_chooser_the_cards():
    scenario = _paused_board()
    game = scenario.game

    with pytest.raises(DecisionPending):
        game.look_at_top_and_split(
            "alice",
            2,
            moved_label="your hand",
            kept_label="bottom of your library",
            source="Commune with Nature",
        )

    assert known(game, "alice") == [
        ("Island", Zone.LIBRARY, 0, False),
        ("Mountain", Zone.LIBRARY, 1, False),
    ]
    assert known(game, "bob") == []


def test_the_pending_look_is_replaced_by_the_put_back_record_not_added_to_it():
    """Answering leaves one look per card - the one against the chooser's own
    order - so the pending look neither outlives the put-back (CR 701.20d)
    nor doubles the record."""
    scenario = _paused_board()
    game = scenario.game
    island, mountain, forest = scenario.top_of_library(3)
    game.decisions.pause_when_unanswered = False
    scenario.scry_bottoming(island, top_order=[forest, mountain])

    game.scry("alice", 3, source="Preordain")

    assert sorted(str(look.card_id) for look in game.reveals) == sorted(
        str(state.id) for state in (island, mountain, forest)
    )
    assert known(game, "alice") == [
        ("Forest", Zone.LIBRARY, 0, False),
        ("Mountain", Zone.LIBRARY, 1, False),
        ("Island", Zone.LIBRARY, 4, False),
    ]
