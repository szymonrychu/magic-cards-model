"""Equip, blocking and loyalty-ability statics (CR 301.5, 509.1, 606.3), read
live off computed ability lines (CR 613.5):

- "This Equipment can be attached only to a creature with toughness 4 or
  greater." (Gate Smasher; O-Naginata's power form) and "This creature can't be
  equipped." (Goblin Brawler): `attach_refusal`, asked when equip is announced
  and resolved and by the CR 704.5n state-based action.
- "Equip {0}. Activate only once each turn." (Leather Armor):
  `equip_once_each_turn`. "You may activate equip abilities any time you could
  cast an instant." (Leonin Shikari) is `keywords.equip_at_instant_speed`'s.
- "Tapped creatures you control can block as though they were untapped."
  (Masako the Humorless) and "This creature can block Dragons as though it had
  reach." (Dragon Hunter): `blocks_as_though_untapped`, `blocks_as_though_reach`.
- "You may activate the loyalty abilities of planeswalkers you control twice
  each turn rather than only once." (Oath of Teferi) and "Planeswalkers' loyalty
  abilities you activate cost an additional [+1] to activate." (Carth the
  Lion): `loyalty_activation_limit`, `additional_loyalty_cost`.
"""

import re
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..numbers import parse_count

if TYPE_CHECKING:
    from ..models.game import Game

_ATTACH_ONLY_RE = re.compile(
    r"^this equipment can be attached only to a creature with (?P<stat>power|toughness) "
    r"(?P<n>\d+) or (?P<cmp>greater|less)\.?$",
    re.IGNORECASE,
)
_CANT_BE_EQUIPPED_RE = re.compile(r"^(?:this [a-z]+|~) can't be equipped\.?$", re.IGNORECASE)
_EQUIP_ONCE_RE = re.compile(
    r"^(?:[^\u2014]+ \u2014 )?equip\b.*\bactivate only once each turn\.?$", re.IGNORECASE
)
_UNTAPPED_BLOCK_RE = re.compile(
    r"^tapped creatures you control can block as though they were untapped\.?$", re.IGNORECASE
)
_REACH_RE = re.compile(
    r"^(?:this [a-z]+|~) can block (?P<what>[a-z]+)s as though it had reach\.?$", re.IGNORECASE
)
_LOYALTY_LIMIT_RE = re.compile(
    r"^you may activate the loyalty abilities of planeswalkers you control "
    r"(?P<n>\w+) times? each turn rather than only once\.?$|"
    r"^you may activate the loyalty abilities of planeswalkers you control "
    r"(?P<word>twice|thrice) each turn rather than only once\.?$",
    re.IGNORECASE,
)
_LOYALTY_COST_RE = re.compile(
    r"^planeswalkers' loyalty abilities you activate cost an additional \[\+1\] to activate\.?$",
    re.IGNORECASE,
)
_PATTERNS = (
    _ATTACH_ONLY_RE,
    _CANT_BE_EQUIPPED_RE,
    _EQUIP_ONCE_RE,
    _UNTAPPED_BLOCK_RE,
    _REACH_RE,
    _LOYALTY_LIMIT_RE,
    _LOYALTY_COST_RE,
)
_TIMES = {"twice": 2, "thrice": 3}


def reads_equip_block_line(text: str) -> bool:
    from .keywords import is_instant_speed_equip_line

    line = " ".join(text.split())
    return any(pattern.match(line) for pattern in _PATTERNS) or is_instant_speed_equip_line(line)


def _lines(game: "Game", permanent: CardState) -> list[str]:
    from .triggers.collect import _computed_ability_lines

    return [" ".join(line.split()) for line in _computed_ability_lines(game, permanent)]


def _stat(game: "Game", host: CardState, stat: str) -> int:
    try:
        chars = game.characteristics_of(host)
        return chars.numeric_power if stat == "power" else chars.numeric_toughness
    except KeyError:
        return (host.power if stat == "power" else host.toughness) or 0


def attach_refusal(game: "Game", equipment: CardState, host: CardState | None) -> str | None:
    """Why `equipment` may not be attached to `host` by its own or the host's
    static line, or None (CR 301.5)."""
    if host is None:
        return None
    for line in _lines(game, equipment):
        match = _ATTACH_ONLY_RE.match(line)
        if match is None:
            continue
        value = _stat(game, host, match["stat"].lower())
        bound = int(match["n"])
        ok = value >= bound if match["cmp"].lower() == "greater" else value <= bound
        if not ok:
            return (
                f"{equipment.name} can be attached only to a creature with {match['stat'].lower()} "
                f"{bound} or {match['cmp'].lower()}, and {host.name} has {value} (CR 301.5)"
            )
    if any(_CANT_BE_EQUIPPED_RE.match(line) for line in _lines(game, host)):
        return f"{host.name} can't be equipped (CR 301.5)"
    return None


def equip_once_each_turn(equipment: CardState) -> bool:
    """Whether the Equipment prints "Equip ... Activate only once each turn."."""
    return any(
        _EQUIP_ONCE_RE.match(" ".join(line.split()))
        for line in (equipment.card.oracle_text or "").splitlines()
    )


def equip_activation_key(equipment: CardState) -> str:
    return f"{equipment.id}:equip"


def blocks_as_though_untapped(game: "Game", blocker: CardState) -> bool:
    controller = blocker.controller
    return any(
        _UNTAPPED_BLOCK_RE.match(line)
        for permanent in game.permanents_controlled_by(controller or "")
        for line in _lines(game, permanent)
    )


def blocks_as_though_reach(game: "Game", blocker: CardState, attacker: CardState) -> bool:
    try:
        subtypes = {s.lower() for s in game.characteristics_of(attacker).subtypes}
    except KeyError:
        subtypes = {s.lower() for s in attacker.subtypes}
    for line in _lines(game, blocker):
        match = _REACH_RE.match(line)
        if match and match["what"].lower() in subtypes:
            return True
    return False


def loyalty_activation_limit(game: "Game", player: str) -> int:
    limit = 1
    for permanent in game.permanents_controlled_by(player):
        for line in _lines(game, permanent):
            match = _LOYALTY_LIMIT_RE.match(line)
            if match is None:
                continue
            word = (match["word"] or match["n"]).lower()
            times = _TIMES.get(word) or parse_count(word, article=False) or 1
            limit = max(limit, times)
    return limit


def additional_loyalty_cost(game: "Game", player: str) -> int:
    """How many loyalty counters "cost an additional [+1]" statics add."""
    return sum(
        1
        for permanent in game.permanents_controlled_by(player)
        for line in _lines(game, permanent)
        if _LOYALTY_COST_RE.match(line)
    )
