"""Statics that open hidden information to other players, read live off the
computed ability lines of the battlefield (CR 613.5):

- "Players play with their hands revealed." (Zur's Weirding) and "Your
  opponents play with their hands revealed." (Telepathy): the hand is revealed
  to every player (CR 701.20a), read by `Game.hand_is_revealed`.
- "Players play with the top card of their libraries revealed." (Lantern of
  Insight, Wizened Snitches): CR 400.2's public top card, read by
  `Game.reveals_top_card`.
- "You may look at face-down creatures your opponents control any time."
  (Found Footage; Keeper of the Lens: "... you don't control ..."): the
  viewer knows those cards (`Game.known_to`).
- "You may look at an additional two cards each time you surveil." (Enhanced
  Surveillance): `additional_looks`, added to the cards `Game.surveil` shows.
"""

import re
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..numbers import parse_count

if TYPE_CHECKING:
    from ..models.game import Game

_ALL_HANDS = "players play with their hands revealed"
_OPPONENT_HANDS = "your opponents play with their hands revealed"
_ALL_TOPS = "players play with the top card of their libraries revealed"
_FACE_DOWN_RE = re.compile(
    r"^you may look at face-down creatures (?:your opponents control|you don't control) "
    r"any time\.?$",
    re.IGNORECASE,
)
_ADDITIONAL_RE = re.compile(
    r"^you may look at an additional (?P<n>\w+) cards? each time you (?P<verb>surveil|scry)\.?$",
    re.IGNORECASE,
)


def _normal(line: str) -> str:
    return " ".join(line.split()).rstrip(".").lower()


def reads_revealed_information_line(text: str) -> bool:
    line = _normal(text)
    return (
        line in (_ALL_HANDS, _OPPONENT_HANDS, _ALL_TOPS)
        or _FACE_DOWN_RE.match(" ".join(text.split())) is not None
        or _ADDITIONAL_RE.match(" ".join(text.split())) is not None
    )


def _held_lines(game: "Game", needle: str):
    """(permanent, normalised line) for each battlefield line containing `needle`."""
    from .triggers.collect import _computed_ability_lines

    for permanent in game.battlefield:
        for line in _computed_ability_lines(game, permanent):
            if needle in line.lower():
                yield permanent, _normal(line)


def hand_revealed_by_others(game: "Game", owner: str) -> bool:
    """Whether a permanent anyone controls reveals `owner`'s hand."""
    for permanent, line in _held_lines(game, "hands revealed"):
        if line == _ALL_HANDS or (line == _OPPONENT_HANDS and permanent.controller != owner):
            return True
    return False


def top_card_revealed_by_others(game: "Game") -> bool:
    return any(line == _ALL_TOPS for _, line in _held_lines(game, "libraries revealed"))


def face_down_visible_to(game: "Game", viewer: str) -> list[CardState]:
    """Face-down creatures `viewer` may look at any time."""
    if not any(
        permanent.controller == viewer and _FACE_DOWN_RE.match(line + ".")
        for permanent, line in _held_lines(game, "face-down creatures")
    ):
        return []
    return [
        state
        for state in game.battlefield
        if state.face_down_characteristics is not None and state.controller != viewer
    ]


def additional_looks(game: "Game", player: str, verb: str) -> int:
    """How many extra cards `player` looks at each time they `verb`."""
    total = 0
    for permanent, line in _held_lines(game, "an additional"):
        match = _ADDITIONAL_RE.match(line + ".")
        if match and match["verb"].lower() == verb and permanent.controller == player:
            total += parse_count(match["n"], article=False) or 0
    return total
