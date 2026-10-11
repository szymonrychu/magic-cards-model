"""Discard replacement statics (CR 701.9a, CR 614.1a): "If a spell or ability an
opponent controls causes you to discard this card, put it onto the battlefield
instead of putting it into your graveyard."

The discard is the ordinary `keywords.discard` move into a graveyard, raised as
a zone change while `Game` marks a discard in progress. This replacement is the
card's own (`anywhere`: it works from the hand) and applies when the object
resolving is a spell or ability controlled by an opponent of the discarding
player - a cost, a cleanup discard or the player's own effect never qualifies.
"""

import re
from typing import TYPE_CHECKING

from ...models.card_state import CardState
from ...models.zone import Zone
from .model import (
    CardReplacement,
    EventKind,
    ReplaceableEvent,
    ReplacementEffect,
    ReplacementKind,
)
from .parse import _is_opponent, _owner_username

if TYPE_CHECKING:
    from ...models.game import Game

_CAUSE_RE = re.compile(
    r"^a spell or ability an opponent controls causes you to discard "
    r"(?:this (?:card|creature|permanent|spell))$",
    re.IGNORECASE,
)
_INSTEAD_RE = re.compile(
    r"^put it onto the battlefield$",
    re.IGNORECASE,
)


def _compile_discard_onto_battlefield(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.INSTEAD_OF:
        return None
    if not _CAUSE_RE.fullmatch((effect.condition or "").strip()):
        return None
    if not _INSTEAD_RE.fullmatch((effect.replacement or "").strip()):
        return None
    if (effect.event or "").strip().lower() != "putting it into your graveyard":
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if event.kind is not EventKind.ZONE_CHANGE or event.card is not source:
            return False
        if event.origin is not Zone.HAND or event.destination is not Zone.GRAVEYARD:
            return False
        if not game._discarding:  # noqa: SLF001
            return False
        resolving = game.resolving
        return resolving is not None and _is_opponent(
            game, resolving.controller, _owner_username(game, source)
        )

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.destination = Zone.BATTLEFIELD

    return CardReplacement(label=effect.text, applies=applies, apply=apply, anywhere=True)


DISCARD_COMPILERS = (_compile_discard_onto_battlefield,)
