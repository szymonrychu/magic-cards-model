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


_REVEAL_TAKE_ONE_RE = re.compile(
    r"^reveal the top (?P<n>\w+) cards of your library\.\s*"
    r"you may put (?:(?P<shares>a card that shares a creature type with it)"
    r"|an? (?P<quality>.+?) card) from among them into your hand\.\s*"
    r"put the rest on the bottom of your library in a random order\.?$",
    re.IGNORECASE,
)


def parse_reveal_top_take_one_rest_bottom(text: str) -> Any:
    """ "Reveal the top `<n>` cards of your library. You may put a `<card that
    shares a creature type with it | quality card>` from among them into your
    hand. Put the rest on the bottom of your library in a random order."
    (Tajuru Paragon).

    CR 701.20a reveals every card, CR 608.2d offers the one optional pick from
    among the revealed cards, and CR 701.24-style ordering is a random one
    (CR 401.4 for several cards put on the bottom at once). "it" is the
    ability's source (CR 603.7c); two creatures share a type per CR 205.3m and
    changeling's all-types (CR 702.73a, `chosen_type.shares_creature_type`).
    """
    if "from among them into your hand" not in text.lower():
        return None
    match = _REVEAL_TAKE_ONE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None
    quality = match.group("quality")
    if quality is not None:
        from .effects import _quality_matcher, _search_quality_is_readable

        if not _search_quality_is_readable(quality):
            return None
        quality_matches = _quality_matcher(quality)
    else:
        quality_matches = None

    def effect(game: "Game", ability: Any) -> None:
        from random import Random

        from ..models.zone import Zone
        from .chosen_type import shares_creature_type
        from .effects.modal import _choose_one_card

        player = game.controller_of(ability)
        source = ability.source(game)
        revealed = list(player.library[:count])
        for card in revealed:
            game.reveal(card, source=ability.source_name)
        if quality_matches is not None:
            candidates = [card for card in revealed if quality_matches(card)]
        elif source is None:
            candidates = []
        else:
            candidates = [card for card in revealed if shares_creature_type(game, card, source)]
        taken = None
        if candidates and game.may(
            player,
            "put a card from among the revealed cards into your hand",
            source=ability.source_name,
            source_id=source_id_of(ability),
            cards=candidates,
        ):
            taken = _choose_one_card(
                game,
                player,
                candidates,
                prompt="choose a card to put into your hand",
                source=ability.source_name,
                source_id=source_id_of(ability),
            )
            player.move(taken, Zone.HAND)
        rest = [card for card in revealed if card is not taken]
        Random(f"{game.shuffle_seed}:{game.shuffles_performed}:reveal-bottom").shuffle(rest)  # noqa: S311
        for card in rest:
            player.move(card, Zone.LIBRARY)
        if rest:
            game.shuffles_performed += 1

    return effect
