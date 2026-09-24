"""Control-changing effects with a stated duration (CR 613.1b, layer 2), and
the "tap it; it loses all abilities / doesn't untap / can't become untapped
for as long as ..." riders that ride on the same kind of one-shot
instruction.

Entry points `control_change_ability_effect`/`control_change_spell_effect`
are tried by `machines/effects.py` ahead of its clause split: every shape
here is two sentences joined by an anaphor ("It", "That creature"), which
`_prepare_effect_clauses` would cut apart.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models.card_state import CANT_BECOME_UNTAPPED_TEXT, CardState
from ..models.zone import Zone
from .layers import (
    DOESNT_UNTAP_TEXT,
    Condition,
    ContinuousEffect,
    Duration,
    Layer,
    Modification,
    RemainsOnBattlefield,
    YouStillControl,
    grant_ability,
    lose_all_abilities,
    only_this_incarnation,
)

if TYPE_CHECKING:
    from ..models.game import Game
    from .effects import AbilityEffect, Effect
    from .triggers import AbilityOnStack

#: A self-reference: "this <noun>" once `self_normalized_effect_text` has
#: rewritten the card's own name, or the printed name itself (CR 201.5: a
#: card's name in its own text means that object) - `trigger_effect_for`
#: tries the unnormalized text first.
_SELF = (
    r"(?:this (?:creature|permanent|saga|enchantment|artifact|land|planeswalker)"
    r"|[A-Z][^.]*?)"
)

#: "Tap `<target>`. `<It|That creature|They|...>` `<rider>` for as long as
#: `<you control this|this remains on the battlefield>`." - The Wondrous Wasp
#: ("It loses all abilities for as long as The Wondrous Wasp remains on the
#: battlefield"), Spider-Woman, Secret Agent ("That creature can't become
#: untapped for as long as you control Spider-Woman"), Dungeon Geists, Ty Lee,
#: Chi Blocker, Icefall Regent, Tidebinder Mage and Time of Ice ("... doesn't
#: untap during its controller's untap step for as long as you control ...").
#:
#: CR 701.26a taps each target; the rider is a layer 6 effect (CR 613.1f)
#: with CR 611.2b's "for as long as" duration, which is the *source's*: it
#: never starts if the source is already gone (or already out of its
#: controller's hands) as the ability resolves, and the tap still happens.
_TAP_THEN_LOCK_RE = re.compile(
    r"^tap (?P<phrase>(?:up to (?:one|two|three|four|\d+) )?target [^.]+?)\.\s*"
    r"(?:it|that creature|that permanent|those creatures|those permanents|they) "
    r"(?P<rider>loses? all abilities"
    r"|(?:doesn'?t|don'?t) untap during (?:its controller'?s|their controllers'?) untap steps?"
    r"|can'?t become untapped)"
    rf" for as long as (?:you control (?P<controlled>{_SELF})|(?P<remains>{_SELF}) remains "
    r"on the battlefield)\.?$",
    re.IGNORECASE,
)


def _lock_condition(game: Game, ability: AbilityOnStack, *, controlled: bool) -> Condition | None:
    """The CR 611.2b condition built off the ability's source as it resolves,
    or `None` when the duration never starts: the source is not the object
    that put the ability on the stack any more (CR 400.7), or - for "you
    control" - it is not controlled by the ability's controller."""
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD or source.zone_change_stamp is None:
        return None
    if ability.source_stamp is not None and source.zone_change_stamp != ability.source_stamp:
        return None
    if controlled:
        if source.controller != ability.controller:
            return None
        return YouStillControl(
            card_id=source.id, stamp=source.zone_change_stamp, controller=ability.controller
        )
    return RemainsOnBattlefield(card_id=source.id, stamp=source.zone_change_stamp)


def _rider_modification(rider: str) -> tuple[str, Modification]:
    lowered = rider.lower()
    if lowered.startswith("lose"):
        return "loses all abilities", lose_all_abilities
    if lowered.startswith("can"):
        return "can't become untapped", grant_ability(CANT_BECOME_UNTAPPED_TEXT)
    return "doesn't untap during its controller's untap step", grant_ability(DOESNT_UNTAP_TEXT)


def _parse_tap_then_lock_clause(effect_text: str) -> AbilityEffect | None:
    """`_TAP_THEN_LOCK_RE`'s shape, or `None`."""
    from .effects import _targets_understood

    match = _TAP_THEN_LOCK_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    what, modification = _rider_modification(match.group("rider"))
    controlled = match.group("controlled") is not None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        targets = [
            target
            for target in game.resolve_card_targets(ability)
            if target.zone is Zone.BATTLEFIELD
        ]
        for target in targets:
            target.tap_if_untapped()
        condition = _lock_condition(game, ability, controlled=controlled)
        if condition is None:
            return
        store = game.continuous_effects
        timestamp = store.tick()
        for target in targets:
            store.add(
                ContinuousEffect(
                    description=f"{ability.source_name}: {target.name} {what}",
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    duration=Duration.FOR_AS_LONG_AS,
                    condition=condition,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=modification,
                ),
                game=game,
            )

    return effect


def control_change_ability_effect(effect_text: str) -> AbilityEffect | None:
    """A control change or rider on an activated or triggered ability."""
    for reader in (_parse_tap_then_lock_clause,):
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None


def control_change_spell_effect(effect_text: str) -> Effect | None:
    """A control change or rider on a resolving spell."""
    return None


__all__ = [
    "CardState",
    "control_change_ability_effect",
    "control_change_spell_effect",
]
