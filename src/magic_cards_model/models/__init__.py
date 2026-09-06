"""Pydantic data models."""

from .card import Card, CardFace, Color, Layout, Legalities, Legality, Rarity, Supertype, Type
from .card_state import CardState, TargetKind, TargetRef
from .deck import CardResolver, Deck, DeckIllegal, DeckLimits
from .game import Game
from .mana import ManaCost, ManaPool
from .match import Match, register_card_resolver
from .player import Player
from .zone import Zone

__all__ = [
    "Card",
    "CardFace",
    "CardResolver",
    "CardState",
    "Color",
    "Deck",
    "DeckIllegal",
    "DeckLimits",
    "Game",
    "Layout",
    "Legalities",
    "Legality",
    "ManaCost",
    "ManaPool",
    "Match",
    "Player",
    "Rarity",
    "register_card_resolver",
    "Supertype",
    "TargetKind",
    "TargetRef",
    "Type",
    "Zone",
]
