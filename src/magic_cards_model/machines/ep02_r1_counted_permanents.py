"""EP-02 R1 T3: the counted-permanents reader.

`counted_group_reader` is the one place a counted group of permanents is read
off the live board for the shapes the older readers (`amounts.count_expression`,
`amounts._for_each_qualifier_count`) do not reach:

- a keyword qualifier before or after the control clause: "creatures with
  defender you control", "creatures you control with defender" (CR 702.3);
- a type list with a status word: "tapped artifacts, creatures, and lands you
  control" (CR 110.5 - tapped is a status, not a characteristic);
- a subtype list with "other": "other Squirrels, Bats, Lizards, and Rats you
  control" (a changeling or any permanent of two listed types counts once);
- "snow" / "nonsnow" supertype words (CR 205.4g).

The count is read off the computed board (CR 613.5), so a permanent that only
became a creature or gained defender through a continuous effect still counts.
`parse_counted_amount_text` is the whole-text companion for the clauses that
print the count after the verb ("Add {R} for each creature you control", "You
get an amount of {E} equal to the number of creatures you control", "All
creatures get -1/-1 until end of turn for each Swamp you control"): the count is
fixed once as the object resolves (CR 608.2h) and written into the text the
ordinary clause readers already understand.
"""

import functools
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from .amount_sentences import cards_for_each_pattern, pump_for_each_pattern

if TYPE_CHECKING:
    from ..models import Game

#: `(game, controller, source_id) -> int`; `source_id` is `None` where the
#: caller has no source (it only matters for "other").
CountedGroupReader = Callable[["Game", str, "str | None"], int]

_KEYWORDS = frozenset(
    {
        "defender",
        "flying",
        "reach",
        "haste",
        "vigilance",
        "trample",
        "deathtouch",
        "lifelink",
        "menace",
        "first strike",
        "double strike",
        "hexproof",
        "indestructible",
        "flash",
    }
)

_GROUP_RE = re.compile(
    r"^(?:the )?(?:number of )?"
    r"(?P<other>other )?"
    r"(?P<status>tapped |untapped )?"
    r"(?P<snow>snow |nonsnow )?"
    r"(?P<list>[A-Za-z]+(?:(?:,? (?:and/or|and|or)|,) [A-Za-z]+)*)"
    r"(?: with (?P<kw_pre>[a-z ]+?))?"
    r" (?P<whose>you control|your opponents control)"
    r"(?: with (?P<kw_post>[a-z ]+))?$",
    re.IGNORECASE,
)


_YOU_RE = re.compile(r"\byour?\b", re.IGNORECASE)


def counting_controller(game: "Game", acting: str, source_id: "str | None", each: str) -> str:
    """Whose board a "for each <group>" tail counts when the clause acts on a player
    other than the object's controller ("target opponent loses 1 life for each
    Vampire you control"): "you" is the controller of the resolving object, never
    the player the instruction is done to; "they control" is that player's."""
    if source_id is None or _YOU_RE.search(each) is None:
        return acting
    from uuid import UUID

    origin = game.find_by_id(UUID(source_id))
    return acting if origin is None or origin.controller is None else origin.controller


@functools.cache
def counted_group_reader(phrase: str) -> CountedGroupReader | None:
    """`phrase` ("creatures with defender you control") as a reader, or `None`
    when any word of it is left unread - never a partial count."""
    from .ep02_r2_counted_permanents import split_group_extras

    phrase, extras = split_group_extras(phrase)
    match = _GROUP_RE.fullmatch(phrase.strip().rstrip("."))
    if match is None:
        return None
    keyword = (match.group("kw_pre") or match.group("kw_post") or "").lower() or None
    if keyword is not None and keyword not in _KEYWORDS:
        return None
    from .effects.text import _singular_card_type, _singular_subtype_for_count_expression

    words = [
        word
        for word in re.split(r",?\s*(?:and/or|and|or)\s+|,\s*", match.group("list"), flags=re.I)
        if word
    ]
    card_types = set()
    subtypes = set()
    for word in words:
        if word.lower() in ("permanent", "permanents"):
            card_types.add(None)  # every permanent (CR 110.1)
        elif (card_type := _singular_card_type(word)) is not None:
            card_types.add(card_type)
        elif (subtype := _singular_subtype_for_count_expression(word)) is not None:
            subtypes.add(subtype)
        else:
            return None
    any_permanent = None in card_types
    other = match.group("other") is not None
    status = (match.group("status") or "").strip().lower()
    snow = (match.group("snow") or "").strip().lower()
    opponents = match.group("whose").lower() == "your opponents control"

    def count(game: "Game", controller: str, source_id: "str | None") -> int:
        from ..models import Supertype
        from .combat import has_keyword

        board = game.computed_board()
        total = 0
        for permanent in game.battlefield:
            computed = board.of(permanent)
            owner = computed.controller
            if owner is None or (owner != controller) != opponents:
                continue
            if other and source_id is not None and str(permanent.id) == str(source_id):
                continue
            if status and permanent.tapped != (status == "tapped"):
                continue
            if snow and (Supertype.SNOW in computed.supertypes) != (snow == "snow"):
                continue
            if extras is not None and not extras.matches(computed):
                continue
            if not (
                any_permanent
                or card_types & set(computed.types)
                or any(word.lower() in subtypes for word in computed.subtypes)
            ):
                continue
            if keyword is not None and not has_keyword(permanent, keyword, game):
                continue
            total += 1
        return total

    return count


