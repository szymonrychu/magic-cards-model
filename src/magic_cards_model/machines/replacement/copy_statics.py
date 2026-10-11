"""Group enter-as-a-copy statics (CR 614.1c, 614.12, 707.2):

- "Creatures you control enter as a copy of this creature." (Essence of the
  Wild)
- "Nontoken creatures you control enter as a copy of enchanted creature."
  (Infinite Reflection)

A permanent's static replacement that rewrites how *other* permanents enter:
the copy effect is registered the same way a Clone's own is
(`enters._apply_copy_of`), but the copied object is fixed by the printed
phrase rather than chosen.
"""

import re

from ...models.card import Type
from ...models.card_state import CardState
from ...models.token import is_token
from .enters import _apply_copy_of
from .model import (
    CardReplacement,
    EventKind,
    ReplaceableEvent,
    ReplacementEffect,
    ReplacementKind,
)

_SUBJECT_RE = re.compile(r"^(?P<nontoken>nontoken )?creatures you control$", re.IGNORECASE)


def _compile_group_enters_as_copy(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.ENTERS_AS_COPY or effect.self_replacement:
        return None
    if effect.condition is not None or effect.optional or effect.tapped:
        return None
    if effect.copy_exception is not None or effect.copy_exception_unparsed is not None:
        return None
    subject = _SUBJECT_RE.match((effect.subject or "").strip())
    copy_of = (effect.copy_of or "").strip().lower()
    if subject is None or copy_of not in ("this creature", "enchanted creature"):
        return None
    nontoken = subject.group("nontoken") is not None

    def copied(game, source: CardState) -> CardState | None:
        if copy_of == "this creature":
            return source
        return next((c for c in game.battlefield if c.id == source.attached_to), None)

    def applies(game, source: CardState, event: ReplaceableEvent) -> bool:
        card = event.card
        if event.kind is not EventKind.ENTERS_BATTLEFIELD or card is None:
            return False
        if card.id == source.id or card.controller != source.controller:
            return False
        if Type.CREATURE not in card.types or (nontoken and is_token(card)):
            return False
        return copied(game, source) is not None

    def apply(game, source: CardState, event: ReplaceableEvent) -> None:
        target = copied(game, source)
        if event.card is not None and target is not None:
            _apply_copy_of(game, effect, source.name, source, event, event.card, target)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


COPY_COMPILERS = (_compile_group_enters_as_copy,)
