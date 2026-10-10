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

import re

from ..machines.abilities import _strip_reminder
from ..machines.layers.parse import _parse_layer_sentence
from ..machines.replacement import (
    ReplacementKind,
    _classify_choice,
    _compile_opponents_permanents_enter_tapped,
    parse_replacement_effects,
)
from ..machines.replacement.enters_choices import enters_choice_apply, reads_attach_follow_up

_SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
#: Alhammarret, High Arbiter's second sentence is part of the one reveal-then-name
#: choice `enters_choice_apply` performs (it reads the whole raw line).
_NAME_FROM_REVEALED_RE = re.compile(
    r"^you choose the name of a nonland card revealed this way\.?$", re.IGNORECASE
)


def _effects_of_line(printing, text):
    wanted = _strip_reminder(text)[0].strip()
    return [
        effect
        for effect in parse_replacement_effects(printing)
        if _strip_reminder(effect.raw)[0].strip() == wanted
    ]


def reads_enters_choices_line(printing, text, *, card_name=None, legendary=False) -> bool:
    lowered = text.lower()
    if "enter" not in lowered:
        return False
    effects = _effects_of_line(printing, text)
    if not effects:
        return False
    if not all(_performed(effect) for effect in effects):
        return False
    # Later sentences of the same line ("If the coin comes up heads, ...", "If
    # you do, it enters attached ...") must each be read too: by a layer rung
    # that applies the recorded answer, or as the second half of the choice.
    sentences = _SENTENCE_BREAK_RE.split(_strip_reminder(text)[0].strip())
    return all(_follow_up_read(sentence) for sentence in sentences[1:])


def _follow_up_read(sentence: str) -> bool:
    return (
        reads_attach_follow_up(sentence)
        or _NAME_FROM_REVEALED_RE.match(sentence) is not None
        or _parse_layer_sentence(sentence) is not None
    )


def _performed(effect) -> bool:
    if effect.kind is ReplacementKind.ENTERS_TAPPED and not effect.self_replacement:
        return _compile_opponents_permanents_enter_tapped(effect) is not None
    if (
        effect.kind in (ReplacementKind.AS_ENTERS, ReplacementKind.AS_TURNED_FACE_UP)
        and effect.self_replacement
    ):
        # The production chooser exists for this exact sentence (the same
        # builders `_self_enters_modifiers` registers as it gathers).
        return (
            enters_choice_apply(effect, effect.subject or "") is not None
            or _classify_choice(effect.replacement or "") is not None
        )
    return False
