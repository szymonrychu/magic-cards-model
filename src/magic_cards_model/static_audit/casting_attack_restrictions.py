"""Audit of the casting and activation prohibitions (EP-01 R2 T4: CR 601.3,
CR 101.2, CR 602.5, CR 305.1, CR 508.1c, CR 509.1b): a line is credited only
when the production reader of its family performs it - `static_cast_bans`
(the "can't cast / play / activate / attack" grammar), the spell's own
"cast this spell only if" gate, or `casting_restrictions`' cast windows."""

from ..machines.casting_restrictions import reads_player_rule_static_line
from ..machines.static_cast_bans import reads_self_cast_restriction_line, reads_static_ban_line
from ..models.card import Supertype


def reads_casting_attack_restrictions_line(printing, text, *, card_name, legendary) -> bool:
    lowered = text.lower()
    if "cast" not in lowered and "play lands" not in lowered and "activate" not in lowered:
        return False
    name = card_name or printing.name
    # "Threshold - You can't cast this spell unless ...": an ability word is a label only
    body = text.split(" — ", 1)[1] if " — " in text else text
    is_legendary = legendary or Supertype.LEGENDARY in printing.supertypes
    return (
        reads_static_ban_line(printing, body, card_name=name)
        or reads_self_cast_restriction_line(body, card_name=name, legendary=is_legendary)
        or reads_player_rule_static_line(body)
    )
