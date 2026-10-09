"""Group attack restrictions and requirements (CR 508.1c, 508.1d, 509.1b)."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.card import Card
    from ..models.card_state import CardState
    from ..models.game import Game


def group_attack_refusal(game: "Game", creature: "CardState", defender) -> str | None:
    return None


def group_block_refusal(game: "Game", blocker: "CardState", attacker: "CardState") -> str | None:
    return None


def group_attack_requirements(game: "Game", creature: "CardState") -> list[bool]:
    """One entry per attack requirement; True when only an attack on a player obeys it."""
    return []


def reads_group_attack_line(printing: "Card", text: str, *, card_name: str) -> bool:
    return False
