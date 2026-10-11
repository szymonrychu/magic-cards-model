"""EP-01 round 2, task T1: "[You may discard a card. If you do, ]exile the top
`<n>` cards of your library, then choose one of them. You may play that card
this turn." (Party Thrasher).

CR 118.12 reads the optional discard and its "if you do"; CR 701.5a is the
exile, CR 608.2d the choice among the cards just exiled ("one of them" is one
of the cards exiled by this very instruction), and CR 601.3 / CR 611.2a the
permission to play the chosen card for the rest of the turn. The cards not
chosen stay exiled with no permission.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..numbers import parse_count
from .casting import PlayAction
from .decisions import Decision, DecisionKind, source_id_of

if TYPE_CHECKING:
    from ..models.game import Game

_RE = re.compile(
    r"^(?:(?P<may>you may )discard a card\.\s*if you do, )?"
    r"exile the top (?P<n>\w+) cards? of your library, then choose one of them\.\s*"
    r"you may (?P<action>play|cast) that card this turn\.?$",
    re.IGNORECASE,
)


def parse_exile_top_choose_one_play(text: str) -> Any:
    """The whole-text effect, or None when `text` is not that shape."""
    lowered = text.lower()
    if "then choose one of them" not in lowered:
        return None
    match = _RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None
    action = PlayAction.PLAY if match.group("action").lower() == "play" else PlayAction.CAST
    optional_discard = match.group("may") is not None

    def effect(game: "Game", stack_object: Any) -> None:
        from .effects.draw_discard import _discard_cards

        player = game.controller_of(stack_object)
        name = getattr(stack_object, "source_name", None) or stack_object.name
        sid = source_id_of(stack_object)
        if optional_discard:
            ask = Decision(
                kind=DecisionKind.MAY,
                player=player.username,
                prompt="discard a card",
                source=name,
                affirmative_is_legal=bool(player.hand),
                source_id=sid,
            )
            if not game.ask(ask):
                return
            if not _discard_cards(game, player, 1, name, source_id=sid, exact=True):
                return
        exiled = [game.exile_permanent(card) for card in list(player.library[:count])]
        if not exiled:
            return
        picked = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt="choose one of the exiled cards; you may play it this turn",
                source=name,
                amount=1,
                exact=True,
                cards=tuple(card.id for card in exiled),
                source_id=sid,
            )
        )
        chosen = next(card for card in exiled if card.id == picked[0])
        game.grant_play_permission(
            chosen,
            player.username,
            action=action,
            source_name=name,
            rule="CR 601.3, CR 611.2a",
            until_end_of_turn=True,
        )

    return effect
