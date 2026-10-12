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

Everything here is a pure reader over the engine's own bookkeeping
(`Player.life_lost_this_turn`, `Game.life_gained_amount_this_turn`); no new
persisted field. The sibling `effects` modules are imported lazily inside the
functions because they import this module at the top of their own.
"""

import functools
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.player import Player
from ..models.zone import Zone
from ..numbers import AMOUNT, COUNT, parse_count, parse_multiplier

if TYPE_CHECKING:
    from ..models.game import Game, StackObject

#: Who loses (or mills): the opponent groups, everyone, or a declared target
#: (CR 102.2 and 102.3 define "opponent"; a declared target is read off the stack object).
_WHO = r"(?P<who>each opponent|each other player|each player|target opponent|target player)"

_THIS_TURN_THEY_LOST_RE = re.compile(
    r"^(?:the )?(?:amount of )?life they(?:'ve| have)? lost this turn$", re.IGNORECASE
)
_LOSS_RE = re.compile(rf"^{_WHO} loses (?P<amount>.+?)$", re.IGNORECASE)
_LIFE_EQUAL_TO_RE = re.compile(r"^life equal to (?P<expr>.+)$", re.IGNORECASE)
_X_LIFE_RE = re.compile(
    r"^(?:(?P<mult>[a-z0-9]+ times |twice )?x) life(?:, where x is (?P<expr>.+))?$", re.IGNORECASE
)
_N_LIFE_RE = re.compile(rf"^(?P<n>{COUNT}) life$", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"\.\s+|,\s*then\s+", re.IGNORECASE)
_GAIN_PAIR_RE = re.compile(
    r"^you gain life equal to the (?:total )?life lost this way\.?$", re.IGNORECASE
)
_COUNTERS_PAIR_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on (?:this [a-z]+|it) "
    r"for each 1 life lost this way\.?$",
    re.IGNORECASE,
)

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

_MILL_RE = re.compile(
    rf"^{_WHO} mills x cards?, where x is (?P<expr>.+?)\.?$",
    re.IGNORECASE,
)

#: What a parsed reader runs against: (game, stack_object).
Resolution = Callable[["Game", "StackObject"], None]
#: One player-specific amount: (game, controller, source, x, recipient).
_Amount = Callable[["Game", str, "CardState | None", int, Player], int]


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


@functools.cache
def _amount_reader(text: str, *, spell_x: bool) -> "_Amount | None":
    """The amount of one "loses <amount>" tail, as a per-recipient reader."""
    from .effects.amounts import amount_expression

    tail = text.strip()
    if match := _LIFE_EQUAL_TO_RE.fullmatch(tail):
        return _expression_amount(match.group("expr"), amount_expression)
    if match := _X_LIFE_RE.fullmatch(tail):
        multiplier = 1
        if match.group("mult"):
            multiplier = parse_multiplier(match.group("mult").strip())
            if multiplier is None:
                return None
        if match.group("expr"):
            inner = _expression_amount(match.group("expr"), amount_expression)
            if inner is None:
                return None
            return lambda game, controller, source, x, who: (
                multiplier * inner(game, controller, source, x, who)
            )
        if not spell_x:
            return None
        return lambda _game, _controller, _source, x, _who: multiplier * x
    if match := _N_LIFE_RE.fullmatch(tail):
        fixed = parse_count(match.group("n"))
        if fixed is None:
            return None
        return lambda _game, _controller, _source, _x, _who: fixed
    return None


def _expression_amount(expr: str, amount_expression: Callable) -> "_Amount | None":
    """`expr` as a per-recipient amount: "the life they lost this turn" reads
    the recipient, anything else is `amount_expression`'s (X is the announced X)."""
    if _THIS_TURN_THEY_LOST_RE.fullmatch(expr.strip().rstrip(".")):
        return lambda _game, _controller, _source, _x, who: who.life_lost_this_turn
    reader = amount_expression(expr)
    if reader is None:
        return None
    return lambda game, controller, source, x, _who: reader(game, controller, source, x)


def _recipients(
    game: "Game", who: str, controller: str, stack_object: "StackObject"
) -> list[Player]:
    """The players an "each ..." or "target ..." subject names, in seat order."""
    who = who.lower()
    if who.startswith("target"):
        return [t for t in game.resolve_targets(stack_object) if isinstance(t, Player)]
    if who == "each player":
        return list(game.players_in_game)
    return [player for player in game.players_in_game if player.username != controller]


def _context(game: "Game", stack_object: "StackObject") -> tuple[str, "CardState | None", int]:
    """(controller username, the source permanent or spell, announced X)."""
    if isinstance(stack_object, CardState):
        return (
            game.controller_of(stack_object).username,
            stack_object,
            game.cast_record(stack_object).x_value,
        )
    return stack_object.controller, stack_object.source(game), stack_object.x_value


@functools.cache
def parse_life_loss_text(text: str, *, for_spell: bool) -> "Resolution | None":
    """The whole-text reader described in the module docstring, or `None`."""
    lowered = text.lower()
    if " loses " not in lowered:
        return None
    pieces = _SEPARATOR_RE.split(" ".join(text.strip().split()), maxsplit=1)
    loss = _LOSS_RE.fullmatch(pieces[0].strip().rstrip("."))
    if loss is None:
        return None
    amount = _amount_reader(loss.group("amount"), spell_x=for_spell)
    if amount is None:
        return None
    who = loss.group("who")

    gain = False
    counters: tuple[int, str] | None = None
    if len(pieces) == 2:
        follow = pieces[1].strip()
        if _GAIN_PAIR_RE.fullmatch(follow):
            gain = True
        elif counted := _COUNTERS_PAIR_RE.fullmatch(follow):
            per_life = parse_count(counted.group("n"))
            if per_life is None:
                return None
            counters = (per_life, counted.group("kind"))
        else:
            return None

    def resolve(game: "Game", stack_object: "StackObject") -> None:
        controller, source, x = _context(game, stack_object)
        recipients = _recipients(game, who, controller, stack_object)
        # CR 608.2h: each amount is taken once, before any loss of this
        # instruction changes the numbers it reads.
        amounts = [amount(game, controller, source, x, player) for player in recipients]
        lost = 0
        for player, count in zip(recipients, amounts, strict=True):
            if count <= 0:
                continue
            before = player.life
            game.lose_life(player, count)
            lost += max(before - player.life, 0)
        if lost <= 0:
            return
        if gain:
            game.gain_life(controller, lost)
        elif counters is not None and source is not None and source.zone is Zone.BATTLEFIELD:
            from .effects.counters import _counter_kind

            game.add_counters(source, _counter_kind(counters[1]), counters[0] * lost)

    return resolve


@functools.cache
def parse_mill_x(text: str) -> "Resolution | None":
    """ "<who> mills X cards, where X is <expr>" (CR 701.17a), or `None`."""
    if " mills x " not in text.lower():
        return None
    match = _MILL_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    from .effects.amounts import amount_expression

    reader = _expression_amount(match.group("expr"), amount_expression)
    if reader is None:
        return None
    who = match.group("who")

    def resolve(game: "Game", stack_object: "StackObject") -> None:
        from .effects.library import _mill

        controller, source, x = _context(game, stack_object)
        recipients = _recipients(game, who, controller, stack_object)
        counts = [reader(game, controller, source, x, player) for player in recipients]
        for player, count in zip(recipients, counts, strict=True):
            if count > 0:
                _mill(game, player, count)

    return resolve


__all__ = ["AMOUNT", "life_this_turn_count", "parse_life_loss_text", "parse_mill_x"]
