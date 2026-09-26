"""Converge (an ability word - CR 207.2c, verified 2026-09-26 with
`mise run rules:find 207.2c`; "Ability words are similar to keywords in that
they tie together cards that have similar functionality, but they have no
special rules meaning and no individual entries in the Comprehensive
Rules."): "X is the number of colors of mana spent to cast this spell/creature/it."

Prismatic Ending's own converge clause (`machines/effects._parse_converge_
exile_by_colors_spent`) and CR 702.44b's Sunburst (`machines/replacement.
_sunburst_counter_amount`) each already read "distinct colors actually paid"
off `CastRecord.mana_spent` independently, keyed by an object's own
`Game.cast_record`/`cast_record_of`. This module is the one shared reader the
rest of the pool's converge cards - in an effect position (Arcane Omens,
Archaic's Agony, Snarl Song, Together as One), a target-legality position
(Sundering Archaic's ETB exile, via `machines/targeting.ComparisonCount`),
and an enters-with-counters position (Magmablood/Rancorous/Wildgrowth
Archaic's own "This creature enters with a +1/+1 counter on it for each
color of mana spent to cast it.", via `machines/effects.amount_expression`) -
all reuse instead of reimplementing.

Every printing of converge in the pool reads "the number of colors of mana
spent to cast `<this spell|this creature|it>`" - never a subset of colors, and
never scaled - so one function answers every position: `colors_of_mana_spent`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.card import Color

if TYPE_CHECKING:
    from ..models.game import Game, StackObject


def colors_of_mana_spent(game: Game, obj: StackObject | None) -> int:
    """CR 105.1's five colors, counted distinct among what was actually paid
    for `obj`'s own total cost (CR 601.2h), off `CastRecord.mana_spent`.

    `Color.COLORLESS` is excluded (CR 105.2c: "A colorless object has no
    color" - and colourless mana spent on generic or `{C}` is not one of CR
    105.1's five colors either). Zero when `obj` carries no cast record at
    all: it was never cast (a permanent put onto the battlefield some other
    way, or the synthetic throwaway permanent `support._self_enters_line_
    category` stages to judge whether an enters-with clause is read at all),
    or its record has already been forgotten (`Game.forget_cast_record`) -
    CR 107.1b's "zero is used instead" is the same answer a real game gives
    for a count that resolves to nothing.

    `game.cast_record_of` is keyed by `obj`'s current `zone_change_stamp`
    (CR 400.7), which `Game._carry_cast_record` re-keys onto the permanent a
    spell becomes as it resolves (CR 400.7a/400.7b) - so this reads correctly
    whether `obj` is still the spell on the stack (an effect position) or
    already the permanent it resolved into (an enters-with position).
    """
    record = game.cast_record_of(obj)
    if record is None:
        return 0
    return sum(
        1
        for color, amount in record.mana_spent.items()
        if color is not Color.COLORLESS and amount > 0
    )
