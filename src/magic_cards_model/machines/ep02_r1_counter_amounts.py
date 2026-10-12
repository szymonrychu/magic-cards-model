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
import functools
import re
from collections.abc import Callable, Iterator

from .ep01_r3_amounts import counters_on_it_total

#: What the phrase reads as when no object is being resolved - the support
#: oracle asks "can the engine read this shape", never "what is the number".
PLACEHOLDER = 2

_COUNTS: contextvars.ContextVar[Callable[[str | None], int] | None] = contextvars.ContextVar(
    "ep02_r1_counters_counted", default=None
)
#: How many counters the resolving ability's own cost removed.
_REMOVED: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "ep02_r1_counters_removed", default=None
)
#: The number the triggering event carried - how many cards a scry looked at.
_EVENT_AMOUNT: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "ep02_r1_event_amount", default=None
)


@contextlib.contextmanager
def counters_read_from(
    source, event_amount: int | None = None, *, removed: int | None = None
) -> Iterator[None]:
    """Resolve "the number of <kind> counters on it" against `source` (last
    known information when it has left the battlefield, CR 603.10a); a `None`
    source - gone with no record - counts nothing. `event_amount` is the number
    the triggering event carried, for "for each card looked at while scrying
    this way". `removed` is the number of counters the ability's cost removed
    (CR 107.3a's announced number), for "counters removed this way"."""

    def count(kind: str | None) -> int:
        return 0 if source is None else counters_on_it_total(source, kind)

    token = _COUNTS.set(count)
    amount_token = _EVENT_AMOUNT.set(event_amount)
    removed_token = _REMOVED.set(removed)
    try:
        yield
    finally:
        _REMOVED.reset(removed_token)
        _EVENT_AMOUNT.reset(amount_token)
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


def _self(names: tuple[str, ...] = ()) -> str:
    # The card's own name is swapped for a `\x00<index>\x00` token before the
    # patterns run (`_tokenised`), so each pattern compiles once, not per card.
    return r"(?:it|this [a-z]+|\x00\d+\x00)"


def _tokenised(text: str, names: tuple[str, ...]) -> str:
    """`text` with the card's own name after "on " as a name-independent token."""
    for index, name in enumerate(names):
        token = f"\x00{index}\x00"
        text = re.sub(rf"(\bon ){re.escape(name)}\b", lambda m, t=token: m.group(1) + t, text)
    return text


def _restored(text: str, names: tuple[str, ...]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: names[int(m.group(1))], text)


@functools.cache
def _where_x(names: tuple[str, ...] = ()) -> re.Pattern[str]:
    return re.compile(
        rf",? where X is the number of {_KIND}{_COUNTERS} on {_self()}(?=[.,]|$)",
        re.IGNORECASE,
    )


@functools.cache
def _number_of(names: tuple[str, ...] = ()) -> re.Pattern[str]:
    return re.compile(rf"the number of {_KIND}{_COUNTERS} on {_self()}\b", re.IGNORECASE)


@functools.cache
def _equal_to(names: tuple[str, ...] = ()) -> re.Pattern[str]:
    # "loses life equal to the number of soul counters on this artifact",
    # "deals damage equal to the number of charge counters on it to ..."
    return re.compile(
        rf"\b(?P<what>life|damage) equal to the number of {_KIND}{_COUNTERS} on {_self()}\b",
        re.IGNORECASE,
    )


@functools.cache
def _for_each_pump(names: tuple[str, ...] = ()) -> re.Pattern[str]:
    # "gets +1/+1 until end of turn for each lore counter on this artifact"
    return re.compile(
        rf"\b(?P<verb>gets?) (?P<p>[+-]\d+)/(?P<t>[+-]\d+)(?P<mid>(?: until end of turn)?)"
        rf" for each {_KIND}{_COUNTERS} on {_self()}\b",
        re.IGNORECASE,
    )


@functools.cache
def _a_number_of_counters(names: tuple[str, ...] = ()) -> re.Pattern[str]:
    # "distribute a number of +1/+1 counters equal to the number of +1/+1
    # counters on this creature among ..." (a dies trigger spreading its own)
    return re.compile(
        rf"\ba number of (?P<ck>\+1/\+1|-1/-1|[a-z]+) counters equal to the number of "
        rf"{_KIND}{_COUNTERS} on {_self()}\b",
        re.IGNORECASE,
    )


@functools.cache
def _for_each_verb(names: tuple[str, ...] = ()) -> re.Pattern[str]:
    # "discards a card for each charge counter on this artifact"
    return re.compile(
        rf"\b(?P<verb>discards?|draws?|mills?) (?:a|an|one) (?P<noun>card)"
        rf"(?P<mid>[^.,]*?) for each {_KIND}{_COUNTERS} on {_self()}\b",
        re.IGNORECASE,
    )


