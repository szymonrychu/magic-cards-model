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

from ..numbers import parse_count
from .amount_sentences import (
    cards_for_each_pattern,
    parse_put_counters,
    pump_for_each_pattern,
    put_counters_pattern,
    where_x_markers,
    write_x,
)
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
    # The card's own name is swapped for a `\x00<index>x` token before the
    # patterns run (`_tokenised`), so each pattern compiles once, not per card.
    return r"(?:it|this [a-z]+|\x00\d+x)"


def _tokenised(text: str, names: tuple[str, ...]) -> str:
    """`text` with the card's own name after "on " as a name-independent token."""
    for index, name in enumerate(names):
        token = f"\x00{index}x"
        text = re.sub(rf"(\bon ){re.escape(name)}\b", lambda m, t=token: m.group(1) + t, text)
    return text


def _restored(text: str, names: tuple[str, ...]) -> str:
    return re.sub(r"\x00(\d+)x", lambda m: names[int(m.group(1))], text)


@functools.cache
def _where_x(names: tuple[str, ...] = ()) -> re.Pattern[str]:
    # The expression of a ", where X is ..." (`amount_sentences.where_x_markers`).
    return re.compile(
        rf"the number of {_KIND}{_COUNTERS} on {_self()}(?=[.,]|$)",
        re.IGNORECASE,
    )


def _where_x_split(text: str, expression: re.Pattern[str]) -> tuple[int, re.Match[str]] | None:
    """The first ", where X is <expression>" in `text`: where its marker
    starts, and the expression's match."""
    for marker in where_x_markers(text):
        found = expression.match(text, marker.end())
        if found is not None:
            return marker.start(), found
    return None


@functools.cache
def _number_of(names: tuple[str, ...] = ()) -> re.Pattern[str]:
    # "Double the number of +1/+1 counters on it" (CR 122.1) doubles the stack; it
    # does not ask for the count, so the doubling readers keep the phrase whole.
    return re.compile(
        rf"(?<!double )(?<!triple )the number of {_KIND}{_COUNTERS} on {_self()}\b", re.IGNORECASE
    )


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
        rf"\b{pump_for_each_pattern(rf'{_KIND}{_COUNTERS} on {_self()}')}\b", re.IGNORECASE
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
    each = rf"{_KIND}{_COUNTERS} on {_self()}"
    return re.compile(
        rf"\b(?P<verb>discards?|draws?|mills?) "
        rf"{cards_for_each_pattern(each, count='a|an|one', noun='card', mid='[^.,]*?')}\b",
        re.IGNORECASE,
    )


_COUNTED_KIND = r"(?:(?:\+1/\+1|-1/-1|[a-z]+) )?"
_EACH_KIND_RE = re.compile(rf"^(?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?{_COUNTERS} on ", re.IGNORECASE)


