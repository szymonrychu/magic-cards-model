"""Scoped reuse of the layered board, and the mutation signal that keeps it true.

`Game.computed_board` applies every continuous effect to the whole battlefield
and is recomputed on every call, because the board has to follow the game the
instant anything changes. Read-only work - `machines.legal_actions`, or a
caller serialising a game's state - asks for that board once per permanent and
per ability, which made its cost grow with the square of the battlefield.

`board_snapshot(game)` (also `Game.board_snapshot()`) is the explicit scope in
which the board is computed once and then reused. Outside every scope nothing
is cached and behaviour is exactly what it was.

## The contract

Inside a scope, the cached board is dropped - and the next read recomputes -
whenever the engine is told *that game* is changing:

- **Any field assignment on a model that belongs to the game.** Every pydantic
  model in this package is built on `EngineModel` (or mixes in
  `AnnouncesMutation`), whose `__setattr__`/`__delattr__` announce the change -
  `tapped`, `zone`, a controller, a clock tick.
  `tests/test_models_announce_mutation.py` refuses a model that opts out.
  Private attributes (a leading underscore: `_board_source`,
  `_asking_the_board`) are bookkeeping, not game state, and do not announce.
- **Any mutating `Game` command.** Every such method runs under
  `Game._id_allocator_scope`, which enters `command(game)`: the command's own
  reads are uncached, whatever order it edits lists and assigns fields in, and
  its end invalidates every scope on that game in every thread and task -
  including edits made in place that nothing else announced.
- **Counters and mana pools** edited in place through their own methods
  (`Counters.add`, `ManaPool.add` and the rest) announce explicitly, with
  `announce_mutation(model)` before the edit and `mutation_landed(model)` once
  it is in place.

**Per game.** A change invalidates only the scopes on the game the changed
model belongs to. Which game that is comes from the game's model graph: the
ids of every model reachable from it, walked lazily the first time a change
has to be placed and kept until something is attached to or detached from the
game (a model-valued assignment, or a command ending). A model reachable from
no open scope's game - another game's permanent, a model a read path is
filling in - invalidates nothing, and takes no lock.

**The signal lands with the value.** Each game with an open scope has an epoch.
A field store moves it both before and after the value is written, and a
command moves it when it ends, so a board computed from the old value - by any
thread, at any moment - carries an epoch that is already gone once the new
value is in place. A board is kept only if nothing but the computing context's
own work moved the epoch while it was computed, and never while a command is
running on the game anywhere.

**Closed scopes never serve.** A scope marks its state closed when it ends, so
a context copied inside it (`asyncio.create_task`, `copy_context()`) neither
reads from nor caches into it afterwards; and each scope removes only its own
entry when it ends, so scopes on different games may end in any order.

Anything else - a zone list or dict edited in place by a caller outside any
command, or a caller writing into a board it was handed - is not announced,
and cannot be seen at the moment it happens. It is caught instead: when a
board is cached, a serialised fingerprint of the game and of the board is
taken, and it is compared again at the next change this context announces on
that game and when the scope ends. A mismatch raises `BoardSnapshotStale` and
drops the board, unless an announced change or a running command explains the
difference. A scope is for reading; an unannounced edit inside one is a bug in
the caller, and it is loud. Fingerprints are taken once per cached board and
checked only when it is dropped - never per read.

**Scan pins.** `scan_pin(game)` is for the engine's own read-only scans that
run inside a command, where no scope caches: the board is computed once for the
scan. It is dropped by anything that bears on the board - a field store or an
announced in-place edit on a model of that game, from any thread, whether or
not a command is running - and lifted for the extent of a command started
inside it. It serves only the thread that opened it, and never after its
block ends.

Nested scopes on the same game share one board and the outermost one ends it.
`uncached_boards()` switches caching off entirely for its extent, which is
what equivalence checks compare against. `board_computations()` counts real
board computations, for tests and profiling.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


class BoardSnapshotStale(RuntimeError):
    """The game or a cached board changed inside a board snapshot without the
    engine being told, so the cached board could no longer be trusted."""


class _Tracked:
    """Process-wide state of one game while any scope on it is open anywhere."""

    __slots__ = ("epoch", "game", "lock", "members", "scopes", "structure")

    def __init__(self, game: Any) -> None:
        self.game = game
        self.scopes = 0
        #: Moves on every announced change to this game and at every command's end.
        self.epoch = 0
        #: Moves when a model may have been attached to or detached from the game.
        self.structure = 0
        #: `(structure, ids of every model reachable from the game)`, or None.
        self.members: tuple[int, frozenset[int]] | None = None
        self.lock = threading.Lock()


@dataclass(frozen=True, slots=True)
class _Cached:
    board: Any
    epoch: int
    game_fingerprint: bytes
    board_fingerprint: bytes


@dataclass(eq=False, slots=True)
class _Snapshot:
    """One scope's hold on a game's board, in the context that opened it."""

    tracked: _Tracked
    cached: _Cached | None = None
    closed: bool = False


@dataclass(eq=False, slots=True)
class _Fill:
    """A board being computed for a snapshot: how many epoch moves were this
    context's own doing (a board computation stamps permanents)."""

    tracked: _Tracked
    outer: _Fill | None
    bumps: int = 0


