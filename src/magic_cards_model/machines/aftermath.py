"""Aftermath (CR 702.127a): the graveyard half of a split card (CR 709).

CR 702.127a: "Aftermath is an ability found on some split cards (see rule 709,
"Split Cards"). It represents three static abilities. "Aftermath" means "You
may cast this half of this split card from your graveyard," "This half of this
split card can't be cast from any zone other than a graveyard," and "If this
spell was cast from a graveyard, exile it instead of putting it anywhere else
any time it would leave the stack.""

The three abilities, and where each is performed:

- **"You may cast this half ... from your graveyard"** - CR 601.3's
  permission, a `KeywordCastOption` (`aftermath_cast_option`) that
  `casting.keyword_cast_options` lists like flashback's. It covers the
  aftermath half alone (`KeywordCastOption.face_only`): the other half of the
  card has no permission to be cast from the graveyard (CR 709.3a: "Only the
  chosen half is evaluated to see if it can be cast").
- **"This half ... can't be cast from any zone other than a graveyard"** -
  `aftermath_face_refusal`, asked per half by `Casting` (CR 709.3a) and by
  `legal_actions`, so a permission from anywhere else (a hand, an exile
  grant) never reaches that half.
- **"exile it instead of putting it anywhere else any time it would leave the
  stack"** - `exiles_on_leaving_the_stack`, read by `machines/replacement`'s
  stack replacements (CR 604.5: a static ability of the spell itself) for a
  spell whose chosen half has aftermath and whose `CastRecord.origin_zone` is
  a graveyard. "Any time" covers a countered spell as well as a resolved one.

Nothing here keys on a card name: the half carrying the keyword is found by
its own printed "Aftermath" keyword line (CR 702.127a's "ability found on some
split cards").
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models.card import Card, CardFace, Layout
from ..models.zone import Zone

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from .casting.options import KeywordCastOption

#: The keyword line that opens the aftermath half's text box, with or without
#: its CR 207.2a reminder text.
_AFTERMATH_LINE_RE = re.compile(r"^aftermath(?:\s*\(.*\))?\s*$", re.IGNORECASE)

RULE = "CR 702.127a"


def aftermath_face(card: Card) -> CardFace | None:
    """The half of this split card that has aftermath, or None."""
    if card.layout is not Layout.SPLIT:
        return None
    for face in card.card_faces or []:
        first = (face.oracle_text or "").split("\n", 1)[0].strip()
        if _AFTERMATH_LINE_RE.fullmatch(first):
            return face
    return None


def aftermath_cast_option(card: Card) -> KeywordCastOption | None:
    """CR 702.127a's first ability as a cast option: the aftermath half, from
    the graveyard, for its own mana cost (no alternative cost is named)."""
    face = aftermath_face(card)
    if face is None:
        return None
    from .casting.options import KeywordCastOption

    return KeywordCastOption(
        keyword="Aftermath",
        rule=RULE,
        zone=Zone.GRAVEYARD,
        pays_mana_cost=True,
        face_only=face.name,
    )


def aftermath_face_refusal(card: Card, face: str | None, zone: Zone) -> str | None:
    """CR 702.127a's second ability: why `face` of `card` can't be cast from
    `zone`, or None. Only the aftermath half is restricted."""
    half = aftermath_face(card)
    if half is None or face != half.name or zone is Zone.GRAVEYARD:
        return None
    return (
        f"{half.name} has aftermath and can't be cast from any zone other than a "
        f"graveyard, not from the {zone.value} ({RULE})"
    )


def aftermath_face_only_refusal(card_name: str, required: str, face: str | None) -> str:
    """The refusal for a cast that claimed the aftermath permission but named
    another half (or none) - CR 702.127a gives that permission to one half."""
    named = face or "no half"
    return (
        f"{card_name} may be cast from the graveyard with aftermath only as {required}, "
        f"not as {named} ({RULE}, CR 709.3a)"
    )


def exiles_on_leaving_the_stack(spell: CardState, origin_zone: Zone, face: str | None) -> bool:
    """CR 702.127a's third ability: whether this spell - cast as `face` from
    `origin_zone` - is exiled instead of going anywhere else as it leaves the
    stack."""
    half = aftermath_face(spell.card)
    return half is not None and face == half.name and origin_zone is Zone.GRAVEYARD
