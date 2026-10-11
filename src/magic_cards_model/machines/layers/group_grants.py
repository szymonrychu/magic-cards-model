"""EP-01 round 2, task T1: static sentences over a *group* of permanents,
read generally (CR 611.3, CR 613.1, CR 613.4c).

One subject grammar (`parse_group`) feeds four predicates, so "Other green
creatures you control get +1/+1", "All Rats have fear", "Artifacts you
control have indestructible", "All lands are Islands in addition to their
other types", "All nonland permanents are legendary", "Non-Archon creatures
have base power and toughness 1/1" and "Creatures you control of the chosen
type get +1/+1" are not seven regexes but one subject and one predicate each.
The subject becomes a `GroupMatch` selector that is re-asked on every CR 613.5
computation (CR 611.3a: a static ability's effect "isn't 'locked in'").

Run last: `parse.py`'s `_parse_static_layer_sentence` falls through to
`parse_group_static_sentence` only when none of the older, narrower shapes
read the sentence, so nothing they already read changes.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from ...data.subtypes import subtype_vocabulary
from ...models.card import Color, Supertype, Type
from ...models.card_state import CardState
from .model import (
    AddEveryCreatureType,
    AddSupertype,
    ContinuousEffect,
    GroupMatch,
    Layer,
    LoseAllAbilities,
    Only,
    Sublayer,
    add_subtype,
    add_type,
    grant_ability,
    modify_power_toughness,
    set_power_toughness,
)

if TYPE_CHECKING:
    from .apply import LayerContext

_GROUP_COLORS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}
_GROUP_BASIC_LAND_TYPES = {
    "plains": "Plains",
    "island": "Island",
    "swamp": "Swamp",
    "mountain": "Mountain",
    "forest": "Forest",
}
_GROUP_TYPE_WORDS = {
    "creature": Type.CREATURE,
    "artifact": Type.ARTIFACT,
    "enchantment": Type.ENCHANTMENT,
    "land": Type.LAND,
    "planeswalker": Type.PLANESWALKER,
    "battle": Type.BATTLE,
}

#: Cheap lowercase gate: a group sentence names one of these verbs.
_VERB_RE = re.compile(r" (?:gets?|have|has|are|is) ")

_SUFFIX_CONTROL_RE = re.compile(r" (?P<who>you control|your opponents control)$")
_SUFFIX_CHOSEN_RE = re.compile(r" of the chosen type$")
_SUFFIX_COUNTER_RE = re.compile(r" with (?:an? |one or more )?(?P<kind>[a-z+/\-0-9]+) counters? on (?:them|it)$")
_SUFFIX_KEYWORD_RE = re.compile(r" (?P<how>with|without) (?P<keyword>[a-z]+)$")


def _singular(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word == "fungi":
        return "fungus"
    return word[:-1] if word.endswith("s") else word


@functools.cache
def parse_group(subject: str) -> dict[str, Any] | None:
    """The `GroupMatch` clauses a printed group subject names, plus the three
    source-relative flags (`other`, `chosen`) the builder resolves - or `None`
    if any word is not understood (fail closed, never a guessed group)."""
    text = subject.strip().lower()
    for quantifier in ("all ", "each "):
        if text.startswith(quantifier):
            text = text[len(quantifier) :]
    fields: dict[str, Any] = {"scope": "any"}
    chosen = False
    changed = True
    while changed:
        changed = False
        if match := _SUFFIX_CONTROL_RE.search(text):
            fields["scope"] = "you" if match["who"] == "you control" else "opponents"
            text = text[: match.start()]
            changed = True
        elif match := _SUFFIX_CHOSEN_RE.search(text):
            chosen = True
            text = text[: match.start()]
            changed = True
        elif match := _SUFFIX_COUNTER_RE.search(text):
            fields["with_counter"] = match["kind"]
            text = text[: match.start()]
            changed = True
        elif match := _SUFFIX_KEYWORD_RE.search(text):
            key = "with_keyword" if match["how"] == "with" else "without_keyword"
            fields[key] = match["keyword"]
            text = text[: match.start()]
            changed = True
    other = False
    words = text.split()
    if words and words[0] == "other":
        other = True
        words = words[1:]
    if not words:
        return None
    all_types: list[Type] = []
    any_types: list[Type] = []
    not_types: list[Type] = []
    any_subtypes: list[str] = []
    not_subtypes: list[str] = []
    any_colors: list[Color] = []
    not_colors: list[Color] = []
    vocabulary = subtype_vocabulary()
    joined = False
    for word in words:
        if word == "and":
            joined = True
            continue
        if word in _GROUP_COLORS:
            any_colors.append(_GROUP_COLORS[word])
        elif word == "colorless":
            fields["colorless"] = True
        elif word in ("legendary", "nonlegendary"):
            fields["legendary"] = word == "legendary"
        elif word == "nontoken":
            fields["token"] = False
        elif word in ("token", "tokens"):
            fields["token"] = True
        elif word == "permanents" or word == "permanent":
            pass
        elif word.startswith("non"):
            rest = word[3:].lstrip("-")
            if rest in _GROUP_COLORS:
                not_colors.append(_GROUP_COLORS[rest])
            elif rest in _GROUP_TYPE_WORDS:
                not_types.append(_GROUP_TYPE_WORDS[rest])
            elif _singular(rest) in vocabulary:
                not_subtypes.append(_singular(rest))
            else:
                return None
        elif _singular(word) in _GROUP_TYPE_WORDS:
            card_type = _GROUP_TYPE_WORDS[_singular(word)]
            (any_types if joined else all_types).append(card_type)
            if joined and all_types:
                any_types.insert(0, all_types.pop())
        elif _singular(word) in vocabulary:
            any_subtypes.append(_singular(word))
        else:
            return None
        joined = False
    fields["all_types"] = tuple(all_types)
    fields["any_types"] = tuple(any_types)
    fields["not_types"] = tuple(not_types)
    fields["any_subtypes"] = tuple(any_subtypes)
    fields["not_subtypes"] = tuple(not_subtypes)
    fields["any_colors"] = tuple(any_colors)
    fields["not_colors"] = tuple(not_colors)
    fields["other"] = other
    fields["chosen"] = chosen
    return fields


def group_selector(spec: dict[str, Any], source: CardState) -> GroupMatch:
    """`spec` (from `parse_group`) bound to `source`: whose permanents, the
    source itself excluded for "other", and the chosen creature type read off
    the source's CR 614.12a choice."""
    from .parse import chosen_creature_type_of

    fields = {key: value for key, value in spec.items() if key not in ("other", "chosen")}
    chosen_missing = False
    if spec["chosen"]:
        chosen_type = chosen_creature_type_of(source)
        if chosen_type is None:
            chosen_missing = True
        else:
            fields["any_subtypes"] = (*fields["any_subtypes"], chosen_type)
    return GroupMatch(
        username=source.controller,
        other_than=source.id if spec["other"] else None,
        empty_if_unset=chosen_missing,
        **fields,
    )


