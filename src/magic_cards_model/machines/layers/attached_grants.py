"""Aura and Equipment statics that read the object they are attached to
(EP-01 round 2, task T5).

Every sentence here is a static ability of an Aura or Equipment whose subject
is "enchanted <thing>" / "equipped creature" - whatever the source is attached
to (CR 303.4b, CR 301.5a), read off `CardState.attached_to` and never off the
board, with an unattached source producing nothing (CR 303.4c, CR 301.5c).
`parse_attached_sentence` is the one entry point, called last by
`parse._parse_layer_sentence_ungated` so a shape another reader already owns
keeps its reader.

The families, each a template and never a card:

- a count-sized pump: "gets +X/+X, where X is the number of <type> cards in
  your graveyard / its controller's graveyard / your hand" and "... where X is
  its mana value", "gets +2/+2 for each Aura and Equipment attached to it"
  (layer 7c, CR 613.4c; the count is recounted on every board computation,
  CR 611.3a, CR 613.5);
- a conditional rider: "gets an additional +2/+2 as long as there are four or
  more card types among cards in your graveyard" (delirium) / "... as long as
  you have no cards in hand" (hellbent). The ability word has no rules meaning
  (CR 207.2c); the condition is the text, read when the effects are built;
- a plain permanent subject: "Enchanted permanent gets +1/+1 and has
  vigilance.", "has indestructible.", "has ward {1}.", "Equipped creature has
  nonbasic landwalk.";
- a type, colour, ability and name rewrite: "Enchanted land is a 2/2 blue
  Elemental creature with flying. It's still a land." (layer 4 adds the types,
  CR 613.1d; layer 5 sets the colour, CR 613.1e; layer 6 grants the keyword,
  CR 613.1f; sublayer 7b sets base power and toughness, CR 613.4b),
  "loses all abilities and has base power and toughness 1/1", "is a colorless
  Food artifact with "..." and loses all other card types and abilities",
  "is a green and white Citizen creature with base power and toughness 1/1
  named ...", "loses all land types and abilities and has "..." ", "is a Demon
  Spirit.", "is legendary.", "is snow.", "loses flying.";
- a quoted ability, which is a layer 6 grant of the quoted text and also goes
  on `CardState.granted_ability_texts` so it is a real activated, mana or
  triggered ability (`attached_quoted_texts`, read by
  `parse.quoted_ability_grants`; CR 113.10a).
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from uuid import UUID

from ...data.subtypes import canonical_subtype
from ...models.card import Color, Supertype, Type
from ...models.card_state import CardState, ChoiceKind
from ...numbers import parse_count
from ._common import _COLOR_WORDS
from .apply import EffectBuilder, LayerContext
from .model import (
    _PERMANENT_CARD_TYPES,
    AddSubtype,
    AddSupertype,
    AddType,
    BecomeACopyOfObject,
    ContinuousEffect,
    CopySublayer,
    CountAttachedWithAnySubtype,
    CountByControllerOfObject,
    CountObjectManaValue,
    FixedCount,
    Layer,
    LoseAllLandTypes,
    Modification,
    SetColors,
    SetCreatureTypes,
    SetName,
    SetPower,
    SetTypesAndSubtypes,
    Sublayer,
    _only,
    _split_and_validate_keywords,
    count_card_types,
    grant_ability,
    lose_all_abilities,
    lose_keyword,
    modify_power_toughness,
    modify_power_toughness_per,
    set_power_toughness,
)

_ATTACHED_SUBJECT = r"(?P<attachment>enchanted|equipped) (?P<noun>[a-z]+)"
_PT = r"(?P<power>[+-](?:\d+|x))/(?P<toughness>[+-](?:\d+|x))"


def _source_line(source: CardState, sentence: str) -> str:
    from .parse import _source_line_for

    return _source_line_for(source, sentence)


def _subject_ok(noun: str) -> bool:
    from .parse import _card_type_word

    return (
        noun in {"permanent", "land"}
        or _card_type_word(noun) is not None
        or (noun.capitalize() in {"Mountain", "Island", "Plains", "Swamp", "Forest"})
    )


def _multiplier(box: str) -> int:
    """`+X` -> 1, `-X` -> -1, `+0`/`-0` -> 0, `+2` -> 2 (a count's multiplier)."""
    sign = -1 if box.startswith("-") else 1
    body = box[1:].lower()
    return 0 if body == "0" else sign * (1 if body == "x" else int(body))


# --------------------------------------------------------------------------
# Counts
# --------------------------------------------------------------------------

_ZONE_COUNT_RE = re.compile(
    r"^the number of (?:(?P<kind>[a-z]+) )?cards in "
    r"(?P<whose>your|its controller's) (?P<zone>graveyard|hand)$",
    re.IGNORECASE,
)
_MANA_VALUE_RE = re.compile(r"^its mana value$", re.IGNORECASE)
_ATTACHED_COUNT_RE = re.compile(
    r"^(?P<subtypes>[a-z]+(?: (?:and|and/or|or) [a-z]+)*) attached to it$", re.IGNORECASE
)

CountFactory = Callable[[CardState, LayerContext], object]


def _card_kinds(kind: str | None) -> tuple[Type, ...] | None:
    """The card types a "<kind> cards" qualifier names - `()` for every card,
    `None` for a qualifier this does not read."""
    from .parse import _card_type_word

    if kind is None:
        return ()
    if kind.lower() == "permanent":
        return tuple(_PERMANENT_CARD_TYPES)
    card_type = _card_type_word(kind)
    return None if card_type is None else (card_type,)


def _count_factory(phrase: str) -> CountFactory | None:
    """A "where X is ..." phrase as a factory taking the source and the layer
    context and returning the `Count` (read at build time for a zone, off the
    asking object for a mana value)."""
    text = phrase.strip().rstrip(".")
    if _MANA_VALUE_RE.fullmatch(text):
        return lambda source, context: CountObjectManaValue()
    match = _ZONE_COUNT_RE.fullmatch(text)
    if match is None:
        return None
    kinds = _card_kinds(match.group("kind"))
    zone = match.group("zone").lower()
    if kinds is None or (zone == "hand" and kinds):
        return None
    yours = match.group("whose").lower() == "your"

    def qualifying(cards: Sequence[CardState]) -> int:
        return sum(1 for card in cards if not kinds or any(kind in card.types for kind in kinds))

    if zone == "hand":
        if yours:
            return lambda source, context: FixedCount(value=context.hand_size_of(source.controller))
        return lambda source, context: CountByControllerOfObject(
            counts=tuple(sorted(context.hand_size_by_player.items()))
        )
    if yours:
        return lambda source, context: FixedCount(
            value=qualifying(context.graveyard_of(source.controller))
        )
    return lambda source, context: CountByControllerOfObject(
        counts=tuple(
            sorted(
                (player, qualifying(cards))
                for player, cards in context.graveyard_by_controller.items()
            )
        )
    )


# --------------------------------------------------------------------------
# Conditions ("as long as ...") read when the effects are built
# --------------------------------------------------------------------------

_CARD_TYPES_AMONG_RE = re.compile(
    r"^there are (?P<n>[a-z0-9]+) or more card types among cards in your graveyard$",
    re.IGNORECASE,
)
_NO_CARDS_IN_HAND_RE = re.compile(r"^you have no cards in hand$", re.IGNORECASE)
_HAND_AT_MOST_RE = re.compile(r"^you have (?P<n>[a-z0-9]+) or fewer cards in hand$", re.IGNORECASE)
_GRAVEYARD_AT_LEAST_RE = re.compile(
    r"^(?:there are|you have) (?P<n>[a-z0-9]+) or more cards in your graveyard$", re.IGNORECASE
)
_ConditionFn = Callable[[CardState, LayerContext], bool]


def _condition(text: str) -> _ConditionFn | None:
    text = text.strip().rstrip(".")
    if match := _CARD_TYPES_AMONG_RE.fullmatch(text):
        n = parse_count(match.group("n"), article=False)
        if n is None:
            return None
        return lambda source, context: (
            count_card_types(context.graveyard_of(source.controller)) >= n
        )
    if _NO_CARDS_IN_HAND_RE.fullmatch(text):
        return lambda source, context: context.hand_size_of(source.controller) == 0
    if match := _HAND_AT_MOST_RE.fullmatch(text):
        n = parse_count(match.group("n"), article=False)
        if n is None:
            return None
        return lambda source, context: context.hand_size_of(source.controller) <= n
    if match := _GRAVEYARD_AT_LEAST_RE.fullmatch(text):
        n = parse_count(match.group("n"), article=False)
        if n is None:
            return None
        return lambda source, context: len(context.graveyard_of(source.controller)) >= n
    return None


# --------------------------------------------------------------------------
# Pumps
# --------------------------------------------------------------------------

_PUMP_WHERE_X_RE = re.compile(
    rf"^{_ATTACHED_SUBJECT} gets {_PT}, where x is (?P<phrase>.+)$", re.IGNORECASE
)
_PUMP_FOR_EACH_RE = re.compile(
    rf"^{_ATTACHED_SUBJECT} gets {_PT} for each (?P<phrase>.+)$", re.IGNORECASE
)
_PUMP_ADDITIONAL_RE = re.compile(
    rf"^{_ATTACHED_SUBJECT} gets an additional {_PT} as long as (?P<condition>.+)$", re.IGNORECASE
)
_PERMANENT_STATIC_RE = re.compile(
    rf"^{_ATTACHED_SUBJECT}(?: gets (?P<pt>[+-]\d+/[+-]\d+))?(?: and)?"
    r"(?: (?:has|have) (?P<keywords>.+))?$",
    re.IGNORECASE,
)


def _pump_per_count_builder(
    factory: CountFactory, power: int, toughness: int, *, subject: str, line: str
) -> EffectBuilder:
    def builder(source, timestamp, targets, context):
        attached = source.attached_to
        if attached is None:
            return []
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: {subject} gets {power:+d}/{toughness:+d} per counted object"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line(source, line),
                selector=_only(attached),
                modification=modify_power_toughness_per(factory(source, context), power, toughness),
            )
        ]

    return builder


