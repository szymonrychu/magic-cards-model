"""Untap-step statics: the printed lines that change CR 502.3's untap.

CR 502.3: "Third, the active player determines which permanents they control
will untap. Then they untap them all simultaneously. This turn-based action
doesn't use the stack. Normally, all of a player's permanents untap, but
effects can keep one or more of a player's permanents from untapping."
CR 614.10: "An effect that causes a player to skip an event, step, phase, or
turn is a replacement effect. 'Skip [something]' is the same as 'Instead of
doing [something], do nothing.'"

Every reader here takes one ability line already self-normalised the way the
battlefield sweep normalises it (`abilities.self_normalized_effect_text`: a
card's own name reads "this permanent") and returns the parsed shape, or
None. Qualities go through `conditions.board.quality` and conditions through
`Game.condition_holds` - the engine's shared readers - so a line is read only
when every word of it is. `Game.untap_step_rule`, `Game._untap_step_impl`
and `Game._advance_past_checks` perform them; `static_audit/
game_rules_untap.py` credits a line only when one of these reads it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Any

from magic_cards_model.text_norm import collapsed

if TYPE_CHECKING:
    from ..models.card_state import CardState

_SELF = r"this (?:creature|artifact|permanent|land|enchantment)"
_ABILITY_WORD = re.compile(r"^[A-Z][\w' ]+ — ")


def _clean(line: str) -> str:
    text = re.sub(r"\s*\([^)]*\)", "", line).strip()
    text = _ABILITY_WORD.sub("", text)
    return collapsed(text).rstrip(".")


@dataclass(frozen=True)
class OtherPlayersUntap:
    """ "Untap <what> during each other player's untap step." - `quality`
    is None for the permanent itself, else the quality of the permanents its
    controller controls; `condition` is a leading "As long as ..."."""

    quality: str | None
    condition: str | None = None


_OTHER_PLAYERS_UNTAP_RE = re.compile(
    rf"^(?:as long as (?P<cond>.+?), )?untap (?:(?P<self>{_SELF})|all (?P<all>.+?) you control"
    r"|each (?P<each>\w+) you control(?: (?P<with>with .+?))?) during each other player'?s "
    r"untap step$",
    re.IGNORECASE,
)


@cache
def other_players_untap_of_line(line: str) -> OtherPlayersUntap | None:
    """Seedborn Muse's, Prophet of Kruphix's, Unwinding Clock's, Ivorytusk
    Fortress's, Thousand Moons Infantry's and Quest for Renewal's shape."""
    from .conditions.board import quality

    if "other player" not in line.lower():
        return None
    match = _OTHER_PLAYERS_UNTAP_RE.fullmatch(_clean(line))
    if match is None:
        return None
    condition = match.group("cond")
    if match.group("self"):
        return OtherPlayersUntap(quality=None, condition=condition)
    if match.group("all"):
        # "creatures and lands": each creature and each land (CR 205.2a's
        # list of types, any one of which will do).
        phrase = re.sub(r"\s+and\s+", " or ", match.group("all").strip().lower())
    else:
        phrase = f"{match.group('each')} {match.group('with') or ''}".strip().lower()
    if quality(phrase) is None:
        return None
    return OtherPlayersUntap(quality=phrase, condition=condition)


_GROUP_DOESNT_UNTAP_RE = re.compile(
    r"^(?P<q>.+?) don'?t untap during their controllers'? untap steps?$", re.IGNORECASE
)


@cache
def group_doesnt_untap_of_line(line: str) -> str | None:
    """ "<Quality> don't untap during their controllers' untap steps." - the
    quality phrase (Choke's "Islands", Marble Titan's "Creatures with power 3
    or greater"), read for every player's permanents."""
    from .conditions.board import quality

    if "untap" not in line.lower():
        return None
    match = _GROUP_DOESNT_UNTAP_RE.fullmatch(_clean(line))
    if match is None:
        return None
    phrase = match.group("q").strip().lower()
    if phrase.startswith(("this ", "enchanted ", "equipped ")) or quality(phrase) is None:
        return None
    return phrase


_SELF_DOESNT_UNTAP_IF_RE = re.compile(
    rf"^{_SELF} doesn'?t untap during your untap step if (?P<cond>.+)$", re.IGNORECASE
)


@cache
def self_doesnt_untap_condition_of_line(line: str) -> str | None:
    """ "<This> doesn't untap during your untap step if <condition>." -
    Steel Dromedary's "it has a +1/+1 counter on it", Alirios's "you control
    a Reflection"."""
    if "untap" not in line.lower():
        return None
    match = _SELF_DOESNT_UNTAP_IF_RE.fullmatch(_clean(line))
    return None if match is None else match.group("cond").strip()


