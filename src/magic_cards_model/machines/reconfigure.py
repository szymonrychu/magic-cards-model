"""Reconfigure (CR 702.151).

CR 702.151a: "Reconfigure represents two activated abilities. Reconfigure
[cost] means '[Cost]: Attach this permanent to another target creature you
control. Activate only as a sorcery' and '[Cost]: Unattach this permanent.
Activate only if this permanent is attached to a creature and only as a
sorcery.'" Both are written out here as synthetic `KeywordActivation`s, the
shape equip uses (`machines/keywords.equip_activation`); an activation with a
target is the attach, one without is the unattach (`_reconfigure_effect`).

CR 702.151b: "Attaching an Equipment with reconfigure to another creature
causes the Equipment to stop being a creature until it becomes unattached
from that creature." That is `reconfigure_not_a_creature` below, a layer 4
type change (CR 613.1d) built with every static effect each time the board is
computed, for as long as the permanent is attached. Because it is no creature
while attached, CR 301.5c's "An Equipment that's also a creature can't equip
a creature unless that Equipment has reconfigure" never bites, and CR
704.5n's unattach (`keywords.equipment_state_based_actions`) runs only when
the host itself stops being a legal one - after which the Equipment is a
creature again.
"""

from typing import Any

from ..models.card import Card, Type
from ..models.card_state import CardState, TargetRef
from ..models.zone import Zone
from .abilities import KeywordAbility, keyword_abilities
from .keywords import (
    KEYWORD_EFFECTS,
    KeywordActivation,
    _keyword_cost,
    _protection_refusal_for_attachment,
    _synthetic_ability,
)

__all__ = [
    "RECONFIGURE_ATTACH_EFFECT",
    "RECONFIGURE_RULE",
    "RECONFIGURE_UNATTACH_EFFECT",
    "has_reconfigure",
    "reconfigure_attach_activation",
    "reconfigure_not_a_creature",
    "reconfigure_unattach_activation",
    "reconfigure_unattach_refusal",
]

RECONFIGURE_RULE = "CR 702.151a"
#: CR 702.151a's two expansions, after the colon.
RECONFIGURE_ATTACH_EFFECT = "Attach this permanent to another target creature you control."
RECONFIGURE_UNATTACH_EFFECT = "Unattach this permanent."


def _reconfigure_ability(card: Card) -> KeywordAbility | None:
    return next(
        (a for a in keyword_abilities(card) if a.canonical.lower() == "reconfigure"),
        None,
    )


def has_reconfigure(card: Card) -> bool:
    """Whether this card prints reconfigure (CR 702.151a)."""
    return _reconfigure_ability(card) is not None


def _activation(game: Any, equipment: CardState, player: str, effect: str) -> KeywordActivation:
    ability = _reconfigure_ability(equipment.card)
    if ability is None:
        raise ValueError(f"{equipment.name} has no reconfigure ability ({RECONFIGURE_RULE})")
    cost = _keyword_cost(ability, player)
    if cost is None:
        raise ValueError(
            f"{equipment.name}'s reconfigure cost {ability.cost!r} could not be read, "
            "so it cannot be paid"
        )
    return KeywordActivation(
        card=equipment,
        player=player,
        keyword=ability.canonical,
        rule=RECONFIGURE_RULE,
        zone=Zone.BATTLEFIELD,
        cost=cost,
        sorcery_only=True,
        ability=_synthetic_ability(ability, cost_text=ability.cost or "", effect=effect),
        game=game,
    )


def _is_creature_now(game: Any, permanent: CardState) -> bool:
    try:
        return bool(game.characteristics_of(permanent).is_creature)
    except (AttributeError, KeyError):
        return permanent.is_creature


def _attach_refusal(game: Any, equipment: CardState, target: Any, player: str) -> str | None:
    """Why `target` is not "another target creature you control" for this
    Equipment's reconfigure (CR 702.151a, CR 115.1), or None."""
    if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
        return f"{RECONFIGURE_RULE}: the target must be a creature on the battlefield"
    if target.id == equipment.id:
        return f"{equipment.name} must attach to another creature, not itself ({RECONFIGURE_RULE})"
    if not _is_creature_now(game, target):
        return f"{target.name} is not a creature ({RECONFIGURE_RULE})"
    if game.controller_of(target).username != player:
        return f"{player} does not control {target.name} ({RECONFIGURE_RULE})"
    return _protection_refusal_for_attachment(game, equipment, target)


