"""The forms an "as [this] enters" choice leaves on the permanent (EP-01 R1 T2).

The replacement side (`machines/replacement/enters_choices.py`) asks the choice
and records it on `CardState.choice` or links the cards it exiled (CR 614.12a,
CR 607.2a); these are the static sentences that read the record back:

- "As this creature enters, it becomes your choice of a 3/3 creature with
  flying, a 2/5 ..." and Molten Sentry's coin-gated "this creature enters as a
  5/2 creature with haste": base power/toughness (CR 613.4b) and keywords
  (CR 613.1f) from the recorded body.
- "~'s power and toughness are each equal to the exiled card's mana value" /
  "... the total power of the exiled cards ..." (Living Lore, Sutured Ghoul):
  characteristic-defining abilities (CR 604.3, CR 613.4a) over the cards linked
  to this object (CR 607.2a).
- "... each equal to the number of face-down creatures on the battlefield"
  (Ixidron, CR 708.2).
- "If you do, until this creature is turned face down, it becomes a copy of that
  creature, except it has ..." (Vesuvan Shapeshifter, CR 707.2, CR 707.9a): the
  copiable values snapshotted when the creature was chosen (CR 707.2b).

`layers/parse.py` imports `parse_entering_form_sentence` lazily (this module
imports from it at module scope).
"""

import functools
import re
from collections.abc import Sequence
from uuid import UUID

from ...models.card_state import CardState, ChoiceKind
from ..chosen_body import parse_body
from .apply import EffectBuilder, LayerContext
from .model import (
    Characteristics,
    ContinuousEffect,
    FixedCount,
    Layer,
    Sublayer,
    define_power,
    define_power_toughness,
    define_toughness,
    grant_ability,
    modify_power_toughness,
    set_power_toughness,
)
from .parse import _become_a_copy_builder, _only, _source_line_for, _split_and_validate_keywords

_CHOOSES_BODY_RE = re.compile(
    r"^as this [a-z ]+ enters(?: or is turned face up)?, it becomes your choice of .+$",
    re.IGNORECASE,
)
_COIN_BODY_RE = re.compile(
    r"^if (?:the coin|it) comes up (?P<side>heads|tails), this creature enters as "
    r"(?P<body>an? \d+/\d+ creature(?: with [a-z ,]+)?)\.?$",
    re.IGNORECASE,
)
_CHOSEN_CREATURE_PUMP_RE = re.compile(
    r"^the chosen creature gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)"
    r"(?: and has (?P<keywords>[a-z ,]+?))?\.?$",
    re.IGNORECASE,
)
_FACE_DOWN_COUNT_RE = re.compile(
    r"^this permanent's power and toughness are each equal to the number of "
    r"face-down creatures on the battlefield\.?$",
    re.IGNORECASE,
)
_EXILED_MANA_VALUE_RE = re.compile(
    r"^this permanent's power and toughness are each equal to the exiled card's mana value\.?$",
    re.IGNORECASE,
)
_EXILED_TOTALS_RE = re.compile(
    r"^this permanent's power is equal to the total power of the exiled cards and its "
    r"toughness is equal to their total toughness\.?$",
    re.IGNORECASE,
)
_COPY_UNTIL_FACE_DOWN_RE = re.compile(
    r"^if you do, until this creature is turned face down, it becomes a copy of that "
    r'creature, except it has "(?P<ability>.+)"\.?$',
    re.IGNORECASE | re.DOTALL,
)


def _printed_number(value: str | None) -> int:
    """A printed power/toughness as a number; `*` and the absent box are 0."""
    return int(value) if value is not None and value.lstrip("-").isdigit() else 0


def _body_effects(
    source: CardState, timestamp: int, body_text: str, line: str
) -> list[ContinuousEffect]:
    body = parse_body(body_text)
    if body is None:
        return []
    keywords = _split_and_validate_keywords(", ".join(body.keywords)) if body.keywords else []
    effects = [
        ContinuousEffect(
            description=f"{source.name}: becomes a {body.power}/{body.toughness} creature",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.SET,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=_source_line_for(source, line),
            selector=_only(source.id),
            modification=set_power_toughness(body.power, body.toughness),
        )
    ]
    effects.extend(
        ContinuousEffect(
            description=f"{source.name}: has {keyword}",
            layer=Layer.ABILITY,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=_source_line_for(source, line),
            selector=_only(source.id),
            modification=grant_ability(keyword),
        )
        for keyword in keywords or []
    )
    return effects


def _chosen_body_builder(line: str) -> EffectBuilder:
    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        chosen = source.choice
        if chosen is None or chosen.kind is not ChoiceKind.BODY:
            return []
        return _body_effects(source, timestamp, chosen.value, line)

    return builder