_ATTACHED_DOESNT_UNTAP_AS_LONG_AS_RE = re.compile(
    r"^as long as (?P<cond>.+?), enchanted (?:creature|permanent) doesn'?t untap during its "
    r"controller'?s untap step$",
    re.IGNORECASE,
)


@cache
def attached_doesnt_untap_condition_of_line(line: str) -> str | None:
    """ "As long as <condition>, enchanted creature doesn't untap during its
    controller's untap step." (Winter's Rest)."""
    if "untap" not in line.lower():
        return None
    match = _ATTACHED_DOESNT_UNTAP_AS_LONG_AS_RE.fullmatch(_clean(line))
    return None if match is None else match.group("cond").strip()


_MAY_CHOOSE_NOT_TO_UNTAP_RE = re.compile(
    rf"^you may choose not to untap {_SELF} during your untap step$", re.IGNORECASE
)


@cache
def is_may_choose_not_to_untap_line(line: str) -> bool:
    """ "You may choose not to untap <this> during your untap step." - CR
    502.3's own "the active player determines which permanents they control
    will untap"."""
    return "choose not to untap" in line.lower() and bool(
        _MAY_CHOOSE_NOT_TO_UNTAP_RE.fullmatch(_clean(line))
    )


_AT_MOST_ONE_RE = re.compile(
    r"^players can'?t untap more than one (?P<q>.+?) during their untap steps?$", re.IGNORECASE
)


@cache
def untap_at_most_one_of_line(line: str) -> str | None:
    """ "Players can't untap more than one <quality> during their untap
    steps." - the quality (Stoic Angel's creature, Imi Statue's artifact,
    Winter Moon's nonbasic land)."""
    from .conditions.board import quality

    if "more than one" not in line.lower():
        return None
    match = _AT_MOST_ONE_RE.fullmatch(_clean(line))
    if match is None:
        return None
    phrase = match.group("q").strip().lower()
    return phrase if quality(phrase) is not None else None


@dataclass(frozen=True)
class UpkeepSkip:
    """ "Players skip their upkeep steps." (`everyone`) or "Skip your upkeep
    step[ if <condition>]." (its controller only)."""

    everyone: bool
    condition: str | None = None


_SKIP_UPKEEP_RE = re.compile(
    r"^(?:(?P<all>players skip their upkeep steps)|skip your upkeep step(?: if (?P<cond>.+))?)$",
    re.IGNORECASE,
)


@cache
def upkeep_skip_of_line(line: str) -> UpkeepSkip | None:
    """Eon Hub's and Gibbering Descent's Hellbent skip (CR 614.10)."""
    if "upkeep" not in line.lower():
        return None
    match = _SKIP_UPKEEP_RE.fullmatch(_clean(line))
    if match is None:
        return None
    return UpkeepSkip(everyone=bool(match.group("all")), condition=match.group("cond"))


def reads_untap_static_line(line: str) -> bool:
    """Whether one of the readers above reads `line` (self-normalised)."""
    return (
        other_players_untap_of_line(line) is not None
        or group_doesnt_untap_of_line(line) is not None
        or self_doesnt_untap_condition_of_line(line) is not None
        or attached_doesnt_untap_condition_of_line(line) is not None
        or is_may_choose_not_to_untap_line(line)
        or untap_at_most_one_of_line(line) is not None
        or upkeep_skip_of_line(line) is not None
    )


# -- the board ----------------------------------------------------------------


def normalized_lines(game: Any, permanent: CardState) -> list[str]:
    """`permanent`'s computed ability lines (CR 613.1f), self-normalised."""
    from ..models.card import Supertype
    from .abilities import self_normalized_effect_text

    chars = game.characteristics_of(permanent)
    legendary = Supertype.LEGENDARY in chars.supertypes
    name = chars.name or permanent.name
    return [
        self_normalized_effect_text(name, line, legendary=legendary) for line in chars.abilities
    ]


def matches(game: Any, controller: str, phrase: str, permanent: CardState) -> bool:
    """`phrase` (a `conditions.board.quality`) of `permanent`, "you" being
    `controller`."""
    from .conditions import ConditionContext
    from .conditions.board import quality

    test = quality(phrase)
    if test is None:
        return False
    context = ConditionContext(game=game, controller=controller)
    return bool(test(context, permanent, game.characteristics_of(permanent)))


def holds(game: Any, controller: str, condition: str | None, source: CardState) -> bool:
    """A printed condition, read by `Game.condition_holds`; an unread one is
    not known to hold."""
    if condition is None:
        return True
    return game.condition_holds(controller, condition, source) is True
