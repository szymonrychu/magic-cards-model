"""Audit of the alternative-cast, face-down and zone keyword statics of
EP-01 round 3 (T4): the face-down group's quoted grant (CR 708.2, CR
613.1f), the mutate graveyard permission (CR 702.140a, CR 601.3) and the
library-top plot grant (CR 702.170f).

Each line is credited only when the PRODUCTION reader that performs it
reads it - never a re-derived regex.
"""

from functools import cache

_FACE_DOWN = "face-down creatures"
_MUTATE = "using its mutate ability"
_PLOT = "plot"


@cache
def _granted_ability_is_performed(granted: str) -> bool:
    """Whether a quoted granted line is an activated ability whose effect a
    production dispatcher performs (not a notice)."""
    from magic_cards_model.machines.abilities import parse_granted_ability_lines
    from magic_cards_model.machines.effects.dispatch import _ability_effect_or_notice
    from magic_cards_model.machines.effects.tokens import _is_notice_only

    abilities = parse_granted_ability_lines([granted])
    if len(abilities) != 1:
        return False
    effect_text = getattr(abilities[0], "effect", None)
    if not effect_text:
        return False
    effect = _ability_effect_or_notice(effect_text)
    return effect is not None and not _is_notice_only(effect)


def reads_alt_cast_keywords_line(
    printing, text: str, *, card_name: str | None = None, legendary: bool = False
) -> bool:
    lowered = text.lower()
    if _FACE_DOWN in lowered:
        from magic_cards_model.machines.face_down_keywords import FACE_DOWN_GROUP_QUOTED_GRANT_RE

        match = FACE_DOWN_GROUP_QUOTED_GRANT_RE.fullmatch(text.strip())
        if match is not None and _granted_ability_is_performed(match["ability"].strip()):
            return True
    if _MUTATE in lowered:
        from magic_cards_model.machines.face_down_keywords import mutate_cast_zones

        if mutate_cast_zones(printing) - {"hand"}:
            return True
    if _PLOT in lowered:
        from magic_cards_model.machines.face_down_keywords import reads_library_plot_grant_line

        if reads_library_plot_grant_line(text):
            return True
    return False