def reconfigure_attach_activation(
    game: Any, equipment: CardState, target: CardState, player: str
) -> KeywordActivation:
    """CR 702.151a's first ability: "[Cost]: Attach this permanent to another
    target creature you control. Activate only as a sorcery." The target is
    announced and checked here (CR 601.2c via CR 602.2b), rechecked on
    resolution (CR 608.2b). Hexproof and shroud are the target check's
    (`targeting.profile_for_text`)."""
    from .targeting import profile_for_text

    refusal = _attach_refusal(game, equipment, target, player)
    if refusal is not None:
        raise ValueError(refusal)
    activation = _activation(game, equipment, player, RECONFIGURE_ATTACH_EFFECT)
    profile_for_text("Attach this permanent to target creature you control.").check(
        [target], player, game, source_id=equipment.id
    )
    activation.targets = [TargetRef.to_card(target)]
    return activation


def reconfigure_unattach_refusal(game: Any, equipment: CardState) -> str | None:
    """CR 702.151a's second ability's own restriction (CR 602.5b): "Activate
    only if this permanent is attached to a creature"."""
    host = game.find_by_id(equipment.attached_to) if equipment.attached_to else None
    if (
        isinstance(host, CardState)
        and host.zone is Zone.BATTLEFIELD
        and _is_creature_now(game, host)
    ):
        return None
    return (
        f"{equipment.name}'s unattach can only be activated while it is attached to a "
        f"creature ({RECONFIGURE_RULE}, CR 602.5b)"
    )


def reconfigure_unattach_activation(
    game: Any, equipment: CardState, player: str
) -> KeywordActivation:
    """CR 702.151a's second ability: "[Cost]: Unattach this permanent.
    Activate only if this permanent is attached to a creature and only as a
    sorcery." `KeywordActivation.why_not` asks `reconfigure_unattach_
    refusal` for an untargeted reconfigure activation."""
    return _activation(game, equipment, player, RECONFIGURE_UNATTACH_EFFECT)


def _reconfigure_effect(activation: KeywordActivation) -> CardState | None:
    """Resolve either reconfigure ability (CR 608.2): attach to the target if
    it is still legal (CR 608.2b), or unattach (CR 701.3d)."""
    game = activation.game
    equipment = game.find_by_id(activation.card.id)
    if not isinstance(equipment, CardState):
        equipment = activation.card
    if equipment.zone is not Zone.BATTLEFIELD:
        return None
    if not activation.targets:
        equipment.unattach()
        return equipment
    for target in activation.targets:
        creature = game.resolve_target(target)
        if _attach_refusal(game, equipment, creature, activation.player) is not None:
            continue
        equipment.attach_to(creature)
        return creature
    return None


def reconfigure_not_a_creature(source: CardState, timestamp: int) -> list[Any]:
    """CR 702.151b: attached, an Equipment with reconfigure is not a creature
    (layer 4, CR 613.1d), for as long as it stays attached. Read off the
    printing, like `_impending_not_a_creature`: the effect came from the
    attaching, so a later ability-removing effect (layer 6) does not undo it
    (CR 613.6)."""
    if source.zone is not Zone.BATTLEFIELD or source.attached_to is None:
        return []
    if not has_reconfigure(source.card):
        return []
    from .layers import ContinuousEffect, Layer, RemoveType, _only

    return [
        ContinuousEffect(
            description=f"{source.name}: attached, not a creature (CR 702.151b)",
            layer=Layer.TYPE,
            timestamp=timestamp,
            source_id=source.id,
            selector=_only(source.id),
            modification=RemoveType(card_type=Type.CREATURE),
        )
    ]


KEYWORD_EFFECTS["reconfigure"] = _reconfigure_effect
