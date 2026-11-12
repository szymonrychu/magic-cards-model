"""Group statics that hand every member of a group a quoted ability
(EP-01 round 2, task T5).

"Elves you control have "{T}: Add {B}."" (Tyvar Kell), "Each creature you
control with a counter on it has "{T}: Add {G}."" (Rishkar, Peema Renegade),
"Sliver creatures you control have "Whenever this creature deals combat damage
to a player, ..."" (Tempered Sliver), "All Sliver creatures have "Whenever ..""
(Fungus Sliver), "All artifacts have "At the beginning of your upkeep, sacrifice
this artifact unless you pay {1}."" (Kataki, War's Wage), "Treasures you control
have "{T}, Sacrifice this artifact: Add two mana of any one color."" (Goldspan
Dragon), "Other Caves you control have ...", "Permanents you control have ...".

CR 113.10a: a granted ability is the quoted ability itself - mana, activated or
triggered, with any activation instructions - and CR 613.1f puts the grant in
layer 6. The group is a static ability's subject (CR 611.3), so it is judged
live, on every computation (CR 611.3a, CR 613.5): a creature that stops being an
Elf, or loses its counter, stops being granted the ability, and a creature
outside the group gets nothing.

`parse_group_quoted_sentence` is the layer reader (called last by
`parse._parse_layer_sentence_ungated`); `group_quoted_grant_of` is the same
parse as data for `parse.quoted_ability_grants`, which puts each granted line on
`CardState.granted_ability_texts` so it is a real ability and not only text on
the computed board.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass

from ...data.subtypes import canonical_subtype
from ...models.card import Color, Type
from ...models.card_state import CardState
from .apply import EffectBuilder
from .model import (
    ContinuousEffect,
    GrantGroup,
    Layer,
    Selector,
    _split_and_validate_keywords,
    grant_ability,
)

_SENTENCE_RE = re.compile(
    r"^(?P<quantifier>each|all) ?(?P<other>other )?(?P<head>.+?)(?P<you> you control)?"
    r"(?: with (?P<condition>.+?))? (?:have|has) \"(?P<ability>.+)\"\.?$"
    r"|^(?P<other2>other )?(?P<head2>[^\"]+?)(?P<you2> you control)?"
    r"(?: with (?P<condition2>[^\"]+?))? (?:have|has) \"(?P<ability2>.+)\"\.?$",
    re.IGNORECASE | re.DOTALL,
)
_COLORS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}
_TYPE_NOUNS = {
    "creature": Type.CREATURE,
    "artifact": Type.ARTIFACT,
    "land": Type.LAND,
    "enchantment": Type.ENCHANTMENT,
    "planeswalker": Type.PLANESWALKER,
    "battle": Type.BATTLE,
}
#: Plurals that are not "the singular plus s" (CR 205.3m's creature types).
_IRREGULAR_PLURALS = {"elves": "elf", "dwarves": "dwarf", "wolves": "wolf", "fungi": "fungus"}


def _singular(word: str) -> str | None:
    """A printed plural (or already singular) subtype word as its lowercase
    singular subtype, or `None` if it names no subtype."""
    lowered = word.lower()
    candidates = [lowered, lowered.removesuffix("s"), _IRREGULAR_PLURALS.get(lowered, lowered)]
    if lowered.endswith("ies"):
        candidates.append(lowered.removesuffix("ies") + "y")
    if lowered.endswith("ves"):
        candidates += [lowered.removesuffix("ves") + "f", lowered.removesuffix("ves") + "fe"]
    for candidate in candidates:
        if canonical_subtype(candidate) is not None:
            return canonical_subtype(candidate)
    return None


@dataclass(frozen=True)
class GroupQuotedGrant:
    """A group and the quoted ability it is given."""

    ability: str
    other: bool
    you_control: bool
    required_types: tuple[Type, ...]
    any_of_types: tuple[Type, ...]
    any_of_subtypes: tuple[str, ...]
    colors_any: tuple[Color, ...]
    counter_kind: str | None
    keyword: str | None
    subject: str

    def selector(self, source: CardState) -> Selector:
        return GrantGroup(
            username=source.controller if self.you_control else None,
            any_controller=not self.you_control,
            exclude_id=source.id if self.other else None,
            required_types=self.required_types,
            any_of_types=self.any_of_types,
            any_of_subtypes=self.any_of_subtypes,
            colors_any=self.colors_any,
            counter_kind=self.counter_kind,
            keyword=self.keyword,
        )


def _terms(head: str) -> list[str]:
    return [
        term.strip()
        for term in re.split(r",\s*(?:and\s+)?|\s+and\s+", head.strip(), flags=re.IGNORECASE)
        if term.strip()
    ]


def _condition(text: str | None) -> tuple[str | None, str | None] | None:
    """`(counter_kind, keyword)` for a "with ..." rider, `(None, None)` for
    none, or `None` for one this does not read."""
    if text is None:
        return None, None
    body = text.strip().lower()
    if match := re.fullmatch(
        r"(?:an? )?(?:(?P<kind>[+-]\d+/[+-]\d+|[a-z]+) )?counters? on (?:it|them)", body
    ):
        return (match["kind"] or ""), None
    keywords = _split_and_validate_keywords(body)
    if keywords is not None and len(keywords) == 1:
        return None, keywords[0].lower()
    return None


@functools.lru_cache(maxsize=4096)
def group_quoted_grant_of(sentence: str) -> GroupQuotedGrant | None:
    """`sentence` as a group quoted-ability grant, or `None`."""
    if '"' not in sentence or " have " not in sentence.lower() and " has " not in sentence.lower():
        return None
    match = _SENTENCE_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    first = match["head"] is not None
    head = match["head"] if first else match["head2"]
    ability = (match["ability"] if first else match["ability2"]).strip()
    you = (match["you"] if first else match["you2"]) is not None
    other = (match["other"] if first else match["other2"]) is not None
    condition = match["condition"] if first else match["condition2"]
    quantifier = (match["quantifier"] or "").lower() if first else ""
    if not you and not quantifier:
        return None  # a bare "Creatures have ..." is not a printed shape
    read_condition = _condition(condition)
    if condition is not None and read_condition is None:
        return None
    counter_kind, keyword = read_condition or (None, None)

    required: list[Type] = []
    any_types: list[Type] = []
    any_subtypes: list[str] = []
    colors: list[Color] = []
    terms = _terms(head)
    if not terms:
        return None
    for term in terms:
        words = term.split()
        noun = words[-1].lower()
        noun_type = _TYPE_NOUNS.get(noun.removesuffix("s"))
        if len(words) == 1:
            if noun == "permanents":
                continue
            if noun_type is not None:
                any_types.append(noun_type)
                continue
            subtype = _singular(noun)
            if subtype is None:
                return None
            any_subtypes.append(subtype)
            continue
        if noun_type is None and noun != "permanents":
            return None
        if noun_type is not None:
            required.append(noun_type)
        for qualifier in words[:-1]:
            lowered = qualifier.lower()
            if lowered in _COLORS:
                colors.append(_COLORS[lowered])
            elif lowered in _TYPE_NOUNS:
                # "Artifact creatures you control" (Hive Mind Coprocessor): a
                # card type naming the group's second requirement.
                required.append(_TYPE_NOUNS[lowered])
            elif (subtype := _singular(lowered)) is not None:
                any_subtypes.append(subtype)
            else:
                return None
    # "Permanents you control" with no further limit is a real group; anything
    # else must have named something.
    named_something = (
        required or any_types or any_subtypes or colors or counter_kind is not None or keyword
    )
    if not named_something and "permanents" not in head.lower():
        return None
    return GroupQuotedGrant(
        ability=ability,
        other=other,
        you_control=you,
        required_types=tuple(dict.fromkeys(required)),
        any_of_types=tuple(dict.fromkeys(any_types)),
        any_of_subtypes=tuple(dict.fromkeys(any_subtypes)),
        colors_any=tuple(dict.fromkeys(colors)),
        counter_kind=counter_kind,
        keyword=keyword,
        subject=sentence.split('"')[0].strip(),
    )


def group_quoted_builder(grant: GroupQuotedGrant, *, line: str) -> EffectBuilder:
    """Layer 6 (CR 613.1f): one grant of the quoted text over the live group."""

    def builder(source, timestamp, targets, context):
        from .parse import _source_line_for

        return [
            ContinuousEffect(
                description=f'{source.name}: {grant.subject} have "{grant.ability}"',
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=grant.selector(source),
                modification=grant_ability(grant.ability),
            )
        ]

    return builder


@functools.lru_cache(maxsize=4096)
def parse_group_quoted_sentence(sentence: str) -> EffectBuilder | None:
    grant = group_quoted_grant_of(sentence.strip())
    return None if grant is None else group_quoted_builder(grant, line=sentence)
