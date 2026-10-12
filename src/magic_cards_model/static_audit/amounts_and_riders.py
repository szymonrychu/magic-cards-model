"""Static lines of the EP-01 R3 T8 cards (variable amounts and riders).

A line is credited only when the PRODUCTION reader performs it:

- "Enchanted player can't gain life." - `Game.life_gain_prohibited` reads it
  off the battlefield (CR 119.7, CR 303.4m); `is_player_rules_static_line` is
  that reader's own recogniser.
"""

from magic_cards_model.models.game._damage_life import is_player_rules_static_line


def reads_amounts_and_riders_line(printing, text, *, card_name=None, legendary=False) -> bool:
    lowered = text.lower()
    if "can't gain life" in lowered:
        return is_player_rules_static_line(text)
    return False
