"""Counter and token replacement statics (CR 614.16, CR 122.6, CR 701.7b):
"If one or more <kind> counters would be put on <subject>, that many plus one
... are put on it instead", "twice that many of each of those kinds", and
"If you would create one or more <kind> tokens, instead create those tokens
plus an additional <predefined> token" / "one of each" / "that many <token> or
that many <token>".

The counter event is `EventKind.ADD_COUNTERS` (one per kind); the token event
is `EventKind.CREATE_TOKENS`, raised before any token exists (CR 701.7b), so a
filter on "artifact" or "Treasure" reads the stated `TokenDefinition`.
"""

import re
from typing import TYPE_CHECKING

from ...models.card import Type
from ...models.card_state import CardState
from ...models.token import PREDEFINED, TokenDefinition
from ..decisions import Decision, DecisionKind
from .model import CardReplacement, EventKind, ReplaceableEvent, ReplacementEffect, ReplacementKind
from .parse import _names_of, _read_token_descriptor

if TYPE_CHECKING:
    from ...models.game import Game

_NUMBER = {"one": 1, "two": 2, "three": 3, "four": 4}
_TYPE_WORDS = {
    "creature": Type.CREATURE,
    "artifact": Type.ARTIFACT,
    "land": Type.LAND,
    "enchantment": Type.ENCHANTMENT,
    "planeswalker": Type.PLANESWALKER,
    "permanent": None,
}

