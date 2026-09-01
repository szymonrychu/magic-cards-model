"""Priority, as a state machine (CR 117).

One player holds priority at a time. Passing moves it to the next player. When
every player passes in succession, what happens depends on the stack: the top
item resolves, or, if the stack is empty, the step or phase ends (CR 117.4).

Casting a spell or activating an ability resets the count, and the player who
did it keeps priority (CR 117.3c).

Not every step hands priority out. CR 502.4: "No player receives priority during
the untap step, so no spells can be cast or resolve and no abilities can be
activated or resolve." CR 514.3 says the same of the cleanup step, "normally",
with CR 514.3a's exception. While a step like that is in progress the machine is
*withheld*: `holder` is None, nobody may pass, and `Game` restores it as the next
step that does grant priority begins.
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

    withheld: str | None = None
    """Why no player has priority right now, or None if somebody does.

    CR 502.4 and CR 514.3 each name a step in which no player receives priority.
    The text stored here is the rule's own, so the refusal a pass gets back is
    the rule rather than a paraphrase. `Game` is what puts it here and what
    clears it, because the reason is a property of the step, not of CR 117.

    Deliberately not a bare bool: "nobody has priority" is always for a stated
    reason, and a caller who is refused deserves to be told which one.
    """

    @property
    def seat(self) -> str:
        """The seat priority sits at, whether or not it is being granted.

        The bookkeeping pointer. `holder` is the rules answer and is None while
        priority is withheld; this is where it resumes when it comes back, and
        is what a round of passes is counted against.
        """
        return self.players[self.holder_index]

    @property
    def holder(self) -> str | None:
        """Who has priority, or None if nobody does (CR 502.4, 514.3)."""
        return None if self.withheld is not None else self.seat

    @property
    def decider(self) -> str | None:
        """Who may act on the priority currently held (CR 723.5).

        None while priority is withheld: there is no held priority to act on.
        """
        holder = self.holder
        return None if holder is None else self.decider_for(holder)

    def withhold(self, reason: str) -> None:
        """Nobody receives priority until it is granted again (CR 502.4, 514.3).

        `reason` is quoted straight back at whoever tries to act, so it should be
        the rule's own wording.
        """
        self.withheld = reason

    def grant(self) -> None:
        """Priority is handed out again; the seat it resumes at is unchanged."""
        self.withheld = None

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
        if self.seat in self.departed:
            self._step_holder()
        self.passes = min(self.passes, len(self.seated))

    def holds_priority(self, player: str) -> bool:
        return self.holder == player

    def _step_holder(self) -> None:
        """Move priority to the next seat that is still in the game."""
        for _ in range(len(self.players)):
            self.holder_index = (self.holder_index + 1) % len(self.players)
            if self.seat not in self.departed:
                return

    def reset(self, active_index: int | None = None) -> str:
        """Give priority to the active player, as each step does (CR 117.3a).

        If the active player has left the game, the next player in turn order
        receives priority instead (CR 800.4j).

        Grants priority as well as moving it: this is the "beginning of most
        steps and phases" moment of CR 117.3a, and a step that is *not* one of
        those has `Game` withhold it again straight afterwards (CR 502.4,
        514.3). Returns the seat, which is the holder in every case but that.
        """
        if active_index is not None:
            self.active_index = active_index
        self.holder_index = self.active_index
        self.passes = 0
        self.withheld = None
        if self.seat in self.departed and self.seated:
            self._step_holder()
        return self.seat

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
        if player not in (self.seat, self.decider_for(self.seat)):
            raise ValueError(f"{player} does not have priority, {self.seat} does")

        acting_for = self.seat if player != self.seat else player
        self.holder_index = self.players.index(acting_for)
        self.passes = 0
        return self.seat

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

        Refuses everybody while priority is withheld (CR 502.4, 514.3): there is
        no priority to act on, so there is no decision for anyone to make.
        """
        if player not in self.players:
            raise KeyError(f"no player named {player}")
        if player in self.departed:
            raise ValueError(f"{player} has left the game")
        if self.withheld is not None:
            raise ValueError(self.withheld)
        if self.decider_for(self.seat) == player:
            return
        if self.seat == player:
            raise ValueError(
                f"{self.decider_for(self.seat)} is making {player}'s decisions this turn (CR 723.5)"
            )
        raise ValueError(f"{player} does not have priority, {self.seat} does")
