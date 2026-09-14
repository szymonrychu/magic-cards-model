"""Read-only "what if" questions about a land, answered by the engine itself.

Three entry points, all side-effect free, for a seat that wants to plan its
land sequencing without a parallel rules model of its own:

- `predict_enters(game, player, land)` - how `land`, in `player`'s hand or
  library, would enter the battlefield right now: `untapped`, `tapped`, or
  `untapped_if_paid` (an optional cost such as a shockland's "you may pay 2
  life", CR 614.1c / 614.12a, decides it).
- `payability(game, player, card, *, assuming_land=None)` - every mana-paid
  option `legal_actions` enumerates for `card` (casting it, and a hand-activated
  ability such as cycling, typecycling or channel), each with its own
  `Affordability`, and whether any of them is payable - now, or with
  `assuming_land` on the battlefield.
- `payability_matrix(game, player, cards, lands)` - both of the above for many
  cards and lands at once, as one batch (see "Batching" below).

**All of them run the real engine on a decoded copy.** The copy is
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

**Optional costs.** When entering the copy offered `player` an optional payment
(CR 119.4, CR 608.2d - taken whenever legal, `default_answer`'s own policy),
the land is entered a second time with every such payment declined. A land that
is untapped only in the first run is `untapped_if_paid`, and the declined
questions' prompts are its `optional_costs`. A payment that is legal but leaves
the player losing at the next state-based check (CR 704.5a) sets
`lethal_if_paid`, and payability then uses the declined run.

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

**Batching.** Every answer about a land is worked out on the one board its
prediction already built, so a payability question never enters a land a
second time. `payability_matrix` settles one copy for "now" and one board per
distinct land, runs `legal_actions` once on each and reads every card's options
off that one enumeration, and treats every library copy of one printing as the
same question, with one exception: the copy currently on top of the library
always gets its own evaluation, never the shared one, because a play-from-top
effect (CR 401.5) reads which physical copy is there and a buried copy is not
interchangeable with it. Every other library copy of that printing still
shares - the card identity differs, nothing else a payment reads does.

**What "assuming" does not check.** It does not ask whether the land could be
played this turn (CR 305.2's land drop) or how it would get from the library to
the battlefield (a fetch land's search) - the caller composes those. A land in
the library is put onto the battlefield front face up (CR 712.14); one in hand
that is a modal double-faced card with a land back is played with that face up
(CR 712.12), mirroring `Game.play_land`.
"""

from collections.abc import Callable, Sequence
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
    #: Why the answer failed closed (an unread enters-tapped line), what a
    #: trigger resolving after it enters would change about it (CR 603.3), and
    #: why `lethal_if_paid` is set.
    notices: tuple[str, ...] = ()
    #: `UNTAPPED_IF_PAID` only: paying `optional_costs` is legal (CR 119.4) but
    #: would lose the game at the next state-based action check (CR 704.5a),
    #: so the untapped option is not one a player can use to cast anything.
    lethal_if_paid: bool = False


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


class LandPayability(BaseModel):
    """One land's column of `PayabilityMatrix`."""

    model_config = ConfigDict(frozen=True)

    land_id: UUID
    #: What `predict_enters` answers for this land.
    prediction: EntersPrediction
    #: What `payability(..., assuming_land=this land)` answers, one per card
    #: asked about, in the order given - the land itself left out.
    cards: tuple[Payability, ...]


class PayabilityMatrix(BaseModel):
    """`payability_matrix`'s answer."""

    model_config = ConfigDict(frozen=True)

    #: What `payability(card)` answers, one per card, in the order given.
    now: tuple[Payability, ...]
    #: One per land, in the order given.
    lands: tuple[LandPayability, ...]

    def get(self, card_id: UUID, land_id: UUID | None = None) -> Payability | None:
        """The answer for `card_id` now, or with `land_id` assumed; `None` for
        a pair that was not asked (a card and itself as the land included)."""
        if land_id is None:
            rows: tuple[Payability, ...] = self.now
        else:
            rows = next((entry.cards for entry in self.lands if entry.land_id == land_id), ())
        return next((row for row in rows if row.card_id == card_id), None)


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

#: What building a board returns: the copy, the entered land (or None for the
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
    #: Who had lost the game once the land entered, before any trigger
    #: resolved: the state-based check CR 704.3 makes first (CR 704.5a).
    losers_on_entry: frozenset[str] = frozenset()


class _Evaluated(NamedTuple):
    """A land's prediction and the settled board every payability question
    about that land is answered on."""

    prediction: EntersPrediction
    board: "Game"
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


def _plays_land_face(card: CardState) -> bool:
    """CR 712.12: an MDFC with a land back is played from hand land face up."""
    return card.zone is Zone.HAND and not card.card.is_land and card.card.land_face is not None


