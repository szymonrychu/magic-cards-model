"""EP-01 round 1, task T7: the cost-modification family of static lines
(CR 601.2f, 118.7, 118.8, 118.9).

Every predicate here asks the production reader that performs the line at a
real cast - never a regex of its own (see `static_audit/__init__.py`).
"""

from functools import cache

from magic_cards_model.machines.casting.options import (
    reads_mandatory_additional_cost_line,
    reads_optional_additional_cost_line,
    reads_or_pay_additional_cost_line,
    reads_printed_alternative_cost_line,
)

#: Cheap lowercase gate: every shape this module can credit carries one of these.
_GATES = (
    "less to cast",
    "more to cast",
    "less to activate",
    "more to activate",
    "additional cost",
    "rather than pay",
    "spend mana as though",
)


@cache
def _reads(text: str) -> bool:
    return (
        reads_mandatory_additional_cost_line(text)
        or reads_optional_additional_cost_line(text)
        or reads_or_pay_additional_cost_line(text)
        or reads_printed_alternative_cost_line(text)
    )


def reads_static_line(printing, text, *, card_name=None, legendary=False) -> bool:
    lowered = text.lower()
    if not any(gate in lowered for gate in _GATES):
        return False
    return _reads(text)
