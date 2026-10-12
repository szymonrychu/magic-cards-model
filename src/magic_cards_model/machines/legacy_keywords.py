"""Keyword abilities written out as the triggered abilities their rules say.

CR 702.1: a keyword is shorthand for one or more abilities. These are the
combat and death-trigger keywords of the older sets plus a few newer ones:

- afterlife (CR 702.135a): "When this permanent is put into a graveyard from
  the battlefield, create N 1/1 white and black Spirit creature tokens with
  flying."
- graft (CR 702.58a): enters with N +1/+1 counters, and moves one onto each
  creature that enters afterwards.
- backup (CR 702.165a): "When this creature enters, put N +1/+1 counters on
  target creature. If that's another creature, it also gains the non-backup
  abilities of this creature printed below this one until end of turn."
- mentor (CR 702.134a): "Whenever this creature attacks, put a +1/+1 counter
  on target attacking creature with power less than this creature's power."

`machines/keywords._TRIGGER_EXPANSIONS` registers `LEGACY_EXPANSIONS`, so the
trigger matcher and the effect parser see them like any printed trigger.
"""

import re
from collections.abc import Callable
from functools import cache

from .abilities import KeywordAbility, TriggeredAbility, TriggerEvent, TriggerWord

_WORDS = {1: "a", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def _count(ability: KeywordAbility) -> int:
    return ability.count if ability.count is not None else 1


def _afterlife_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.135a / CR 702.135b (each instance triggers separately)."""
    from .keywords import _expansion

    count = _count(ability)
    noun = "token" if count == 1 else "tokens"
    quantity = _WORDS.get(count, str(count))
    return _expansion(
        ability,
        keyword="afterlife",
        word=TriggerWord.WHEN,
        condition="this permanent is put into a graveyard from the battlefield",
        effect=f"create {quantity} 1/1 white and black Spirit creature {noun} with flying",
        event=TriggerEvent.DIES,
    )


def _mentor_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.134a / CR 702.134b (each instance triggers separately)."""
    from .keywords import _expansion

    return _expansion(
        ability,
        keyword="mentor",
        word=TriggerWord.WHENEVER,
        condition="this creature attacks",
        effect=(
            "put a +1/+1 counter on target attacking creature with power less than "
            "this creature's power"
        ),
        event=TriggerEvent.ATTACKS,
    )


def _graft_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.58a's second half: "Whenever another creature enters, if this
    permanent has a +1/+1 counter on it, you may move a +1/+1 counter from this
    permanent onto that creature." (The static half - enters with N counters -
    is `machines/replacement/enters._modular_entering_counters`.) CR 702.58b:
    each instance works separately."""
    from .keywords import _expansion

    return _expansion(
        ability,
        keyword="graft",
        word=TriggerWord.WHENEVER,
        condition="another creature enters",
        intervening_if="this permanent has a +1/+1 counter on it",
        effect="you may move a +1/+1 counter from this permanent onto that creature",
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
    )


BACKUP_GRANT_CLAUSE = (
    "If that's another creature, it also gains the non-backup abilities of this creature "
    "printed below this one until end of turn"
)


def _backup_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.165a. The abilities it grants are the printed lines below the
    backup line (`backup_granted_lines`), read when the ability resolves."""
    from .keywords import _expansion

    count = _count(ability)
    noun = "counter" if count == 1 else "counters"
    return _expansion(
        ability,
        keyword="backup",
        word=TriggerWord.WHEN,
        condition="this creature enters",
        effect=(
            f"put {_WORDS.get(count, str(count))} +1/+1 {noun} on target creature. "
            f"{BACKUP_GRANT_CLAUSE}"
        ),
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
    )


_REMINDER_RE = re.compile(r"\s*\([^)]*\)")


@cache
def backup_granted_lines(oracle_text: str) -> tuple[str, ...]:
    """The abilities printed below the backup line of `oracle_text` (CR 702.165a),
    one entry per printed line with its reminder text removed. Abilities printed
    above the backup line are never granted (CR 702.165a)."""
    lines = oracle_text.split("\n")
    for index, line in enumerate(lines):
        if line.lower().startswith("backup"):
            below = (_REMINDER_RE.sub("", rest).strip() for rest in lines[index + 1 :])
            return tuple(rest for rest in below if rest)
    return ()


#: The keyword (Scryfall spelling, lowercase) and the one ability it expands to.
LEGACY_EXPANSIONS: dict[str, Callable[[KeywordAbility], list[TriggeredAbility]]] = {
    "afterlife": lambda ability: [_afterlife_ability(ability)],
    "mentor": lambda ability: [_mentor_ability(ability)],
    "graft": lambda ability: [_graft_ability(ability)],
    "backup": lambda ability: [_backup_ability(ability)],
}
