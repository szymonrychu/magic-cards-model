"""Read-only "what if" questions about a land, answered by the engine itself.

Two entry points, both side-effect free, for a seat that wants to plan its land
sequencing without a parallel rules model of its own:

- `predict_enters(game, player, land)` - how `land`, in `player`'s hand or
  library, would enter the battlefield right now: `untapped`, `tapped`, or
  `untapped_if_paid` (an optional cost such as a shockland's "you may pay 2
  life", CR 614.1c / 614.12a, decides it).
- `payability(game, player, card, *, assuming_land=None)` - every mana-paid
  option `legal_actions` enumerates for `card` (casting it, and a hand-activated
  ability such as cycling, typecycling or channel), each with its own
  `Affordability`, and whether any of them is payable - now, or with
  `assuming_land` on the battlefield.

**Both run the real engine on a decoded copy.** The copy is
`Game.model_validate(game.model_dump(mode="json"))`, the same round trip every
scenario test proves, so nothing done to it reaches `game`. The land enters the
copy through `Game.put_onto_battlefield`, which is `Game.enter_the_battlefield`:
CR 614.12's replacement effects - the land's own and every other permanent's -
are applied exactly as a real play applies them, and the mana solver that
`legal_actions` reports affordability with (`cost.plan_mana_payment`) is the one
`auto_tap` pays with. There is no second reading of enters-tapped text here and
no second payment search, so a prediction and the real play cannot disagree.
The one exception is deliberate: an enters-tapped line the engine does not read
(`replacement.unread_self_enters_tapped_lines`) is reported `tapped` with a
notice, failing closed, even though the engine itself currently skips it.

**Optional costs.** The copy is entered twice when needed: once with every
optional payment the seat is asked about taken whenever it is legal (CR 119.4,
CR 608.2d - `default_answer`'s own policy), and once with each one declined. A
land that is untapped only in the first run is `untapped_if_paid`, and the
declined questions' prompts are its `optional_costs`.

**Triggers.** Entering can trigger abilities (CR 603.2): Amulet of Vigor
untapping the land, a landfall ability adding mana. In a real game they go on
the stack before anyone next gets priority (CR 603.3), so before a sorcery-speed
spell could be cast. The copy puts them on the stack and resolves them through
the engine, one at a time, as long as neither step asks anybody a question.
A trigger that asks one - a color, a target, a surveil - is not answered by a
guess: the copy is rebuilt with that trigger left out, and the answer names it
in a notice. `predict_enters` still reports how the land *enters*, because the
trigger resolves after it is on the battlefield, and adds a notice when a
resolved trigger would untap or otherwise change it.

**What "assuming" does not check.** It does not ask whether the land could be
played this turn (CR 305.2's land drop) or how it would get from the library to
the battlefield (a fetch land's search) - the caller composes those. A land in
the library is put onto the battlefield front face up (CR 712.14); one in hand
that is a modal double-faced card with a land back is played with that face up
(CR 712.12), mirroring `Game.play_land`.
"""

from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING, Any, NamedTuple
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.action import Action, ActionKind, Affordability
from ..models.card_state import CardState
from ..models.zone import Zone
from .decisions import Decision, DecisionKind, DecisionScript, ScriptedAnswer
from .legal_actions import legal_actions
from .replacement import unread_self_enters_tapped_lines

if TYPE_CHECKING:
    from ..models.game import Game


class EntersState(StrEnum):
    """How a land would enter the battlefield right now."""

    UNTAPPED = "untapped"
    TAPPED = "tapped"
    #: Untapped only if an optional cost is paid as it enters (CR 614.12a) -
    #: `EntersPrediction.optional_costs` names it.
    UNTAPPED_IF_PAID = "untapped_if_paid"


class EntersPrediction(BaseModel):
    """`predict_enters`'s answer. Ids and strings only, never a live object."""

    model_config = ConfigDict(frozen=True)

    card_id: UUID
    name: str
    zone: Zone
    state: EntersState
    #: The prompts of the optional payments whose refusal taps it ("pay 2
    #: life"), empty unless `state` is `UNTAPPED_IF_PAID`.
    optional_costs: tuple[str, ...] = ()
    #: Why the answer failed closed (an unread enters-tapped line), and what a
    #: trigger resolving after it enters would change about it (CR 603.3).
    notices: tuple[str, ...] = ()


