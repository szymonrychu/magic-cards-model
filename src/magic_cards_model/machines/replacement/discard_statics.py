"""Discard-replacement statics (CR 701.9a, 614.1a, 113.6b):

- "If a spell or ability an opponent controls causes you to discard this card,
  put it onto the battlefield [with two +1/+1 counters on it] instead of
  putting it into your graveyard." (Obstinate Baloth, Dodecapod) - the card's
  own line, working from the hand.
- "If a spell or ability an opponent controls causes you to discard a card,
  you may reveal that card and put it on top of your library instead of
  putting it anywhere else." (Nephalia Academy) - a permanent's line.

A discard raised by a cost, the cleanup step or the player's own spell is not
"caused by an opponent's spell or ability", so neither applies to it.
"""

import re

from ...models.card_state import CardState
from ...models.zone import Zone
from ..decisions import Decision, DecisionKind
from .model import (
    CardReplacement,
    EventKind,
    ReplaceableEvent,
    ReplacementEffect,
    ReplacementKind,
)

_CAUSE_RE = re.compile(
    r"^a spell or ability an opponent controls causes you to discard (?P<what>this card|a card)$",
    re.IGNORECASE,
)
_BATTLEFIELD_RE = re.compile(
    r"^put it onto the battlefield(?: with (?P<n>a|an|one|two|three|four) "
    r"(?P<kind>[+\-]\d+/[+\-]\d+) counters? on it)?$",
    re.IGNORECASE,
)
_LIBRARY_TOP_RE = re.compile(
    r"^you may reveal that card and put it on top of your library$", re.IGNORECASE
)
_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4}


def _caused_by_opponent(game, owner: str, event: ReplaceableEvent) -> bool:
    cause = event.cause_controller
    return (
        event.kind is EventKind.ZONE_CHANGE
        and event.discarded
        and event.origin is Zone.HAND
        and cause is not None
        and cause != owner
    )


def _compile_discard_replacement(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.INSTEAD_OF or effect.condition is None:
        return None
    cause = _CAUSE_RE.match(effect.condition.strip())
    if cause is None:
        return None
    replacement = (effect.replacement or "").strip().rstrip(".")
    event_text = (effect.event or "").strip().lower()
    if cause.group("what").lower() == "this card":
        match = _BATTLEFIELD_RE.match(replacement)
        if match is None or event_text != "putting it into your graveyard":
            return None
        counters = (
            {match.group("kind"): _NUMBERS[match.group("n").lower()]}
            if match.group("n")
            else {}
        )

        def applies(game, source: CardState, event: ReplaceableEvent) -> bool:
            return event.card is not None and event.card.id == source.id and _caused_by_opponent(
                game, event.card.owner or "", event
            )

        def apply(game, source: CardState, event: ReplaceableEvent) -> None:
            event.destination = Zone.BATTLEFIELD
            event.counters = dict(counters)

        return CardReplacement(label=effect.text, applies=applies, apply=apply, anywhere=True)
    if _LIBRARY_TOP_RE.match(replacement) is None or event_text != "putting it anywhere else":
        return None

    def applies_top(game, source: CardState, event: ReplaceableEvent) -> bool:
        return (
            event.card is not None
            and (event.card.owner or "") == source.controller
            and _caused_by_opponent(game, source.controller or "", event)
        )

    def apply_top(game, source: CardState, event: ReplaceableEvent) -> None:
        answer = game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=source.controller or "",
                prompt="Reveal that card and put it on top of your library instead?",
                source=source.name,
                source_id=str(source.id),
            )
        )
        if answer:
            event.destination = Zone.LIBRARY
            event.library_position = "top"

    return CardReplacement(label=effect.text, applies=applies_top, apply=apply_top)


DISCARD_COMPILERS = (_compile_discard_replacement,)
