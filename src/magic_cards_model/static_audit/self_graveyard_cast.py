"""Audit of "You may cast this card from your graveyard[ if ...]. If you do, it
enters with <counters>" lines (CR 601.3, CR 604.6, CR 614.1c).

Credited only when the PRODUCTION option builder, `keyword_cast_options`, really
yields a graveyard cast option for the card carrying those counters, and the
shared condition registry reads the printed condition (an unread condition would
refuse the option at every cast, never silently allow it).
"""

from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.machines.casting.permissions import (
    CAST_PERMISSION,
    reads_printed_self_zone_cast_with_counters_line,
)
from magic_cards_model.models.zone import Zone
from magic_cards_model.static_audit.enters_counters import _stage


def reads_static_line(
    printing, text: str, *, card_name: str | None = None, legendary: bool = False
) -> bool:
    if not reads_printed_self_zone_cast_with_counters_line(text):
        return False
    options = [
        option
        for option in keyword_cast_options(printing)
        if option.keyword == CAST_PERMISSION
        and option.zone is Zone.GRAVEYARD
        and option.enters_with_counters
        and option.understood
    ]
    if not options:
        return False
    for option in options:
        if option.condition is None:
            continue
        game, state = _stage(printing, rich=True, record=None)
        if game.condition_holds("sweep_you", option.condition, state) is None:
            return False
    return True
