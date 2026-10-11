"""Static abilities that change the rules of the game rather than an object
(CR 611.1's third category, "affects players or the rules of the game").

None of these changes a characteristic, so none is a layer effect (CR 613.11:
they "are applied after all other continuous effects have been applied").
Each is read here off one printed line and asked where the rule it changes
is applied - never applied in advance:

- the legend rule (CR 704.5j) switched off for everyone ("The "legend rule"
  doesn't apply.", Mirror Gallery) or for one subtype a player controls
  ("... doesn't apply to Spiders you control.", Spider-Verse) -
  `Game._legend_rule_losers`;
- Abyssal Persecutor's reversed "You can't win the game and your opponents
  can't lose the game." (CR 101.2 over CR 104.2b/104.3) -
  `Game._game_outcome_prohibition`;
- "You don't lose the game for having 0 or less life." (Phyrexian Unlife,
  and the second half of Marina Vendrell's Grimoire's compound line) - CR
  704.5a alone is switched off, in `Game._losing_players`;
- "As long as you have 0 or less life, all damage is dealt to you as though
  its source had infect." (Phyrexian Unlife) - CR 702.90b's result, in the
  damage event;
- "Your life total can't change." (Platinum Emperion) - CR 119.7 and CR
  119.8 at once: no life is gained or lost and no life can be paid;
- "You can't get poison counters." and "Creatures you control can't have
  -1/-1 counters put on them." (Melira, Sylvok Outcast) - CR 101.2 at the
  one choke point for each (`Game.add_player_counters`, `Game.add_counters`);
- "Creatures your opponents control lose infect." (Melira) - this one IS a
  layer 6 effect (CR 613.1f), built by `opponents_lose_keyword_builder`.

Every reader is a pure `str -> result` function, memoised, behind a cheap
literal gate, so `support.py`'s audit (`static_audit/game_rules_untap.py`)
can ask the same reader the game does.
"""

from __future__ import annotations

import re
from functools import cache
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game


_REMINDER_RE = re.compile(r"\s*\([^)]*\)")


def _norm(line: str) -> str:
    """One line with its reminder text (CR 207.2a) dropped and its quotes and
    whitespace made plain."""
    line = _REMINDER_RE.sub("", line)
    return " ".join(line.replace("’", "'").replace("“", '"').replace("”", '"').split())


# -- the legend rule (CR 704.5j) ---------------------------------------------


class LegendRuleExemption(NamedTuple):
    """`everyone`: the legend rule doesn't apply at all (Mirror Gallery).
    Otherwise `subtype`: it doesn't apply to permanents of that subtype the
    source's controller controls (Spider-Verse's Spiders)."""

    everyone: bool
    subtype: str | None


_LEGEND_RULE_RE = re.compile(
    r"^the \"legend rule\" doesn't apply(?: to (?P<quality>[a-z][a-z' -]*?)s you control)?\.?$",
    re.IGNORECASE,
)


@cache
def legend_rule_exemption_of_line(line: str) -> LegendRuleExemption | None:
    """The legend-rule exemption one static line states, or None. "...
    permanents you control" (Mirror Box) is `LEGEND_RULE_EXEMPT_TEXT`'s own
    layer grant and is not read twice here."""
    if "legend rule" not in line.lower():
        return None
    match = _LEGEND_RULE_RE.fullmatch(_norm(line))
    if match is None:
        return None
    quality = match.group("quality")
    if quality is None:
        return LegendRuleExemption(everyone=True, subtype=None)
    from ..data.creature_types import creature_types

    subtype = quality.strip().title()
    if subtype not in creature_types():
        return None
    return LegendRuleExemption(everyone=False, subtype=subtype)


def legend_rule_exemptions(game: Game, board: Any) -> tuple[bool, dict[str, set[str]]]:
    """(whether the legend rule is off for everyone, each player's exempt
    subtypes), read off the computed board (CR 604.2, CR 613.1f)."""
    everyone = False
    by_player: dict[str, set[str]] = {}
    for state in game.battlefield:
        chars = board.of(state)
        for line in chars.abilities:
            exemption = legend_rule_exemption_of_line(line)
            if exemption is None:
                continue
            if exemption.everyone:
                everyone = True
            elif chars.controller is not None and exemption.subtype is not None:
                by_player.setdefault(chars.controller, set()).add(exemption.subtype)
    return everyone, by_player


# -- winning and losing (CR 101.2, CR 104.3, CR 704.5a) -----------------------