def _additional_pump_builder(
    power: int, toughness: int, condition: _ConditionFn, *, subject: str, line: str
) -> EffectBuilder:
    def builder(source, timestamp, targets, context):
        attached = source.attached_to
        if attached is None or not condition(source, context):
            return []
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: {subject} gets an additional {power:+d}/{toughness:+d}"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line(source, line),
                selector=_only(attached),
                modification=modify_power_toughness(power, toughness),
            )
        ]

    return builder


def _parse_pump(sentence: str) -> EffectBuilder | None:
    if match := _PUMP_WHERE_X_RE.fullmatch(sentence):
        if not _subject_ok(match["noun"].lower()):
            return None
        factory = _count_factory(match["phrase"])
        if factory is None:
            return None
        return _pump_per_count_builder(
            factory,
            _multiplier(match["power"]),
            _multiplier(match["toughness"]),
            subject=f"{match['attachment'].lower()} {match['noun'].lower()}",
            line=sentence,
        )
    if match := _PUMP_FOR_EACH_RE.fullmatch(sentence):
        if not _subject_ok(match["noun"].lower()):
            return None
        counted = _ATTACHED_COUNT_RE.fullmatch(match["phrase"].strip().rstrip("."))
        if counted is None:
            return None
        words = [
            canonical_subtype(word)
            for word in re.split(r" (?:and/or|and|or) ", counted["subtypes"], flags=re.IGNORECASE)
        ]
        if any(word is None for word in words):
            return None
        subtypes = tuple(word.lower() for word in words if word is not None)
        return _pump_per_count_builder(
            lambda source, context: CountAttachedWithAnySubtype(subtypes=subtypes),
            _multiplier(match["power"]),
            _multiplier(match["toughness"]),
            subject=f"{match['attachment'].lower()} {match['noun'].lower()}",
            line=sentence,
        )
    if match := _PUMP_ADDITIONAL_RE.fullmatch(sentence):
        if not _subject_ok(match["noun"].lower()):
            return None
        condition = _condition(match["condition"])
        if condition is None:
            return None
        return _additional_pump_builder(
            _multiplier(match["power"]),
            _multiplier(match["toughness"]),
            condition,
            subject=f"{match['attachment'].lower()} {match['noun'].lower()}",
            line=sentence,
        )
    return None


