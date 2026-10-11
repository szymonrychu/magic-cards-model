"""Statics about the abilities of cards in graveyards.

- "Cards in graveyards lose all abilities." (CR 613.1f, CR 113.6b): the
  graveyard-functioning abilities of a card - flashback and the other graveyard
  cast keywords (CR 702.34a), unearth (CR 702.84a), dredge (CR 702.52a) - stop
  existing. Judged from the battlefield, whoever controls the static.
- "Each artifact card in your graveyard has unearth {1}{B}{R}." (CR 702.84a,
  CR 613.1f): each card of that type in the static controller's graveyard
  gains an unearth ability. A Jailer-style removal wins over a grant here.
"""

import re
from functools import cache
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game
    from .abilities import KeywordAbility

_LOSE_ALL_RE = re.compile(r"^cards in graveyards lose all abilities\.?$", re.IGNORECASE)
_GRANT_UNEARTH_RE = re.compile(
    r"^each (?P<kind>[a-z]+) card in your graveyard has unearth (?P<cost>(?:\{[^}]+\})+)\.?$",
    re.IGNORECASE,
)


_REMINDER_RE = re.compile(r"\s*\([^)]*\)\s*$")


class _UnearthGrant(NamedTuple):
    card_type: str
    cost: str


@cache
def _grant(line: str) -> _UnearthGrant | None:
    match = _GRANT_UNEARTH_RE.fullmatch(_REMINDER_RE.sub("", line).strip())
    return None if match is None else _UnearthGrant(match["kind"].lower(), match["cost"])


def reads_graveyard_ability_line(line: str) -> bool:
    return _LOSE_ALL_RE.fullmatch(line.strip()) is not None or _grant(line) is not None


def graveyard_abilities_lost_by(game: "Game") -> str | None:
    """The name of a permanent whose static strips every graveyard card of its
    abilities, or None."""
    for source in game.battlefield:
        for line in game.characteristics_of(source).abilities:
            if _LOSE_ALL_RE.fullmatch(line.strip()):
                return source.name
    return None


def granted_unearth_abilities(game: "Game", card: "CardState") -> "list[KeywordAbility]":
    """The unearth abilities the battlefield gives `card` while it is in a
    graveyard."""
    from .abilities import keyword_abilities_in_lines

    owner = game._graveyard_owner_of(card)  # noqa: SLF001
    if owner is None:
        return []
    types = None
    granted: list[KeywordAbility] = []
    for source in game.battlefield:
        if game.controller_of(source).username != owner:
            continue
        for line in game.characteristics_of(source).abilities:
            grant = _grant(line)
            if grant is None:
                continue
            if types is None:
                types = {str(kind).lower() for kind in game.characteristics_of(card).types}
            if grant.card_type in types:
                granted.extend(keyword_abilities_in_lines([f"Unearth {grant.cost}"], ["Unearth"]))
    return granted
