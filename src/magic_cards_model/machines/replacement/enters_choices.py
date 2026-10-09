"""EP-01 round 1 (T2): the "enters tapped" and "as [this] enters" families.

CR 614.12 - replacement effects that modify how a permanent enters; CR 614.1d -
"[This permanent] enters ..." / "[Objects] enter ..." wordings; CR 614.12a - a
choice such an effect needs is made before the permanent enters.

Everything here is read by `enters.py` (which imports this module); anything
this module needs from `enters.py` is imported lazily to keep the cycle
one-directional.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...models.card import Color, Supertype, Type
from ...models.card_state import CardState, ChoiceKind
from .model import CardReplacement, EventKind, ReplacementEffect

if TYPE_CHECKING:
    from ...models.game import Game

EntersCondition = Callable[["Game", CardState], bool]

# --------------------------------------------------------------------------
# "unless you control a <quality>" conditions (CR 614.1d, CR 614.12)
# --------------------------------------------------------------------------

_COLOR_WORDS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}
_CARD_TYPES: dict[str, Type] = {
    "artifact": Type.ARTIFACT,
    "creature": Type.CREATURE,
    "enchantment": Type.ENCHANTMENT,
    "land": Type.LAND,
    "planeswalker": Type.PLANESWALKER,
}

#: "you control a legendary creature" / "a legendary green creature" - a card
#: type with supertype and color qualifiers in front of it.
_YOU_CONTROL_QUALIFIED_RE = re.compile(
    r"^you control an? (?P<quals>(?:(?:legendary|snow|white|blue|black|red|green) )+)"
    r"(?P<type>artifact|creature|enchantment|land|planeswalker)$",
    re.IGNORECASE,
)
#: "you control a Mount or Vehicle" - subtypes joined by "or", the article
#: printed only on the first.
_YOU_CONTROL_SUBTYPE_LIST_RE = re.compile(
    r"^you control an? (?P<first>[A-Z][\w'-]*)(?P<rest>(?: or (?:an? )?[A-Z][\w'-]*)+)$"
)
#: "unless you revealed a Dragon card this way or you control a Dragon" - the
#: follow-up of a reveal land's optional "you may reveal a Dragon card from your
#: hand" (CR 614.12a): tapped unless the reveal happened or the board answers.
REVEALED_OR_CONTROL_RE = re.compile(
    r"^unless you revealed an? (?P<revealed>.+?) card this way "
    r"or you control an? (?P<subtype>[A-Z][\w'-]*)$"
)


def _controlled_matching(game: "Game", entering: CardState, test) -> bool:
    controller = entering.controller
    if controller is None:
        return False
    board = game.computed_board()
    return any(
        test(board.of(permanent))
        for permanent in game.battlefield
        if permanent.controller == controller and permanent.id != entering.id
    )


def read_extra_enters_condition(condition: str) -> EntersCondition | None:
    """The conditions T2 adds to `enters._read_enters_condition`."""
    match = _YOU_CONTROL_QUALIFIED_RE.match(condition)
    if match is not None:
        words = match.group("quals").lower().split()
        card_type = _CARD_TYPES[match.group("type").lower()]
        colors = {_COLOR_WORDS[w] for w in words if w in _COLOR_WORDS}
        legendary = "legendary" in words
        snow = "snow" in words

        def qualified(chars) -> bool:
            return (
                card_type in chars.types
                and (not legendary or Supertype.LEGENDARY in chars.supertypes)
                and (not snow or Supertype.SNOW in chars.supertypes)
                and colors <= set(chars.colors)
            )

        return lambda game, entering: _controlled_matching(game, entering, qualified)

    match = _YOU_CONTROL_SUBTYPE_LIST_RE.match(condition)
    if match is not None:
        subtypes = frozenset(
            {match.group("first"), *re.findall(r"(?:an? )?([A-Z][\w'-]*)", match.group("rest"))}
        )
        return lambda game, entering: _controlled_matching(
            game, entering, lambda chars: bool(subtypes & set(chars.subtypes))
        )
    return None


def reveal_follow_up_subtype(effect: ReplacementEffect) -> str | None:
    """The subtype a reveal land's "or you control a <subtype>" names, or None."""
    match = REVEALED_OR_CONTROL_RE.match((effect.condition or "").strip().rstrip("."))
    return match.group("subtype") if match is not None else None


