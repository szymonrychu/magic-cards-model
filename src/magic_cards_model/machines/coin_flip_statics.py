"""Statics that fix the result of a coin flip (CR 705.3).

"The first time you flip one or more coins each turn, those coins come up
heads and you win those flips." (Two-Headed Coin). CR 705.3: "ignore the
actual results of that flip and use the indicated results instead".
"""

import re
from functools import cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.game import Game

_FIRST_FLIP_HEADS_RE = re.compile(
    r"^(?:[^—]+ — )?the first time you flip one or more coins each turn, "
    r"those coins come up heads and you win those flips\.?$",
    re.IGNORECASE,
)

#: `Game.turn_facts` key: the player has flipped coins this turn.
FLIPPED_COINS = "flipped_coins"


@cache
def reads_first_flip_heads_line(text: str) -> bool:
    return "coins come up heads" in text.lower() and bool(
        _FIRST_FLIP_HEADS_RE.fullmatch(text.strip())
    )


def first_flip_is_forced_heads(game: "Game", flipper: str) -> bool:
    """Whether this flip is `flipper`'s first this turn and a permanent they
    control says it comes up heads; the flip is recorded either way."""
    first = flipper not in game.turn_facts.get(FLIPPED_COINS, ())
    game.record_turn_fact(FLIPPED_COINS, flipper)
    if not first:
        return False
    return any(
        reads_first_flip_heads_line(line)
        for permanent in game.permanents_controlled_by(flipper)
        for line in game.characteristics_of(permanent).abilities
    )