@functools.cache
def _for_each_put(names: tuple[str, ...] = ()) -> re.Pattern[str]:
    # "put a -1/-1 counter on target creature for each -1/-1 counter on this creature"
    return re.compile(
        rf"\b(?P<verb>puts?|distributes?) (?:a|an|one) (?P<ck>\+1/\+1|-1/-1|[a-z]+) counter"
        rf"(?P<mid> [^.,]*?) for each {_KIND}{_COUNTERS} on {_self()}\b",
        re.IGNORECASE,
    )


@functools.cache
def _for_each_target(names: tuple[str, ...] = ()) -> re.Pattern[str]:
    # "for each isolation counter on it, exile up to one target nonland permanent
    # an opponent controls until ..." - one target per counter (CR 601.2c).
    return re.compile(
        rf"for each {_KIND}{_COUNTERS} on {_self()}, (?P<verb>[a-z]+) up to one target "
        rf"(?P<noun>[a-z]+(?: [a-z]+)*?)(?P<tail> an opponent controls| you control| until|[,.]|$)",
        re.IGNORECASE,
    )


_FOR_EACH_SCRIED = re.compile(
    r"\b(?P<verb>gets?) (?P<p>[+-]\d+)/(?P<t>[+-]\d+)(?P<mid>(?: until end of turn)?)"
    r" for each card looked at while scrying this way\b",
    re.IGNORECASE,
)


def _for_each_scried(text: str) -> str:
    """ "gets +1/+1 until end of turn for each card looked at while scrying this
    way" (Celeborn the Wise) read as the pump for the scry's own number of cards
    (CR 701.22a: it looks at the top N); `PLACEHOLDER` when classifying."""
    looked = _EVENT_AMOUNT.get()
    n = PLACEHOLDER if looked is None else looked

    def pump(m: re.Match[str]) -> str:
        power, toughness = int(m.group("p")) * n, int(m.group("t")) * n
        return f"{m.group('verb')} {power:+d}/{toughness:+d}{m.group('mid')}"

    return _FOR_EACH_SCRIED.sub(pump, text)


_REMOVED_WHERE_X = re.compile(
    r",? where X is the number of (?:(?:\+1/\+1|-1/-1|[a-z]+) )?counters? removed this way"
    r"(?=[.,]|$)",
    re.IGNORECASE,
)
_FOR_EACH_REMOVED = re.compile(
    r"\bfor each counter removed(?: this way)?, (?P<who>[^.]*?) (?P<verb>gets?) "
    r"(?P<p>[+-]\d+)/(?P<t>[+-]\d+)(?P<mid>(?: until end of turn)?)",
    re.IGNORECASE,
)


def _counters_removed_text(text: str) -> str:
    """The number of counters the ability's cost removed (Blademane Baku's
    "Remove X ki counters: For each counter removed, this creature gets +2/+0",
    Ooze Flux's "an X/X Ooze, where X is the number of +1/+1 counters removed
    this way") read as the number announced with the cost (CR 107.3a, CR 118.3);
    `PLACEHOLDER` when classifying."""
    removed = _REMOVED.get()
    n = PLACEHOLDER if removed is None else removed
    where = _REMOVED_WHERE_X.search(text)
    if where is not None:
        rest = text[: where.start()] + text[where.end() :]
        text = re.sub(r"\bX\b", str(n), rest)

    def pump(m: re.Match[str]) -> str:
        p, t = int(m.group("p")) * n, int(m.group("t")) * n
        return f"{m.group('who')} {m.group('verb')} {p:+d}/{t:+d}{m.group('mid')}"

    return _FOR_EACH_REMOVED.sub(pump, text)


def _placed_first(text: str) -> tuple[str, int] | None:
    """The kind and number of counters a leading "Put <n> <kind> counter(s) on
    <itself>, then ..." instruction adds before the rest of the text is read."""
    match = re.match(
        rf"\s*put (?P<n>an?|one|two|three|\d+) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? "
        rf"on {_self()}[,.] then ",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    word = match.group("n").lower()
    number = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3}.get(word)
    return match.group("kind").lower(), number if number is not None else int(word)


@functools.cache
def _put_for_each_controlled(names: tuple[str, ...] = ()) -> re.Pattern[str]:
    # "put a loyalty counter on this permanent for each creature you control"
    return re.compile(
        rf"\bput (?:a|an|one) (?P<ck>\+1/\+1|-1/-1|[a-z]+) counter on {_self()}"
        rf" for each (?P<other>other )?(?P<noun>[a-z]+) you control\b",
        re.IGNORECASE,
    )


def counters_counted_text(text: str, names: tuple[str, ...] = ()) -> str:
    """`text` with each "number of <kind> counters on <the source>" phrase read
    as the number it is now (CR 122.1, CR 608.2h); unchanged when it has none.

    `names` are the strings the card's own text uses to mean itself (CR 201.5)."""
    if names and "counter" in text.lower():
        return _restored(_counted_tokenised(_tokenised(text, names)), names)
    return _counted_tokenised(text)