class Payability(BaseModel):
    """`payability`'s answer."""

    model_config = ConfigDict(frozen=True)

    card_id: UUID
    #: Whether any of `options` is `Affordability.YES`.
    payable: bool
    #: Every action `legal_actions` enumerates for this card other than playing
    #: it as a land - a cast per cast option, and each hand-activated ability -
    #: each carrying its own `affordable`, `unaffordable_reason` and `pays_with`.
    #: A cast that is not legal right now (CR 117.1a timing, CR 611.1
    #: prohibitions) is absent, exactly as `legal_actions` omits it.
    options: tuple[Action, ...]
    #: How `assuming_land` was taken to enter, when one was given.
    assumed_land: EntersPrediction | None = None
    #: Each triggered ability the answer left unresolved because resolving it
    #: needed somebody's choice, named rather than guessed.
    notices: tuple[str, ...] = ()


#: The yes-or-no payments an entering permanent can offer (CR 608.2d). Declining
#: every one of them is always legal, which is what makes the second run safe.
_OPTIONAL_PAYMENTS = (
    DecisionKind.MAY,
    DecisionKind.PAY_LIFE,
    DecisionKind.PAY_ENERGY,
    DecisionKind.PAY_MANA,
)

#: Asked while simultaneous triggers are put on the stack (CR 603.3b). The
#: copy resolves only triggers that need no choice, and what each of those
#: does does not depend on the order it resolves in, so this is not a guess.
_NOT_A_TRIGGER_CHOICE = frozenset({DecisionKind.ORDER_TRIGGERS})

#: Bounds on settling triggers: rebuilds of the copy (one per trigger found to
#: need a choice), and resolutions per rebuild. A board past either bound is
#: answered without its triggers, with a notice.
_MAX_SETTLE_PASSES = 16
_MAX_RESOLUTIONS = 64

#: What `_enter_on_a_copy` returns: the copy, the entered land (or None for the
#: board as it is), and every question asked while it entered.
_Built = tuple["Game", CardState | None, list[Decision]]


class _Settled(NamedTuple):
    board: "Game"
    entered: CardState | None
    #: Questions asked while the land entered, before any trigger resolved.
    asked: list[Decision]
    #: The entered land's (zone, tapped, controller, counters) as it entered.
    entry: tuple[Any, ...] | None
    #: Source names of the triggers that resolved, in order.
    resolved: tuple[str, ...]
    #: One per trigger left unresolved.
    notices: tuple[str, ...]


def _card(game: "Game", card: CardState | UUID) -> CardState:
    card_id = card.id if isinstance(card, CardState) else card
    found = game.find_by_id(card_id)
    if found is None:
        raise ValueError(f"no card with id {card_id} is in this game")
    return found


def _land_to_enter(game: "Game", player: str, land: CardState | UUID) -> CardState:
    found = _card(game, land)
    me = game.player(player)
    if not any(found.id == other.id for other in (*me.hand, *me.library)):
        raise ValueError(f"{found.name} is not in {player}'s hand or library")
    played_as_land_face = found.zone is Zone.HAND and found.card.land_face is not None
    if not found.card.is_land and not played_as_land_face:
        raise ValueError(f"{found.name} is not a land")
    return found


def _decoded_copy(game: "Game") -> "Game":
    copy = type(game).model_validate(game.model_dump(mode="json"))
    # A copy answers every question itself: no caller's scripted answers, no
    # replay tape, and never a pause waiting on a seat.
    copy.decisions = DecisionScript()
    return copy


def _enter_on_a_copy(
    game: "Game", player: str, land_id: UUID, *, decline_optional_payments: bool
) -> _Built:
    copy = _decoded_copy(game)
    if decline_optional_payments:
        for kind in _OPTIONAL_PAYMENTS:
            copy.decisions.add(ScriptedAnswer(kind=kind, value=False, player=player, uses=None))
    entering = copy.find_by_id(land_id)
    assert entering is not None  # decoded from the game `land_id` was found in
    if (
        entering.zone is Zone.HAND
        and not entering.card.is_land
        and entering.card.land_face is not None
    ):
        entering.land_face_played = entering.card.land_face.name  # CR 712.12
    asked_before = len(copy.decisions.asked)
    copy.put_onto_battlefield(entering, player)
    return copy, entering, copy.decisions.asked[asked_before:]


