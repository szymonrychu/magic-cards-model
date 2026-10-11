"""EP-01 round 2, task T7: audit rules for the cost family of static lines.

`reads_cost_line` asks the PRODUCTION reader whether it performs the line (never a
regex of its own); see `static_audit/__init__.py`.
"""

import re

from magic_cards_model.machines.cost import static_free_cast_grant
from magic_cards_model.machines.vivid import (
    COSTS_LESS_PER_COLOR_AMONG_RE,
    parse_colors_among_qualifier,
)
from magic_cards_model.models.game._common import _SPEND_AS_ANY_COLOR_STATIC_RE
from magic_cards_model.models.mana import spend_only_from


def reads_cost_line(
    printing, text: str, *, card_name: str | None = None, legendary: bool = False
) -> bool:
    lowered = text.lower()
    if "spend only mana produced by" in lowered:
        # `ManaSpend.casting` limits the payment to that kind of source.
        return spend_only_from(text.strip()) is not None
    if "mana of any type" in lowered:
        # `Game.spends_mana_of_any_type_for_spell` reads this same sentence.
        return _SPEND_AS_ANY_COLOR_STATIC_RE.match(text.strip()) is not None
    if "without paying its mana cost" in lowered:
        return static_free_cast_grant(text) is not None
    if "color among" in lowered:
        match = COSTS_LESS_PER_COLOR_AMONG_RE.search(
            re.sub(r"^vivid\s+\S\s*", "", text, flags=re.I)
        )
        return (
            match is not None and parse_colors_among_qualifier(match.group("qualifier")) is not None
        )
    return False