@functools.cache
def _for_each_put(names: tuple[str, ...] = ()) -> re.Pattern[str]:
    # "put a -1/-1 counter on target creature for each -1/-1 counter on this
    # creature": `amount_sentences`' put-counters wording, counting the source's.
    return re.compile(
        rf"\b{put_counters_pattern(rf'{_COUNTED_KIND}{_COUNTERS} on {_self()}')}\b",
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
    rf"\b{pump_for_each_pattern('card looked at while scrying this way')}\b", re.IGNORECASE
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
    r"the number of (?:(?:\+1/\+1|-1/-1|[a-z]+) )?counters? removed this way(?=[.,]|$)",
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
    where = _where_x_split(text, _REMOVED_WHERE_X)
    if where is not None:
        text = write_x(text[: where[0]] + text[where[1].end() :], n)

    def pump(m: re.Match[str]) -> str:
        p, t = int(m.group("p")) * n, int(m.group("t")) * n
        return f"{m.group('who')} {m.group('verb')} {p:+d}/{t:+d}{m.group('mid')}"

    return _FOR_EACH_REMOVED.sub(pump, text)


def _placed_first(text: str) -> tuple[str, int] | None:
    """The kind and number of counters a leading "Put <n> <kind> counter(s) on
    <itself>, then ..." instruction adds before the rest of the text is read."""
    lead = re.match(r"\s*(?P<put>[^.,]+)[,.] then ", text, re.IGNORECASE)
    put = None if lead is None else parse_put_counters(lead.group("put"))
    if put is None or put.x or put.each is not None:
        return None
    if re.fullmatch(_self(), put.on, re.IGNORECASE) is None:
        return None
    return put.kind.lower(), put.n


def counters_counted_text(text: str, names: tuple[str, ...] = ()) -> str:
    """`text` with each "number of <kind> counters on <the source>" phrase read
    as the number it is now (CR 122.1, CR 608.2h); unchanged when it has none.

    `names` are the strings the card's own text uses to mean itself (CR 201.5)."""
    if '"' in text:
        # A granted ability's own count ("gains "... equal to the number of lore
        # counters on it"") is read when that ability applies, not now (CR 611.3a).
        return "".join(
            piece if index % 2 else counters_counted_text(piece, names)
            for index, piece in enumerate(re.split(r'("[^"]*")', text))
        )
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

    where = _where_x_split(text, _where_x())
    if where is not None:
        number = n_of(where[1])
        text = write_x(text[: where[0]] + text[where[1].end() :], number)
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
        if m.group("on").strip().lower() == "it":
            # "Put a counter on it for each <kind> counter on this enchantment"
            # (Alien Invasion): "it" is the token just created, not the object
            # counted, and its own reader counts the source's counters after
            # the token exists.
            return m.group(0)
        unit = parse_count(m.group("count"))
        counted = _EACH_KIND_RE.match(m.group("each"))
        if unit is None or counted is None:
            return m.group(0)
        n = unit * n_of(counted)
        return f"{m.group('verb')} {_plural(n, m.group('kind') + ' counter')} on {m.group('on')}"

    text = _for_each_put().sub(put_counters, text)

    def targets(m: re.Match[str]) -> str:
        n = n_of(m)
        noun = m.group("noun")
        wording = "one target " + noun if n == 1 else f"{n} target {noun}s"
        return f"{m.group('verb')} up to {wording}{m.group('tail')}"

    return _for_each_target().sub(targets, text)


def counters_self_reference_normalised(text: str, names: tuple[str, ...]) -> str:
    """`text` with a card's own name after "counters on" read as CR 700.7's
    "this permanent" ("the number of charge counters on The Eternity Elevator",
    "a verse counter on Yisan"), so the mana-ability reader and every counter
    reader see the one self-reference they already know (CR 201.5)."""
    if "counter" not in text.lower() or not names:
        return text
    named = "|".join(re.escape(name) for name in names)
    return re.sub(rf"(\bcounters? on )(?:{named})\b", r"\1this permanent", text)


def counters_counted_for(text: str, source, names: tuple[str, ...]) -> str:
    """`counters_counted_text` with each count read off `source` right now - the
    form a target announcement needs (CR 601.2c: "for each isolation counter on
    it, exile up to one target ..." names as many targets as there are counters
    as the ability goes on the stack)."""
    with counters_read_from(source):
        return counters_counted_text(text, names)


# -- the player chooses which counters come off, and from which permanents

#: The mode that ends an "up to N" removal early (CR 608.2d: up to N includes
#: fewer, none included).
STOP_REMOVING = "no more counters"


def choose_counters_to_remove(game, ability, target, limit: int) -> int:
    """Remove up to `limit` counters from `target`, one at a time, each time
    asking the ability's controller which kind comes off next (CR 122.1: any
    kind is a counter; CR 608.2d: the controller chooses as it resolves) or to
    stop. The first option is the kind the target holds most of, so an
    unscripted player removes the most counters. Returns how many came off."""
    from .decisions import Decision, DecisionKind, source_id_of

    order = sorted(target.counters, key=lambda kind: -target.counter_count(kind))
    controller = game.controller_of(ability).username
    removed = 0
    while removed < limit:
        kinds = tuple(str(kind) for kind in order if target.counter_count(kind) > 0)
        if not kinds:
            break
        answer = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_MODE,
                player=controller,
                prompt=(
                    f"choose the kind of counter to remove from {target.name} "
                    f"({limit - removed} more allowed)"
                ),
                source=ability.name,
                source_id=source_id_of(ability),
                options=(*kinds, STOP_REMOVING),
            )
        )
        if answer not in kinds:
            break
        target.remove_counters(answer, 1)
        removed += 1
    return removed


def choose_removal_allocation(
    game, payer: str, candidates, have: Callable, total: int, *, source=None, source_id=None
) -> list:
    """Which permanent each of `total` counters comes off, as a cost
    "Remove N counters from among creatures you control" is paid (CR 118.3,
    CR 601.2b/h): one question per counter over the permanents still holding
    one, so the payer decides both which permanents and how many from each.
    The first permanent offered is the first in battlefield order, so an
    unscripted payer drains permanents front to back. Returns the permanents
    chosen, one entry per counter."""
    from .decisions import Decision, DecisionKind

    left = {card.id: have(card) for card in candidates}
    picks: list = []
    for _ in range(total):
        offered = [card for card in candidates if left[card.id] > 0]
        if len(offered) > 1:
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=payer,
                    prompt=f"remove a counter from which permanent? ({total - len(picks)} to go)",
                    source=source,
                    source_id=source_id,
                    amount=1,
                    cards=tuple(card.id for card in offered),
                    default_cards=(offered[0].id,),
                )
            )
            by_id = {card.id: card for card in offered}
            pick = by_id[answer[0]]
        else:
            pick = offered[0]
        left[pick.id] -= 1
        picks.append(pick)
    return picks
