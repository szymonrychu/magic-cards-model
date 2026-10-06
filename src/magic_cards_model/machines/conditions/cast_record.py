"""Cast-record conditions: how a spell was cast and which costs were paid for
it (CR 601.2b-h), read off `CastRecord`.

Each reader here is a `ConditionReader` registered through `READERS`; see
`machines/conditions/__init__.py` for the contract every reader keeps.

"It" / "that spell" / "he" / the source's own name is the object the clause
is about: for a triggered ability, `machines/triggers._cast_record_for_clause`
decides - the trigger event's subject ("Whenever you cast a noncreature spell,
if at least four mana was spent to cast it") unless the trigger condition
names the source itself ("When this creature enters, if it was bargained"),
and on CR 608.2a's recheck the object the ability came from (CR 113.7a); for
any other condition, the source. An object that was never cast has no record
(`Game.note_cast` writes one only as a spell becomes cast, CR 601.2i), which
answers every "was cast"/"was paid" clause False and every "wasn't" clause
True - a fact, not an unread clause.

Rules verified with `mise run rules:find`:

- CR 601.2a: casting moves the card "from where it is to the stack" - where
  it was cast from is `CastRecord.origin_zone`.
- CR 601.2h: the mana spent is what paid the total cost - not the mana value
  (CR 202.3), which no reduction or life payment changes.
- CR 202.3e: on the stack, X in a mana cost is the announced value.
- CR 106.3: mana's source is the source of the ability that produced it.
- CR 107.4h: {S} is mana from a snow source.
- CR 105.2c: colorless is not a color - {C} is not colored mana.
- CR 702.33d: a spell whose kicker cost was declared is "kicked"; CR 702.33b:
  "Kicker [cost 1] and/or [cost 2]" is two kicker costs, and CR 702.33f's "if
  it was kicked with its [A] kicker" names one of them.
- CR 702.166b: a spell whose bargain cost was declared "has been
  'bargained.'"
- CR 701.59c: "if evidence was collected" is linked to the collect evidence
  additional cost.
- CR 702.104b: "tribute wasn't paid" is true if the chosen opponent didn't
  have the creature enter with the +1/+1 counters its tribute names.
- CR 702.76a (prowl), CR 702.137a (spectacle), CR 702.35a (madness), CR
  702.117a (surge), CR 702.119a (emerge), CR 702.190a (sneak), CR 702.188a
  (web-slinging): alternative costs, recorded as `CastRecord.keyword`.
- CR 707.10: a copy of a spell isn't cast.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...numbers import COUNT, MULTIPLIER, parse_count, parse_multiplier
from . import ConditionReader

if TYPE_CHECKING:
    from ...models.card_state import CardState
    from ...models.game import CastRecord
    from . import ConditionContext


# -- whose record -----------------------------------------------------------


def _about_the_event_subject(context: "ConditionContext") -> bool:
    """Whether "it" is the trigger event's own subject rather than the
    source - `_cast_record_for_clause`'s own test."""
    from ..abilities import TriggeredAbility
    from ..triggers import _is_legendary_source, _self_referential

    ability, source = context.ability, context.source
    if not isinstance(ability, TriggeredAbility) or source is None or context.event is None:
        return False
    return not _self_referential(
        ability.condition, source.name, legendary=_is_legendary_source(source)
    )


def _names_the_source_outright(subject: str | None) -> bool:
    """A subject that can only be the source itself - "this creature", a
    legend's "he"/"she", or a name - as opposed to "it"/"they", whose object
    the trigger condition decides."""
    if subject is None:
        return False
    return subject.strip() not in ("it", "they", "that spell", "that creature")


def _record(context: "ConditionContext", subject: str | None = None) -> "CastRecord | None":
    """The `CastRecord` the clause reads, or None when that object was never
    cast (or its record is gone). A clause whose subject names the source
    outright ("this creature wasn't kicked" on an end step trigger) reads the
    source's own record, by its stamp on the recheck (CR 113.7a)."""
    from ..abilities import TriggeredAbility
    from ..triggers import _cast_record_for_clause

    source, ability = context.source, context.ability
    if source is None:
        return None
    if _names_the_source_outright(subject):
        if context.source_stamp is not None:
            return context.game.cast_record_as_last_known(context.source_stamp)
        return context.game.cast_record_of(source)
    if isinstance(ability, TriggeredAbility):
        return _cast_record_for_clause(
            context.game, ability, source, context.event, context.source_stamp
        )
    return context.game.cast_record_of(source)


