"""Game zones.

The seven zones the rules define (CR 400.1), plus the sideboard, which the rules
treat as being outside the game rather than as a zone of its own.

**Outside the game is not a zone.** CR 400.11a: "Cards in a player's sideboard
are outside the game. See rule 100.4." - the sideboard is a *group of cards*
that is outside the game, not an eighth zone, and the rules never give outside
the game a zone number the way CR 400.1 numbers the seven. CR 100.4 says what a
sideboard is: "a group of additional cards the player may use to modify their
deck between games of a match", capped at fifteen in constructed (CR 100.4a).

Three rules govern what may be done with a card out there, and all three are
about the boundary rather than about a zone:

- **CR 400.11c** - "Cards outside the game can't be affected by spells or
  abilities, except for characteristic-defining abilities printed on them (see
  rule 604.3) and spells and abilities that allow those cards to be brought
  into the game." So an outside-the-game card is not a legal target, is not
  destroyed by a wrath, and is reachable only by the one narrow class of
  ability that fetches it - Karn, the Great Creator's `−2`.
- **CR 108.3b** - "Some spells and abilities allow a player to take cards they
  own from outside the game and bring them into the game." Ownership is the
  gate, not control: the same rule fixes an outside-the-game card's owner as
  "the player who started the game with it in their sideboard".
- **CR 400.11b** - "Some effects bring cards into a game from outside the game.
  Those cards remain in the game until the game ends, their owner leaves the
  game, or a rule or effect removes them from the game."

Which is why `Zone.SIDEBOARD` is the storage for outside-the-game cards here and
`Player.outside_the_game` is the rules-level reading of it: the engine needs
somewhere to keep the objects, and `Zone` is where a `CardState` records where
it is, but nothing should conclude from `Zone.SIDEBOARD` being a `Zone` member
that the rules have an outside-the-game zone. `Zone.is_outside_the_game` is the
predicate to ask instead.
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

    @property
    def is_outside_the_game(self) -> bool:
        """True if cards held here are outside the game (CR 400.11a).

        The sideboard is the one such group this model keeps, and the seven
        rules zones of CR 400.1 are all inside the game. See the module
        docstring: this is a property of the cards, not a zone number.
        """
        return self in _OUTSIDE_THE_GAME


_HIDDEN = frozenset({Zone.LIBRARY, Zone.HAND, Zone.SIDEBOARD})
_SHARED = frozenset({Zone.BATTLEFIELD, Zone.STACK, Zone.EXILE, Zone.COMMAND})
_ORDERED = frozenset({Zone.LIBRARY, Zone.GRAVEYARD, Zone.STACK})
_OUTSIDE_THE_GAME = frozenset({Zone.SIDEBOARD})