class ReversedOutcomeProhibition(NamedTuple):
    """Abyssal Persecutor's "You can't win the game and your opponents can't
    lose the game." - the mirror of `GameOutcomeProhibition`'s halves."""

    you_cant_win: bool
    opponents_cant_lose: bool


_YOU_CANT_WIN = "you can't win the game"
_OPPONENTS_CANT_LOSE = "your opponents can't lose the game"
_REVERSED_RE = re.compile(
    rf"^(?P<first>{_YOU_CANT_WIN}|{_OPPONENTS_CANT_LOSE})"
    rf"(?: and (?P<second>{_YOU_CANT_WIN}|{_OPPONENTS_CANT_LOSE}))?\.?$",
    re.IGNORECASE,
)


@cache
def reversed_outcome_prohibition_of_line(line: str) -> ReversedOutcomeProhibition | None:
    if "the game" not in line:
        return None
    match = _REVERSED_RE.fullmatch(_norm(line))
    if match is None:
        return None
    halves = [match.group("first").lower()]
    if match.group("second") is not None:
        halves.append(match.group("second").lower())
    if len(set(halves)) != len(halves):
        return None
    return ReversedOutcomeProhibition(
        you_cant_win=_YOU_CANT_WIN in halves, opponents_cant_lose=_OPPONENTS_CANT_LOSE in halves
    )


_NO_ZERO_LIFE_LOSS = "don't lose the game for having 0 or less life"
_NO_ZERO_LIFE_LOSS_RE = re.compile(
    rf"^you (?:have no maximum hand size and )?{_NO_ZERO_LIFE_LOSS}\.?$", re.IGNORECASE
)


@cache
def ignores_zero_life_loss_line(line: str) -> bool:
    """ "You don't lose the game for having 0 or less life." (Phyrexian
    Unlife), alone or as the second half of Marina Vendrell's Grimoire's
    "You have no maximum hand size and don't lose the game for having 0 or
    less life." (whose first half `models/player.py` reads)."""
    if "0 or less life" not in line:
        return False
    return _NO_ZERO_LIFE_LOSS_RE.fullmatch(_norm(line)) is not None


_DAMAGE_AS_INFECT_RE = re.compile(
    r"^as long as you have 0 or less life, all damage is dealt to you as though "
    r"its source had infect\.?$",
    re.IGNORECASE,
)


@cache
def damage_as_infect_at_zero_life_line(line: str) -> bool:
    if "infect" not in line:
        return False
    return _DAMAGE_AS_INFECT_RE.fullmatch(_norm(line)) is not None


# -- life totals (CR 119.7, CR 119.8) -----------------------------------------

_LIFE_CANT_CHANGE_RE = re.compile(r"^your life total can't change\.?$", re.IGNORECASE)


@cache
def life_total_cant_change_line(line: str) -> bool:
    if "life total" not in line:
        return False
    return _LIFE_CANT_CHANGE_RE.fullmatch(_norm(line)) is not None


# -- counters (CR 101.2, CR 122.1) --------------------------------------------

_CANT_GET_POISON_RE = re.compile(r"^you can't get poison counters\.?$", re.IGNORECASE)


@cache
def cant_get_poison_line(line: str) -> bool:
    if "poison" not in line:
        return False
    return _CANT_GET_POISON_RE.fullmatch(_norm(line)) is not None


_CREATURES_CANT_HAVE_COUNTERS_RE = re.compile(
    r"^creatures you control can't have (?P<kind>[+-]\d+/[+-]\d+) counters put on them\.?$",
    re.IGNORECASE,
)


@cache
def controlled_creatures_counter_prohibition(line: str) -> str | None:
    """The counter kind "Creatures you control can't have <kind> counters put
    on them." forbids (Melira's "-1/-1"), or None."""
    if "counters put on them" not in line:
        return None
    match = _CREATURES_CANT_HAVE_COUNTERS_RE.fullmatch(_norm(line))
    return None if match is None else match.group("kind")


_OPPONENTS_LOSE_KEYWORD_RE = re.compile(
    r"^creatures your opponents control lose (?P<keyword>[a-z]+)\.?$", re.IGNORECASE
)


@cache
def opponents_lose_keyword_of_line(line: str) -> str | None:
    """The keyword "Creatures your opponents control lose <keyword>." takes
    away (Melira's infect), or None - only a keyword this engine executes."""
    if " lose " not in line:
        return None
    match = _OPPONENTS_LOSE_KEYWORD_RE.fullmatch(_norm(line))
    if match is None:
        return None
    from .combat import Keyword

    keyword = match.group("keyword").lower()
    return keyword if keyword in {k.value for k in Keyword} else None


