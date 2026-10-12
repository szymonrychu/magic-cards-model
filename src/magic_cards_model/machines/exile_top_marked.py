"""EP-01 round 3, task T6: "Exile the top `<n>` card(s) of `<whose>` library
[face down | with a `<kind>` counter on it]. [You may look at it for as long as
it remains exiled.]" - the exile half of CR 607.2a's linked pair.

Colfenor's Plans ("exile the top seven cards of your library face down"),
Grimoire Thief (target opponent's, three), Rogue Class ("that player's", the
player combat damage was dealt to), Jacob Hauken's back face (one, with a look
rider), Evelyn, the Covetous ("each player's library with a collection counter
on it"), and the printings that merely carry the template: Bomat Courier,
Connecting the Dots.

Every card the instruction exiles is marked as exiled *with* the ability's
source (`ExileAnnotation`, CR 607.2a; the source's incarnation, CR 400.7), so
the object's other abilities read it back ("cards exiled with this creature",
"a card exiled by an ability you controlled"). "Face down" (CR 406.3) leaves
the card with no characteristics (CR 406.3a) and visible to nobody; the look
rider is `Game.look` for the ability's controller (CR 701.20e), which lasts
until the card leaves exile (CR 406.3).

`mark_exiled` is the shared tail: the graveyard-exile readers
(`machines/exiled_with_peek.py`) mark what they exile the same way.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.player import Player
from ..models.zone import Zone
from ..numbers import count_pattern, parse_count

if TYPE_CHECKING:
    from ..models.game import Game

_WHOSE = (
    r"your|each player'?s|each opponent'?s|target opponent'?s|target player'?s|that player'?s"
)

_EXILE_TOP_RE = re.compile(
    rf"^exile the top (?:card|{count_pattern('n')} cards) of (?P<whose>{_WHOSE}) library"
    r"(?P<face_down> face down)?"
    r"(?: with an? (?P<counter>[a-z]+) counter on it)?\.?"
    r"(?P<look>\s+you may look at (?:that card|it|those cards|them) for as long as "
    r"(?:it|they) remains? exiled\.?)?$",
    re.IGNORECASE,
)


def mark_exiled(
    game: Game,
    ability: Any,
    card: CardState,
    *,
    face_down: bool = False,
    counter: str | None = None,
    looker: str | None = None,
) -> None:
    """Record `card` (just moved to exile by `ability`) as exiled with the
    ability's source (CR 607.2a), then apply the exiling text's own riders:
    face down (CR 406.3), a counter put on it in exile (CR 122.1), a look for
    `looker` that lasts while it stays exiled (CR 406.3, CR 701.20e)."""
    from .effects.removal import linked_exile_annotation

    if card.zone is not Zone.EXILE:
        return
    card.exile_annotation = linked_exile_annotation(game, ability, card)
    if face_down:
        card.face_up = False
    if counter is not None:
        game.add_counters(card, counter, 1)
    if looker is not None:
        game.look(card, looker, source=ability.source_name)


def _owners(game: Game, ability: Any, whose: str) -> list[Player]:
    from .effects._common import _players_in_apnap_order

    controller = game.controller_of(ability).username
    if whose == "your":
        return [game.player(controller)]
    if whose.startswith("each player"):
        return _players_in_apnap_order(game)
    if whose.startswith("each opponent"):
        return [p for p in _players_in_apnap_order(game) if p.username != controller]
    if whose.startswith("that player"):
        event = getattr(ability, "event", None)
        player = getattr(event, "player", None)
        return [game.player(player)] if player is not None else []
    return [t for t in game.resolve_targets(ability) if isinstance(t, Player)]


def exiled_by_top_of_library(
    game: Game, ability: Any, owners: Iterable[Player], count: int
) -> list[CardState]:
    """Exile `count` cards off the top of each owner's library, in order."""
    exiled: list[CardState] = []
    for owner in owners:
        exiled += [c for c in game.exile_cards(list(owner.library[:count])) if c.zone is Zone.EXILE]
    return exiled


def parse_exile_top_marked(text: str) -> Any:
    """The whole-text effect for the shape above, or None."""
    lowered = text.lower()
    if "exile the top" not in lowered or " library" not in lowered:
        return None
    if "face down" not in lowered and " counter on it" not in lowered:
        return None
    match = _EXILE_TOP_RE.fullmatch(" ".join(re.sub(r"\([^)]*\)", "", text).split()))
    if match is None:
        return None
    count = parse_count(match.group("n")) if match.group("n") else 1
    if count is None:
        return None
    whose = match.group("whose").lower()
    face_down = match.group("face_down") is not None
    counter = match.group("counter")
    counter = counter.lower() if counter else None
    look = match.group("look") is not None

    def effect(game: Game, ability: Any) -> None:
        controller = game.controller_of(ability).username
        owners = _owners(game, ability, whose)
        for card in exiled_by_top_of_library(game, ability, owners, count):
            mark_exiled(
                game,
                ability,
                card,
                face_down=face_down,
                counter=counter,
                looker=controller if look else None,
            )

    return effect
