"""A player: their name, their zones, and the cards in them."""

from random import Random
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .card_state import CardState, Counter, CounterKind, Counters
from .deck import CardResolver, Deck
from .mana import ManaPool
from .token import move_refused
from .zone import Zone

POISON_TO_LOSE = 10
"""CR 704.5c: ten or more poison counters and the player loses the game."""

Seed = int | str | bytes | Random
"""What a shuffle takes. Never nothing: an unseeded shuffle is not reproducible."""


def _rng(seed: Seed) -> Random:
    return seed if isinstance(seed, Random) else Random(seed)  # noqa: S311 - not cryptographic


class Player(BaseModel):
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

    mana_pool: ManaPool = Field(default_factory=ManaPool)
    zones: dict[Zone, list[CardState]] = Field(
        default_factory=lambda: {
            Zone.LIBRARY: [],
            Zone.HAND: [],
            Zone.GRAVEYARD: [],
            Zone.SIDEBOARD: [],
        }
    )
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
    tried_to_draw_from_empty_library: bool = False
    """Set when a draw found no cards. The player loses the next time state-based
    actions are checked (CR 104.3c, 704.5b) - which the game does, not the player."""

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
        return self.zones.setdefault(zone, [])

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
        """
        if card_state.owner is None:
            card_state.owner = self.username
        if move_refused(card_state, zone) is not None:
            return
        card_state.move_to(zone)
        self.cards_in(zone).append(card_state)

    def move(self, card_state: CardState, to_zone: Zone) -> None:
        """Move a card between this player's zones.

        A move CR 111.8 refuses leaves the card exactly where it is - it is not
        lifted out of its current zone and then dropped, it simply does not move.
        """
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
    def cards_over_maximum_hand_size(self) -> int:
        """How many cards the cleanup step would make this player discard (CR 402.2)."""
        return max(0, len(self.hand) - self.maximum_hand_size)

    def discard_to_maximum_hand_size(
        self, chosen: list[CardState] | None = None
    ) -> list[CardState]:
        """Discard down to maximum hand size, as the cleanup step does (CR 514.1).

        CR 701.9b makes this the player's own choice, so passing None does not
        pick for them: it asks, through `Game.ask_cleanup_discard` (CR 608.2d),
        which routes to a scripted answer, then a live decision provider, and
        only then to the back of the hand - the same fallback this method used
        before that machinery existed, kept as the default so an unscripted,
        unprovided game is unaffected. A player built outside a game (no
        `self.game`) has nothing to ask, so it falls straight back to that same
        default. Returns what was discarded, which is empty when the hand was
        already small enough.
        """
        needed = self.cards_over_maximum_hand_size
        if chosen is None:
            if self.game is not None:
                chosen = self.game.ask_cleanup_discard(self, needed)
            else:
                chosen = self.hand[len(self.hand) - needed :] if needed else []
        if len(chosen) != needed:
            raise ValueError(f"{self.username} must discard {needed} cards, not {len(chosen)}")
        return [self.discard(card_state) for card_state in chosen]

    def gain_life(self, amount: int) -> int:
        """Gain life, returning the new total (CR 118.3).

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
        Pride's end step trigger never went on the stack.
        """
        if amount < 0:
            raise ValueError("cannot gain a negative amount of life")
        self.life += amount
        if self.game is not None:
            self.game.life_gained_this_turn.add(self.username)
        return self.life

    def lose_life(self, amount: int) -> int:
        """Lose life, returning the new total (CR 118.2).

        Life goes below zero freely: losing the game for being at zero or less
        is a state-based action the game checks (CR 704.5a), not something
        that happens the instant the life is lost.
        """
        if amount < 0:
            raise ValueError("cannot lose a negative amount of life")
        self.life -= amount
        return self.life

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
        return self

    def shuffle(self, seed: Seed) -> list[CardState]:
        """Randomise the library (CR 103.3).

        The seed is required. An unseeded shuffle makes a scenario that fails
        once and passes the next run, which is worse than no test at all.
        """
        _rng(seed).shuffle(self.library)
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
            self.hand.remove(card_state)
            card_state.move_to(Zone.LIBRARY)
            self.library.append(card_state)  # the bottom of the library is its end

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