# --------------------------------------------------------------------------
# "Enchanted permanent gets +N/+N and has <keywords>" / "Equipped creature has
# <keywords>" - the creature-only readers' permanent twin
# --------------------------------------------------------------------------

_LANDWALK_RE = re.compile(r"^(?:nonbasic|legendary|snow|artifact) landwalk$", re.IGNORECASE)


def keywords_of(raw: str) -> list[str] | None:
    """`raw` as a keyword list, with the supertype/card-type landwalks
    (CR 702.14a) `_split_and_validate_keywords` does not whitelist."""
    parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", raw.strip())
    if parts and all(_LANDWALK_RE.fullmatch(part.strip()) for part in parts):
        return [part.strip().capitalize() for part in parts]
    return _split_and_validate_keywords(raw)


def _parse_permanent_static(sentence: str) -> EffectBuilder | None:
    match = _PERMANENT_STATIC_RE.fullmatch(sentence.rstrip("."))
    if match is None or not _subject_ok(match["noun"].lower()):
        return None
    if match["pt"] is None and match["keywords"] is None:
        return None
    keywords: list[str] = []
    if match["keywords"] is not None:
        parsed = keywords_of(match["keywords"])
        if parsed is None:
            return None
        keywords = parsed
    power = toughness = 0
    if match["pt"] is not None:
        p, t = match["pt"].split("/")
        power, toughness = int(p), int(t)
    from .parse import _attached_creature_static_builder

    return _attached_creature_static_builder(
        power,
        toughness,
        keywords,
        subject=f"{match['attachment'].lower()} {match['noun'].lower()}",
        line=sentence,
    )


