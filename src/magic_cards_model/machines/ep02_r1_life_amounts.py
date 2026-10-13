"""EP-02 R1 T1: life lost "this way" and life lost or gained "this turn" as an amount.

One mechanic: a later instruction reads the life an earlier one really took or
gave.

- `parse_life_loss_text` reads a whole resolution text of the shape
  "<who> loses <amount> life[. | , then ]<follow-up>" where the follow-up is
  absent, "you gain life equal to the (total) life lost this way", or "put N
  <kind> counters on this creature for each 1 life lost this way". The life
  that follows is what each player's life total really lost (CR 119.3 adjusts
  the total; a player whose life total can't change, Platinum Emperion's controller, loses none),
  summed over every player who lost, never a second evaluation of the first
  sentence's amount (CR 608.2c: a later instruction modifies the earlier one).
  The amount is a number, X (CR 107.3a), "N times X", or "life equal to
  <expr>" / ", where X is <expr>" for any expression `amount_expression` reads,
  plus the per-player "the life they lost this turn" (CR 608.2h: taken once per
  player, as the instruction is applied).
- `life_this_turn_count` is the shared reader for the this-turn totals:
  "the total life lost by all players this turn" and the opponents' twin.
- `parse_mill_x` reads "<who> mills X cards, where X is <expr>" (CR 701.17a).

The sentences themselves ("<who> loses <amount>", the gain and counters
follow-ups, the mill) are read by `amount_sentences`, which every amount
reader shares; this module supplies the life-lost amounts. Everything here is
a pure reader over the engine's own bookkeeping (`Player.life_lost_this_turn`,
`Game.life_gained_amount_this_turn`); no new persisted field.
"""

import functools
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.player import Player
from ..numbers import AMOUNT, halve
from .amount_sentences import (
    Amount,
    apply_life,
    apply_mill,
    controller_of,
    life_clause_amount,
    parse_life_clause,
    parse_mill_clause,
    parse_put_counters,
    put_counters_on_source,
    recipient_amount,
)
from .conditions import claims

if TYPE_CHECKING:
    from ..models.game import Game, StackObject

#: Who loses (or mills): the opponent groups, everyone, or a declared target
#: (CR 102.2 and 102.3 define "opponent"; a declared target is read off the stack object).
_WHO = frozenset(
    {"each opponent", "each other player", "each player", "target opponent", "target player"}
)

_SEPARATOR_RE = re.compile(r"\.\s+|,\s*then\s+", re.IGNORECASE)
_HALF_LOSS_RE = re.compile(
    r"^(?P<who>[a-z ]+?) loses half (?:their|his or her) life,\s*rounded (?P<direction>up|down)$",
    re.IGNORECASE,
)
_IF_CONDITION_RE = re.compile(r"^if (?P<condition>[^,]+), (?P<rest>.+)$", re.IGNORECASE)


def _condition_holds(game: "Game", stack_object: "StackObject", condition: str) -> bool:
    """`condition` read against the resolving spell or ability (CR 608.2c)."""
    from .conditions import ConditionContext, read_condition

    source = stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
    context = ConditionContext(
        game=game, controller=controller_of(game, stack_object), source=source
    )
    return bool(read_condition(context, condition))


#: The follow-up amounts: "the (total) life lost this way", "1 life lost this way".
_LOST_THIS_WAY_RE = re.compile(r"^the (?:total )?life lost this way$", re.IGNORECASE)
_PER_LIFE_LOST_RE = re.compile(r"^1 life lost this way$", re.IGNORECASE)

#: "the total life lost by all players this turn", "the total amount of life
#: your opponents lost this turn" - the totals of `Player.life_lost_this_turn`
#: (CR 119.3's loss, gross: CR 118.3b's paid life counts as lost too).
_TOTAL_LOST_BY_RE = re.compile(
    r"^the total (?:amount of )?life lost by (?P<who>all players|your opponents|each opponent) "
    r"this turn$",
    re.IGNORECASE,
)
_TOTAL_LOST_RE = re.compile(
    r"^the total (?:amount of )?life (?P<who>all players|your opponents) "
    r"(?:have |has )?lost this turn$",
    re.IGNORECASE,
)
_YOU_LOST_RE = re.compile(
    r"^the (?:amount of )?life you(?:'ve| have)? lost this turn$", re.IGNORECASE
)

#: What a parsed reader runs against: (game, stack_object).
Resolution = Callable[["Game", "StackObject"], None]