def _split_keywords(raw: str) -> list[str] | None:
    from .model import _split_and_validate_keywords

    return _split_and_validate_keywords(raw)


_GROUP_PUMP_RE = re.compile(
    r"^(?P<subject>.+?) gets? (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)"
    r"(?: and (?:have|has) (?P<keywords>.+))?$"
)
_LOSE_ALL_RE = re.compile(
    r"^(?P<subject>.+?) lose all abilities(?: and have base power and toughness "
    r"(?P<power>\d+)/(?P<toughness>\d+))?$"
)
_HAND_PUMP_RE = re.compile(
    r"^(?P<subject>.+?) gets? (?P<p>[+-](?:x|0))/(?P<t>[+-](?:x|0)), "
    r"where x is the number of cards in your hand$"
)
_GROUP_GRANT_RE = re.compile(r"^(?P<subject>.+?) (?:have|has) (?P<keywords>.+)$")
_GROUP_BASE_PT_RE = re.compile(
    r"^(?P<subject>.+?) (?:have|has) base power and toughness (?P<power>\d+)/(?P<toughness>\d+)$"
)
_GROUP_ARE_RE = re.compile(
    r"^(?P<subject>.+?) (?:are|is) (?P<tail>.+?)"
    r"(?: in addition to (?:their|its) other (?:creature )?types)$"
)
_ARE_LEGENDARY_RE = re.compile(r"^(?P<subject>.+?) (?:are|is) legendary$")
_GROUP_SELF_RE = re.compile(r"^this (?:creature|permanent|artifact|enchantment|land|token)$")
_SELF_ALSO_RE = re.compile(
    r"^this (?:creature|permanent|artifact|enchantment|land|token) is also (?:an? )?(?P<tail>.+)$"
)


