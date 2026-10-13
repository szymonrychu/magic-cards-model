"""EP-02 R3 T6: the count a create-token sentence asks for (token-count-amounts).

Extends the shared amount readers (`effects.amounts.amount_expression` through
`_amount_term`, and `_for_each_multiplier`) additively; nothing here replaces a
reader they own, and the token clause itself stays `effects.tokens`'s.

Board facts a token count reads, each taken once when the instruction is applied
(CR 608.2h):

- "the number of opponents you have" and "the number of opponents who control
  <permanent>" - the players still in the game (CR 104.5);
- "<creatures> that died this turn" - CR 700.4's dies, read from the turn ledger
  as the creature last existed (CR 603.10a), so a token or a subtype is judged
  by what it was when it died;
- "<permanents> that entered the battlefield under your control this turn";
- "<Auras and/or Equipment> attached to <this permanent>" (CR 301.5a);
- "differently named creature tokens you control" (CR 201.2: names differ);
- "unlocked doors among Rooms you control" (CR 709.5c's unlocked designations);
- "the amount of mana spent to cast that spell" - the spell a cast trigger names
  (CR 601.2h: the total cost paid);
- "time it was kicked" as a "for each" tail (CR 702.33d).
"""

import functools
import re
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from ..models.card_state import CardState

if TYPE_CHECKING:
    from ..models.game import Game

#: `(game, controller, source object, announced X) -> int`, `effects.amounts`'s
#: `AmountReader`.
Reader = Callable[["Game", str, CardState | None, int], int]

_PREFIX = r"^(?:the )?(?:number|amount) of "


def _opponents_of(game: "Game", controller: str) -> list:
    return [player for player in game.players_in_game if player.username != controller]


# -- opponents ------------------------------------------------------------------

_OPPONENTS_YOU_HAVE_RE = re.compile(_PREFIX + r"opponents you have$", re.IGNORECASE)
_OPPONENTS_WHO_CONTROL_RE = re.compile(
    _PREFIX + r"opponents who control (?:an? |)(?P<what>.+)$", re.IGNORECASE
)


def _opponents_you_have(_text: str) -> Reader:
    return lambda game, controller, _obj, _x: len(_opponents_of(game, controller))


def _opponents_who_control(match: re.Match[str]) -> Reader | None:
    """CR 109.5: each opponent who controls at least one permanent matching the
    description counts once."""
    from .targeting import permanent_description

    requirement = permanent_description(match.group("what").strip())
    if requirement is None:
        return None

    def count(game: "Game", controller: str, _obj: CardState | None, _x: int) -> int:
        board = game.computed_board()
        total = 0
        for opponent in _opponents_of(game, controller):
            if any(
                board.of(permanent).controller == opponent.username
                and not requirement.rejects(permanent, controller, game)
                for permanent in game.battlefield
            ):
                total += 1
        return total

    return count


# -- the turn ledger -------------------------------------------------------------

_DIED_RE = re.compile(
    r"^(?:the )?(?:number of )?(?P<what>.+?) that died this turn$", re.IGNORECASE
)
_ENTERED_RE = re.compile(
    r"^(?:the )?(?:number of )?(?P<what>.+?) that entered the battlefield under your "
    r"control this turn$",
    re.IGNORECASE,
)


def _ledger_count(kind: str, what: str, *, yours_only: bool) -> Reader | None:
    from .conditions.history import _quality

    # CR 111.1: a token is a permanent that is not represented by a card; the
    # ledger's characteristics carry that as they last existed (CR 603.10a).
    token_filter = None
    words = [word for word in what.split() if word]
    for index, word in enumerate(words):
        if word.lower() in ("nontoken", "non-token"):
            token_filter, words = False, words[:index] + words[index + 1 :]
            break
    quality = _quality(" ".join(words))
    if quality is None:
        return None

    def count(game: "Game", controller: str, _obj: CardState | None, _x: int) -> int:
        return sum(
            1
            for entry in game.turn_history
            if entry.kind == kind
            and (not yours_only or entry.player == controller)
            and quality(entry)
            and (
                token_filter is None
                or (entry.characteristics is not None)
                and entry.characteristics.is_token is token_filter
            )
        )

    return count


# -- tokens and rooms ------------------------------------------------------------

_DIFFERENTLY_NAMED_RE = re.compile(
    _PREFIX + r"differently named (?P<what>creature tokens?) you control$", re.IGNORECASE
)
_UNLOCKED_DOORS_RE = re.compile(
    _PREFIX + r"unlocked doors among Rooms you control$", re.IGNORECASE
)


def _differently_named_tokens(_match: re.Match[str]) -> Reader:
    def count(game: "Game", controller: str, _obj: CardState | None, _x: int) -> int:
        board = game.computed_board()
        names = set()
        for permanent in game.battlefield:
            chars = board.of(permanent)
            if chars.controller == controller and chars.is_token and "creature" in {
                str(kind).lower().rsplit(".", 1)[-1] for kind in chars.types
            }:
                names.add(chars.name)
        return len(names)

    return count


def _unlocked_doors(_match: re.Match[str]) -> Reader:
    """CR 709.5c: each half of a Room permanent you control that is unlocked."""

    def count(game: "Game", controller: str, _obj: CardState | None, _x: int) -> int:
        board = game.computed_board()
        return sum(
            len(permanent.unlocked_doors)
            for permanent in game.battlefield
            if board.of(permanent).controller == controller
            and "room" in {subtype.lower() for subtype in board.of(permanent).subtypes}
        )

    return count


