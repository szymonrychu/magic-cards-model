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
whenever the engine is told the game is changing:

- **Any field assignment on any engine model.** Every pydantic model in this
  package is built on `EngineModel` (or mixes in `AnnouncesMutation`), whose
  `__setattr__`/`__delattr__` announce the change before it lands - `tapped`,
  `zone`, a controller, a clock tick. `tests/test_models_announce_mutation.py`
  refuses a model that opts out. Private attributes (a leading underscore:
  `_board_source`, `_asking_the_board`) are bookkeeping, not game state, and do
  not announce.
- **Any mutating `Game` command.** Every such method runs under
  `Game._id_allocator_scope`, which suspends the snapshot for its whole extent:
  the command's own reads are uncached, whatever order it edits lists and
  assigns fields in, and nothing it computed half-way through survives it.
- **Counters and mana pools** edited in place through their own methods
  (`Counters.add`, `ManaPool.add` and the rest) announce explicitly.

Anything else - a zone list or dict edited in place by a caller outside any
command, or a caller writing into a board it was handed - is not announced,
and cannot be seen at the moment it happens. It is caught instead: when a
board is cached, a serialised fingerprint of the game and of the board is
taken, and it is compared again at the next announced change and when the
scope ends. A mismatch raises `BoardSnapshotStale` and drops the board, so a
stale board is never silently carried past either point. A scope is for
reading; an unannounced edit inside one is a bug in the caller, and it is loud.

Nested scopes on the same game share one board and the outermost one ends it.
`uncached_boards()` switches caching off entirely for its extent, which is
what equivalence checks compare against. `board_computations()` counts real
board computations, for tests and profiling.

The state lives in a `ContextVar`, so threads and async tasks each see only
the scopes they opened. A change announced from another context cannot check
this context's fingerprints, but it still moves a process-wide epoch that
every cached board is compared with before it is served.
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


@dataclass
class _Snapshot:
    game: Any
    suspended: int = 0
    board: Any = None
    epoch: int = -1
    game_fingerprint: bytes = b""
    board_fingerprint: bytes = b""


_snapshots: ContextVar[dict[int, _Snapshot] | None] = ContextVar(
    "magic_cards_model_board_snapshots", default=None
)
_uncached: ContextVar[bool] = ContextVar("magic_cards_model_uncached_boards", default=False)

_lock = threading.Lock()
#: How many snapshot scopes are open in any context. Zero is the fast path
#: every field assignment in the engine takes.
_live = 0
#: Moves on every announced change while any scope is open, in any context.
_epoch = 0
_computations = 0


def board_computations() -> int:
    """How many times a layered board has actually been computed so far."""
    return _computations


def _fingerprint(model: BaseModel) -> bytes:
    return type(model).__pydantic_serializer__.to_json(model)


def _verify_and_drop(snapshot: _Snapshot) -> None:
    board = snapshot.board
    if board is None:
        return
    snapshot.board = None
    if _fingerprint(snapshot.game) != snapshot.game_fingerprint:
        raise BoardSnapshotStale(
            "the game changed inside a board snapshot without announcing it (an in-place "
            "edit outside any engine command), so the cached board may have been stale"
        )
    if _fingerprint(board) != snapshot.board_fingerprint:
        raise BoardSnapshotStale(
            "a cached board was written into inside a board snapshot; boards are shared "
            "there and must be treated as read-only"
        )


def announce_mutation() -> None:
    """The game is about to change: drop every cached board this context holds.

    Called by every engine model's field assignment, by `Counters` and
    `ManaPool` before an in-place edit, and on entry to a mutating command.
    Before a board is dropped its fingerprints are checked, which is where an
    earlier unannounced edit is caught.
    """
    global _epoch
    if not _live:
        return
    with _lock:
        _epoch += 1
    held = _snapshots.get()
    if held:
        for snapshot in held.values():
            _verify_and_drop(snapshot)


class AnnouncesMutation:
    """Mixin for a pydantic model: every public field assignment announces itself."""

    __slots__ = ()

    def __setattr__(self, name: str, value: Any) -> None:
        if _live and not name.startswith("_"):
            announce_mutation()
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if _live and not name.startswith("_"):
            announce_mutation()
        super().__delattr__(name)


class EngineModel(AnnouncesMutation, BaseModel):
    """The base of every pydantic model in this package - see `AnnouncesMutation`."""


def _snapshot_for(game: Any) -> _Snapshot | None:
    held = _snapshots.get()
    return None if held is None else held.get(id(game))


@contextmanager
def board_snapshot(game: Any) -> Iterator[None]:
    """Compute `game`'s layered board at most once for the extent of the block,
    for as long as nothing changes it - see this module's docstring."""
    global _live
    if _snapshot_for(game) is not None:
        yield  # nested: the outer scope owns the board and ends it
        return

    snapshot = _Snapshot(game=game)
    token = _snapshots.set({**(_snapshots.get() or {}), id(game): snapshot})
    with _lock:
        _live += 1
    raised = True
    try:
        yield
        raised = False
    finally:
        try:
            if raised:
                snapshot.board = None
            else:
                _verify_and_drop(snapshot)
        finally:
            with _lock:
                _live -= 1
            _snapshots.reset(token)


@contextmanager
def suspended(game: Any) -> Iterator[None]:
    """A mutating command is running on `game`: no board is cached until it ends."""
    snapshot = _snapshot_for(game)
    if snapshot is None:
        yield
        return
    announce_mutation()
    snapshot.suspended += 1
    try:
        yield
    finally:
        snapshot.suspended -= 1
        snapshot.board = None


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
    otherwise `compute()` - kept for reuse only inside a live, unsuspended scope."""
    global _computations
    snapshot = _snapshot_for(game)
    if snapshot is None or snapshot.suspended or _uncached.get():
        _computations += 1
        return compute()
    if snapshot.board is not None and snapshot.epoch == _epoch:
        return snapshot.board
    snapshot.board = None
    _computations += 1
    board = compute()
    # Computing the board stamps new permanents and reconciles granted ability
    # text, both announced; the fingerprints and epoch are taken after that.
    snapshot.game_fingerprint = _fingerprint(game)
    snapshot.board_fingerprint = _fingerprint(board)
    snapshot.epoch = _epoch
    snapshot.board = board
    return board