def _effects(
    source: CardState,
    timestamp: int,
    line: str,
    selector: Any,
    description: str,
    parts: Sequence[tuple[Layer, Sublayer | None, Any]],
) -> list[ContinuousEffect]:
    from .parse import _source_line_for

    ability = _source_line_for(source, line)
    return [
        ContinuousEffect(
            description=f"{source.name}: {description}",
            layer=layer,
            sublayer=sublayer,
            timestamp=timestamp,
            order=order,
            source_id=source.id,
            source_ability=ability,
            selector=selector,
            modification=modification,
        )
        for order, (layer, sublayer, modification) in enumerate(parts)
    ]


#: A legend's bare first word is a CR 201.5c self-reference, so "Sliver
#: Hivelord"'s own "Sliver creatures you control have ..." reaches the parser
#: as "this permanent creatures you control": the word was the creature type
#: (CR 205.3m), not the card naming itself. "this permanent" followed by a
#: plural noun can never be a self-reference, so it is read back as the
#: source's first name word.
_SELF_WORD_FOR_TYPE_RE = re.compile(r"\bthis permanent(?= [a-z]+s\b)")


def _subject_selector(subject: str, source: CardState) -> Any | None:
    if _GROUP_SELF_RE.fullmatch(subject.strip().lower()):
        return Only(card_id=source.id)
    subject = _SELF_WORD_FOR_TYPE_RE.sub(source.name.split()[0].lower(), subject)
    spec = parse_group(subject)
    return None if spec is None else group_selector(spec, source)


def _type_parts(tail: str) -> list[tuple[Layer, Sublayer | None, Any]] | None:
    """Layer 4 additions (CR 613.1d, CR 205.1b) for "Islands", "artifacts",
    "Clerics, Rogues and Wizards", "every creature type"."""
    cleaned = tail.strip().lower().removeprefix("an ").removeprefix("a ")
    if cleaned in ("every creature type", "all creature types"):
        return [(Layer.TYPE, None, AddEveryCreatureType())]
    parts: list[tuple[Layer, Sublayer | None, Any]] = []
    vocabulary = subtype_vocabulary()
    for word in re.split(r",\s*(?:and\s+)?|\s+and\s+", cleaned):
        word = word.strip().removeprefix("a ").removeprefix("an ")
        if not word:
            return None
        singular = _singular(word)
        if singular in _GROUP_BASIC_LAND_TYPES:
            from ._common import BASIC_LAND_TYPES

            name = _GROUP_BASIC_LAND_TYPES[singular]
            parts.append((Layer.TYPE, None, add_subtype(name, BASIC_LAND_TYPES[name])))
        elif singular in _GROUP_TYPE_WORDS:
            parts.append((Layer.TYPE, None, add_type(_GROUP_TYPE_WORDS[singular])))
        elif singular in vocabulary:
            parts.append((Layer.TYPE, None, add_subtype(singular.title())))
        else:
            return None
    return parts or None


