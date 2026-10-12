"""EP-02 R1 T8: the counters-counted amount - an amount that is the number of
counters on an object.

"... mills X cards, where X is the number of oil counters on this artifact",
"loses life equal to the number of soul counters on this artifact", "discards
a card for each charge counter on this artifact", "put a -1/-1 counter on
target creature for each -1/-1 counter on this creature".

CR 122.1: a counter is a marker placed on an object, and its kind is its name
(any name is a legal kind), so "the number of <kind> counters on it" counts the
markers of that kind and a phrase naming no kind counts every counter. When the
object has left the battlefield (a dies trigger), CR 603.10a has the ability
look back in time and CR 122.2 has already emptied the live counters, so the
count is read from the object's last known information
(`ep01_r3_amounts.counters_on_it_total`).

The count is fixed once, as the ability resolves (CR 608.2h), so it is read
into the effect text before the family parsers see it: every parser already
reads "mills 3 cards", "loses 3 life", "puts 3 -1/-1 counters on", and none
needs to know where the 3 came from. `counters_read_from` names the object the
count is taken off; outside a resolution (the support oracle classifying a
printing) the phrase reads as `PLACEHOLDER`, which only has to be a number the
parsers accept in the plural.
"""

import contextlib
import contextvars
import re
from collections.abc import Callable, Iterator

from .ep01_r3_amounts import counters_on_it_total

#: What the phrase reads as when no object is being resolved - the support
#: oracle asks "can the engine read this shape", never "what is the number".
PLACEHOLDER = 2

_COUNTS: contextvars.ContextVar[Callable[[str | None], int] | None] = contextvars.ContextVar(
    "ep02_r1_counters_counted", default=None
)


@contextlib.contextmanager
def counters_read_from(source) -> Iterator[None]:
    """Resolve "the number of <kind> counters on it" against `source` (last
    known information when it has left the battlefield, CR 603.10a); a `None`
    source - gone with no record - counts nothing."""

    def count(kind: str | None) -> int:
        return 0 if source is None else counters_on_it_total(source, kind)

    token = _COUNTS.set(count)
    try:
        yield
    finally:
        _COUNTS.reset(token)


def _counted(kind: str | None) -> int:
    reader = _COUNTS.get()
    return PLACEHOLDER if reader is None else reader(kind)


def _kind(raw: str | None) -> str | None:
    return None if raw is None else raw.lower()


def _plural(n: int, noun: str) -> str:
    return f"a {noun}" if n == 1 else f"{n} {noun}s"


_KIND = r"(?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?"
_COUNTERS = r"counters?"


def _self(names: tuple[str, ...]) -> str:
    named = "".join(f"|{re.escape(name)}" for name in names)
    return rf"(?:it|this [a-z]+{named})"


def _where_x(names: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        rf",? where X is the number of {_KIND}{_COUNTERS} on {_self(names)}(?=[.,]|$)",
        re.IGNORECASE,
    )


def _number_of(names: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(rf"the number of {_KIND}{_COUNTERS} on {_self(names)}\b", re.IGNORECASE)


def _equal_to(names: tuple[str, ...]) -> re.Pattern[str]:
    # "loses life equal to the number of soul counters on this artifact",
    # "deals damage equal to the number of charge counters on it to ..."
    return re.compile(
        rf"\b(?P<what>life|damage) equal to the number of {_KIND}{_COUNTERS} on {_self(names)}\b",
        re.IGNORECASE,
    )


def _for_each_pump(names: tuple[str, ...]) -> re.Pattern[str]:
    # "gets +1/+1 until end of turn for each lore counter on this artifact"
    return re.compile(
        rf"\b(?P<verb>gets?) (?P<p>[+-]\d+)/(?P<t>[+-]\d+)(?P<mid>(?: until end of turn)?)"
        rf" for each {_KIND}{_COUNTERS} on {_self(names)}\b",
        re.IGNORECASE,
    )


def _for_each_verb(names: tuple[str, ...]) -> re.Pattern[str]:
    # "discards a card for each charge counter on this artifact"
    return re.compile(
        rf"\b(?P<verb>discards?|draws?|mills?) (?:a|an|one) (?P<noun>card)"
        rf"(?P<mid>[^.,]*?) for each {_KIND}{_COUNTERS} on {_self(names)}\b",
        re.IGNORECASE,
    )


def _for_each_put(names: tuple[str, ...]) -> re.Pattern[str]:
    # "put a -1/-1 counter on target creature for each -1/-1 counter on this creature"
    return re.compile(
        rf"\b(?P<verb>puts?|distributes?) (?:a|an|one) (?P<ck>\+1/\+1|-1/-1|[a-z]+) counter"
        rf"(?P<mid> [^.,]*?) for each {_KIND}{_COUNTERS} on {_self(names)}\b",
        re.IGNORECASE,
    )


def _for_each_target(names: tuple[str, ...]) -> re.Pattern[str]:
    # "for each isolation counter on it, exile up to one target nonland permanent
    # an opponent controls until ..." - one target per counter (CR 601.2c).
    return re.compile(
        rf"for each {_KIND}{_COUNTERS} on {_self(names)}, (?P<verb>[a-z]+) up to one target "
        rf"(?P<noun>[a-z ]+?)(?P<tail> an opponent controls|you control|[ ,.]|$)",
        re.IGNORECASE,
    )


def counters_counted_text(text: str, names: tuple[str, ...] = ()) -> str:
    """`text` with each "number of <kind> counters on <the source>" phrase read
    as the number it is now (CR 122.1, CR 608.2h); unchanged when it has none.

    `names` are the strings the card's own text uses to mean itself (CR 201.5)."""
    lowered = text.lower()
    if "counter" not in lowered or " on " not in lowered:
        return text

    def n_of(match: re.Match[str]) -> int:
        return _counted(_kind(match.group("kind")))

    where = _where_x(names).search(text)
    if where is not None:
        number = n_of(where)
        rest = text[: where.start()] + text[where.end() :]
        text = re.sub(r"\bX\b", str(number), rest)
    equal = _equal_to(names).search(text)
    if equal is not None:
        # "... and that much damage to up to one target creature" repeats the
        # amount the first half was just read as (CR 608.2c).
        number = n_of(equal)
        text = _equal_to(names).sub(lambda m: f"{number} {m.group('what')}", text)
        text = re.sub(r"\bthat much (damage|life)\b", rf"{number} \1", text)
    text = _number_of(names).sub(lambda m: str(n_of(m)), text)

    def pump(m: re.Match[str]) -> str:
        n = n_of(m)
        power, toughness = int(m.group("p")) * n, int(m.group("t")) * n
        return f"{m.group('verb')} {power:+d}/{toughness:+d}{m.group('mid')}"

    text = _for_each_pump(names).sub(pump, text)

    def verb_noun(m: re.Match[str]) -> str:
        n = n_of(m)
        return f"{m.group('verb')} {_plural(n, m.group('noun'))}{m.group('mid')}"

    text = _for_each_verb(names).sub(verb_noun, text)

    def put_counters(m: re.Match[str]) -> str:
        n = n_of(m)
        return f"{m.group('verb')} {_plural(n, m.group('ck') + ' counter')}{m.group('mid')}"

    text = _for_each_put(names).sub(put_counters, text)

    def targets(m: re.Match[str]) -> str:
        n = n_of(m)
        noun = m.group("noun")
        wording = "one target " + noun if n == 1 else f"{n} target {noun}s"
        return f"{m.group('verb')} up to {wording}{m.group('tail')}"

    return _for_each_target(names).sub(targets, text)
