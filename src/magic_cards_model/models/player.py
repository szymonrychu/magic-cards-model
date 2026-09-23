"""A player: their name, their zones, and the cards in them."""

from collections.abc import Callable, Iterable, Mapping
from random import Random
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, ConfigDict, Field

from ..machines.layers import Duration
from ..snapshot import EngineModel
from .card import Card
from .card_state import CardState, Counter, CounterKind, Counters
from .deck import CardResolver, Deck
from .mana import ManaPool
from .token import move_refused
from .zone import Zone, refuse_shared_zone

POISON_TO_LOSE = 10
"""CR 704.5c: ten or more poison counters and the player loses the game."""


class PlayerTargetingGrant(EngineModel):
    """One hexproof or shroud ability an effect gave a player, with how long
    it lasts (CR 702.11c, CR 702.11d, CR 702.18a, CR 611.2a).

    `quality` is set only for CR 702.11d's "hexproof from [quality]"; plain
    hexproof and shroud leave it `None`. `until_next_turn_of` names whose next
    turn ends a `Duration.UNTIL_YOUR_NEXT_TURN` grant - the "your" of the
    printed text, the grant's own controller."""

    model_config = ConfigDict(frozen=True)

    keyword: Literal["hexproof", "shroud"]
    quality: str | None = None
    duration: Duration = Duration.UNTIL_END_OF_TURN
    until_next_turn_of: str | None = None
    source_name: str = ""


class PlayerZones(dict[Zone, list[CardState]]):
    """`Player.zones`: the per-player zones, and only those (CR 400.1).

    "Each player has their own library, hand, and graveyard. The other zones
    are shared by all players." A plain `dict` let a shared zone be written
    into a player anyway - `zones[Zone.EXILE] = [...]`, or the
    `zones.setdefault(zone, [])` inside `Player.cards_in`, which minted an
    empty per-player exile pile as a side effect of a *read*. Cards put into
    such a pile are invisible to `Game.exile`, `Game.all_targetables` and
    every seat's board, and a test asserting on the same read saw nothing
    wrong. Refusing here is what makes the pile impossible to create rather
    than merely wrong to create.

    `get` and `in` are deliberately left alone: neither mints anything, and
    "this player has no exile pile" is a thing a test is allowed to check.
    """

    __slots__ = ()

    def __getitem__(self, zone: Zone) -> list[CardState]:
        refuse_shared_zone(zone, doing="read")
        return super().__getitem__(zone)

    def __setitem__(self, zone: Zone, cards: list[CardState]) -> None:
        refuse_shared_zone(zone, doing="write")
        super().__setitem__(zone, cards)

    def __missing__(self, zone: Zone) -> list[CardState]:
        refuse_shared_zone(zone, doing="read")
        raise KeyError(zone)

    def setdefault(self, zone: Zone, default: list[CardState] | None = None) -> list[CardState]:
        refuse_shared_zone(zone, doing="read")
        return super().setdefault(zone, default if default is not None else [])

    def update(self, other: Any = (), /, **kwargs: list[CardState]) -> None:
        keys: Iterable[Any] = other.keys() if isinstance(other, Mapping) else ()
        for zone in keys:
            refuse_shared_zone(Zone(zone), doing="write")
        super().update(other, **kwargs)


def _per_player_zones(zones: dict[Zone, list[CardState]]) -> PlayerZones:
    """Refuse a shared zone at decode too, then wrap.

    `PlayerZones(zones)` alone would not catch it: `dict.__init__` fills the
    mapping at C level without going through `__setitem__`, so a persisted
    game carrying a bogus `"exile"` pile - written by this defect before it
    was closed - would decode straight back into one.
    """
    for zone in zones:
        refuse_shared_zone(zone, doing="decode")
    return PlayerZones(zones)


PerPlayerZones = Annotated[dict[Zone, list[CardState]], AfterValidator(_per_player_zones)]

Seed = int | str | bytes | Random
"""What a shuffle takes. Never nothing: an unseeded shuffle is not reproducible."""


def _rng(seed: Seed) -> Random:
    return seed if isinstance(seed, Random) else Random(seed)  # noqa: S311 - not cryptographic


#: "You have no maximum hand size." - the emblem ability this engine reads
#: generally (CR 114.2's own template): Wrenn and Seven's -8 and Tamiyo,
#: Inquisitive Student's -7 both print this exact sentence.
_NO_MAXIMUM_HAND_SIZE_EMBLEM_TEXT = "you have no maximum hand size"


