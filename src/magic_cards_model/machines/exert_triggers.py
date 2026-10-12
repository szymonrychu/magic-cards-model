"""The exert event and the "Whenever you exert a creature" triggers it feeds.

CR 701.43a: "To exert a permanent, you choose to have it not untap during your
next untap step." Exerting is a keyword action, so an ability can watch for it:
Battlefield Scavenger's "Whenever you exert a creature, ..." triggers each time
its controller exerts a creature - as it attacks (CR 701.43d, `machines/
exert_on_attack`) or as a cost (CR 701.43a, `machines/cost/components`).
CR 701.43b: a permanent can be exerted again before it untaps, and each of
those is still an exert, so each raises the event.

`exert_permanent` is the one place that exerts: it sets the flag
(`keywords.exert`), records the exert for "hasn't been exerted this turn"
(`Game.exerted_this_turn`) and raises `ExtraTriggerEvent.EXERTED`.
"""

import re
from typing import TYPE_CHECKING

from ..models.card_state import CardState

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers.events import GameEvent

#: "Whenever you exert a creature" (the Amonkhet exert payoffs). The controller
#: is the exerting player; the subject is any creature, the source included.
EXERT_CONDITION = re.compile(r"^you exert (?:a|an|another) (?P<what>creature|permanent)$")


def exert_permanent(game: "Game", permanent: CardState) -> CardState:
    """Exert `permanent` (CR 701.43a) and raise the exert event.

    Raises `ValueError` for a permanent that is not on the battlefield
    (CR 701.43c), exactly as `keywords.exert` does."""
    from .keywords import exert
    from .triggers.events import ExtraTriggerEvent, GameEvent

    exert(permanent)
    game.exerted_this_turn.add(permanent.id)
    controller = game.controller_of(permanent).username
    game.emit(
        GameEvent(
            event=ExtraTriggerEvent.EXERTED,
            subject_id=permanent.id,
            subject_name=permanent.name,
            subject_controller=controller,
            subject_types=tuple(game.characteristics_of(permanent).types),
            player=controller,
        )
    )
    return permanent


def exert_condition_matches(condition: str, controller: str, event: "GameEvent") -> bool:
    """Whether `event` is an exert by `controller` of what `condition` names."""
    from ..models.card import Type
    from .triggers.events import ExtraTriggerEvent

    match = EXERT_CONDITION.match(condition)
    if match is None or event.event is not ExtraTriggerEvent.EXERTED:
        return False
    if event.player != controller:
        return False
    return match.group("what") == "permanent" or Type.CREATURE in event.subject_types
