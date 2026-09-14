"""Scenario: one layered board per read-only enumeration, and never a stale one.

`Game.computed_board` applies every continuous effect to the whole
battlefield, and is deliberately recomputed on every call outside a scope:
the board has to follow the game the moment anything changes. Read-only work
used to pay for that once per permanent and per ability - `legal_actions` on
a 25-permanent board rebuilt the board almost two hundred times - so its cost
grew with the square of the battlefield.

`Game.board_snapshot()` is the explicit scope inside which the board is
computed once and reused, and `machines.legal_actions.legal_actions` opens one
itself. This file is the contract that scope has to keep:

- **Count.** `legal_actions` computes the board a small constant number of
  times, and that number does not grow with the battlefield. Counted by the
  engine's own `snapshot.board_computations()`, not a mock.
- **Equivalence.** The same boards answer identically inside a scope and with
  caching switched off (`snapshot.uncached_boards()`): an anthem, a type
  changing effect that adds abilities, an ability-removing one, an effect
  whose result depends on other permanents, and a control change.
- **Invalidation.** A zone move, counters, a tap and a control change made
  through real engine commands inside a scope are all seen by the very next
  read. A change the engine was not told about - an in-place edit to a zone
  list, or a caller writing into a returned board - raises
  `BoardSnapshotStale` rather than serving a stale board.

Every card here is a real printing; nothing is targeted by name.
"""

from __future__ import annotations

import json
from uuid import NAMESPACE_OID, uuid5

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.game import Game
from magic_cards_model.snapshot import BoardSnapshotStale, board_computations, uncached_boards
from tests.cards import card_state
from tests.scenarios.harness import PlayedScenario, Scenario

#: Twelve permanents for alice: lands, a mana creature, creatures with tap and
#: non-tap activated abilities, a triggered ability, an anthem (layer 7), a
#: land-type grant that adds a mana ability (layers 4 and 6), and a creature
#: whose power and toughness read every graveyard.
ALICE_PERMANENTS = [
    "Glorious Anthem",
    "Llanowar Elves",
    "Mother of Runes",
    "Walking Ballista",
    "Blood Artist",
    "Tarmogoyf",
    "Urborg, Tomb of Yawgmoth",
    "Forest",
    "Forest",
    "Plains",
    "Swamp",
    "Sol Ring",
]

#: Ten more for bob, with abilities of their own.
BOB_PERMANENTS = [
    "Grizzly Bears",
    "Ornithopter",
    "Memnite",
    "Guide of Souls",
    "Mother of Runes",
    "Llanowar Elves",
    "Mountain",
    "Mountain",
    "Island",
    "Island",
]