# --------------------------------------------------------------------------
# Type, colour, ability and name rewrites
# --------------------------------------------------------------------------

_QUOTED_REF = re.compile(r"\x00(\d+)\x00")
_CARD_TYPE_WORDS = {
    "creature": Type.CREATURE,
    "artifact": Type.ARTIFACT,
    "land": Type.LAND,
    "enchantment": Type.ENCHANTMENT,
}
_SPLIT_RE = re.compile(r",? and (?:it )?(?=loses |is |are |has |have |can't )", re.IGNORECASE)


@dataclass
class _Change:
    """What one attached rewrite sentence does, by layer."""

    name: str | None = None
    set_types: tuple[Type, ...] | None = None
    set_subtypes: tuple[str, ...] = ()
    add_types: tuple[Type, ...] = ()
    add_subtypes: tuple[str, ...] = ()
    creature_types: tuple[str, ...] | None = None
    supertypes: tuple[Supertype, ...] = ()
    lose_land_types: bool = False
    colors: tuple[Color, ...] | None = None
    lose_abilities: bool = False
    lose_keywords: tuple[str, ...] = ()
    keywords: list[str] = field(default_factory=list)
    quoted: list[str] = field(default_factory=list)
    base_pt: tuple[int, int] | None = None
    base_power: int | None = None
    cant_be_enchanted: bool = False
    copy_of_chosen: bool = False

    def anything(self) -> bool:
        return any(
            (
                self.name,
                self.set_types,
                self.add_types,
                self.add_subtypes,
                self.creature_types,
                self.supertypes,
                self.lose_land_types,
                self.colors is not None,
                self.lose_abilities,
                self.lose_keywords,
                self.keywords,
                self.quoted,
                self.base_pt,
                self.base_power is not None,
                self.cant_be_enchanted,
                self.copy_of_chosen,
            )
        )


def _colors_of(words: list[str]) -> tuple[Color, ...] | None:
    """The colour words at the start of a head: a colour set, `()` for
    colorless, `None` if there is no colour word at all."""
    if words and words[0].lower() == "colorless":
        return ()
    found = [_COLOR_WORDS[word.lower()] for word in words if word.lower() in _COLOR_WORDS]
    return tuple(found) if found else None