def _chosen_creature_pump_builder(
    power: int, toughness: int, keyword_text: str | None, line: str
) -> EffectBuilder:
    """Tyrannical Pitlord: "The chosen creature gets +3/+3 and has flying." -
    the object recorded by the as-enters choice (CR 614.12a), pumped (CR 613.4c)
    and granted keywords (CR 613.1f) for as long as the source is on the
    battlefield (CR 611.3a)."""
    keywords = _split_and_validate_keywords(keyword_text) if keyword_text else []

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        chosen = source.choice
        if chosen is None or chosen.kind is not ChoiceKind.OBJECT:
            return []
        selector = _only(UUID(chosen.value))
        effects = [
            ContinuousEffect(
                description=f"{source.name}: the chosen creature gets {power:+}/{toughness:+}",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=selector,
                modification=modify_power_toughness(power, toughness),
            )
        ]
        effects.extend(
            ContinuousEffect(
                description=f"{source.name}: the chosen creature has {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=selector,
                modification=grant_ability(keyword),
            )
            for keyword in keywords or []
        )
        return effects

    return builder


def _coin_body_builder(side: str, body_text: str, line: str) -> EffectBuilder:
    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        chosen = source.choice
        if chosen is None or chosen.kind is not ChoiceKind.COIN or chosen.value != side:
            return []
        return _body_effects(source, timestamp, body_text, line)

    return builder


def _cda(source: CardState, timestamp: int, line: str, modification) -> ContinuousEffect:
    return ContinuousEffect(
        description=f"{source.name}: power and toughness from {line}",
        layer=Layer.POWER_TOUGHNESS,
        sublayer=Sublayer.CHARACTERISTIC_DEFINING,
        characteristic_defining=True,
        timestamp=timestamp,
        source_id=source.id,
        source_ability=_source_line_for(source, line),
        selector=_only(source.id),
        modification=modification,
    )


def _face_down_count_builder(line: str) -> EffectBuilder:
    def builder(source, timestamp, targets, context):
        return [
            _cda(
                source,
                timestamp,
                line,
                define_power_toughness(FixedCount(value=context.face_down_creatures)),
            )
        ]

    return builder


def _exiled_mana_value_builder(line: str) -> EffectBuilder:
    def builder(source, timestamp, targets, context):
        total = sum(int(card.mana_value) for card in context.cards_exiled_with(source))
        return [_cda(source, timestamp, line, define_power_toughness(FixedCount(value=total)))]

    return builder


def _exiled_totals_builder(line: str) -> EffectBuilder:
    def builder(source, timestamp, targets, context):
        exiled = context.cards_exiled_with(source)
        power = sum(_printed_number(card.card.power) for card in exiled)
        toughness = sum(_printed_number(card.card.toughness) for card in exiled)
        return [
            _cda(source, timestamp, line, define_power(FixedCount(value=power))),
            _cda(source, timestamp, line, define_toughness(FixedCount(value=toughness))),
        ]

    return builder


def _copy_until_face_down_builder(ability: str) -> EffectBuilder:
    def builder(source, timestamp, targets, context):
        chosen = source.choice
        if source.face_down or chosen is None or chosen.kind is not ChoiceKind.COPY_OF:
            return []
        copied = Characteristics.model_validate_json(chosen.value)
        return _become_a_copy_builder(
            until_eot=False, copiable_values=copied, added_abilities=(ability,)
        )(source, timestamp, [source], context)

    return builder


@functools.lru_cache(maxsize=4096)
def parse_entering_form_sentence(sentence: str) -> EffectBuilder | None:
    """The builder for one sentence of the shapes above, or None."""
    text = sentence.strip()
    if _CHOOSES_BODY_RE.match(text):
        return _chosen_body_builder(text)
    if match := _COIN_BODY_RE.match(text):
        return _coin_body_builder(match.group("side").lower(), match.group("body"), text)
    if match := _CHOSEN_CREATURE_PUMP_RE.match(text):
        keyword_text = match.group("keywords")
        if keyword_text and _split_and_validate_keywords(keyword_text) is None:
            return None
        return _chosen_creature_pump_builder(
            int(match.group("power")), int(match.group("toughness")), keyword_text, text
        )
    if _FACE_DOWN_COUNT_RE.match(text):
        return _face_down_count_builder(text)
    if _EXILED_MANA_VALUE_RE.match(text):
        return _exiled_mana_value_builder(text)
    if _EXILED_TOTALS_RE.match(text):
        return _exiled_totals_builder(text)
    if match := _COPY_UNTIL_FACE_DOWN_RE.match(text):
        return _copy_until_face_down_builder(match.group("ability"))
    return None
