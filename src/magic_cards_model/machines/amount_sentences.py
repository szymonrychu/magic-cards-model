"""Amount sentences: one reader per printed shape of an instruction that
spends an amount, and the one resolver for the player it names.

    <who> gains/loses N life | life equal to <expr> | N life for each <each> | X life
    <who> mills N cards | cards equal to <expr> | X cards
    <who> draws/discards N cards | cards equal to <expr> | X cards
    <source> deals N damage to <to> | damage equal to <expr> to <to>
                                    | damage to <to> equal to <expr>
    put N/X <kind> counters on <object> [for each <each>]
    add {M} for each <each>
    <body with X>, where X is <expr>

Each shape is read here, once. The modules that spend an amount supply only
their own amount - what an earlier instruction moved this way, a graveyard
count, a counted group, the counters on an object, a referenced or moved
object's characteristic, the life lost this turn - as a pluggable reader, and
apply it through the helpers below, so no two readers of one wording can
disagree, or both apply.

Every amount is taken once, as the instruction is applied, before the
instruction changes what it reads (CR 608.2h). Players who act at the same
time do so in APNAP order (CR 101.4).
"""

import functools
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.player import Player
from ..models.zone import Zone
from ..numbers import COUNT, halve, parse_count, parse_multiplier

if TYPE_CHECKING:
    from ..models.game import Game

#: One player-specific amount: `(game, stack_object, recipient) -> int`.
Amount = Callable[["Game", Any, Player], int]


def clean(sentence: str) -> str:
    """`sentence` with straight apostrophes, single spaces and no closing full
    stop - case kept."""
    return " ".join(sentence.replace("’", "'").split()).rstrip(".").strip()


# --------------------------------------------------------------------------
# ", where X is <expr>"
# --------------------------------------------------------------------------

_WHERE_X_RE = re.compile(r"(?:,\s*|\s+)where x is\s+", re.IGNORECASE)


def where_x_markers(text: str) -> Iterator[re.Match[str]]:
    """Every ", where X is " in `text`; the expression starts at `match.end()`."""
    return _WHERE_X_RE.finditer(text)


def split_where_x(sentence: str) -> tuple[str, str] | None:
    """`(body, tail)` of "<body>, where X is <tail>", or `None`. The tail is
    everything after the marker; a caller whose expression is followed by
    more text reads where it ends."""
    match = _WHERE_X_RE.search(sentence)
    if match is None:
        return None
    body = sentence[: match.start()].strip()
    tail = sentence[match.end() :].strip().rstrip(".").strip()
    if not body or not tail:
        return None
    return body, tail


#: ", where X is <expr>" closing its sentence anywhere in a multi-sentence text:
#: an optional "twice " / "three times " in front of the expression and an
#: optional "as this ability/spell resolves" after it are not part of it.
_WHERE_X_SENTENCE_RE = re.compile(
    r",\s*where X is (?P<mult>twice |three times )?(?P<expr>[^.]+?)"
    r"(?: as (?:this (?:ability|spell) resolves|it resolves))?(?=\.(?:\s|$)|$)",
    re.IGNORECASE,
)
_MULTIPLIER_WORDS = {"twice ": 2, "three times ": 3}


@dataclass(frozen=True)
class WhereXDefinition:
    """A ", where X is <expr>" found inside a multi-sentence text: the
    definition's expression and multiplier, and the text on either side of it."""

    expr: str
    multiplier: int
    before: str
    after: str

    @property
    def rest(self) -> str:
        """The text without the definition - the part that uses X."""
        return self.before + self.after

    def uses_x(self, rest: str | None = None) -> bool:
        return re.search(r"\bX\b", self.rest if rest is None else rest, re.IGNORECASE) is not None


def find_where_x(text: str) -> WhereXDefinition | None:
    """The ", where X is <expr>" closing a sentence of `text`, or `None`. X is
    measured once as the object resolves and written into the rest of the text
    as a number (CR 608.2h, CR 107.3a); this is the one place that finds the
    definition, for every module that measures it differently."""
    match = _WHERE_X_SENTENCE_RE.search(text)
    if match is None:
        return None
    multiplier = _MULTIPLIER_WORDS.get((match.group("mult") or "").lower(), 1)
    return WhereXDefinition(
        match.group("expr").strip(), multiplier, text[: match.start()], text[match.end() :]
    )


