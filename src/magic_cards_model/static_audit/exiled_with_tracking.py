"""Standing "cards exiled with this" statics (EP-01 R3, T6).

A line is credited only when the production reader performs it:
`machines/exiled_with_peek.reads_look_at_exiled_with_line`, the very predicate
`Game.known_to` evaluates for the permission (CR 406.3, CR 607.2a).
"""

from magic_cards_model.machines.exiled_with_peek import reads_look_at_exiled_with_line


def reads_exiled_with_tracking_line(printing, text, *, card_name=None, legendary=False) -> bool:
    return reads_look_at_exiled_with_line(card_name or printing.name, text, legendary)
