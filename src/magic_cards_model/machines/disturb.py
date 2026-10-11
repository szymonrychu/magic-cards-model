"""Disturb (CR 702.146): cast a double-faced card transformed from your graveyard.

CR 702.146a: "Disturb is an ability found on the front face of some
double-faced cards (see rule 712, "Double-Faced Cards"). "Disturb [cost]"
means "You may cast this card transformed from your graveyard by paying
[cost] rather than its mana cost." See rule 712.8c."
CR 702.146b: "A resolving double-faced spell that was cast using its disturb
ability enters the battlefield with its back face up."

The keyword is three pieces, and each lives where the rules put it:

- **the permission** (CR 601.3) and **the alternative cost** (CR 118.9) are
  this module's `disturb_cast_option`, a graveyard `KeywordCastOption` that
  `keyword_cast_options` offers - so `legal_actions`, `Game.alternative_
  costs_for` and `Casting.use_keyword` all see it with no disturb-specific
  code of their own;
- **the face**: the option carries `casts_transformed`, which
  `Casting.use_keyword` turns into `Casting.cast_transformed` (CR 712.11a:
  "put on the stack with its back face up"; CR 712.8c: only the back face's
  characteristics, the front face's mana value). The resolving spell keeps
  `CardState.transformed`, so it enters back face up (CR 702.146b) through
  the same path every transformed spell already takes;
- **the exile** is not part of the keyword at all: every disturb back face
  prints its own "If <this> would be put into a graveyard from anywhere,
  exile it instead." - a self-replacement the replacement machinery already
  reads off the moved object's current face in every zone
  (`CardReplacement.anywhere`, CR 614.1a), on the stack and on the
  battlefield alike.

CR 712.11d keeps the front face's disturb ability in view while the back
face is evaluated for castability, which is exactly what a printed option
read off the card (not off the face) does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.zone import Zone

if TYPE_CHECKING:
    from .abilities import KeywordAbility
    from .casting.options import KeywordCastOption

DISTURB = "Disturb"


def disturb_cast_option(ability: KeywordAbility) -> KeywordCastOption:
    """The graveyard cast "Disturb [cost]" hands out (CR 702.146a): the
    printed cost rather than the mana cost, cast transformed. A cost this
    engine cannot read is offered as not understood, so the cast is refused
    in the engine's words rather than silently waved through."""
    from .casting.options import KeywordCastOption
    from .cost import total_cost_for_phrase

    cost = total_cost_for_phrase(ability.cost) if ability.cost else None
    return KeywordCastOption(
        keyword=DISTURB,
        rule="CR 702.146a",
        zone=Zone.GRAVEYARD,
        cost=cost,
        pays_mana_cost=False,
        casts_transformed=True,
        owner_only=True,
        understood=cost is not None,
    )
