"""The optional or counted action in an "As [this] enters, ..." sentence whose
result sizes the counters it enters with (CR 614.1c, CR 614.12a).

    As this creature enters, you may reveal a Dragon card from your hand. If
    you do or if you control a Dragon, this creature enters with a +1/+1
    counter on it.                                             (Dragon's Disciple)
    As this creature enters, you may reveal any number of other artifact cards
    from your hand. This creature enters with a +1/+1 counter on it for each
    card revealed this way.                                    (Arsenal Thresher)
    As this creature enters, you may return a nonland permanent you control to
    its owner's hand. If you do, ...                           (Rescuer Sphinx)
    As this creature enters, you may put two cards your opponents own from
    exile into their owners' graveyards. If you do, ...        (Ulamog's Despoiler)
    As this creature enters, exile up to X creature cards from your graveyard.
    It enters with three +1/+1 counters on it for each creature card exiled
    this way.                                                  (Mimeoplasm)

CR 614.12a makes the choice before the permanent enters, so each action runs
inside `apply_replacements` and returns how many objects it acted on. The
sentence that follows reads that number: "If you do" is "at least one", "for
each card revealed this way" multiplies it (`counters_for`).
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...models.card import Type
from ...models.card_state import CardState, ExileAnnotation, ExileMarker
from ...models.zone import Zone
from ...numbers import COUNT, parse_count
from ..decisions import Decision, DecisionKind, source_id_of

if TYPE_CHECKING:
    from ...models.card_state import CardState as _CardState  # noqa: F401
    from ...models.game import Game
    from .model import ReplaceableEvent

#: `act(game, who, event, source, card_name) -> int`: how many objects the
#: action was performed on.
Action = Callable[["Game", str, "ReplaceableEvent", "CardState | None", str], int]

_REVEAL = re.compile(
    r"^you may reveal (?:an? (?P<one>[\w-]+) card"
    r"|any number of (?P<other>other )?(?P<many>[\w-]+) cards) from your hand\.?$",
    re.IGNORECASE,
)
_RETURN = re.compile(
    r"^you may return an? nonland permanent you control to its owner's hand\.?$", re.IGNORECASE
)
_PUT_FROM_EXILE = re.compile(
    r"^you may put two cards your opponents own from exile into their owners' graveyards\.?$",
    re.IGNORECASE,
)
_EXILE_UP_TO_X = re.compile(r"^exile up to x creature cards from your graveyard\.?$", re.IGNORECASE)


def _choose(
    game: "Game",
    who: str,
    candidates: list["CardState"],
    ceiling: int,
    prompt: str,
    card_name: str,
    source: "CardState | None",
) -> list["CardState"]:
    """One `CHOOSE_CARDS` question, `exact=False` (CR 107.1c): zero is always a
    legal answer, so "you may" needs no separate yes/no and an unscripted
    answer declines."""
    ceiling = min(ceiling, len(candidates))
    if ceiling <= 0:
        return []
    answer = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=who,
            prompt=prompt,
            source=card_name,
            source_id=source_id_of(source),
            amount=ceiling,
            exact=False,
            cards=tuple(candidate.id for candidate in candidates),
        )
    )
    assert isinstance(answer, tuple)
    by_id = {candidate.id: candidate for candidate in candidates}
    return [by_id[card_id] for card_id in answer]


def _reveal(match: re.Match[str]) -> Action:
    from .enters import _noun_matches

    quality = (match.group("one") or match.group("many")).lower()
    many = match.group("many") is not None
    other = match.group("other") is not None

    def act(game, who, event, source, card_name):
        entering = event.card
        candidates = [
            card
            for card in game.player(who).hand
            if not (other and entering is not None and card.id == entering.id)
            and _noun_matches(card, quality)
        ]
        chosen = _choose(
            game,
            who,
            candidates,
            len(candidates) if many else 1,
            f"choose cards to reveal as {card_name} enters",
            card_name,
            source,
        )
        for card in chosen:
            game.reveal(card, source=card_name)
        return len(chosen)

    return act


def _return(_match: re.Match[str]) -> Action:
    def act(game, who, event, source, card_name):
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(who)
            if Type.LAND not in game.characteristics_of(permanent).types
        ]
        chosen = _choose(
            game,
            who,
            candidates,
            1,
            f"choose a nonland permanent to return as {card_name} enters",
            card_name,
            source,
        )
        for permanent in chosen:
            game.return_to_hand(permanent)
        return len(chosen)

    return act


def _put_from_exile(_match: re.Match[str]) -> Action:
    def act(game, who, event, source, card_name):
        candidates = [
            card
            for card in game.exile
            if (card.owner or card.controller) not in (None, who) and not card.token
        ]
        if len(candidates) < 2:
            return 0
        chosen = _choose(
            game,
            who,
            candidates,
            2,
            f"choose two cards to put into their owners' graveyards as {card_name} enters",
            card_name,
            source,
        )
        if len(chosen) not in (0, 2):
            raise ValueError(f"{card_name}: put exactly two cards into graveyards, or none")
        for card in chosen:
            game.put_into_graveyard(card)
        return len(chosen) // 2

    return act


def _exile_up_to_x(_match: re.Match[str]) -> Action:
    def act(game, who, event, source, card_name):
        record = game.cast_record_of(event.card) if event.card is not None else None
        x_value = record.x_value if record is not None else 0
        candidates = [card for card in game.player(who).graveyard if Type.CREATURE in card.types]
        chosen = _choose(
            game,
            who,
            candidates,
            x_value,
            f"choose creature cards to exile as {card_name} enters",
            card_name,
            source,
        )
        for exiled in game.exile_cards(chosen):
            if exiled.zone is Zone.EXILE and source is not None:
                # CR 607.2a: exiled "with" the entering permanent, which its
                # "target creature card exiled with it" ability reads.
                exiled.exile_annotation = ExileAnnotation(
                    marker=ExileMarker.LINKED,
                    owner=exiled.owner,
                    turn_exiled=game.turn.turns_taken if game.turn is not None else None,
                    linked_permanent_id=source.id,
                    linked_permanent_stamp=None,
                )
        return len(chosen)

    return act


_ACTIONS = (
    (_REVEAL, _reveal),
    (_RETURN, _return),
    (_PUT_FROM_EXILE, _put_from_exile),
    (_EXILE_UP_TO_X, _exile_up_to_x),
)


def as_enters_action(replacement: str) -> Action | None:
    """The action an "As [this] enters, `<replacement>`" sentence performs, or
    None when it is not one of the shapes above."""
    text = (replacement or "").strip()
    for pattern, build in _ACTIONS:
        match = pattern.match(text)
        if match is not None:
            return build(match)
    return None


_PER_OBJECT = re.compile(
    rf"^(?:(?P<n>{COUNT}) times )?(?:[\w-]+ )?cards? (?:exiled|revealed) this way$", re.IGNORECASE
)


def counters_for(
    game: "Game",
    who: str,
    entering: "CardState",
    done: int,
    *,
    amount: int | None,
    expression: str | None,
    condition: str | None,
) -> int:
    """How many counters the sentence after the action puts on `entering`,
    given that the action was performed on `done` objects."""
    if expression is not None:
        per = _PER_OBJECT.match(expression.strip())
        if per is None:
            return 0
        return (parse_count(per.group("n")) if per.group("n") else 1) * done
    if amount is None:
        return 0
    if condition is None:
        return amount
    for alternative in re.split(r"\s+or\s+(?:if\s+)?", condition.strip()):
        alternative = alternative.strip().rstrip(".")
        if alternative == "you do":
            if done > 0:
                return amount
        elif game.condition_holds(who, alternative, entering):
            return amount
    return 0
