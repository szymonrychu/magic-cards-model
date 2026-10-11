"""Untap-step statics that make a player choose what may untap (CR 502.3).

Storage Matrix: "As long as this artifact is untapped, each player chooses
artifact, creature, or land during their untap step. That player can untap only
permanents of the chosen type this step." CR 502.3: the active player determines
which permanents untap, and effects can keep some from untapping; this is such an
effect, asked once per untapped Storage Matrix on the battlefield, read off the
computed board (CR 613.5) at the start of the step (CR 611.3a: not locked in).

CR 502.3 and CR 604.2 verified with `mise run rules:find`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from .decisions import Decision, DecisionKind

if TYPE_CHECKING:
    from ..models.game import Game

#: The condition and choice of the line, and the restriction sentence after it.
_UNTAP_CHOICE_RE = re.compile(
    r"^as long as (?P<self>[^,]+?) is untapped, each player chooses (?P<types>[^.]+?) "
    r"during their untap step\. that player can untap only permanents of the chosen type "
    r"this step\.?$",
    re.IGNORECASE,
)


def untap_choice_types(line: str) -> tuple[str, ...] | None:
    """The types an untap-step choice line offers ("artifact, creature, or
    land"), or None when `line` is not that line."""
    match = _UNTAP_CHOICE_RE.fullmatch(" ".join(line.split()))
    if match is None:
        return None
    types = tuple(
        word.strip().lower()
        for word in re.split(r",\s*(?:or\s+)?|\s+or\s+", match["types"])
        if word.strip()
    )
    return types or None


def is_untap_choice_line(line: str) -> bool:
    """Whether a static line is Storage Matrix's - what the static audit counts."""
    return untap_choice_types(line) is not None


def untap_type_restrictions(
    game: Game, username: str, permanents: list[CardState]
) -> list[CardState]:
    """`permanents` (what `username`'s untap step would untap) narrowed by every
    untapped permanent whose computed text makes the player choose a type."""
    board = game.computed_board()
    remaining = list(permanents)
    for source in list(game.battlefield):
        if source.tapped:
            continue
        for line in board.of(source).abilities:
            types = untap_choice_types(line)
            if types is None:
                continue
            chosen = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_QUALITY,
                    player=username,
                    prompt=f"choose {', '.join(types)}: only permanents of that type untap",
                    source=source.name,
                    source_id=str(source.id),
                    options=types,
                    quality="card type",
                )
            )
            remaining = [
                permanent
                for permanent in remaining
                if str(chosen).lower()
                in {each.value.lower() for each in game.characteristics_of(permanent).types}
            ]
    return remaining
