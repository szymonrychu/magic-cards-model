"""Seat-facing checks for a CR 116.2 special action this engine already
executes, but whose existing entry point only asks whether the *object* is
eligible - never who is asking, or whether they can actually pay.

`Game.why_cannot_turn_face_up` (CR 702.37e, CR 702.168d, CR 701.40b) is the
object-level check: is this a face-down permanent at all, does it have a
turn-up cost, is a static ability banning it right now. It says nothing about
*who* may take the action, because until now every caller already knew - a
scenario always calls `begin_turning_face_up` for the permanent's own real
controller. A seat surface cannot assume that: a request naming the wrong
player, or a player who genuinely cannot pay, needs a refusal in the engine's
own words rather than a `ValueError` half-way through `CostPayment.pay`.

`why_cannot_turn_face_up_as` below is that seat-facing wrapper, added rather
than folded into `Game.why_cannot_turn_face_up` itself so every existing call
site - `begin_turning_face_up`, and every scenario test that already calls
`why_cannot_turn_face_up(permanent)` - keeps its exact existing behaviour.
`Game.begin_turning_face_up`/`Game.turn_face_up` are the reused begin/finish
pair (CR 116.1: paying can take more than one priority-free moment); a seat
caller checks this function first, then calls those two unchanged.

A Room's unlock cost (CR 709.5e, CR 116.2m) is the other special action here:
`why_cannot_unlock_door` is its whole legality check (the door, who controls
it, and CR 709.5e's own timing), `why_cannot_unlock_door_as` adds CR 118.3's
"can they actually pay", and `unlock_cost` is what is paid - the locked
half's own printed mana cost, read off whichever half the seat names, never
off a card name. `Game.begin_unlocking_door`/`Game.finish_unlocking_door`
are its begin/finish pair, the second running through `Game.unlock_door` so
CR 709.5h's "When you unlock this door" fires exactly as it does for a cast
half.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this module.
"""

from typing import TYPE_CHECKING, Any

from ..models.card import Layout
from ..models.card_state import CardState
from ..models.zone import Zone
from .cost import TotalCost, could_pay_mana_cost
from .keywords import turn_face_up_cost
from .turn import MAIN_PHASES

if TYPE_CHECKING:  # pragma: no cover - import cycle: game.py builds on this module
    from ..models.game import Game

__all__ = [
    "door_face",
    "locked_doors",
    "unlock_cost",
    "why_cannot_turn_face_up_as",
    "why_cannot_unlock_door",
    "why_cannot_unlock_door_as",
]


def why_cannot_turn_face_up_as(
    game: "Game", username: str, permanent: CardState, *, procedure: str | None = None
) -> str | None:
    """Why `username` cannot turn `permanent` face up right now, or None.

    Checked in the order a seat meets them:

    1. Is this even a face-down permanent with a turn-up cost, and is nothing
       banning it (`Game.why_cannot_turn_face_up` - CR 702.37e, CR 702.168d,
       CR 701.40b, plus a static ban such as Unable to Scream or Karlov
       Watchdog).
    2. Does `username` control it - CR 702.37e/CR 702.168d/CR 701.40b each
       say "a permanent **you** control".
    3. Can `username` actually pay the cost right now (CR 118.3: an unpayable
       special action is not one a seat can be told to just go take).

    `procedure` (`"morph"` or `"manifest"`) asks about one specific one of
    CR 701.40c-d's two procedures for a card that is manifested *and* has
    morph or disguise; `None` keeps asking about whichever the old default
    preference reaches first - see `Game.why_cannot_turn_face_up`'s and
    `turn_face_up_cost`'s own docstrings.
    """
    reason = game.why_cannot_turn_face_up(permanent, procedure=procedure)
    if reason is not None:
        return reason
    controller = game.controller_of(permanent).username
    if username != controller:
        return (
            f"{username} does not control {permanent.card.name}, so only {controller} "
            f"may turn it face up (CR 702.37e, CR 702.168d, CR 701.40b)"
        )
    total = turn_face_up_cost(permanent, username, procedure=procedure)
    # `Game.why_cannot_turn_face_up` already returned None above, which is
    # exactly the condition under which `turn_face_up_cost` returns a real
    # cost rather than None - see both functions' own docstrings.
    assert total is not None
    sources = game.permanents_controlled_by(username)
    if not could_pay_mana_cost(total.mana, sources, game=game, payer=username):
        return (
            f"{username} cannot pay {total.mana} to turn {permanent.card.name} face up "
            f"right now (CR 118.3)"
        )
    return None


