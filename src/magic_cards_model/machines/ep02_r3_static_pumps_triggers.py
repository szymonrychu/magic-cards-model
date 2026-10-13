"""EP-02 R3 T1: the non-static clauses of the static-for-each-pump cards (triggers).

Each rung reads an amount the static readers already know (`ep02_r3_static_pumps`
counts) or a plain game count, at the moment the instruction is applied
(CR 608.2h):

- "draw a card for each Aura you control that's attached to a creature" (Sage's
  Reverie): a board count, CR 303.4 / CR 301.5 attachment, read after the Aura
  entered (so it counts itself, CR 303.4f).
- "create a number of <token> tokens equal to the number of opponents you have"
  (Silverwing Squadron): CR 102.2 / CR 102.3 opponents; a player who has left
  the game is no longer an opponent (CR 800.4a).
"""

import re
from typing import TYPE_CHECKING, Any

from .effects._chains import FORWARD, MIXED_CLAUSE

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game


def board_count_now(game: "Game", source: "CardState", phrase: str) -> int | None:
    """The number `phrase` ("Aura you control that's attached to a creature")
    counts on the board right now, asked from `source`'s point of view, or
    `None` when the static count reader does not know the phrase."""
    from .effects.continuous import layer_context_for
    from .ep02_r3_static_pumps import count_for

    context = layer_context_for(game, game.player(source.controller))
    count = count_for(phrase, source, context)
    if count is None:
        return None
    board = game.computed_board()
    return count(board.of(source), board.characteristics)


_DRAW_FOR_EACH_RE = re.compile(
    r"^draw a card for each (?P<each>(?:[a-z-]+ )*aura you control that's attached to a creature)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_draw_for_each_board_count(text: str, *, for_spell: bool) -> Any:
    """ "Draw a card for each `<permanent description>`" over a board count
    the static readers know (CR 121.1: draw one card that many times)."""
    match = _DRAW_FOR_EACH_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    each = match["each"].lower()

    def effect(game: "Game", stack_object: Any) -> None:
        source = stack_object.source_or_last_known(game)
        if source is None:
            return
        amount = board_count_now(game, source, each)
        if amount:
            game.draw_cards(game.controller_of(stack_object), amount)

    return effect


_TOKENS_PER_OPPONENT_RE = re.compile(
    r"^create a number of (?P<desc>.+?) tokens(?P<tail> with .+?)? equal to the number of opponents you have\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_tokens_per_opponent(text: str, *, for_spell: bool) -> Any:
    """ "Create a number of `<token>` tokens equal to the number of opponents
    you have" (CR 102.2, CR 111.2)."""
    match = _TOKENS_PER_OPPONENT_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    from .effects.tokens import _token_creator_for_count

    create = _token_creator_for_count(match["desc"], match["tail"] or "")
    if create is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        controller = game.controller_of(stack_object).username
        opponents = [p for p in game.players_in_game if p.username != controller]
        create(game, stack_object, len(opponents))

    return effect
