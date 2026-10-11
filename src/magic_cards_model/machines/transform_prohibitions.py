"""Statics that stop permanents transforming: "Non-Human Werewolves you control
can't transform." (CR 701.27a, CR 701.28f).

The group is a creature subtype, optionally narrowed by a "non-<subtype>"
prefix, or the bare words "creatures" / "permanents". It is judged on the
permanent as it is now (CR 613.5), so a Human Werewolf front face still
transforms into its non-Human back face under such a static, and cannot
transform back.
"""

import re
from functools import cache
from typing import TYPE_CHECKING, NamedTuple

from ..data.subtypes import canonical_subtype
from ..models.card_state import CardState

if TYPE_CHECKING:
    from ..models.game import Game

_CANT_TRANSFORM_RE = re.compile(
    r"^(?:non-?(?P<excluded>[A-Za-z]+) )?(?P<word>[A-Za-z]+) you control can'?t transform\.?$",
    re.IGNORECASE,
)


class _Group(NamedTuple):
    subtype: str | None  # None: every creature or permanent
    excluded: str | None  # "Non-Human": a subtype the members must not have


@cache
def _parse(line: str) -> _Group | None:
    if "transform" not in line.lower():
        return None
    match = _CANT_TRANSFORM_RE.fullmatch(line.strip().replace("’", "'"))
    if match is None:
        return None
    word, excluded = match.group("word"), match.group("excluded")
    if word.lower() in {"creatures", "permanents"}:
        return _Group(None, None) if excluded is None else None
    subtype = canonical_subtype(word)
    if subtype is None:
        return None
    if excluded is None:
        return _Group(subtype, None)
    excluded_subtype = canonical_subtype(excluded)
    return None if excluded_subtype is None else _Group(subtype, excluded_subtype)


def reads_cant_transform_line(line: str) -> bool:
    return _parse(line) is not None


def transform_is_prevented(game: "Game", permanent: CardState) -> bool:
    """Whether a static on the battlefield says `permanent` can't transform."""
    controller = game.controller_of(permanent).username
    subtypes: set[str] | None = None
    for source in game.battlefield:
        if game.controller_of(source).username != controller:
            continue
        for line in game.characteristics_of(source).abilities:
            group = _parse(line)
            if group is None:
                continue
            if subtypes is None:
                subtypes = {kind.lower() for kind in game.characteristics_of(permanent).subtypes}
            if group.subtype is not None and group.subtype not in subtypes:
                continue
            if group.excluded is not None and group.excluded in subtypes:
                continue
            return True
    return False