def _counted_tokenised(text: str) -> str:
    lowered = text.lower()
    if "scrying this way" in lowered:
        text = _for_each_scried(text)
    if "removed" in lowered and not re.search(r"\bremove\b", lowered):
        # Removed by the ability's cost, not by an instruction of its own text
        # (which counts what it removed itself).
        text = _counters_removed_text(text)
    if "counter" not in lowered or " on " not in lowered:
        return text

    placed = _placed_first(text)

    def n_of(match: re.Match[str]) -> int:
        kind = _kind(match.group("kind"))
        # CR 608.2c: the instructions run in order, so a count read after "Put a
        # charge counter on this artifact, then ..." includes that counter, which
        # the live board does not hold until the first instruction has run.
        extra = placed[1] if placed is not None and kind in (None, placed[0]) else 0
        return _counted(kind) + extra

    where = _where_x().search(text)
    if where is not None:
        number = n_of(where)
        rest = text[: where.start()] + text[where.end() :]
        text = re.sub(r"\bX\b", str(number), rest)
    text = _a_number_of_counters().sub(lambda m: _plural(n_of(m), f"{m.group('ck')} counter"), text)
    equal = _equal_to().search(text)
    if equal is not None:
        # "... and that much damage to up to one target creature" repeats the
        # amount the first half was just read as (CR 608.2c).
        number = n_of(equal)
        text = _equal_to().sub(lambda m: f"{number} {m.group('what')}", text)
        text = re.sub(r"\bthat much (damage|life)\b", rf"{number} \1", text)
    text = _number_of().sub(lambda m: str(n_of(m)), text)

    def pump(m: re.Match[str]) -> str:
        n = n_of(m)
        power, toughness = int(m.group("p")) * n, int(m.group("t")) * n
        return f"{m.group('verb')} {power:+d}/{toughness:+d}{m.group('mid')}"

    text = _for_each_pump().sub(pump, text)

    def verb_noun(m: re.Match[str]) -> str:
        n = n_of(m)
        return f"{m.group('verb')} {_plural(n, m.group('noun'))}{m.group('mid')}"

    text = _for_each_verb().sub(verb_noun, text)

    def put_counters(m: re.Match[str]) -> str:
        n = n_of(m)
        return f"{m.group('verb')} {_plural(n, m.group('ck') + ' counter')}{m.group('mid')}"

    text = _for_each_put().sub(put_counters, text)

    def targets(m: re.Match[str]) -> str:
        n = n_of(m)
        noun = m.group("noun")
        wording = "one target " + noun if n == 1 else f"{n} target {noun}s"
        return f"{m.group('verb')} up to {wording}{m.group('tail')}"

    text = _for_each_target().sub(targets, text)

    def put_for_each(m: re.Match[str]) -> str:
        # CR 122.1: the same count "where X is the number of <things> you control"
        # the put-X-counters reader already knows, in the plural it wants.
        return (
            f"put X {m.group('ck')} counters on this permanent, where X is the number of "
            f"{m.group('other') or ''}{m.group('noun')}s you control"
        )

    return _put_for_each_controlled().sub(put_for_each, text)


def counters_self_reference_normalised(text: str, names: tuple[str, ...]) -> str:
    """`text` with a card's own name after "counters on" read as CR 700.7's
    "this permanent" ("the number of charge counters on The Eternity Elevator",
    "a verse counter on Yisan"), so the mana-ability reader and every counter
    reader see the one self-reference they already know (CR 201.5)."""
    if "counter" not in text.lower() or not names:
        return text
    named = "|".join(re.escape(name) for name in names)
    return re.sub(rf"(\bcounters? on )(?:{named})\b", r"\1this permanent", text)


def counters_mana_lines_self_normalised(text: str, names: tuple[str, ...]) -> str:
    """`counters_self_reference_normalised` for the parts of `text` a counter
    count reads: the cost of an activated ability ("Put a verse counter on
    Yisan:") and the whole of a mana ability (CR 605.1a: "{T}: Add X mana ...,
    where X is the number of charge counters on <its own name>"). The effect
    half of any other line keeps the name it prints."""
    return "\n".join(map(lambda line: _normalised_line(line, names), text.split("\n")))


def _normalised_line(line: str, names: tuple[str, ...]) -> str:
    cost, colon, effect = line.partition(":")
    if not colon:
        return line
    if ": add " in line.lower():
        return counters_self_reference_normalised(line, names)
    if names:
        named = "|".join(re.escape(name) for name in names)
        effect = re.sub(
            rf"(\bnumber of (?:\+1/\+1 |-1/-1 |[a-z]+ )?counters? on )(?:{named})\b",
            r"\1this permanent",
            effect,
        )
    return counters_self_reference_normalised(cost, names) + colon + effect


def counters_counted_for(text: str, source, names: tuple[str, ...]) -> str:
    """`counters_counted_text` with each count read off `source` right now - the
    form a target announcement needs (CR 601.2c: "for each isolation counter on
    it, exile up to one target ..." names as many targets as there are counters
    as the ability goes on the stack)."""
    with counters_read_from(source):
        return counters_counted_text(text, names)
