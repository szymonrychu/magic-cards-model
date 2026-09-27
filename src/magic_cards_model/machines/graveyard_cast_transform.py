"""A spell that, cast from a graveyard, turns itself into its own back face.

"`<instructions>`. If this spell was cast from a graveyard, exile it, then put
it onto the battlefield transformed under its owner's control[ with a
`<kind>` counter on it]." - Esper Origins // Summon: Esper Maduin, whose
flashback (CR 702.34a) is what casts it from a graveyard.

The leading instructions are read by the ordinary spell parser. The rider
asks `Game.cast_record(spell).origin_zone` - CR 601.2's cast record, a copy
never counting as cast from anywhere - and, when it holds, the resolving spell
exiles itself (CR 701.13a) and CR 712.14a's "transformed" puts the back face
onto the battlefield under its owner's control. CR 608.2n's graveyard step
then finds no spell left (`Game._resolve_top`'s own zone check). The counter
is put on as it arrives, the same way every "return ... with a finality
counter on it" reader here does it (CR 122.1h's finality counter then exiles
it instead of letting it reach a graveyard).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models.zone import Zone

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game
    from .effects import Effect

_CAST_FROM_GRAVEYARD_TRANSFORM_RE = re.compile(
    r"^(?P<head>.+?\.)\s*if this spell was cast from a graveyard, exile it, then put it "
    r"onto the battlefield transformed under (?:its owner's|your) control"
    r"(?: with an? (?P<kind>[a-z0-9+/\-]+) counter on it)?\.?$",
    re.IGNORECASE | re.DOTALL,
)


def parse_cast_from_graveyard_transform_clause(text: str) -> Effect | None:
    """`_CAST_FROM_GRAVEYARD_TRANSFORM_RE`'s spell effect, or `None` when the
    text is another shape or its leading instructions are unreadable."""
    from .effects import _counter_kind, parse_mixed_effect_for_spell
    from .replacement import strip_reminder_text

    rules_text, _ = strip_reminder_text(text)
    match = _CAST_FROM_GRAVEYARD_TRANSFORM_RE.fullmatch(" ".join(rules_text.split()))
    if match is None:
        return None
    head = parse_mixed_effect_for_spell(match.group("head").strip())
    if head is None:
        return None
    kind = _counter_kind(match.group("kind")) if match.group("kind") else None

    def effect(game: Game, spell: CardState) -> None:
        head(game, spell)
        record = game.cast_record(spell)
        if record.is_copy or record.origin_zone is not Zone.GRAVEYARD:
            return
        if spell.card.back_face is None:
            return  # CR 712.14a: a card with no back face stays where it is.
        game.exile_cards([spell])
        if spell.zone is not Zone.EXILE:
            return
        owner = spell.owner or game.controller_of(spell).username
        permanent = game.put_onto_battlefield(spell, owner, transformed=True)
        if kind is not None and permanent.zone is Zone.BATTLEFIELD:
            game.add_counters(permanent, kind, 1)

    return effect
