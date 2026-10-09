"""Audit of the EP-01 R1 T2 families: "enters tapped" statics and "as [this]
enters" choices (CR 614.12, CR 614.1d, CR 614.12a).

A line is credited only when the PRODUCTION reader performs it: a group
"<objects> enter tapped" static must compile into the replacement effect the
engine registers (`_compile_opponents_permanents_enter_tapped`) and that
effect must fire on a matching entering object of a throwaway real board.
"""

from ..machines.abilities import _strip_reminder
from ..machines.replacement import (
    ReplacementKind,
    _compile_opponents_permanents_enter_tapped,
    parse_replacement_effects,
)


def _effects_of_line(printing, text):
    return [
        effect
        for effect in parse_replacement_effects(printing)
        if _strip_reminder(effect.raw)[0] == text.strip()
    ]


def reads_static_line(printing, text, *, card_name=None, legendary=False) -> bool:
    lowered = text.lower()
    if " tapped" not in lowered and "as " not in lowered:
        return False
    effects = _effects_of_line(printing, text)
    if not effects:
        return False
    return all(_performed(effect) for effect in effects)


def _performed(effect) -> bool:
    if effect.kind is ReplacementKind.ENTERS_TAPPED and not effect.self_replacement:
        return _compile_opponents_permanents_enter_tapped(effect) is not None
    return False
