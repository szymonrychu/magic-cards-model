"""Source damage to a target and to a group defined off that target.

"`<src>` deals N damage to target creature and each other creature
`<that shares a color with it | with the same name as that creature>`."
(Wojek Embermage, Izzet Staticaster.) One target (CR 115.1); the rest of the
group is not targeted but read off it by CR 400.7 back-reference as the
ability resolves - a shared color (CR 105.2c: a colorless object has no
color, so it shares none) or a shared name. CR 608.2b: with the one target
illegal the ability doesn't resolve, so the group is not damaged either.

The other back-reference shapes this module once read have one reader each
in `machines/effects.py`: "and M damage to that creature's controller"
(`_DAMAGE_TARGET_ALSO_DAMAGES_CONTROLLER_RE`), "That creature deals damage
equal to its power to this creature" (`_RIDER_DEALS_DAMAGE_EQUAL_TO_ITS_
POWER_RE`), and an elided or back-referring "... instead" alternative
(`_parse_condition_instead_clause_for_ability`).

Rules looked up with `mise run rules:find` in the session that wrote this:
CR 105.2c, CR 608.2b.
"""

import re
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import COUNT, parse_count

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers import AbilityOnStack

_DAMAGE_TARGET_AND_EACH_OTHER_RE = re.compile(
    rf"^(?P<subject>[^.]+?) deals (?P<n>{COUNT}) damage to target creature and each other "
    r"creature (?:(?P<color>that shares a colou?r with it)"
    r"|(?P<name>with the same name as that creature))\.?$",
    re.IGNORECASE,
)


def _parse_damage_target_and_each_other(text: str) -> Any:
    match = _DAMAGE_TARGET_AND_EACH_OTHER_RE.fullmatch(text)
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    by_color = match.group("color") is not None

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        source = ability.source_or_last_known(game)
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        board = game.computed_board()
        wanted = board.of(target)
        group = [target]
        for other in game.battlefield:
            if other is target:
                continue
            chars = board.of(other)
            if not chars.is_creature:
                continue
            if by_color:
                shares = bool(set(chars.colors) & set(wanted.colors))  # CR 105.2c
            else:
                shares = bool(wanted.name) and chars.name == wanted.name
            if shares:
                group.append(other)
        for creature in group:
            game.deal_damage(creature, amount, source=source)

    return effect


def damage_backref_ability_effect(effect_text: str) -> Any:
    """The shape above, if `effect_text` reads as it, or None."""
    from .effects import _strip_non_effect_preamble

    text = " ".join(_strip_non_effect_preamble(effect_text).split())
    return _parse_damage_target_and_each_other(text)
