"""Scenario: `snapshot.scan_pin`, one board for a read-only scan inside a command.

`snapshot.command` never caches, so the engine's own scans that run inside a
command - the trigger scan after an event, the state trigger sweep, the
state-based action losers check - pin the board for their extent instead
(`tests/scenarios/test_board_snapshot_commands.py` is what they buy). A pin
is only safe if nothing that bears on the board can land while it is held, so
this file is its contract, each case both outside and inside a command on the
same game:

- **Once.** A pinned scan computes the board once.
- **Dropped.** A field store, an announced `Counters` edit and a `ManaPool`
  edit on the pinned game each drop the pin, and the next read sees the change.
- **Lifted.** A command started inside the pin lifts it; the read after it
  sees what the command did.
- **Isolated.** Neither another thread nor a context copied inside the pin is
  served it, while it is open or after it ends; `uncached_boards()` bypasses it.

Every card here is a real printing; nothing is targeted by name.
"""

from __future__ import annotations

import contextvars
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import CardState, Color
from magic_cards_model.models.game import Game
from magic_cards_model.snapshot import board_computations, scan_pin, uncached_boards
from tests.scenarios.harness import PlayedScenario, Scenario
from tests.scenarios.test_board_snapshot import ALICE_PERMANENTS, BOB_PERMANENTS


def _scenario(alice: list[str], bob: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 5, battlefield=alice)
        .player("bob", library=["Island"] * 5, battlefield=bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- the scan pin a command's read-only scan opens ----------------------------


def _anthem_board() -> tuple[Game, CardState, CardState]:
    """alice's Llanowar Elves under her Glorious Anthem ("Creatures you control
    get +1/+1."), a 2/2 on the computed board."""
    game = _scenario(ALICE_PERMANENTS, BOB_PERMANENTS).game
    anthem = next(card for card in game.battlefield if card.name == "Glorious Anthem")
    elves = next(card for card in game.battlefield if card.name == "Llanowar Elves")
    return game, anthem, elves


@contextmanager
def _maybe_commanding(game: Game, commanding: bool) -> Iterator[None]:
    """The scans a pin exists for run inside a command on the same game."""
    if commanding:
        with game._id_allocator_scope():
            yield
    else:
        yield


def _power(game: Game, state: CardState) -> int | str | None:
    return game.characteristics_of(state).power


COMMANDING = pytest.mark.parametrize("commanding", [False, True], ids=["reading", "in-a-command"])


@COMMANDING
def test_a_pinned_scan_computes_the_board_once(commanding):
    game, _, elves = _anthem_board()

    with _maybe_commanding(game, commanding):
        before = board_computations()
        with scan_pin(game):
            for permanent in game.battlefield:
                game.characteristics_of(permanent)
            _power(game, elves)
        assert board_computations() - before == 1


@COMMANDING
def test_a_field_store_inside_a_pinned_scan_drops_the_pin(commanding):
    """Handing the Elves to bob takes them out from under alice's Anthem."""
    game, _, elves = _anthem_board()

    with _maybe_commanding(game, commanding), scan_pin(game):
        assert _power(game, elves) == 2
        elves.controller = "bob"
        assert _power(game, elves) == 1


@COMMANDING
def test_a_counters_edit_inside_a_pinned_scan_drops_the_pin(commanding):
    game, _, elves = _anthem_board()

    with _maybe_commanding(game, commanding), scan_pin(game):
        assert _power(game, elves) == 2
        elves.counters.add("+1/+1", 1)
        assert _power(game, elves) == 3


@COMMANDING
def test_a_mana_pool_edit_inside_a_pinned_scan_drops_the_pin(commanding):
    """Omnath, Locus of Mana: "Omnath gets +1/+1 for each unspent green mana you
    have." - read off the mana pool by the layered board."""
    scenario = _scenario(["Omnath, Locus of Mana", "Forest"], ["Island"])
    game = scenario.game
    omnath = next(card for card in game.battlefield if card.name == "Omnath, Locus of Mana")

    with _maybe_commanding(game, commanding), scan_pin(game):
        assert _power(game, omnath) == 1
        game.player("alice").mana_pool.add(Color.GREEN, 2)
        assert _power(game, omnath) == 3


@COMMANDING
def test_a_nested_command_inside_a_pinned_scan_drops_the_pin(commanding):
    """Destroying the Anthem is a command; the read after it sees the Elves
    without the Anthem's +1/+1."""
    game, anthem, elves = _anthem_board()

    with _maybe_commanding(game, commanding), scan_pin(game):
        assert _power(game, elves) == 2
        game.destroy(anthem)
        assert _power(game, elves) == 1


def test_a_pin_is_not_used_by_another_thread():
    game, _, elves = _anthem_board()
    counts: list[int] = []

    def read_twice() -> None:
        before = board_computations()
        _power(game, elves)
        _power(game, elves)
        counts.append(board_computations() - before)

    with scan_pin(game):
        _power(game, elves)
        worker = threading.Thread(target=read_twice)
        worker.start()
        worker.join()

    assert counts == [2]


def test_a_context_copied_inside_a_pin_does_not_use_it():
    """Neither in another thread while the pin is open, nor anywhere once the
    pin's block has ended."""
    game, _, elves = _anthem_board()
    counts: list[int] = []

    def read_twice() -> None:
        before = board_computations()
        _power(game, elves)
        _power(game, elves)
        counts.append(board_computations() - before)

    with scan_pin(game):
        _power(game, elves)
        copied = contextvars.copy_context()
        worker = threading.Thread(target=copied.run, args=(read_twice,))
        worker.start()
        worker.join()
    copied.run(read_twice)

    assert counts == [2, 2]


def test_uncached_boards_computes_afresh_inside_a_pinned_scan():
    game, _, elves = _anthem_board()

    before = board_computations()
    with uncached_boards(), scan_pin(game):
        _power(game, elves)
        _power(game, elves)
    assert board_computations() - before == 2
