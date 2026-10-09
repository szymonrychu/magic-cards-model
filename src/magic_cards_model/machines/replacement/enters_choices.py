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
from ...models.card_state import CardState, Choice, ChoiceKind
from ..decisions import Decision, DecisionKind, source_id_of
from .model import Apply, CardReplacement, EventKind, ReplaceableEvent, ReplacementEffect

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


# --------------------------------------------------------------------------
# "As [this] enters, choose ..." (CR 614.1c, CR 614.12a)
# --------------------------------------------------------------------------

#: CR 300.1's card types, the closed universe a "card type" answer comes from.
CARD_TYPE_OPTIONS = (
    "artifact",
    "battle",
    "creature",
    "enchantment",
    "instant",
    "kindred",
    "land",
    "planeswalker",
    "sorcery",
)
_COLOR_WORD_OPTIONS = ("white", "blue", "black", "red", "green")

_CHOOSE_MODE_RE = re.compile(r"^choose (?P<opts>[A-Z][\w'-]*(?:, [A-Z][\w'-]*)*(?:,? or [A-Z][\w'-]*)+)$")
_CHOOSE_PHRASES_RE = re.compile(
    r"^choose (?P<opts>(?:white|blue|black|red|green) [A-Z]\w+(?:, (?:white|blue|black|red|green) [A-Z]\w+)*"
    r",? or (?:white|blue|black|red|green) [A-Z]\w+)$"
)
_CHOOSE_TYPE_LIST_RE = re.compile(
    r"^choose (?P<opts>(?:artifact|battle|creature|enchantment|instant|land|planeswalker|sorcery)"
    r"(?:, (?:artifact|battle|creature|enchantment|instant|land|planeswalker|sorcery))*"
    r",? or (?:artifact|battle|creature|enchantment|instant|land|planeswalker|sorcery))$"
)
_CHOOSE_CARD_TYPE_RE = re.compile(
    r"^(?:look at an opponent's hand, then )?choose a card type(?: other than (?P<ex>creature(?: or land)?))?$"
)
_CHOOSE_NUMBER_RE = re.compile(r"^choose a number(?: between (?P<lo>\d+) and (?P<hi>\d+))?$")
_LOOK_THEN_NAME_RE = re.compile(r"^look at an opponent's hand, then choose any card name$")


def _split_options(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in re.split(r",\s*(?:or\s+)?|\s+or\s+", text) if part.strip())


def _ask_quality(
    kind: ChoiceKind,
    options: tuple[str, ...],
    prompt: str,
    card_name: str,
    *,
    look_at_opponent_hand: bool = False,
    validator: Callable[[str], str | None] | None = None,
) -> Apply:
    """One CR 614.12a choice, asked of the entering permanent's controller
    through `CHOOSE_A_QUALITY` and recorded on `CardState.choice`. An answer
    outside `options` (when the rules enumerate them) or refused by
    `validator` raises, as the existing quality choices do."""

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        who = source.controller if source is not None else None
        if who is None:
            return
        seen: tuple = ()
        if look_at_opponent_hand:
            # "Look at an opponent's hand": the cards are shown to the chooser
            # alone (they are carried on the question, not revealed to the table).
            seen = tuple(
                card.id
                for opponent in game.players_in_game
                if opponent.username != who
                for card in game.player(opponent.username).hand
            )
        decision = Decision(
            kind=DecisionKind.CHOOSE_A_QUALITY,
            player=who,
            prompt=prompt,
            source=card_name,
            source_id=source_id_of(source),
            options=options,
            quality=kind.value,
            cards=seen,
        )
        value = game.ask(decision)
        assert isinstance(value, str)
        if options:
            matched = next((o for o in options if o.lower() == value.lower()), None)
            if matched is None:
                raise ValueError(f"{card_name}: {value!r} is not one of {', '.join(options)}")
            value = matched
        if validator is not None and (refusal := validator(value)) is not None:
            raise ValueError(f"{card_name}: {refusal}")
        source.choice = Choice(kind=kind, value=value)

    return apply


def _number_validator(low: int | None, high: int | None) -> Callable[[str], str | None]:
    def check(value: str) -> str | None:
        if not value.isdigit():
            return f"{value!r} is not a number"
        number = int(value)
        if low is not None and not low <= number <= (high if high is not None else number):
            return f"{number} is not between {low} and {high}"
        return None

    return check


def enters_choice_apply(effect: ReplacementEffect, card_name: str) -> Apply | None:
    """What an "As [this] enters, choose ..." sentence of the shapes T2 adds does
    as the permanent enters, or None when no shape here reads it."""
    text = (effect.replacement or "").strip().rstrip(".")
    match = _CHOOSE_PHRASES_RE.match(text) or _CHOOSE_MODE_RE.match(text)
    if match is not None:
        options = _split_options(match.group("opts"))
        return _ask_quality(
            ChoiceKind.MODE, options, f"choose {', '.join(options)}", card_name
        )
    match = _CHOOSE_TYPE_LIST_RE.match(text)
    if match is not None:
        return _ask_quality(
            ChoiceKind.CARD_TYPE,
            _split_options(match.group("opts")),
            "choose a card type",
            card_name,
        )
    match = _CHOOSE_CARD_TYPE_RE.match(text)
    if match is not None:
        excluded = set(_split_options(match.group("ex") or ""))
        options = tuple(t for t in CARD_TYPE_OPTIONS if t not in excluded)
        return _ask_quality(
            ChoiceKind.CARD_TYPE,
            options,
            "choose a card type",
            card_name,
            look_at_opponent_hand=text.startswith("look at"),
        )
    match = _CHOOSE_NUMBER_RE.match(text)
    if match is not None:
        low = int(match.group("lo")) if match.group("lo") else None
        high = int(match.group("hi")) if match.group("hi") else None
        options = tuple(str(n) for n in range(low, high + 1)) if low is not None else ()
        return _ask_quality(
            ChoiceKind.NUMBER,
            options,
            "choose a number",
            card_name,
            validator=_number_validator(low, high),
        )
    if text == "choose a planeswalker type":
        return _ask_quality(
            ChoiceKind.PLANESWALKER_TYPE,
            (),
            "choose a planeswalker type",
            card_name,
            validator=lambda v: None if v[:1].isupper() and v.isalpha() else f"{v!r} is not a planeswalker type",
        )
    if text == "choose a color word":
        return _ask_quality(ChoiceKind.COLOR_WORD, _COLOR_WORD_OPTIONS, "choose a color word", card_name)
    if _LOOK_THEN_NAME_RE.match(text):
        return _ask_quality(
            ChoiceKind.CARD_NAME, (), "choose a card name", card_name, look_at_opponent_hand=True
        )
    return None


__all__ = [
    "ChoiceKind",
    "enters_choice_apply",
    "compile_group_enter_tapped",
    "read_extra_enters_condition",
    "read_group_subject",
    "reveal_follow_up_subtype",
]
