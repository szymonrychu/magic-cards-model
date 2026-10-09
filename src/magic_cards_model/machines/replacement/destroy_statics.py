"""Destruction-replacement statics (CR 614.1a, CR 701.8, CR 701.19):

- "If this creature would be destroyed, regenerate it." (Mossbridge Troll) - a
  permanent regeneration: unlike a shield (CR 701.19a), nothing is spent.
- "If enchanted land would be destroyed, instead sacrifice this Aura and that
  land gains indestructible until end of turn." (Crackling Emergence)
"""

import re
from typing import TYPE_CHECKING

from ...models.card import Type
from ...models.card_state import CardState
from ..layers import ContinuousEffect, Duration, Layer, grant_ability, only_this_incarnation
from .model import (
    CardReplacement,
    EventKind,
    ReplaceableEvent,
    ReplacementEffect,
    ReplacementKind,
    _cant_be_regenerated,
)
from .parse import strip_reminder_text

if TYPE_CHECKING:
    from ...models.game import Game

_EVENT_RE = re.compile(
    r"^(?P<subject>this [a-z]+|~|enchanted (?P<type>land|creature|artifact|permanent)) "
    r"would be destroyed$",
    re.IGNORECASE,
)
_REGENERATE_RE = re.compile(r"^regenerate (?:it|that \w+)$", re.IGNORECASE)
_SACRIFICE_RE = re.compile(
    r"^sacrifice this (?:Aura|enchantment) and that (?P<type>land|creature|artifact|permanent) "
    r"gains indestructible until end of turn$",
    re.IGNORECASE,
)
_TYPES = {"land": Type.LAND, "creature": Type.CREATURE, "artifact": Type.ARTIFACT}


def _event_predicate(effect: ReplacementEffect):
    event_text = strip_reminder_text(effect.event or "")[0].strip()
    match = _EVENT_RE.match(event_text)
    if match is None:
        return None
    enchanted = match.group("type")
    if enchanted is None and not effect.self_replacement:
        return None
    wanted = _TYPES.get((enchanted or "").lower())

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        card = event.card
        if event.kind is not EventKind.DESTROY or event.replaced or card is None:
            return False
        if enchanted is None:
            return card.id == source.id
        if source.attached_to != card.id:
            return False
        return wanted is None or wanted in game.characteristics_of(card).types

    return applies


def _regenerate(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    """CR 701.19a's replacement, applied by a static ability: tap it, heal it,
    take it out of combat. CR 701.19c: a "can't be regenerated" destruction
    skips it entirely (handled by `applies`)."""
    card = event.card
    card.damage = 0
    game.tap_permanent(card)
    game.combat.remove(card.id)  # CR 506.4
    event.replaced = True


def _compile_destroy(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD or effect.condition is not None:
        return None
    predicate = _event_predicate(effect)
    if predicate is None:
        return None
    printed = strip_reminder_text(effect.replacement or "")[0].strip().rstrip(".")
    if _REGENERATE_RE.match(printed):

        def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
            return (
                predicate(game, source, event)
                and event.regeneration_allowed
                and not _cant_be_regenerated(game, event.card)
            )

        return CardReplacement(label=effect.text, applies=applies, apply=_regenerate)
    if _SACRIFICE_RE.match(printed):

        def sacrifice_aura(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
            from ..effects.continuous import continuous_effects

            card = event.card
            event.replaced = True  # CR 614.6: the destruction never happens
            store = continuous_effects(game)
            store.add(_indestructible_until_end_of_turn(store, source, card))
            game.sacrifice(source)

        return CardReplacement(label=effect.text, applies=predicate, apply=sacrifice_aura)
    return None


def _indestructible_until_end_of_turn(store, source: CardState, card: CardState):
    """CR 613.1f: `card` has indestructible until end of turn (CR 611.2a)."""
    return ContinuousEffect(
        description=f"{source.name}: {card.name} gains indestructible until end of turn",
        layer=Layer.ABILITY,
        timestamp=store.tick(),
        duration=Duration.UNTIL_END_OF_TURN,
        selector=only_this_incarnation(card, card.zone_change_stamp),
        modification=grant_ability("Indestructible"),
    )


DESTROY_COMPILERS = (_compile_destroy,)
