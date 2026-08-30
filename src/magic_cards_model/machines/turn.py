"""The turn structure as a state machine (CR 500-514).

A turn is a fixed sequence of steps, so the machine is a lookup table plus a
turn counter and an active player. Advancing past cleanup starts the next turn
and passes priority to the next player.

Two things break the plain round-the-table order, and both live here:

- **extra turns (CR 500.7)** - a queue of turns inserted directly after the
  current one, taken most-recently-created first;
- **one player controlling another (CR 723)** - a turn that belongs to one
  player but whose decisions are made by somebody else.

Emrakul, the Promised End needs both at once, which is why they are modelled
together rather than as two unrelated flags.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Phase(StrEnum):
    BEGINNING = "beginning"
    PRECOMBAT_MAIN = "precombat_main"
    COMBAT = "combat"
    POSTCOMBAT_MAIN = "postcombat_main"
    ENDING = "ending"


class Step(StrEnum):
    # Beginning phase
    UNTAP = "untap"
    UPKEEP = "upkeep"
    DRAW = "draw"

    # Main phases have no steps; they are modelled as a step of the same name
    PRECOMBAT_MAIN = "precombat_main"

    # Combat phase
    BEGINNING_OF_COMBAT = "beginning_of_combat"
    DECLARE_ATTACKERS = "declare_attackers"
    DECLARE_BLOCKERS = "declare_blockers"
    COMBAT_DAMAGE = "combat_damage"
    END_OF_COMBAT = "end_of_combat"

    POSTCOMBAT_MAIN = "postcombat_main"

    # Ending phase
    END_STEP = "end_step"
    CLEANUP = "cleanup"


TURN_ORDER: tuple[Step, ...] = (
    Step.UNTAP,
    Step.UPKEEP,
    Step.DRAW,
    Step.PRECOMBAT_MAIN,
    Step.BEGINNING_OF_COMBAT,
    Step.DECLARE_ATTACKERS,
    Step.DECLARE_BLOCKERS,
    Step.COMBAT_DAMAGE,
    Step.END_OF_COMBAT,
    Step.POSTCOMBAT_MAIN,
    Step.END_STEP,
    Step.CLEANUP,
)

PHASE_OF: dict[Step, Phase] = {
    Step.UNTAP: Phase.BEGINNING,
    Step.UPKEEP: Phase.BEGINNING,
    Step.DRAW: Phase.BEGINNING,
    Step.PRECOMBAT_MAIN: Phase.PRECOMBAT_MAIN,
    Step.BEGINNING_OF_COMBAT: Phase.COMBAT,
    Step.DECLARE_ATTACKERS: Phase.COMBAT,
    Step.DECLARE_BLOCKERS: Phase.COMBAT,
    Step.COMBAT_DAMAGE: Phase.COMBAT,
    Step.END_OF_COMBAT: Phase.COMBAT,
    Step.POSTCOMBAT_MAIN: Phase.POSTCOMBAT_MAIN,
    Step.END_STEP: Phase.ENDING,
    Step.CLEANUP: Phase.ENDING,
}

MAIN_PHASES = frozenset({Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN})

#: Nobody receives priority in these steps unless something triggers (CR 502.1, 514.3).
NO_PRIORITY = frozenset({Step.UNTAP, Step.CLEANUP})


class TurnMachine(BaseModel):
    """Where a game is in the turn sequence."""

    players: list[str] = Field(min_length=1)
    active_index: int = 0
    turn_number: int = 1
    step: Step = Step.UNTAP

    departed: list[str] = Field(default_factory=list)
    """Players who have left the game (CR 104.5, 800.4).

    They keep their seat in `players`, because turn order is seating order and
    the remaining players do not shuffle up; they are simply skipped when the
    turn passes.
    """

    turns_taken: int = 1
    """How many turns have begun, counting extra ones (CR 500.7).

    `turn_number` counts rounds of the table and deliberately does not move for
    an extra turn, so it is not a usable "did the turn change" signal any more.
    This is: it goes up exactly once per turn that actually begins, which is
    what `Game.advance` watches to reset the land drop and the once-per-turn
    activation counts.
    """

    extra_turns: list[str] = Field(default_factory=list)
    """Extra turns waiting to be taken, in the order they were created (CR 500.7).

    "Some effects can give a player extra turns. They do this by adding the
    turns directly after the specified turn. If a player is given multiple extra
    turns, the extra turns are added one at a time. If multiple players are
    given extra turns, the extra turns are added one at a time, in APNAP order
    (see rule 101.4). The most recently created turn will be taken first."

    So this is a stack, not a queue: `begin_next_turn` pops the *end*.
    """

    taking_extra_turn: bool = False
    """Whether the turn now in progress is an extra one (CR 500.7)."""

    order_index: int | None = None
    """Where the round-the-table rotation stands, when that is not `active_index`.

    CR 500.7 *inserts* an extra turn after the current one; it does not move the
    table on. So during an extra turn the active seat and the rotation part
    company, and this is the rotation. None means they agree, which is the
    ordinary case and the starting one.
    """

    pending_player_control: dict[str, str] = Field(default_factory=dict)
    """Player-controlling effects waiting for their turn, controlled -> controller.

    CR 723.1: "Some cards allow a player to control another player during that
    player's next turn. This effect applies to the next turn that the affected
    player actually takes." CR 723.1b: "If a turn is skipped, any pending
    player-controlling effects wait until the player who would be affected
    actually takes a turn" - which is why this is keyed by the *controlled*
    player and consulted when their turn begins, rather than counted down.

    CR 723.1a: "Multiple player-controlling effects that affect the same player
    overwrite each other. The last one to be created is the one that works" -
    which is a plain dict assignment.
    """

    player_control: dict[str, str] = Field(default_factory=dict)
    """The player-controlling effect in force right now, controlled -> controller.

    CR 723.1: "The affected player is controlled during the entire turn; the
    effect doesn't end until the beginning of the next turn." So this is filled
    in as a turn begins and cleared as the *following* turn begins, never in
    between - not at cleanup, and not when the controlled player's turn ends.
    """

    @property
    def active_player(self) -> str:
        return self.players[self.active_index]

    @property
    def seated(self) -> list[str]:
        """The players still in the game, in turn order."""
        return [player for player in self.players if player not in self.departed]

    def leave(self, username: str) -> None:
        """This player has left the game, so the turn no longer passes to them.

        Their current turn is not cut short: CR 800.4j has a turn continue to
        its completion without an active player when its player leaves.

        Their extra turns go with them, and so does any player-controlling
        effect at either end of it: a player who has left makes no decisions and
        nobody makes decisions for them.
        """
        if username in self.players and username not in self.departed:
            self.departed.append(username)
        self.extra_turns = [player for player in self.extra_turns if player != username]
        self.pending_player_control = {
            controlled: controller
            for controlled, controller in self.pending_player_control.items()
            if username not in (controlled, controller)
        }
        self.player_control = {
            controlled: controller
            for controlled, controller in self.player_control.items()
            if username not in (controlled, controller)
        }

    @property
    def phase(self) -> Phase:
        return PHASE_OF[self.step]

    @property
    def grants_priority(self) -> bool:
        return self.step not in NO_PRIORITY

    @property
    def is_first_turn(self) -> bool:
        return self.turn_number == 1

    def can_cast_sorcery(self, stack_is_empty: bool, player: str) -> bool:
        """Sorcery timing: your main phase, empty stack, you have priority."""
        return (
            self.step in MAIN_PHASES
            and stack_is_empty
            and player == self.active_player
            and self.grants_priority
        )

    def skips_draw(self) -> bool:
        """Whether the active player skips this draw step (CR 103.8a).

        CR 103.8a, in full: "In a two-player game, the player who plays first
        skips the draw step (see rule 504, 'Draw Step') of their first turn."

        Three conditions, and each of them is a separate word in that sentence:

        - **two players.** CR 103.8c is explicit that "in all other multiplayer
          games, no player skips the draw step of their first turn". (The
          exception, CR 103.8b/810.6, is Two-Headed Giant, which is not
          modelled.)
        - **the player who plays first**, which is seat 0 here, since nothing
          models a play/draw choice yet.
        - **their first turn** - not the game's first turn. `turn_number` is a
          count of rounds of the table and CR 500.7 leaves it alone for an extra
          turn, so a first-turn extra turn would still read as turn 1 and skip a
          second draw. `turns_taken` is the count that goes up once per turn
          that actually begins, so the skip is spent after exactly one turn.
        """
        return (
            len(self.players) == 2
            and self.turns_taken == 1
            and self.is_first_turn
            and self.active_index == 0
        )

    def advance(self) -> Step:
        """Move to the next step, rolling into the next player's turn after cleanup."""
        index = TURN_ORDER.index(self.step)
        if index + 1 < len(TURN_ORDER):
            self.step = TURN_ORDER[index + 1]
        else:
            self.begin_next_turn()
        return self.step

    def begin_next_turn(self) -> None:
        """Pass the turn to the next player still in the game (CR 500.1, 800.4).

        Turn order is seating order, so a player who has left is stepped over
        rather than removed. The turn number counts rounds of the table, so it
        goes up whenever the pass wraps back to the first seat - occupied or not.

        An extra turn (CR 500.7) is taken first and jumps the order entirely:
        it is inserted directly after the turn that just ended, so nothing about
        whose seat comes next changes, and `turn_number` does not move because
        no round of the table was completed.
        """
        self.step = Step.UNTAP
        self.turns_taken += 1

        rotation = self.active_index if self.order_index is None else self.order_index

        extra = self._next_extra_turn()
        if extra is not None:
            self.order_index = rotation
            self.active_index = self.players.index(extra)
            self.taking_extra_turn = True
            self._begin_player_control()
            return

        self.taking_extra_turn = False
        self.active_index = rotation
        for _ in range(len(self.players)):
            self.active_index = (self.active_index + 1) % len(self.players)
            if self.active_index == 0:
                self.turn_number += 1
            if self.active_player not in self.departed:
                break
        self.order_index = None
        self._begin_player_control()

    # -- extra turns (CR 500.7) --------------------------------------------

    def grant_extra_turn(self, username: str) -> None:
        """This player takes an extra turn after the current one (CR 500.7).

        Raises for a player who is not at the table at all. A player who has
        left the game keeps no turns: CR 800.4 steps over their seat, so their
        queued extra turns are dropped when `leave` is called.
        """
        if username not in self.players:
            raise KeyError(f"no player named {username}")
        self.extra_turns.append(username)

    def _next_extra_turn(self) -> str | None:
        """Pop the extra turn that is taken next, skipping departed players.

        CR 500.7: "The most recently created turn will be taken first", so the
        end of the list comes off first.
        """
        while self.extra_turns:
            candidate = self.extra_turns.pop()
            if candidate not in self.departed:
                return candidate
        return None

    # -- controlling another player (CR 723) -------------------------------

    def gain_control_of_player(self, controller: str, controlled: str) -> None:
        """Queue a player-controlling effect for `controlled`'s next turn (CR 723.1).

        CR 723.1a has a later effect overwrite an earlier one, which is what a
        plain assignment does. CR 723.9 allows an effect that gives a player
        control of themselves, so `controller == controlled` is legal and simply
        means they go on deciding for themselves.
        """
        for username in (controller, controlled):
            if username not in self.players:
                raise KeyError(f"no player named {username}")
        self.pending_player_control[controlled] = controller

    def _begin_player_control(self) -> None:
        """Apply and expire player-controlling effects as a turn begins (CR 723.1).

        "The affected player is controlled during the entire turn; the effect
        doesn't end until the beginning of the next turn." Both halves happen
        here, in that order: whatever was in force expires now, and a pending
        effect for the player whose turn this is takes hold for the whole turn.
        """
        self.player_control = {}
        controller = self.pending_player_control.pop(self.active_player, None)
        if controller is not None and controller not in self.departed:
            self.player_control[self.active_player] = controller

    def controller_of_player(self, username: str) -> str:
        """Who makes this player's decisions right now (CR 723.5, 723.8, 723.9).

        Themselves, unless a player-controlling effect is in force on this turn.
        CR 723.8: a player who controls another player also goes on making their
        own choices, so nothing about the controller's own entry changes.
        """
        return self.player_control.get(username, username)

    def is_controlled(self, username: str) -> bool:
        """Whether somebody else is making this player's decisions (CR 723.1)."""
        return self.controller_of_player(username) != username

    def advance_to(self, step: Step) -> Step:
        """Advance until `step` is reached. Raises if it has already passed."""
        if TURN_ORDER.index(step) < TURN_ORDER.index(self.step):
            raise ValueError(f"{step} already passed this turn, currently at {self.step}")
        while self.step is not step:
            self.advance()
        return self.step
