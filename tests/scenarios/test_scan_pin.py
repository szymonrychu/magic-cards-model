"""Scenario: `snapshot.scan_pin`, one board for a read-only scan inside a command.

`snapshot.command` never caches, so the engine's own scans that run inside a
command - the trigger scan after an event, the state trigger sweep, the
state-based action losers check - pin the board for their extent instead
(`tests/scenarios/test_board_snapshot_commands.py` is what they buy). A pin
is only safe if nothing that bears on the board can land while it is held, so
this file is its contract, each case both outside and inside a command on the
same game:

- **Once.** A pinned scan computes the board once.
- **Dropped.** A field store, an announced `Counters` edit, a `ManaPool` edit
  and an announced in-place edit of the game (a payment's open pool) on the
  pinned game each drop the pin, and the next read sees the change.
- **Lifted.** A command started inside the pin lifts it; the read after it
  sees what the command did.
- **From any thread.** Each of those changes made by another thread drops the
  pin too, wherever the pinned read is when it lands - filling the pin or
  served from it - and wherever the change is in dropping it.
- **Isolated.** Neither another thread nor a context copied inside the pin is
  served it, while it is open or after it ends, nor is the opening context
  once the block has ended; `uncached_boards()` bypasses it.

Every card here is a real printing; nothing is targeted by name.
"""

from __future__ import annotations

import contextvars
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import FrameType
from typing import Any

import pytest

from magic_cards_model import snapshot
from magic_cards_model.machines import Step
from magic_cards_model.models import CardState, Color
from magic_cards_model.models.game import Game
from magic_cards_model.models.mana import ManaPool
from magic_cards_model.snapshot import (
    announce_mutation,
    board_computations,
    mutation_landed,
    scan_pin,
    uncached_boards,
)
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


def _anthem_board(
    alice: list[str] | None = None, bob: list[str] | None = None
) -> tuple[Game, CardState, CardState]:
    """alice's Llanowar Elves under her Glorious Anthem ("Creatures you control
    get +1/+1."), a 2/2 on the computed board."""
    game = _scenario(alice or ALICE_PERMANENTS, bob or BOB_PERMANENTS).game
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


def test_a_pin_does_not_serve_its_own_context_after_its_block_ends():
    game, _, elves = _anthem_board()

    with scan_pin(game):
        _power(game, elves)
    before = board_computations()
    _power(game, elves)
    _power(game, elves)

    assert board_computations() - before == 2


# -- a pin opened inside a board snapshot --------------------------------------


def test_a_pin_opened_inside_a_snapshot_holding_a_board_computes_nothing():
    """The payment planner opens a pin per mana source it asks about; a scope
    that already holds a good board serves every one of them."""
    game, _, elves = _anthem_board()

    with game.board_snapshot():
        _power(game, elves)
        before = board_computations()
        for _ in range(3):
            with scan_pin(game):
                _power(game, elves)
                _power(game, elves)
        assert board_computations() - before == 0


def test_a_pin_opened_inside_a_snapshot_before_it_holds_a_board_fills_the_snapshot():
    game, _, elves = _anthem_board()

    with game.board_snapshot():
        before = board_computations()
        with scan_pin(game):
            _power(game, elves)
        with scan_pin(game):
            _power(game, elves)
        _power(game, elves)
        assert board_computations() - before == 1


def test_a_field_store_inside_a_pin_inside_a_snapshot_is_seen_by_the_next_read():
    game, _, elves = _anthem_board()

    with game.board_snapshot():
        assert _power(game, elves) == 2
        with scan_pin(game):
            assert _power(game, elves) == 2
            elves.controller = "bob"
            assert _power(game, elves) == 1
        assert _power(game, elves) == 1


def test_a_counters_edit_inside_a_pin_inside_a_snapshot_is_seen_by_the_next_read():
    game, _, elves = _anthem_board()

    with game.board_snapshot(), scan_pin(game):
        assert _power(game, elves) == 2
        elves.counters.add("+1/+1", 1)
        assert _power(game, elves) == 3


