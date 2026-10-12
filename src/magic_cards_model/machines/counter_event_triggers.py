"""CR 122.6 counter events as trigger conditions, in the singular and the
removal direction.

`machines/triggers` already reads the plural "one or more <kind> counters are
put on <subject>" (one event, however many counters, CR 603.2c). This module
adds the two shapes it left unread:

- **"a[n] [<kind>] counter is put on <subject>"** - the singular form
  (Hollowmurk Siege: "Whenever a counter is put on a creature you control").
- **"a[n] [<kind>] counter is removed from <subject>"** and its plural twin
  (Protean Hydra: "Whenever a +1/+1 counter is removed from this creature").

Removal is a new event, `ExtraTriggerEvent.COUNTERS_REMOVED`, raised by
`CardState.remove_counters` (through `Game.note_counters_removed`) whatever
removed the counters: a cost, an effect, or a damage replacement.

CR 603.2c: "An ability triggers only once each time its trigger event occurs.
However, it can trigger repeatedly if one event contains multiple
occurrences." One instruction that moves three counters is one event holding
three occurrences, so the singular "a counter" form triggers three times
(`counter_event_occurrences`) while the plural "one or more" form triggers
once. An ability that triggers "only once each turn" (CR 603.2h) is never
multiplied.

The subject is one of: the ability's own source ("this creature"), or a
quality of permanent ("a creature you control", "another permanent you
control", "a creature an opponent controls", "a creature").
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.zone import Zone
from .triggers.events import ExtraTriggerEvent, GameEvent

if TYPE_CHECKING:  # pragma: no cover
    from ..models.game import Game
    from .abilities import TriggeredAbility

COUNTER_EVENT_CONDITION = re.compile(
    r"^(?P<quantity>an?|one or more) "
    r"(?:(?!counters?\b)(?P<kind>[a-z0-9+/-]+) )?counters? "
    r"(?:is|are) (?P<verb>put on|removed from) (?P<subject>.+)$"
)

_SELF_SUBJECT = re.compile(r"^(?:it|this [a-z]+(?: [a-z]+)?)$")
_QUALITY_SUBJECT = re.compile(
    r"^(?:(?P<article>another|an?) )?(?P<quality>[a-z][a-z -]*?)"
    r"(?P<whose> you control| an opponent controls| your opponents control)?$"
)


def read_counter_event(condition: str) -> re.Match[str] | None:
    """The singular put/removed shape this module owns, or None.

    A plural "one or more ... are put on" is the older reader's, so it is
    declined here; a plural removal is this module's."""
    match = COUNTER_EVENT_CONDITION.match(condition.strip().lower())
    if match is None:
        return None
    if match["verb"] == "put on" and match["quantity"] == "one or more":
        return None
    if "while" in match["subject"]:
        return None
    return match


def counter_event_watched(condition: str) -> frozenset[ExtraTriggerEvent]:
    """The event a condition this module reads watches, or an empty set."""
    match = read_counter_event(condition)
    if match is None:
        return frozenset()
    if match["verb"] == "put on":
        return frozenset({ExtraTriggerEvent.COUNTERS_PUT})
    return frozenset({ExtraTriggerEvent.COUNTERS_REMOVED})


def counter_event_matches(
    game: Game,
    condition: str,
    source: CardState,
    controller: str,
    event: GameEvent,
    *,
    mine: bool,
) -> bool:
    """Whether `event` is the counter event `condition` names (CR 122.6).

    `mine` is whether the condition's subject words name the source itself
    (the caller's `_self_referential`)."""
    match = read_counter_event(condition)
    if match is None:
        return False
    wanted = (
        ExtraTriggerEvent.COUNTERS_PUT
        if match["verb"] == "put on"
        else ExtraTriggerEvent.COUNTERS_REMOVED
    )
    if event.event is not wanted:
        return False
    if match["kind"] is not None and (event.counter_kind or "").lower() != match["kind"]:
        return False
    subject = match["subject"].strip()
    if _SELF_SUBJECT.match(subject) or mine:
        return event.subject_id == source.id
    quality_match = _QUALITY_SUBJECT.match(subject)
    if quality_match is None:
        return False
    from ..models.game import _permanent_quality

    quality = _permanent_quality(quality_match["quality"])
    if quality is None:
        return False
    if quality_match["article"] == "another" and event.subject_id == source.id:
        return False
    permanent = game.find_by_id(event.subject_id) if event.subject_id else None
    if not isinstance(permanent, CardState) or permanent.zone is not Zone.BATTLEFIELD:
        return False
    owner = game.controller_of(permanent).username
    whose = (quality_match["whose"] or "").strip()
    if whose == "you control" and owner != controller:
        return False
    if whose in ("an opponent controls", "your opponents control") and owner == controller:
        return False
    return quality(game.characteristics_of(permanent))


def counter_event_occurrences(ability: TriggeredAbility, event: GameEvent) -> int:
    """How many times one event triggers `ability` (CR 603.2c).

    A singular "a counter" condition counts each counter the event carries as
    its own occurrence; "one or more" is one occurrence however many arrive,
    and a once-each-turn ability (CR 603.2h) is never repeated."""
    match = read_counter_event(ability.condition)
    if match is None or match["quantity"] == "one or more" or ability.once_per_turn:
        return 1
    return max(event.amount or 1, 1)
