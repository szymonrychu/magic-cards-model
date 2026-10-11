"""EP-01 round 2, task T7: variable static pumps, characteristic-defining
abilities, static cast/play permissions, cost modification and mana-spending
statics, static replacement and enters leftovers (CR 604.3, 613.4a, 601.3,
601.2f, 614.1, 614.12).

One private module per sub-family (`_t7_*`), each asking the production reader
that performs the line; this module only fans the call out. The pump, d20,
replacement and zone-grant lines are credited by their production readers
directly (`support.py` asks `reads_spell_keyword_grant_line`,
`reads_granted_zone_keyword_line` and the effect/replacement parsers), so they
need no audit module.
"""

from magic_cards_model.static_audit import (
    _t7_casting,
    _t7_cda,
    _t7_cost,
)

_READERS = (_t7_cda.reads_cda_line, _t7_casting.reads_casting_line, _t7_cost.reads_cost_line)


def reads_pumps_cda_cost_replacement_line(
    printing, text: str, *, card_name: str | None = None, legendary: bool = False
) -> bool:
    return any(
        reader(printing, text, card_name=card_name, legendary=legendary) for reader in _READERS
    )
