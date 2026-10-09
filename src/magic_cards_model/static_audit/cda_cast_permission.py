"""EP-01 round 1, task 8: the static cast/play permission lines.

Each reader asked here is the PRODUCTION one - the function that
`machines/casting` really consults at a cast - never a re-derived regex, so a
line is credited only when the engine performs it (CR 601.3, CR 611.3d).
"""

from magic_cards_model.machines.casting import (
    cast_condition_readable,
    conditional_free_cast_condition,
    reads_quality_flash_grant_line,
    reads_static_zone_cast_permission_line,
)


def reads_static_line(printing, text, *, card_name=None, legendary=False) -> bool:
    """Whether one static line of `printing` is a cast/play permission the
    casting machine reads whole."""
    if reads_static_zone_cast_permission_line(text) or reads_quality_flash_grant_line(text):
        return True
    free_condition = conditional_free_cast_condition(text)
    return free_condition is not None and cast_condition_readable(free_condition)
