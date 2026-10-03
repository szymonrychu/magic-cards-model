"""How the trigger event happened: a trigger condition's own "while <doing
something>" qualifier (`TriggeredAbility.event_qualifier`).

"When you sacrifice this creature while casting a spell with emerge" (Foul
Emissary), "When this creature is exiled from the battlefield while you're
activating a craft ability" (Market Gnome), "Whenever you choose to put one or
more cards on the bottom of your library while scrying" (The Temporal Anchor):
each qualifier is part of the trigger event (CR 603.2), so it is read off the
event itself and answers False with no event to read.

Rules verified with `mise run rules:find`:

- CR 601.2h - a spell's total cost is paid while it is being cast; CR 602.2b
  - an ability's cost while it is being activated. `Game.paying_cost_of`
  marks every event raised meanwhile (`GameEvent.during_cost_of`).
- CR 702.119a (emerge) and CR 702.167a (craft) - the costs these sacrifice
  and exile with, whose keyword the mark carries.
- CR 606.4 - a loyalty ability's cost is a loyalty symbol "that may be
  modified by other effects"; CR 606.5 combines such costs. "you removed two
  or more loyalty counters to activate it" (Way of the Mind Sculptor) reads
  what the activation's cost actually removed, recorded on the event as
  `GameEvent.loyalty_removed` - so CR 603.4's recheck on resolution reads the
  activation, never the board it has since changed.
- CR 701.22a - scry's "put any number of them on the bottom of your library",
  the choice `Game.scry` raises as `TriggerEvent.LIBRARY_BOTTOM_CHOSEN`.
"""

import re
from typing import TYPE_CHECKING

from ...numbers import COUNT, parse_count
from . import ConditionReader

if TYPE_CHECKING:
    from . import ConditionContext


def _while_casting(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "casting a spell with emerge": the event happened while its player
    paid the total cost of a spell cast with that keyword (CR 601.2h)."""
    event = context.event
    if event is None or event.during_cost_of != "spell":
        return False
    if event.during_cost_player != context.controller:
        return False
    return event.during_cost_keyword == match.group("keyword")


def _while_activating(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you're activating a craft ability": the event happened while its
    player paid the cost of an ability that keyword expands (CR 602.2b)."""
    event = context.event
    if event is None or event.during_cost_of != "ability":
        return False
    if event.during_cost_player != context.controller:
        return False
    return event.during_cost_keyword == match.group("keyword")


def _while_doing_a_keyword_action(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "scrying": the event was a choice made during that keyword action."""
    event = context.event
    if event is None:
        return False
    return event.keyword_action == match.group("action")


def _removed_loyalty_counters(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you removed two or more loyalty counters to activate it": the loyalty
    ability whose activation is the trigger event had a cost that removed at
    least that many loyalty counters (CR 606.4)."""
    event = context.event
    if event is None or event.loyalty_removed is None:
        return False
    needed = parse_count(match.group("count"))
    return needed is not None and event.loyalty_removed >= needed


READERS: tuple[ConditionReader, ...] = (
    ConditionReader(
        re.compile(rf"you removed (?P<count>{COUNT}) or more loyalty counters? to activate it"),
        _removed_loyalty_counters,
    ),
    ConditionReader(
        re.compile(r"(?:you(?:'re| are) )?casting an? spell with (?P<keyword>[a-z][a-z-]*)"),
        _while_casting,
    ),
    ConditionReader(
        re.compile(r"(?:you(?:'re| are) )?activating an? (?P<keyword>[a-z][a-z-]*) ability"),
        _while_activating,
    ),
    ConditionReader(
        re.compile(r"(?P<action>scry|surveil)(?:ing|ling)"),
        _while_doing_a_keyword_action,
    ),
)
