"""A Siege's intrinsic defeat trigger (CR 310.12b).

CR 310.12b: "Sieges have the intrinsic ability 'When the last defense counter
is removed from this permanent, exile it, then you may cast it transformed
without paying its mana cost.'" Nothing prints it - the reminder text on a
Siege is reminder text (CR 207.2a) - so `siege_triggered_abilities` writes it
out for every card whose front face is a Siege (CR 205.3q: Siege is the one
battle type), the way `machines/keywords.py` writes out a keyword's
triggered abilities.

The condition is read by `machines/triggers._LAST_COUNTER_CONDITION` against
`ExtraTriggerEvent.LAST_COUNTER_REMOVED`; the effect by
`exile_then_cast_transformed_effect` below. Defense 0 without the trigger
pending is CR 704.5v's state-based action
(`Game._defeated_battles_to_put_into_graveyard`).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from magic_cards_model.text_norm import collapsed

from ..models.card import Card, Type, subtypes_of, types_of
from ..models.zone import Zone
from .abilities import TriggeredAbility, TriggerWord
from .decisions import source_id_of

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game
    from .effects import AbilityEffect
    from .triggers import AbilityOnStack

DEFEAT_CONDITION = "the last defense counter is removed from this permanent"
DEFEAT_EFFECT = "exile it, then you may cast it transformed without paying its mana cost"

#: "exile it, then you may cast it transformed without paying its mana cost"
#: - CR 310.12b's effect, and the same instruction on any ability whose "it"
#: is its own source.
_EXILE_THEN_CAST_TRANSFORMED_RE = re.compile(
    r"^exile (?:it|this permanent), then you may cast it transformed "
    r"without paying its mana cost\.?$",
    re.IGNORECASE,
)


def _defeat_trigger(face: str) -> TriggeredAbility:
    return TriggeredAbility(
        raw=f"When {DEFEAT_CONDITION}, {DEFEAT_EFFECT}.",
        text=f"When {DEFEAT_CONDITION}, {DEFEAT_EFFECT}.",
        face=face,
        word=TriggerWord.WHEN,
        condition=DEFEAT_CONDITION,
        effect=DEFEAT_EFFECT,
        event=None,
    )


def siege_triggered_abilities(card: Card) -> list[TriggeredAbility]:
    """CR 310.12b's intrinsic trigger, for a card whose front face is a
    Siege battle; none for anything else. It belongs to the front face, so
    it stops functioning once the permanent is transformed."""
    front = card.card_faces[0] if card.card_faces else card
    if Type.BATTLE not in types_of(front.type_line) or "Siege" not in subtypes_of(front.type_line):
        return []
    return [_defeat_trigger(front.name)]


def copied_siege_triggered_abilities(game: Game, source: CardState) -> list[TriggeredAbility]:
    """CR 310.12b's trigger for a permanent whose copiable values a copy
    effect rewrote into a Siege battle (CR 707.2) - Clever Impersonator
    entering as a copy of one. Its printed card is not a Siege, so
    `siege_triggered_abilities` cannot see it; the computed board can.
    Written with no face, like any ability the printed card does not carry."""
    chars = game.characteristics_of(source)
    if Type.BATTLE not in chars.types or "Siege" not in chars.subtypes:
        return []
    return [_defeat_trigger("")]


def exile_then_cast_transformed_effect(effect_text: str) -> AbilityEffect | None:
    """`_EXILE_THEN_CAST_TRANSFORMED_RE`'s instruction, or `None`.

    "Exile it" is the ability's own source, and only the object that
    triggered it (CR 400.7): one that already left the battlefield is not
    exiled, and then there is no "it" to cast. The cast is made while the
    ability resolves (CR 608.2g), by its controller, back face up (CR
    712.11a), without paying its mana cost (CR 118.9)."""
    if _EXILE_THEN_CAST_TRANSFORMED_RE.fullmatch(collapsed(effect_text)) is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if (
            source is None
            or source.zone is not Zone.BATTLEFIELD
            or (
                ability.source_stamp is not None
                and source.zone_change_stamp != ability.source_stamp
            )
        ):
            return
        game.exile_permanent(source)
        if source.zone is not Zone.EXILE or source.card.back_face is None:
            # CR 712.11a casts a double-faced card back face up; a card with
            # no back face (a copy of a Siege) has nothing to cast that way.
            return
        game.may_cast_during_resolution(
            source,
            ability.controller,
            prompt=f"cast {source.name} transformed without paying its mana cost",
            source=ability.source_name,
            source_id=source_id_of(ability),
            source_name=ability.source_name,
            rule="CR 310.12b",
            transformed=True,
        )

    return effect
