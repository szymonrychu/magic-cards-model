"""EP-01 round 2, task T7: audit rules for the casting family of static lines.

`reads_casting_line` asks the PRODUCTION reader whether it performs the line (never a
regex of its own); see `static_audit/__init__.py`.
"""

from magic_cards_model.models.game import Game
from magic_cards_model.models.game._casting import each_player_additional_land_plays_of_line


def reads_casting_line(
    printing, text: str, *, card_name: str | None = None, legendary: bool = False
) -> bool:
    # `Game.land_allowance` counts this line for every player (CR 305.2, 611.3d).
    if each_player_additional_land_plays_of_line(text) is not None:
        return True
    # `Game.known_to` shows the opposing face-down creatures to its controller.
    return Game._LOOK_AT_TOP_AND_FACE_DOWN_ANY_TIME_RE.fullmatch(text.strip()) is not None
