"""The one place every object id in this engine is minted.

`new_id()` replaces every bare `uuid4()` call used as a `CardState`,
`ContinuousEffect`, `DelayedTrigger`, `AbilityOnStack`, `CastingRestriction`, or
`Card` id. By default it behaves exactly like `uuid4()` - existing behaviour is
unchanged for any caller, script, or test that never installs an allocator.

Every `Game` method that can mint one - `advance`, `pass_priority`,
`resolve_top`, `play_land`, `activate_ability`, `declare_attackers`,
`declare_blockers`, the pregame moves, `put_on_stack`, `untap_step`,
`destroy`, `check_state_based_actions`, `retain_priority`, and `Casting`'s
own construction, `cast()` and `cancel()`, plus `MarkedExile`'s `take()` and
`cancel()` and `CostPayment`'s `pay()` and `tap_for_mana()` - installs a
deterministic allocator for the span of that one call, through
`Game._id_allocator_scope`: `uuid5` of the game's own
`game_uid` and its `objects_created` counter, the same convention
`Game.shuffles_performed` and `Game.coin_flips_performed` already use for their
own randomness (see `models/game.py`). That is what makes a game replayed from
one decoded snapshot - the same sequence of calls, twice - mint the same ids in
the same order both times, so the two resulting games dump byte-identically.

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