def test_a_change_from_another_thread_inside_a_pin_inside_a_snapshot_is_seen():
    game, _, elves = _anthem_board()

    with game.board_snapshot(), scan_pin(game):
        assert _power(game, elves) == 2
        worker = threading.Thread(target=lambda: setattr(elves, "controller", "bob"))
        worker.start()
        worker.join()
        assert _power(game, elves) == 1


def test_a_command_inside_a_pin_inside_a_snapshot_is_seen_by_the_next_read():
    game, anthem, elves = _anthem_board()

    with game.board_snapshot(), scan_pin(game):
        assert _power(game, elves) == 2
        game.destroy(anthem)
        assert _power(game, elves) == 1


def test_a_pin_inside_a_command_inside_a_snapshot_computes_its_own_board_once():
    """A command suspends the snapshot on its game, so a scan inside it pins
    exactly as it does with no snapshot open."""
    game, _, elves = _anthem_board()

    with game.board_snapshot():
        _power(game, elves)
        with game._id_allocator_scope():
            before = board_computations()
            with scan_pin(game):
                _power(game, elves)
                _power(game, elves)
            assert board_computations() - before == 1


# -- an announced in-place edit of the game ------------------------------------


def _omnath_board() -> tuple[Game, CardState]:
    """alice's Omnath, Locus of Mana: "Omnath gets +1/+1 for each unspent green
    mana you have." - a 1/1 with nothing floating."""
    game = _scenario(["Omnath, Locus of Mana", "Forest"], ["Island"]).game
    omnath = next(card for card in game.battlefield if card.name == "Omnath, Locus of Mana")
    return game, omnath


def _open_a_payment_pool(game: Game, username: str, green: int) -> None:
    """What a mana payment does as it opens (`machines.cost`): publish its
    working pool as the payer's unspent mana, an in-place edit of
    `Game.open_payment_pools` announced around the edit."""
    working = ManaPool()
    working.add(Color.GREEN, green)
    announce_mutation(game)
    game.open_payment_pools[username] = working
    mutation_landed(game)


@COMMANDING
def test_an_announced_edit_of_the_game_inside_a_pinned_scan_drops_the_pin(commanding):
    game, omnath = _omnath_board()

    with _maybe_commanding(game, commanding), scan_pin(game):
        assert _power(game, omnath) == 1
        _open_a_payment_pool(game, "alice", 2)
        assert _power(game, omnath) == 3


# -- changes made by another thread --------------------------------------------


def _anthem(game: Game) -> CardState:
    return next(card for card in game.battlefield if card.name == "Glorious Anthem")


def _elves_board() -> tuple[Game, CardState]:
    game, _, elves = _anthem_board()
    return game, elves


#: Each change a pin must not survive: the board it is made on, the change, and
#: the subject's power before and after it.
CHANGES: dict[
    str,
    tuple[Callable[[], tuple[Game, CardState]], Callable[[Game, CardState], object], int, int],
] = {
    "field-store": (_elves_board, lambda game, elves: setattr(elves, "controller", "bob"), 2, 1),
    "counters": (_elves_board, lambda game, elves: elves.counters.add("+1/+1", 1), 2, 3),
    "mana-pool": (
        _omnath_board,
        lambda game, omnath: game.player("alice").mana_pool.add(Color.GREEN, 2),
        1,
        3,
    ),
    "announced-game-edit": (
        _omnath_board,
        lambda game, omnath: _open_a_payment_pool(game, "alice", 2),
        1,
        3,
    ),
    "command": (_elves_board, lambda game, elves: game.destroy(_anthem(game)), 2, 1),
}


def _in_another_thread(work: Callable[[], object]) -> None:
    failures: list[BaseException] = []

    def run() -> None:
        try:
            work()
        except BaseException as error:  # re-raised in the calling thread below
            failures.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    if failures:
        raise failures[0]


