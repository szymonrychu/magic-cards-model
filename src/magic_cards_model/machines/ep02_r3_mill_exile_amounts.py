"""EP-02 R3 T3: mill / exile-the-top-X amounts and the referenced-stat
amounts that feed them.

    Target player mills cards equal to your life total.
    Up to one target player mills cards equal to this creature's power.
    Any number of target players each mill two cards.
    Any number of target players each mill cards equal to the number of cards
    in their graveyard.
    Destroy all creatures, then any number of target players each mill half
    their library, rounded down.

CR 701.17a: to mill a number of cards, a player puts that many cards from the
top of their library into their graveyard; with fewer cards in the library they
mill as many as possible. CR 107.1c: "any number of" targets is nought upwards
(the targeting reader already honours it). CR 107.1a: a "half" prints which
way it rounds. CR 608.2h: an amount is taken once, as the instruction is
applied, before any card moves.

The wording is `amount_sentences.parse_mill_clause`'s; this module adds the
subjects that sentence leaves open ("up to one target player", "any number of
target players each") and the "half their library" amount, and hooks them in as
one clause rung. The amount is read for each recipient through
`amount_sentences.recipient_amount`, so "their graveyard" is the recipient's own
and "your life total" the controller's.

Registered behind a cheap lowercase gate with memoised parsers, to stay inside
the classify budget.
"""

import functools
import re
from typing import TYPE_CHECKING, Any

from ..numbers import halve
from .amount_sentences import (
    Amount,
    apply_mill,
    clean,
    parse_mill_clause,
    recipient_amount,
)
from .effects._chains import FORWARD, MIXED_CLAUSE

if TYPE_CHECKING:
    from ..models.game import Game
    from .effects._common import TargetedClause

# --------------------------------------------------------------------------
# "<who> mills <amount>": the subject and the amount
# --------------------------------------------------------------------------

_SUBJECT_RE = re.compile(
    r"^(?:(?P<quantity>up to one|any number of) )?(?P<who>target (?:player|opponent)s?)"
    r"(?: each)?$|^(?P<plain>you|each player|each opponent|that player|they)(?: each)?$",
    re.IGNORECASE,
)
_HALF_LIBRARY_RE = re.compile(
    r"^(?P<subject>.+?) mills? half (?:their|your) library, rounded (?P<way>up|down)$",
    re.IGNORECASE,
)
_PLAYER_PLURAL_RE = re.compile(r"\bplayers\b|\bopponents\b", re.IGNORECASE)


def _recipients_word(subject: str) -> tuple[str, bool] | None:
    """The `amount_sentences.resolve_recipients` word `subject` names, and
    whether it targets: "up to one target player" and "any number of target
    players each" both read as "target player" (the targeting reader keeps the
    count, CR 107.1c)."""
    match = _SUBJECT_RE.fullmatch(clean(subject))
    if match is None:
        return None
    if match.group("plain") is not None:
        return match.group("plain").lower(), False
    word = _PLAYER_PLURAL_RE.sub(lambda m: m.group(0)[:-1], match.group("who").lower())
    return word, True


@functools.cache
def parse_mill_amount(text: str) -> tuple[str, Amount, bool] | None:
    """`(recipients word, amount, targets)` for a mill sentence whose subject
    is one of `_SUBJECT_RE`'s and whose amount is a fixed number, "cards equal
    to <expr>" or "half their library, rounded up|down", else `None`."""
    sentence = clean(text)
    lowered = sentence.lower()
    if "mill" not in lowered:
        return None
    if (half := _HALF_LIBRARY_RE.fullmatch(sentence)) is not None:
        named = _recipients_word(half.group("subject"))
        if named is None:
            return None
        round_up = half.group("way").lower() == "up"

        def half_library(_game: "Game", _obj: Any, who: Any) -> int:
            return halve(len(who.library), round_up=round_up)

        return named[0], half_library, named[1]
    clause = parse_mill_clause(sentence)
    if clause is None or clause.kind == "x" or clause.subject is None:
        return None
    named = _recipients_word(clause.subject)
    if named is None:
        return None
    if clause.kind == "fixed":
        fixed = clause.n

        def fixed_amount(_game: "Game", _obj: Any, _who: Any) -> int:
            return fixed

        return named[0], fixed_amount, named[1]
    amount = recipient_amount(clause.expr or "")
    return None if amount is None else (named[0], amount, named[1])


@MIXED_CLAUSE.rung("s36", for_spell=FORWARD)
def _parse_mill_amount_clause(clause: str, *, for_spell: bool) -> "TargetedClause | None":
    """`parse_mill_amount`'s sentence as one clause, spell or ability."""
    if "mill" not in clause.lower():
        return None
    parsed = parse_mill_amount(clause)
    if parsed is None:
        return None
    who, amount, targets = parsed
    if targets:
        from .effects._common import _targets_understood

        subject = clean(clause).split(" mill", 1)[0]
        subject = re.sub(r" each$", "", subject, flags=re.IGNORECASE)
        if not _targets_understood(subject, count_agnostic=True, allow_player_targets=True):
            return None

    def effect(game: "Game", stack_object: Any) -> None:
        apply_mill(game, stack_object, who, amount)

    return effect
