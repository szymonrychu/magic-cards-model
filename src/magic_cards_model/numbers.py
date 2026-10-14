"""The one reader for a count a card prints.

Magic spells its counts out - "Draw seven cards", "Create thirteen tapped 2/2
black Zombie creature tokens", "mills twelve cards" - and prints digits for
others ("loses 1,000 life", "deals 3 damage"). Every oracle-text parser in
`machines/` and `models/` reads its counts through this module, so a number
word is learned once, not once per parser: before it existed there were
fourteen separate tables, most of them stopping at "ten".

CR 107.1: "The only numbers the Magic game uses are integers." So every count
here reads as an `int`, and anything that is not one is a marker, never a
guess:

- `VariableX` - CR 107.3's X ("a placeholder for a number that needs to be
  determined"), with the text of its "where X is ..." definition when the card
  prints one. Evaluating that text is the caller's business
  (`machines/effects.py`'s `amount_expression`/`count_expression`), not this
  module's: it only reads words.
- `Quantity` - a count with its bounds: "up to two" (none to two), CR 107.1c's
  "any number of" ("any positive number or zero"), "one or more", and "that
  many" (a count carried from an earlier event or instruction, which the
  caller has to supply).

Nothing here raises on an unknown word. A reader answers `None`, and the
parser that asked fails closed with it.

Every CR number in this docstring was looked up with `mise run rules:find` in
the session that wrote it.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from magic_cards_model.text_norm import collapsed

__all__ = [
    "AMOUNT",
    "COUNT",
    "MULTIPLIER",
    "ORDINAL",
    "QUANTITY",
    "Quantity",
    "QuantitySource",
    "VariableX",
    "Half",
    "count_pattern",
    "halve",
    "parse_amount",
    "parse_count",
    "parse_half",
    "parse_multiplier",
    "parse_ordinal",
    "parse_quantity",
    "quantity_pattern",
    "where_x_pattern",
]

_ARTICLES = {"a": 1, "an": 1}

_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
}

_ORDINALS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
}

#: "once", "twice", "thrice" - the multipliers printed as one word.
_MULTIPLIER_WORDS = {"once": 1, "twice": 2, "thrice": 3}

#: A number printed in digits. The comma-grouped alternative comes first so
#: "1,000" (The Millennium Calendar) is read whole rather than as "1" with
#: ",000" left over.
_DIGITS = r"\d{1,3}(?:,\d{3})+|\d+"


def _alternation(words: Iterable[str]) -> str:
    """Longest first, so "seventeen" is never matched short as "seven"."""
    return "|".join(sorted(words, key=len, reverse=True))


#: A compound number word above twenty - "twenty-five" (Jace, Reality
#: Sculptor's own "twenty-five or more loyalty counters"), "thirty-one" -
#: read the ordinary English way, tens plus ones, with either a hyphen or a
#: bare space between them (both are printed in Magic text; Wizards' own
#: style guide favours the hyphen, but oracle text is not always styled
#: consistently). `_TENS` is every multiple of ten `_WORDS` already names
#: ("twenty" through "fifty"); `_ONES` is "one" through "nine" - "twenty-
#: zero"/"twenty-ten" are not real compounds and are excluded by construction
#: rather than checked for.
_TENS = {word: value for word, value in _WORDS.items() if value >= 20 and value % 10 == 0}
_ONES = {word: value for word, value in _WORDS.items() if 1 <= value <= 9}
_COMPOUND_TENS_RE = re.compile(rf"(?:{_alternation(_TENS)})[\s-]+(?:{_alternation(_ONES)})")


def _parse_compound_tens(text: str) -> int | None:
    """ "twenty-five" -> 25, or `None` when `text` is not this shape."""
    if not _COMPOUND_TENS_RE.fullmatch(text):
        return None
    tens_word, ones_word = re.split(r"[\s-]+", text, maxsplit=1)
    tens = _TENS.get(tens_word)
    ones = _ONES.get(ones_word)
    if tens is None or ones is None:
        return None
    return tens + ones


_COUNT_NO_ARTICLE = rf"(?:{_DIGITS}|{_COMPOUND_TENS_RE.pattern}|{_alternation(_WORDS)})"

#: Every count a card prints: "a", "an", "zero" through "twenty", the tens to
#: "fifty", a compound of the two ("twenty-five"), and digits. No X - a
#: parser that embeds this cannot match an X it has no way to evaluate. Case
#: is the embedding pattern's business (`re.IGNORECASE`), as it was for
#: every table this replaced.
COUNT = rf"(?:{_DIGITS}|{_COMPOUND_TENS_RE.pattern}|{_alternation({**_WORDS, **_ARTICLES})})"

#: `COUNT` or CR 107.3's X.
AMOUNT = rf"(?:{COUNT}|[xX])"

#: "once", "twice", "thrice", "three times", "10 times".
MULTIPLIER = rf"(?:{_alternation(_MULTIPLIER_WORDS)}|{_COUNT_NO_ARTICLE} times)"

#: "first" through "twentieth".
ORDINAL = rf"(?:{_alternation(_ORDINALS)})"

#: Every quantifier `parse_quantity` reads: "three", "up to two", "up to X",
#: "X", "any number of", "one or more", "that many", "up to that many".
QUANTITY = rf"(?:any number of|one or more|(?:up to )?(?:that many|{AMOUNT}))"


def count_pattern(name: str | None = None, *, x: bool = False, article: bool = True) -> str:
    """A regex fragment matching one count, for a parser to embed.

    `name` wraps it in a named group. `x=True` also matches CR 107.3's X (read
    it back with `parse_amount`). `article=False` leaves out "a"/"an", for a
    capture that could land on an article that is not a count ("Choose a
    color").
    """
    body = COUNT if article else _COUNT_NO_ARTICLE
    if x:
        body = rf"(?:{body}|[xX])"
    return rf"(?P<{name}>{body})" if name else body


def where_x_pattern(name: str = "where_x") -> str:
    """An optional ", where X is <expression>" tail, capturing the expression
    in the named group (None when the card prints no definition)."""
    return rf"(?:,\s*where\s+[xX]\s+is\s+(?P<{name}>[^.]+))?"


def quantity_pattern(name: str) -> str:
    """`QUANTITY` in a named group, read back with `parse_quantity`."""
    return rf"(?P<{name}>{QUANTITY})"


def parse_count(word: str, *, article: bool = True) -> int | None:
    """The integer a printed count means, or `None` when `word` is not one.

    Digits ("7", "1,000"), "zero" through "twenty", the tens to "fifty", a
    compound of the two ("twenty-five"), and "a"/"an" as one unless
    `article=False`. Never raises.
    """
    text = word.strip().lower()
    if re.fullmatch(_DIGITS, text):
        return int(text.replace(",", ""))
    if article and text in _ARTICLES:
        return _ARTICLES[text]
    if text in _WORDS:
        return _WORDS[text]
    return _parse_compound_tens(text)


@dataclass(frozen=True)
class VariableX:
    """CR 107.3's X, not yet a number. `expression` is the printed definition
    after "where X is" ("the number of Elves you control"), or None when the
    card defines no X in its text (CR 107.3a: the controller announces it)."""

    expression: str | None = None


_X_AMOUNT = re.compile(r"\s*x(?:\s*,\s*where\s+x\s+is\s+(?P<expr>.+?))?\s*\.?\s*", re.IGNORECASE)


def parse_amount(text: str) -> int | VariableX | None:
    """A count, or a `VariableX` for "X" / "X, where X is ...", or `None`."""
    match = _X_AMOUNT.fullmatch(text)
    if match is not None:
        expression = match.group("expr")
        return VariableX(expression.strip() if expression else None)
    return parse_count(text)


def parse_multiplier(text: str) -> int | None:
    """ "once" 1, "twice" 2, "thrice" 3, "<count> times" that count; else None."""
    words = text.strip().lower().split()
    if len(words) == 1:
        return _MULTIPLIER_WORDS.get(words[0])
    if len(words) == 2 and words[1] == "times":
        return parse_count(words[0], article=False)
    return None


def parse_ordinal(word: str) -> int | None:
    """ "first" 1 through "twentieth" 20, or None."""
    return _ORDINALS.get(word.strip().lower())


class QuantitySource(StrEnum):
    """Where a `Quantity`'s number comes from."""

    FIXED = "fixed"
    """Printed: "three", "up to two"."""
    X = "x"
    """CR 107.3's X, still to be determined."""
    ANY_NUMBER = "any_number"
    """CR 107.1c: "any positive number or zero"."""
    ONE_OR_MORE = "one_or_more"
    """At least one, no printed maximum."""
    THAT_MANY = "that_many"
    """A count carried from an earlier event or instruction."""


@dataclass(frozen=True)
class Quantity:
    """How many a quantifier asks for.

    `amount` is the most (None when there is no printed maximum or the number
    is not known from the text); `minimum` the fewest (None when it equals the
    amount once that is known, as for a bare "X" or "that many"). `expression`
    is a `VariableX`'s "where X is" text.
    """

    amount: int | None
    minimum: int | None
    source: QuantitySource
    expression: str | None = None

    @property
    def exact(self) -> bool:
        """True when exactly `amount` must be chosen, not a range."""
        return self.minimum is None or self.minimum == self.amount


def parse_quantity(text: str) -> Quantity | None:
    """ "three", "up to two", "X", "up to X", "any number of", "one or more",
    "that many", "up to that many" as a `Quantity`; anything else None."""
    words = collapsed(text.strip().lower())
    if words in ("any number of", "any number"):
        return Quantity(amount=None, minimum=0, source=QuantitySource.ANY_NUMBER)
    if words == "one or more":
        return Quantity(amount=None, minimum=1, source=QuantitySource.ONE_OR_MORE)
    up_to = words.startswith("up to ")
    rest = words.removeprefix("up to ") if up_to else words
    if rest == "that many":
        return Quantity(amount=None, minimum=0 if up_to else None, source=QuantitySource.THAT_MANY)
    amount = parse_amount(rest)
    if isinstance(amount, VariableX):
        return Quantity(
            amount=None,
            minimum=0 if up_to else None,
            source=QuantitySource.X,
            expression=amount.expression,
        )
    if amount is None:
        return None
    return Quantity(amount=amount, minimum=0 if up_to else amount, source=QuantitySource.FIXED)


@dataclass(frozen=True)
class Half:
    """ "half `<of>`, rounded up/down" - a count that is half of something
    else, with the rounding direction CR 107.1a requires the card to print:
    "If a spell or ability could generate a fractional number, the spell or
    ability will tell you whether to round up or down."

    `of` is the printed text being halved, verbatim ("the number of cards in
    your library", "their library"); what it counts is the caller's business,
    the same division of labour `VariableX.expression` has.
    """

    of: str
    round_up: bool


#: "half the number of cards in your library, rounded up" (Tamiyo, Seasoned
#: Scholar), "half their library, rounded down" (Traumatize), "the top half of
#: their library, rounded up" (Ulamog, the Defiler) - "the top" is where the
#: cards come from, not part of the count, so it is read and dropped here.
_HALF_RE = re.compile(
    r"\s*(?:the top )?half (?:of )?(?P<of>.+?),\s*rounded (?P<direction>up|down)\s*\.?\s*",
    re.IGNORECASE,
)


def parse_half(text: str) -> Half | None:
    """A `Half` for "[the top] half [of] `<of>`, rounded up|down", or `None`.

    A "half" with no printed rounding direction is not read: CR 107.1a says
    the card will say which way, and guessing would be a defect.
    """
    match = _HALF_RE.fullmatch(text)
    if match is None:
        return None
    return Half(of=match.group("of").strip(), round_up=match.group("direction").lower() == "up")


def halve(value: int, *, round_up: bool) -> int:
    """`value` halved, rounded the way CR 107.1a's printed direction says."""
    return (value + 1) // 2 if round_up else value // 2