class Player(EngineModel):
    """One player and everything they own.

    Only the per-player zones live here. The battlefield, stack, exile, and
    command zone are shared, so a game state owns those, not a player.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    username: str
    life: int = 20
    counters: Counters = Field(default_factory=Counters)
    """Counters on the player, not on an object (CR 122.1).

    Poison is the one with a rule of its own - ten of them lose the game
    (CR 704.5c) - and energy is what `{E}` pays with (CR 107.14). Any other
    kind a card invents is just a name and a count.
    """

    cannot_gain_life: bool = False
    """Whether an effect says this player can't gain life.

    CR 101.2: "When a rule or effect allows or directs something to happen, and
    another effect states that it can't happen, the 'can't' effect takes
    precedence." CR 614.17 puts these effects next to replacement effects
    without making them replacement effects, and CR 614.17c closes the door
    behind them: an event that can't happen "can only be replaced by a
    self-replacement effect". So `gain_life` does not reduce the gain to zero
    or prevent it - the gain simply does not occur, and nothing downstream
    (CR 119.9's "whenever a player gains life", say) sees an event.

    Two shapes of card set it, and neither can reach it yet: Screaming
    Nemesis's "they can't gain life for the rest of the game" is a one-shot
    effect with an unbounded duration, and Leyline of Punishment's "Players
    can't gain life." is a static ability whose continuous effect would set it
    on every player while the Leyline is on the battlefield. The first needs a
    row in `machines/effects.py`, the second one in `machines/layers.py`; both
    are `xfail`ed in `tests/scenarios/test_life_gain_prohibition.py`."""

    cannot_lose_life: bool = False
    """Whether an effect says this player can't lose life (CR 101.2, as above).

    The mirror of `cannot_gain_life`, here because CR 119.8 is the mirror of
    CR 119.7 and `exchange_life_totals` has to check both ends of the exchange
    to answer CR 701.12a's "if the entire exchange can't happen, no part of the
    exchange occurs" correctly. `lose_life` does not consult it: no card in the
    pool imposes it, and a prohibition half-enforced across the engine's life
    paths would be worse than one enforced in the single place that reads it."""

    protection_from: list[str] = Field(default_factory=list)
    """Every quality this *player* has protection from (CR 702.16a).

    CR 702.16a: "Protection is a static ability, written 'Protection from
    [quality].' This quality is usually a color ... but can be any
    characteristic value or information." Runed Halo's "You have protection
    from the chosen card name." is the card-name flavour, and CR 702.16b,
    CR 702.16c and CR 702.16e each say "permanent **or player**" - the player
    half had nowhere to live before this list.

    A permanent's protection is read off its text by `Game.protection_qualities`
    and `Game._effective_protection_qualities`; a player has no text, so a
    grant is recorded here instead, by `gain_protection_from`."""

    targeting_grants: list[PlayerTargetingGrant] = Field(default_factory=list)
    """Hexproof and shroud this *player* was given by a resolved spell or
    ability (CR 702.11c, CR 702.11d, CR 702.18a's "or player", CR 611.2a).

    One entry per ability: CR 702.11f makes "hexproof from blue and from
    black" two abilities, so it is two entries. A static grant ("You have
    hexproof.") is not recorded here - it is read fresh off the battlefield by
    `Game.player_hexproof`/`Game.player_has_shroud`, so it ends with its
    permanent (CR 604.2). `Game.cleanup_step` drops the "until end of turn"
    entries (CR 514.2) and `Game.begin_turn_for` the "until your next turn"
    ones (CR 611.2a)."""

    mana_pool: ManaPool = Field(default_factory=ManaPool)
    zones: PerPlayerZones = Field(
        default_factory=lambda: PlayerZones(
            {
                Zone.LIBRARY: [],
                Zone.HAND: [],
                Zone.GRAVEYARD: [],
                Zone.SIDEBOARD: [],
            }
        )
    )
    """This player's own zones (CR 400.1), and never a shared one.

    A `PlayerZones`, which refuses `Zone.BATTLEFIELD`, `Zone.STACK`,
    `Zone.EXILE`, `Zone.COMMAND` and `Zone.ANTE` outright - those live in
    `Game.shared_zones`, one each per game rather than one each per player.
    """
    library_epoch: int = 0
    """How many times this player's library has been reordered or added to.

    CR 701.20d: "If cards in a player's library are shuffled or otherwise
    reordered, any revealed cards that are reordered stop being revealed and
    become new objects", and CR 401.2 keeps the library one ordered pile, so a
    record of which card sat where is only good for the order it was made in.
    `Reveal.library_epoch` records this counter and `Game.known_to` compares
    it. It moves on every shuffle (`Game.shuffle_library`, `shuffle`), every
    card put into the library (`add`, which `move` and CR 103.5's mulligan
    bottoming go through) and every put-back that writes the library list
    directly (`note_library_changed`). Drawing or otherwise taking a card off
    the library does not move it: the cards left keep their order."""

    starting_hand_size: int = 7
    """CR 103.5. A field because effects can change it, though none do yet."""

    maximum_hand_size: int = 7
    """CR 402.2. How many cards may be kept through the cleanup step.

    A field for the same reason: a player may have any number of cards in hand,
    and only the cleanup step's turn-based action (CR 514.1, 703.4n) cares.
    """

    mulligans_taken: int = 0
    hand_kept: bool = False
    first_mulligan_free: bool = False
    """Whether this game's first mulligan costs nothing (CR 103.5c, CR 800.6).

    "In a multiplayer game and in any Brawl game, the first mulligan a player
    takes doesn't count toward the number of cards that player will put on the
    bottom of their library or the number of mulligans that player may take."
    A multiplayer game is one that begins with more than two players (CR 800.1,
    CR 100.1b), so the match sets this for every player of such a game before
    the mulligan process runs; a two-player game leaves it off.
    """
    life_lost_tally: int = 0
    """Bookkeeping behind `life_lost_this_turn` - read that, not this.

    Every life loss adds to it and nothing subtracts, because "the life you've
    lost this turn" is gross: Children of Korlis gives back what was lost even
    if the same turn gave some of it back already."""

    life_lost_tally_turn: int | None = None
    """Which turn `life_lost_tally` was counted during, as `TurnMachine.
    turns_taken`.

    The tally clears itself by comparing this stamp rather than by being
    emptied at the turn boundary, because the turn boundary is `Game.advance`'s
    and a `Player` has no hook there. `turns_taken` is the same signal
    `Game.advance` and `PlayPermission.expired` already compare against, and it
    is the right one: CR 500.7's extra turn ("Some effects can give a player
    extra turns. They do this by adding the turns directly after the specified
    turn") moves neither the active seat nor the turn number, so the same
    player taking two turns in a row still gets two different stamps.

    `None` is the stamp of a player with no game around them, which never
    changes, so a `Player` built on its own accumulates and never clears."""

    tried_to_draw_from_empty_library: bool = False
    """Set when a draw found no cards. The player loses the next time state-based
    actions are checked (CR 104.3c, 704.5b) - which the game does, not the player."""

    has_citys_blessing: bool = False
    """CR 702.131c: "a designation that has no rules meaning other than to act
    as a marker that other rules and effects can identify." Granted by *ascend*
    (CR 702.131b's "any time", through `machines.keywords.
    grant_the_citys_blessing`, which `Game.emit` runs before matching
    triggers; CR 702.131a's spell version as the spell resolves) once a player
    controls ten or more permanents.

    Set-only: CR 702.131c gives no rule that ever takes it away, so a player
    who drops back under ten permanents keeps it, and this field is never
    cleared on a new turn the way `life_gained_this_turn` is."""

    companion_id: UUID | None = None
    """The `CardState.id` of this player's chosen companion (CR 702.139a),
    once `load_deck` has verified its printed condition against the mainboard
    and stamped it into `Zone.SIDEBOARD` - an id, not the object itself, the
    same "ids only" convention `models/action.py` documents: the live card is
    reached through `outside_the_game`/`owned_outside_the_game`, never
    embedded here a second time. `None` for a player with no revealed
    companion, which is the default - CR 103.2b's reveal is optional."""

    companion_action_used: bool = False
    """CR 116.2g: "but only if they haven't done so yet this game" - the
    special action that pays `{3}` to put the companion into hand may be
    taken once. Set by `Game.bring_companion_to_hand`."""

    game: Any = Field(default=None, exclude=True, repr=False)
    """The game this player is in, set by `Game.model_post_init`.

    A back-reference and nothing more. It exists because a handful of things a
    player does are decided by rules that live above them - CR 701.9a's discard
    is replaceable (CR 702.35a), and a `Player` on its own has nothing to ask.

    Excluded from the serialised model and from `repr`, so the game state stays
    a tree: `Game` already holds the players, and this would otherwise be a
    cycle. A player built outside a game has `None` here and every path that
    reads it falls back to the unreplaced behaviour."""

    @property
    def library(self) -> list[CardState]:
        return self.zones[Zone.LIBRARY]

    def note_library_changed(self, *, placed: list[CardState] | None = None) -> None:
        """Move `library_epoch` on (CR 701.20d), for a put-back that writes
        the library list directly instead of going through `add`.

        With no `placed`, every library record ends: a shuffle, or a write
        that puts cards above others or reorders them. `placed` names the
        cards a put-back just wrote *below or among only themselves* - onto
        the bottom, or a scry's own cards - leaving every other card in the
        order it was in (CR 401.2), so the live library records of those
        other cards are re-pinned to the new epoch (`Game.keep_untouched_
        library_records`) and a record of a card in `placed` still ends."""
        game = self.game
        if placed is None or game is None:
            self.library_epoch += 1
            return
        game.keep_untouched_library_records(self, placed)

    @property
    def hand(self) -> list[CardState]:
        return self.zones[Zone.HAND]

    @property
    def graveyard(self) -> list[CardState]:
        return self.zones[Zone.GRAVEYARD]

    @property
    def sideboard(self) -> list[CardState]:
        return self.zones[Zone.SIDEBOARD]

    def cards_in(self, zone: Zone) -> list[CardState]:
        """The cards in one of *this player's* zones (CR 400.1).

        Raises `SharedZoneError` for the battlefield, the stack, exile, the
        command zone and the ante zone: those are the game's, not a player's,
        and asking here used to mint an empty pile of the player's own as a
        side effect of the read. `Game.battlefield` / `Game.exile` /
        `Game.stack` / `Game.ante_zone` are the real ones.
        """
        refuse_shared_zone(zone, doing="read")
        return self.zones.setdefault(zone, [])

    # -- outside the game (CR 400.11) --------------------------------------

    @property
    def outside_the_game(self) -> list[CardState]:
        """The cards this player has outside the game (CR 400.11a).

        "Cards in a player's sideboard are outside the game." The sideboard is
        the only group of outside-the-game cards this model keeps, so this is
        the sideboard read at the level the rules talk about it - and it is a
        *reading*, not a second store: `models/zone.py` explains why outside
        the game is not a zone and `Zone.SIDEBOARD` is where the objects live.

        The distinction matters for what a card out here may do. CR 400.11c:
        "Cards outside the game can't be affected by spells or abilities,
        except for characteristic-defining abilities printed on them ... and
        spells and abilities that allow those cards to be brought into the
        game." Nothing in this engine iterates the sideboard as though it were
        a zone of the game, and nothing should start.
        """
        return self.sideboard

    def owned_outside_the_game(
        self, matches: "Callable[[CardState], bool] | None" = None
    ) -> list[CardState]:
        """The outside-the-game cards this player *owns*, optionally filtered.

        CR 108.3b: "Some spells and abilities allow a player to take cards they
        own from outside the game and bring them into the game." Owning is the
        gate - "you own", not "you control" - and CR 108.3b fixes the owner of
        an outside-the-game card as "the player who started the game with it in
        their sideboard", which `Player.add` stamps in `load_deck`.

        A card sitting in this player's sideboard that somebody else owns is
        therefore not theirs to bring in, and is filtered out here rather than
        being caught later: `Player.add` only fills in a blank owner, so a
        sideboard can hold an object stamped for another player.
        """
        return [
            state
            for state in self.outside_the_game
            if state.owner == self.username and (matches is None or matches(state))
        ]

    def bring_into_the_game(self, card_state: CardState, zone: Zone = Zone.HAND) -> CardState:
        """Take a card this player owns from outside the game into `zone`.

        CR 400.11b: "Some effects bring cards into a game from outside the
        game. Those cards remain in the game until the game ends, their owner
        leaves the game, or a rule or effect removes them from the game,
        whichever comes first." Nothing puts a card back out, so this is a
        one-way move, and the card is an ordinary object of its new zone from
        here on.

        Refuses anything CR 108.3b does not allow: a card that is not outside
        the game at all, and a card this player does not own. Both raise rather
        than being quietly skipped - a fetch that silently found nothing is the
        shape of bug this whole subsystem exists to make impossible.

        Note what this does *not* touch: the registered `Deck`. Deck legality
        (CR 100.2a, 100.4a) is a property of the decklist, checked by
        `Deck.check_legality` against `Match.decks`, and a card moving out of
        the physical sideboard mid-game changes neither board of that list.
        """
        if not card_state.zone.is_outside_the_game:
            raise ValueError(
                f"{card_state.name} is in {card_state.zone.value}, not outside the game "
                f"(CR 400.11a)"
            )
        if card_state.owner != self.username:
            raise ValueError(
                f"{self.username} does not own {card_state.name}, so it cannot be brought "
                f"in from outside the game (CR 108.3b)"
            )
        if card_state not in self.outside_the_game:
            raise ValueError(f"{card_state.name} is not among {self.username}'s outside-game cards")
        if zone is Zone.EXILE:
            # CR 400.1: a shared zone belongs to the game, so the move into it
            # is the game's to make - `Player.move` would build a per-player
            # pile of it instead. Exile is the only shared zone anything in
            # this pool brings a card in to (Wish), and CR 406.2's door is
            # `Game.exile_cards`, which lifts the card out of the sideboard
            # itself. Every other shared zone falls through to `move` below
            # and is refused there.
            if self.game is None:
                raise ValueError(
                    f"{card_state.name} cannot be brought into the shared exile zone "
                    f"without a game (CR 400.1, CR 406.2)"
                )
            self.game.exile_cards([card_state])
            return card_state
        self.move(card_state, zone)
        return card_state

    def add(self, card_state: CardState, zone: Zone) -> None:
        """Put a card into one of this player's zones, and record who owns it.

        CR 108.3: "The owner of a card in the game is the player who started the
        game with it in their deck." Ownership never changes afterwards - a card
        that ends up in an opponent's graveyard is still owned by the player who
        brought it - so it is stamped once, the first time the card is put into
        one of a player's zones, and left alone from then on.

        Which is why this only fills in a blank. A card moving between zones
        goes through here too (`move`, `draw`, `discard` all do), and the first
        of those must not restamp an opponent's card as this player's.

        CR 111.8 can refuse the move outright: "A token that has left the
        battlefield can't move to another zone or come back onto the battlefield.
        If such a token would change zones, it remains in its current zone
        instead." `TokenState.move_to` declines to change the token's own `zone`,
        and this is the other half - a refused card is not appended to the new
        zone's list either, or the game state would list a token in a zone its
        own `zone` attribute denies. Ownership is still stamped, because CR 108.3
        is about who brought the object and has nothing to do with where it is.

        `zone` must be one of this player's own (CR 400.1). The battlefield,
        the stack, exile, the command zone and the ante zone are shared, so
        putting a card into one of those is the *game*'s move to make -
        `Game.put_onto_battlefield`, `Game.put_on_stack`, `Game.exile_cards` /
        `Game.exile_permanent`, `Game.ante`. Naming one here is refused rather
        than quietly building a per-player pile of it.
        """
        refuse_shared_zone(zone, doing="put a card into")
        if card_state.owner is None:
            card_state.owner = self.username
        if move_refused(card_state, zone) is not None:
            return
        origin = card_state.zone
        from_own_hidden_group_to_hand = (
            zone is Zone.HAND
            and (origin is Zone.LIBRARY or origin.is_outside_the_game)
            and card_state.owner == self.username
        )
        # CR 400.2: every player saw the card's face in a public zone - unless
        # it sat in exile face down, which CR 406.3 lets nobody examine.
        from_public_zone_to_hand = (
            zone is Zone.HAND
            and not origin.is_hidden
            and not (origin is Zone.EXILE and not card_state.face_up)
            and card_state.owner == self.username
        )
        stamp_before = card_state.zone_change_stamp
        if not origin.is_shared:
            # CR 400.7: a card that moves is a new object in its new zone and
            # nothing of it stays behind. A caller that looked at a card and
            # left it listed where it was (battle 7, B7-01: a card put into
            # hand stayed in the library too) must not duplicate it.
            held = self.zones.get(origin, [])
            for index, state in enumerate(held):
                if state is card_state:
                    del held[index]
                    break
        card_state.move_to(zone)
        self.cards_in(zone).append(card_state)
        if zone is Zone.LIBRARY:
            # Appended, so below every card already there (CR 401.2): their
            # order is untouched and what was known about them stays true.
            self.note_library_changed(placed=[card_state])
        elif from_own_hidden_group_to_hand and self.game is not None:
            # CR 121.1's draw, any effect making the same move, or a card
            # revealed from outside the game and put into hand (CR 400.11a,
            # CR 701.20a): what a player knew may follow it into the hand.
            self.game.carry_knowledge_into_hand(card_state, stamp_before, origin)
        elif from_public_zone_to_hand and self.game is not None:
            self.game.carry_public_knowledge_into_hand(card_state, origin)

    def move(self, card_state: CardState, to_zone: Zone) -> None:
        """Move a card between this player's zones.

        Both ends have to be this player's own (CR 400.1), and both are
        checked before anything moves: a card sitting in a shared zone is not
        a player's to lift out, and a shared zone is not a player's to drop it
        into. Either way the answer is the same - that move belongs to `Game`.

        A move CR 111.8 refuses leaves the card exactly where it is - it is not
        lifted out of its current zone and then dropped, it simply does not move.
        """
        refuse_shared_zone(card_state.zone, doing="take a card out of")
        refuse_shared_zone(to_zone, doing="put a card into")
        if move_refused(card_state, to_zone) is not None:
            return
        self.cards_in(card_state.zone).remove(card_state)
        self.add(card_state, to_zone)

    def draw(self, count: int = 1) -> list[CardState]:
        """Draw from the top of the library. Raises if the library runs out.

        Drawing from an empty library does not lose the game on the spot: the
        player loses the next time state-based actions are checked. That check
        belongs to the game, so this only reports the failure.
        """
        if len(self.library) < count:
            raise ValueError(f"{self.username} cannot draw {count} from {len(self.library)} cards")

        drawn = self.library[:count]
        for card_state in drawn:
            self.move(card_state, Zone.HAND)
        return drawn

    def draw_up_to(self, count: int = 1) -> list[CardState]:
        """Draw `count`, or as many as are left, and record a failed draw.

        CR 104.3c: a player required to draw more cards than are left draws the
        remaining cards and then loses the game the next time a player would
        receive priority. That loss is a state-based action (CR 704.5b), so it
        belongs to the game; this only sets the flag the game reads.

        `draw` stays strict, because a scenario asking for a draw it cannot
        make is usually a scenario that drifted. This is the variant the
        rules-driven paths - the draw step, and the opening hand - use.
        """
        available = min(count, len(self.library))
        if available < count:
            self.tried_to_draw_from_empty_library = True
        return self.draw(available) if available else []

    # -- discarding --------------------------------------------------------

    def discard(self, card_state: CardState) -> CardState:
        """Discard a card (CR 701.9a).

        "To discard a card, move it from its owner's hand to that player's
        graveyard." That move can be replaced: CR 702.35a's madness is "if a
        player would discard this card, that player discards it, but exiles it
        instead of putting it into their graveyard", so the card is still
        discarded and simply lands somewhere else.

        Deciding that needs a game, and `machines/keywords.discard` is where the
        rule lives - it applies the replacement and raises CR 702.35a's second
        ability off the exiling. `Player.game` is the back-reference that gets
        there. A player built outside a game has none, and falls back to the
        plain CR 701.9a move.
        """
        if card_state not in self.hand:
            raise ValueError(f"{card_state.name} is not in {self.username}'s hand")
        if self.game is not None:
            # Imported here: `machines/keywords.py` builds on the models.
            from ..machines.keywords import discard as discard_with_replacements

            return discard_with_replacements(self.game, card_state, self.username)
        self.move(card_state, Zone.GRAVEYARD)
        return card_state

    @property
    def emblems(self) -> list[CardState]:
        """CR 114.2's "[Player] gets an emblem with [ability]": every emblem
        this player controls, in the order granted - read off the shared
        command zone (`Game.create_emblem`, `Game.emblems_of`), where an
        emblem's abilities function (CR 114.4). Empty for a player not bound
        to a game."""
        game = self.game
        return [] if game is None else game.emblems_of(self.username)

    @property
    def has_no_maximum_hand_size(self) -> bool:
        """CR 613.11: whether some continuous effect this player controls
        overrides CR 402.2's own maximum hand size to "no maximum" - read
        generally off any emblem granting CR 114.2's own "You have no
        maximum hand size." sentence, not any one card's name, so a future
        printing granting the identical ability the same way is covered for
        free.
        """
        return any(
            (emblem.card.oracle_text or "").strip().rstrip(".").lower()
            == _NO_MAXIMUM_HAND_SIZE_EMBLEM_TEXT
            for emblem in self.emblems
        )

    @property
    def cards_over_maximum_hand_size(self) -> int:
        """How many cards the cleanup step would make this player discard
        (CR 402.2), or zero unconditionally when `has_no_maximum_hand_size`
        holds (CR 613.11's own game-rule-modifying continuous effect)."""
        if self.has_no_maximum_hand_size:
            return 0
        return max(0, len(self.hand) - self.maximum_hand_size)

    def discard_to_maximum_hand_size(
        self, chosen: list[CardState] | None = None
    ) -> list[CardState]:
        """Discard down to maximum hand size, as the cleanup step does (CR 514.1).

        CR 701.9b makes this the player's own choice, so passing None does not
        pick for them: it asks, through `Game.ask_cleanup_discard` (CR 608.2d),
        which routes to a scripted answer, then the replay tape, and only then
        to the back of the hand - the same fallback this method used before
        that machinery existed, kept as the default so an unscripted game is
        unaffected. A player built outside a game (no `self.game`) has nothing
        to ask, so it falls straight back to that same default. Returns what
        was discarded, which is empty when the hand was already small enough.

        CR 514.1's turn-based action only fires "if the active player's hand
        contains more cards than their maximum hand size" - at or under it,
        there is nothing to discard and, per CR 701.9b, nothing to choose
        either (there is exactly one legal answer: discard none). `needed ==
        0` short-circuits before ever calling `Game.ask_cleanup_discard`, so a
        player already within their maximum hand size is never asked a
        decision with no real choice in it - a live seat behind the api
        (`magic-cards-model-api`) would otherwise park a request for a whole
        decision timeout only to be answered "discard nothing".

        The cards go out through `Game.discard_cards`, the one place that
        counts a discard into `Game.cards_discarded_this_turn` and emits
        `TriggerEvent.DISCARDS_A_CARD`. CR 701.9a has no quiet variant for the
        cleanup step, and the trigger is not academic here: CR 514.3a has the
        game check, immediately after this discard, whether "any triggered
        abilities are waiting to be put onto the stack ... those abilities are
        put onto the stack and the active player gets priority", followed by
        another cleanup step. A discard trigger fired during cleanup reopens
        the step rather than being swallowed by the turn ending, so routing it
        anywhere else would lose a real play. It also goes out as **one**
        instruction with a count, which is what CR 603.2c and Captain Howler's
        "for each card discarded this way" want from a multi-card discard.

        A player with no game still falls back to `discard` card by card;
        there is no counter and no trigger to feed out there.
        """
        needed = self.cards_over_maximum_hand_size
        if chosen is None:
            if needed == 0:
                chosen = []
            elif self.game is not None:
                chosen = self.game.ask_cleanup_discard(self, needed)
            else:
                chosen = self.hand[len(self.hand) - needed :]
        if len(chosen) != needed:
            raise ValueError(f"{self.username} must discard {needed} cards, not {len(chosen)}")
        for card_state in chosen:
            if card_state not in self.hand:
                raise ValueError(f"{card_state.name} is not in {self.username}'s hand")
        if self.game is None:
            return [self.discard(card_state) for card_state in chosen]
        return self.game.discard_cards(self.username, list(chosen))

    def gain_life(self, amount: int) -> int:
        """Gain life, returning the new total (CR 119.3).

        CR 119.3: "If an effect causes a player to gain life or lose life, that
        player's life total is adjusted accordingly."

        This is the one place a life total goes up. `Game.gain_life` applies
        replacement effects (CR 119.10, e.g. Alhammarret's Archive) and then
        calls here for the actual change - but a parsed effect that gains life
        directly (`machines/effects.py`'s "you gain N life" clauses) and a
        cost that pays with life the other way (`machines/cost.py`) both land
        here too, without going through `Game.gain_life` first.

        CR 119.9 treats "whenever a player gains life" as "whenever a source
        causes a player to gain life" - it does not care which code path
        caused it - so the per-turn fact (`Game.life_gained_this_turn`) is
        recorded right here, the one spot every gain passes through, rather
        than only at `Game.gain_life`'s call site. Recording it only there
        left the direct paths silently unrecorded: two Guide of Souls raising
        alice from 20 to 22 left `life_gained_this_turn` empty, and Ocelot
        Pride's end step trigger never went on the stack. Its amount twin,
        `Game.life_gained_amount_this_turn`, is recorded in the same place
        for the same reason - Germinate Recruits' own X (CR 107.3f) needs the
        total, not just whether any gain happened.

        `cannot_gain_life` refuses the whole thing (CR 101.2): the life total
        is left alone *and* nothing is recorded, because a gain that can't
        happen is not a gain event for CR 119.9 to trigger on. The argument
        check runs first regardless - a negative "gain" is a caller bug at any
        life total, and a prohibited player is not somewhere to hide one.

        `cannot_gain_life` is the prohibition set directly on this player;
        `Game.life_gain_prohibited` is the one a permanent on the battlefield
        imposes (Leyline of Punishment's "Players can't gain life"). Both are
        CR 119.7's "an effect says that a player can't gain life" and both
        refuse identically - the board-derived one is asked fresh rather than
        mirrored onto a field, because CR 604.2 ends it with its source.
        """
        if amount < 0:
            raise ValueError("cannot gain a negative amount of life")
        if self.cannot_gain_life:
            return self.life
        if self._prohibited_from_gaining_life:
            return self.life
        self.life += amount
        if self.game is not None:
            self.game.life_gained_this_turn.add(self.username)
            self.game.life_gained_amount_this_turn[self.username] = (
                self.game.life_gained_amount_this_turn.get(self.username, 0) + amount
            )
        return self.life

    @property
    def _prohibited_from_gaining_life(self) -> bool:
        """Whether something on the battlefield forbids this player gaining
        life (CR 119.7). False for a player with no game around them - there is
        no battlefield to carry the prohibition."""
        game = self.game
        if game is None:
            return False
        return game.life_gain_prohibited(self.username) is not None

    def lose_life(self, amount: int) -> int:
        """Lose life, returning the new total (CR 119.3).

        Life goes below zero freely: losing the game for being at zero or less
        is a state-based action the game checks (CR 704.5a), not something
        that happens the instant the life is lost.

        This is the one place a life total goes down other than by an exchange
        (which comes back through here anyway, CR 701.12c), so it is where the
        per-turn tally behind `life_lost_this_turn` is kept: damage routes here
        via `Game.deal_damage` (CR 119.2, "damage dealt to a player normally
        causes that player to lose that much life") and a life *cost* routes
        here via `machines/cost.py` (CR 118.3b, "paying life is done by
        subtracting the indicated amount of life"). Counting at the call sites
        instead would miss whichever one a later card invents.
        """
        if amount < 0:
            raise ValueError("cannot lose a negative amount of life")
        self.life -= amount
        if amount:
            self._record_life_lost(amount)
        return self.life

    # -- life lost this turn -----------------------------------------------

    @property
    def _current_turn_stamp(self) -> int | None:
        """`TurnMachine.turns_taken`, or None for a player with no turn around
        them - one built outside a game, or in a game whose turn machine has
        not been made yet."""
        game = self.game
        if game is None or getattr(game, "turn", None) is None:
            return None
        return game.turn.turns_taken

    def _record_life_lost(self, amount: int) -> None:
        stamp = self._current_turn_stamp
        if self.life_lost_tally_turn != stamp:
            self.life_lost_tally = 0
            self.life_lost_tally_turn = stamp
        self.life_lost_tally += amount

    @property
    def life_lost_this_turn(self) -> int:
        """How much life this player has lost so far this turn, gross.

        Children of Korlis's "You gain life equal to the life you've lost this
        turn. (Damage causes loss of life.)" is the question this answers, and
        the reminder text is not the whole list: CR 119.2 makes damage a loss,
        CR 118.3b makes a life payment a loss, CR 701.12c makes the losing half
        of a life-total exchange a loss, and every one of them subtracts
        through `lose_life`.

        Gross rather than net - a player who loses 4 and gains 4 has still lost
        4 - and it reads as zero once the turn has moved on, without anything
        having to clear it (see `life_lost_tally_turn`)."""
        return self.life_lost_tally if self.life_lost_tally_turn == self._current_turn_stamp else 0

    # -- exchanging life totals (CR 701.12) --------------------------------

    def why_cannot_exchange_life_totals(self, other: "Player") -> str | None:
        """Why an exchange of life totals with `other` can't happen, or None.

        CR 701.12c: "When life totals are exchanged, each player gains or loses
        the amount of life necessary to equal the other player's previous life
        total." Because the exchange *is* gains and losses, the prohibitions on
        gaining and losing apply to it, and the rules say so directly:

        - CR 119.7: "If an effect says that a player can't gain life, that
          player can't make an exchange such that the player's life total would
          become higher; in that case, the exchange won't happen."
        - CR 119.8: the mirror, for a player who can't lose life and an
          exchange that would lower them.

        Only the direction each player actually moves is checked: a player who
        can't gain life may exchange downwards freely, which is the branch of
        the Screaming Nemesis episode where the exchange goes through.

        Asked of either player, about either player - CR 701.12a's "the entire
        exchange" is one event and has no near side.

        Both prohibitions are consulted for the gaining half: the one set on
        the player and the one a permanent imposes through
        `Game.life_gain_prohibited`, because CR 119.7 is written about "an
        effect", not about where this engine happens to keep it.
        """
        for player, opponent in ((self, other), (other, self)):
            if opponent.life > player.life and (
                player.cannot_gain_life or player._prohibited_from_gaining_life
            ):
                return (
                    f"{player.username} can't gain life, so the exchange that would raise "
                    f"their life total from {player.life} to {opponent.life} won't happen "
                    f"(CR 119.7)"
                )
            if opponent.life < player.life and player.cannot_lose_life:
                return (
                    f"{player.username} can't lose life, so the exchange that would lower "
                    f"their life total from {player.life} to {opponent.life} won't happen "
                    f"(CR 119.8)"
                )
        return None

    def exchange_life_totals(self, other: "Player") -> int:
        """Exchange life totals with `other`, returning the life *this* player
        lost by it (CR 701.12a, CR 701.12c).

        CR 701.12a: "When such a spell or ability resolves, if the entire
        exchange can't happen, no part of the exchange occurs." So the refusal
        is decided before anything moves - a refused exchange leaves both life
        totals alone and records neither a gain nor a loss, rather than
        applying the half that was legal. CR 701.12g says the same of an
        exchange of two numerical values where one of them is a life total.

        CR 701.12c makes the exchange itself gains and losses, so it goes
        through `gain_life` and `lose_life` and is visible to everything that
        watches them: `Game.life_gained_this_turn` for CR 119.9's triggers, and
        `life_lost_this_turn` for Children of Korlis.

        The return value is signed from this player's side because that is the
        question the cards ask - Mister Negative's "If you lost life this way,
        draw that many cards." A player who gained reports a negative loss, and
        a refused or empty exchange reports 0; `why_cannot_exchange_life_totals`
        is the one that distinguishes "refused" from "nothing to move"."""
        if other is self or self.why_cannot_exchange_life_totals(other) is not None:
            return 0

        mine, theirs = self.life, other.life
        for player, becomes in ((self, theirs), (other, mine)):
            difference = becomes - player.life
            if difference > 0:
                player.gain_life(difference)
            elif difference < 0:
                player.lose_life(-difference)
        return mine - theirs

    # -- protection (CR 702.16) --------------------------------------------

    def gain_protection_from(self, quality: str) -> None:
        """Give this player protection from `quality` (CR 702.16a).

        CR 702.16m: "Multiple instances of protection from the same quality on
        the same permanent or player are redundant", so a quality already held
        is not recorded twice - two Runed Halos naming the same card are one
        protection, and the list stays the set of qualities it reads as."""
        if quality not in self.protection_from:
            self.protection_from.append(quality)

    def lose_protection_from(self, quality: str) -> None:
        """Take a protection away again, for when the effect granting it ends.

        Silent about a quality this player never had: an effect ending is not
        an error, and nothing in CR 702.16 makes removal conditional on the
        grant having applied."""
        if quality in self.protection_from:
            self.protection_from.remove(quality)

    def has_protection_from(self, quality: str) -> bool:
        """Whether this player has protection from exactly this quality."""
        return quality in self.protection_from

    def protection_refusal(self, source: Card) -> str | None:
        """Why this player's protection stops `source` touching them, or None.

        CR 702.16b: "A permanent or player with protection can't be targeted by
        spells with the stated quality and can't be targeted by abilities from
        a source with the stated quality." CR 702.16e prevents that source's
        damage as well.

        Only the **card-name** flavour of the quality is decided here, and
        deliberately: a name is matched against the printing alone (CR 702.16a
        allows "any characteristic value or information" as a quality, and
        Runed Halo's chosen card name is exactly that), so it needs no board
        to answer, while a colour or card-type quality is matched the way
        `Game.protection_refusal` already matches one for a permanent - with
        the game's own reader, off `protection_from`. Wiring that reader to
        players is `machines/targeting.py`'s side of the work; see
        `tests/scenarios/test_player_protection.py`.

        The match is exact. A substring match would refuse every source whose
        name merely contains the chosen one."""
        for quality in self.protection_from:
            if quality == source.name:
                return (
                    f"{self.username} has protection from {quality}, so {source.name} "
                    f"cannot target them (CR 702.16b)"
                )
        return None

    # -- starting the game -------------------------------------------------

    def load_deck(
        self,
        deck: Deck,
        resolve: CardResolver,
        *,
        check_legality: bool = True,
    ) -> "Player":
        """Put a decklist into the library, and its sideboard into the sideboard.

        The library comes out in decklist order, which is not a legal starting
        state on its own: CR 103.3 has every player shuffle before the game
        begins, and `shuffle` is what does that. The sideboard is set aside
        rather than shuffled in (CR 103.2a, 400.11a).

        Every card is stamped as this player's, by `add`: CR 108.3 makes the
        owner "the player who started the game with it in their deck", and this
        is where a deck becomes a library. CR 108.3b says the same of the
        sideboard - "its owner is considered to be the player who started the
        game with it in their sideboard".

        `check_legality` is on by default and off for the scenarios that want a
        deliberately illegal pile.
        """
        if check_legality:
            deck.check_legality(resolve)

        self.zones[Zone.LIBRARY] = []
        self.zones[Zone.SIDEBOARD] = []
        for card_name in deck.mainboard_names():
            self.add(CardState(card=resolve(card_name), controller=self.username), Zone.LIBRARY)
        for card_name in deck.sideboard_names():
            self.add(CardState(card=resolve(card_name), controller=self.username), Zone.SIDEBOARD)
        if deck.companion is not None:
            # `check_legality`/`deck.problems` above already refused an
            # unfulfilled or unreadable condition when `check_legality` is on;
            # a caller that turned it off (a deliberately illegal scenario) is
            # trusted the same way it already is for mainboard/sideboard size.
            companion_state = CardState(card=resolve(deck.companion), controller=self.username)
            self.add(companion_state, Zone.SIDEBOARD)
            self.companion_id = companion_state.id
        return self

    def shuffle(self, seed: Seed) -> list[CardState]:
        """Randomise the library (CR 103.3).

        The seed is required. An unseeded shuffle makes a scenario that fails
        once and passes the next run, which is worse than no test at all.
        """
        _rng(seed).shuffle(self.library)
        self.note_library_changed()
        return self.library

    def draw_opening_hand(self) -> list[CardState]:
        """Draw a starting hand of seven (CR 103.5).

        A library too small to fill the hand does not raise: the cards that are
        there are drawn, and `tried_to_draw_from_empty_library` records the
        failed draw so the game can lose the player at the next state-based
        check (CR 104.3c).
        """
        if self.hand:
            raise ValueError(f"{self.username} already has an opening hand")

        return self.draw_up_to(self.starting_hand_size)

    def mulligan(self, seed: Seed) -> list[CardState]:
        """Take a London mulligan: hand back, shuffle, draw a fresh seven (CR 103.5).

        "To take a mulligan, a player shuffles the cards in their hand back into
        their library, draws a new hand of cards equal to their starting hand
        size, then puts a number of those cards equal to the number of times
        that player has taken a mulligan on the bottom of their library in any
        order."

        Every mulligan draws a full hand, whatever the tally so far. The cost is
        counted, not paid on the spot: `keep_hand` puts one card on the bottom
        per mulligan taken, which is the count the rule states - CR 902.5a's
        example spells the arithmetic out with a vanguard hand of nine: "If the
        player takes a mulligan three times before keeping, they draw a new hand
        of nine cards and put three of those on the bottom of their library" -
        three, not one, then two, then three. In a multiplayer game the first
        mulligan costs nothing (CR 103.5c, CR 800.6).

        A mulligan is legal only while the player's opening hand would not fall
        below zero: "A player can take mulligans until their opening hand would
        be zero cards, after which they may not take further mulligans."
        """
        if self.hand_kept:
            raise ValueError(f"{self.username} has already kept a hand")
        if not self.can_mulligan:
            raise ValueError(
                f"{self.username} cannot mulligan past a hand of nothing "
                f"({self.mulligans_taken} taken)"
            )

        for card_state in list(self.hand):
            self.move(card_state, Zone.LIBRARY)
        self.shuffle(seed)
        self.mulligans_taken += 1
        return self.draw_opening_hand()

    @property
    def can_mulligan(self) -> bool:
        """Whether taking another mulligan is legal (CR 103.5).

        "A player can take mulligans until their opening hand would be zero
        cards, after which they may not take further mulligans." Keeping now
        costs one card per counted mulligan, so the last legal mulligan is the
        one that brings that cost to the size of the drawn hand - seven in a
        two-player game, one more when CR 103.5c makes the first free.
        """
        return self.mulligans_taken < self.starting_hand_size + (
            1 if self.first_mulligan_free else 0
        )

    @property
    def cards_to_bottom(self) -> int:
        """How many cards keeping this hand costs: one per mulligan (CR 103.5).

        CR 103.5c and CR 800.6: "the first mulligan a player takes doesn't count
        toward the number of cards that player will put on the bottom of their
        library", in a multiplayer game - so a free first mulligan is not paid
        for, and the second one is the first that is.
        """
        counted = self.mulligans_taken - (1 if self.first_mulligan_free else 0)
        return min(max(counted, 0), len(self.hand))

    def keep_hand(self, bottom: list[CardState] | None = None) -> list[CardState]:
        """Keep the current hand, bottoming one card per mulligan taken (CR 103.5).

        The player chooses which cards and in what order; passing None bottoms
        the cards at the back of the hand, which keeps a scenario that does not
        care about the choice reproducible.
        """
        if self.hand_kept:
            raise ValueError(f"{self.username} has already kept a hand")

        needed = self.cards_to_bottom
        if bottom is None:
            bottom = self.hand[len(self.hand) - needed :] if needed else []
        if len(bottom) != needed:
            raise ValueError(
                f"{self.username} must put {needed} cards on the bottom, not {len(bottom)}"
            )
        for card_state in bottom:
            if card_state not in self.hand:
                raise ValueError(f"{card_state.name} is not in {self.username}'s hand")

        for card_state in bottom:
            self.move(card_state, Zone.LIBRARY)  # the bottom of the library is its end

        self.hand_kept = True
        return list(self.hand)

    # -- counters (CR 122.1) -----------------------------------------------

    def counter_count(self, kind: CounterKind) -> int:
        """How many counters of one kind this player has."""
        return self.counters[kind]

    def add_counters(self, kind: CounterKind, amount: int = 1) -> int:
        """Give this player counters, returning the new count (CR 122.1)."""
        return self.counters.add(kind, amount)

    def remove_counters(self, kind: CounterKind, amount: int = 1) -> int:
        """Take counters off this player. Raises if there are too few (CR 118.3)."""
        return self.counters.remove(kind, amount)

    @property
    def poison(self) -> int:
        """Poison counters on this player (CR 122.1f)."""
        return self.counters[Counter.POISON]

    @property
    def is_poisoned(self) -> bool:
        """CR 122.1f: "a player is 'poisoned' if they have one or more poison counters"."""
        return self.poison > 0

    @property
    def loses_to_poison(self) -> bool:
        """CR 704.5c: "if a player has ten or more poison counters, that player loses".

        A state-based action, so the game applies it (CR 104.3d). This is only
        where the threshold lives. Two-Headed Giant sets its own number
        (CR 704.6b, CR 810.8d) and is not modelled.
        """
        return self.poison >= POISON_TO_LOSE

    @property
    def energy(self) -> int:
        """Energy counters, which is what `{E}` is paid with (CR 107.14)."""
        return self.counters[Counter.ENERGY]

    @property
    def experience(self) -> int:
        """Experience counters on this player (CR 122.1)."""
        return self.counters[Counter.EXPERIENCE]

    def untap_all(self, permanents: list[CardState]) -> None:
        """Untap the permanents this player controls. Used by the untap step.

        The battlefield is shared, so the caller passes in the permanents this
        player controls rather than reading them off the player.
        """
        for card_state in permanents:
            card_state.untap()
