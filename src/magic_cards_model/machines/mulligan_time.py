"""Actions a card allows "any time you could mulligan" (CR 103.5b).

    Any time you could mulligan and this card is in your hand, you may exile all
    the cards from your hand, then draw that many cards.          (Serum Powder)

CR 103.5b: the player may perform the action at a time they would declare
whether they will take a mulligan, in any round; if they perform it, they then
declare. `Game.mulligan_time_options` offers it to a seat that still owes a
declaration, `Game.take_mulligan_time_action` performs it, and
`Game.settle_pregame` asks it of an unattended seat (who declines by default).
"""

import re
from typing import TYPE_CHECKING

from ..models.card import Card
from ..models.card_state import CardState
from .abilities import self_normalized_effect_text

if TYPE_CHECKING:
    from ..models.game import Game

_EXILE_HAND_REDRAW_RE = re.compile(
    r"^any time you could mulligan and this card is in your hand, you may exile all "
    r"the cards from your hand, then draw that many cards\.?$",
    re.IGNORECASE,
)


def mulligan_time_line(card_name: str, paragraph: str) -> str | None:
    """The line itself when `paragraph` is a mulligan-time action this module
    performs, else `None`."""
    line = re.sub(r"\s*\([^)]*\)\s*$", "", paragraph).strip()
    if "could mulligan" not in line.lower():
        return None
    normalized = self_normalized_effect_text(card_name, line)
    return line if _EXILE_HAND_REDRAW_RE.match(normalized) else None


def mulligan_time_lines(card: Card) -> list[str]:
    return [
        read
        for paragraph in (card.oracle_text or "").split("\n")
        if (read := mulligan_time_line(card.name, paragraph)) is not None
    ]


def perform_exile_hand_and_redraw(game: "Game", username: str, card: CardState) -> int:
    """CR 103.5b: exile every card in hand (the source included), then draw that
    many. Returns how many were exiled and drawn."""
    player = game.player(username)
    hand = list(player.hand)
    game.exile_cards(hand)
    game.draw_cards(player, len(hand))
    return len(hand)