@COMMANDING
@pytest.mark.parametrize("change", CHANGES)
def test_a_change_from_another_thread_drops_the_pin(change, commanding):
    build, make, before, after = CHANGES[change]
    game, subject = build()

    with _maybe_commanding(game, commanding), scan_pin(game):
        assert _power(game, subject) == before
        _in_another_thread(lambda: make(game, subject))
        assert _power(game, subject) == after


Trace = Callable[[FrameType, str, Any], Any]


def _counting_lines(pause_at: int, at_pause: Callable[[], None]) -> Trace:
    """A local trace function that runs `at_pause()` once, just before the
    `pause_at`-th line it sees (counted from zero, across every frame it is
    installed on)."""
    lines = 0

    def local(frame: FrameType, event: str, arg: Any) -> Trace:
        nonlocal lines
        if event == "line":
            if lines == pause_at:
                at_pause()
            lines += 1
        return local

    return local


@contextmanager
def _traced(trace: Trace) -> Iterator[None]:
    sys.settrace(trace)
    try:
        yield
    finally:
        sys.settrace(None)


def _small_anthem_board() -> tuple[Game, CardState]:
    game, _, elves = _anthem_board(["Glorious Anthem", "Llanowar Elves", "Forest"], ["Island"])
    return game, elves


def _change_at_a_line_of_the_read(pause_at: int, reading: str, commanding: bool) -> bool:
    """One interleaving of `test_a_change_from_another_thread_at_any_line_...`:
    whether the read had a `pause_at`-th line to interrupt."""
    game, elves = _small_anthem_board()
    changed: list[int] = []

    def hand_the_elves_to_bob() -> None:
        _in_another_thread(lambda: setattr(elves, "controller", "bob"))
        changed.append(pause_at)

    local = _counting_lines(pause_at, hand_the_elves_to_bob)
    outermost: list[FrameType] = []

    def trace(frame: FrameType, event: str, arg: Any) -> Trace | None:
        if event == "call" and not outermost and frame.f_code is snapshot.cached_board.__code__:
            outermost.append(frame)
            return local
        return None

    with _maybe_commanding(game, commanding), scan_pin(game):
        if reading == "served":
            assert _power(game, elves) == 2
        with _traced(trace):
            interrupted = _power(game, elves)
        if not changed:
            return False
        assert interrupted in (1, 2), (pause_at, interrupted)
        assert _power(game, elves) == 1, pause_at
    return True


@COMMANDING
@pytest.mark.parametrize("reading", ["filling", "served"])
def test_a_change_from_another_thread_at_any_line_of_a_pinned_read_is_never_missed(
    reading, commanding
):
    """Another thread hands the Elves to bob at every line boundary of one read
    of the pinned board - the read that fills the pin, or one it serves - and
    the read after it sees the change. The read the change interrupted may
    answer either way; it must not crash, and it must not leave the pin
    holding the board from before the change."""
    pause_at = 0
    while _change_at_a_line_of_the_read(pause_at, reading, commanding):
        pause_at += 1

    assert pause_at > 2


def _inside(frame: FrameType | None, outer: FrameType) -> bool:
    while frame is not None:
        if frame is outer:
            return True
        frame = frame.f_back
    return False


