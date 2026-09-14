"""Scenario: a mutating command shares the layered board between its mutations.

`Game.board_snapshot()` is suspended for the whole extent of a mutating
command, so a command's own reads are never served a board from before one of
its own edits. That left every read-only scan inside a command - the trigger
scans after an event, the state trigger sweep, the state-based action check -
rebuilding the board once per permanent: one play land on a 28-permanent
board computed it 122 times, and an api POST action paid that on every
request (2026-09-14).

The scans now open a scope of their own around the reading half only, with
no mutation inside it, so the board is shared within one scan and computed
afresh for the next. This file is the contract:

- **Count.** Playing a land, passing priority and resolving a spell each
  compute the board a small constant number of times, the same on a small
  board as on a large one (`snapshot.board_computations()`).
- **Equivalence.** The game after each command is byte-identical to the game
  after the same command with every board computed afresh
  (`snapshot.uncached_boards()`), triggers included.
- **No stale board inside a command.** A scan after a mutation in the same
  command reads the board that mutation left.

Every card here is a real printing; nothing is targeted by name.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models.game import Game
from magic_cards_model.snapshot import board_computations, uncached_boards
from tests.scenarios.harness import PlayedScenario, Scenario
from tests.scenarios.test_board_snapshot import ALICE_PERMANENTS, BOB_PERMANENTS

#: How many times a command may compute the board, whatever the size of the
#: battlefield: one per read-only scan it runs, and no scan repeats per
#: permanent. Resolving a creature spell is the busiest here at 13 - two
#: state-based action rounds (the losers check and the equipment check after
#: it), two state trigger sweeps, the entering permanent's replacement,
#: loyalty, lore and enters-event reads, and the trigger scan for the event.
BOARDS_PER_COMMAND = 16

SMALL_ALICE = ["Forest", "Forest", "Glorious Anthem", "Llanowar Elves"]
SMALL_BOB = BOB_PERMANENTS[:2]


def _scenario(alice: list[str], bob: list[str]) -> PlayedScenario:
    """A precombat main phase with alice holding priority and a land and a
    two-mana creature in hand."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Plains", "Grizzly Bears"], library=["Island"] * 5, battlefield=alice
        )
        .player("bob", library=["Island"] * 5, battlefield=bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # The city's blessing check reads the board only once a player without the
    # blessing controls ten permanents: a threshold, not a per-permanent cost,
    # but one the small board and the large one fall on opposite sides of.
    # Both players already have it, so both boards pay the same.
    for player in scenario.game.players:
        player.has_citys_blessing = True
    return scenario


def _play_land(game: Game) -> None:
    plains = next(card for card in game.player("alice").hand if card.name == "Plains")
    game.play_land(plains, "alice")


def _pass_priority(game: Game) -> None:
    game.pass_priority("alice")


def _resolve(game: Game) -> None:
    game.pass_priority("bob")


COMMANDS: dict[str, Callable[[Game], None]] = {
    "play_land": _play_land,
    "pass_priority": _pass_priority,
    "resolve": _resolve,
}


def _run(raw: str, command: Callable[[Game], None]) -> tuple[int, str]:
    game = Game.model_validate_json(raw)
    before = board_computations()
    command(game)
    return board_computations() - before, game.model_dump_json()


def _starting_points(alice: list[str], bob: list[str]) -> dict[str, str]:
    """Each command's starting game as JSON, so every run of it starts from the
    very same game, ids included. For `resolve`, alice's Grizzly Bears are on
    the stack and alice has passed, so bob's pass resolves them."""
    raw = _scenario(alice, bob).game.model_dump_json()
    stacked = _scenario(alice, bob)
    forests = stacked.untapped_sources("Forest", "Forest", username="alice")
    stacked.cast_onto_stack("Grizzly Bears", *forests, username="alice")
    stacked.pass_priority("alice")
    return {"play_land": raw, "pass_priority": raw, "resolve": stacked.game.model_dump_json()}


def test_a_command_computes_the_board_a_constant_number_of_times():
    small = _starting_points(SMALL_ALICE, SMALL_BOB)
    large = _starting_points(ALICE_PERMANENTS, BOB_PERMANENTS)
    assert len(Game.model_validate_json(large["play_land"]).battlefield) >= 20

    counts = {
        name: (_run(small[name], command)[0], _run(large[name], command)[0])
        for name, command in COMMANDS.items()
    }

    assert all(large_count <= BOARDS_PER_COMMAND for _, large_count in counts.values()), counts
    assert all(small_count == large_count for small_count, large_count in counts.values()), counts


def test_a_command_leaves_the_same_game_as_with_every_board_computed_afresh():
    for alice, bob in ((SMALL_ALICE, SMALL_BOB), (ALICE_PERMANENTS, BOB_PERMANENTS)):
        for name, raw in _starting_points(alice, bob).items():
            _, cached = _run(raw, COMMANDS[name])
            with uncached_boards():
                _, uncached = _run(raw, COMMANDS[name])
            assert cached == uncached, name


def _dress_down_resolving() -> str:
    """alice's Dress Down ("Creatures lose all abilities.") on the stack with
    alice passed, so bob's pass resolves it. Bob's Grizzly Bears have 2
    damage and survive only as a 3/3 under his Angel of Jubilation's "Other
    nonblack creatures you control get +1/+1"; alice has Blood Artist
    ("Whenever this creature or another creature dies, ...")."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dress Down"],
            library=["Island"] * 5,
            battlefield=["Island", "Island", "Blood Artist"],
        )
        .player("bob", library=["Island"] * 5, battlefield=["Angel of Jubilation", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.damage = 2
    assert scenario.game.characteristics_of(bears).toughness == 3
    scenario.cast_onto_stack(
        "Dress Down",
        *scenario.untapped_sources("Island", "Island", username="alice"),
        username="alice",
    )
    scenario.pass_priority("alice")
    return scenario.game.model_dump_json()


def test_a_scan_after_a_mutation_in_the_same_command_reads_the_board_it_left():
    """One pass resolves Dress Down, and the same command then checks
    state-based actions and scans for triggers. The moment Dress Down is on
    the battlefield the Angel has no abilities, the Bears are a 2/2 with 2
    damage, and they die. A check served the board from before Dress Down
    entered would keep them alive; the game is the same with every board
    computed afresh."""
    raw = _dress_down_resolving()

    _, cached = _run(raw, _resolve)
    with uncached_boards():
        _, uncached = _run(raw, _resolve)
    assert cached == uncached

    game = Game.model_validate_json(cached)
    assert [card.name for card in game.player("bob").graveyard] == ["Grizzly Bears"]
    triggered = [item.source_name for item in (*game.stack, *game.pending_triggers)]
    assert "Dress Down" in triggered, triggered


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Blood Artist still triggers on a creature that dies after Dress Down removed its "
        "abilities. Dying is being put into a graveyard from the battlefield (CR 700.4), so "
        "its trigger looks back in time (CR 603.10a) and uses the abilities that existed "
        "immediately before the event (CR 603.10) - when Blood Artist had none. The same "
        "happens with every board computed afresh, so it is a trigger-reading gap, not a "
        "board snapshot one."
    ),
)
def test_a_creature_that_lost_its_dies_trigger_does_not_trigger():
    _, cached = _run(_dress_down_resolving(), _resolve)

    game = Game.model_validate_json(cached)
    assert [card.name for card in game.player("bob").graveyard] == ["Grizzly Bears"]
    triggered = [item.source_name for item in (*game.stack, *game.pending_triggers)]
    assert "Blood Artist" not in triggered, triggered


def test_computing_the_board_inside_a_command_mints_no_game_ids():
    """The effects a board is built from are rebuilt on every computation and
    thrown away with it. If they drew on the game's deterministic id counter,
    how often a command happened to compute the board - which a snapshot
    scope, or another thread's change moving its epoch, decides - would change
    `objects_created` and every id minted after it, and a replayed command
    would no longer mint the ids it minted the first time."""
    game = _scenario(ALICE_PERMANENTS, BOB_PERMANENTS).game
    before = game.objects_created

    with game._id_allocator_scope():
        game.computed_board()
        game.computed_board()

    assert game.objects_created == before