def _unread_notices(game: "Game", player: str, land_id: UUID) -> tuple[str, ...]:
    copy = _decoded_copy(game)
    land = copy.find_by_id(land_id)
    assert land is not None
    if land.zone is Zone.HAND and not land.card.is_land and land.card.land_face is not None:
        land.land_face_played = land.card.land_face.name
    return tuple(
        f'{land.name}: "{line}" is not read by the engine, so it is reported tapped '
        "rather than guessed (CR 614.1d)"
        for line in unread_self_enters_tapped_lines(land)
    )


# --------------------------------------------------------------------------
# Triggers (CR 603.2, 603.3)
# --------------------------------------------------------------------------


def _observed(card: CardState | None) -> tuple[Any, ...] | None:
    if card is None:
        return None
    return (card.zone, card.tapped, card.controller, dict(card.counters))


def _name_of(stack_object: Any) -> str:
    return str(getattr(stack_object, "source_name", None) or getattr(stack_object, "name", "?"))


def _choices(asked: list[Decision]) -> list[Decision]:
    """The questions in `asked` that are somebody's real choice: not trigger
    ordering, and not a question whose only legal answer is no."""
    return [
        decision
        for decision in asked
        if decision.kind not in _NOT_A_TRIGGER_CHOICE and decision.affirmative_is_legal
    ]


def _left_unresolved(name: str, asked: list[Decision]) -> str:
    prompts = "; ".join(dict.fromkeys(decision.prompt for decision in asked))
    return (
        f"{name}'s triggered ability needs a choice ({prompts}), so it is left "
        "unresolved rather than guessed (CR 603.3)"
    )


def _resolve_choice_free(
    board: "Game", skipped: dict[UUID, str]
) -> tuple[UUID, str] | tuple[list[str], bool]:
    """Put `board`'s pending triggers on the stack and resolve them, one at a
    time, leaving out every id in `skipped`.

    Returns `(id, notice)` for the first trigger that asks a real question -
    the board is then half-settled and must be rebuilt - or `(resolved source
    names, finished)`, `finished` False when `_MAX_RESOLUTIONS` ran out.
    Objects already on the stack before this was called are never resolved.
    """
    base = len(board.stack)
    resolved: list[str] = []
    for _ in range(_MAX_RESOLUTIONS):
        board.check_state_based_actions()  # CR 704.3, before triggers go on
        if board.is_over:
            return resolved, True
        waiting = [trigger for trigger in board.pending_triggers if trigger.id not in skipped]
        if waiting:
            first, rest = waiting[0], waiting[1:]
            board.pending_triggers = [first]
            mark = len(board.decisions.asked)
            board.put_triggers_on_stack()
            board.pending_triggers = rest + board.pending_triggers
            asked = _choices(board.decisions.asked[mark:])
            if asked:
                return first.id, _left_unresolved(_name_of(first), asked)
            continue
        board.pending_triggers = []
        if len(board.stack) <= base:
            return resolved, True
        top = board.stack[-1]
        mark = len(board.decisions.asked)
        board.resolve_top()
        asked = _choices(board.decisions.asked[mark:])
        if asked:
            return top.id, _left_unresolved(_name_of(top), asked)
        resolved.append(_name_of(top))
    return resolved, False


def _settle(rebuild: Callable[[], _Built]) -> _Settled:
    """A board built by `rebuild` with every choice-free trigger resolved and
    every other one left out and named. See the module docstring."""
    skipped: dict[UUID, str] = {}
    for _ in range(_MAX_SETTLE_PASSES):
        board, entered, asked = rebuild()
        entry = _observed(entered)
        outcome = _resolve_choice_free(board, skipped)
        if isinstance(outcome[0], UUID):
            blocker, notice = outcome
            skipped[blocker] = str(notice)
            continue
        resolved, finished = outcome
        notices = list(skipped.values())
        if not finished:
            notices.append(
                f"triggered abilities were still resolving after {_MAX_RESOLUTIONS}, so "
                "the answer stops there (CR 603.3)"
            )
        return _Settled(board, entered, asked, entry, tuple(resolved), tuple(notices))
    board, entered, asked = rebuild()
    board.pending_triggers = []
    notices = (
        *skipped.values(),
        f"triggered abilities still needed choices after {_MAX_SETTLE_PASSES} attempts, "
        "so none of them is counted (CR 603.3)",
    )
    return _Settled(board, entered, asked, _observed(entered), (), notices)


