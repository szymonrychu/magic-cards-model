"""Keyword abilities written out as the triggered abilities their rules say.

CR 702.1: a keyword is shorthand for one or more abilities. These are the
combat and death-trigger keywords of the older sets plus a few newer ones:

- afterlife (CR 702.135a): "When this permanent is put into a graveyard from
  the battlefield, create N 1/1 white and black Spirit creature tokens with
  flying."
- mentor (CR 702.134a): "Whenever this creature attacks, put a +1/+1 counter
  on target attacking creature with power less than this creature's power."

`machines/keywords._TRIGGER_EXPANSIONS` registers `LEGACY_EXPANSIONS`, so the
trigger matcher and the effect parser see them like any printed trigger.
"""

from collections.abc import Callable

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


#: The keyword (Scryfall spelling, lowercase) and the one ability it expands to.
LEGACY_EXPANSIONS: dict[str, Callable[[KeywordAbility], list[TriggeredAbility]]] = {
    "afterlife": lambda ability: [_afterlife_ability(ability)],
    "mentor": lambda ability: [_mentor_ability(ability)],
}
