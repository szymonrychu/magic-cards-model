"""EP-01 round 2, task T3: conditional static lines (CR 611.3, 604.2, 613.1f):
"As long as `<condition>`, ...", "During your turn, ...", an ability word in
front of either (CR 207.2c), "This spell has `<keyword>` as long as ...".

Every predicate asks the production reader that performs the line - the layer
reader `machines/layers/conditional_statics` for a characteristic change, and
the machine that owns the rule for the lines that change no characteristic
(equip timing, exhaust, the untap step, extra triggers, alternative costs, spell
keywords, cast permissions). Never a regex of its own (see
`static_audit/__init__.py`).
"""

import re
from functools import cache

from magic_cards_model.machines.abilities import self_normalized_effect_text
from magic_cards_model.machines.casting.options import conditional_alternative_cost_offers
from magic_cards_model.machines.casting.permissions import (
    conditional_flash_condition,
    reads_granted_zone_keyword_line,
)
from magic_cards_model.machines.keywords import (
    is_exhaust_reactivation_line,
    is_instant_speed_equip_line,
)
from magic_cards_model.machines.layers.conditional_statics import reads_conditional_static
from magic_cards_model.machines.spell_grants import spell_keyword_grant
from magic_cards_model.machines.triggers.collect import is_additional_trigger_line
from magic_cards_model.machines.untap_choices import is_untap_choice_line

#: Cheap lowercase gate: every shape this module can credit carries one of these.
_GATES = ("as long as", "during your ", "this spell has", "have retrace", "has retrace")

_ABILITY_WORD_RE = re.compile(r"^[A-Za-z' ]{2,30} — ")
_REMINDER_RE = re.compile(r"\s*\([^()]*\)")


@cache
def _reads(raw: str, normalized: str) -> bool:
    stripped = _ABILITY_WORD_RE.sub("", _REMINDER_RE.sub("", raw)).strip()
    return (
        reads_conditional_static(normalized)
        or reads_conditional_static(stripped)
        or is_instant_speed_equip_line(stripped)
        or is_exhaust_reactivation_line(stripped)
        or is_untap_choice_line(stripped)
        or is_additional_trigger_line(stripped)
        or bool(conditional_alternative_cost_offers(stripped))
        or conditional_flash_condition(stripped) is not None
        or (grant := spell_keyword_grant(stripped)) is not None
        and grant.subject == "self_spell"
    )


def reads_conditional_statics_line(
    printing, text: str, *, card_name: str | None = None, legendary: bool = False
) -> bool:
    lowered = text.lower()
    if not any(gate in lowered for gate in _GATES):
        return False
    normalized = (
        self_normalized_effect_text(card_name, text, legendary=legendary) if card_name else text
    )
    if _reads(text, normalized):
        return True
    return reads_granted_zone_keyword_line(printing, text)