def _change_notice(land_name: str, settled: _Settled) -> str | None:
    """What resolving triggers did to the entered land, if anything."""
    if settled.entered is None or settled.entry is None or not settled.resolved:
        return None
    now = _observed(settled.board.find_by_id(settled.entered.id))
    if now == settled.entry:
        return None
    sources = ", ".join(dict.fromkeys(settled.resolved))
    entered_tapped = settled.entry[1]
    if now is not None and now[0] == settled.entry[0] and entered_tapped and not now[1]:
        what = "untap it"
    else:
        what = "change it"
    state = "tapped" if entered_tapped else "untapped"
    return (
        f"{land_name} enters {state}; once it is on the battlefield a triggered "
        f"ability ({sources}) would {what} (CR 603.3)"
    )


# --------------------------------------------------------------------------
# Public entry points
# --------------------------------------------------------------------------


def predict_enters(game: "Game", player: str, land: CardState | UUID) -> EntersPrediction:
    """How `land`, in `player`'s hand or library, would enter the battlefield
    under `player`'s control right now. Mutates nothing. See the module
    docstring.

    Raises `ValueError` for a card that is not a land (an MDFC with a land
    back face counts from the hand, CR 712.12) or not in `player`'s hand or
    library.
    """
    found = _land_to_enter(game, player, land)
    notices = _unread_notices(game, player, found.id)
    base = {"card_id": found.id, "name": found.name, "zone": found.zone}
    if notices:
        return EntersPrediction(**base, state=EntersState.TAPPED, notices=notices)

    paying = _settle(
        lambda: _enter_on_a_copy(game, player, found.id, decline_optional_payments=False)
    )
    change = _change_notice(found.name, paying)
    triggered = (change,) if change is not None else ()
    assert paying.entry is not None
    if paying.entry[1]:
        return EntersPrediction(**base, state=EntersState.TAPPED, notices=triggered)

    _, declining, asked = _enter_on_a_copy(game, player, found.id, decline_optional_payments=True)
    assert declining is not None
    if not declining.tapped:
        return EntersPrediction(**base, state=EntersState.UNTAPPED, notices=triggered)
    costs = tuple(
        decision.prompt
        for decision in asked
        if decision.kind in _OPTIONAL_PAYMENTS and decision.player == player
    )
    return EntersPrediction(
        **base, state=EntersState.UNTAPPED_IF_PAID, optional_costs=costs, notices=triggered
    )


def payability(
    game: "Game",
    player: str,
    card: CardState | UUID,
    *,
    assuming_land: CardState | UUID | None = None,
) -> Payability:
    """Whether `player` could pay for `card` right now, or with
    `assuming_land` (a land in their hand or library) on the battlefield as
    `predict_enters` says it would enter, its optional cost paid when legal and
    its choice-free triggers resolved. Mutates nothing. See the module
    docstring.
    """
    target = _card(game, card)
    assumed: EntersPrediction | None = None
    if assuming_land is None:
        settled = _settle(lambda: (_decoded_copy(game), None, []))
    else:
        land = _land_to_enter(game, player, assuming_land)
        if land.id == target.id:
            raise ValueError(
                f"{land.name} cannot be both the card asked about and the land assumed"
            )
        assumed = predict_enters(game, player, land)
        fail_closed_tapped = assumed.state is EntersState.TAPPED

        def rebuild() -> _Built:
            board, entered, asked = _enter_on_a_copy(
                game, player, land.id, decline_optional_payments=False
            )
            if fail_closed_tapped and entered is not None:
                # Fail closed on an unread line too: the prediction said tapped.
                entered.tapped = True
            return board, entered, asked

        settled = _settle(rebuild)
    options = tuple(
        action
        for action in legal_actions(settled.board, player)
        if action.card_id == target.id and action.kind is not ActionKind.PLAY_LAND
    )
    return Payability(
        card_id=target.id,
        payable=any(option.affordable is Affordability.YES for option in options),
        options=options,
        assumed_land=assumed,
        notices=settled.notices,
    )


__all__ = ["EntersPrediction", "EntersState", "Payability", "payability", "predict_enters"]
