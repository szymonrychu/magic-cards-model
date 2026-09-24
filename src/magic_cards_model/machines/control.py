"""Control-changing instructions a resolving spell or ability performs
(CR 613.1b's layer 2), beyond the "gain control of ... until end of turn"
shape `machines/layers.py` reads as a layer sentence.

`exchange_control` is CR 701.12's exchange of two permanents: Bilbo,
Luckwearer // Burglar's Plot's "Exchange control of two target nonland
permanents that share a card type.", Switcheroo's "Exchange control of two
target creatures.", Shifting Loyalties' "... two target permanents that share
a card type.".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.zone import Zone
from .layers import ContinuousEffect, Duration, Layer, only_this_incarnation, set_controller

if TYPE_CHECKING:
    from ..models.game import Game


def exchange_control(
    game: Game,
    first: CardState,
    second: CardState,
    *,
    source_name: str,
    share_a_card_type: bool = False,
) -> bool:
    """Exchange control of `first` and `second` (CR 701.12), or do nothing.

    - CR 701.12a: "if the entire exchange can't be completed, no part of the
      exchange occurs" - both must still be on the battlefield, and, for a
      pair that must "share a card type", still share one (their computed
      types, CR 613.1d);
    - CR 701.12b: "if those permanents are controlled by the same player, the
      exchange effect does nothing", otherwise "each of those players
      simultaneously gains control of the permanent that was controlled by
      the other player".

    The control change is two layer 2 effects (CR 613.1b) with one shared
    timestamp (simultaneous, CR 613.7b) and no duration - CR 611.2a: "If no
    duration is stated, it lasts until the end of the game" - each keyed to
    the object as it is now (CR 400.7). Returns whether the exchange happened.
    """
    if first.zone is not Zone.BATTLEFIELD or second.zone is not Zone.BATTLEFIELD:
        return False
    if first.id == second.id:
        return False
    if share_a_card_type:
        common = set(game.characteristics_of(first).types) & set(
            game.characteristics_of(second).types
        )
        if not common:
            return False
    first_controller = game.controller_of(first).username
    second_controller = game.controller_of(second).username
    if first_controller == second_controller:
        return False
    store = game.continuous_effects
    timestamp = store.tick()
    for permanent, new_controller in ((first, second_controller), (second, first_controller)):
        store.add(
            ContinuousEffect(
                description=f"{source_name}: {new_controller} gains control of {permanent.name}",
                layer=Layer.CONTROL,
                timestamp=timestamp,
                duration=Duration.INDEFINITE,
                selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                modification=set_controller(new_controller),
            ),
            game,
        )
    return True