def write_x(body: str, n: int) -> str:
    """`body` with every X written as `n`."""
    return re.sub(r"\bX\b", str(n), body, flags=re.IGNORECASE)


# --------------------------------------------------------------------------
# The player a subject names
# --------------------------------------------------------------------------

#: The subjects `resolve_recipients` reads.
RECIPIENT_WORDS = frozenset(
    {
        "you",
        "target player",
        "target opponent",
        "each opponent",
        "each other player",
        "each player",
        "that player",
        "they",
    }
)


def resolve_recipients(
    game: "Game",
    stack_object: Any,
    who: str,
    controller: str,
    *,
    targets: list[Any] | None = None,
    fallback: tuple[str, ...] = (),
) -> list[Player]:
    """The players `who` names, in APNAP order (CR 101.4).

    "you" is the controller (CR 109.5); "each opponent" / "each other player"
    every other player still in the game; "target ..." the chosen players
    (`targets` when the caller walks its own target list); "that player" /
    "they" the chosen player, else `fallback` (a caller's own antecedent),
    else the player the trigger event concerns."""
    who = who.lower()
    if who == "you":
        return [game.player(controller)]
    from .effects._common import _players_in_apnap_order

    if who == "each player":
        return list(_players_in_apnap_order(game))
    if who in ("each opponent", "each other player"):
        return [player for player in _players_in_apnap_order(game) if player.username != controller]
    pool = game.resolve_targets(stack_object) if targets is None else targets
    chosen = [target for target in pool if isinstance(target, Player)]
    if who.startswith("target"):
        return chosen
    if who in ("that player", "they"):
        if chosen:
            return chosen[:1]
        if fallback:
            return [game.player(fallback[0])]
        event = getattr(stack_object, "event", None)
        if event is not None and event.player is not None:
            return [game.player(event.player)]
    return []


def controller_of(game: "Game", stack_object: Any) -> str:
    return game.controller_of(stack_object).username


def source_card(game: "Game", stack_object: Any) -> CardState | None:
    """The resolving spell itself, or an ability's source."""
    if isinstance(stack_object, CardState):
        return stack_object
    return stack_object.source(game)


# --------------------------------------------------------------------------
# Life (CR 119.3)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LifeClause:
    """ "<subject> gains/loses <amount>".

    `kind` is "fixed" (`n` life), "equal" (life equal to `expr`), "for_each"
    (`n` life for each `expr`), "x" (`n` times X life; `expr` is the
    where-X expression, `None` for the announced X) or "half" (half of the recipient's own
    life total, CR 107.1a: `n` is 1 when the card rounds up, 0 when it rounds down)."""

    subject: str | None
    verb: str
    gains: bool
    kind: str
    n: int
    expr: str | None

    @property
    def who(self) -> str:
        return (self.subject or "").lower()


_LIFE_RE = re.compile(
    rf"^(?:(?P<subject>.+?) )?(?P<verb>gains?|loses?) "
    rf"(?:(?P<each_n>{COUNT}) life for each (?P<each>.+)"
    r"|life equal to (?P<expr>.+)"
    r"|(?P<half>half (?:their|your)) life(?:, rounded (?P<direction>up|down))?"
    r"|(?P<mult>[a-z0-9]+ times |twice )?(?P<x>x) life"
    rf"|(?P<fmult>[a-z0-9]+ times |twice )(?P<fn>{COUNT}) life"
    rf"|(?P<n>{COUNT}) life)$",
    re.IGNORECASE,
)


