"""Activation-cost mana conditions: what mana paid an activated ability's own
cost (CR 601.2h, imported for activation by CR 602.2b: "The remainder of the
process for activating an ability is identical to the process for casting a
spell listed in rules 601.2b-i ... An activated ability's analog to a spell's
mana cost ... is its activation cost"), read off the resolving
`AbilityOnStack` itself rather than off a `CastRecord` - an ability was never
cast (CR 601.2a), so it has no `CastRecord` at all; `cast_record.py`'s own
family of "spent to cast" readers answers a spell's version of the identical
question.

Each reader here is a `ConditionReader`, registered through `READERS`; see
`machines/conditions/__init__.py` for the contract every reader keeps.

Reached only when the caller threads the *resolving* `AbilityOnStack` through
`Game.condition_holds`'s own `ability=` parameter - `machines/effects.
layer_or_counter_instead` (CR 614.1a's "if `<condition>`, ... instead" swap)
does, for Paragon of Modernity's and Jetmir's Fixer's own upgrade sentences.
Every other `condition_holds` caller passes an ability *definition*
(`TriggeredAbility`/`ActivatedAbility`) there instead, or nothing at all,
neither of which was itself activated and so carries no mana-spent record -
`_stack_ability` answers `None` for those rather than raising, and every
reader here answers False on a `None`, the same "unreadable is not true"
default `read_condition`'s own contract asks for a clause that IS claimed.

Rules verified with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 602.2b** - activating an ability pays its cost exactly the way
  casting a spell pays a mana cost (CR 601.2h).
- **CR 601.2h** - "the mana spent" is whatever actually paid the total cost.
- **CR 105.1** - the five colors; **CR 105.2c** - colorless is not one of them.
- **CR 106.3** - the source of mana is the source of the ability that
  produced it, which is what makes a Treasure's own sacrifice ability "mana
  from a Treasure" regardless of which color it added.
"""

import re
from typing import TYPE_CHECKING

from ...models.card import Color
from . import ConditionReader
from .objects import QUANTITY, quantity_test

if TYPE_CHECKING:
    from ..triggers import AbilityOnStack
    from . import ConditionContext


def _stack_ability(context: "ConditionContext") -> "AbilityOnStack | None":
    """The resolving `AbilityOnStack` `context.ability` names, or `None` when
    this condition is asked with anything else in that slot - an ability
    *definition*, or nothing (`ConditionContext.ability`'s default)."""
    from ..triggers import AbilityOnStack

    ability = context.ability
    return ability if isinstance(ability, AbilityOnStack) else None


def _colors_of_mana_spent_to_activate(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "`<quantity>` colors of mana were spent to activate this ability" -
    Paragon of Modernity's own "exactly three". CR 105.1's five colors,
    counted distinct among what actually paid the activation (CR 601.2h via
    CR 602.2b); CR 105.2c excludes colorless. `quantity_test` (the same
    reader every "N or more"/"at least N"/"exactly N" clause in `objects.py`
    goes through) makes this a template over the whole family, not just the
    one printed word "exactly"."""
    test = quantity_test(match.group("amount"))
    stack_ability = _stack_ability(context)
    if test is None or stack_ability is None:
        return False
    spent_colors = sum(
        1
        for color, amount in stack_ability.mana_spent.items()
        if color is not Color.COLORLESS and amount > 0
    )
    return test(spent_colors)


def _treasure_mana_spent_to_activate(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "mana from a Treasure was spent to activate this ability" /
    "... wasn't spent ..." (CR 106.3) - Jetmir's Fixer's own upgrade."""
    stack_ability = _stack_ability(context)
    held = stack_ability is not None and stack_ability.treasure_mana_spent > 0
    negated = match.group("verb").strip().lower() != "was"
    return held != negated


READERS: tuple[ConditionReader, ...] = (
    ConditionReader(
        re.compile(
            rf"(?P<amount>{QUANTITY}) colors? of mana (?:were|was) spent to activate "
            r"(?:this ability|that ability|it)"
        ),
        _colors_of_mana_spent_to_activate,
    ),
    ConditionReader(
        re.compile(
            r"mana from an? treasure (?P<verb>wasn'?t|was not|was) spent to activate "
            r"(?:this ability|that ability|it)"
        ),
        _treasure_mana_spent_to_activate,
    ),
)