def parse_group_static_sentence(sentence: str):
    """The builder for one static group sentence, or `None` (see the module
    docstring)."""
    text = sentence.strip().rstrip(".")
    lowered = text.lower()
    if not _VERB_RE.search(lowered) or '"' in text:
        return None
    if match := _LOSE_ALL_RE.fullmatch(lowered):
        if _subject_ok(match["subject"]) is False:
            return None
        parts: list[tuple[Layer, Sublayer | None, Any]] = [
            (Layer.ABILITY, None, LoseAllAbilities())
        ]
        if match["power"] is not None:
            parts.append(
                (
                    Layer.POWER_TOUGHNESS,
                    Sublayer.SET,
                    set_power_toughness(int(match["power"]), int(match["toughness"])),
                )
            )
        return _builder(sentence, match["subject"], "lose all abilities", lambda: parts)
    if match := _SELF_ALSO_RE.fullmatch(lowered):
        parts = _type_parts(match["tail"])
        if parts is None:
            return None
        return _builder(sentence, "this creature", f"is also {match['tail']}", lambda: parts)
    if match := _GROUP_BASE_PT_RE.fullmatch(lowered):
        power, toughness = int(match["power"]), int(match["toughness"])
        subject = match["subject"]
        if _subject_ok(subject) is False:
            return None
        return _builder(
            sentence,
            subject,
            f"have base P/T {power}/{toughness}",
            lambda: [(Layer.POWER_TOUGHNESS, Sublayer.SET, set_power_toughness(power, toughness))],
        )
    if match := _HAND_PUMP_RE.fullmatch(lowered):
        if _subject_ok(match["subject"]) is False:
            return None
        return _hand_pump_builder(sentence, match["subject"], match["p"], match["t"])
    if match := _GROUP_PUMP_RE.fullmatch(lowered):
        power, toughness = int(match["power"]), int(match["toughness"])
        keywords: list[str] = []
        if match["keywords"]:
            read = _split_keywords(match["keywords"])
            if read is None:
                return None
            keywords = read
        if _subject_ok(match["subject"]) is False:
            return None
        return _builder(
            sentence,
            match["subject"],
            f"get {power:+d}/{toughness:+d}",
            lambda: [
                (
                    Layer.POWER_TOUGHNESS,
                    Sublayer.MODIFY,
                    modify_power_toughness(power, toughness),
                ),
                *[(Layer.ABILITY, None, grant_ability(keyword)) for keyword in keywords],
            ],
        )
    if match := _ARE_LEGENDARY_RE.fullmatch(lowered):
        if _subject_ok(match["subject"]) is False:
            return None
        return _builder(
            sentence,
            match["subject"],
            "are legendary",
            lambda: [(Layer.TYPE, None, AddSupertype(supertype=Supertype.LEGENDARY))],
        )
    if match := _GROUP_ARE_RE.fullmatch(lowered):
        parts = _type_parts(match["tail"])
        if parts is None or _subject_ok(match["subject"]) is False:
            return None
        return _builder(sentence, match["subject"], f"are {match['tail']}", lambda: parts)
    if match := _GROUP_GRANT_RE.fullmatch(lowered):
        if match["keywords"].startswith(("base power", "all ")):
            return None
        keywords = _split_keywords(match["keywords"])
        if keywords is None or _subject_ok(match["subject"]) is False:
            return None
        return _builder(
            sentence,
            match["subject"],
            f"have {', '.join(keywords)}",
            lambda: [(Layer.ABILITY, None, grant_ability(keyword)) for keyword in keywords],
        )
    return None


def _subject_ok(subject: str) -> bool:
    if _GROUP_SELF_RE.fullmatch(subject.strip().lower()):
        return True
    return parse_group(_SELF_WORD_FOR_TYPE_RE.sub("human", subject)) is not None


def _builder(sentence: str, subject: str, what: str, parts):
    def build(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector = _subject_selector(subject, source)
        if selector is None:
            return []
        return _effects(source, timestamp, sentence, selector, f"{subject} {what}", parts())

    return build


def _hand_pump_builder(sentence: str, subject: str, power: str, toughness: str):
    """ "... get -X/-0, where X is the number of cards in your hand" (CR 613.4c):
    X is read from the hand every time the effects are rebuilt (CR 613.5), so
    it follows the hand size continuously."""

    def amount(token: str, size: int) -> int:
        return 0 if token[1] == "0" else (size if token[0] == "+" else -size)

    def build(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector = _subject_selector(subject, source)
        if selector is None:
            return []
        size = context.hand_size_of(source.controller)
        return _effects(
            source,
            timestamp,
            sentence,
            selector,
            f"{subject} get {amount(power, size):+d}/{amount(toughness, size):+d}",
            [
                (
                    Layer.POWER_TOUGHNESS,
                    Sublayer.MODIFY,
                    modify_power_toughness(amount(power, size), amount(toughness, size)),
                )
            ],
        )

    return build