@functools.cache
def parse_life_clause(text: str) -> LifeClause | None:
    """The life change `text` prints, or `None`."""
    sentence = clean(text)
    if " life" not in sentence.lower():
        return None
    where = None
    if (split := split_where_x(sentence)) is not None:
        sentence, where = split
    match = _LIFE_RE.fullmatch(sentence)
    if match is None:
        return None
    if where is not None and match.group("x") is None:
        return None
    subject, verb = match.group("subject"), match.group("verb")
    gains = verb.lower().startswith("gain")
    if match.group("each") is not None:
        unit = parse_count(match.group("each_n"))
        if unit is None:
            return None
        return LifeClause(subject, verb, gains, "for_each", unit, match.group("each"))
    if match.group("expr") is not None:
        return LifeClause(subject, verb, gains, "equal", 1, match.group("expr"))
    if match.group("half") is not None:
        rounds_up = (match.group("direction") or "").lower() == "up"
        return LifeClause(subject, verb, gains, "half", int(rounds_up), None)
    if match.group("x") is not None:
        multiplier = 1
        if match.group("mult"):
            found = parse_multiplier(match.group("mult").strip())
            if found is None:
                return None
            multiplier = found
        return LifeClause(subject, verb, gains, "x", multiplier, where)
    if match.group("fn") is not None:
        # "twice 3 life": an X already written in as a number (a modal spell's mode text).
        base, factor = (
            parse_count(match.group("fn")),
            parse_multiplier(match.group("fmult").strip()),
        )
        if base is None or factor is None:
            return None
        return LifeClause(subject, verb, gains, "fixed", base * factor, None)
    fixed = parse_count(match.group("n"))
    if fixed is None:
        return None
    return LifeClause(subject, verb, gains, "fixed", fixed, None)


def change_life(game: "Game", players: list[Player], amounts: list[int], gains: bool) -> int:
    """Each player gains or loses their amount (a non-positive one is none);
    returns the total by which life totals really moved."""
    moved = 0
    for player, amount in zip(players, amounts, strict=True):
        if amount <= 0:
            continue
        before = player.life
        if gains:
            game.gain_life(player, amount)
        else:
            game.lose_life(player, amount)
        moved += abs(player.life - before)
    return moved


def apply_life(
    game: "Game",
    stack_object: Any,
    who: str,
    gains: bool,
    amount: Amount,
    *,
    targets: list[Any] | None = None,
    fallback: tuple[str, ...] = (),
) -> int:
    """`who` gains or loses `amount` each: every amount is read before any
    life moves (CR 608.2h). Returns the total life moved."""
    controller = controller_of(game, stack_object)
    players = resolve_recipients(
        game, stack_object, who, controller, targets=targets, fallback=fallback
    )
    amounts = [amount(game, stack_object, player) for player in players]
    return change_life(game, players, amounts, gains)


# --------------------------------------------------------------------------
# Mill (CR 701.17a)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MillClause:
    """ "<subject> mills <amount>": `kind` "fixed" (`n` cards), "equal"
    (cards equal to `expr`) or "x" (X cards, `expr` the where-X
    expression)."""

    subject: str | None
    kind: str
    n: int
    expr: str | None

    @property
    def who(self) -> str:
        return (self.subject or "").lower()


_MILL_RE = re.compile(
    rf"^(?:(?P<subject>.+?) )?mills? "
    rf"(?:(?P<x>x) cards?|cards equal to (?P<expr>.+)|(?P<n>{COUNT}) cards?)$",
    re.IGNORECASE,
)


@functools.cache
def parse_mill_clause(text: str) -> MillClause | None:
    """The mill `text` prints, or `None`."""
    sentence = clean(text)
    if "mill" not in sentence.lower():
        return None
    where = None
    if (split := split_where_x(sentence)) is not None:
        sentence, where = split
    match = _MILL_RE.fullmatch(sentence)
    if match is None:
        return None
    subject = match.group("subject")
    if match.group("x") is not None:
        return None if where is None else MillClause(subject, "x", 1, where)
    if where is not None:
        return None
    if match.group("expr") is not None:
        return MillClause(subject, "equal", 1, match.group("expr"))
    fixed = parse_count(match.group("n"))
    return None if fixed is None else MillClause(subject, "fixed", fixed, None)


def mill_players(game: "Game", players: list[Player], amounts: list[int]) -> None:
    from .effects.library import _mill

    for player, amount in zip(players, amounts, strict=True):
        if amount > 0:
            _mill(game, player, amount)


def apply_mill(
    game: "Game",
    stack_object: Any,
    who: str,
    amount: Amount,
    *,
    targets: list[Any] | None = None,
    fallback: tuple[str, ...] = (),
) -> None:
    """`who` mills `amount` each, every amount read before any card moves."""
    controller = controller_of(game, stack_object)
    players = resolve_recipients(
        game, stack_object, who, controller, targets=targets, fallback=fallback
    )
    mill_players(game, players, [amount(game, stack_object, player) for player in players])


