"""Blitz (CR 702.152).

CR 702.152a: "Blitz represents three abilities: two static abilities that
function while the card with blitz is on the stack, one of which may create a
delayed triggered ability, and a static ability that functions while the
object with blitz is on the battlefield. 'Blitz [cost]' means 'You may cast
this card by paying [cost] rather than its mana cost,' 'If this spell's blitz
cost was paid, sacrifice the permanent this spell becomes at the beginning of
the next end step,' and 'As long as this permanent's blitz cost was paid, it
has haste and "When this permanent is put into a graveyard from the
battlefield, draw a card."'"

Three abilities, three places:

- the alternative cost is `machines/casting/options.py`'s `keyword_cast_
  options` (dash's shape, CR 702.109a);
- the delayed sacrifice is `create_blitz_delayed_trigger` below, created as
  the permanent is put onto the battlefield (CR 608.3g) from `Game._create_
  resolution_delayed_triggers`, the same place dash's and warp's are;
- the battlefield static is `blitz_static_effects` below, a layer 6 grant
  (CR 613.1f) built with every other static effect each time the board is
  computed (`machines/layers/registry.effects_for`), for as long as the
  object is the one cast for its blitz cost - `CardState.cast_with_keyword`,
  which CR 400.7 clears the moment it changes zones.
"""

from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.zone import Zone
from .abilities import TriggerEvent
from .turn import Step

if TYPE_CHECKING:  # pragma: no cover
    from ..models.game import Game

__all__ = [
    "BLITZ_ABILITY_TEXTS",
    "BLITZ_RULE",
    "blitz_static_effects",
    "create_blitz_delayed_trigger",
    "was_blitzed",
]

BLITZ_RULE = "CR 702.152a"

#: The two abilities CR 702.152a's battlefield static grants, the second in
#: the rule's own words.
BLITZ_ABILITY_TEXTS: tuple[str, ...] = (
    "Haste",
    "When this permanent is put into a graveyard from the battlefield, draw a card.",
)


def was_blitzed(permanent: CardState) -> bool:
    """Whether this object is the permanent a spell cast for its blitz cost
    became (CR 702.152a's "as long as this permanent's blitz cost was
    paid")."""
    return (permanent.cast_with_keyword or "").lower() == "blitz"


def blitz_static_effects(source: CardState, timestamp: int) -> list[Any]:
    """CR 702.152a's third ability: haste and the dies-draw, as layer 6
    additions stamped with the permanent's own timestamp (CR 613.7a)."""
    if source.zone is not Zone.BATTLEFIELD or not was_blitzed(source):
        return []
    from .layers import ContinuousEffect, Layer, _only, grant_ability

    return [
        ContinuousEffect(
            description=f"{source.name}: blitz cost paid, has {text!r} ({BLITZ_RULE})",
            layer=Layer.ABILITY,
            timestamp=timestamp,
            source_id=source.id,
            selector=_only(source.id),
            modification=grant_ability(text),
        )
        for text in BLITZ_ABILITY_TEXTS
    ]


def create_blitz_delayed_trigger(game: "Game", permanent: CardState) -> None:
    """CR 702.152a's second ability, created as the permanent enters (CR
    608.3g): "sacrifice the permanent this spell becomes at the beginning of
    the next end step".

    CR 603.7d gives it the spell's controller as it resolved; CR 603.7c's
    expected zone and stamp keep it off a permanent that left and came back.
    The sacrifice is `SacrificeEach` over the one object, which is
    `Game.sacrifice` (CR 701.21a) by that controller only - a permanent
    someone else has taken control of is not theirs to sacrifice.
    """
    from .delayed import DelayedTrigger, SacrificeEach

    if not was_blitzed(permanent) or permanent.zone is not Zone.BATTLEFIELD:
        return
    controller = permanent.controller or game.active_player.username
    game.delayed_triggers.create(
        DelayedTrigger(
            text=(
                "Sacrifice the permanent this spell becomes at the beginning of the next end step."
            ),
            effect=SacrificeEach(subjects=((permanent.id, permanent.zone_change_stamp),)),
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=Step.END_STEP,
            controller=controller,
            source_id=permanent.id,
            source_name=permanent.name,
            subject_id=permanent.id,
            expected_zone=Zone.BATTLEFIELD,  # CR 603.7c
            expected_stamp=permanent.zone_change_stamp,  # CR 603.7c parenthetical
        )
    )