def _subject(context: "ConditionContext") -> "CardState | None":
    """The object "it" names - the event's subject or the source."""
    if _about_the_event_subject(context):
        event = context.event
        return context.game.find_by_id(event.subject_id) if event and event.subject_id else None
    return context.source


def _cast_by_you(context: "ConditionContext") -> bool:
    """ "You cast it": the caster is the clause's "you" (CR 109.5). A spell's
    controller is its caster (CR 405.4), and the permanent it became enters
    under that player's control (CR 608.3a), which the event recorded."""
    if not _about_the_event_subject(context):
        return True
    event = context.event
    controller = getattr(event, "subject_controller", None) if event is not None else None
    if controller is None:
        subject = _subject(context)
        controller = subject.controller if subject is not None else None
    return controller == context.controller


def _names_its_object(subject: str, context: "ConditionContext") -> bool:
    """Whether the clause's grammatical subject is the object the clause is
    about: a pronoun, "this <noun>", "that spell", or the source's own name
    (CR 201.5)."""
    from ..abilities import self_reference_names
    from ..triggers import _is_legendary_source

    words = subject.strip()
    if words in ("it", "he", "she", "they", "that spell", "that creature") or re.fullmatch(
        r"this [a-z]+", words
    ):
        return True
    source = context.source
    if source is None:
        return False
    return any(
        words == name.lower()
        for name in self_reference_names(source.name, legendary=_is_legendary_source(source))
    )


#: The subject a cast-record clause is printed with: a pronoun, "this
#: <noun>", "that spell", or a name (checked against the source by
#: `_names_its_object` when read).
_PRONOUN = r"it|he|she|they|that spell|that creature|this [a-z]+"
_SUBJECT = rf"(?P<subject>{_PRONOUN})"
#: A legend's own name as the subject too ("Jace was kicked", CR 201.5) -
#: anything that opens like a quantifier or a group ("none of them") is left
#: to the readers of those.
_NAMED_SUBJECT = (
    rf"(?P<subject>{_PRONOUN}"
    r"|(?!(?:a|an|another|each|all|no|none|target|that|those|these|you|your)\b)"
    r"[a-z][a-z0-9 ,'-]*?)"
)
_IT = r"(?:it|him|her|them|that spell|this spell|this creature)"


# -- where it was cast from ---------------------------------------------------