def _read_is_clause(clause: str, quotes: list[str], change: _Change) -> bool:
    """`is a[n] ...` / `is legendary` / `is snow`, folded into `change`."""
    body = clause.strip().rstrip(".")
    lowered = body.lower()
    if lowered == "a copy of the chosen creature":
        change.copy_of_chosen = True
        return True
    if lowered in {"legendary", "snow"}:
        change.supertypes += (Supertype.LEGENDARY if lowered == "legendary" else Supertype.SNOW,)
        return True
    in_addition = False
    for marker in (
        r"[,.]? ?(?:and )?(?:it|that)'s still an? land",
        r" that's still an? land",
        r"\. it's still an? land",
    ):
        replaced = re.sub(marker + r"$", "", body, flags=re.IGNORECASE)
        if replaced != body:
            body, in_addition = replaced, True
            break
    named = re.search(r" named (?P<name>[A-Z][^\x00]*?)$", body)
    if named:
        change.name = named["name"].strip()
        body = body[: named.start()]
    # "... and Q0 named X" / "... with Q0": quoted abilities
    for quoted in re.finditer(r"\x00(\d+)\x00", body):
        change.quoted.append(quotes[int(quoted[1])])
    body = re.sub(r"(?:,? ?(?:and|with) )?\x00\d+\x00,?", "", body).strip()
    body = re.sub(r"\s+", " ", body)
    pt = re.search(r" with base power and toughness (\d+)/(\d+)$", body)
    if pt:
        change.base_pt = (int(pt[1]), int(pt[2]))
        body = body[: pt.start()]
    with_keywords = re.search(
        r" with (?P<kw>[a-z ,]+?)(?: and base power and toughness (\d+)/(\d+))?$", body
    )
    if with_keywords and with_keywords["kw"].lower() not in {"base power and toughness"}:
        parsed = keywords_of(with_keywords["kw"])
        if parsed is None:
            return False
        change.keywords.extend(parsed)
        if with_keywords[2]:
            change.base_pt = (int(with_keywords[2]), int(with_keywords[3]))
        body = body[: with_keywords.start()]
    body = re.sub(r"^(?:an?|the) ", "", body, flags=re.IGNORECASE)
    tokens = body.split()
    if tokens and re.fullmatch(r"\d+/\d+", tokens[0]):
        change.base_pt = tuple(int(n) for n in tokens[0].split("/"))  # type: ignore[assignment]
        tokens = tokens[1:]
    # colour words, possibly joined by "and"
    color_words: list[str] = []
    while tokens and (
        tokens[0].lower() in _COLOR_WORDS
        or tokens[0].lower() == "colorless"
        or (
            tokens[0].lower() == "and"
            and color_words
            and len(tokens) > 1
            and tokens[1].lower() in _COLOR_WORDS
        )
    ):
        word = tokens.pop(0)
        if word.lower() != "and":
            color_words.append(word)
    if color_words:
        change.colors = _colors_of(color_words)
    card_types: list[Type] = []
    subtypes: list[str] = []
    for token in tokens:
        lowered_token = token.lower()
        if lowered_token in _CARD_TYPE_WORDS:
            card_types.append(_CARD_TYPE_WORDS[lowered_token])
        elif (subtype := canonical_subtype(token)) is not None:
            subtypes.append(subtype)
        else:
            return False
    types = tuple(card_types)
    subs = tuple(word.capitalize() for word in subtypes)
    if in_addition:
        change.add_types, change.add_subtypes = types, subs
    elif types:
        change.set_types, change.set_subtypes = types, subs
    elif subs:
        change.creature_types = subs
    return True


