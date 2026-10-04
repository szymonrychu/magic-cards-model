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
  cards and lands at once, as one batch (see "Batching" below), and with
  `assuming_untapped=True` the same batch answered a land drop ahead (see
  "Assuming untapped" below).

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

**Mana abilities that cost life.** Auto-tap never activates a mana ability
whose cost is more than a bare {T} (CR 118.3c), but the player may (CR 601.2g,
605.3a), so a what-if answer counts "{T}, Pay N life: Add ..." abilities
(`cost.life_paid_mana_activations`). An option the ordinary enumeration calls
unaffordable is judged again with them (`legal_actions(...,
include_life_paid_mana=True)`, life rows tried last). A plan that needs one is
then played on a further copy: each life-paid ability in it is activated
through `Game.begin_activating`/`activate_ability` for the colours the plan
chose, the state-based check runs (CR 704.5a), and the option is counted only
if the player is still in the game and the ordinary enumeration now calls it
affordable from the floating mana. `Payability.life_paid` is the life the
cheapest payable option costs, and a notice names each ability. Any other
extra cost (a sacrifice, a mana payment) is not activated: a card left
unpayable names each such source in a notice instead.

**Assuming untapped.** `payability_matrix(..., assuming_untapped=True)` answers
every question on a board where `player`'s untap step has already happened.
What untaps is not decided here: `Game.untap_step_rule` is the one place that
rule lives (CR 614.10's skip verdict for the whole step, then CR 502.3's "the
active player determines which permanents they control will untap", less the
permanents an effect keeps from untapping), and the untapping goes through
`Player.untap_all`, so CR 122.1d's stun counter and CR 701.43a's exert are
spent inside `CardState.untap` exactly as the real step spends them. The
hypothetical and the step therefore cannot answer differently.

It models the mana and nothing else. No card is drawn, no upkeep trigger
resolves, no turn or phase advances, nothing the opponent does in between is
accounted for, no event is emitted, and no permanent another player controls
is touched - `untap_step_rule` is asked about one player. The caller's game is
not mutated: the untapping happens on the same decoded copy every other board
here is built on. Every `Payability` answered this way carries a notice saying
all of that, because one row read on its own would otherwise look like a
prediction of the next turn, which it is not.

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

from pydantic import ConfigDict

from ..models.action import Action, ActionKind, Affordability, ManaPlanEntry
from ..models.card import Color
from ..models.card_state import CardState
from ..models.zone import Zone
from ..snapshot import EngineModel
from .abilities import ActivatedAbility
from .cost import (
    _SpendContext,
    _withheld_mana_sources,
    counted_mana_options,
    life_paid_mana_activations,
)
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


class EntersPrediction(EngineModel):
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


class Payability(EngineModel):
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
    #: needed somebody's choice, named rather than guessed; each life-paid
    #: mana ability an option counts, or was refused because paying it loses
    #: the game (CR 704.5a); and, when an option is still unpayable, each mana
    #: ability with another extra cost that was not activated (CR 118.3c).
    notices: tuple[str, ...] = ()
    #: The life the cheapest payable option costs through "{T}, Pay N life"
    #: mana abilities the player activates themselves (CR 605.3a). 0 when a
    #: payable option needs none, and when nothing is payable.
    life_paid: int = 0


class LandPayability(EngineModel):
    """One land's column of `PayabilityMatrix`."""

    model_config = ConfigDict(frozen=True)

    land_id: UUID
    #: What `predict_enters` answers for this land.
    prediction: EntersPrediction
    #: What `payability(..., assuming_land=this land)` answers, one per card
    #: asked about, in the order given - the land itself left out.
    cards: tuple[Payability, ...]


class PayabilityMatrix(EngineModel):
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


#: The sentence every answer under `assuming_untapped` carries, so a reader
#: who sees only one `Payability` still knows what it is and is not.
_ASSUMING_UNTAPPED_NOTICE = (
    "assuming untapped: this is a mana hypothetical about permanents untapping, not a "
    "prediction of the next turn - it does not draw a card, does not resolve an upkeep "
    "trigger, does not advance the turn, and does not account for anything the opponent "
    "does in between"
)


