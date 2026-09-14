"""A match: a sequence of games between the same players.

Starting a game is CR 103, in order: decide who takes the first turn (103.1),
set sideboards aside (103.2a), shuffle (103.3), set life totals (103.4), and
draw opening hands (103.5). `start_game` deals the hands and then leaves the
game *resting* in `Step.MULLIGAN`, the first of the two pregame steps that model
CR 103.5's mulligan process and CR 103.6's opening-hand actions. Neither is a
CR 500 step of a turn - see `machines/turn.py`'s module docstring, which sets
out what the representation does and does not claim.

The game is progressed through them seat by seat, through `Game`:
`Game.declare_mulligan` for CR 103.5's declaration and
`Game.take_opening_hand_action` / `Game.finish_opening_hand_actions` for
CR 103.6's actions. Nothing there asks anybody anything, so nothing there waits.
`run_mulligans` here is the headless shortcut over the same machinery: it walks
the whole pregame through the ordinary decision defaults in one call, which is
what every unattended game and every scenario wants.
"""

from random import Random

from pydantic import Field

from ..snapshot import EngineModel
from .deck import CardResolver, Deck
from .game import Game
from .player import Player

_CARD_RESOLVERS: dict[str, CardResolver] = {}
"""Resolvers registered by name, for `Match.bind_card_resolver` to find again.

A `CardResolver` (`deck.CardResolver = Callable[[str], Card]`) is a plain
callable, which is exactly what `Match.card_resolver` being `exclude=True`
already says pydantic has nothing to serialize it into: a `Match` rebuilt
from a `model_dump` never had one to begin with, and CR 103.5 needs a real
one to deal an opening hand. Naming a resolver here, once, wherever it is
defined, is what lets `Match.card_resolver_name` - a plain string, and
therefore the one part of "how a decklist name becomes a printing" that
*does* survive the round trip - stand in for the callable until
`bind_card_resolver` puts it back.
"""


def register_card_resolver(name: str, resolver: CardResolver) -> None:
    """Register `resolver` under `name` for `Match.bind_card_resolver` to use.

    Re-registering the same name replaces the resolver rather than refusing,
    since a resolver is usually a thin wrapper over a card pool that can
    itself change between runs (a refreshed fixture pool, a different
    Scryfall snapshot) while the name a `Match` was serialised with should
    not have to.
    """
    _CARD_RESOLVERS[name] = resolver


