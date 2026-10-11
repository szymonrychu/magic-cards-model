"""Static "players can't ..." prohibitions on player actions (CR 101.2: a
prohibition beats the permission or instruction it forbids), read live off the
computed ability lines of every permanent on the battlefield (CR 613.5):

- "Players can't pay life or sacrifice creatures to cast spells or activate
  abilities." (Angel of Jubilation) and "Players can't pay life to cast spells
  or to activate abilities that aren't mana abilities." (Karn's Sylex): a cost
  that pays life or sacrifices such a permanent is refused (`payment_refusal`,
  asked by `CostComponent.why_not`, so a Phyrexian symbol's life is covered).
- "Players can't search libraries." (Mindlock Orb) and its variant "Any player
  may pay {2} for that player to ignore this effect until end of turn."
  (Leonin Arbiter): `library_search_blocked`, asked by `Game.search_library`.
- "Spells and abilities your opponents control can't cause you to sacrifice
  permanents." (Sigarda, Host of Herons; Tajuru Preserver):
  `sacrifice_caused_by_opponent`, asked by `Game.sacrifice` while a stack
  object of an opponent resolves.
- "Each opponent can't venture into the dungeon more than once each turn."
  (Keen-Eared Sentry): `venture_refused`.
"""

import re
from functools import cache
from typing import TYPE_CHECKING, NamedTuple

from ..models.card import Type
from ..models.card_state import CardState
from ..models.mana import ManaCost

if TYPE_CHECKING:
    from ..models.game import Game

_PAYMENT_RE = re.compile(
    r"^players can't (?P<acts>.+?) to cast spells(?: or to activate abilities| or activate "
    r"abilities)(?P<nonmana> that aren't mana abilities)?\.?$",
    re.IGNORECASE,
)
_SEARCH_RE = re.compile(
    r"^players can't search libraries\.?(?P<pay> any player may pay (?P<cost>\{\d+\}) for that "
    r"player to ignore this effect until end of turn\.?)?$",
    re.IGNORECASE,
)
_CAUSE_SACRIFICE_RE = re.compile(
    r"^spells and abilities your opponents control can't cause you to sacrifice permanents\.?$",
    re.IGNORECASE,
)
_VENTURE_RE = re.compile(
    r"^each opponent can't venture into the dungeon more than once each turn\.?$", re.IGNORECASE
)
_TYPES = {t.value.lower(): t for t in Type}

IGNORES_SEARCH_PROHIBITION = "ignores_search_prohibition"
VENTURED = "ventured_into_the_dungeon"


class PaymentBan(NamedTuple):
    pay_life: bool
    sacrifice: frozenset[str]
    nonmana_only: bool


@cache
def _payment_ban(line: str) -> PaymentBan | None:
    match = _PAYMENT_RE.match(line)
    if match is None:
        return None
    pay_life, sacrifice = False, set()
    for act in re.split(r"\s+or\s+", match["acts"].lower()):
        if act == "pay life":
            pay_life = True
        elif act.startswith("sacrifice "):
            noun = act.removeprefix("sacrifice ").strip()
            singular = noun[:-1] if noun.endswith("s") else noun
            if noun == "permanents":
                sacrifice.add("permanent")
            elif singular in _TYPES:
                sacrifice.add(singular)
            else:
                return None
        else:
            return None
    return PaymentBan(pay_life, frozenset(sacrifice), match["nonmana"] is not None)


def reads_player_action_prohibition_line(text: str) -> bool:
    """Whether `text` is a prohibition this module enforces."""
    line = " ".join(text.split())
    lowered = line.lower()
    if "can't" not in lowered:
        return False
    return (
        _payment_ban(line) is not None
        or _SEARCH_RE.match(line) is not None
        or _CAUSE_SACRIFICE_RE.match(line) is not None
        or _VENTURE_RE.match(line) is not None
    )


def _lines(game: "Game") -> list[tuple[CardState, str]]:
    from .triggers.collect import _computed_ability_lines

    return [
        (permanent, " ".join(line.split()))
        for permanent in game.battlefield
        for line in _computed_ability_lines(game, permanent)
        if "can't" in line.lower()
    ]


def payment_refusal(
    game: "Game", *, life: bool, sacrificed: tuple[CardState, ...] = ()
) -> str | None:
    """Why a cost that pays life (`life`) or sacrifices `sacrificed` cannot be
    paid, or None."""
    for permanent, line in _lines(game):
        ban = _payment_ban(line)
        if ban is None:
            continue
        if life and ban.pay_life:
            return (
                f"{permanent.name}: players can't pay life to cast spells or activate "
                "abilities (CR 101.2)"
            )
        for victim in sacrificed:
            try:
                words = {t.value.lower() for t in game.characteristics_of(victim).types}
            except KeyError:
                words = {t.value.lower() for t in victim.types}
            if "permanent" in ban.sacrifice or ban.sacrifice & words:
                return (
                    f"{permanent.name}: players can't sacrifice {victim.name} to cast spells "
                    "or activate abilities (CR 101.2)"
                )
    return None


def library_search_blocked(game: "Game", player: str) -> CardState | None:
    """The permanent whose "players can't search libraries" stops `player`'s
    search now (CR 101.2), after any "pay {2}" release (Leonin Arbiter) is
    offered; None when the search may go ahead."""
    for permanent, line in _lines(game):
        match = _SEARCH_RE.match(line)
        if match is None:
            continue
        if player in game.turn_facts.get(IGNORES_SEARCH_PROHIBITION, ()):
            continue
        if match["pay"]:
            cost = ManaCost.parse(match["cost"])
            order = [player, *(p.username for p in game.players if p.username != player)]
            for payer in order:
                if game.may_pay_mana_cost(
                    game.player(payer),
                    cost,
                    source=permanent.name,
                    source_id=str(permanent.id),
                    prompt=f"pay {match['cost']} so {player} ignores {permanent.name} this turn",
                ):
                    game.record_turn_fact(IGNORES_SEARCH_PROHIBITION, player)
                    break
            else:
                return permanent
            continue
        return permanent
    return None


def sacrifice_caused_by_opponent(game: "Game", permanent: CardState) -> bool:
    """Whether `permanent`'s controller is protected from the sacrifice the
    resolving spell or ability of an opponent would cause (CR 101.2)."""
    resolving = game.resolving
    cause = getattr(resolving, "controller", None) if resolving is not None else None
    owner = permanent.controller
    if cause is None or owner is None or cause == owner:
        return False
    for holder, line in _lines(game):
        if holder.controller == owner and _CAUSE_SACRIFICE_RE.match(line):
            return True
    return False


def venture_refused(game: "Game", player: str) -> bool:
    """Whether `player` may not venture now: an opponent's "can't venture more
    than once each turn" and they already did this turn."""
    if player not in game.turn_facts.get(VENTURED, ()):
        return False
    return any(
        holder.controller != player and _VENTURE_RE.match(line) for holder, line in _lines(game)
    )
