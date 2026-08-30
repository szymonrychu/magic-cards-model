"""Priority, as a state machine (CR 117).

One player holds priority at a time. Passing moves it to the next player. When
every player passes in succession, what happens depends on the stack: the top
item resolves, or, if the stack is empty, the step or phase ends (CR 117.4).

Casting a spell or activating an ability resets the count, and the player who
did it keeps priority (CR 117.3c).
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class PriorityOutcome(StrEnum):
    """What passing priority just caused."""

    PASSED = "passed"
    """Priority moved to the next player and the game continues."""

    RESOLVE_TOP = "resolve_top"
    """Everyone passed with a non-empty stack, so the top item resolves."""

    END_STEP = "end_step"
    """Everyone passed on an empty stack, so the step or phase ends."""


class PriorityMachine(BaseModel):
    """Who holds priority, and how many players have passed in a row."""

    players: list[str] = Field(min_length=1)
    active_index: int = 0
    holder_index: int = 0
    passes: int = 0

    departed: list[str] = Field(default_factory=list)
    """Players who have left the game (CR 104.5, 800.4).

    They keep their seat, because priority passes in turn order and turn order
    is seating order, but they never receive priority and never count towards a
    round of passes.
    """

    controlled_by: dict[str, str] = Field(default_factory=dict)
    """Who is making each player's decisions, controlled -> controller (CR 723).

    A mirror of `TurnMachine.player_control`, kept in step by `Game`. Priority
    itself is untouched by a player-controlling effect: CR 723.3 says "only
    control of the player changes", and a controlled player is still the one who
    *holds* priority. What changes is who may act on it (CR 723.5), which is
    `decider`.
    """

    @property
    def holder(self) -> str:
        return self.players[self.holder_index]

    @property
    def decider(self) -> str:
        """Who may act on the priority currently held (CR 723.5)."""
        return self.decider_for(self.holder)

    def decider_for(self, player: str) -> str:
        """Who makes this player's choices - themselves, unless controlled (CR 723.5)."""
        return self.controlled_by.get(player, player)

    @property
    def active_player(self) -> str:
        return self.players[self.active_index]

    @property
    def seated(self) -> list[str]:
        """The players still in the game, in turn order."""
        return [player for player in self.players if player not in self.departed]

    def leave(self, player: str) -> None:
        """This player has left the game and is skipped from now on (CR 800.4).

        If they were holding priority, it moves on to the next player in turn
        order, which is also what CR 800.4j says happens to the active player's
        priority when they leave mid-turn.
        """
        if player not in self.players or player in self.departed:
            return
        self.departed.append(player)
        self.controlled_by = {
            controlled: controller
            for controlled, controller in self.controlled_by.items()
            if player not in (controlled, controller)
        }
        if not self.seated:
            return
        if self.holder in self.departed:
            self._step_holder()
        self.passes = min(self.passes, len(self.seated))

    def holds_priority(self, player: str) -> bool:
        return self.holder == player

    def _step_holder(self) -> None:
        """Move priority to the next seat that is still in the game."""
        for _ in range(len(self.players)):
            self.holder_index = (self.holder_index + 1) % len(self.players)
            if self.holder not in self.departed:
                return

    def reset(self, active_index: int | None = None) -> str:
        """Give priority to the active player, as each step does (CR 117.3a).

        If the active player has left the game, the next player in turn order
        receives priority instead (CR 800.4j).
        """
        if active_index is not None:
            self.active_index = active_index
        self.holder_index = self.active_index
        self.passes = 0
        if self.holder in self.departed and self.seated:
            self._step_holder()
        return self.holder

    def retain(self, player: str) -> str:
        """The player who just acted keeps priority (CR 117.3c).

        Called after casting a spell or activating an ability, since either
        resets the round of passes.

        Deliberately not gated on `require`: this is bookkeeping after the fact,
        not a decision. It may be called with the controlled player (who cast the
        spell) or with their controller (who decided to), and either way priority
        ends up with the player the object belongs to - CR 723.3 keeps the
        controlled player the one holding it.
        """
        if player not in self.players:
            raise KeyError(f"no player named {player}")
        if player in self.departed:
            raise ValueError(f"{player} has left the game")
        if player not in (self.holder, self.decider):
            raise ValueError(f"{player} does not have priority, {self.holder} does")

        acting_for = self.holder if player != self.holder else player
        self.holder_index = self.players.index(acting_for)
        self.passes = 0
        return self.holder

    def pass_priority(self, player: str, stack_is_empty: bool) -> PriorityOutcome:
        """Pass priority. Raises if `player` is not the one holding it.

        A round of passes is over once everyone *still in the game* has passed
        in succession; players who have left are not waited for (CR 800.4).
        """
        self.require(player)

        self.passes += 1
        self._step_holder()

        if self.passes < len(self.seated):
            return PriorityOutcome.PASSED

        # Everyone passed in succession.
        self.passes = 0
        self.reset()
        return PriorityOutcome.END_STEP if stack_is_empty else PriorityOutcome.RESOLVE_TOP

    def require(self, player: str) -> None:
        """Refuse a decision by anyone who cannot make the one now called for.

        Ordinarily that is whoever holds priority. While a player-controlling
        effect is in force it is their controller instead, and *only* their
        controller: CR 723.5 hands over "all choices and decisions the controlled
        player is allowed to make", which leaves the controlled player none to
        make. Passing priority is one of them.

        The priority itself does not move (CR 723.3): the controlled player is
        still the one holding it, and still the active player.
        """
        if player not in self.players:
            raise KeyError(f"no player named {player}")
        if player in self.departed:
            raise ValueError(f"{player} has left the game")
        if self.decider == player:
            return
        if self.holder == player:
            raise ValueError(f"{self.decider} is making {player}'s decisions this turn (CR 723.5)")
        raise ValueError(f"{player} does not have priority, {self.holder} does")
