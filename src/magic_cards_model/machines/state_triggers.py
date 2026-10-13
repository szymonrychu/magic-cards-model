"""CR 603.8 state triggers whose game state is a printed condition.

CR 603.8: "Some triggered abilities trigger when a game state (such as a player
controlling no permanents of a particular card type) is true, rather than
triggering when an event occurs. These abilities trigger as soon as the game
state matches the condition."

`machines/triggers.state_triggers_for` already sweeps the battlefield for the
counter-count shape ("there are N or more <kind> counters on <this>"). This
module is the other half: a state trigger whose condition is one the shared
condition reader (`machines/conditions`) already evaluates - "you control no
Swamps", "you control no snow lands", "you control no permanents with
phylactery counters on them", "you control no other creatures", "there are no
cards in your graveyard". It asks that reader rather than re-deriving any of
them, so every new board or player condition it learns is a state trigger for
free.

The entry gate is deliberately narrow (`STATE_CONDITION_START`): only a
condition that opens with the negative-count forms state triggers print is a
state trigger. An event-shaped condition that happens to be readable elsewhere
is never reinterpreted as a state.
"""

from __future__ import annotations

import re
from functools import cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from ..models.card_state import CardState
    from ..models.game import Game

#: The openings a printed state trigger uses for "nothing of this kind is
#: there": "When you control no Swamps", "When there are no cards in your
#: graveyard", "When there are no creatures on the battlefield", "When you have
#: no cards in hand".
STATE_CONDITION_START = re.compile(r"^(?:you control no|there are no|you have no) ", re.IGNORECASE)


#: "When Garruk has two or fewer loyalty counters on him": a permanent's own counter
#: count falling to a bound is a state (CR 603.8), where "has N or more counters" is
#: also printed as an event-shaped condition elsewhere, so only the "or fewer" bound
#: opens a state trigger here.
STATE_COUNTER_AT_MOST = re.compile(
    r"^.+? has [a-z0-9]+ or fewer [^.]+? counters on (?:him|her|it|them)$", re.IGNORECASE
)


@cache
def reads_state_condition(condition: str) -> bool:
    """Whether `condition` is a CR 603.8 state the condition reader evaluates."""
    from .conditions import claims

    text = condition.strip().rstrip(".")
    opens = STATE_CONDITION_START.match(text) or STATE_COUNTER_AT_MOST.match(text)
    return opens is not None and claims(text)


def state_condition_holds(game: Game, source: CardState, controller: str, condition: str) -> bool:
    """Whether the state `condition` names is true right now for `source`'s
    controller (CR 109.5's "you")."""
    from .conditions import ConditionContext, read_condition

    return bool(read_condition(ConditionContext(game, controller, source), condition))