# --------------------------------------------------------------------------
# Draw and discard
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CardsClause:
    """ "<subject> draws/discards <amount>": `kind` "fixed", "equal" or "x"."""

    subject: str | None
    draws: bool
    kind: str
    n: int
    expr: str | None

    @property
    def who(self) -> str:
        return (self.subject or "").lower()


_CARDS_RE = re.compile(
    rf"^(?:then )?(?:(?P<subject>.+?) )?(?P<verb>draws?|discards?) "
    rf"(?:cards equal to (?P<expr>.+)|(?P<x>x) cards|(?P<n>{COUNT}) cards?)$",
    re.IGNORECASE,
)


@functools.cache
def parse_cards_clause(text: str) -> CardsClause | None:
    """The draw or discard `text` prints, or `None`."""
    match = _CARDS_RE.fullmatch(clean(text))
    if match is None:
        return None
    draws = match.group("verb").lower().startswith("draw")
    if match.group("expr") is not None:
        return CardsClause(match.group("subject"), draws, "equal", 1, match.group("expr"))
    if match.group("x") is not None:
        return CardsClause(match.group("subject"), draws, "x", 1, None)
    fixed = parse_count(match.group("n"))
    if fixed is None:
        return None
    return CardsClause(match.group("subject"), draws, "fixed", fixed, None)


# --------------------------------------------------------------------------
# Damage
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DamageClause:
    """ "<source> deals <amount> to <to>": `expr` for "damage equal to
    <expr>" in either order, else the fixed `n`."""

    source: str
    to: str
    n: int
    expr: str | None


_DAMAGE_RE = re.compile(
    rf"^(?P<source>.+?) deals? (?:damage equal to (?P<expr>.+?) to (?P<to>.+)"
    r"|damage to (?P<to_b>.+?) equal to (?P<expr_b>.+)"
    rf"|(?P<n>{COUNT}) damage to (?P<to_n>.+))$",
    re.IGNORECASE,
)


@functools.cache
def parse_damage_clause(text: str) -> DamageClause | None:
    """The damage `text` prints, or `None`."""
    match = _DAMAGE_RE.fullmatch(clean(text))
    if match is None:
        return None
    source = match.group("source")
    if match.group("expr") is not None:
        return DamageClause(source, match.group("to"), 1, match.group("expr"))
    if match.group("expr_b") is not None:
        return DamageClause(source, match.group("to_b"), 1, match.group("expr_b"))
    fixed = parse_count(match.group("n"))
    return None if fixed is None else DamageClause(source, match.group("to_n"), fixed, None)


# --------------------------------------------------------------------------
# Counters (CR 122.1)
# --------------------------------------------------------------------------

#: A counter kind as printed.
COUNTER_KIND = r"[+-]\d+/[+-]\d+|[a-z]+"
#: "this creature", "this permanent": the source itself (CR 109.5's "this").
_SELF_RE = re.compile(r"^this [a-z]+$", re.IGNORECASE)


@dataclass(frozen=True)
class PutCounters:
    """ "put <n|X> <kind> counters on <on> [for each <each>]"; `x` is True for
    X, `expr` the where-X expression."""

    n: int
    x: bool
    kind: str
    on: str
    each: str | None
    expr: str | None

    @property
    def on_self(self) -> bool:
        return _SELF_RE.fullmatch(self.on) is not None


def put_counters_pattern(each: str = r"[^.]+") -> str:
    """The "put N <kind> counter(s) on <on> for each <each>" wording, with
    `each` the counted phrase a caller searches for."""
    return (
        rf"(?P<verb>puts?|distributes?) (?P<count>x|{COUNT}) (?P<kind>{COUNTER_KIND}) counters? "
        rf"on (?P<on>[^.,]+?) for each (?P<each>{each})"
    )


_PUT_RE = re.compile(
    rf"^(?:then )?(?:{put_counters_pattern()}"
    rf"|(?P<verb_b>puts?) (?P<count_b>x|{COUNT}) (?P<kind_b>{COUNTER_KIND}) counters? "
    r"on (?P<on_b>.+))$",
    re.IGNORECASE,
)