# --------------------------------------------------------------------------
# Whole-text companion: a count printed after the verb.
# --------------------------------------------------------------------------

_NUMBER = r"\d+|an?|one|two|three|four|five"
#: "<head> N cards/damage<mid> for each <P>" - the older clause readers either
#: lack the verb, or cut the sentence apart at the commas and "and"s inside the
#: counted list ("tapped artifact, creature, and land you control"). Life is
#: `amount_sentences.parse_life_clause`'s.
_FOR_EACH_AMOUNT_RE = re.compile(
    rf"^(?P<head>.*?\b){cards_for_each_pattern(count=_NUMBER, noun='cards?|damage')}\.?$",
    re.IGNORECASE,
)
_PUMP_FOR_EACH_RE = re.compile(
    rf"^(?:until end of turn, )?(?P<subject>.*?) {pump_for_each_pattern()}\.?$",
    re.IGNORECASE,
)
_ENERGY_FOR_EACH_RE = re.compile(
    r"^(?:then )?(?:you )?gets? (?P<symbol>\{E\}) for each (?P<each>[^.]+?)\.?$", re.IGNORECASE
)
_ENERGY_EQUAL_RE = re.compile(
    r"^(?:then )?(?:you )?gets? an amount of (?P<symbol>\{E\}) equal to (?P<expr>[^.]+?)\.?$",
    re.IGNORECASE,
)
#: A sentence that opens with a condition or a loop is not a plain instruction.
_CONDITIONAL_OPENING_RE = re.compile(
    r"^(?:if|unless|when|whenever|for each|as long as)\b", re.IGNORECASE
)
#: A permanent spell is handed its whole oracle text, abilities included
#: (CR 608.3a: nothing there for a parser to read); an ability line is never
#: part of the spell's own resolution.
_ABILITY_LINE_RE = re.compile(r"^[^.]*:\s|^(?:when|whenever|at the beginning)\b", re.IGNORECASE)

#: `(game, stack_object) -> int`, evaluated as the object resolves (CR 608.2h).
_ObjectCount = Callable[["Game", object], int]


def _resolving_context(game: "Game", obj: object) -> "tuple[str, object, str | None]":
    """`(controller, source card, source id)` of a resolving spell or ability."""
    from ..models import CardState

    controller = game.controller_of(obj).username  # type: ignore[arg-type]
    if isinstance(obj, CardState):
        return controller, obj, str(obj.id)
    source_id = getattr(obj, "source_id", None)
    return controller, obj.source_or_last_known(game), None if source_id is None else str(source_id)  # type: ignore[attr-defined]


def _each_reader(each: str) -> _ObjectCount | None:
    from .effects.amounts import _for_each_multiplier
    from .ep02_r2_devotion_domain_party import colors_of_reference

    if (colors := colors_of_reference(each)) is not None:
        return colors  # "each of its colors" / "each of that spell's colors"

    multiplier = _for_each_multiplier(each)
    if multiplier is None:
        return None

    def read(game: "Game", obj: object) -> int:
        controller, _source, source_id = _resolving_context(game, obj)
        return multiplier(game, controller, source_id)

    return read


def _expression_reader(expr: str) -> _ObjectCount | None:
    """A "where X is <expr>" / "equal to <expr>" count that is a counted group or a
    board count (`count_expression`), never a term about the source or a referent
    ("its power", "this creature's power") - those need their own object."""
    from .effects.amounts import count_expression

    counted = count_expression(expr)
    if counted is not None:

        def read_board(game: "Game", obj: object) -> int:
            controller, _source, _source_id = _resolving_context(game, obj)
            return counted(game, controller)

        return read_board
    group = counted_group_reader(expr)
    if group is None:
        return None

    def read_group(game: "Game", obj: object) -> int:
        controller, _source, source_id = _resolving_context(game, obj)
        return group(game, controller, source_id)

    return read_group