def _enter_on_a_copy(
    game: "Game", player: str, land_id: UUID, *, decline_optional_payments: bool
) -> _Built:
    copy = _decoded_copy(game)
    if decline_optional_payments:
        for kind in _OPTIONAL_PAYMENTS:
            copy.decisions.add(ScriptedAnswer(kind=kind, value=False, player=player, uses=None))
    entering = copy.find_by_id(land_id)
    assert entering is not None  # decoded from the game `land_id` was found in
    if _plays_land_face(entering):
        assert entering.card.land_face is not None
        entering.land_face_played = entering.card.land_face.name
    asked_before = len(copy.decisions.asked)
    copy.put_onto_battlefield(entering, player)
    return copy, entering, copy.decisions.asked[asked_before:]


def _unread_notices(land: CardState) -> tuple[str, ...]:
    """Read off a shallow copy of the card with its land face up - no game is
    needed to read one card's own printed lines."""
    face_up = land
    if _plays_land_face(land):
        assert land.card.land_face is not None
        face_up = land.model_copy(update={"land_face_played": land.card.land_face.name})
    return tuple(
        f'{face_up.name}: "{line}" is not read by the engine, so it is reported tapped '
        "rather than guessed (CR 614.1d)"
        for line in unread_self_enters_tapped_lines(face_up)
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
        board.check_state_based_actions()  # CR 704.3
        losers = frozenset(board.losers)
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
        return _Settled(board, entered, asked, entry, tuple(resolved), tuple(notices), losers)
    board, entered, asked = rebuild()
    entry = _observed(entered)
    board.check_state_based_actions()  # CR 704.3
    board.pending_triggers = []
    notices = (
        *skipped.values(),
        f"triggered abilities still needed choices after {_MAX_SETTLE_PASSES} attempts, "
        "so none of them is counted (CR 603.3)",
    )
    return _Settled(board, entered, asked, entry, (), notices, frozenset(board.losers))


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
# One land, one board
# --------------------------------------------------------------------------


def _evaluate_land(game: "Game", player: str, land: CardState) -> _Evaluated:
    """`predict_enters`'s answer for `land`, already validated by
    `_land_to_enter`, with the settled board payability is judged on: the
    paying run, the declined run when the payment is lethal, and a run forced
    tapped when the prediction failed closed."""
    base = {"card_id": land.id, "name": land.name, "zone": land.zone}
    unread = _unread_notices(land)
    if unread:

        def entered_tapped() -> _Built:
            board, entered, asked = _enter_on_a_copy(
                game, player, land.id, decline_optional_payments=False
            )
            if entered is not None:
                entered.tapped = True  # fail closed: the prediction says tapped
            return board, entered, asked

        forced = _settle(entered_tapped)
        prediction = EntersPrediction(**base, state=EntersState.TAPPED, notices=unread)
        return _Evaluated(prediction, forced.board, forced.notices)

    paying = _settle(
        lambda: _enter_on_a_copy(game, player, land.id, decline_optional_payments=False)
    )
    change = _change_notice(land.name, paying)
    triggered = (change,) if change is not None else ()
    assert paying.entry is not None
    offered = [
        decision
        for decision in paying.asked
        if decision.kind in _OPTIONAL_PAYMENTS
        and decision.player == player
        and decision.affirmative_is_legal
    ]
    if paying.entry[1] or not offered:
        state = EntersState.TAPPED if paying.entry[1] else EntersState.UNTAPPED
        prediction = EntersPrediction(**base, state=state, notices=triggered)
        return _Evaluated(prediction, paying.board, paying.notices)

    declining_board, declining, asked = _enter_on_a_copy(
        game, player, land.id, decline_optional_payments=True
    )
    assert declining is not None
    if not declining.tapped:
        prediction = EntersPrediction(**base, state=EntersState.UNTAPPED, notices=triggered)
        return _Evaluated(prediction, paying.board, paying.notices)
    costs = tuple(
        decision.prompt
        for decision in asked
        if decision.kind in _OPTIONAL_PAYMENTS and decision.player == player
    )
    # CR 704.3 / 704.5a: a payment is lethal when the player has lost at the
    # first state-based check after paying, and has not after declining.
    declining_board.check_state_based_actions()
    lethal = player in paying.losers_on_entry and declining_board.is_in_game(player)
    notices = triggered
    if lethal:
        notices = (
            *triggered,
            f"{land.name}: paying {' and '.join(costs)} is legal (CR 119.4) but leaves "
            f"{player} at 0 or less life, and they lose the game (CR 704.5a)",
        )
    prediction = EntersPrediction(
        **base,
        state=EntersState.UNTAPPED_IF_PAID,
        optional_costs=costs,
        notices=notices,
        lethal_if_paid=lethal,
    )
    if not lethal:
        return _Evaluated(prediction, paying.board, paying.notices)
    # A lethal optional payment is not a way to cast anything: the land is
    # judged as it enters when that payment is declined.
    declined = _settle(
        lambda: _enter_on_a_copy(game, player, land.id, decline_optional_payments=True)
    )
    return _Evaluated(prediction, declined.board, declined.notices)


def _now(game: "Game") -> _Settled:
    return _settle(lambda: (_decoded_copy(game), None, []))


def _options_by_card(board: "Game", player: str, card_ids: set[UUID]) -> dict[UUID, list[Action]]:
    """One `legal_actions` enumeration, read for every card asked about."""
    grouped: dict[UUID, list[Action]] = {card_id: [] for card_id in card_ids}
    for action in legal_actions(board, player):
        if action.card_id in grouped and action.kind is not ActionKind.PLAY_LAND:
            grouped[action.card_id].append(action)
    return grouped


def _answer(
    card_id: UUID,
    options: list[Action],
    assumed: EntersPrediction | None,
    notices: tuple[str, ...],
) -> Payability:
    return Payability(
        card_id=card_id,
        payable=any(option.affordable is Affordability.YES for option in options),
        options=tuple(options),
        assumed_land=assumed,
        notices=notices,
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
    return _evaluate_land(game, player, _land_to_enter(game, player, land)).prediction


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
    not lethal, and its choice-free triggers resolved. Mutates nothing. See the
    module docstring.
    """
    target = _card(game, card)
    if assuming_land is None:
        now = _now(game)
        options = _options_by_card(now.board, player, {target.id})[target.id]
        return _answer(target.id, options, None, now.notices)
    land = _land_to_enter(game, player, assuming_land)
    if land.id == target.id:
        raise ValueError(f"{land.name} cannot be both the card asked about and the land assumed")
    evaluated = _evaluate_land(game, player, land)
    options = _options_by_card(evaluated.board, player, {target.id})[target.id]
    return _answer(target.id, options, evaluated.prediction, evaluated.notices)


def payability_matrix(
    game: "Game",
    player: str,
    cards: Sequence[CardState | UUID],
    lands: Sequence[CardState | UUID],
) -> PayabilityMatrix:
    """`payability` for every card in `cards` now and with each land in
    `lands` assumed, and `predict_enters` for each land, as one batch. Every
    answer is the one the single call gives; a card is never asked about with
    itself as the land. Mutates nothing. See the module docstring.

    Raises `ValueError` as `payability` and `predict_enters` do.
    """
    targets = [_card(game, card) for card in cards]
    target_ids = {target.id for target in targets}

    now = _now(game)
    now_options = _options_by_card(now.board, player, target_ids)
    answers_now = tuple(
        _answer(target.id, now_options[target.id], None, now.notices) for target in targets
    )

    # Two library copies of one printing are the same question only because
    # nothing here reads which physical copy entered. An effect that plays
    # from a revealed top of the library (CR 401.5) reads exactly that, and a
    # copy on top of the library is not interchangeable with a buried one
    # under it - so the top card is never folded into the shared cache below,
    # even though every other same-printing copy still is. This is the
    # smallest rule that stays correct for such an effect without giving up
    # the sharing that makes a big library affordable to batch: it costs at
    # most one extra evaluation (the top card's own), not one per copy.
    library = game.player(player).library
    top_id = library[0].id if library else None

    shared: dict[str, tuple[_Evaluated, dict[UUID, list[Action]]]] = {}
    columns: list[LandPayability] = []
    for reference in lands:
        land = _land_to_enter(game, player, reference)
        # Library copies of one printing are one question - unless a copy is
        # also a card asked about, whose options would read the entered copy,
        # or is the top card, whose answer a play-from-top effect could read.
        key = (
            str(land.card.id)
            if land.zone is Zone.LIBRARY and land.id not in target_ids and land.id != top_id
            else None
        )
        if key is not None and key in shared:
            evaluated, options = shared[key]
        else:
            evaluated = _evaluate_land(game, player, land)
            options = _options_by_card(evaluated.board, player, target_ids)
            if key is not None:
                shared[key] = (evaluated, options)
        prediction = evaluated.prediction
        if prediction.card_id != land.id:
            prediction = prediction.model_copy(update={"card_id": land.id})
        column = tuple(
            _answer(target.id, options[target.id], prediction, evaluated.notices)
            for target in targets
            if target.id != land.id
        )
        columns.append(LandPayability(land_id=land.id, prediction=prediction, cards=column))
    return PayabilityMatrix(now=answers_now, lands=tuple(columns))


__all__ = [
    "EntersPrediction",
    "EntersState",
    "LandPayability",
    "Payability",
    "PayabilityMatrix",
    "payability",
    "payability_matrix",
    "predict_enters",
]