# --------------------------------------------------------------------------
# Group "<objects> enter tapped" (CR 614.1d)
# --------------------------------------------------------------------------

_PLURAL_TYPES: dict[str, Type | None] = {
    "permanents": None,
    "artifacts": Type.ARTIFACT,
    "creatures": Type.CREATURE,
    "enchantments": Type.ENCHANTMENT,
    "lands": Type.LAND,
    "planeswalkers": Type.PLANESWALKER,
    "battles": Type.BATTLE,
}
_SPLIT_RE = re.compile(r",\s*(?:and\s+|or\s+)?|\s+(?:and|or)\s+")
_SCOPES = (
    (" your opponents control", "opponents"),
    (" enchanted player controls", "enchanted"),
    (" you control", "you"),
)

GroupTest = Callable[["Game", CardState, CardState], bool]


def _noun_test(noun: str) -> Callable[[CardState], bool] | None:
    words = noun.split()
    if not words or words[-1] not in _PLURAL_TYPES:
        return None
    card_type = _PLURAL_TYPES[words[-1]]
    tests: list[Callable[[CardState], bool]] = []
    if card_type is not None:
        tests.append(lambda card, t=card_type: t in card.types)
    for word in words[:-1]:
        if word == "snow":
            tests.append(lambda card: Supertype.SNOW in card.supertypes)
        elif word == "nonbasic":
            tests.append(lambda card: Supertype.BASIC not in card.supertypes)
        elif word.startswith("non-") and len(word) > 4:
            banned = word[4:]
            tests.append(
                lambda card, b=banned: b not in {s.lower() for s in card.subtypes}
                and all(t.value.lower() != b for t in card.types)
            )
        elif word.startswith("non") and word[3:] in _CARD_TYPES:
            banned_type = _CARD_TYPES[word[3:]]
            tests.append(lambda card, b=banned_type: b not in card.types)
        else:
            return None
    return lambda card: all(test(card) for test in tests)


def read_group_subject(subject: str) -> GroupTest | None:
    """"Artifacts, creatures, and lands your opponents control", "Permanents",
    "Non-Phyrexian creatures", "Snow lands your opponents control", "Creatures
    enchanted player controls" as `(game, source, entering) -> bool`, or None
    for any noun this does not read (fail closed rather than drop it)."""
    text = subject.strip().lower()
    scope = "any"
    for suffix, name in _SCOPES:
        if text.endswith(suffix):
            text, scope = text[: -len(suffix)], name
            break
    tests = []
    for noun in _SPLIT_RE.split(text):
        test = _noun_test(noun.strip())
        if test is None:
            return None
        tests.append(test)
    if not tests:
        return None

    def matches(game: "Game", source: CardState, entering: CardState) -> bool:
        controller = entering.controller
        if scope == "opponents" and (controller is None or controller == source.controller):
            return False
        if scope == "you" and controller != source.controller:
            return False
        if scope == "enchanted":
            attachment = getattr(source, "attachment", None)
            if attachment is None or attachment.username != controller:
                return False
        return any(test(entering) for test in tests)

    return matches


def compile_group_enter_tapped(effect: ReplacementEffect) -> CardReplacement | None:
    """A non-self "<objects> enter tapped" static (CR 614.1d) as a replacement
    effect watching every matching permanent as it enters (CR 614.12: judged
    on the object as it would exist on the battlefield)."""
    if effect.self_replacement or effect.condition:
        return None
    test = read_group_subject(effect.subject or "")
    if test is None:
        return None

    def applies(game: "Game", source: CardState, event) -> bool:
        card = event.card
        return event.kind is EventKind.ENTERS_BATTLEFIELD and card is not None and test(
            game, source, card
        )

    def apply(game: "Game", source: CardState, event) -> None:
        event.tapped = True

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


__all__ = [
    "ChoiceKind",
    "compile_group_enter_tapped",
    "read_extra_enters_condition",
    "read_group_subject",
    "reveal_follow_up_subtype",
]
