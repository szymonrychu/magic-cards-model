"""A match: a sequence of games between the same players.

Starting a game is CR 103, in order: decide who takes the first turn (103.1),
set sideboards aside (103.2a), shuffle (103.3), set life totals (103.4), and
draw opening hands (103.5). The hands are dealt by `start_game` and settled by
`run_mulligans`, which runs the London mulligan of CR 103.5 to completion.
"""

from random import Random

from pydantic import BaseModel, Field

from ..machines.decisions import ask_mulligan
from .deck import CardResolver, Deck
from .game import Game
from .player import Player


class Match(BaseModel):
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
    """How a decklist name becomes a printing. Required to deal a real opening hand."""

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

        Mulligans are not taken here: the hands are dealt and `run_mulligans`
        settles them, which is CR 103.5's own sequence.
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

        game = Game(players=fresh)
        self.games.append(game)
        self.first_players.append(first_player)
        self.choosers.append(chooser)
        return game

    def run_mulligans(self, game: Game | None = None) -> Game:
        """Settle every opening hand of a game through the London mulligan (CR 103.5).

        Defaults to the most recent game this match started. Every round asks
        each player still deciding whether they will take a mulligan, then
        repeats "until no player takes a mulligan" (CR 103.5).

        CR 103.5, in the order the rule states it: "First, the starting player
        declares whether they will take a mulligan. Then each other player in
        turn order does the same. Once each player has made a declaration, all
        players who decided to take mulligans do so at the same time." So each
        round collects every declaration before any mulligan is taken, walking
        the game's player list - which puts whoever takes the first turn first,
        which is that order. A player who declares against "may not take any
        further mulligans": their opening hand is "the remaining cards" of the
        hand they hold, `keep_hand` pays their bottoming cost, and later rounds
        do not ask them again. A player at CR 103.5's ceiling - "a player can
        take mulligans until their opening hand would be zero cards, after
        which they may not take further mulligans" - is offered no declaration
        at all; keeping a hand of nothing is what is left to them.

        In a multiplayer game - one that begins with more than two players (CR
        800.1) - CR 103.5c and CR 800.6 make each player's first mulligan free:
        it counts neither toward the cards they put on the bottom nor toward
        how many mulligans they may take.

        Each mulligan shuffles that player's library seeded off the match seed,
        like the opening shuffle of CR 103.3, so a match with the same seed and
        the same declarations replays identically. CR 103.6's opening-hand
        actions are a separate sequence that begins once this process is
        complete, and are not modelled.
        """
        if game is None:
            if not self.games:
                raise ValueError("no game has been started to run mulligans for")
            game = self.games[-1]
        elif not any(past is game for past in self.games):
            raise ValueError("that game is not one this match started")

        if len(game.players) > 2:
            # CR 800.1 makes that a multiplayer game; CR 103.5c and CR 800.6
            # make the first mulligan free in one.
            for player in game.players:
                player.first_mulligan_free = True

        while True:
            deciding = [player for player in game.players if not player.hand_kept]
            if not deciding:
                break

            declarations: list[tuple[Player, bool]] = []
            for player in deciding:
                # CR 103.5 puts the declaration in turn order, starting player
                # first - which is the game's player list order. A player at
                # the zero-hand ceiling is not offered a choice (CR 103.5).
                wants = (
                    ask_mulligan(game.decisions, player.username) if player.can_mulligan else False
                )
                declarations.append((player, wants))

            if not any(wants for _, wants in declarations):
                for player, _ in declarations:
                    player.keep_hand()
                break

            # "all players who decided to take mulligans do so at the same
            # time": every declaration above is in before any mulligan is taken.
            for player, wants in declarations:
                if wants:
                    player.mulligan(
                        self._game_seed(f"mulligan:{player.username}:{player.mulligans_taken}")
                    )
            for player, wants in declarations:
                if not wants:
                    player.keep_hand()

        return game


def _fresh(player: Player) -> Player:
    """A copy of the player with empty zones, ready for the next game."""
    return Player(username=player.username, life=20)
