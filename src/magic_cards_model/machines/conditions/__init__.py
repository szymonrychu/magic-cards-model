"""One reader for every printed condition the engine gates something on.

Three rules paths ask the same kind of question - "is this printed condition
true right now?" - and used to ask three different readers:

- CR 603.4 / CR 608.2a's intervening "if" on a triggered ability
  (`machines/triggers.intervening_if_answer`);
- CR 602.1b's "Activate only if <condition>" instruction
  (`Game.why_cannot_activate`, `Game.activation_instruction_refusal`);
- a modal "If <condition>, choose N instead" (CR 700.2, `Game.condition_holds`).

This package is the shared fallback all three reach once their own built-in
shapes decline. A clause is read by the first `ConditionReader` whose pattern
matches it whole; failing that by `Game`'s built-in `_CONDITION_*` chain;
failing that as a compound of halves each read the same way.

**The contract.** A reader that claims a clause (its pattern matches) always
answers True or False - False when the context it needs is missing, for
instance a clause about the trigger event asked with no event at hand. Only a
clause nobody claims answers None, and None is the one answer every caller
turns into a fail-closed notice (`InterveningIfNotice`, an activation refused
"rather than allowed unchecked"). A reader must never raise.

**Where readers live.** One module per family, each exporting
`READERS: tuple[ConditionReader, ...]`: `timing` (whose turn, which phase or
step), `board` (what is on the battlefield), `cast_record` (how a spell was
cast), `activation` (what mana paid an *activated ability's* own cost,
`cast_record`'s twin for CR 602.2b), `history` (what happened this turn),
`player` (hands, graveyards, life), `objects` (the source and the event's own
subject) and `events` (a trigger event's own "while <doing something>"
qualifier). `READERS` below is read at call time, never cached, so each
family fills only its own module.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from magic_cards_model.text_norm import collapsed

if TYPE_CHECKING:
    from ...models.card_state import CardState
    from ...models.game import Game
    from ..abilities import ActivatedAbility, TriggeredAbility
    from ..triggers import GameEvent

__all__ = [
    "ConditionContext",
    "ConditionReader",
    "claims",
    "read_condition",
    "readers",
]


@dataclass(frozen=True)
class ConditionContext:
    """Everything a condition may be read against.

    `controller` is CR 109.5's "you": the player who activated the ability,
    the controller of a triggered ability's source when it triggered, or the
    player a condition is asked for. `source` is the object the condition is
    printed on; `event` the trigger event (CR 603.2) for an intervening "if",
    whose recheck on resolution (CR 608.2a) reads the same persisted event;
    `ability` the triggered or activated ability asking; `source_stamp` the
    source's zone-change stamp as the ability was created, for a recheck that
    reads the object the ability came from (CR 113.7a) after it has moved.
    """

    game: "Game"
    controller: str
    source: "CardState | None" = None
    event: "GameEvent | None" = None
    ability: "TriggeredAbility | ActivatedAbility | None" = None
    source_stamp: UUID | None = None


@dataclass(frozen=True)
class ConditionReader:
    """One template: `pattern` is matched against the whole clause (lowercase,
    trailing period and surrounding space stripped), and `read` answers it.

    `read` must return a bool for every clause `pattern` matches - it has
    claimed the clause - and must never raise.
    """

    pattern: re.Pattern[str]
    read: Callable[[ConditionContext, re.Match[str]], bool]


# The family modules import the contract above, so they are loaded only once it
# exists.
from . import (  # noqa: E402
    activation,
    board,
    cast_record,
    choice,
    events,
    history,
    objects,
    player,
    timing,
)


def readers() -> tuple[ConditionReader, ...]:
    """Every registered reader, family by family, read at call time."""
    return (
        *timing.READERS,
        *board.READERS,
        *cast_record.READERS,
        *choice.READERS,
        *activation.READERS,
        *history.READERS,
        *player.READERS,
        *objects.READERS,
        *events.READERS,
    )


def _normalized(text: str) -> str:
    return collapsed(text.strip().rstrip(".").strip()).lower()


def _claiming(text: str) -> tuple[ConditionReader, re.Match[str]] | None:
    for reader in readers():
        match = reader.pattern.fullmatch(text)
        if match is not None:
            return reader, match
    return None


def read_condition(context: ConditionContext, text: str) -> bool | None:
    """Whether `text` is true in `context`, or None when nothing claims it.

    Tried in order: a registered reader; `Game`'s own built-in chain
    (`Game.builtin_condition_holds`); and last the compound combinator, which
    reads "X and Y" as all of its halves and "X or Y" / "X or if Y" as any of
    them - but only when every half is itself read, each against this same
    context, so an anaphor in one half ("you cast it and there are ...")
    resolves to the same object it does in the other.
    """
    clause = _normalized(text)
    if not clause:
        return None
    claimed = _claiming(clause)
    if claimed is not None:
        reader, match = claimed
        return bool(reader.read(context, match))
    built_in = context.game.builtin_condition_holds(context.controller, clause, context.source)
    if built_in is not None:
        return built_in
    return _read_compound(context, clause)


def claims(text: str) -> bool:
    """Whether some reader recognises `text`'s shape - a text-only check, with
    no game in sight, for a parser deciding what it can gate on. A compound is
    claimed only when every half is."""
    clause = _normalized(text)
    if not clause:
        return False

    from ...models.game import builtin_condition_readable

    if _claiming(clause) is not None or builtin_condition_readable(clause):
        return True
    return any(claims(left) and claims(right) for _joiner, left, right in _binary_splits(clause))


#: The joiners a compound condition is printed with. "or if" is Gathering
#: Place's "Activate only if this land entered this turn or if you control a
#: basic land"; a leading comma is the serial form ("..., or ...").
_JOINER = re.compile(r",? (?P<joiner>and|or if|or) ")


def _binary_splits(clause: str) -> list[tuple[str, str, str]]:
    """Every way to cut `clause` once at a joiner, left to right, as
    `(joiner, left, right)` - "or if" normalised to "or"."""
    splits = []
    for match in _JOINER.finditer(clause):
        left = clause[: match.start()].strip()
        right = clause[match.end() :].strip()
        if left and right:
            joiner = "and" if match.group("joiner") == "and" else "or"
            splits.append((joiner, left, right))
    # A serial list's earlier commas ("A, B, and C" - Happily Ever After)
    # join with the list's closing joiner: cutting at one leaves "A" and
    # "B, and C", each read the same way in turn.
    closing = _SERIAL_CLOSING.search(clause)
    if closing is not None:
        joiner = "and" if closing.group("joiner") == "and" else "or"
        for match in _SERIAL_COMMA.finditer(clause, 0, closing.start()):
            left = clause[: match.start()].strip()
            right = clause[match.end() :].strip()
            if left and right:
                splits.append((joiner, left, right))
    return splits


#: A serial list's closing item: ", and C" / ", or C".
_SERIAL_CLOSING = re.compile(r", (?P<joiner>and|or) ")
#: A bare comma, the separator between a serial list's earlier items.
_SERIAL_COMMA = re.compile(r", (?!and |or )")


def _read_half(context: ConditionContext, half: str) -> bool | None:
    """One half of a compound, read by every reader the whole clause could have
    been: an intervening "if" half goes back through the triggered chain
    (`intervening_if_answer`, which itself ends in `read_condition`), anything
    else through `read_condition`."""
    from ..abilities import TriggeredAbility

    ability = context.ability
    if isinstance(ability, TriggeredAbility) and context.source is not None:
        from ..triggers import intervening_if_answer

        return intervening_if_answer(
            context.game,
            ability.model_copy(update={"intervening_if": half}),
            context.source,
            context.event,
            context.source_stamp,
        )
    return read_condition(context, half)


def _read_compound(context: ConditionContext, clause: str) -> bool | None:
    for joiner, left, right in _binary_splits(clause):
        left_answer = _read_half(context, left)
        if left_answer is None:
            continue
        right_answer = _read_half(context, right)
        if right_answer is None:
            continue
        if joiner == "and":
            return left_answer and right_answer
        return left_answer or right_answer
    return None
