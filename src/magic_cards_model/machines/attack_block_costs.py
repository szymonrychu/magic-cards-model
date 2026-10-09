"""Costs to attack or block (CR 508.1h, 509.1d)."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.card import Card
    from ..models.card_state import CardState
    from ..models.game import Game


def attack_costs(game: "Game", creature: "CardState", defender) -> list:
    """`combat.AttackCost` entries charged to `creature` attacking `defender`."""
    return []


def reads_attack_block_cost_line(printing: "Card", text: str, *, card_name: str) -> bool:
    return False
