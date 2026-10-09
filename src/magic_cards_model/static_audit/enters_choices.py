"""Audit of the EP-01 R1 T2 families: "enters tapped" statics and "as [this]
enters" choices (CR 614.12, CR 614.1d, CR 614.12a).

A line is credited only when the PRODUCTION reader performs it: a group
"<objects> enter tapped" static must compile into the replacement effect the
engine registers (`_compile_opponents_permanents_enter_tapped`), and an "as
[this] enters, choose ..." sentence must be one the production chooser builders
(`enters_choice_apply`, `_classify_choice`) return a performer for - the same
builders `_self_enters_modifiers` registers as the permanent enters. Conditional
self "enters tapped unless ..." lines are credited by the existing
`_self_enters_line_category` once `_enters_tapped_condition` reads them.
"""

from ..machines.abilities import _strip_reminder
from ..machines.replacement import (
    ReplacementKind,
    _classify_choice,
    _compile_opponents_permanents_enter_tapped,
    parse_replacement_effects,
)
from ..machines.replacement.enters_choices import enters_choice_apply


def _effects_of_line(printing, text):
    return [
        effect
        for effect in parse_replacement_effects(printing)
        if _strip_reminder(effect.raw)[0] == text.strip()
    ]


def reads_static_line(printing, text, *, card_name=None, legendary=False) -> bool:
    lowered = text.lower()
    if "enter" not in lowered:
        return False
    effects = _effects_of_line(printing, text)
    if not effects:
        return False
    return all(_performed(effect) for effect in effects)


def _performed(effect) -> bool:
    if effect.kind is ReplacementKind.ENTERS_TAPPED and not effect.self_replacement:
        return _compile_opponents_permanents_enter_tapped(effect) is not None
    if effect.kind is ReplacementKind.AS_ENTERS and effect.self_replacement:
        # The production chooser exists for this exact sentence (the same
        # builders `_self_enters_modifiers` registers as it gathers).
        return (
            enters_choice_apply(effect, effect.subject or "") is not None
            or _classify_choice(effect.replacement or "") is not None
        )
    return False
