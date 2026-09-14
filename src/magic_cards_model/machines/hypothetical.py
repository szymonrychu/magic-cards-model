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

**What "assuming" does not check.** It does not ask whether the land could be
played this turn (CR 305.2's land drop) or how it would get from the library to
the battlefield (a fetch land's search) - the caller composes those. A land in
the library is put onto the battlefield front face up (CR 712.14); one in hand
that is a modal double-faced card with a land back is played with that face up
(CR 712.12), mirroring `Game.play_land`.
"""

from enum import StrEnum
from typing import TYPE_CHECKING, Any
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
    #: Why the answer failed closed, one entry per unread enters-tapped line.
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


#: The yes-or-no payments an entering permanent can offer (CR 608.2d). Declining
#: every one of them is always legal, which is what makes the second run safe.
_OPTIONAL_PAYMENTS = (
    DecisionKind.MAY,
    DecisionKind.PAY_LIFE,
    DecisionKind.PAY_ENERGY,
    DecisionKind.PAY_MANA,
)


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
) -> tuple["Game", CardState, list[Decision]]:
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

    _, paying, _ = _enter_on_a_copy(game, player, found.id, decline_optional_payments=False)
    if paying.tapped:
        return EntersPrediction(**base, state=EntersState.TAPPED)

    _, declining, asked = _enter_on_a_copy(game, player, found.id, decline_optional_payments=True)
    if not declining.tapped:
        return EntersPrediction(**base, state=EntersState.UNTAPPED)
    costs = tuple(
        decision.prompt
        for decision in asked
        if decision.kind in _OPTIONAL_PAYMENTS and decision.player == player
    )
    return EntersPrediction(**base, state=EntersState.UNTAPPED_IF_PAID, optional_costs=costs)


def payability(
    game: "Game",
    player: str,
    card: CardState | UUID,
    *,
    assuming_land: CardState | UUID | None = None,
) -> Payability:
    """Whether `player` could pay for `card` right now, or with
    `assuming_land` (a land in their hand or library) on the battlefield as
    `predict_enters` says it would enter, its optional cost paid when legal.
    Mutates nothing. See the module docstring.
    """
    target = _card(game, card)
    assumed: EntersPrediction | None = None
    if assuming_land is None:
        board: Any = _decoded_copy(game)
    else:
        land = _land_to_enter(game, player, assuming_land)
        if land.id == target.id:
            raise ValueError(
                f"{land.name} cannot be both the card asked about and the land assumed"
            )
        assumed = predict_enters(game, player, land)
        board, entered, _ = _enter_on_a_copy(game, player, land.id, decline_optional_payments=False)
        if assumed.state is EntersState.TAPPED:
            # Fail closed on an unread line too: the prediction said tapped.
            entered.tapped = True
    options = tuple(
        action
        for action in legal_actions(board, player)
        if action.card_id == target.id and action.kind is not ActionKind.PLAY_LAND
    )
    return Payability(
        card_id=target.id,
        payable=any(option.affordable is Affordability.YES for option in options),
        options=options,
        assumed_land=assumed,
    )


__all__ = ["EntersPrediction", "EntersState", "Payability", "payability", "predict_enters"]
