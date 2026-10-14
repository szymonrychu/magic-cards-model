"""EP-02 R3 T1: the non-static clauses of the static-for-each-pump cards (events)."""
"""EP-02 R3 T1: the event-driven clauses of the static-for-each-pump cards.

- "each player gains control of each land they own that you control" (Herald of
  Leshrac's leaves-the-battlefield trigger): a layer 2 control change with no
  duration (CR 613.1b, CR 611.2a) for every land on the battlefield that
  `you` control and another player owns (CR 108.3), applied to each object as
  it is now (CR 400.7).
"""

import re
from typing import TYPE_CHECKING, Any

from .effects._chains import ABILITY_TEXT

if TYPE_CHECKING:
    from ..models.game import Game

_RETURN_LANDS_RE = re.compile(
    r"^each player gains control of each (?P<noun>land|permanent|creature|artifact) they own "
    r"that you control\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_each_player_regains_what_they_own(text: str) -> Any:
    """ "Each player gains control of each `<permanent>` they own that you
    control" (CR 701.?): every such permanent goes back to its owner."""
    match = _RETURN_LANDS_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    from ..models.card import Type

    wanted = {
        "land": Type.LAND,
        "permanent": None,
        "creature": Type.CREATURE,
        "artifact": Type.ARTIFACT,
    }[match["noun"].lower()]

    def effect(game: "Game", ability: Any) -> None:
        from .layers import (
            ContinuousEffect,
            Duration,
            Layer,
            only_this_incarnation,
            set_controller,
        )

        controller = game.controller_of(ability).username
        board = game.computed_board()
        store = game.continuous_effects
        timestamp = store.tick()
        for permanent in list(game.battlefield):
            chars = board.of(permanent)
            if chars.controller != controller or permanent.owner in (None, controller):
                continue
            if wanted is not None and wanted not in chars.types:
                continue
            store.add(
                ContinuousEffect(
                    description=f"{permanent.owner} gains control of {permanent.name}",
                    layer=Layer.CONTROL,
                    timestamp=timestamp,
                    duration=Duration.INDEFINITE,
                    selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                    modification=set_controller(permanent.owner),
                ),
                game,
            )

    return effect