def _untapped_copy(game: "Game", player: str) -> tuple["Game", tuple[str, ...]]:
    """A copy of `game` with `player`'s untap step already taken, and one
    notice saying what that moved.

    The rule is not re-implemented here. `Game.untap_step_rule` is the one
    place it lives - CR 614.10's skip verdict for the whole step, then
    CR 502.3's "the active player determines which permanents they control
    will untap", less the permanents an effect keeps from untapping - and the
    untapping itself goes through `Player.untap_all`, exactly as
    `Game._untap_step_impl` does. That second half is not decoration: the rule
    deliberately leaves CR 122.1d's stun counter and CR 701.43a's exert to
    `CardState.untap`, where every route to untapping passes, so a caller that
    read the rule and untapped the batch itself would report a stunned or
    exerted permanent as untapping. Going through `untap_all` is what makes
    this hypothetical and the real step give the same answer.

    Nothing else about the step is taken: no `BECOMES_UNTAPPED` event is
    emitted, the skip is read and not spent, and no turn or phase moves. The
    caller's `game` is untouched - `_decoded_copy` is the same round trip
    every other board here is built on.
    """
    copy = _decoded_copy(game)
    verdict = copy.untap_step_rule(player)
    if verdict.skipped:
        return copy, (
            f"assuming untapped: {player} skips their next untap step (CR 614.10), "
            f"so nothing untaps and this is the board as it stands",
        )
    was_tapped = [state for state in verdict.permanents if state.tapped]
    copy.player(player).untap_all(verdict.permanents)
    # Named from what actually untapped rather than from the batch, so a
    # permanent whose untap was replaced (CR 122.1d, CR 701.43a) is not
    # claimed as untapped by a notice the board disagrees with.
    untapped = [state.name for state in was_tapped if not state.tapped]
    if not untapped:
        return copy, (
            f"assuming untapped: nothing {player} controls would untap, "
            f"so this is the board as it stands",
        )
    return copy, (
        f"assuming untapped: {', '.join(untapped)} untap for {player}; "
        f"every other permanent is left exactly as it is now",
    )


class _CardOptions(NamedTuple):
    """One card's options on one board, with what judging them added."""

    options: list[Action]
    notices: tuple[str, ...] = ()
    life_paid: int = 0


#: `(permanent id, ability index)` of each life-paid mana ability on a board,
#: with its permanent, the ability and the life it costs.
_LifePaid = dict[tuple[UUID, int], tuple[CardState, ActivatedAbility, int]]

#: The fields an affordability verdict sets on an `Action`, cleared to compare
#: the same action across two enumerations.
_VERDICT: dict[str, Any] = {
    "affordable": Affordability.UNKNOWN,
    "unaffordable_reason": None,
    "pays_with": (),
}


class _Played(NamedTuple):
    """The outcome of activating one set of life-paid mana abilities on a
    copy: the enumeration afterwards, or why there is none."""

    after: list[Action]
    #: Why nothing was enumerated: a refused activation, or a lost game.
    refusal: str | None = None
    lethal: bool = False


def _grouped(actions: list[Action], card_ids: set[UUID]) -> dict[UUID, list[Action]]:
    grouped: dict[UUID, list[Action]] = {card_id: [] for card_id in card_ids}
    for action in actions:
        if action.card_id in grouped and action.kind is not ActionKind.PLAY_LAND:
            grouped[action.card_id].append(action)
    return grouped


def _twin(action: Action, among: list[Action]) -> Action | None:
    """`action` as another enumeration of the same board reports it."""
    bare = action.model_copy(update=_VERDICT)
    return next((other for other in among if other.model_copy(update=_VERDICT) == bare), None)


def _life_paid_sources(board: "Game", player: str) -> _LifePaid:
    found: _LifePaid = {}
    for source in board.battlefield:
        if source.tapped or source.controller not in (None, player):
            continue
        for index, ability, life in life_paid_mana_activations(source, board):
            found[(source.id, index)] = (source, ability, life)
    return found


def _key(entry: ManaPlanEntry) -> tuple[UUID, int]:
    assert entry.ability_index is not None  # a life-paid row always has its index
    return entry.card_id, entry.ability_index


def _named(entries: Sequence[ManaPlanEntry], life_paid: _LifePaid) -> str:
    return "; ".join(
        f'{source.name}\'s "{ability.cost}: {ability.effect}"'
        for source, ability, _life in (life_paid[_key(entry)] for entry in entries)
    )