# -- attached ---------------------------------------------------------------------

_ATTACHED_RE = re.compile(
    r"^(?:the )?(?:number of )?(?P<kinds>[A-Za-z ,/]+?) attached to "
    r"(?P<ref>it|him|her|this [a-z]+|[A-Z][\w',-]*(?: [A-Z][\w',-]*)*)$"
)
_KIND_SPLIT_RE = re.compile(r"\s*(?:,\s*(?:and/or\s+|or\s+|and\s+)?|\s+and/or\s+|\s+or\s+|\s+and\s+)")


def _attached_count(match: re.Match[str]) -> Reader | None:
    """CR 301.5a, CR 303.4: what is attached to the object the ability is on."""
    words = [word for word in _KIND_SPLIT_RE.split(match.group("kinds").strip()) if word]
    if not words:
        return None
    wanted = {word.lower() for word in words}
    if not wanted <= {"aura", "equipment", "fortification", "auras"}:
        return None
    wanted = {word.removesuffix("s") if word == "auras" else word for word in wanted}

    def count(game: "Game", _controller: str, obj: CardState | None, _x: int) -> int:
        if obj is None:
            return 0
        board = game.computed_board()
        return sum(
            1
            for permanent in game.battlefield
            if permanent.attached_to == obj.id
            and wanted & {subtype.lower() for subtype in board.of(permanent).subtypes}
        )

    return count


# -- mana spent, kicks ----------------------------------------------------------------

_MANA_SPENT_THAT_SPELL_RE = re.compile(
    _PREFIX + r"mana spent to cast (?:that|the) spell$", re.IGNORECASE
)
_TIME_KICKED_RE = re.compile(
    r"^(?:the )?(?:number of )?times? (?:it|this (?:creature|permanent|artifact|enchantment|spell)) "
    r"was kicked$",
    re.IGNORECASE,
)


def _mana_spent_on_triggering_spell(_match: re.Match[str]) -> Reader:
    """CR 601.2h: the total mana spent to cast the spell a cast trigger names,
    read off that spell's cast record."""

    def count(game: "Game", _controller: str, _obj: CardState | None, _x: int) -> int:
        resolving = game.resolving
        event = getattr(resolving, "event", None)
        if event is None or event.subject_id is None:
            return 0
        spell = game.find_by_id(event.subject_id)
        if not isinstance(spell, CardState):
            return 0
        record = game.cast_record_of(spell)
        return 0 if record is None else record.total_mana_spent

    return count


def _times_kicked(_match: re.Match[str]) -> Reader:
    def count(game: "Game", _controller: str, obj: CardState | None, _x: int) -> int:
        record = None if obj is None else game.cast_record_of(obj)
        return 0 if record is None else record.kicked

    return count


@functools.cache
def amount_term(text: str) -> Reader | None:
    """One `amount_expression` term this module reads, or `None`."""
    phrase = " ".join(text.strip().rstrip(".").split())
    lowered = phrase.lower()
    if "opponents" in lowered:
        if _OPPONENTS_YOU_HAVE_RE.fullmatch(phrase):
            return _opponents_you_have(phrase)
        if (who := _OPPONENTS_WHO_CONTROL_RE.fullmatch(phrase)) is not None:
            return _opponents_who_control(who)
    if lowered.endswith("this turn"):
        if (entered := _ENTERED_RE.fullmatch(phrase)) is not None:
            return _ledger_count("entered", entered.group("what"), yours_only=True)
        if (died := _DIED_RE.fullmatch(phrase)) is not None:
            return _ledger_count("to_graveyard", died.group("what"), yours_only=False)
    if "differently named" in lowered and (named := _DIFFERENTLY_NAMED_RE.fullmatch(phrase)):
        return _differently_named_tokens(named)
    if "unlocked doors" in lowered and (doors := _UNLOCKED_DOORS_RE.fullmatch(phrase)):
        return _unlocked_doors(doors)
    if "attached to" in lowered and (attached := _ATTACHED_RE.fullmatch(phrase)):
        return _attached_count(attached)
    if "mana spent" in lowered and (spent := _MANA_SPENT_THAT_SPELL_RE.fullmatch(phrase)):
        return _mana_spent_on_triggering_spell(spent)
    if "kicked" in lowered and (kicked := _TIME_KICKED_RE.fullmatch(phrase)):
        return _times_kicked(kicked)
    return None


@functools.cache
def for_each_count(phrase: str) -> Callable[["Game", str, str | None], int] | None:
    """The count of a "for each <phrase>" tail: the same readers as "the number
    of <phrase>", with the ability's source as the object (CR 608.2h)."""
    from .effects.amounts import amount_expression

    text = " ".join(phrase.strip().rstrip(".").split())
    reader = amount_term(f"the number of {text}") or amount_expression(f"the number of {text}")
    if reader is None:
        return None

    def count(game: "Game", controller: str, source_id: str | None) -> int:
        source = None
        if source_id is not None:
            found = game.find_by_id(UUID(str(source_id)))
            source = found if isinstance(found, CardState) else None
        return int(reader(game, controller, source, 0))

    return count