def _read_has_clause(clause: str, quotes: list[str], change: _Change) -> bool:
    body = clause.strip().rstrip(".")
    if match := re.fullmatch(r"base power (\d+)", body, re.IGNORECASE):
        change.base_power = int(match[1])
        return True
    if match := re.fullmatch(r"base power and toughness (\d+)/(\d+)", body, re.IGNORECASE):
        change.base_pt = (int(match[1]), int(match[2]))
        return True
    pieces = re.split(r",? and |, ", body)
    for piece in pieces:
        piece = piece.strip()
        quote = _QUOTED_REF.fullmatch(piece)
        if quote:
            change.quoted.append(quotes[int(quote[1])])
            continue
        if match := re.fullmatch(r"base power (\d+)", piece, re.IGNORECASE):
            change.base_power = int(match[1])
            continue
        parsed = keywords_of(piece)
        if parsed is None:
            return False
        change.keywords.extend(parsed)
    return True


def _read_loses_clause(clause: str, change: _Change) -> bool:
    body = clause.strip().rstrip(".").lower()
    if body in {"all abilities", "all other abilities"}:
        change.lose_abilities = True
        return True
    if body == "all land types and abilities":
        change.lose_land_types = change.lose_abilities = True
        return True
    if body == "all other card types and abilities":
        change.lose_abilities = True
        return True
    parsed = keywords_of(body)
    if parsed is None:
        return False
    change.lose_keywords += tuple(word.lower() for word in parsed)
    return True


NO_OTHER_AURAS = "can't be enchanted by other auras"


def _read_change(sentence: str) -> tuple[_Change, str, list[str]] | None:
    """A rewrite sentence as `(change, subject, quoted texts)`, or `None`."""
    quotes: list[str] = []

    def stash(match: re.Match[str]) -> str:
        quotes.append(match["text"])
        return f"\x00{len(quotes) - 1}\x00"

    text = re.sub(r'"(?P<text>[^"]+)"', stash, sentence.rstrip())
    subject = re.match(
        rf"^{_ATTACHED_SUBJECT} (?=(?:loses|is|are|has|have) )", text, flags=re.IGNORECASE
    )
    if subject is None or not _subject_ok(subject["noun"].lower()):
        return None
    rest = text[subject.end() :].rstrip(".")
    change = _Change()
    for clause in _SPLIT_RE.split(rest):
        clause = clause.strip()
        verb, _, tail = clause.partition(" ")
        verb = verb.lower()
        if verb == "loses":
            ok = _read_loses_clause(tail, change)
        elif verb in {"is", "are"}:
            ok = _read_is_clause(tail, quotes, change)
        elif verb in {"has", "have"}:
            ok = _read_has_clause(tail, quotes, change)
        elif clause.lower() == NO_OTHER_AURAS:
            change.cant_be_enchanted = ok = True
        else:
            ok = False
        if not ok:
            return None
    if not change.anything():
        return None
    return change, f"{subject['attachment'].lower()} {subject['noun'].lower()}", list(change.quoted)