_PUT_NUMBER_OF_RE = re.compile(
    rf"^(?P<verb>puts?) a number of (?P<kind>{COUNTER_KIND}) counters on (?P<on>.+?) "
    r"equal to (?P<expr>.+)$",
    re.IGNORECASE,
)


@functools.cache
def parse_put_counters(text: str) -> PutCounters | None:
    """The counters `text` puts, or `None`. "Put a number of +1/+1 counters on
    target creature equal to <amount>" reads as "put X ... counters, where X is
    <amount>"."""
    sentence = clean(text)
    where = None
    if (number_of := _PUT_NUMBER_OF_RE.fullmatch(sentence)) is not None:
        sentence = f"{number_of['verb']} x {number_of['kind']} counters on {number_of['on']}"
        where = number_of["expr"]
    elif (split := split_where_x(sentence)) is not None:
        sentence, where = split
    match = _PUT_RE.fullmatch(sentence)
    if match is None:
        return None
    if match.group("verb") is not None:
        count, kind, on, each = match.group("count", "kind", "on", "each")
    else:
        count, kind, on = match.group("count_b", "kind_b", "on_b")
        each = None
    x = count.lower() == "x"
    if x != (where is not None):
        return None
    n = 1 if x else parse_count(count)
    if n is None:
        return None
    return PutCounters(n, x, kind, on, each, where)


def put_counters_on_source(
    game: "Game", stack_object: Any, kind: str, amount: int, source: CardState | None = None
) -> None:
    """`amount` counters of `kind` on the resolving object's source while it
    is still on the battlefield (CR 122.1)."""
    from .effects.counters import _counter_kind

    source = source_card(game, stack_object) if source is None else source
    if amount > 0 and source is not None and source.zone is Zone.BATTLEFIELD:
        game.add_counters(source, _counter_kind(kind), amount)


def self_counters_for_each_effect(
    text: str, *, for_spell: bool
) -> "Callable[[Game, Any], None] | None":
    """ "put a +1/+1 counter on this creature for each creature card in your
    graveyard", "put a loyalty counter on this permanent for each creature you
    control": counters on the ability's own source (CR 122.1), the count read
    by `_for_each_multiplier` once as it applies (CR 608.2h). A source that
    has left the battlefield gets none."""
    if for_spell or " for each " not in text.lower():
        return None
    put = parse_put_counters(text)
    if put is None or put.x or put.each is None or not put.on_self:
        return None
    if "this way" in put.each.lower():
        return None  # what an earlier instruction moved is the this-way ledger's count
    from .decisions import source_id_of
    from .effects.amounts import _for_each_multiplier

    reader = _for_each_multiplier(put.each)
    if reader is None:
        return None
    unit, kind = put.n, put.kind

    def effect(game: "Game", stack_object: Any) -> None:
        amount = unit * reader(game, stack_object.controller, source_id_of(stack_object))
        put_counters_on_source(game, stack_object, kind, amount, stack_object.source(game))

    return effect


# --------------------------------------------------------------------------
# Per-unit amounts multiplied by a count: "gets +1/+1 for each ...",
# "draws a card for each ..."
# --------------------------------------------------------------------------


def pump_for_each_pattern(each: str = r"[^.]+?") -> str:
    """ "get(s) +P/+T [until end of turn] for each <each>", with `each` the
    counted phrase a caller reads."""
    return (
        r"(?P<verb>gets?) (?P<p>[+-]\d+)/(?P<t>[+-]\d+)(?P<mid>(?: until end of turn)?)"
        rf" for each (?P<each>{each})"
    )


def cards_for_each_pattern(
    each: str = r"[^.]+?",
    *,
    count: str = COUNT,
    noun: str = r"cards?",
    mid: str = r"[^.]*?",
) -> str:
    """ "<N> card(s)<mid> for each <each>", the per-unit number a count
    multiplies; the keyword arguments narrow it for a caller."""
    return rf"(?P<n>{count}) (?P<noun>{noun})\b(?P<mid>{mid}) for each (?P<each>{each})"


# --------------------------------------------------------------------------
# Mana (CR 106.4)
# --------------------------------------------------------------------------

_ADD_MANA_FOR_EACH_RE = re.compile(
    r"^(?:then )?add (?P<symbols>(?:\{[wubrgc]\})+|\{[wubrgc]\}(?: or \{[wubrgc]\})+)"
    r" for each (?P<each>.+)$",
    re.IGNORECASE,
)


