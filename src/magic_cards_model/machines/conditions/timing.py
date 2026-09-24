"""Timing conditions: whose turn it is, which phase or step, who is defending.

Every answer is read off the turn machine (`Game.turn`) as it stands when the
condition is asked - CR 603.4 as the trigger event occurs, CR 608.2a again as
the ability resolves - except "you cast it during your main phase", which is a
fact about the cast and is read off its `CastRecord`.

Rules verified with `mise run rules:find`:

- CR 109.5: "you" is the controller of the object, the player who activated
  the ability, or the controller of the source when a triggered ability
  triggered.
- CR 505.1: "The precombat and postcombat main phases are individually and
  collectively known as the main phase."
- CR 506.1: the combat phase's five steps; a turn may have more than one
  combat phase (CR 500.8's additional phases), so "the first combat phase of
  the turn" is counted, not assumed (`Game.turn_count("combat_phases", ...)`).
- CR 506.2: "During the combat phase of a two-player game, the nonactive
  player is the defending player"; CR 508.5's defending player of one attack
  is the player attacked or the controller of the planeswalker attacked.
"""

import re
from typing import TYPE_CHECKING

from . import ConditionReader

if TYPE_CHECKING:
    from . import ConditionContext


def _turn(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it's [not] your turn" / "it's not their turn" / "it's [not] an
    opponent's turn". "Their" is the player the trigger event names - the
    caster of Scytheclaw Raptor's "Whenever a player casts a spell, if it's
    not their turn" - so without an event there is nobody to ask about."""
    turn = context.game.turn
    if turn is None or turn.in_pregame:
        return False
    whose = match.group("whose")
    if whose == "their":
        player = context.event.player if context.event is not None else None
        if player is None:
            return False
        holds = turn.active_player == player
    elif whose == "your":
        holds = turn.active_player == context.controller
    else:  # an opponent's
        holds = turn.active_player != context.controller
    return holds != bool(match.group("negated"))


def _main_phase(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it's your [precombat|postcombat] main phase" (CR 505.1)."""
    from ..turn import MAIN_PHASES, Step

    turn = context.game.turn
    if turn is None or turn.active_player != context.controller:
        return False
    which = match.group("which")
    if which == "precombat":
        holds = turn.step is Step.PRECOMBAT_MAIN
    elif which == "postcombat":
        holds = turn.step is Step.POSTCOMBAT_MAIN
    else:
        holds = turn.step in MAIN_PHASES
    return holds != bool(match.group("negated"))


def _first_combat_phase(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it's the first combat phase of the turn" (CR 506.1, CR 500.8): a combat
    phase is in progress and no other has begun before it this turn. A combat
    entered without its beginning being counted (a staged board) is the first."""
    from ..turn import Phase

    turn = context.game.turn
    if turn is None or turn.phase is not Phase.COMBAT:
        return False
    return context.game.turn_count("combat_phases", turn.active_player) <= 1


def _defending_player(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you're the defending player" (CR 506.2, CR 508.5). An attack event
    names its own defending player; otherwise any attack in the current combat
    against the player (or a planeswalker or battle they control) makes them
    one."""
    from ..combat import defending_player

    game = context.game
    you = context.controller
    event = context.event
    if event is not None and event.defender_controller is not None:
        holds = event.defender_controller == you
    elif event is not None and event.defender is not None:
        holds = defending_player(game, event.defender) == you
    else:
        holds = any(
            defending_player(game, attack.defender) == you for attack in game.combat.attacks
        )
    return holds != bool(match.group("negated"))


def _cast_during_main_phase(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you cast it during your main phase" - Sentinel's Mark's addendum shape
    (CR 505.1). A fact about the cast, not about now: the `CastRecord` notes
    the step and the active player as the spell was cast (CR 601.2i), and a
    permanent that was never cast has no record, so the answer is False."""
    from ..abilities import TriggeredAbility
    from ..turn import MAIN_PHASES

    record = None
    source = context.source
    if isinstance(context.ability, TriggeredAbility) and source is not None:
        from ..triggers import _cast_record_for_clause

        record = _cast_record_for_clause(
            context.game, context.ability, source, context.event, context.source_stamp
        )
    elif source is not None:
        record = context.game.cast_record_of(source)
    if record is None or record.cast_step is None:
        return False
    return record.cast_step in MAIN_PHASES and record.cast_during_turn_of == context.controller


READERS: tuple[ConditionReader, ...] = (
    ConditionReader(
        re.compile(r"it(?:'s| is) (?P<negated>not )?(?P<whose>your|their|an opponent's) turn"),
        _turn,
    ),
    ConditionReader(
        re.compile(
            r"it(?:'s| is) (?P<negated>not )?your (?:(?P<which>precombat|postcombat) )?"
            r"main phase"
        ),
        _main_phase,
    ),
    ConditionReader(
        re.compile(r"it(?:'s| is) the first combat phase of the turn"),
        _first_combat_phase,
    ),
    ConditionReader(
        re.compile(r"you(?:'re| are) (?P<negated>not )?the defending player"),
        _defending_player,
    ),
    ConditionReader(
        re.compile(r"you cast (?:it|him|her|them|this (?:spell|[a-z]+)) during your main phase"),
        _cast_during_main_phase,
    ),
)
