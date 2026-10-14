"""CR 701.3d's "unattach" instruction aimed at the permanent an Aura or
Equipment is attached to.

Two shapes, registered into the ability ladder by
`machines/effects/continuous.py` (the "attach" family):

- "Unattach enchanted `<noun>`." - Carry Away's "When this Aura enters,
  unattach enchanted Equipment.": the Equipment the Aura is on comes off
  whatever it equips.
- "`<instruction about the enchanted permanent>`. If it's an? `<subtype>`,
  unattach it." - Tamiyo's Compleation's "When this Aura enters, tap enchanted
  permanent. If it's an Equipment, unattach it."

CR 701.3d: "To 'unattach' an Equipment from a creature means to move it away
from that creature so the Equipment is on the battlefield but is not equipping
anything." The enchanted permanent is read off the source as the ability
resolves, or off its last known information if the source has left
(CR 608.2h).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from magic_cards_model.text_norm import collapsed

from ..models.card_state import CardState
from ..models.zone import Zone

if TYPE_CHECKING:
    from ..models.game import Game
    from .effects import AbilityEffect
    from .triggers import AbilityOnStack

_ATTACHED_NOUN = r"(?:creature|permanent|artifact|enchantment|land|planeswalker|Equipment|Vehicle)"

_UNATTACH_ATTACHED_RE = re.compile(
    rf"^unattach (?:enchanted|equipped) {_ATTACHED_NOUN}\.?$", re.IGNORECASE
)

_THEN_IF_SUBTYPE_UNATTACH_RE = re.compile(
    rf"^(?P<first>[^.]*\b(?:enchanted|equipped) {_ATTACHED_NOUN}\b[^.]*\.)\s*"
    r"if it'?s an? (?P<subtype>[A-Z][a-z]+), unattach it\.?$",
    re.IGNORECASE,
)


def attached_host(game: Game, ability: AbilityOnStack) -> CardState | None:
    """The permanent the ability's source is attached to - its last known
    host once the source has left the battlefield (CR 608.2h) - if that
    permanent is still on the battlefield."""
    source = ability.source(game)
    if source is None:
        return None
    host_id = (
        source.attached_to if source.zone is Zone.BATTLEFIELD else source.last_known_attached_to
    )
    if host_id is None:
        return None
    host = game.find_by_id(host_id)
    if not isinstance(host, CardState) or host.zone is not Zone.BATTLEFIELD:
        return None
    return host


def parse_unattach_attached_clause(effect_text: str) -> AbilityEffect | None:
    """`_UNATTACH_ATTACHED_RE`'s shape, or `None`."""
    if _UNATTACH_ATTACHED_RE.fullmatch(collapsed(effect_text)) is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        host = attached_host(game, ability)
        if host is not None and host.attachment is not None:
            host.unattach()

    return effect


def parse_then_if_subtype_unattach_clause(effect_text: str) -> AbilityEffect | None:
    """`_THEN_IF_SUBTYPE_UNATTACH_RE`'s shape, or `None`: the first sentence
    read whole by the ordinary readers, then the enchanted permanent comes
    off what it is attached to if it has the named subtype (CR 205.3) as the
    rider resolves."""
    match = _THEN_IF_SUBTYPE_UNATTACH_RE.fullmatch(collapsed(effect_text))
    if match is None:
        return None
    from .effects import parse_mixed_effect

    first = parse_mixed_effect(match.group("first"))
    if first is None:
        return None
    subtype = match.group("subtype").capitalize()

    def effect(game: Game, ability: AbilityOnStack) -> None:
        first(game, ability)
        host = attached_host(game, ability)
        if (
            host is not None
            and host.attachment is not None
            and subtype in game.characteristics_of(host).subtypes
        ):
            host.unattach()

    return effect
