"""EP-01 round 2, task T7: audit rules for the characteristic-defining and
deck-construction static lines.

Each predicate asks the PRODUCTION reader: `DeckLimits.copies_allowed` for
"A deck can have any number of cards named ~" (CR 100.2a), and
`additional_mana_ability_life` for the extra life cost on mana abilities
(CR 118.8).
"""

from magic_cards_model.models.card import has_changeling
from magic_cards_model.models.deck import DeckLimits
from magic_cards_model.models.game._costs_mana import additional_mana_ability_life


def reads_line(
    printing, text: str, *, card_name: str | None = None, legendary: bool = False
) -> bool:
    lowered = text.lower()
    if "a deck can have" in lowered:
        limits = DeckLimits.constructed()
        return limits.copies_allowed(printing) != limits.max_copies
    if "is every creature type" in lowered:
        return has_changeling(text)
    if "cost an additional" in lowered:
        return additional_mana_ability_life(text) > 0
    return False
