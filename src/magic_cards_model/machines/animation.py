"""Self-animation of a noncreature permanent that states no power or toughness.

"This Vehicle becomes an artifact creature until end of turn." - the effect
half of Bladewheel Chariot's "Tap two other untapped artifacts you control:"
and Honeymoon Hearse's "Tap two untapped creatures you control:" abilities,
and the same words crew's own definition uses (CR 702.122a). The manland
template that *does* state a P/T ("This land becomes a 2/2 creature with all
creature types ...") is `machines/layers.py`'s `_ANIMATION_RE`.

- **CR 613.1d** - "becomes an artifact creature" is a layer 4 type change that
  adds artifact and creature; the Vehicle keeps every other type and subtype
  it has.
- **CR 301.7a / 301.7b** - a Vehicle has its printed power and toughness only
  while it is a creature and has them immediately once it becomes one, so no
  layer 7 effect is created: a pump or a counter stacks on top (CR 613.4c).
- **CR 611.2a** - the effect lasts as long as stated; with no duration it
  lasts until the end of the game.

Read by `machines/layers._parse_layer_sentence`, imported lazily there: this
module imports from `layers.py` at module scope, so `layers.py` cannot import
it back at its own top level without a cycle (the same arrangement
`machines/attacking_statics.py` uses).
"""

import re
from collections.abc import Sequence

from ..models.card import Type
from ..models.card_state import CardState
from .layers import (
    ContinuousEffect,
    Duration,
    EffectBuilder,
    Layer,
    LayerContext,
    add_type,
    only_this_incarnation,
)

#: "This Vehicle becomes an artifact creature until end of turn." The subject
#: is the ability's own source ("this <noun>"), so `targets` holds it.
_SELF_BECOMES_ARTIFACT_CREATURE_RE = re.compile(
    r"^this (?:vehicle|artifact|permanent) becomes an artifact creature"
    r"(?P<until_eot> until end of turn)?\.?$",
    re.IGNORECASE,
)


def _self_becomes_artifact_creature_builder(duration: Duration) -> EffectBuilder:
    """Two layer 4 additions (CR 613.1d), artifact and creature, on the source's
    current incarnation - a Vehicle that left and came back (CR 400.7) is a new
    object this effect never touches."""

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: {target.name} becomes an artifact creature",
                layer=Layer.TYPE,
                timestamp=timestamp,
                duration=duration,
                selector=only_this_incarnation(target, target.zone_change_stamp),
                modification=add_type(card_type),
            )
            for target in targets
            for card_type in (Type.ARTIFACT, Type.CREATURE)
        ]

    return builder


def parse_self_becomes_artifact_creature(sentence: str) -> EffectBuilder | None:
    """`_SELF_BECOMES_ARTIFACT_CREATURE_RE`'s builder, or `None`."""
    match = _SELF_BECOMES_ARTIFACT_CREATURE_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    return _self_becomes_artifact_creature_builder(
        Duration.UNTIL_END_OF_TURN if match.group("until_eot") else Duration.INDEFINITE
    )
