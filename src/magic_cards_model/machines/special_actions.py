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

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this module.
"""

from typing import TYPE_CHECKING

from ..models.card_state import CardState
from .cost import could_pay_mana_cost
from .keywords import turn_face_up_cost

if TYPE_CHECKING:  # pragma: no cover - import cycle: game.py builds on this module
    from ..models.game import Game

__all__ = ["why_cannot_turn_face_up_as"]


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
