"""Game zones.

The seven zones the rules define (CR 400.1), plus the sideboard, which the rules
treat as being outside the game rather than as a zone of its own.
"""

from enum import StrEnum


class Zone(StrEnum):
    # The seven rules zones
    LIBRARY = "library"
    HAND = "hand"
    BATTLEFIELD = "battlefield"
    GRAVEYARD = "graveyard"
    STACK = "stack"
    EXILE = "exile"
    COMMAND = "command"

    # Not a rules zone: cards here are outside the game until swapped in
    SIDEBOARD = "sideboard"

    @property
    def is_hidden(self) -> bool:
        """True if the zone's contents are hidden from opponents."""
        return self in _HIDDEN

    @property
    def is_shared(self) -> bool:
        """True if one instance is shared by all players, rather than one each."""
        return self in _SHARED

    @property
    def is_ordered(self) -> bool:
        """True if the order of objects in the zone matters."""
        return self in _ORDERED


_HIDDEN = frozenset({Zone.LIBRARY, Zone.HAND, Zone.SIDEBOARD})
_SHARED = frozenset({Zone.BATTLEFIELD, Zone.STACK, Zone.EXILE, Zone.COMMAND})
_ORDERED = frozenset({Zone.LIBRARY, Zone.GRAVEYARD, Zone.STACK})