def life_this_turn_count(phrase: str) -> "Callable[[Game, str], int] | None":
    """`(game, controller) -> int` for the this-turn life totals, or `None`.

    "the total life lost by all players this turn" sums every player's
    `life_lost_this_turn` (Tainted Sigil); "... your opponents ..." sums the
    controller's opponents' (CR 102.2, 102.3); "the life you've lost this turn" is the
    controller's own. Each is read once, where the instruction is applied
    (CR 608.2h).
    """
    lowered = phrase.lower()
    if "life" not in lowered or "this turn" not in lowered:
        return None
    stripped = phrase.strip().rstrip(".")
    match = _TOTAL_LOST_BY_RE.fullmatch(stripped) or _TOTAL_LOST_RE.fullmatch(stripped)
    if match is not None:
        everyone = match.group("who").lower() == "all players"

        def total_lost(game: "Game", controller: str) -> int:
            return sum(
                player.life_lost_this_turn
                for player in game.players_in_game
                if everyone or player.username != controller
            )

        return total_lost
    if _YOU_LOST_RE.fullmatch(stripped):
        return lambda game, controller: game.player(controller).life_lost_this_turn
    return None


def _follow_up(follow: str) -> "Callable[[Game, StackObject, int], None] | None":
    """What "you gain life equal to the life lost this way" or "put N counters
    on this creature for each 1 life lost this way" does with the life lost."""
    gain = parse_life_clause(follow)
    if (
        gain is not None
        and gain.who == "you"
        and gain.gains
        and gain.kind == "equal"
        and _LOST_THIS_WAY_RE.fullmatch(gain.expr or "")
    ):
        return lambda game, stack_object, lost: (
            game.gain_life(controller_of(game, stack_object), lost) if lost > 0 else None
        )
    put = parse_put_counters(follow)
    if (
        put is not None
        and not put.x
        and (put.on_self or put.on.lower() == "it")
        and _PER_LIFE_LOST_RE.fullmatch(put.each or "")
    ):
        per_life, kind = put.n, put.kind
        return lambda game, stack_object, lost: put_counters_on_source(
            game, stack_object, kind, per_life * lost
        )
    return None


@functools.cache
def parse_life_loss_text(text: str, *, for_spell: bool) -> "Resolution | None":
    """The whole-text reader described in the module docstring, or `None`."""
    lowered = text.lower()
    if " loses " not in lowered:
        return None
    pieces = _SEPARATOR_RE.split(" ".join(text.strip().split()), maxsplit=1)
    half = _HALF_LOSS_RE.fullmatch(pieces[0].strip().rstrip("."))
    amount: Amount | None
    if half is not None and half.group("who").lower() in _WHO:
        # Blood Tribute's "loses half their life, rounded up" - CR 107.1a
        # rounds the half of the player's own life total (CR 119.1).
        who = half.group("who").lower()
        round_up = half.group("direction").lower() == "up"

        def amount(game: "Game", stack_object: object, player: Player) -> int:
            return halve(player.life, round_up=round_up)
    else:
        loss = parse_life_clause(pieces[0])
        if loss is None or loss.gains or loss.who not in _WHO or loss.kind == "for_each":
            return None
        amount = life_clause_amount(loss, spell_x=for_spell)
        if amount is None:
            return None
        who = loss.who
    follow_up = None
    condition = None
    if len(pieces) == 2:
        follow = pieces[1]
        if (conditioned := _IF_CONDITION_RE.fullmatch(follow.strip())) is not None:
            # "If this spell was kicked, you gain life equal to the life lost
            # this way." - CR 702.33d's kicked, read off the cast record.
            condition, follow = conditioned.group("condition"), conditioned.group("rest")
            if not claims(condition):
                return None
        follow_up = _follow_up(follow)
        if follow_up is None:
            return None

    def resolve(game: "Game", stack_object: "StackObject") -> None:
        lost = apply_life(game, stack_object, who, False, amount)
        if condition is not None and not _condition_holds(game, stack_object, condition):
            return
        if follow_up is not None and lost > 0:
            follow_up(game, stack_object, lost)

    return resolve


@functools.cache
def parse_mill_x(text: str) -> "Resolution | None":
    """ "<who> mills X cards, where X is <expr>" (CR 701.17a), or `None`."""
    if " mills x " not in text.lower():
        return None
    clause = parse_mill_clause(text)
    if clause is None or clause.kind != "x" or clause.who not in _WHO:
        return None
    if clause.who.startswith("target"):
        from .effects import _targets_understood

        if not _targets_understood(clause.who, allow_player_targets=True):
            return None
    amount: Amount | None = recipient_amount(clause.expr or "")
    if amount is None:
        return None
    who = clause.who

    def resolve(game: "Game", stack_object: "StackObject") -> None:
        apply_mill(game, stack_object, who, amount)

    return resolve


__all__ = ["AMOUNT", "life_this_turn_count", "parse_life_loss_text", "parse_mill_x"]
