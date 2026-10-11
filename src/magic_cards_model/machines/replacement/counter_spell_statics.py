"""Counter-a-spell replacement statics (CR 701.6a, 614.1a, 608.2g):

"If a spell or ability you control would counter a spell, instead exile that
spell and you may play that card without paying its mana cost." (Guile)

`Game.counter` raises `EventKind.COUNTER_SPELL` for a spell about to be
countered; the effect redirects it to exile and names who may play it free.
"""

import re

from ...models.card_state import CardState
from ...models.zone import Zone
from .model import (
    CardReplacement,
    EventKind,
    ReplaceableEvent,
    ReplacementEffect,
    ReplacementKind,
)

_EVENT_RE = re.compile(r"^a spell or ability you control would counter a spell$", re.IGNORECASE)
_REPLACEMENT_RE = re.compile(
    r"^exile that spell and you may play that card without paying its mana cost$",
    re.IGNORECASE,
)


def _compile_counter_exiles_and_plays_free(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD or effect.condition is not None:
        return None
    if _EVENT_RE.match((effect.event or "").strip()) is None:
        return None
    if _REPLACEMENT_RE.match((effect.replacement or "").strip().rstrip(".")) is None:
        return None

    def applies(game, source: CardState, event: ReplaceableEvent) -> bool:
        return (
            event.kind is EventKind.COUNTER_SPELL
            and event.destination is Zone.GRAVEYARD
            and event.cause_controller == source.controller
        )

    def apply(game, source: CardState, event: ReplaceableEvent) -> None:
        event.destination = Zone.EXILE
        event.free_play_player = source.controller
        event.free_play_source = source.name

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


COUNTER_SPELL_COMPILERS = (_compile_counter_exiles_and_plays_free,)
