"""Layer readers for the EP-01 round 2 "other statics" grab-bag (T8):

- "~ isn't legendary if it's a token." (CR 613.1d, CR 205.4b, CR 111.1)
- "Permanents you control have "Ward-Sacrifice a permanent."" is the ordinary
  quoted-ability grant and needs no reader here.

Each reader is a memoised pure function of the sentence, tried from
`parse._parse_layer_sentence_ungated` behind a cheap literal gate.
"""

import functools
import re
from collections.abc import Sequence

from ...models.card import Supertype, Type
from ...models.card_state import CardState
from ...models.token import TokenState
from .apply import EffectBuilder, LayerContext
from .model import (
    ContinuousEffect,
    Layer,
    LoseAllAbilitiesExceptManaAbilities,
    PermanentsOfTypes,
    RemoveSupertype,
    _only,
)

_NOT_LEGENDARY_IF_TOKEN_RE = re.compile(
    r"^(?:this (?:creature|permanent|artifact|enchantment|land)|it) "
    r"isn'?t legendary if it'?s a token\.?$",
    re.IGNORECASE,
)


_LOSE_ALL_EXCEPT_MANA_RE = re.compile(
    r"^all (?P<group>lands|creatures|artifacts|enchantments) lose all abilities "
    r"except mana abilities\.?$",
    re.IGNORECASE,
)
_GROUP_TYPES = {
    "lands": Type.LAND,
    "creatures": Type.CREATURE,
    "artifacts": Type.ARTIFACT,
    "enchantments": Type.ENCHANTMENT,
}


def _counter_static_sentence(sentence: str) -> EffectBuilder | None:
    from ..ep02_r2_counter_amounts import parse_counter_static_sentence

    return parse_counter_static_sentence(sentence)


@functools.cache
def parse_other_static_sentence(sentence: str) -> EffectBuilder | None:
    lowered = sentence.lower()
    if "legendary" in lowered and _NOT_LEGENDARY_IF_TOKEN_RE.fullmatch(sentence):
        return _not_legendary_if_token_builder(sentence)
    if " counter" in lowered and (counted := _counter_static_sentence(sentence)) is not None:
        return counted
    if "except mana abilities" in lowered and (
        match := _LOSE_ALL_EXCEPT_MANA_RE.fullmatch(sentence)
    ):
        return _lose_all_except_mana_builder(_GROUP_TYPES[match["group"].lower()], sentence)
    return None


def _lose_all_except_mana_builder(card_type: Type, line: str) -> EffectBuilder:
    """Layer 6 (CR 613.1f): every permanent of the type loses its abilities but
    its mana abilities, whoever controls it."""
    from .parse import _source_line_for

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: {card_type.value}s lose all abilities except mana abilities"
                ),
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=PermanentsOfTypes(card_types=(card_type,)),
                modification=LoseAllAbilitiesExceptManaAbilities(),
            )
        ]

    return builder


def _not_legendary_if_token_builder(line: str) -> EffectBuilder:
    """CR 111.1 / CR 613.1d: a token copy of the source is the only object this
    reads as its own, so a non-token source builds nothing."""
    from .parse import _source_line_for

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        if not isinstance(source, TokenState):
            return []
        return [
            ContinuousEffect(
                description=f"{source.name}: isn't legendary because it's a token",
                layer=Layer.TYPE,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(source.id),
                modification=RemoveSupertype(supertype=Supertype.LEGENDARY),
            )
        ]

    return builder