_snapshots: ContextVar[dict[int, _Snapshot] | None] = ContextVar(
    "magic_cards_model_board_snapshots", default=None
)
_commanding: ContextVar[frozenset[int]] = ContextVar(
    "magic_cards_model_commanding", default=frozenset()
)
_filling: ContextVar[_Fill | None] = ContextVar("magic_cards_model_filling", default=None)
_uncached: ContextVar[bool] = ContextVar("magic_cards_model_uncached_boards", default=False)

#: Guards `_tracked`, `_live` and `_commands`: scope and command boundaries
#: only, never a field assignment.
_lock = threading.Lock()
#: Every game with an open scope in any context, by `id`.
_tracked: dict[int, _Tracked] = {}
#: How many snapshot scopes are open in any context. Zero is the fast path
#: every field assignment in the engine takes.
_live = 0
#: How many commands are running on each game, in any context, by `id`.
_commands: dict[int, int] = {}
_computations = 0


@dataclass(eq=False, slots=True)
class _Pin:
    """One `scan_pin`: its own membership record of the game, the thread it
    serves, and the board it holds while nothing has dropped it."""

    tracked: _Tracked
    thread: int
    board: Any = None
    drops: int = 0
    lifted: int = 0
    closed: bool = False


_pins: ContextVar[dict[int, _Pin] | None] = ContextVar("magic_cards_model_scan_pins", default=None)
_pin_filling: ContextVar[_Pin | None] = ContextVar("magic_cards_model_pin_filling", default=None)
#: Every open pin in any context, so a change from any thread reaches it.
_open_pins: list[_Pin] = []


def _drop_pins(model: object | None, *, structural: bool, lift: int = 0) -> None:
    """Drop every open pin on a game `model` belongs to - commands or not."""
    filling = _pin_filling.get()
    for pin in tuple(_open_pins):
        if pin is not filling and (lift or _holds(pin.tracked, model)):
            if lift and pin.tracked.game is not model:
                continue
            pin.lifted += lift
            pin.board = None
            pin.drops += 1
            if structural:
                pin.tracked.structure += 1


_ATTACHES = (BaseModel, list, tuple, dict, set, frozenset)


def board_computations() -> int:
    """How many times a layered board has actually been computed so far."""
    return _computations


def _fingerprint(model: BaseModel) -> bytes:
    return type(model).__pydantic_serializer__.to_json(model)


def _reachable(root: BaseModel) -> frozenset[int]:
    """The ids of every model reachable from `root`, private attributes included."""
    seen: set[int] = set()
    stack: list[Any] = [root]
    push, pop = stack.extend, stack.pop
    while stack:
        item = pop()
        if isinstance(item, BaseModel):
            key = id(item)
            if key in seen:
                continue
            seen.add(key)
            push(item.__dict__.values())
            private = item.__pydantic_private__
            if private:
                push(private.values())
        elif isinstance(item, list | tuple | set | frozenset):
            push(item)
        elif isinstance(item, dict):
            push(item.values())
    return frozenset(seen)


def _holds(tracked: _Tracked, model: object | None) -> bool:
    """Whether `model` belongs to the tracked game (None: assume it does)."""
    if model is None or model is tracked.game:
        return True
    structure = tracked.structure
    members = tracked.members
    if members is None or members[0] != structure:
        members = (structure, _reachable(tracked.game))
        if tracked.structure == structure:  # nothing attached while walking
            tracked.members = members
    return id(model) in members[1]


def _bump(tracked: _Tracked, *, structural: bool) -> None:
    with tracked.lock:
        tracked.epoch += 1
        if structural:
            tracked.structure += 1
        fill = _filling.get()
        while fill is not None:
            if fill.tracked is tracked:
                fill.bumps += 1
            fill = fill.outer


