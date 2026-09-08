"""Game zones.

The seven zones the rules define (CR 400.1), the optional eighth that same rule
names ("Some older cards also use the ante zone"), plus the sideboard, which the
rules treat as being outside the game rather than as a zone of its own.

**Ante is a zone, and a public one.** CR 400.2 lists "Graveyard, battlefield,
stack, exile, ante, and command" as the public zones, and CR 407.4 gives the
only verb that reaches it: "To ante an object is to put that object into the
ante zone from whichever zone it's currently in. The owner of an object is the
only player who can ante that object." `Game.ante` enforces that ownership
check; CR 407.3 is why nothing else in the pool can put a card there.

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

    #: CR 400.1's optional eighth: "Some older cards also use the ante zone."
    #: CR 407.4 is the only way in - "To ante an object is to put that object
    #: into the ante zone from whichever zone it's currently in" - and CR 400.2
    #: lists ante among the public zones. `Game.ante` is the verb.
    ANTE = "ante"

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
#: CR 400.1: "Each player has their own library, hand, graveyard, and sideboard.
#: The other zones are shared by all players" - ante among them.
_SHARED = frozenset({Zone.BATTLEFIELD, Zone.STACK, Zone.EXILE, Zone.COMMAND, Zone.ANTE})
_ORDERED = frozenset({Zone.LIBRARY, Zone.GRAVEYARD, Zone.STACK})
_OUTSIDE_THE_GAME = frozenset({Zone.SIDEBOARD})


class SharedZoneError(RuntimeError):
    """A `Player` was asked for a zone CR 400.1 gives the game, not a player.

    CR 400.1: "Each player has their own library, hand, and graveyard. The
    other zones are shared by all players." So there is exactly one
    battlefield, one stack, one exile zone, one command zone and one ante
    zone in a game, they live in `Game.shared_zones`, and `Player.zones`
    never holds any of them.

    Asking a player for one used to be silently answered - `Player.cards_in`
    was `zones.setdefault(zone, [])`, so a *read* minted an empty per-player
    pile and handed it back. Anything then written into that pile was
    invisible to `Game.exile`, to `Game.all_targetables` and to every seat's
    board view, and a test asserting on the same read saw a perfectly
    consistent per-player exile zone that does not exist. Refusing is what
    makes that class of defect impossible rather than merely discouraged.

    A `RuntimeError` rather than a `ValueError` on purpose, the same choice
    `SchemaVersionMismatch` makes: `machines/` catches `ValueError` in dozens
    of places around effect resolution, and a shared-zone mistake swallowed
    there would come back as "the effect did nothing", which is the very
    symptom this exception exists to stop being silent.
    """


#: Where each shared zone actually lives, named in the refusal so a caller is
#: told what to use instead of only that this was wrong.
_SHARED_ZONE_ACCESSOR = {
    Zone.BATTLEFIELD: "Game.battlefield",
    Zone.STACK: "Game.stack",
    Zone.EXILE: "Game.exile",
    Zone.COMMAND: "Game.shared_zones[Zone.COMMAND]",
    Zone.ANTE: "Game.ante_zone",
}


def refuse_shared_zone(zone: Zone, *, doing: str) -> None:
    """Raise `SharedZoneError` if `zone` is one of CR 400.1's shared zones."""
    if not zone.is_shared:
        return
    raise SharedZoneError(
        f"cannot {doing} a player's {zone.value}: the {zone.value} is shared by all "
        f'players (CR 400.1: "Each player has their own library, hand, and graveyard. '
        f'The other zones are shared by all players."), so no player has one of their '
        f"own - use {_SHARED_ZONE_ACCESSOR[zone]}"
    )