@functools.cache
def parse_add_mana_for_each(text: str) -> tuple[str, str] | None:
    """`(symbols, counted phrase)` of "add {M} for each <each>", or `None`."""
    match = _ADD_MANA_FOR_EACH_RE.fullmatch(clean(text))
    return None if match is None else (match.group("symbols"), match.group("each"))


def add_mana_for_each_effect(text: str) -> "Callable[[Game, Any], None] | None":
    """ "add {M} for each <each>" (CR 106.4) as an effect: the count, read by
    `_for_each_multiplier` when the instruction is followed (CR 608.2h), times
    the symbols into the controller's mana pool."""
    from .decisions import source_id_of
    from .effects.amounts import _for_each_multiplier

    parsed = parse_add_mana_for_each(text)
    if parsed is None:
        return None
    symbols, each = parsed
    reader = _for_each_multiplier(each)
    if reader is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        controller = controller_of(game, stack_object)
        add_mana_times(
            game,
            controller,
            symbols,
            reader(game, controller, source_id_of(stack_object)),
            stack_object=stack_object,
        )

    return effect


def add_mana_times(
    game: "Game",
    controller: str,
    symbols: str,
    times: int,
    *,
    retain_until: Any = None,
    stack_object: Any = None,
) -> None:
    """`symbols` into the controller's mana pool `times` times, each unit tagged
    `retain_until` (`ManaRetentionScope`) when the text says the player does not
    lose it as steps and phases end (CR 500.5).

    A listed "{R} or {G}" is one mana per unit, its colour chosen for each unit
    separately as the instruction is followed (CR 608.2d; the pair is the
    palette, `_choose_a_color(colors=...)`)."""
    from ..models.card import Color
    from .decisions import source_id_of
    from .effects._common import _MANA_SYMBOL_RE
    from .effects.modal import _choose_a_color

    colors = [Color(symbol.upper()) for symbol in _MANA_SYMBOL_RE.findall(symbols)]
    player = game.player(controller)
    pool = player.mana_pool
    listed = " or " in symbols.lower()
    for _ in range(max(times, 0)):
        if listed:
            chosen = _choose_a_color(
                game,
                player,
                getattr(stack_object, "source_name", None) or getattr(stack_object, "name", ""),
                f"add {symbols}",
                source_id=source_id_of(stack_object) if stack_object is not None else None,
                colors=colors,
            )
            pool.add(chosen, retain_until=retain_until)
            continue
        for color in colors:
            pool.add(color, retain_until=retain_until)


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------

_CREATE_RE = re.compile(r"^(?:(?P<subject>.+?) )?creates? (?P<rest>.+)$", re.IGNORECASE)
_X_OVER_X_RE = re.compile(r"\bx/x\b", re.IGNORECASE)
_X_COUNT_RE = re.compile(r"^x(?=\s)", re.IGNORECASE)

#: `(game, player, amount)`: make the tokens for one player.
TokenMaker = Callable[["Game", str, int], None]


def parse_create(text: str) -> tuple[str, str] | None:
    """`(subject, what is created)` of "<subject> create(s) <rest>"; the
    subject is "" when none is printed."""
    match = _CREATE_RE.fullmatch(clean(text))
    if match is None:
        return None
    return (match.group("subject") or "").lower(), match.group("rest")