def _signal(model: object | None, *, structural: bool) -> None:
    """Move the epoch of every open game `model` belongs to, in every context.

    A game this context is running a command on is skipped: the command's end
    moves it, after every edit the command makes."""
    _drop_pins(model, structural=structural)
    commanding = _commanding.get()
    for key, tracked in tuple(_tracked.items()):
        if key not in commanding and _holds(tracked, model):
            _bump(tracked, structural=structural)


def _verify_and_drop(snapshot: _Snapshot) -> None:
    cached = snapshot.cached
    if cached is None:
        return
    snapshot.cached = None
    if _fingerprint(cached.board) != cached.board_fingerprint:
        raise BoardSnapshotStale(
            "a cached board was written into inside a board snapshot; boards are shared "
            "there and must be treated as read-only"
        )
    tracked = snapshot.tracked
    if cached.epoch != tracked.epoch or id(tracked.game) in _commands:
        return  # an announced change or a running command explains any difference
    if _fingerprint(tracked.game) != cached.game_fingerprint:
        raise BoardSnapshotStale(
            "the game changed inside a board snapshot without announcing it (an in-place "
            "edit outside any engine command), so the cached board may have been stale"
        )


def _before(model: object | None) -> None:
    """A change to `model` is about to land: check and drop this context's
    boards on the games it belongs to, then signal every context."""
    _drop_pins(model, structural=False)
    held = _snapshots.get()
    if held:
        for snapshot in tuple(held.values()):
            if (
                snapshot.cached is not None
                and not snapshot.closed
                and _holds(snapshot.tracked, model)
            ):
                _verify_and_drop(snapshot)
    _signal(model, structural=False)


def announce_mutation(model: object | None = None) -> None:
    """`model` is about to be edited in place: drop the boards of the games it
    belongs to (None: of every game), checking their fingerprints first, which
    is where an earlier unannounced edit is caught.

    Pair it with `mutation_landed(model)` once the edit is in place - that is
    the signal a board computed meanwhile, by any thread, cannot survive.
    """
    if _live:
        _before(model)


def mutation_landed(model: object | None = None, *, structural: bool = True) -> None:
    """The in-place edit `announce_mutation(model)` announced is now in place.

    `structural=False` promises the edit attached or detached no model (a
    count, a colour total), which keeps the game's model graph warm.
    """
    if _live:
        _signal(model, structural=structural)


class AnnouncesMutation:
    """Mixin for a pydantic model: every public field assignment announces itself,
    before the value is stored and again once it is."""

    __slots__ = ()

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
            return
        if _live:
            _before(self)
        super().__setattr__(name, value)
        if _live:
            _signal(self, structural=isinstance(value, _ATTACHES))

    def __delattr__(self, name: str) -> None:
        if name.startswith("_"):
            super().__delattr__(name)
            return
        if _live:
            _before(self)
        super().__delattr__(name)
        if _live:
            _signal(self, structural=True)


class EngineModel(AnnouncesMutation, BaseModel):
    """The base of every pydantic model in this package - see `AnnouncesMutation`."""


def _open_snapshot(key: int) -> _Snapshot | None:
    held = _snapshots.get()
    snapshot = None if held is None else held.get(key)
    return None if snapshot is None or snapshot.closed else snapshot


@contextmanager
def board_snapshot(game: Any) -> Iterator[None]:
    """Compute `game`'s layered board at most once for the extent of the block,
    for as long as nothing changes it - see this module's docstring."""
    global _live
    key = id(game)
    if _open_snapshot(key) is not None:
        yield  # nested: the outer scope owns the board and ends it
        return

    with _lock:
        tracked = _tracked.get(key)
        if tracked is None:
            tracked = _tracked[key] = _Tracked(game)
        tracked.scopes += 1
        _live += 1
    snapshot = _Snapshot(tracked)
    _snapshots.set({**(_snapshots.get() or {}), key: snapshot})
    raised = True
    try:
        yield
        raised = False
    finally:
        try:
            if raised:
                snapshot.cached = None
            else:
                _verify_and_drop(snapshot)
        finally:
            snapshot.closed = True
            snapshot.cached = None
            with _lock:
                tracked.scopes -= 1
                _live -= 1
                if not tracked.scopes:
                    del _tracked[key]
            # Remove only this scope's own entry: another scope in this context
            # may have opened after it and still be open.
            held = _snapshots.get()
            if held is not None and held.get(key) is snapshot:
                rest = {other: kept for other, kept in held.items() if other != key}
                _snapshots.set(rest or None)


