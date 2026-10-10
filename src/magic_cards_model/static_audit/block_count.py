"""Block-count, block-only, lure and exact-blockers static lines (EP-01 R1, T3).

A line is credited only when the engine's own readers read every sentence of
it with a subject they resolve:

- `machines/block_statics.py`'s parsers - the ones `block_refusal`,
  `declaration_refusal` and `declare_blockers` enforce through (CR 509.1a,
  509.1b, 509.1c);
- for a one-shot mode ("\u2022 Glorfindel must be blocked this turn if able."),
  the effect parser that grants the requirement when the mode resolves
  (`effects.continuous._parse_block_requirement_grant_clause`, CR 509.1c,
  CR 611.2a) - asked on the line self-normalised the way the dispatcher does.
"""

from magic_cards_model.machines.abilities import self_normalized_effect_text
from magic_cards_model.machines.block_statics import reads_block_static_line


def reads_static_line(printing, text, *, card_name=None, legendary=False) -> bool:
    lowered = text.lower()
    if "block" not in lowered:
        return False
    name = card_name or printing.name
    line = text.lstrip("\u2022* ").strip()
    if "must be blocked this turn" in lowered:
        from magic_cards_model.machines.effects.continuous import (
            _parse_block_requirement_grant_clause,
        )

        normalized = self_normalized_effect_text(name, line, legendary=legendary)
        return _parse_block_requirement_grant_clause(normalized) is not None
    return reads_block_static_line(line, name)