def _own_colors(
    ability: ActivatedAbility, adds: str, board: "Game", source: CardState, player: str
) -> Color | list[Color]:
    """The colours a plan entry's ability makes itself, without what a
    triggered mana ability adds after it (`cost._with_triggered_mana` lists
    the ability's own mana first). A count the board decides ("for each",
    "where X is", devotion) is counted on `board`, the way the plan was."""
    mana = ability.mana
    assert mana is not None  # a life-paid mana ability
    counted, _amount = counted_mana_options(board, player, source, mana, mana.options)
    first = Color(adds[0]) if adds else None
    lengths = [len(option) for option in counted if first is None or option[:1] == [first]]
    if lengths:
        count = lengths[0]
    else:
        count = len(mana.options[0]) if mana.options else mana.any_color_count
    colors = [Color(symbol) for symbol in adds][:count]
    return colors[0] if len(colors) == 1 else colors


def _play_life_payments(
    board: "Game", player: str, entries: Sequence[ManaPlanEntry], life_paid: _LifePaid
) -> _Played:
    """Activate each life-paid ability in `entries` on a copy of `board`
    (CR 605.3a, costs paid per CR 602.2b), run the state-based check
    (CR 704.5a), and enumerate again."""
    copy = _decoded_copy(board)
    try:
        for entry in entries:
            assert entry.ability_index is not None
            source = copy.find_by_id(entry.card_id)
            assert source is not None  # decoded from the board the plan was made on
            ability = life_paid[(entry.card_id, entry.ability_index)][1]
            payment = copy.begin_activating(source, entry.ability_index, player)
            payment.pay()
            copy.activate_ability(
                source,
                entry.ability_index,
                player,
                color=_own_colors(ability, entry.adds, copy, source, player),
            )
    except ValueError as refusal:
        return _Played([], refusal=str(refusal))
    copy.check_state_based_actions()
    if not copy.is_in_game(player):
        return _Played([], lethal=True)
    return _Played(legal_actions(copy, player))


def _option_label(option: Action) -> str:
    return option.keyword or option.alternative_cost or option.kind.value


def _with_life_payments(
    board: "Game",
    player: str,
    options: list[Action],
    judged_again: list[Action],
    life_paid: _LifePaid,
    played: dict[tuple[Any, ...], _Played],
) -> _CardOptions:
    """`options` with each unaffordable one that life-paid mana abilities pay
    for replaced by its affordable twin from `judged_again`."""
    result: list[Action] = []
    notices: list[str] = []
    costs: list[int] = []
    for option in options:
        twin = _twin(option, judged_again) if option.affordable is Affordability.NO else None
        paying = (
            [entry for entry in twin.pays_with if (entry.card_id, entry.ability_index) in life_paid]
            if twin is not None and twin.affordable is Affordability.YES
            else []
        )
        if not paying:
            result.append(option)
            if option.affordable is Affordability.YES:
                costs.append(0)
            continue
        key = tuple((entry.card_id, entry.ability_index, entry.adds) for entry in paying)
        if key not in played:
            played[key] = _play_life_payments(board, player, paying, life_paid)
        outcome = played[key]
        life = sum(life_paid[_key(entry)][2] for entry in paying)
        named = _named(paying, life_paid)
        after = _twin(option, outcome.after)
        if outcome.lethal:
            notices.append(
                f"{_option_label(option)}: activating {named} pays {life} life and leaves "
                f"{player} at 0 or less life, and they lose the game (CR 704.5a), so it "
                "is not counted"
            )
            result.append(option)
        elif (
            outcome.refusal is not None
            or after is None
            or after.affordable is not Affordability.YES
        ):
            why = outcome.refusal or "the mana it makes still does not pay for it"
            notices.append(f"{_option_label(option)}: activating {named} is not counted ({why})")
            result.append(option)
        else:
            notices.append(
                f"{_option_label(option)}: payable by activating {named}, paying {life} life, "
                f"which auto-tap never does for {player} (CR 118.3c) but they may (CR 605.3a)"
            )
            assert twin is not None  # `paying` is read off it
            result.append(twin)
            costs.append(life)
    return _CardOptions(result, tuple(notices), min(costs) if costs else 0)


