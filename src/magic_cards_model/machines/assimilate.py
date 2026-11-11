"""Assimilate - CR 701.72, the trk keyword action.

CR 701.72a: "To assimilate a permanent, gain control of it and put a +1/+1
counter on it. It becomes a Borg artifact creature." CR 701.72b: "To
assimilate a permanent card that's in a zone other than the battlefield, put
it onto the battlefield under your control with a +1/+1 counter on it. It's
a Borg artifact creature." The reminder text every printing carries spells
the type change out: "It's a Borg artifact creature and loses all other
creature types."

The type change is three layer 4 effects (CR 613.1d) sharing one timestamp:
gain the artifact and creature card types (CR 205.1b keeps the others) and
set the creature types to exactly Borg (`SetCreatureTypes`, CR 205.1a's
replacement of the creature-type set, a changeling's included since its
CDA applies first, CR 613.3). The control change of the permanent form is a
layer 2 effect (CR 613.1b). No duration is printed, so each lasts until the
end of the game (CR 611.2a), keyed to the object as it is now: a permanent
that leaves and comes back is a new object (CR 400.7) and is no longer
assimilated. A later type change applies after these in timestamp order
(CR 613.7), so a creature type granted afterwards is added back on top.

The clause readers that perform it live in `machines/effects/returns.py`
(`_parse_reanimate_by_assimilating_target_clause`,
`_parse_reanimate_by_assimilating_exiled_card_clause`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.card import Type
from ..models.card_state import CardState
from ..models.zone import Zone
from .layers import (
    AddType,
    ContinuousEffect,
    Duration,
    Layer,
    SetCreatureTypes,
    only_this_incarnation,
    set_controller,
)

if TYPE_CHECKING:
    from ..models.game import Game

#: The creature type CR 701.72a/b name.
BORG = "Borg"


def _make_borg(game: Game, permanent: CardState, source_name: str, timestamp: int) -> None:
    """The layer 4 half of CR 701.72a/b on `permanent` as it is now."""
    selector = only_this_incarnation(permanent, permanent.zone_change_stamp)
    for modification in (
        AddType(card_type=Type.ARTIFACT),
        AddType(card_type=Type.CREATURE),
        SetCreatureTypes(subtypes=(BORG,)),
    ):
        game.continuous_effects.add(
            ContinuousEffect(
                description=f"{source_name}: {permanent.name} is a Borg artifact creature",
                layer=Layer.TYPE,
                timestamp=timestamp,
                duration=Duration.INDEFINITE,
                selector=selector,
                modification=modification,
            ),
            game,
        )


def assimilate_card(game: Game, controller: str, card: CardState, *, source_name: str) -> bool:
    """CR 701.72b: put `card` (in a zone other than the battlefield) onto the
    battlefield under `controller`'s control with a +1/+1 counter on it, a
    Borg artifact creature. Returns whether it arrived (a card that left its
    zone, or a replacement that sent it elsewhere, is not assimilated)."""
    if card.zone is Zone.BATTLEFIELD:
        return assimilate_permanent(game, controller, card, source_name=source_name)
    with game._id_allocator_scope(), game.entering_together():  # noqa: SLF001 - persisted ids
        game.put_onto_battlefield(card, controller, counters={"+1/+1": 1})
        if card.zone is not Zone.BATTLEFIELD:
            return False
        _make_borg(game, card, source_name, game.continuous_effects.tick())
    return True


def assimilate_permanent(
    game: Game, controller: str, permanent: CardState, *, source_name: str
) -> bool:
    """CR 701.72a: gain control of `permanent` (layer 2, no duration), put a
    +1/+1 counter on it and make it a Borg artifact creature."""
    if permanent.zone is not Zone.BATTLEFIELD:
        return False
    with game._id_allocator_scope():  # noqa: SLF001 - ids minted here are persisted
        _assimilate_permanent(game, controller, permanent, source_name)
    return True


def _assimilate_permanent(
    game: Game, controller: str, permanent: CardState, source_name: str
) -> None:
    timestamp = game.continuous_effects.tick()
    game.continuous_effects.add(
        ContinuousEffect(
            description=f"{source_name}: {controller} gains control of {permanent.name}",
            layer=Layer.CONTROL,
            timestamp=timestamp,
            duration=Duration.INDEFINITE,
            selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
            modification=set_controller(controller),
        ),
        game,
    )
    game.add_counters(permanent, "+1/+1", 1, putter=controller)
    _make_borg(game, permanent, source_name, timestamp)
