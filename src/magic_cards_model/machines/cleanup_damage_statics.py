"""Statics that change what the cleanup step does to a permanent (CR 514.2).

"Damage isn't removed from [this creature] during cleanup steps." - the
permanent keeps the damage marked on it when CR 514.2's simultaneous removal
happens, so the damage stays until it leaves the battlefield (CR 400.7) or is
otherwise removed (healing, regeneration is not damage removal).
"""

import re
from functools import cache
from typing import TYPE_CHECKING

from ..models.card_state import CardState

if TYPE_CHECKING:
    from ..models.game import Game

_DAMAGE_KEPT_RE = re.compile(
    r"^damage isn'?t removed from (?:this|that) (?:creature|permanent|artifact|"
    r"enchantment|land|planeswalker|battle) during cleanup steps\.?$",
    re.IGNORECASE,
)


@cache
def reads_damage_kept_through_cleanup_line(text: str) -> bool:
    return "cleanup steps" in text.lower() and _DAMAGE_KEPT_RE.fullmatch(text.strip()) is not None


def damage_survives_cleanup(game: "Game", permanent: CardState) -> bool:
    """Whether `permanent` has the static above (CR 514.2 skips its damage)."""
    return any(
        reads_damage_kept_through_cleanup_line(line)
        for line in game.characteristics_of(permanent).abilities
    )