def _cast_from(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you cast it from your hand" / "you didn't cast it from your hand" /
    "it was cast from a graveyard" (CR 601.2a)."""
    from ...models.zone import Zone

    zone = {"hand": Zone.HAND, "graveyard": Zone.GRAVEYARD, "exile": Zone.EXILE}[
        match.group("zone")
    ]
    record = _record(context)
    held = (
        record is not None
        and not record.is_copy
        and record.origin_zone is zone
        and (match.group("you") is None or _cast_by_you(context))
    )
    return held != bool(match.group("negated") or match.group("negated2"))


def _was_cast(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "he was cast", "they were cast" - CR 601.2's cast, as opposed to any
    other way onto the battlefield. A copy was not cast (CR 707.10)."""
    if not _names_its_object(match.group("subject"), context):
        return False
    record = _record(context, match.group("subject"))
    held = record is not None and not record.is_copy
    return held != bool(match.group("negated"))


# -- how much mana, and which -------------------------------------------------


def _x_count(state: "CardState") -> int:
    return (state.mana_cost or "").upper().count("{X}")


def _mana_value_on_the_stack(state: "CardState", record: "CastRecord") -> float:
    """CR 202.3e: X is the announced value while the spell is on the stack."""
    return state.mana_value + _x_count(state) * record.x_value


def _at_least_mana_spent(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "at least four mana was spent to cast it" / "N or more mana was spent"
    (CR 601.2h)."""
    needed = parse_count(match.group("count") or match.group("count2"))
    record = _record(context)
    if needed is None or record is None:
        return False
    return record.total_mana_spent >= needed


def _other_value(context: "ConditionContext", text: str, record: "CastRecord") -> float | None:
    """The value the amount spent is compared with: the spell's own mana value,
    or the source's power or toughness."""
    words = text.strip()
    if words in ("its mana value", "that spell's mana value"):
        subject = _subject(context)
        return None if subject is None else _mana_value_on_the_stack(subject, record)
    stat = re.fullmatch(r"(?P<owner>.+?)'s? (?P<stat>power|toughness)", words)
    if stat is None or not _names_its_object(stat.group("owner"), context):
        return None
    source = context.source
    if source is None:
        return None
    game = context.game
    value = game.power_of(source) if stat.group("stat") == "power" else game.toughness_of(source)
    return float(value or 0)


def _amount_compared(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "the amount of mana spent to cast it was less than its mana value",
    "... is greater than Liberator's power"."""
    record = _record(context)
    if record is None:
        return False
    other = _other_value(context, match.group("other"), record)
    if other is None:
        return False
    spent = record.total_mana_spent
    comparison = match.group("comparison")
    if comparison == "greater than":
        return spent > other
    if comparison == "less than":
        return spent < other
    return spent == other


def _same_color(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "at least three mana of the same color was spent to cast it" (CR
    105.2c: colorless is not a color)."""
    from ...models.card import Color

    needed = parse_count(match.group("count"))
    record = _record(context)
    if needed is None or record is None:
        return False
    return any(
        amount >= needed
        for color, amount in record.mana_spent.items()
        if color is not Color.COLORLESS
    )


def _no_colored_mana(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "no colored mana was spent to cast it" - true for a spell cast for no
    mana at all. A spell never cast has no record: False."""
    from ...models.card import Color

    record = _record(context)
    if record is None:
        return False
    return not any(
        amount > 0 for color, amount in record.mana_spent.items() if color is not Color.COLORLESS
    )


_SYMBOL_COLORS = {"w": "W", "u": "U", "b": "B", "r": "R", "g": "G", "c": "C"}


def _symbol_not_spent(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "{C} wasn't spent to cast it" - no mana of that symbol's kind."""
    from ...models.card import Color

    record = _record(context)
    if record is None:
        return False
    color = Color(_SYMBOL_COLORS[match.group("symbol")])
    return record.mana_of_color_spent(color) == 0


def _from_creatures(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "three or more mana from creatures was spent to cast it" (CR 106.3)."""
    needed = parse_count(match.group("count") or match.group("count2"))
    record = _record(context)
    if needed is None or record is None:
        return False
    return record.creature_mana_spent >= needed


def _snow_of_its_colors(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "{S} of any of that spell's colors was spent to cast it" (CR 107.4h)."""
    record = _record(context)
    subject = _subject(context)
    if record is None or subject is None:
        return False
    return any(record.snow_mana_spent.get(color, 0) > 0 for color in subject.colors)


# -- optional and alternative costs ---------------------------------------------


def _kicked(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it was kicked" / "he was kicked" / "this creature wasn't kicked" /
    "it was kicked twice" / "it was kicked with its {2}{U} kicker"
    (CR 702.33d, 702.33f)."""
    if not _names_its_object(match.group("subject"), context):
        return False
    record = _record(context, match.group("subject"))
    kicked = record.kicked if record is not None else 0
    which = match.group("cost")
    times = match.group("times")
    if which is not None:
        paid = [cost.lower() for cost in (record.kicker_costs_paid if record else [])]
        held = which.lower() in paid
    elif times is not None:
        needed = parse_multiplier(times)
        held = needed is not None and kicked >= needed
    else:
        held = kicked > 0
    return held != bool(match.group("negated"))


def _keyword_cost_paid(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "its prowl cost was paid", "his sneak cost was paid", "they were cast
    using web-slinging" - the alternative cost the spell was cast for
    (`CastRecord.keyword`, CR 118.9a allows one).

    "... this turn" (Karai, Future of the Foot's own "If her sneak cost was
    paid this turn, instead return that card to the battlefield") narrows a
    sneak/surge/etc. permanent that keeps its `CastRecord` for the rest of
    the game to only the turn it actually entered on. `CastRecord` carries no
    turn number of its own, but CR 702.190a's sneak (and every other
    alternative cost this reader claims) is paid as part of *casting*, and a
    permanent spell becomes the permanent it will ever be the moment it
    resolves - the same turn it was cast, always - so "paid this turn" is
    exactly "paid, and this permanent's own `turn_entered` is the current
    turn" (`CardState.turn_entered`, the same field summoning sickness
    already reads). The subject ("her"/"his"/"its"/"their") is always the
    ability's own source here - `_record`'s own no-subject-given default
    routes through `_cast_record_for_clause` the identical way every other
    keyword-cost clause in this reader already does - so `context.source` is
    the permanent whose entering turn is being asked about.
    """
    record = _record(context)
    if record is None or record.is_copy:
        return False
    keyword = (record.keyword or "").lower()
    if keyword != match.group("keyword") or not record.keyword_cost_paid:
        return False
    if match.group("this_turn") is None:
        return True
    source = context.source
    turn = context.game.turn
    return source is not None and turn is not None and source.turn_entered == turn.turns_taken


def _bargained(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it was bargained" (CR 702.166b)."""
    if not _names_its_object(match.group("subject"), context):
        return False
    record = _record(context, match.group("subject"))
    held = record is not None and record.bargained
    return held != bool(match.group("negated"))


def _evidence_collected(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "evidence was collected" (CR 701.59c)."""
    record = _record(context)
    held = record is not None and record.evidence_collected
    return held != bool(match.group("negated"))


def _beheld_for_cost(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "if a Dragon was beheld" (CR 701.4b) - the plain, unrestricted
    "you may behold a `<quality>`" additional cost (CR 118.8b), set by
    `Casting.behold_for_cost`. The quality named in the clause is not
    re-checked here: it is fixed by the same printed cost sentence that
    `beheld_for_cost` itself already enforced against whatever was beheld to
    pay it, the identical division `_evidence_collected` already keeps for
    its own linked "if evidence was collected" (CR 701.59c)."""
    record = _record(context)
    held = record is not None and record.beheld_for_cost
    return held != bool(match.group("negated"))


def _revealed_or_controlled(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you revealed a Dragon card or controlled a Dragon as you cast this
    spell": the optional reveal was paid, or the caster controlled a
    permanent of that subtype as the spell became cast (CR 601.2i)."""
    from ...data.subtypes import canonical_subtype

    record = _record(context)
    if record is None:
        return False
    if record.revealed_for_cost:
        return True
    subtype = canonical_subtype(match.group("controlled"))
    return subtype is not None and subtype.lower() in record.controlled_subtypes_as_cast


def _tribute_paid(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "tribute wasn't paid" (CR 702.104b): whether an opponent put +1/+1
    counters on the source as it entered - recorded with its putter by
    CR 122.6's counter placement history (`Game.counters_put_this_turn`),
    which `machines/replacement`'s tribute modifier feeds. The entering and
    the trigger it causes are one turn's business: a turn cannot end while
    the trigger is still on the stack (CR 500.2)."""
    source = context.source
    if source is None:
        return False
    stamp = context.source_stamp or source.zone_change_stamp
    controller = context.controller
    paid = any(
        record.card_id == source.id
        and record.zone_change_stamp == stamp
        and record.kind == "+1/+1"
        and record.putter is not None
        and record.putter != controller
        for record in context.game.counters_put_this_turn
    )
    return paid == (match.group("negated") is None)


def _x_compared(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "X is 5 or more" (Banefire, Finale of Eternity) - CR
    107.3a: "While a spell is on the stack, any X in its mana cost ... equals
    the announced value", which `CastRecord.x_value` holds. No record (the
    object was never cast) is X = 0, CR 107.3b's free-cast answer too."""
    needed = parse_count(match.group("count"))
    if needed is None:
        return False
    if match.group("x") != "x":
        # The announced value already substituted for X (`substitute_x`,
        # CR 107.3a) - "5 is 5 or more" compares two numbers.
        x_value = int(match.group("x"))
    else:
        record = _record(context)
        x_value = record.x_value if record is not None else 0
    if match.group("comparison") in ("more", "greater"):
        return x_value >= needed
    return x_value <= needed


# -- the registry ------------------------------------------------------------------

_NEGATED = r"(?P<negated>n't| not)?"


def _reader(pattern: str, read: Callable[["ConditionContext", re.Match[str]], bool]):
    return ConditionReader(re.compile(pattern), read)


READERS: tuple[ConditionReader, ...] = (
    _reader(
        rf"(?:(?P<you>you) (?:did(?P<negated>n't| not) )?cast {_IT}"
        r"|(?:it|he|she|they|that spell|this spell|this creature) (?:was|were)"
        r"(?P<negated2>n't| not)? cast) "
        r"from (?:your|a|their) (?P<zone>hand|graveyard|exile)",
        _cast_from,
    ),
    _reader(
        rf"{_SUBJECT} (?:was|were)(?P<negated>n't| not)? cast",
        _was_cast,
    ),
    _reader(
        rf"(?:at least (?P<count>{COUNT})|(?P<count2>{COUNT}) or more) mana was spent to "
        rf"cast {_IT}",
        _at_least_mana_spent,
    ),
    _reader(
        rf"(?P<x>x|\d+) is (?P<count>{COUNT}) or (?P<comparison>more|greater|less)", _x_compared
    ),
    _reader(
        rf"the amount of mana spent to cast {_IT} (?:is|was) "
        r"(?P<comparison>greater than|less than|equal to) (?P<other>.+)",
        _amount_compared,
    ),
    _reader(
        rf"at least (?P<count>{COUNT}) mana of the same color was spent to cast {_IT}",
        _same_color,
    ),
    _reader(rf"no colored mana was spent to cast {_IT}", _no_colored_mana),
    _reader(
        rf"\{{(?P<symbol>[wubrgc])\}} (?:wasn't|was not) spent to cast {_IT}",
        _symbol_not_spent,
    ),
    _reader(
        rf"(?:at least (?P<count>{COUNT})|(?P<count2>{COUNT}) or more) mana from creatures "
        rf"was spent to cast {_IT}",
        _from_creatures,
    ),
    _reader(
        rf"\{{s\}} of any of (?:that spell's|its) colors was spent to cast {_IT}",
        _snow_of_its_colors,
    ),
    _reader(
        rf"{_NAMED_SUBJECT} was{_NEGATED} kicked"
        rf"(?: (?P<times>{MULTIPLIER})| with its (?P<cost>(?:\{{[^}}]+\}})+) kicker)?",
        _kicked,
    ),
    # "this creature's sneak cost was paid" (Turncoat Kunoichi) / "this
    # spell's sneak cost was paid" (The Last Ronin's Technique) - CR 700.7's
    # own "this `<type>`" self-reference in its possessive form, alongside
    # the pronoun forms every other TMT sneak-paid rider already used
    # ("her sneak cost was paid" - Karai, Future of the Foot). Purely
    # additive: every subject the bare pronoun alternation already matched
    # still does.
    _reader(
        r"(?:its|his|her|their|this [a-z]+'s) "
        r"(?P<keyword>prowl|spectacle|madness|surge|emerge|sneak|dash"
        r"|evoke|blitz|warp|mayhem|web-slinging|disturb|escape|flashback) cost was paid"
        r"(?P<this_turn> this turn)?",
        _keyword_cost_paid,
    ),
    _reader(
        r"(?:it was|he was|she was|they were) cast using (?P<keyword>web-slinging|sneak|surge"
        r"|prowl|spectacle|madness|emerge|dash|blitz|evoke|mayhem|warp)(?P<this_turn> this turn)?",
        _keyword_cost_paid,
    ),
    _reader(rf"{_SUBJECT} (?:was|were){_NEGATED} bargained", _bargained),
    _reader(r"evidence was(?P<negated>n't| not)? collected", _evidence_collected),
    _reader(
        r"an? (?P<quality>[a-z' -]+?) was(?P<negated>n't| not)? beheld",
        _beheld_for_cost,
    ),
    _reader(
        r"you revealed an? (?P<revealed>[a-z]+) card or controlled an? (?P<controlled>[a-z]+) "
        r"as you cast (?:this spell|it)",
        _revealed_or_controlled,
    ),
    _reader(r"tribute was(?P<negated>n't| not)? paid", _tribute_paid),
)
