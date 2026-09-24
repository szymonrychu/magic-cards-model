"""Copy effects read off oracle text (CR 707): an object becoming a copy of
another, token copies, and copies of spells and abilities on the stack.

Entry points `copy_ability_effect`/`copy_spell_effect` are tried by
`machines/effects.py` ahead of its clause split, because every shape here is
an instruction chain whose later sentences refer back to the first ("copy
that spell. You may choose new targets for the copy.").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .effects import AbilityEffect, Effect


def copy_ability_effect(effect_text: str) -> AbilityEffect | None:
    """A copy instruction on an activated or triggered ability, or `None`."""
    return None


def copy_spell_effect(effect_text: str) -> Effect | None:
    """A copy instruction on a resolving spell, or `None`."""
    return None
