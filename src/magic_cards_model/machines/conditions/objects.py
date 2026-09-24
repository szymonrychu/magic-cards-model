"""Object-state conditions: the source's own state and the trigger event's own
subject ("it", "that creature"), with last known information for a subject
that has left (CR 603.10a).

Each reader here is a `ConditionReader` registered through `READERS`; see
`machines/conditions/__init__.py` for the contract every reader keeps.

Rules verified with `mise run rules:find`:

- CR 605.1a: what makes an activated ability a mana ability - recorded on the
  activation event as `GameEvent.mana_ability`.
- CR 508.1f: "Tapping a creature when it's declared as an attacker isn't a
  cost; attacking simply causes creatures to become tapped" - recorded on
  that tap's event as `GameEvent.declared_attacker`.
"""

import re
from typing import TYPE_CHECKING

from . import ConditionReader

if TYPE_CHECKING:
    from . import ConditionContext


def _activated_ability_is_mana_ability(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it isn't a mana ability" on an activation trigger (Rings of
    Brighthearth, Harsh Mentor): "it" is the activated ability the event
    names, and CR 605.1a's test was made as it was activated. No activation
    event, nothing to ask about."""
    from ..triggers import ExtraTriggerEvent

    event = context.event
    if event is None or event.event is not ExtraTriggerEvent.ABILITY_ACTIVATED:
        return False
    return event.mana_ability == (match.group("negated") is None)


def _declared_as_an_attacker(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it isn't being declared as an attacker" (Verity Circle): whether the
    tap the trigger event reports was CR 508.1f's attack declaration."""
    from ..triggers import TriggerEvent

    event = context.event
    if event is None or event.event is not TriggerEvent.BECOMES_TAPPED:
        return False
    return event.declared_attacker == (match.group("negated") is None)


READERS: tuple[ConditionReader, ...] = (
    ConditionReader(
        re.compile(r"it (?:is(?P<negated>n't| not)) a mana ability|it is a mana ability"),
        _activated_ability_is_mana_ability,
    ),
    ConditionReader(
        re.compile(r"it (?:is(?P<negated>n't| not)|is) being declared as an attacker"),
        _declared_as_an_attacker,
    ),
)