class Match(EngineModel):
    """A best-of-N series. Constructed play is best of three.

    Sideboarding between games is why `Player.sideboard` exists, though nothing
    here enforces that the deck returns to its registered list afterwards.

    Setting the sideboard aside (CR 103.2a) is what puts it *outside the game*
    (CR 400.11a), which is the state Karn, the Great Creator's `−2` reaches
    into. CR 400.11b bounds how long a card brought in that way stays: "Those
    cards remain in the game until the game ends, their owner leaves the game,
    or a rule or effect removes them from the game, whichever comes first." The
    game ending is the bound that applies here, and `_fresh` is what honours it
    - every game of a match starts from players with empty zones and reloads
    the registered decklist, so a card fetched out of the sideboard in game one
    is back in the sideboard for game two with no special case, and the
    registered `Deck` - which is what `check_legality` counts (CR 100.2a,
    CR 100.4a) - was never touched by the fetch at all.
    """

    players: list[Player] = Field(min_length=2)
    best_of: int = 3
    games: list[Game] = Field(default_factory=list)

    decks: dict[str, Deck] = Field(default_factory=dict)
    """Registered decklists, by username. A player without one starts with empty zones."""

    card_resolver: CardResolver | None = Field(default=None, exclude=True, repr=False)
    """How a decklist name becomes a printing. Required to deal a real opening hand.

    Excluded from serialization: a plain callable is not something pydantic
    can write down, so a `Match` rebuilt from a `model_dump`/`model_validate`
    round trip never has one, even when the one it started with is still
    registered under `card_resolver_name`. Call `bind_card_resolver` on a
    decoded `Match` to put it back before `start_game` needs it.
    """

    card_resolver_name: str | None = Field(default=None)
    """The name `card_resolver` was registered under (`register_card_resolver`).

    The one part of "how a decklist name becomes a printing" that a
    `model_dump`/`model_validate` round trip does not throw away, because it
    is a plain string rather than the callable itself. `bind_card_resolver`
    reads it back after a decode to re-inject `card_resolver`.
    """

    seed: int | str = 0
    """Base seed for every shuffle in the match.

    Deliberately not None: an unseeded shuffle makes a game that cannot be
    replayed, and a scenario test that cannot be trusted. Each player's shuffle
    in each game derives its own seed from this one, so two players never get
    the same permutation.
    """

    random_first_player: bool = False
    """Whether game one picks a starting player at random (CR 103.1).

    Off by default, which makes seat order the "mutually agreeable method" the
    rule allows and keeps a scenario reading the same way every run. Turn it on
    and the choice is still reproducible, because it comes off `seed`.
    """

    first_players: list[str] = Field(default_factory=list)
    """Who took the first turn of each game, in order."""

    choosers: list[str | None] = Field(default_factory=list)
    """Who chose the starting player for each game. None means nobody had the choice."""

    @property
    def wins_needed(self) -> int:
        """Games one player must take to win the match."""
        return self.best_of // 2 + 1

    @property
    def usernames(self) -> list[str]:
        return [player.username for player in self.players]

    @property
    def draws(self) -> int:
        """Games that ended in a draw (CR 104.4a).

        A drawn game is finished - `Game.is_over` covers it - but it is a win
        for neither player, so it counts here and in neither column of `score`.
        Read off the games rather than stored: a match has no hook into the
        moment a game ends, and a stored counter would go stale. The CR leaves
        what a draw does to a match's result to the Tournament Rules (CR 100.6);
        this model only counts the games.
        """
        return sum(1 for game in self.finished_games if game.drawn)

    @property
    def finished_games(self) -> list[Game]:
        return [game for game in self.games if game.is_over]

    @property
    def current_game(self) -> Game | None:
        """The game in progress, if there is one."""
        return next((game for game in self.games if not game.is_over), None)

    @property
    def score(self) -> dict[str, int]:
        """Games won, per player. Everyone who has not won a game scores zero.

        A drawn game (CR 104.4a) is finished but won by nobody, so it lands in
        `draws` and in neither column here. `wins_needed` therefore counts
        *wins*, and a drawn game uses up a game of `best_of` without moving
        either player closer to theirs.
        """
        tally = dict.fromkeys(self.usernames, 0)
        for game in self.finished_games:
            if game.winner in tally:
                tally[game.winner] += 1
        return tally

    @property
    def winner(self) -> str | None:
        """Whoever has taken enough games, or None while the match is live."""
        for username, wins in self.score.items():
            if wins >= self.wins_needed:
                return username
        return None

    @property
    def is_over(self) -> bool:
        """Won outright, or out of games to play.

        Draws make the second case reachable with no winner at all: a best of
        three split 1-1-1 is over because `best_of` games happened, not because
        anybody won it. How a drawn match scores is a Tournament Rules matter
        (CR 100.6), not a Comprehensive Rules one, so `winner` just stays None.
        """
        return self.winner is not None or len(self.games) >= self.best_of

    # -- card resolver -------------------------------------------------------

    def bind_card_resolver(self, name: str | None = None) -> None:
        """Put `card_resolver` back after a decode (CR 103.5 needs one to deal).

        `card_resolver` cannot survive `model_dump`/`model_validate` - it is a
        plain callable, `exclude=True` for exactly that reason - so a `Match`
        rebuilt from a dict has only `card_resolver_name`, a plain string,
        left to go on. This looks that name up in `register_card_resolver`'s
        registry and puts the callable back, which is what lets a decoded
        `Match` load a deck and deal an opening hand at all.

        `name` overrides `card_resolver_name` rather than requiring the field
        be set first, so a caller re-homing a decoded `Match` onto a resolver
        registered under a different name than the one it shipped with still
        has a way in - and, when given, it is also stored back onto
        `card_resolver_name`, so the `Match` now names the resolver it is
        actually carrying.
        """
        resolver_name = name if name is not None else self.card_resolver_name
        if resolver_name is None:
            raise ValueError(
                "no card_resolver_name to bind - pass name= or set "
                "card_resolver_name before calling bind_card_resolver"
            )
        try:
            resolver = _CARD_RESOLVERS[resolver_name]
        except KeyError:
            raise KeyError(
                f"{resolver_name!r} is not a registered card resolver. "
                f"Registered: {', '.join(sorted(_CARD_RESOLVERS)) or '(none)'}. "
                "Call register_card_resolver(name, resolver) first."
            ) from None
        self.card_resolver = resolver
        self.card_resolver_name = resolver_name

    # -- decks -------------------------------------------------------------

    def register_deck(self, username: str, deck: Deck, *, check_legality: bool = True) -> Deck:
        """Register a player's decklist for the match.

        Checked against the format's construction rules here rather than at
        `start_game`, so an illegal list is a deck registration problem and not
        a mid-match surprise.
        """
        if username not in self.usernames:
            raise KeyError(f"no player named {username}")
        if check_legality:
            if self.card_resolver is None:
                raise ValueError("a match needs a card_resolver to check a deck's legality")
            deck.check_legality(self.card_resolver)
        self.decks[username] = deck
        return deck

    # -- who goes first (CR 103.1) -----------------------------------------

    def chooser_for_next_game(self) -> str | None:
        """Who decides who takes the first turn of the next game (CR 103.1).

        In the first game of a match nobody has the choice by right, so this is
        None and the players use any mutually agreeable method. Afterwards the
        loser of the previous game chooses. A game with no single loser - a
        draw, or more than two players - hands the choice back to whoever chose
        last time.
        """
        if not self.finished_games:
            return None

        previous = self.games[-1]
        losers = [username for username in self.usernames if username != previous.winner]
        if len(losers) == 1:
            return losers[0]
        return self.choosers[-1] if self.choosers else None

    def _first_player(self, on_the_play: str | None, chooser: str | None) -> str:
        if on_the_play is not None:
            if on_the_play not in self.usernames:
                raise KeyError(f"no player named {on_the_play}")
            return on_the_play
        if chooser is not None:
            # The choice is the chooser's; playing first is the choice they make.
            return chooser
        if self.random_first_player:
            return Random(self._game_seed("first-player")).choice(self.usernames)  # noqa: S311
        return self.usernames[0]

    # -- starting a game (CR 103) ------------------------------------------

    def _game_seed(self, tag: str) -> str:
        """A seed of its own for each shuffle, derived from the match seed."""
        return f"{self.seed}:{len(self.games)}:{tag}"

    def start_game(
        self,
        *,
        on_the_play: str | None = None,
        deal_opening_hands: bool = True,
    ) -> Game:
        """Begin the next game of the match, dealt and shuffled (CR 103).

        Players who have a registered deck get it loaded, shuffled, and dealt
        into a seven-card opening hand; players who do not start with empty
        zones, which is what an unconfigured scenario wants. The game's player
        order puts whoever takes the first turn first.

        Mulligans are not taken here. The hands are dealt and the game is left
        resting in `Step.MULLIGAN`, before CR 103.8's first turn: every seat
        declares through `Game.declare_mulligan`, and a caller with nobody live
        to ask calls `run_mulligans` to settle the whole pregame at once.
        """
        if self.winner is not None:
            raise ValueError(f"{self.winner} has already won the match")
        if self.current_game is not None:
            raise ValueError("the previous game is still in progress")
        if len(self.games) >= self.best_of:
            raise ValueError(f"a best of {self.best_of} cannot run a game {len(self.games) + 1}")

        chooser = self.chooser_for_next_game()
        first_player = self._first_player(on_the_play, chooser)

        fresh = [_fresh(player) for player in self.players]
        fresh.sort(key=lambda player: player.username != first_player)

        for player in fresh:
            deck = self.decks.get(player.username)
            if deck is None:
                continue
            if self.card_resolver is None:
                raise ValueError("a match needs a card_resolver to load a deck")
            # CR 103.2a: the sideboard is set aside before the deck is shuffled.
            player.load_deck(deck, self.card_resolver, check_legality=False)
            player.shuffle(self._game_seed(f"shuffle:{player.username}"))
            if deal_opening_hands:
                player.draw_opening_hand()

        game = Game(players=fresh, schema_version=Game.CURRENT_SCHEMA_VERSION)
        self.games.append(game)
        self.first_players.append(first_player)
        self.choosers.append(chooser)

        if len(game.players) > 2:
            # CR 800.1 makes that a multiplayer game; CR 103.5c and CR 800.6
            # make the first mulligan free in one. Set before the game rests in
            # the mulligan step, because `can_mulligan` reads it from the first
            # declaration onwards.
            for player in game.players:
                player.first_mulligan_free = True

        # The pregame seed prefix is `_game_seed`'s, evaluated here - after the
        # append, exactly as it was when `run_mulligans` derived it on its own -
        # so every seeded replay of a mulligan produces the shuffle it always did.
        game.begin_pregame(f"{self.seed}:{len(self.games)}")
        return game

    def run_mulligans(self, game: Game | None = None) -> Game:
        """Settle a game's whole pregame with nobody live to ask (CR 103.5, CR 103.6).

        Defaults to the most recent game this match started. The process itself
        lives on `Game` now, as two steps the game rests in - `Step.MULLIGAN` and
        `Step.PREGAME_ACTIONS` - and this is the headless driver over it:
        `Game.settle_pregame` puts each declaration through `ask_mulligan` and
        each CR 103.6 action through `Game.ask`, so a scripted answer wins, then
        the replay tape, and only when neither speaks does the documented
        default stand - keep the dealt hand, bottom from the back of it,
        decline every opening-hand action.

        That preserves both halves of what this method meant before:

        - **the rules order.** CR 103.5: "First, the starting player declares
          whether they will take a mulligan. Then each other player in turn order
          does the same. Once each player has made a declaration, all players who
          decided to take mulligans do so at the same time." Every declaration of
          a round is collected before any mulligan is taken, in the game's player
          order, which puts whoever takes the first turn first. A player at
          CR 103.5's ceiling - "a player can take mulligans until their opening
          hand would be zero cards, after which they may not take further
          mulligans" - is offered no declaration at all. CR 103.6's actions
          follow, because they begin "once the mulligan process (see rule 103.5)
          is complete"; `Match.start_game` set CR 103.5c and CR 800.6's free
          first mulligan for a multiplayer game before any of it began.
        - **the seeded replay.** Each mulligan reshuffles off a seed derived from
          the match seed, and the string is the one this method used to build
          itself - `start_game` hands `Game.pregame_seed` the same prefix.

        Returns the game, settled: hands kept, opening-hand actions done, and the
        turn pointer on `Step.UNTAP` of CR 103.8's first turn.

        A caller with live seats does **not** use this. It leaves the game in the
        pregame steps and lets each seat act through `Game.declare_mulligan` and
        `Game.take_opening_hand_action` / `Game.finish_opening_hand_actions`,
        none of which asks anybody anything and none of which waits.
        """
        if game is None:
            if not self.games:
                raise ValueError("no game has been started to run mulligans for")
            game = self.games[-1]
        elif not any(past is game for past in self.games):
            raise ValueError("that game is not one this match started")

        game.settle_pregame()
        return game


def _fresh(player: Player) -> Player:
    """A copy of the player with empty zones, ready for the next game."""
    return Player(username=player.username, life=20)
