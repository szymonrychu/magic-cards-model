"""Mass instructions over the stack: "counter all ..." and "exile all ...
spells".

Two printed shapes, each read whole because `split_effect_clauses` would
otherwise cut their own "and" apart:

- **"Counter all `<objects>`[. Create `<token>` for each `<object>` countered
  this way.]"** - Glen Elendra's Answer's "Counter all spells your opponents
  control and all abilities your opponents control. Create a 1/1 blue and
  black Faerie creature token with flying for each spell and ability
  countered this way." `<objects>` is an "and"-joined list of "spells" and
  "[activated |triggered ]abilities", each with an optional controller scope
  ("your opponents control", "you control", "you don't control").
- **"Exile all [other] spells[ `<scope>`] and counter all `<objects>`."** -
  Summary Dismissal's "Exile all other spells and counter all abilities."

CR 701.6a is the counter verb: "To counter a spell or ability means to
cancel it, removing it from the stack." `Game.counter` already refuses it for
a spell that can't be countered (CR 101.2, CR 113.6g), and such a spell is
not "countered this way" - it is still on the stack afterwards, which is how
the count below tells the two apart. Exiling a spell is CR 701.13a's
different verb (`Game.exile_from_stack`), which "can't be countered" does not
stop.

The resolving object itself is never swept: `Game.resolve_top` pops it off
the stack before its effect runs (CR 608.2), so "other" is only a reminder
that the printed card never meant itself.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState

if TYPE_CHECKING:
    from ..models.game import Game

#: One object kind in a "counter all ..." list, with its controller scope.
_OBJECT_RE = re.compile(
    r"^all (?P<noun>spells|(?:(?P<kind>activated|triggered) )?abilities)"
    r"(?: (?P<scope>your opponents control|you control|you don'?t control))?$",
    re.IGNORECASE,
)
_COUNTER_ALL_RE = re.compile(r"^counter (?P<objects>all .+?)\.?$", re.IGNORECASE)
_EXILE_ALL_SPELLS_AND_COUNTER_RE = re.compile(
    r"^exile all (?P<other>other )?spells"
    r"(?: (?P<scope>your opponents control|you control|you don'?t control))?"
    r" and counter (?P<objects>all .+?)\.?$",
    re.IGNORECASE,
)
#: "Create `<token>` for each spell[ and ability] countered this way."
_TOKENS_FOR_EACH_COUNTERED_RE = re.compile(
    r"^(?P<create>create .+?) for each (?:spell|ability|spell and ability|spell or ability)"
    r" countered this way\.?$",
    re.IGNORECASE,
)

#: CR 113.6g's own line, read by `casting_restrictions.cannot_be_countered`
#: - not an instruction, so not one of this text's sentences.
_CANT_BE_COUNTERED_SENTENCE_RE = re.compile(r"^this spell can'?t be countered\.?$", re.I)

StackFilter = Callable[[Any, str], bool]


def _scope_holds(scope: str | None, controller: str | None, you: str) -> bool:
    if scope is None:
        return True
    scope = scope.lower().replace("don't", "dont")
    if scope == "your opponents control" or scope == "you dont control":
        return controller is not None and controller != you
    return controller == you


def _object_filter(item_text: str) -> StackFilter | None:
    match = _OBJECT_RE.fullmatch(item_text.strip())
    if match is None:
        return None
    wants_spell = match.group("noun").lower() == "spells"
    kind = (match.group("kind") or "").lower()
    scope = match.group("scope")

    def matches(stack_object: Any, you: str) -> bool:
        is_spell = isinstance(stack_object, CardState)
        if wants_spell != is_spell:
            return False
        if kind and not is_spell:
            triggered = getattr(stack_object, "event", None) is not None
            if (kind == "triggered") != triggered:
                return False
        return _scope_holds(scope, getattr(stack_object, "controller", None), you)

    return matches


def _objects_filter(objects: str) -> StackFilter | None:
    """An "and"-joined list of `_OBJECT_RE` items as one filter, or None when
    any item is unreadable."""
    items = re.split(r"\s+and\s+", objects.strip())
    filters = [_object_filter(item) for item in items]
    if not filters or any(f is None for f in filters):
        return None
    readable = [f for f in filters if f is not None]
    return lambda stack_object, you: any(f(stack_object, you) for f in readable)


def _controller_of(game: "Game", stack_object: Any) -> str:
    return game.controller_of(stack_object).username


def _counter_matching(game: "Game", wanted: StackFilter, you: str) -> int:
    """Counter every stack object `wanted` picks; how many really left the
    stack (CR 701.6a) - an uncounterable one stays and is not counted."""
    countered = 0
    for stack_object in [item for item in game.stack if wanted(item, you)]:
        if stack_object not in game.stack:
            continue
        game.counter(stack_object)
        if stack_object not in game.stack:
            countered += 1
    return countered


def parse_mass_stack_whole_text(text: str, *, for_spell: bool) -> Any:
    """The whole text as one of this module's shapes, or None."""
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=\.)\s+", text.strip())
        if sentence.strip() and not _CANT_BE_COUNTERED_SENTENCE_RE.fullmatch(sentence.strip())
    ]
    if not sentences:
        return None

    from .effects import _parse_token_clause

    first = sentences[0]

    exile_match = _EXILE_ALL_SPELLS_AND_COUNTER_RE.fullmatch(first)
    if exile_match is not None and len(sentences) == 1:
        wanted = _objects_filter(exile_match.group("objects"))
        if wanted is None:
            return None
        exile_scope = exile_match.group("scope")

        def exile_and_counter(game: "Game", stack_object: Any) -> None:
            you = _controller_of(game, stack_object)
            for spell in [item for item in game.stack if isinstance(item, CardState)]:
                if _scope_holds(exile_scope, spell.controller, you):
                    game.exile_from_stack(spell)
            _counter_matching(game, wanted, you)

        return exile_and_counter

    counter_match = _COUNTER_ALL_RE.fullmatch(first)
    if counter_match is None or len(sentences) > 2:
        return None
    wanted = _objects_filter(counter_match.group("objects"))
    if wanted is None:
        return None
    token_clause = None
    if len(sentences) == 2:
        tokens = _TOKENS_FOR_EACH_COUNTERED_RE.fullmatch(sentences[1])
        if tokens is None:
            return None
        token_clause = _parse_token_clause(tokens.group("create"), for_spell=for_spell)
        if token_clause is None:
            return None

    def counter_all(game: "Game", stack_object: Any) -> None:
        you = _controller_of(game, stack_object)
        countered = _counter_matching(game, wanted, you)
        if token_clause is not None:
            # CR 608.2h: the number is fixed once, from what was countered.
            for _ in range(countered):
                token_clause(game, stack_object)

    return counter_all