def _other_extra_costs(board: "Game", player: str, life_paid: _LifePaid) -> tuple[str, ...]:
    """Each mana ability auto-tap withholds whose extra cost is not life."""
    counted = {(source.id, ability.raw) for source, ability, _life in life_paid.values()}
    context = _SpendContext(game=board, payer=player, spend=None)
    return tuple(
        dict.fromkeys(
            f'{source.name}\'s mana ability "{ability.cost}: {ability.effect}" costs more than '
            "{T} and life, so it is not activated here (CR 118.3c)"
            for source, ability in _withheld_mana_sources(context, board.battlefield)
            if (source.id, ability.raw) not in counted
        )
    )


def _options_by_card(board: "Game", player: str, card_ids: set[UUID]) -> dict[UUID, _CardOptions]:
    """One `legal_actions` enumeration, read for every card asked about, and
    judged again with life-paid mana abilities when an option is unaffordable
    (see "Mana abilities that cost life" in the module docstring)."""
    grouped = _grouped(legal_actions(board, player), card_ids)
    answers = {card_id: _CardOptions(options) for card_id, options in grouped.items()}
    unpaid = {
        card_id
        for card_id, options in grouped.items()
        if any(option.affordable is Affordability.NO for option in options)
    }
    if not unpaid:
        return answers
    life_paid = _life_paid_sources(board, player)
    if life_paid:
        judged_again = _grouped(legal_actions(board, player, include_life_paid_mana=True), unpaid)
        played: dict[tuple[Any, ...], _Played] = {}
        for card_id in unpaid:
            answers[card_id] = _with_life_payments(
                board, player, grouped[card_id], judged_again[card_id], life_paid, played
            )
    others: tuple[str, ...] | None = None
    for card_id in unpaid:
        answer = answers[card_id]
        if all(option.affordable is not Affordability.NO for option in answer.options):
            continue
        if others is None:
            others = _other_extra_costs(board, player, life_paid)
        if others:
            answers[card_id] = answer._replace(notices=(*answer.notices, *others))
    return answers


def _answer(
    card_id: UUID,
    judged: _CardOptions,
    assumed: EntersPrediction | None,
    notices: tuple[str, ...],
) -> Payability:
    return Payability(
        card_id=card_id,
        payable=any(option.affordable is Affordability.YES for option in judged.options),
        options=tuple(judged.options),
        assumed_land=assumed,
        notices=(*notices, *judged.notices),
        life_paid=judged.life_paid,
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
    *,
    assuming_untapped: bool = False,
) -> PayabilityMatrix:
    """`payability` for every card in `cards` now and with each land in
    `lands` assumed, and `predict_enters` for each land, as one batch. Every
    answer is the one the single call gives; a card is never asked about with
    itself as the land. Mutates nothing. See the module docstring.

    `assuming_untapped=True` answers all of it on a board where `player`'s
    untap step has already happened: the permanents `Game.untap_step_rule`
    says would untap, untapped through `Player.untap_all`. It is the one
    question a seat looking a land drop ahead needs. **What it models** is the
    mana: which of `player`'s permanents are untapped and therefore available
    to pay. **What it does not model** is the rest of the turn - no card is
    drawn, no upkeep trigger resolves, no turn or phase advances, nothing the
    opponent does in between is accounted for, and no permanent anybody else
    controls is touched. Every `Payability` it answers says so in its own
    `notices`, so a row read on its own cannot be mistaken for a prediction.

    The default answers byte for byte what the call without it answers.

    Raises `ValueError` as `payability` and `predict_enters` do.
    """
    hypothetical_notices: tuple[str, ...] = ()
    if assuming_untapped:
        game, what_untapped = _untapped_copy(game, player)
        hypothetical_notices = (_ASSUMING_UNTAPPED_NOTICE, *what_untapped)
    targets = [_card(game, card) for card in cards]
    target_ids = {target.id for target in targets}

    now = _now(game)
    now_options = _options_by_card(now.board, player, target_ids)
    answers_now = tuple(
        _answer(target.id, now_options[target.id], None, (*hypothetical_notices, *now.notices))
        for target in targets
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

    shared: dict[str, tuple[_Evaluated, dict[UUID, _CardOptions]]] = {}
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
            _answer(
                target.id,
                options[target.id],
                prediction,
                (*hypothetical_notices, *evaluated.notices),
            )
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
