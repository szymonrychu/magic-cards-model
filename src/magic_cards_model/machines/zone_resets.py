"""Symmetric "reset" effects that touch every player's hand, graveyard, and
library at once - the mass-bounce-and-wheel family (CR 701.3's "return",
CR 701.24a's "shuffle").

`machines/effects.py` already reads a *mandatory* per-player wheel ("each
player shuffles their hand and graveyard into their library", Day's Undoing,
via `_parse_each_player_step`'s own `_SHUFFLE_HAND_AND_GRAVEYARD_RE`) and the
plain mass bounce ("return all creatures to their owners' hands",
`_parse_mass_return_to_hand_clause`). This module owns the one shape neither
of those is: an *optional* per-player wheel whose second half ("then each
player who does draws N cards") is conditioned on that same player's own
CR 608.2d choice in the first half, restated as its own sentence rather than
folded into one bare "and" - Turtles in Time's own second sentence.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..models.zone import Zone
from ..numbers import COUNT, parse_count
from .decisions import source_id_of

if TYPE_CHECKING:
    from ..models.game import Game

#: "Each player may shuffle their hand and graveyard into their library[,]
#: then each player who does draws `<n>` cards." - Turtles in Time's own
#: second sentence, and "Each player may shuffle their hand and graveyard
#: into their library. Each player who does draws `<n>` cards." - Step
#: Between Worlds' identical mechanic printed as two full sentences instead
#: of a comma-"then" join. `merge_each_player_may_shuffle_hand_graveyard_
#: then_draw_clauses` below reconstructs both the same way once `machines.
#: effects.split_effect_clauses` has cut either one into fragments, which is
#: why "then" is optional here rather than the join this pattern insists on.
#: Distinct from Day's Undoing's mandatory "each player shuffles ..." (no
#: "may", no restated subject) - this one asks CR 608.2d's own "you may" of
#: every player, and the draw is conditioned on that individual player's own
#: answer rather than being a flat instruction to everybody.
EACH_PLAYER_MAY_SHUFFLE_HAND_GRAVEYARD_THEN_DRAW_RE = re.compile(
    r"^each player may shuffle (?:their|your|his or her) hand and graveyard into "
    r"(?:their|your|his or her) library\.\s*(?:then\s+)?each player who does draws "
    rf"(?P<count>{COUNT}) cards?\.?$",
    re.IGNORECASE,
)


def _build_each_player_may_shuffle_hand_graveyard_then_draw_effect(
    count: int, *, for_spell: bool
) -> Any:
    def effect(game: Game, stack_object: Any) -> None:
        source = stack_object.name if for_spell else stack_object.source_name
        source_id = source_id_of(stack_object)
        for player in list(game.players):
            if not game.is_in_game(player.username):
                continue
            if not game.may(
                player,
                "shuffle your hand and graveyard into your library",
                source=source,
                source_id=source_id,
            ):
                continue
            for card_state in list(player.hand) + list(player.graveyard):
                player.move(card_state, Zone.LIBRARY)
            game.shuffle_library(player)
            game.draw_cards(player.username, count)

    return effect


def parse_each_player_may_shuffle_hand_graveyard_then_draw_clause(
    text: str, *, for_spell: bool
) -> Any | None:
    """`EACH_PLAYER_MAY_SHUFFLE_HAND_GRAVEYARD_THEN_DRAW_RE`'s shape, read off
    a single already-whole clause - see `merge_each_player_may_shuffle_hand_
    graveyard_then_draw_clauses` below for the ordinary case, where `machines.
    effects.split_effect_clauses`'s own separators have cut the printed
    sentence into fragments first.
    """
    match = EACH_PLAYER_MAY_SHUFFLE_HAND_GRAVEYARD_THEN_DRAW_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    count = parse_count(match.group("count"))
    if count is None:
        return None
    return _build_each_player_may_shuffle_hand_graveyard_then_draw_effect(
        count, for_spell=for_spell
    )


def merge_each_player_may_shuffle_hand_graveyard_then_draw_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, Any] | None:
    """Rejoins `machines.effects.split_effect_clauses`'s own three-way cut of
    Turtles in Time's second sentence: its `_CLAUSE_SEPARATOR` splits on a
    bare " and " as well as a period and ", then", so "shuffle their hand
    **and** graveyard into their library, **then** each player who does
    draws seven cards" comes back as three fragments - "shuffle their hand",
    "graveyard into their library", "each player who does draws N cards" (its
    own leading "then" already stripped by that same splitter) - none of
    which is CR 608.2c's one instruction on its own.

    One `Game.may` per player still in the game (CR 101.4/CR 608.2d), in
    seating order - the same order `_parse_each_player_may_discard_hand_and_
    draw_clause` already walks for the twin "each player may discard their
    hand and draw N cards" shape. A player who declines shuffles nothing
    (their hand and graveyard stay exactly where they are) and draws
    nothing, since "each player who does" ties the draw 1:1 to that same
    player's own answer, never to anyone else's.

    CR 701.24a's shuffle is the library alone; the hand and graveyard are
    moved into it first (CR 400.7: each card becomes a new library object),
    then the whole thing is shuffled - the identical two-step order Day's
    Undoing's own per-player step already performs for the mandatory shape.
    """
    if index + 2 >= len(clauses):
        return None
    combined = (
        f"{clauses[index].strip()} and {clauses[index + 1].strip()}. {clauses[index + 2].strip()}"
    )
    match = EACH_PLAYER_MAY_SHUFFLE_HAND_GRAVEYARD_THEN_DRAW_RE.fullmatch(
        " ".join(combined.split())
    )
    if match is None:
        return None
    count = parse_count(match.group("count"))
    if count is None:
        return None
    return 3, _build_each_player_may_shuffle_hand_graveyard_then_draw_effect(
        count, for_spell=for_spell
    )
