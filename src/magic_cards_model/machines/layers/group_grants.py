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
from ...models.card_state import CANT_HAVE_KIND_COUNTERS_TEXT, LETHAL_BY_POWER_TEXT, CardState
from .model import (
    AddEveryCreatureType,
    AddSupertype,
    ContinuousEffect,
    GroupMatch,
    Layer,
    LoseAllAbilities,
    Only,
    SetCreatureTypes,
    Sublayer,
    add_subtype,
    add_type,
    grant_ability,
    grant_ability_instance,
    grant_keyword,
    lose_keyword,
    modify_power_toughness,
    set_basic_land_type,
    set_colors,
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
_VERB_RE = re.compile(r" (?:gets?|have|has|are|is|loses?) ")

_NAMED_RE = re.compile(r"^(?P<head>.+?) named (?P<names>.+)$")
_SUFFIX_CONTROL_RE = re.compile(r" (?P<who>you control|your opponents control)$")
_SUFFIX_CHOSEN_RE = re.compile(r" of the chosen type$")
_SUFFIX_COUNTER_RE = re.compile(
    r" with (?:an? |one or more )?(?P<kind>[a-z+/\-0-9]+) counters? on (?:them|it)$"
)
_SUFFIX_NO_COUNTER_RE = re.compile(
    r" without (?:an? )?(?P<kind>[a-z+/\-0-9]+) counters? on (?:them|it)$"
)
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
    if named := _NAMED_RE.fullmatch(text):
        # "Equipment named Sword of Kaldra, Shield of Kaldra, and Helm of
        # Kaldra": the head is an ordinary group, the tail a list of names.
        head = parse_group(named["head"])
        if head is None:
            return None
        head["named"] = tuple(
            part.strip() for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", named["names"]) if part
        )
        return head
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
        elif match := _SUFFIX_NO_COUNTER_RE.search(text):
            fields["without_counter"] = match["kind"]
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
    if fields.get("named"):
        # CR 201.5: the source's own name in the list reaches the parser as
        # "this permanent".
        fields["named"] = tuple(
            source.name.lower() if name == "this permanent" else name for name in fields["named"]
        )
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
_SHARES_WITH_EQUIPPED_RE = re.compile(
    r"^creatures that share (?P<what>a color|a creature type) with equipped creature "
    r"gets? (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)$"
)
_COUNT_PUMP_RE = re.compile(
    r"^(?P<subject>.+?) gets? (?P<p>[+-](?:x|0))/(?P<t>[+-](?:x|0)), where x is "
    r"(?P<count>your speed|the number of creature cards in all graveyards)$"
)
_GROUP_GRANT_RE = re.compile(r"^(?P<subject>.+?) (?:have|has) (?P<keywords>.+)$")
_GROUP_BASE_PT_RE = re.compile(
    r"^(?P<subject>.+?) (?:have|has) base power and toughness (?P<power>\d+)/(?P<toughness>\d+)$"
)
_GROUP_ARE_RE = re.compile(
    r"^(?P<subject>.+?) (?:are|is) (?P<tail>.+?)"
    r"(?: in addition to (?:their|its) other (?:creature )?types)$"
)
_GROUP_ARE_PLAIN_RE = re.compile(
    r"^(?P<subject>.+?) (?:are|is) (?P<tail>every creature type|the chosen type|colorless|"
    r"white|blue|black|red|green|plains|islands|swamps|mountains|forests)$"
)
_GROUP_NO_COUNTERS_RE = re.compile(
    r"^(?P<subject>.+?) can't have (?P<kind>\+1/\+1|-1/-1) counters put on (?:them|it)$"
)
_LETHAL_BY_POWER_RE = re.compile(
    r"^lethal damage dealt to (?P<subject>.+?) is determined by (?:their|its) power "
    r"rather than (?:their|its) toughness$"
)
_GROUP_LOSE_KEYWORDS_RE = re.compile(r"^(?P<subject>.+?) loses? (?P<keywords>[a-z ,]+)$")
_GROUP_EQUIP_CREW_RE = re.compile(
    r"^(?P<subject>.+?) (?:have|has) (?P<ability>equip(?: [a-z]+)* (?:\{[^{}]+\})+|crew \d+)$"
)
_SAME_IS_TRUE_RE = re.compile(r"^the same is true for (?P<subjects>.+)$")
_OFF_ZONE_WORD_RE = re.compile(r"\b(?:cards?|spells?)\b")
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
    subject = _battlefield_part(_SELF_WORD_FOR_TYPE_RE.sub(source.name.split()[0].lower(), subject))
    spec = parse_group(subject) if subject else None
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
    if match := _GROUP_EQUIP_CREW_RE.fullmatch(lowered):
        if _subject_ok(match["subject"]) is False:
            return None
        granted = " ".join(
            w.upper() if w[0] == "{" else w.capitalize() for w in match["ability"].split()
        )
        return _builder(
            sentence,
            match["subject"],
            f"have {granted}",
            lambda: [(Layer.ABILITY, None, grant_ability_instance(granted))],
        )
    if match := _GROUP_NO_COUNTERS_RE.fullmatch(lowered):
        if _subject_ok(match["subject"]) is False:
            return None
        text_line = CANT_HAVE_KIND_COUNTERS_TEXT.format(kind=match["kind"])
        return _builder(
            sentence,
            match["subject"],
            f"can't have {match['kind']} counters put on them",
            lambda: [(Layer.ABILITY, None, grant_ability(text_line))],
        )
    if match := _LETHAL_BY_POWER_RE.fullmatch(lowered):
        if _subject_ok(match["subject"]) is False:
            return None
        return _builder(
            sentence,
            match["subject"],
            "lethal damage is determined by power",
            lambda: [(Layer.ABILITY, None, grant_ability(LETHAL_BY_POWER_TEXT))],
        )
    if (
        (match := _GROUP_LOSE_KEYWORDS_RE.fullmatch(lowered))
        and not match["keywords"].startswith("all ")
        and (lost := _split_keywords(match["keywords"])) is not None
    ):
        if _subject_ok(match["subject"]) is False:
            return None
        return _builder(
            sentence,
            match["subject"],
            f"lose {', '.join(lost)}",
            lambda: [(Layer.ABILITY, None, lose_keyword(keyword)) for keyword in lost],
        )
    if match := _LOSE_ALL_RE.fullmatch(lowered):
        if _subject_ok(match["subject"]) is False or _is_bare_all_creatures(match["subject"]):
            # "All creatures lose all abilities ..." is Humility's own
            # `LAYER_EFFECTS` row (its CR 613.6 interplay is pinned by
            # `tests/test_layers.py`), so the generic reader leaves it there.
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
    if match := _SHARES_WITH_EQUIPPED_RE.fullmatch(lowered):
        return _shares_with_equipped_builder(
            sentence,
            "color" if match["what"] == "a color" else "creature_type",
            int(match["power"]),
            int(match["toughness"]),
        )
    if match := _COUNT_PUMP_RE.fullmatch(lowered):
        if not _count_subject_ok(match["subject"]):
            return None
        return _count_pump_builder(
            sentence, match["subject"], match["p"], match["t"], match["count"]
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
                *[(Layer.ABILITY, None, grant_keyword(keyword)) for keyword in keywords],
            ],
        )
    if match := _SAME_IS_TRUE_RE.fullmatch(lowered):
        # "The same is true for creature spells you control and creature cards
        # you own that aren't on the battlefield." (Maskwood Nexus): the
        # off-battlefield half of the sentence before it, applied by
        # `machines/zone_grants.py`; nothing for the battlefield here.
        from ..zone_grants import line_grants_off_zone

        if not line_grants_off_zone(f"creatures are every creature type. {lowered}"):
            return None
        return lambda source, timestamp, targets, context: []
    if match := _GROUP_ARE_PLAIN_RE.fullmatch(lowered):
        if not _subject_ok(match["subject"]) or not _battlefield_part(match["subject"]):
            return None
        return _plain_are_builder(sentence, match["subject"], match["tail"])
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
            lambda: [(Layer.ABILITY, None, grant_keyword(keyword)) for keyword in keywords],
        )
    return None


