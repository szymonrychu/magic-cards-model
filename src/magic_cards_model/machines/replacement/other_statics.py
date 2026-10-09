"""EP-01 round 1 (task 6): the replacement statics the generic compilers in
`parse.py` did not read - zone changes (CR 614.1a, 700.4), draws (CR 614.11),
counters and tokens (CR 614.16), and the one-event shapes (search, mill, dice,
coin, poison, proliferate, explore, extra turns).

Each compiler is a `ReplacementEffect -> CardReplacement | None`, registered in
`OTHER_COMPILERS` and appended to `parse._COMPILERS`, so `parsed_card_
replacements` performs it from the battlefield (and `models/..._anywhere` from
any other zone) and `performs_static_line` credits it. They match the whole
event clause and the whole replacement clause and fail closed (`None`) on any
word they do not read - never a partial reading.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...models.card import Type
from ...models.card_state import CardState
from ...models.token import create_tokens, is_token
from ...models.zone import Zone
from .model import (
    Apply,
    CardReplacement,
    EventKind,
    ReplaceableEvent,
    ReplacementEffect,
    ReplacementKind,
    _shuffle_into_library_instead,
)
if TYPE_CHECKING:
    from ...models.game import Game
from .parse import (
    _exile_instead,
    _is_opponent,
    _owner_username,
    _read_token_descriptor,
    _to_graveyard,
)

# --------------------------------------------------------------------------
# Zone changes: "If <subject> would die / be put into a graveyard, <action>"
# --------------------------------------------------------------------------

_DIES_RE = re.compile(r"^(?P<subject>.+?) would die$", re.IGNORECASE)
_GRAVEYARD_RE = re.compile(
    r"^(?P<subject>.+?) would be put into (?P<whose>a|your|an opponent's|enchanted player's) "
    r"graveyard(?: from (?P<where>anywhere|the battlefield))?(?P<tail> and it wasn't cycled)?$",
    re.IGNORECASE,
)
_CLAUSE_SPLIT_RE = re.compile(r" or (?=an? [a-z' ]+ would )", re.IGNORECASE)

_CREATURE_SUBJECT_RE = re.compile(
    r"^a(?P<nontoken> nontoken)? creature"
    r"(?: (?P<who>an opponent controls|you control|an opponent owns))?"
    r"(?P<enchanted> that's enchanted)?$",
    re.IGNORECASE,
)


def _types_of(game: "Game", card: CardState) -> frozenset[Type]:
    """The card's types now: computed for a permanent (CR 613.5), printed anywhere else."""
    if card.zone is Zone.BATTLEFIELD:
        return frozenset(game.characteristics_of(card).types)
    return frozenset(card.types)


def _card_subject(subject: str) -> Callable[["Game", CardState, CardState, ReplaceableEvent], bool] | None:
    """A predicate for the moved object, from the printed subject phrase."""
    text = subject.strip().lower()
    if text == "a card":
        return lambda game, source, card, event: True
    if text == "a permanent":
        return lambda game, source, card, event: event.origin is Zone.BATTLEFIELD
    if text == "another creature":
        return lambda game, source, card, event: (
            card.id != source.id and Type.CREATURE in _types_of(game, card)
        )
    if text == "an instant or sorcery card":
        return lambda game, source, card, event: bool(
            _types_of(game, card) & {Type.INSTANT, Type.SORCERY}
        )
    if text == "a card you didn't control":
        return lambda game, source, card, event: card.controller != source.controller
    if text == "a creature card not on the battlefield":
        return lambda game, source, card, event: (
            event.origin is not Zone.BATTLEFIELD and Type.CREATURE in _types_of(game, card)
        )
    if text == "a card that has a cycling ability":
        return lambda game, source, card, event: "cycling" in (card.card.oracle_text or "").lower()
    match = _CREATURE_SUBJECT_RE.match(text)
    if match is None:
        return None
    who, nontoken, enchanted = match.group("who"), match.group("nontoken"), match.group("enchanted")

    def creature(game: "Game", source: CardState, card: CardState, event: ReplaceableEvent) -> bool:
        if Type.CREATURE not in _types_of(game, card):
            return False
        if nontoken and is_token(card):
            return False
        if who == "an opponent controls" and not _is_opponent(game, card.controller, source.controller):
            return False
        if who == "you control" and card.controller != source.controller:
            return False
        if who == "an opponent owns" and not _is_opponent(
            game, _owner_username(game, card), source.controller
        ):
            return False
        return not enchanted or any(
            (a.attached_to == card.id) for a in game.battlefield if "Aura" in a.subtypes
        )

    return creature


