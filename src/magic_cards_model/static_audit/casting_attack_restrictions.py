"""Audit of the casting and activation prohibitions (EP-01 R2 T4: CR 601.3,
CR 101.2, CR 602.5, CR 305.1, CR 508.1c, CR 509.1b): a line is credited only
when the production reader of its family performs it - `static_cast_bans`
(the "can't cast / play / activate / attack" grammar), the spell's own
"cast this spell only if" gate, or `casting_restrictions`' cast windows."""

from ..machines.attached_restrictions import reads_attached_restriction_line
from ..machines.casting_restrictions import reads_player_rule_static_line
from ..machines.combat import (
    _self_reference_names,
    attacker_cap_pattern,
    reads_block_requirement_line,
)
from ..machines.effects.continuous import _SELF_AT_MOST_ONE_BLOCKER_THIS_TURN_RE
from ..machines.static_cast_bans import reads_self_cast_restriction_line, reads_static_ban_line
from ..models.card import Supertype


def reads_casting_attack_restrictions_line(printing, text, *, card_name, legendary) -> bool:
    lowered = text.lower()
    if "blocks each combat if able" in lowered and reads_block_requirement_line(text):
        return True
    name = card_name or printing.name
    if "no more than one creature can attack" in lowered and attacker_cap_pattern(
        name.split(",")[0].strip()
    ).search(text):
        # CR 508.1c: `combat.attacker_cap_restriction` refuses a second attacker.
        return True
    if "can't be blocked by more than one creature" in lowered:
        # A mode granting the restriction until end of turn (Glorfindel).
        generic = text
        for alias in sorted(_self_reference_names(name), key=len, reverse=True):
            generic = generic.replace(alias, "this creature")
        if _SELF_AT_MOST_ONE_BLOCKER_THIS_TURN_RE.fullmatch(generic.strip()):
            return True
    if "activated abilities can't be activated" in lowered and reads_attached_restriction_line(
        printing, text, card_name=card_name
    ):
        return True
    if "cast" not in lowered and "play lands" not in lowered and "activate" not in lowered:
        return False
    # "Threshold - You can't cast this spell unless ...": an ability word is a label only
    body = text.split(" — ", 1)[1] if " — " in text else text
    is_legendary = legendary or Supertype.LEGENDARY in printing.supertypes
    return (
        reads_static_ban_line(printing, body, card_name=name)
        or reads_self_cast_restriction_line(body, card_name=name, legendary=is_legendary)
        or reads_player_rule_static_line(body)
    )
