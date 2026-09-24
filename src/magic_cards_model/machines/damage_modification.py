"""Static replacement effects that modify a damage event as it would happen
(CR 614.1a, CR 614.2), compiled from a permanent's own printed text.

`machines/replacement.py` owns the replacement machinery - parsing a
permanent's "If ... would ..., ... instead" sentences into `ReplacementEffect`
records, gathering the applicable ones off the battlefield, and CR 616.1's
ordering. This module only adds two more of its `_COMPILERS`:

- `compile_damage_plus_source_characteristic` - "If a source you control
  would deal noncombat damage to an opponent or a permanent an opponent
  controls, instead it deals that much damage plus X, where X is Hawkeye's
  power." (Hawkeye, Young Avenger). The same event shape and recipient phrases
  `replacement._compile_damage_plus_amount` reads for Torbran's fixed "plus
  2", with an addend read off the permanent carrying the effect each time
  the replacement applies.
- `compile_heal_other_damage` - "If damage would be dealt to Wolverine,
  instead that damage is dealt, but all other damage already dealt to him is
  healed." (Wolverine, Fierce Fighter): the damage is dealt unchanged, and
  the damage already marked on the permanent (CR 120.3e) is removed first.
  Combat damage is one simultaneous event (CR 510.2), so damage another
  source dealt in the same combat damage step is not "already dealt" and is
  kept (`Game.combat_damage_marked_this_step`).

The replacement-module names are imported inside each function: this module
is itself imported by `machines/replacement.py` while that module is still
loading.
"""

import re
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.zone import Zone

if TYPE_CHECKING:
    from ..models.game import Game
    from .replacement import CardReplacement, ReplaceableEvent, ReplacementEffect

#: "it deals that much damage plus X, where X is `<name>`'s power" - the
#: addend a characteristic of the permanent that has the effect (CR 201.5:
#: its own name, or its short name, or "this creature").
_PLUS_SOURCE_CHARACTERISTIC_RE = re.compile(
    r"^it deals that much damage plus x, where x is (?P<who>.+?)'s "
    r"(?P<stat>power|toughness)$",
    re.IGNORECASE,
)


def _names_itself(who: str, holder: CardState) -> bool:
    """Whether `who` is how `holder`'s own text names it (CR 201.5)."""
    lowered = who.strip().lower()
    names = {
        "this creature",
        "this permanent",
        holder.name.lower(),
        holder.name.split(",")[0].strip().lower(),
    }
    return lowered in names


def compile_damage_plus_source_characteristic(
    effect: "ReplacementEffect",
) -> "CardReplacement | None":
    """Hawkeye, Young Avenger's shape - see the module docstring."""
    from .replacement import (
        _DAMAGE_RECIPIENTS,
        _SOURCE_YOU_CONTROL_DAMAGE_EVENT_RE,
        CardReplacement,
        EventKind,
        ReplacementKind,
    )

    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    event_match = _SOURCE_YOU_CONTROL_DAMAGE_EVENT_RE.fullmatch((effect.event or "").strip())
    if event_match is None:
        return None
    recipient = _DAMAGE_RECIPIENTS.get(event_match.group("recipient").strip().lower())
    if recipient is None:
        return None
    match = _PLUS_SOURCE_CHARACTERISTIC_RE.fullmatch((effect.replacement or "").strip().rstrip("."))
    if match is None:
        return None
    quality = event_match.group("quality")
    noncombat = event_match.group("noncombat") is not None
    who = match.group("who")
    wants_power = match.group("stat").lower() == "power"

    def applies(game: "Game", source: CardState, event: "ReplaceableEvent") -> bool:
        if event.kind is not EventKind.DAMAGE or event.source is None:
            return False
        if noncombat and event.combat:
            return False
        if not _names_itself(who, source):
            return False
        controller = game.controller_of(source).username
        if game.controller_of(event.source).username != controller:
            return False
        if quality is not None and not game.source_has_quality(event.source, quality):
            return False
        return recipient(game, controller, event)

    def apply(game: "Game", source: CardState, event: "ReplaceableEvent") -> None:
        # The characteristic as this replacement applies, off the computed
        # board (CR 613.5).
        value = game.power_of(source) if wants_power else game.toughness_of(source)
        event.amount += max(value or 0, 0)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


#: "If damage would be dealt to `<name>`" / "... that damage is dealt, but all
#: other damage already dealt to him is healed".
_DAMAGE_DEALT_TO_SELF_EVENT_RE = re.compile(
    r"^damage would be dealt to (?P<who>.+)$", re.IGNORECASE
)
_HEAL_OTHER_DAMAGE_RE = re.compile(
    r"^that damage is dealt, but all other damage already dealt to (?:it|him|her|them) "
    r"is healed$",
    re.IGNORECASE,
)


def compile_heal_other_damage(effect: "ReplacementEffect") -> "CardReplacement | None":
    """Wolverine, Fierce Fighter's shape - see the module docstring."""
    from .replacement import CardReplacement, EventKind, ReplacementKind

    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    event_match = _DAMAGE_DEALT_TO_SELF_EVENT_RE.fullmatch((effect.event or "").strip())
    if event_match is None:
        return None
    if _HEAL_OTHER_DAMAGE_RE.fullmatch((effect.replacement or "").strip().rstrip(".")) is None:
        return None
    who = event_match.group("who")

    def applies(game: "Game", source: CardState, event: "ReplaceableEvent") -> bool:
        return (
            event.kind is EventKind.DAMAGE
            and event.card is not None
            and event.card.id == source.id
            and source.zone is Zone.BATTLEFIELD
            and _names_itself(who, source)
        )

    def apply(game: "Game", source: CardState, event: "ReplaceableEvent") -> None:
        simultaneous = game.combat_damage_marked_this_step(source) if event.combat else 0
        source.damage = min(source.damage, simultaneous)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)