def token_maker(rest: str) -> TokenMaker | None:
    """ "a 4/4 red Dragon creature token with flying" (that many per unit of
    the amount), "an X/X colorless Phyrexian Horror artifact creature token"
    (sized by the amount) or "X 1/1 green Saproling creature tokens" (the
    amount of them) as a creator, or `None` when the descriptor is unread.
    The amount is counted once, when the instruction is applied (CR 608.2h)."""
    from ..models.token import create_tokens
    from .effects._common import _TOKEN_CLAUSE_RE
    from .effects.tokens import _token_definition_from_words

    sized = _X_OVER_X_RE.search(rest) is not None
    counted = _X_COUNT_RE.match(rest.strip()) is not None

    def definition(amount: int) -> tuple[Any, int, bool] | None:
        text = _X_OVER_X_RE.sub(f"{amount}/{amount}", rest)
        if counted:
            text = _X_COUNT_RE.sub(str(amount), text.strip())
        match = _TOKEN_CLAUSE_RE.fullmatch(text)
        if match is None:
            return None
        count = parse_count(match.group("n"))
        words = match.group("desc").strip().split()
        tapped = bool(words) and words[0].lower() == "tapped"
        if tapped:
            words = words[1:]
        if count is None or not words:
            return None
        token = _token_definition_from_words(" ".join(words), match.group("tail"))
        return None if token is None else (token, count, tapped)

    probe = definition(1)
    if probe is None:
        return None

    def make(game: "Game", player: str, amount: int) -> None:
        if amount <= 0:
            return
        if sized or counted:
            built = definition(amount)
            if built is not None:
                create_tokens(game, built[0], player, built[1], tapped=built[2])
            return
        token, per_unit, tapped = probe
        create_tokens(game, token, player, per_unit * amount, tapped=tapped)

    return make


# --------------------------------------------------------------------------
# Plain expressions read against the recipient
# --------------------------------------------------------------------------

_THEY_LOST_THIS_TURN_RE = re.compile(
    r"^(?:the )?(?:amount of )?life they(?:'ve| have)? lost this turn$", re.IGNORECASE
)


def _context(game: "Game", stack_object: Any) -> tuple[str, CardState | None, int]:
    """(controller username, the source permanent or spell, announced X)."""
    if isinstance(stack_object, CardState):
        return (
            game.controller_of(stack_object).username,
            stack_object,
            game.cast_record(stack_object).x_value,
        )
    return stack_object.controller, stack_object.source(game), stack_object.x_value


@functools.cache
def recipient_amount(expr: str) -> Amount | None:
    """`expr` as an amount read for each recipient: "the life they lost this
    turn" is the recipient's; a graveyard that is the recipient's ("their
    graveyard", "that player's graveyard") is counted for the recipient; any
    other expression `amount_expression` reads is the controller's (X is the
    announced X, CR 107.3a)."""
    from .effects.amounts import amount_expression
    from .ep02_r1_graveyard_counts import recipient_view

    if _THEY_LOST_THIS_TURN_RE.fullmatch(clean(expr)):
        return lambda _game, _obj, who: who.life_lost_this_turn
    phrase, relative = recipient_view(expr)
    reader = amount_expression(phrase)
    if reader is None:
        return None

    def amount(game: "Game", stack_object: Any, who: Player) -> int:
        controller, source, x = _context(game, stack_object)
        return int(reader(game, who.username if relative else controller, source, x))

    return amount


@functools.cache
def recipient_for_each(each: str) -> Amount | None:
    """The count of a "for each <each>" tail, read for each recipient the
    same way `recipient_amount` reads an expression."""
    from .decisions import source_id_of
    from .effects.amounts import _for_each_multiplier
    from .ep02_r1_graveyard_counts import recipient_view

    phrase, relative = recipient_view(each)
    reader = _for_each_multiplier(phrase)
    if reader is None:
        return None

    def amount(game: "Game", stack_object: Any, who: Player) -> int:
        controller = controller_of(game, stack_object)
        return int(
            reader(game, who.username if relative else controller, source_id_of(stack_object))
        )

    return amount


def life_clause_amount(clause: LifeClause, *, spell_x: bool) -> Amount | None:
    """The amount of a life clause whose expression is a plain one
    (`recipient_amount` / `recipient_for_each`), or `None`."""
    if clause.kind == "fixed":
        fixed = clause.n
        return lambda _game, _obj, _who: fixed
    if clause.kind == "equal":
        return recipient_amount(clause.expr or "")
    if clause.kind == "half":
        rounds_up = bool(clause.n)
        return lambda _game, _obj, who: halve(max(who.life, 0), round_up=rounds_up)
    if clause.kind == "for_each":
        per = recipient_for_each(clause.expr or "")
        if per is None:
            return None
        unit = clause.n
        return lambda game, obj, who: unit * per(game, obj, who)
    multiplier = clause.n
    if clause.expr is None:
        if not spell_x:
            return None
        return lambda game, obj, _who: multiplier * _context(game, obj)[2]
    inner = recipient_amount(clause.expr)
    if inner is None:
        return None
    return lambda game, obj, who: multiplier * inner(game, obj, who)