def parse_opponents_lose_keyword(sentence: str):
    """`machines/layers/parse.py`'s hook: the layer 6 builder for
    "Creatures your opponents control lose <keyword>." (CR 613.1f)."""
    keyword = opponents_lose_keyword_of_line(sentence)
    if keyword is None:
        return None
    from .layers.model import (
        ContinuousEffect,
        Layer,
        creatures_controlled_by_opponents_of,
        lose_keyword,
    )
    from .layers.parse import _source_line_for

    def builder(source, timestamp, targets, context):
        return [
            ContinuousEffect(
                description=f"{source.name}: creatures your opponents control lose {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, sentence),
                selector=creatures_controlled_by_opponents_of(source.controller),
                modification=lose_keyword(keyword),
            )
        ]

    return builder


# -- asking the board ---------------------------------------------------------


def _controlled_lines(game: Game, username: str | None = None):
    """(permanent, controller, line) for every computed ability line on the
    battlefield (CR 604.2: only while the source is there and still has it),
    optionally only `username`'s permanents."""
    for permanent in list(game.battlefield):
        try:
            chars = game.characteristics_of(permanent)
        except KeyError:
            continue
        controller = chars.controller or permanent.controller
        if username is not None and controller != username:
            continue
        for line in chars.abilities:
            yield permanent, controller, line


def ignores_zero_life_loss(game: Game, username: str) -> str | None:
    for permanent, _controller, line in _controlled_lines(game, username):
        if ignores_zero_life_loss_line(line):
            return f"{username} doesn't lose for having 0 or less life: {permanent.name} says so"
    return None


def damage_dealt_as_though_infect(game: Game, username: str) -> bool:
    if game.player(username).life > 0:
        return False
    return any(
        damage_as_infect_at_zero_life_line(line)
        for _permanent, _controller, line in _controlled_lines(game, username)
    )


def life_total_cant_change(game: Game, username: str) -> str | None:
    """Why `username`'s life total can't change, or None (CR 119.7/119.8)."""
    if game is None:
        return None
    for permanent, _controller, line in _controlled_lines(game, username):
        if life_total_cant_change_line(line):
            return (
                f"{username}'s life total can't change: {permanent.name} says so "
                "(CR 101.2, CR 119.8)"
            )
    return None


def player_counter_prohibited(game: Game, username: str, kind: str) -> str | None:
    if str(kind).lower() != "poison":
        return None
    for permanent, _controller, line in _controlled_lines(game, username):
        if cant_get_poison_line(line):
            return f"{username} can't get poison counters: {permanent.name} says so (CR 101.2)"
    return None


def permanent_counter_prohibited(game: Game, permanent: CardState, kind: str) -> str | None:
    if "/" not in str(kind):
        return None
    try:
        chars = game.characteristics_of(permanent)
    except KeyError:
        return None
    if not chars.is_creature:
        return None
    owner_of_rule = chars.controller or permanent.controller
    for source, _controller, line in _controlled_lines(game, owner_of_rule):
        if controlled_creatures_counter_prohibition(line) == str(kind):
            return (
                f"{permanent.name} can't have {kind} counters put on it: {source.name} says so "
                "(CR 101.2)"
            )
    return None


def outcome_prohibition_from_reversed(game: Game, username: str, *, lose: bool) -> CardState | None:
    """The permanent whose reversed line stops `username` losing (an
    opponent's "your opponents can't lose the game") or winning (their own
    "you can't win the game"), or None."""
    for permanent, controller, line in _controlled_lines(game):
        prohibition = reversed_outcome_prohibition_of_line(line)
        if prohibition is None:
            continue
        if lose and prohibition.opponents_cant_lose and controller != username:
            return permanent
        if not lose and prohibition.you_cant_win and controller == username:
            return permanent
    return None


def reads_game_rule_line(line: str) -> bool:
    """Whether one of the readers above performs `line` - `support.py`'s
    audit credit (`static_audit/game_rules_untap.py`)."""
    return bool(
        legend_rule_exemption_of_line(line)
        or reversed_outcome_prohibition_of_line(line)
        or ignores_zero_life_loss_line(line)
        or damage_as_infect_at_zero_life_line(line)
        or life_total_cant_change_line(line)
        or cant_get_poison_line(line)
        or controlled_creatures_counter_prohibition(line)
        or opponents_lose_keyword_of_line(line)
    )
