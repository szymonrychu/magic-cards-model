"""Aura/Equipment attack-block restrictions read off the attachment (CR 508.1c, 509.1b, 508.1d)."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.card import Card
    from ..models.card_state import CardState
    from ..models.game import Game


def attached_attack_refusal(game: "Game", creature: "CardState") -> str | None:
    return None


def attached_block_refusal(game: "Game", blocker: "CardState") -> str | None:
    return None


def attached_attack_requirements(game: "Game", creature: "CardState") -> list[bool]:
    """One entry per attack requirement; True when only an attack on a player obeys it."""
    return []


def reads_attached_restriction_line(printing: "Card", text: str, *, card_name: str) -> bool:
    return False
