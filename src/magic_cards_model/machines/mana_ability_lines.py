"""Whether one computed ability line is a mana ability (CR 605.1a, CR 605.1b)."""

from functools import cache

from .abilities import (
    ActivatedAbility,
    TriggeredAbility,
    _is_activated_mana_ability,
    _is_triggered_mana_ability,
    parse_granted_ability_lines,
)


@cache
def line_is_mana_ability(line: str) -> bool:
    """CR 605.1a's criteria for an activated line, CR 605.1b's for a triggered
    one, read the way `parse_granted_ability_lines` reads any computed line."""
    # A basic land type's intrinsic ability (CR 305.6) is printed as reminder
    # text, "({T}: Add {G}.)".
    bare = line.strip()
    if bare.startswith("(") and bare.endswith(")"):
        bare = bare[1:-1]
    for ability in parse_granted_ability_lines([bare]):
        if isinstance(ability, ActivatedAbility) and _is_activated_mana_ability(ability):
            return True
        if isinstance(ability, TriggeredAbility) and _is_triggered_mana_ability(ability):
            return True
    return False