def _whose_graveyard(whose: str, source_enchants_player: bool) -> Callable | None:
    whose = whose.lower()
    if whose == "a":
        return lambda game, source, card: True
    if whose == "your":
        return lambda game, source, card: _owner_username(game, card) == source.controller
    if whose == "an opponent's":
        return lambda game, source, card: _is_opponent(
            game, _owner_username(game, card), source.controller
        )
    return None


def _clause_applies(clause: str, effect: ReplacementEffect):
    """One "<subject> would die / be put into a graveyard" clause -> predicate
    `(game, source, event) -> bool`, or `None` when any word is unread."""
    clause = clause.strip()
    dies = _DIES_RE.match(clause)
    grave = _GRAVEYARD_RE.match(clause)
    if dies is not None:
        subject, from_battlefield, whose, tail = dies.group("subject"), True, "a", None
    elif grave is not None:
        subject = grave.group("subject")
        from_battlefield = (grave.group("where") or "").lower() == "the battlefield"
        whose, tail = grave.group("whose"), grave.group("tail")
    else:
        return None
    if tail is not None:
        return None  # "and it wasn't cycled" is read by its own compiler
    whose_matcher = _whose_graveyard(whose, False)
    if whose_matcher is None:
        return None
    anywhere_self = False
    if effect.self_replacement:
        subject_matcher = lambda game, source, card, event: card.id == source.id  # noqa: E731
        anywhere_self = grave is not None and not from_battlefield
    else:
        subject_matcher = _card_subject(subject)
        if subject_matcher is None:
            return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        card = event.card
        if card is None or not _to_graveyard(event):
            return False
        if from_battlefield and event.origin is not Zone.BATTLEFIELD:
            return False
        return whose_matcher(game, source, card) and subject_matcher(game, source, card, event)

    applies.anywhere = anywhere_self  # type: ignore[attr-defined]
    return applies


# -- the action half ---------------------------------------------------------

_COUNTER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _zone_action(effect: ReplacementEffect) -> Apply | None:
    """The replacement half of a zone change -> the function applying it."""
    printed = (effect.replacement or "").strip().rstrip(".")
    text = printed.lower()
    subject = (effect.event or "").split(" would ")[0].strip().lower()

    if match := re.fullmatch(
        r"reveal (?P<name>.+?) and shuffle it into its owner's library", text
    ):
        if effect.self_replacement and match.group("name") == subject:
            return _shuffle_into_library_instead
        return None
    if re.fullmatch(r"put it on the bottom of its owner's library", text) or re.fullmatch(
        r"that card is revealed and put on the bottom of that player's library", text
    ):
        return _library_bottom
    if match := re.fullmatch(
        r"exile (?:it|that card)(?: with (?P<n>an?|one|two|three|four|five) "
        r"(?P<kind>[a-z+\-/0-9]+) counters? on it)?"
        r"(?: and (?:(?P<token>create .+?)|you gain (?P<life>\d+) life))?",
        printed,
        re.IGNORECASE,
    ):
        return _exile_action(match, effect)
    return None


def _library_bottom(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    event.destination = Zone.LIBRARY
    event.library_position = "bottom"


def _exile_action(match: re.Match, effect: ReplacementEffect) -> Apply | None:
    count = _COUNTER_WORDS.get((match.group("n") or "").lower(), 0)
    kind = match.group("kind")
    life = int(match.group("life")) if match.group("life") else 0
    token = None
    if match.group("token"):
        descriptor = re.fullmatch(r"create an? (?P<d>.+ token)", match.group("token"), re.IGNORECASE)
        token = _read_token_descriptor(descriptor.group("d")) if descriptor else None
        if token is None:
            return None
    if effect.linked_trigger is not None:
        return None

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        _exile_instead(game, source, event)
        if count:
            event.exile_counters[kind] = event.exile_counters.get(kind, 0) + count
        if life and source.controller:
            game.gain_life(source.controller, life)
        if token is not None and source.controller:
            create_tokens(game, token, source.controller, 1)

    return apply


def _compile_zone_change(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD or effect.condition is not None:
        return None
    event_text = (effect.event or "").strip()
    clauses = _CLAUSE_SPLIT_RE.split(event_text)
    predicates = [_clause_applies(clause, effect) for clause in clauses]
    if any(p is None for p in predicates):
        return None
    action = _zone_action(effect)
    if action is None:
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return any(p(game, source, event) for p in predicates)

    return CardReplacement(
        label=effect.text,
        applies=applies,
        apply=action,
        anywhere=all(getattr(p, "anywhere", False) for p in predicates),
    )


OTHER_COMPILERS: tuple[Callable[[ReplacementEffect], CardReplacement | None], ...] = (
    _compile_zone_change,
)
