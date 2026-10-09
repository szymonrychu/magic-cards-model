"""Audit of the attack/block restriction statics (EP-01 R1 T4: CR 508.1c,
509.1b, 508.1d, 508.1h): a line is credited only when the production reader
of its family performs it."""

from ..machines.attached_restrictions import reads_attached_restriction_line
from ..machines.attack_block_costs import reads_attack_block_cost_line
from ..machines.attacking_statics import reads_self_condition_line
from ..machines.combat_statics import reads_block_evasion_line
from ..machines.group_attack_statics import reads_group_attack_line

_FAMILIES = (
    reads_self_condition_line,
    reads_block_evasion_line,
    reads_attached_restriction_line,
    reads_group_attack_line,
    reads_attack_block_cost_line,
)


def reads_static_line(printing, text, *, card_name, legendary) -> bool:
    lowered = text.lower()
    if "attack" not in lowered and "block" not in lowered:
        return False
    return any(family(printing, text, card_name=card_name) for family in _FAMILIES)