def _fill_during_a_drop_at_line(pause_at: int, commanding: bool) -> bool:
    """One interleaving of `test_a_pin_filled_while_another_thread_is_...`:
    whether the drop after the writer's store had a `pause_at`-th line to be
    held at."""
    game, elves = _small_anthem_board()
    announced = threading.Event()
    computed = threading.Event()
    held = threading.Event()
    read_done = threading.Event()
    paused: list[int] = []
    failures: list[BaseException] = []

    def hold_the_writer() -> None:
        paused.append(pause_at)
        held.set()
        assert read_done.wait(10), "the pinned read never finished"

    landed_drop = _counting_lines(pause_at, hold_the_writer)
    announcing: list[FrameType] = []

    def before_returned(frame: FrameType, event: str, arg: Any) -> Trace | None:
        if event == "return":
            announced.set()
            assert computed.wait(10), "the pinned read never computed its board"
        return before_returned

    def writer_trace(frame: FrameType, event: str, arg: Any) -> Trace | None:
        # `_before` drops the pin (twice: itself, then through `_signal`) and
        # returns; only then does the value land, and the drops after that are
        # the ones held at each line.
        if event != "call":
            return None
        if not announcing and frame.f_code is snapshot._before.__code__:
            announcing.append(frame)
            return before_returned
        if announcing and announced.is_set() and frame.f_code is snapshot._drop_pins.__code__:
            return landed_drop if not _inside(frame, announcing[0]) else None
        return None

    def writer() -> None:
        try:
            with _traced(writer_trace):
                elves.counters.add("+1/+1", 1)
        except BaseException as error:  # re-raised in the reading thread below
            failures.append(error)
        finally:
            announced.set()
            held.set()

    outermost: list[FrameType] = []

    def compute_returned(frame: FrameType, event: str, arg: Any) -> None:
        if event == "return":
            computed.set()
            assert held.wait(10), "the writer never reached its pause"

    def read_returned(frame: FrameType, event: str, arg: Any) -> Trace:
        if event == "return":
            read_done.set()
        return read_returned

    def reader_trace(frame: FrameType, event: str, arg: Any) -> Trace | None:
        if event != "call":
            return None
        if not outermost and frame.f_code is snapshot.cached_board.__code__:
            outermost.append(frame)
            return read_returned
        if (
            outermost
            and frame.f_back is outermost[0]
            and frame.f_code is Game._compute_board.__code__
            and not computed.is_set()
        ):
            return compute_returned
        return None

    with _maybe_commanding(game, commanding), scan_pin(game):
        worker = threading.Thread(target=writer)
        worker.start()
        # The writer has announced its store (the first drop is behind it) and
        # is held until the read below has computed its board from the Elves
        # without the counter.
        assert announced.wait(10), "the writer never announced its store"
        try:
            with _traced(reader_trace):
                _power(game, elves)
        finally:
            computed.set()
            read_done.set()
            worker.join()
        if failures:
            raise failures[0]
        if not paused:
            return False
        assert _power(game, elves) == 3, pause_at
    return True


@COMMANDING
def test_a_pin_filled_while_another_thread_is_dropping_it_is_never_kept(commanding):
    """Another thread puts a +1/+1 counter on the Elves, an announced in-place
    edit whose value lands between two drops. The edit is announced (the
    first drop), then the pinned read computes its board from the Elves
    without the counter, then the edit lands and the writer is held at every
    line boundary of the drop that follows it while the read keeps or
    discards the board it computed. Once both are done, the next read sees
    the counter. A field store would not do here: it drops the pin again
    after that, which hides a board kept by mistake."""
    pause_at = 0
    while _fill_during_a_drop_at_line(pause_at, commanding):
        pause_at += 1

    assert pause_at > 2


def test_a_pin_opened_while_another_thread_runs_a_command_is_lifted_by_its_own_command():
    """Another thread's command is running when the pin opens, and ends while
    it is open. A command started inside the pin afterwards still lifts it for
    its whole extent: its reads are uncached, so taking the Anthem off the
    battlefield in place - an edit only the command's end announces - is seen
    by the read after it."""
    game, anthem, elves = _anthem_board()
    started = threading.Event()
    finish = threading.Event()

    def run_a_command() -> None:
        with game._id_allocator_scope():
            started.set()
            assert finish.wait(10), "the pinned thread never let the command end"

    worker = threading.Thread(target=run_a_command)
    worker.start()
    try:
        assert started.wait(10), "the other thread's command never started"
        with scan_pin(game):
            assert _power(game, elves) == 2
            finish.set()
            worker.join()
            with game._id_allocator_scope():
                before = board_computations()
                assert _power(game, elves) == 2
                game.battlefield.remove(anthem)
                assert _power(game, elves) == 1
                assert board_computations() - before == 2
    finally:
        finish.set()
        worker.join()
