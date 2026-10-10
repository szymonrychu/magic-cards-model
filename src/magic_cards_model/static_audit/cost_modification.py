"""EP-01 round 1, task T7: the cost-modification family of static lines
(CR 601.2f, 118.7, 118.8, 118.9).

Every predicate here asks the production reader that performs the line at a
real cast - never a regex of its own (see `static_audit/__init__.py`).
"""

from functools import cache

from magic_cards_model.machines.abilities import self_normalized_effect_text
from magic_cards_model.machines.casting.options import (
    reads_mandatory_additional_cost_line,
    reads_optional_additional_cost_line,
    reads_or_pay_additional_cost_line,
    reads_printed_alternative_cost_line,
)
from magic_cards_model.machines.cost.abilities import ability_cost_modifier
from magic_cards_model.machines.cost.groups import group_spell_modifier
from magic_cards_model.machines.keywords import echo_alternative_cost, is_first_draw_reveal_line

#: Cheap lowercase gate: every shape this module can credit carries one of these.
_GATES = (
    "less to cast",
    "more to cast",
    "less to activate",
    "more to activate",
    "costs you pay cost",
    "cards from your hand costs",
    "equip ability costs",
    "additional cost",
    "rather than pay",
    "echo cost",
    "spend mana as though",
    "reveal the first card you draw",
)


@cache
def _reads(text: str) -> bool:
    return (
        group_spell_modifier(text) is not None
        or ability_cost_modifier(text) is not None
        or echo_alternative_cost(text) is not None
        or is_first_draw_reveal_line(text)
        or reads_mandatory_additional_cost_line(text)
        or reads_optional_additional_cost_line(text)
        or reads_or_pay_additional_cost_line(text)
        or reads_printed_alternative_cost_line(text)
    )


def reads_cost_modification_line(printing, text, *, card_name=None, legendary=False) -> bool:
    lowered = text.lower()
    if not any(gate in lowered for gate in _GATES):
        return False
    if card_name:
        text = self_normalized_effect_text(card_name, text, legendary=legendary)
    return _reads(text)