def _targeted_pump(subject: str, power: int, toughness: int):
    """`render` for "<target subject> gets +P/+T [until end of turn] for each ...":
    the count is multiplied into a literal sentence whose layer effect (CR 611.2,
    CR 613.4c) is applied to each target still legal (CR 608.2b). The generic
    fallback reads the printed "for each" tail itself, which no spell or ability
    can resolve for a target, so the literal is built here."""
    subject = subject[:1].upper() + subject[1:]

    def render(n: int):
        from .effects.amounts import _subject_targets
        from .effects.continuous import continuous_effects, layer_context_for
        from .layers import parsed_layer_effects

        literal = f"{subject} gets {power * n:+d}/{toughness * n:+d} until end of turn."
        builder = parsed_layer_effects(literal)
        if builder is None:
            return None

        def apply(game: "Game", obj: object) -> None:
            _controller, source, _source_id = _resolving_context(game, obj)
            targets = _subject_targets(game, obj, subject)  # type: ignore[arg-type]
            if not targets:
                return
            store = continuous_effects(game)
            timestamp = store.tick()
            context = layer_context_for(game, game.controller_of(obj))  # type: ignore[arg-type]
            for built in builder(source, timestamp, targets, context):
                if built.holds(game):
                    store.add(built)

        return apply

    return render


#: "Until end of turn, you don't lose this mana as steps and phases end." - the
#: sentence after an "Add {M} for each ..." one that keeps its mana (CR 500.5).
_KEEP_MANA_RE = re.compile(
    r"^until end of (?P<scope>turn|combat), you don['’]?t lose this mana "
    r"as steps and phases end\.?$",
    re.IGNORECASE,
)


def _counted_sentence(
    sentence: str, retention: object = None
) -> "tuple[_ObjectCount, Callable[[int], object]] | None":
    """`(count, render)` for one sentence that prints its count after the verb,
    or `None`. `render(n)` is the same sentence with the count written in as a
    plain number (and `None` when that number means the sentence does nothing)."""
    from .amount_sentences import (
        add_mana_times,
        adding_player,
        controller_of,
        parse_add_mana_for_each,
        parse_life_clause,
        split_where_x,
        write_x,
    )

    text = sentence.strip()
    if _CONDITIONAL_OPENING_RE.match(text):
        return None
    where = split_where_x(text)
    if where is not None and re.search(r"\bX\b", where[0], re.IGNORECASE) and "." not in where[1]:
        reader = _expression_reader(where[1])
        body = where[0]
        return None if reader is None else (reader, lambda n: write_x(body, n) + ".")
    if (mana := parse_add_mana_for_each(text)) is not None:
        reader = _each_reader(mana[1])
        symbols = mana[0]
        if reader is not None and text.lower().startswith("that player "):
            # "that player adds {C} for each artifact they control": counted for
            # the player who adds the mana, the trigger event's player.
            from .effects.amounts import _for_each_multiplier

            multiplier = _for_each_multiplier(mana[1])
            if multiplier is not None:

                def count_for_adder(game: "Game", obj: object) -> int:
                    _controller, _source, source_id = _resolving_context(game, obj)
                    return multiplier(game, adding_player(game, obj, text), source_id)

                reader = count_for_adder

        def add(n: int):
            def run(game: "Game", obj: object) -> None:
                add_mana_times(
                    game,
                    adding_player(game, obj, text),
                    symbols,
                    n,
                    retain_until=retention,
                    stack_object=obj,
                )

            return run if n else None

        return None if reader is None else (reader, add)
    if (m := _ENERGY_FOR_EACH_RE.fullmatch(text)) is not None:
        reader = _each_reader(m.group("each"))
        symbol = m.group("symbol")
        return (
            None if reader is None else (reader, lambda n: f"You get {symbol * n}." if n else None)
        )
    if (m := _ENERGY_EQUAL_RE.fullmatch(text)) is not None:
        reader = _expression_reader(m.group("expr"))
        symbol = m.group("symbol")
        return (
            None if reader is None else (reader, lambda n: f"You get {symbol * n}." if n else None)
        )
    life = parse_life_clause(text)
    if life is not None and life.kind in ("equal", "for_each"):
        reader = (
            _expression_reader(life.expr or "")
            if life.kind == "equal"
            else _each_reader(life.expr or "")
        )
        head = f"{life.subject} " if life.subject else ""
        verb, unit = life.verb, life.n
        return None if reader is None else (reader, lambda n: f"{head}{verb} {unit * n} life.")
    if (m := _PUMP_FOR_EACH_RE.fullmatch(text)) is not None:
        reader = _each_reader(m.group("each"))
        subject, power, toughness = m.group("subject", "p", "t")
        if reader is None:
            return None
        if "target" in subject.lower():
            return reader, _targeted_pump(subject, int(power), int(toughness))
        sentence_head = text[: m.start("p")]
        tail = text[m.end("t") : m.start("each")].replace(" for each ", "").rstrip()
        return (
            reader,
            lambda n: f"{sentence_head}{int(power) * n:+d}/{int(toughness) * n:+d}{tail}.",
        )
    if (m := _FOR_EACH_AMOUNT_RE.fullmatch(text)) is not None:
        from ..numbers import parse_count

        reader = _each_reader(m.group("each"))
        each_n = parse_count(m.group("n"))
        if reader is None or each_n is None:
            return None
        head, noun, mid = m.group("head"), m.group("noun").lower(), m.group("mid")
        noun = "cards" if noun.startswith("card") else noun
        return reader, lambda n: f"{head}{each_n * n} {noun}{mid}."
    return None


