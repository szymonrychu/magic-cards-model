"""An optional additional cost another permanent grants to the spells its
controller casts, with the conditional reduction tied to having paid it
(CR 118.8b, CR 601.2f, CR 118.7a).

    Defiler of Faith - As an additional cost to cast white permanent spells,
    you may pay 2 life. Those spells cost {W} less to cast if you paid life
    this way. This effect reduces only the amount of white mana you pay.

CR 604.2: the sentence is a static ability of a permanent on the battlefield,
reaching out at somebody else's spell, so it is read off the computed board
(CR 613.5) each time a spell is announced. The final sentence turns off the
CR 118.7b spill of a coloured reduction into generic mana: a spell with no
such coloured symbol is simply not reduced, which `Casting.total_cost` applies
(`Casting.colored_only_reductions`).
"""

import re
from functools import lru_cache
from typing import Any

from pydantic import ConfigDict

from ...models.card import Color
from ...models.card_state import CardState
from ...snapshot import EngineModel

_GRANTED_LIFE_COST_RE = re.compile(
    r"^As an additional cost to cast (?P<quality>[a-z]+(?: [a-z]+)*) spells, "
    r"you may pay (?P<life>\d+) life\. "
    r"Those spells cost \{(?P<symbol>[WUBRG])\} less to cast if you paid life this way\. "
    r"This effect reduces only the amount of (?P<color>white|blue|black|red|green) mana you pay\.$",
    re.IGNORECASE,
)

_COLOR_BY_WORD = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


class GrantedLifeCost(EngineModel):
    """One `_GRANTED_LIFE_COST_RE` line, read, and the permanent that has it."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    quality: str
    life: int
    color: Color
    """The colour of the one mana the reduction takes off, and the only mana
    it can take it off."""


@lru_cache(maxsize=512)
def granted_life_cost_of_line(text: str) -> tuple[str, int, Color] | None:
    """`(spell quality, life, reduced colour)` for one static line of the
    granting shape, or None. Fails closed: a quality this engine cannot
    decide, or a reduction whose symbol is not the colour the last sentence
    names, leaves the whole line unread."""
    from ..next_spell import spell_quality_is_readable

    match = _GRANTED_LIFE_COST_RE.fullmatch(text.strip())
    if match is None:
        return None
    color = _COLOR_BY_WORD[match.group("color").lower()]
    if color.value != match.group("symbol").upper():
        return None
    quality = match.group("quality").lower()
    if not spell_quality_is_readable(quality):
        return None
    return quality, int(match.group("life")), color


def reads_granted_life_cost_line(text: str) -> bool:
    """What `support.py` asks before crediting the line."""
    return granted_life_cost_of_line(text) is not None


def granted_life_costs(game: Any, spell: CardState, caster: str) -> list[GrantedLifeCost]:
    """Every optional life cost `caster`'s permanents grant `spell` right
    now, one per granting permanent (each Defiler is its own optional cost,
    CR 118.8b)."""
    from ..next_spell import spell_has_quality

    if game is None:
        return []
    board = game.computed_board()
    found: list[GrantedLifeCost] = []
    for permanent in game.permanents_controlled_by(caster):
        for line in board.of(permanent).abilities:
            read = granted_life_cost_of_line(line)
            if read is None:
                continue
            quality, life, color = read
            if spell_has_quality(spell, quality):
                found.append(
                    GrantedLifeCost(
                        source_name=permanent.name, quality=quality, life=life, color=color
                    )
                )
    return found