def _battlefield_part(subject: str) -> str:
    """The permanents of a subject that also names cards off the battlefield
    ("all cards that aren't on the battlefield, spells, and permanents" ->
    "permanents"); the off-battlefield items are `zone_grants`' (CR 613.1d,
    CR 613.1e reach them there)."""
    if not _OFF_ZONE_WORD_RE.search(subject):
        return subject
    items = [re.sub(r"^(?:and|all|each)\s+", "", item.strip()) for item in subject.split(",")]
    return " and ".join(item for item in items if item and not _OFF_ZONE_WORD_RE.search(item))


def _subject_ok(subject: str) -> bool:
    if _GROUP_SELF_RE.fullmatch(subject.strip().lower()):
        return True
    subject = _battlefield_part(subject)
    return bool(subject) and parse_group(_SELF_WORD_FOR_TYPE_RE.sub("human", subject)) is not None


def _plain_are_builder(sentence: str, subject: str, tail: str):
    """ "`<group>` are every creature type / the chosen type / white /
    colorless / Plains" - the sets, not the additions (CR 205.1a, CR 305.7,
    CR 613.1d, CR 613.1e)."""
    singular = _singular(tail)

    def build(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector = _subject_selector(subject, source)
        if selector is None:
            return []
        if tail == "every creature type":
            parts: list[tuple[Layer, Sublayer | None, Any]] = [
                (Layer.TYPE, None, AddEveryCreatureType())
            ]
        elif tail == "the chosen type":
            from .parse import chosen_creature_type_of

            chosen = chosen_creature_type_of(source)
            if chosen is None:
                return []
            parts = [(Layer.TYPE, None, SetCreatureTypes(subtypes=(chosen.title(),)))]
        elif tail == "colorless":
            parts = [(Layer.COLOR, None, set_colors())]
        elif tail in _GROUP_COLORS:
            parts = [(Layer.COLOR, None, set_colors(_GROUP_COLORS[tail]))]
        else:
            from ._common import BASIC_LAND_TYPES

            name = _GROUP_BASIC_LAND_TYPES[tail if tail in _GROUP_BASIC_LAND_TYPES else singular]
            parts = [(Layer.TYPE, None, set_basic_land_type(name, BASIC_LAND_TYPES[name]))]
        return _effects(source, timestamp, sentence, selector, f"{subject} are {tail}", parts)

    return build


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


_THIS_AND_ENCHANTED_RE = re.compile(
    r"^this (?:creature|permanent) and enchanted (?:creature|permanent) each$"
)


def _shares_with_equipped_builder(sentence: str, kind: str, power: int, toughness: int):
    """ "Creatures that share a color with equipped creature get +1/+1"
    (Konda's Banner, CR 613.4c): the group is every creature (whoever controls
    it) sharing the quality with the creature this permanent is attached to,
    asked of the computed board each time (CR 611.3a); unattached, no one."""

    def build(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        if source.attached_to is None:
            return []
        selector = GroupMatch(
            scope="any",
            all_types=(Type.CREATURE,),
            shares_with=source.attached_to,
            share_kind=kind,
        )
        return _effects(
            source,
            timestamp,
            sentence,
            selector,
            f"creatures sharing a {kind.replace('_', ' ')} with the equipped creature get "
            f"{power:+d}/{toughness:+d}",
            [(Layer.POWER_TOUGHNESS, Sublayer.MODIFY, modify_power_toughness(power, toughness))],
        )

    return build


def _count_subject_ok(subject: str) -> bool:
    return (
        bool(_THIS_AND_ENCHANTED_RE.fullmatch(subject.strip())) or _subject_ok(subject) is not False
    )


def _count_of(kind: str, source: CardState, context: LayerContext) -> int:
    """The number a "where X is ..." pump counts, as the effects are rebuilt
    (CR 613.5): CR 702.179f's speed (none reads as 0), or the creature cards in
    every graveyard (`LayerContext.graveyards`, which the layer engine never
    sees on its own)."""
    if kind == "your speed":
        game = source._board_source
        player = (
            None if game is None or source.controller is None else game.player(source.controller)
        )
        return 0 if player is None or player.speed is None else player.speed
    return sum(1 for card in context.graveyards if Type.CREATURE in card.card.types)


def _count_pump_builder(sentence: str, subject: str, power: str, toughness: str, kind: str):
    """ "... get +X/+0, where X is your speed" / "... each get +X/+X, where X is
    the number of creature cards in all graveyards" (CR 613.4c): X is read every
    time the effects are rebuilt, so it follows the count continuously."""

    def amount(token: str, size: int) -> int:
        return 0 if token[1] == "0" else (size if token[0] == "+" else -size)

    def build(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        size = _count_of(kind, source, context)
        selectors: list[Any] = []
        if _THIS_AND_ENCHANTED_RE.fullmatch(subject.strip()):
            selectors.append(Only(card_id=source.id))
            if source.attached_to is not None:
                selectors.append(Only(card_id=source.attached_to))
        else:
            selector = _subject_selector(subject, source)
            if selector is not None:
                selectors.append(selector)
        found: list[ContinuousEffect] = []
        for selector in selectors:
            found.extend(
                _effects(
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
            )
        return found

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


def _is_bare_all_creatures(subject: str) -> bool:
    spec = parse_group(subject)
    return (
        spec is not None
        and spec["scope"] == "any"
        and spec["all_types"] == (Type.CREATURE,)
        and not any(
            spec.get(key)
            for key in (
                "any_types",
                "not_types",
                "any_subtypes",
                "not_subtypes",
                "any_colors",
                "not_colors",
                "colorless",
                "other",
                "chosen",
                "with_counter",
                "with_keyword",
                "without_keyword",
            )
        )
        and spec.get("legendary") is None
        and spec.get("token") is None
    )
