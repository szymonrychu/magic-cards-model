"""The one place every object id in this engine is minted.

`new_id()` replaces every bare `uuid4()` call used as a `CardState`,
`ContinuousEffect`, `DelayedTrigger`, `AbilityOnStack`, `CastingRestriction`, or
`Card` id. By default it behaves exactly like `uuid4()` - existing behaviour is
unchanged for any caller, script, or test that never installs an allocator.

Any method that can mint an id kept in the game opens `Game._id_allocator_scope`
for the span of that one call: `uuid5` of the game's own `game_uid` and its
`objects_created` counter, the same convention `Game.shuffles_performed` and
`Game.coin_flips_performed` already use for their own randomness (see
`models/game.py`). That is what makes a game replayed from one decoded
snapshot - the same sequence of calls, twice - mint the same ids in the same
order both times, so the two resulting games dump byte-identically.

The rule for which methods need this is about what the id is *for*, not what
the method is named: a method opens the scope if it can create a `CardState`,
`ContinuousEffect`, `DelayedTrigger`, `AbilityOnStack`, `CastingRestriction`,
or `Card` id that then gets stored in the game - on a zone, the stack, an
effect list, anywhere a later dump/decode/replay has to see it again. A query
path that only reads the game and returns an answer - `machines/legal_actions.py`
enumerating what a player may do, a `why_not`/`why_cannot_*` refusal check, a
board computation - mints nothing persisted and must not open the scope: doing
so would burn a slot in the `objects_created` sequence for an id nobody keeps,
which desyncs every id minted after it the next time the same call happens to
run (or not run) during replay.

This list goes stale the moment a new call site is added, so do not maintain
one here. Find every current site with:

```sh
grep -rn "with .*_id_allocator_scope()" src/
```

That grep counts the sites that actually open a scope, which is what the
snapshot below reports; a bare `grep -rn "_id_allocator_scope" src/` returns
more, because it also matches this module's own prose, the definition in
`models/game.py`, and the docstrings that reference it. Finding a call to
`new_id()` that is *not* under one of those sites, for something that ends up
stored in the game, is the shape of the bug this mechanism exists to prevent.

Measured 2026-09-07: 69 call sites open the scope - 51 `Game` methods in
`models/game.py`, 7 in `machines/casting.py`, 7 in `machines/keywords.py`,
2 in `models/token.py`, and 2 in `machines/cost.py`. Re-run the grep above
rather than trusting these numbers; they are a snapshot, not a contract.

A `ContextVar` rather than a module-level global: the allocator lives per
context (thread or asyncio task), so two games served concurrently out of one
process never see, or clobber, each other's counter.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar, Token
from uuid import UUID, uuid4

_allocator: ContextVar[Callable[[], UUID] | None] = ContextVar(
    "magic_cards_model_id_allocator", default=None
)


def new_id() -> UUID:
    """Mint one object id.

    Uses whatever allocator `install_id_allocator` last set in this context;
    falls back to plain `uuid4()` when none was installed, which is every
    caller that is not `Game` itself.
    """
    allocator = _allocator.get()
    return uuid4() if allocator is None else allocator()


def install_id_allocator(allocator: Callable[[], UUID]) -> Token:
    """Install `allocator` as the id source for `new_id()` in this context.

    Returns the `Token` `reset_id_allocator` needs to restore whatever
    allocator (or none) was installed before - `ContextVar.set`'s own contract.
    """
    return _allocator.set(allocator)


def reset_id_allocator(token: Token) -> None:
    """Undo one `install_id_allocator` call, restoring the prior allocator."""
    _allocator.reset(token)