def _fold_mana_retention(sentences: list[str]):
    """`(sentences without the retention sentences that follow a counted "Add {M} for
    each ..." sentence, {that sentence: its ManaRetentionScope})`. A retention
    sentence after anything else stays where it is, for the readers that know it."""
    from ..models.mana import ManaRetentionScope

    kept: list[str] = []
    retentions: dict[str, object] = {}
    for sentence in sentences:
        match = _KEEP_MANA_RE.fullmatch(sentence.strip())
        if (
            match is not None
            and kept
            and kept[-1] not in retentions
            and _counted_sentence(kept[-1], ManaRetentionScope.END_OF_TURN) is not None
            and kept[-1].lower().startswith(("add ", "then add "))
        ):
            retentions[kept[-1]] = (
                ManaRetentionScope.END_OF_TURN
                if match.group("scope").lower() == "turn"
                else ManaRetentionScope.END_OF_COMBAT
            )
            continue
        kept.append(sentence)
    return kept, retentions


def parse_counted_amount_text(text: str, *, for_spell: bool):
    """A body whose sentences print their count after the verb ("Each opponent
    loses 1 life for each creature you control", "You draw X cards and you lose
    X life, where X is the number of creatures you control", "Add {R} for each
    ...", "You get an amount of {E} equal to ..."), read sentence by sentence.

    Each such sentence takes its count when its own turn comes (CR 608.2c - the
    instructions are followed in order; CR 608.2h - the count is fixed as the
    instruction is performed, so a Treasure made by the sentence before is
    counted by "for each Treasure you control"), is written into the sentence as
    a plain number, and that sentence is run by the ordinary clause readers.
    Sentences with no such count are read whole by those readers too. `None` when
    any sentence is unreadable - CR 608.2c has no half-run instruction."""
    from .effects.dispatch import _ability_effect_or_notice, _spell_effect_or_notice
    from .effects.text import _plain_resolution_sentences, _strip_non_effect_preamble
    from .effects.tokens import _is_notice_only

    parse = _spell_effect_or_notice if for_spell else _ability_effect_or_notice
    sentences = _plain_resolution_sentences(_strip_non_effect_preamble(text))
    if for_spell and any(_ABILITY_LINE_RE.match(sentence) for sentence in sentences):
        return None
    sentences, retentions = _fold_mana_retention(sentences)
    if not any(
        _counted_sentence(sentence, retentions.get(sentence)) is not None for sentence in sentences
    ):
        return None

    @functools.cache
    def parsed(rendered: str):
        return parse(rendered)

    def readable(effect: object) -> bool:
        return (
            effect is not None
            and not _is_notice_only(effect)
            and getattr(effect, "unparsed_remainder", None) is None
        )

    steps: list = []
    plain: list[str] = []

    def flush_plain() -> bool:
        if not plain:
            return True
        effect = parse(" ".join(plain))
        plain.clear()
        if not readable(effect):
            return False
        steps.append(lambda game, obj, effect=effect: effect(game, obj))
        return True

    for sentence in sentences:
        counted = _counted_sentence(sentence, retentions.get(sentence))
        if counted is None:
            plain.append(sentence)
            continue
        if not flush_plain():
            return None
        count, render = counted
        probe = render(2)
        if probe is None or (isinstance(probe, str) and not readable(parsed(probe))):
            return None

        def run(game, obj, count=count, render=render) -> None:
            rendered = render(max(count(game, obj), 0))
            if rendered is None:
                return
            if not isinstance(rendered, str):
                rendered(game, obj)
                return
            effect = parsed(rendered)
            if effect is not None:
                effect(game, obj)

        steps.append(run)
    if not flush_plain():
        return None

    def effect(game, obj) -> None:
        for step in steps:
            step(game, obj)

    return effect
