"""EP-02 R3 T2: counter amounts and the keywords that put counters on a creature.

Fabricate (CR 702.123a): "When this permanent enters, you may put N +1/+1
counters on it. If you don't, create N 1/1 colorless Servo artifact creature
tokens." Each instance triggers separately (CR 702.123b).
"""

from .abilities import KeywordAbility, TriggeredAbility, TriggerEvent, TriggerWord

_WORDS = {1: "a", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def fabricate_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.123a, written out as the triggered ability it stands for."""
    from .keywords import _expansion

    count = ability.count if ability.count is not None else 1
    quantity = _WORDS.get(count, str(count))
    counters = "counter" if count == 1 else "counters"
    servos = "Servo artifact creature token" if count == 1 else "Servo artifact creature tokens"
    return _expansion(
        ability,
        keyword="fabricate",
        word=TriggerWord.WHEN,
        condition="this permanent enters",
        effect=(
            f"you may put {quantity} +1/+1 {counters} on it. "
            f"If you don't, create {quantity} 1/1 colorless {servos}"
        ),
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
    )
