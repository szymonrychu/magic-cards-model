"""Cleave (CR 702.148): an alternative cost and a text-changing effect.

CR 702.148a: "'Cleave [cost]' means 'You may cast this spell by paying [cost]
rather than paying its mana cost' and 'If this spell's cleave cost was paid,
change its text by removing all text found within square brackets in the
spell's rules text.'" The first half is a cast option
(`casting.options._option_from_keyword`); this module is the second half,
CR 702.148b's text-changing effect, read where a spell's text is resolved and
where the support audit reads a spell's two possible texts.
"""

import re
from typing import TYPE_CHECKING

from .abilities import keyword_abilities

if TYPE_CHECKING:
    from ..models.card import Card
    from ..models.card_state import CardState
    from ..models.game import Game

_BRACKETED = re.compile(r"[ \t]*\[[^\[\]]*\]")

#: A bracketed sentence that defines X ("[X is the number of creatures you
#: control.]", Lantern Flare): uncleaved, it is the spell's own definition of X
#: (CR 107.3f), the same thing the "..., where X is ..." template says.
_BRACKETED_X_DEFINITION = re.compile(r"\.\s*\[(X is [^\[\]]+?)\.?\]")


def cleaved_text(text: str) -> str:
    """`text` with every bracketed span removed (the cleave cost was paid)."""
    return _BRACKETED.sub("", text).replace(" \n", "\n").strip()


def uncleaved_text(text: str) -> str:
    """`text` as it reads when the spell was not cleaved: the bracketed words
    are ordinary text and only the brackets themselves go."""
    text = _BRACKETED_X_DEFINITION.sub(r", where \1.", text)
    return text.replace("[", "").replace("]", "")


def has_cleave(card: "Card") -> bool:
    return any(ability.canonical.lower() == "cleave" for ability in keyword_abilities(card))


def cleave_cost_announces_x(card: "Card") -> bool:
    """Whether the cleave cost carries CR 107.3a's `{X}` (Lantern Flare)."""
    return any(
        ability.canonical.lower() == "cleave" and "{X}" in (ability.cost or "")
        for ability in keyword_abilities(card)
    )


def was_cleaved(game: "Game", spell: "CardState") -> bool:
    """Whether this spell was cast for its cleave cost."""
    if not has_cleave(spell.card):
        return False
    record = game.cast_record(spell)
    return (record.keyword or "").lower() == "cleave" and record.keyword_cost_paid


def spell_text_as_cast(game: "Game", spell: "CardState", text: str) -> str:
    """The resolving text of a spell, bracket-aware (CR 702.148a)."""
    if "[" not in text or not has_cleave(spell.card):
        return text
    return cleaved_text(text) if was_cleaved(game, spell) else uncleaved_text(text)