def _change_builder(change: _Change, *, subject: str, line: str) -> EffectBuilder:
    def builder(source, timestamp, targets, context):
        attached = source.attached_to
        if attached is None:
            return []
        selector = _only(attached)
        ability = _source_line(source, line)
        effects: list[ContinuousEffect] = []

        def add(layer: Layer, modification: Modification, what: str, sublayer=None) -> None:
            effects.append(
                ContinuousEffect(
                    description=f"{source.name}: {subject} {what}",
                    layer=layer,
                    sublayer=sublayer,
                    timestamp=timestamp,
                    order=len(effects),
                    source_id=source.id,
                    source_ability=ability,
                    selector=selector,
                    modification=modification,
                )
            )

        chosen = source.choice
        if change.copy_of_chosen and chosen is not None and chosen.kind is ChoiceKind.OBJECT:
            add(
                Layer.COPY,
                BecomeACopyOfObject(object_id=UUID(chosen.value)),
                "is a copy of the chosen creature",
                CopySublayer.COPIABLE,
            )
        if change.name is not None:
            add(Layer.TEXT, SetName(name=change.name), f"is named {change.name}")
        if change.lose_land_types:
            add(Layer.TYPE, LoseAllLandTypes(), "loses all land types")
        if change.set_types is not None:
            add(
                Layer.TYPE,
                SetTypesAndSubtypes(types=change.set_types, subtypes=change.set_subtypes),
                "has its card types and subtypes set",
            )
        if change.creature_types is not None:
            add(
                Layer.TYPE,
                SetCreatureTypes(subtypes=change.creature_types),
                "has its creature types set",
            )
        if change.add_types or change.add_subtypes:
            for card_type in change.add_types:
                add(Layer.TYPE, AddType(card_type=card_type), f"is also a {card_type.value}")
            for word in change.add_subtypes:
                add(Layer.TYPE, AddSubtype(subtype=word), f"is also a {word}")
        for supertype in change.supertypes:
            add(Layer.TYPE, AddSupertype(supertype=supertype), f"is {supertype.value}")
        if change.colors is not None:
            add(Layer.COLOR, SetColors(colors=change.colors), "has its colour set")
        if change.lose_abilities:
            add(Layer.ABILITY, lose_all_abilities, "loses all abilities")
        for keyword in change.lose_keywords:
            add(Layer.ABILITY, lose_keyword(keyword), f"loses {keyword}")
        for keyword in change.keywords:
            add(Layer.ABILITY, grant_ability(keyword), f"has {keyword}")
        for text in change.quoted:
            add(Layer.ABILITY, grant_ability(text), f'has "{text}"')
        if change.base_pt is not None:
            add(
                Layer.POWER_TOUGHNESS,
                set_power_toughness(*change.base_pt),
                f"has base power and toughness {change.base_pt[0]}/{change.base_pt[1]}",
                Sublayer.SET,
            )
        if change.base_power is not None:
            add(
                Layer.POWER_TOUGHNESS,
                SetPower(power=change.base_power),
                f"has base power {change.base_power}",
                Sublayer.SET,
            )
        return effects

    return builder


def _parse_change(sentence: str) -> EffectBuilder | None:
    read = _read_change(sentence)
    if read is None:
        return None
    change, subject, _ = read
    return _change_builder(change, subject=subject, line=sentence)


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------


@functools.lru_cache(maxsize=4096)
def parse_attached_sentence(sentence: str) -> EffectBuilder | None:
    """`sentence` as one of the attached shapes above, or `None`."""
    lowered = sentence.lower()
    if "enchanted " not in lowered and "equipped " not in lowered:
        return None
    text = sentence.strip()
    return _parse_pump(text) or _parse_permanent_static(text) or _parse_change(text)


@functools.lru_cache(maxsize=4096)
def attached_quoted_texts(sentence: str) -> tuple[str, ...]:
    """The quoted abilities an attached rewrite sentence grants (empty for any
    other sentence) - what `parse.quoted_ability_grants` stores on the
    enchanted permanent so each is a working ability (CR 113.10a)."""
    lowered = sentence.lower()
    if '"' not in sentence or ("enchanted " not in lowered and "equipped " not in lowered):
        return ()
    read = _read_change(sentence.strip())
    return tuple(read[2]) if read is not None else ()


def cant_be_enchanted_by_other_auras_refusal(game, aura: CardState, target) -> str | None:
    """Why `aura` may not be attached to `target` because of "Enchanted land
    has indestructible and can't be enchanted by other Auras." (Consecrate
    Land), or None.

    CR 303.4: "Other effects can limit what a permanent can be enchanted by."
    The limit is the static ability of an Aura attached to `target` that is
    not `aura` itself (that is what "other" means), read off the computed
    board so an Aura that has lost its abilities limits nothing (CR 613.1f).
    `keywords.why_cannot_enchant` asks this for the cast announcement
    (CR 303.4a) and for CR 303.4c's state-based action alike, so an Aura
    already attached when the limit arrives is put into the graveyard.
    """
    if game is None or not isinstance(target, CardState):
        return None
    board = None
    for source in game.battlefield:
        if source.id == aura.id or source.attached_to != target.id:
            continue
        if NO_OTHER_AURAS not in (source.oracle_text or "").lower():
            continue
        board = board if board is not None else game.computed_board()
        if any(NO_OTHER_AURAS in line.lower() for line in board.of(source).abilities):
            return (
                f"{target.name} can't be enchanted by other Auras: {source.name} says "
                f'"can\'t be enchanted by other Auras" (CR 303.4)'
            )
    return None