# -- a Room's unlock cost (CR 709.5e, CR 116.2m) ------------------------------


def _has_shared_type_line(permanent: CardState) -> bool:
    """CR 709.5: a split card that is a permanent card "with a single shared
    type line" - every half carries the same type line (CR 709.5a), which
    is what gives it locked and unlocked halves at all."""
    faces = permanent.card.card_faces or []
    if permanent.card.layout is not Layout.SPLIT or len(faces) < 2:
        return False
    return len({face.type_line for face in faces}) == 1


def door_face(permanent: CardState, door: str) -> Any:
    """The half (CR 709.5j's "door") of `permanent` named `door`, or None."""
    if not _has_shared_type_line(permanent):
        return None
    return next((face for face in permanent.card.card_faces or [] if face.name == door), None)


def locked_doors(permanent: CardState) -> list[Any]:
    """`permanent`'s locked halves (CR 709.5c: "Otherwise, that half is said
    to be 'locked'"), in printed order - empty for anything that is not a
    permanent with a shared type line on the battlefield."""
    if permanent.zone is not Zone.BATTLEFIELD or not _has_shared_type_line(permanent):
        return []
    return [
        face
        for face in permanent.card.card_faces or []
        if face.name not in permanent.unlocked_doors
    ]


def unlock_cost(permanent: CardState, door: str) -> TotalCost:
    """CR 709.5e: "pay the mana cost of a locked half of that permanent" -
    the half's own printed mana cost, nothing else. Not a spell being cast,
    so CR 601.2f's cost increases and reductions never apply to it."""
    face = door_face(permanent, door)
    if face is None:
        raise ValueError(f"{door!r} is not a door of {permanent.card.name} (CR 709.5j)")
    return TotalCost.of(face.mana_cost or None)


def why_cannot_unlock_door(
    game: "Game", username: str, permanent: CardState, door: str
) -> str | None:
    """Why `username` cannot take CR 709.5e's special action for `door` of
    `permanent` right now, or None - legality only; CR 118.6 keeps whether
    the cost can be paid a separate question (`why_cannot_unlock_door_as`).

    CR 709.5e: "A player who controls a permanent that has one or more
    locked halves may pay the mana cost of a locked half of that permanent
    to give that permanent the appropriate unlocked designation ... A player
    can take this action any time they have priority and the stack is empty
    during a main phase of their turn." Priority itself is not checked, for
    the same reason `Game.why_cannot_bring_companion_to_hand` does not: the
    caller is trusted to hold it.
    """
    name = permanent.card.name
    if permanent.zone is not Zone.BATTLEFIELD or not _has_shared_type_line(permanent):
        return f"{name} is not a permanent with a locked half, so it has no unlock cost (CR 709.5e)"
    if door_face(permanent, door) is None:
        doors = ", ".join(face.name for face in permanent.card.card_faces or [])
        return f"{door} is not a door of {name}; its doors are {doors} (CR 709.5j)"
    if door in permanent.unlocked_doors:
        return f"{door} is already unlocked, so there is no locked half to pay for (CR 709.5e)"
    controller = game.controller_of(permanent).username
    if username != controller:
        return (
            f"{username} does not control {name}; only {controller}, who controls it, "
            f"may pay its unlock cost (CR 709.5e)"
        )
    assert game.turn is not None
    if game.turn.step not in MAIN_PHASES:
        return (
            f"{username} cannot unlock a door outside a main phase of their turn "
            f"(CR 709.5e); the turn is in {game.turn.step.value}"
        )
    if not game.stack_is_empty:
        return f"{username} cannot unlock a door while the stack is not empty (CR 709.5e)"
    if username != game.turn.active_player:
        return (
            f"{username} can unlock a door only during a main phase of their own turn "
            f"(CR 709.5e); it is {game.turn.active_player}'s turn"
        )
    return None


def why_cannot_unlock_door_as(
    game: "Game", username: str, permanent: CardState, door: str
) -> str | None:
    """`why_cannot_unlock_door`, plus whether `username` can actually pay the
    unlock cost right now (CR 118.3) - the seat-facing refusal."""
    reason = why_cannot_unlock_door(game, username, permanent, door)
    if reason is not None:
        return reason
    total = unlock_cost(permanent, door)
    sources = game.permanents_controlled_by(username)
    if not could_pay_mana_cost(total.mana, sources, game=game, payer=username):
        return f"{username} cannot pay {total.mana} to unlock {door} right now (CR 118.3)"
    return None