_SPLIT_RE = re.compile(
    r"^if (?P<event>.+?), (?:instead,? )?(?=(?:that many plus|twice that many|three times that many"
    r"|those tokens|create |you may (?:instead )?create))(?P<replacement>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _event_and_replacement(effect: ReplacementEffect) -> tuple[str, str] | None:
    """The event and replacement clauses, re-split from the whole sentence:
    the parser cuts at the first comma, which breaks "a Clue, Food, or
    Treasure token" and "an Army, Goblin, or Orc you control" in two."""
    match = _SPLIT_RE.match(effect.text.strip())
    if match is None:
        return None
    event = match.group("event").strip().rstrip(",")
    replacement = re.sub(r" instead$", "", match.group("replacement").strip().rstrip("."))
    return event, replacement


# -- counters ----------------------------------------------------------------

_COUNTER_EVENT_RE = re.compile(
    r"^one or more (?:(?P<kind>[+\-]\d+/[+\-]\d+|[a-z]+) )?counters "
    r"would be put on (?P<subject>.+)$",
    re.IGNORECASE,
)
_PLUS_REPLACEMENT_RE = re.compile(
    r"^that many plus (?P<n>one|two|three) "
    r"(?P<kind>[+\-]\d+/[+\-]\d+|[a-z]+) counters are put on it$",
    re.IGNORECASE,
)
_EACH_KIND_REPLACEMENT_RE = re.compile(
    r"^(?P<mult>twice|three times) that many of each of those kinds of counters are put on it$",
    re.IGNORECASE,
)
_SUBJECT_LIST_RE = re.compile(r"^an? (?P<list>.+?) you control$", re.IGNORECASE)
_SUBJECT_SPLIT_RE = re.compile(r",\s*(?:or\s+)?|\s+or\s+", re.IGNORECASE)


def _subject_test(game: "Game", permanent: CardState, words: list[str]) -> bool:
    chars = game.characteristics_of(permanent)
    subtypes = {s.lower() for s in chars.subtypes}
    for word in words:
        wanted = _TYPE_WORDS.get(word.lower(), "subtype")
        if wanted is None or (wanted == "subtype" and word.lower() in subtypes):
            return True
        if wanted != "subtype" and wanted in chars.types:
            return True
    return False


def _compile_counter_plus(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD or effect.condition is not None:
        return None
    split = _event_and_replacement(effect)
    if split is None:
        return None
    event = _COUNTER_EVENT_RE.match(split[0])
    replacement = split[1]
    if event is None:
        return None
    kind = (event.group("kind") or "").lower() or None
    multiplier, addend = 1, 0
    if match := _PLUS_REPLACEMENT_RE.match(replacement):
        if match.group("kind").lower() != kind:
            return None
        addend = _NUMBER[match.group("n").lower()]
    elif match := _EACH_KIND_REPLACEMENT_RE.match(replacement):
        if kind is not None:
            return None
        multiplier = 2 if match.group("mult").lower() == "twice" else 3
    else:
        return None
    subject = event.group("subject").strip()
    listed = _SUBJECT_LIST_RE.match(subject)
    words = _SUBJECT_SPLIT_RE.split(listed.group("list")) if listed else None
    if words is None and re.match(r"^an? ", subject, re.IGNORECASE):
        return None  # a group subject this does not read: fail closed

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        card = event.card
        if event.kind is not EventKind.ADD_COUNTERS or event.amount <= 0 or card is None:
            return False
        if kind is not None and str(event.counter_kind).lower() != kind:
            return False
        if words is None:  # the card itself, named by its own name (CR 201.5)
            return card.id == source.id and subject.lower() in {
                n.lower() for n in _names_of(source.card)
            }
        return card.controller == source.controller and _subject_test(game, card, words)

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.amount = event.amount * multiplier + addend

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


# -- tokens ------------------------------------------------------------------

_TOKEN_EVENT_RE = re.compile(
    r"^(?:you would create (?:one or more (?P<filter>[a-z]+) tokens?"
    r"|a (?P<trio>clue, food, or treasure) token|one or more tokens)"
    r"|one or more tokens would be created under your control)$",
    re.IGNORECASE,
)
_PLUS_TOKEN_RE = re.compile(
    r"^(?:create )?those tokens plus an? (?:additional )?(?P<name>[A-Za-z]+) token(?: are created)?$",
    re.IGNORECASE,
)
_ONE_OF_EACH_RE = re.compile(r"^create one of each$", re.IGNORECASE)
_EITHER_RE = re.compile(
    r"^you may (?:instead )?create that many (?P<a>.+?) or that many (?P<b>.+)$",
    re.IGNORECASE,
)


def _token_filter(event_text: str):
    match = _TOKEN_EVENT_RE.match(event_text.strip())
    if match is None:
        return None
    word = (match.group("filter") or "").lower()
    if match.group("trio"):
        names = {"clue", "food", "treasure"}
        return lambda d: bool({s.lower() for s in d.subtypes} & names)
    if not word:
        return lambda d: True
    if word in ("artifact", "creature", "land", "enchantment"):
        wanted = _TYPE_WORDS[word]
        return lambda d: wanted in d.types
    return lambda d: word in {s.lower() for s in d.subtypes}


#: CR 702.169d: "Solved - [ability text]" works only while the Case is solved.
_SOLVED_WORD_RE = re.compile(r"^solved\s+\u2014", re.IGNORECASE)


def _creator_is_you(source: CardState, event: ReplaceableEvent) -> bool:
    return event.creating_controller == source.controller


def _compile_token_replacement(effect: ReplacementEffect) -> CardReplacement | None:  # noqa: C901
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD or effect.condition is not None:
        return None
    split = _event_and_replacement(effect)
    if split is None:
        return None
    wants = _token_filter(split[0])
    if wants is None:
        return None
    replacement = split[1]
    solved_only = _SOLVED_WORD_RE.match(effect.raw.strip()) is not None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if event.kind is not EventKind.CREATE_TOKENS or event.amount <= 0:
            return False
        if event.definition is None or not wants(event.definition):
            return False
        if solved_only and not source.solved:
            return False
        return _creator_is_you(source, event)

    if match := _PLUS_TOKEN_RE.match(replacement):
        extra = PREDEFINED.get(match.group("name").capitalize())
        if extra is None:
            return None

        def add_one(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
            event.extra.append(extra)

        return CardReplacement(label=effect.text, applies=applies, apply=add_one)
    if _ONE_OF_EACH_RE.match(replacement):

        def one_of_each(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
            amount = event.amount
            event.definition = PREDEFINED["Clue"]
            event.card = None
            event.extra.extend([PREDEFINED["Food"]] * amount + [PREDEFINED["Treasure"]] * amount)

        return CardReplacement(label=effect.text, applies=applies, apply=one_of_each)
    if match := _EITHER_RE.match(replacement):
        options: list[TokenDefinition] = []
        for group in ("a", "b"):
            definition = _read_token_descriptor(re.sub(r"\btokens\b", "token", match.group(group)))
            if definition is None:
                return None
            options.append(definition)

        def either(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
            labels = ("keep", *(d.card_name for d in options))
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_QUALITY,
                    player=source.controller or "",
                    prompt="Instead create that many of which token (or keep the original)?",
                    source=source.name,
                    source_id=str(source.id),
                    options=labels,
                )
            )
            for definition in options:
                if answer == definition.card_name:
                    event.definition = definition
                    event.card = None

        return CardReplacement(label=effect.text, applies=applies, apply=either)
    return None


_MODULAR_EVENT_RE = re.compile(
    r"^a modular triggered ability would put one or more (?P<kind>[+\-]\d+/[+\-]\d+) counters "
    r"on a creature you control$",
    re.IGNORECASE,
)


def _compile_modular_plus(effect: ReplacementEffect) -> CardReplacement | None:
    """Zabaz, the Glimmerwasp: "If a modular triggered ability would put one or more
    +1/+1 counters on a creature you control, that many plus one +1/+1 counters
    are put on it instead." (CR 702.43a, 614.1a, 122.6)"""
    if not effect.event or not effect.replacement:
        return None
    head = _MODULAR_EVENT_RE.match(effect.event.strip())
    tail = _PLUS_REPLACEMENT_RE.match(effect.replacement.strip())
    if head is None or tail is None or head.group("kind") != tail.group("kind"):
        return None
    extra = _NUMBER[tail.group("n").lower()]
    kind = head.group("kind")

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return (
            event.kind is EventKind.ADD_COUNTERS
            and event.modular
            and event.card is not None
            and event.amount > 0
            and str(event.counter_kind).lower() == kind
            and event.card.controller == source.controller
            and Type.CREATURE in game.characteristics_of(event.card).types
        )

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.amount += extra

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


COUNTER_TOKEN_COMPILERS = (_compile_counter_plus, _compile_token_replacement, _compile_modular_plus)