def _board(alice: list[str], bob: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Llanowar Elves", "Walking Ballista"],
            graveyard=["Memnite"],
            battlefield=alice,
        )
        .player("bob", hand=["Grizzly Bears"], graveyard=["Forest"], battlefield=bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _actions(game: Game, player: str) -> str:
    return json.dumps(
        [action.model_dump(mode="json") for action in legal_actions(game, player)], sort_keys=True
    )


def _characteristics(game: Game) -> dict[str, dict]:
    return {
        str(permanent.id): game.characteristics_of(permanent).model_dump(mode="json")
        for permanent in game.battlefield
    }


def _computations_during(read) -> int:
    before = board_computations()
    read()
    return board_computations() - before


# -- count -------------------------------------------------------------------


def test_legal_actions_computes_the_board_a_constant_number_of_times():
    """The whole enumeration shares one board, however many permanents ask."""
    small = _board(ALICE_PERMANENTS[:3], BOB_PERMANENTS[:2])
    large = _board(ALICE_PERMANENTS, BOB_PERMANENTS)
    assert len(large.game.battlefield) >= 20

    for scenario in (small, large):
        legal_actions(scenario.game, "alice")  # warm the timestamp registry

    small_count = _computations_during(lambda: legal_actions(small.game, "alice"))
    large_count = _computations_during(lambda: legal_actions(large.game, "alice"))

    assert large_count <= 2, f"legal_actions computed the board {large_count} times"
    assert large_count == small_count, (
        f"the count grew with the battlefield: {small_count} for "
        f"{len(small.game.battlefield)} permanents, {large_count} for "
        f"{len(large.game.battlefield)}"
    )


def test_outside_a_snapshot_every_read_recomputes():
    """Outside a scope the board is exactly as uncached as it always was."""
    game = _board(ALICE_PERMANENTS, BOB_PERMANENTS).game
    goyf = next(card for card in game.battlefield if card.name == "Tarmogoyf")

    count = _computations_during(
        lambda: (game.computed_board(), game.computed_board(), game.characteristics_of(goyf))
    )

    assert count == 3


def test_inside_a_snapshot_the_board_is_computed_once():
    game = _board(ALICE_PERMANENTS, BOB_PERMANENTS).game
    boards = []

    def read() -> None:
        with game.board_snapshot():
            boards.append(game.computed_board())
            for permanent in game.battlefield:
                game.characteristics_of(permanent)
            boards.append(game.computed_board())

    assert _computations_during(read) == 1
    assert boards[0] is boards[1]


def test_nested_snapshots_share_one_board_and_the_outer_one_ends_it():
    game = _board(ALICE_PERMANENTS, BOB_PERMANENTS).game

    def read() -> None:
        with game.board_snapshot():
            game.computed_board()
            with game.board_snapshot():
                game.computed_board()
            game.computed_board()

    assert _computations_during(read) == 1
    assert _computations_during(game.computed_board) == 1, "no board survives the scope"


# -- equivalence -------------------------------------------------------------


def _assert_equivalent(scenario: PlayedScenario) -> None:
    game = scenario.game
    players = [player.username for player in game.players]
    for username in players:
        legal_actions(game, username)  # warm the timestamp registry

    with uncached_boards():
        expected = {username: _actions(game, username) for username in players}
        expected_board = _characteristics(game)

    with game.board_snapshot():
        scoped = {username: _actions(game, username) for username in players}
        scoped_board = _characteristics(game)

    unscoped = {username: _actions(game, username) for username in players}

    assert scoped == expected
    assert unscoped == expected
    assert scoped_board == expected_board


def test_an_anthem_a_land_type_grant_and_a_graveyard_count_read_the_same():
    _assert_equivalent(_board(ALICE_PERMANENTS, BOB_PERMANENTS))


def test_an_ability_removing_effect_and_its_dependency_read_the_same():
    """Humility removes abilities and sets power and toughness while Opalescence
    turns every other enchantment - Humility included - into a creature, so each
    one's result depends on the other permanent being there."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Humility", "Opalescence", "Glorious Anthem", "Llanowar Elves", "Forest"],
        )
        .player("bob", battlefield=["Mother of Runes", "Walking Ballista", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    board = scenario.game.computed_board()
    humility = next(card for card in scenario.game.battlefield if card.name == "Humility")
    assert board.of(humility).power is not None, "the dependency is really on this board"

    _assert_equivalent(scenario)


def test_land_type_changing_effects_read_the_same():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Blood Moon", "Urborg, Tomb of Yawgmoth", "Karplusan Forest", "Forest"],
        )
        .player("bob", battlefield=["Urza's Saga", "Swamp", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _assert_equivalent(scenario)


def _stolen_mother() -> tuple[PlayedScenario, object]:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Act of Treason"], battlefield=["Mountain"] * 3)
        .player("bob", battlefield=["Mother of Runes", "Grizzly Bears", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.creature("Mother of Runes", "bob")
    return scenario, mother


def test_a_control_change_reads_the_same():
    scenario, mother = _stolen_mother()
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Act of Treason", *mountains, targets=[mother])
    assert scenario.game.characteristics_of(mother).controller == "alice"

    _assert_equivalent(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    _assert_equivalent(scenario)


# -- invalidation ------------------------------------------------------------


def _truth(game: Game, permanent) -> dict:
    with uncached_boards():
        return game.characteristics_of(permanent).model_dump(mode="json")


def _goyf_board() -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tarmogoyf", "Glorious Anthem", "Grizzly Bears", "Forest"])
        .player("bob", battlefield=["Llanowar Elves", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_zone_move_inside_a_snapshot_is_seen_by_the_next_read():
    scenario = _goyf_board()
    game = scenario.game
    goyf = scenario.creature("Tarmogoyf", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    with game.board_snapshot():
        before = game.characteristics_of(goyf).power
        assert game.characteristics_of(goyf).power == before
        game.destroy(bears)
        after = game.characteristics_of(goyf).model_dump(mode="json")
        assert after == _truth(game, goyf)
        assert after["power"] == before + 1, "a creature card reached a graveyard"
        assert bears.id not in game.computed_board().characteristics


def test_counters_put_on_inside_a_snapshot_are_seen_by_the_next_read():
    scenario = _goyf_board()
    game = scenario.game
    bears = scenario.creature("Grizzly Bears", "alice")

    with game.board_snapshot():
        before = game.characteristics_of(bears).power
        game.add_counters(bears, "+1/+1", 2)
        assert game.characteristics_of(bears).power == before + 2
        bears.add_counters("+1/+1", 1)
        assert game.characteristics_of(bears).power == before + 3
        assert game.characteristics_of(bears).model_dump(mode="json") == _truth(game, bears)


def test_a_tap_inside_a_snapshot_is_seen_by_the_next_read():
    scenario = _goyf_board()
    game = scenario.game
    forest = scenario.untapped_sources("Forest", username="alice")[0]

    with game.board_snapshot():
        untapped = _actions(game, "alice")
        computations = board_computations()
        forest.tap()
        game.computed_board()
        assert board_computations() == computations + 1, "a tap invalidates the snapshot"
        tapped = _actions(game, "alice")
        with uncached_boards():
            assert tapped == _actions(game, "alice")
    assert tapped != untapped


def test_a_control_change_inside_a_snapshot_is_seen_by_the_next_read():
    scenario, mother = _stolen_mother()
    game = scenario.game
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")

    with game.board_snapshot():
        assert game.characteristics_of(mother).controller == "bob"
        assert game.characteristics_of(mother).controller == "bob"
        scenario.cast_and_resolve("Act of Treason", *mountains, targets=[mother])
        assert game.characteristics_of(mother).controller == "alice"
        assert game.characteristics_of(mother).model_dump(mode="json") == _truth(game, mother)


def _unannounced_bears():
    """A real printing slipped into a zone list by hand. Its ids are fixed so the
    replay run builds the very same object."""
    return card_state(
        "Grizzly Bears",
        Zone.GRAVEYARD,
        owner="bob",
        controller="bob",
        id=uuid5(NAMESPACE_OID, "an unannounced zone edit"),
        zone_change_stamp=uuid5(NAMESPACE_OID, "an unannounced zone edit stamp"),
    )


def test_an_unannounced_zone_edit_raises_at_scope_exit():
    """A list edited in place tells nobody. The scope refuses to end as though
    its board were still true."""
    scenario = _goyf_board()
    game = scenario.game
    goyf = scenario.creature("Tarmogoyf", "alice")

    with pytest.raises(BoardSnapshotStale), game.board_snapshot():
        game.characteristics_of(goyf)
        game.characteristics_of(goyf)
        game.player("bob").graveyard.append(_unannounced_bears())


def test_an_unannounced_zone_edit_raises_at_the_next_announced_change():
    scenario = _goyf_board()
    game = scenario.game
    goyf = scenario.creature("Tarmogoyf", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    with game.board_snapshot():
        game.characteristics_of(goyf)
        game.player("bob").graveyard.append(_unannounced_bears())
        with pytest.raises(BoardSnapshotStale):
            bears.tapped = True
        assert game.characteristics_of(goyf).model_dump(mode="json") == _truth(game, goyf)


def test_writing_into_a_returned_board_raises():
    """A board is shared inside a scope, so a caller writing into one would
    poison every later read. It is refused loudly instead."""
    scenario = _goyf_board()
    game = scenario.game
    bears = scenario.creature("Grizzly Bears", "alice")

    with pytest.raises(BoardSnapshotStale), game.board_snapshot():
        game.computed_board().of(bears).counters["+1/+1"] = 5