@contextmanager
def scan_pin(game: Any) -> Iterator[None]:
    """Compute `game`'s board once for a read-only scan, commands or not - see
    this module's docstring. Nested pins on the same game share the outer one."""
    global _live
    key = id(game)
    held = _pins.get()
    if _serving_pin(key) is not None:
        yield
        return
    pin = _Pin(_Tracked(game), threading.get_ident())
    replaced = None if held is None else held.get(key)  # a lifted outer pin comes back
    with _lock:
        _open_pins.append(pin)
        _live += 1
    _pins.set({**(held or {}), key: pin})
    try:
        yield
    finally:
        pin.closed = True
        pin.board = None
        with _lock:
            _open_pins.remove(pin)
            _live -= 1
        held = _pins.get()
        if held is not None and held.get(key) is pin:
            rest = {other: kept for other, kept in held.items() if other != key}
            if replaced is not None:
                rest[key] = replaced
            _pins.set(rest or None)


def _serving_pin(key: int) -> _Pin | None:
    held = _pins.get()
    pin = None if held is None else held.get(key)
    if pin is None or pin.closed or pin.lifted or pin.thread != threading.get_ident():
        return None
    return pin


@contextmanager
def command(game: Any) -> Iterator[None]:
    """A mutating command is running on `game`: `_command`, with every scan pin
    on `game` lifted for its extent and dropped once it ends."""
    _drop_pins(game, structural=True, lift=1)
    try:
        with _command(game):
            yield
    finally:
        _drop_pins(game, structural=True, lift=-1)


@contextmanager
def _command(game: Any) -> Iterator[None]:
    """A mutating command is running on `game`.

    Nothing is cached for `game` anywhere while it runs, and its end moves the
    epoch of every open scope on `game`, whichever thread or task holds it -
    after every edit the command made, in place or not."""
    key = id(game)
    commanding = _commanding.get()
    if key in commanding:
        yield  # a command inside a command: the outermost one signals
        return
    if _live:
        _before(game)
    with _lock:
        _commands[key] = _commands.get(key, 0) + 1
    token = _commanding.set(commanding | {key})
    try:
        yield
    finally:
        _commanding.reset(token)
        tracked = _tracked.get(key)
        if tracked is not None:
            _bump(tracked, structural=True)
        with _lock:
            running = _commands[key] - 1
            if running:
                _commands[key] = running
            else:
                del _commands[key]


@contextmanager
def uncached_boards() -> Iterator[None]:
    """Compute every board afresh for the extent of the block, scopes or not."""
    token = _uncached.set(True)
    try:
        yield
    finally:
        _uncached.reset(token)


def cached_board[B: BaseModel](game: Any, compute: Callable[[], B]) -> B:
    """`game`'s layered board: the snapshot's cached one when it is still good,
    otherwise `compute()` - kept for reuse only inside an open scope, with no
    command running on `game` and nothing else changing it meanwhile."""
    global _computations
    key = id(game)
    pin = None if _uncached.get() else _serving_pin(key)
    if pin is not None:
        if pin.board is None:
            _computations += 1
            drops, token = pin.drops, _pin_filling.set(pin)
            try:
                board = compute()
            finally:
                _pin_filling.reset(token)
            if pin.drops != drops or pin.closed or pin.lifted:
                return board
            pin.board = board
        return pin.board
    snapshot = _open_snapshot(key)
    if snapshot is None or _uncached.get() or key in _commanding.get():
        _computations += 1
        return compute()
    tracked = snapshot.tracked
    cached = snapshot.cached
    if cached is not None and cached.epoch == tracked.epoch:
        return cached.board
    snapshot.cached = None
    _computations += 1
    start = tracked.epoch
    fill = _Fill(tracked, _filling.get())
    token = _filling.set(fill)
    try:
        # Computing the board stamps new permanents and reconciles granted
        # ability text, both announced; `fill` counts those moves as its own.
        board = compute()
    finally:
        _filling.reset(token)
    if key in _commands:
        return board
    game_fingerprint = _fingerprint(game)
    board_fingerprint = _fingerprint(board)
    with tracked.lock:
        if snapshot.closed or key in _commands or tracked.epoch != start + fill.bumps:
            return board  # something else changed the game while it was computed
        snapshot.cached = _Cached(board, tracked.epoch, game_fingerprint, board_fingerprint)
    return board
