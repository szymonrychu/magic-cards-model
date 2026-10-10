import re
from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from magic_cards_model.phrases import with_indefinite_article

from ...data.creature_types import creature_types
from ...models.card import Card, Color, Supertype, Type, types_of
from ...models.card_state import (
    CardState,
    Choice,
    ChoiceKind,
    Counter,
    DevouredObject,
    ExileMarker,
)
from ...models.token import is_token
from ...models.zone import Zone
from ...numbers import COUNT, parse_count
from ..chosen_type import RESTRICTED_TRIBAL_TYPES, matches_restricted_creature_type_choice
from ..decisions import Decision, DecisionKind, source_id_of
from ..delayed import ReflexiveExileCopiedCard
from ..keyword_counters import enters_count_reader, fixed_enters_count_reader
from .as_enters_actions import Action, as_enters_action, counters_for

if TYPE_CHECKING:
    from ...models.game import Game
    from ..effects import _SacrificeRestriction
from .enters_choices import (
    REVEALED_OR_CONTROL_RE,
    compile_group_enter_tapped,
    enters_choice_apply,
    read_extra_enters_condition,
    reveal_follow_up_subtype,
)
from .model import (
    ApplicableEffect,
    Applies,
    Apply,
    CardReplacement,
    EnterUnderYourControl,
    ReplaceableEvent,
    ReplacementEffect,
    UnwiredChoiceNotice,
)

#: "this creature", "this land", "this permanent", "this" - a self reference.
_THIS = re.compile(
    r"^(this|it|he|she)\b|^this (creature|land|permanent|artifact|enchantment|"
    r"planeswalker|battle|card|spell|vehicle|equipment|token)\b",
    re.IGNORECASE,
)

_ENTERS = r"enters?(?: the battlefield)?"


# CR 614.1d (the bare "[This permanent] enters ..." form; CR 614.1c is
# "enters with"/"As ... enters"/"enters as"). `condition` picks up the "If you
# don't, it enters tapped" form used by the modal double-faced lands, and
# `unless` the "unless ..." form used by the duals. The two groups are kept
# apart on purpose: they carry opposite polarity - a leading "If <cond>," taps
# when the condition *holds*, a trailing "unless <cond>" taps when it does
# *not* - and `_enters_tapped_condition` below reads that polarity back off the
# retained "unless" word.
#
# `trailing_if` is the third polarity, added for Eddymurk Crab's own "This
# creature enters tapped if it's not your turn." - a trailing "if <cond>"
# with no leading comma, unlike the leading `condition` group's "If <cond>,"
# form. Its polarity is the *same* as the leading form (taps when the
# condition holds, CR 614.1d), never negated the way a trailing "unless"
# is - `_try_enters_tapped` folds it into `condition` on equal footing with
# the leading group for exactly that reason.
_ENTERS_TAPPED = re.compile(
    rf"^(?:If (?P<condition>[^,]+),\s*)?(?P<subject>[^,]+?) {_ENTERS} tapped"
    r"(?:\s+(?:(?P<unless>unless .+?)|if (?P<trailing_if>.+?)))?\.?$",
    re.IGNORECASE,
)
# CR 722.3a's bare form: "This creature enters prepared." Every printing in
# the pool states it unconditionally - no "unless"/"If" polarity to read -
# but the leading `If (...)` group is kept anyway for the same reason
# `_ENTERS_TAPPED` keeps one: a future conditional printing should be read by
# this shape rather than falling to `UNPARSED`.
_ENTERS_PREPARED = re.compile(
    rf"^(?:If (?P<condition>[^,]+),\s*)?(?P<subject>[^,]+?) {_ENTERS} prepared\.?$",
    re.IGNORECASE,
)
# CR 614.1d - "[Objects] enter [the battlefield] untapped." Spelunking's own
# "Lands you control enter untapped": a plural, class-scoped subject ("Lands
# you control"), not `_ENTERS_TAPPED`'s singular "[this permanent]" - and the
# opposite tapped state, which is why this is not folded into that regex with
# an alternation. `subject` is read back for `_refers_to_self` the same way
# every other entering-shape regex here does, though a "you control" subject
# never actually matches it (it names a class, not the printing card itself).
_ENTERS_UNTAPPED = re.compile(rf"^(?P<subject>.+?) {_ENTERS} untapped\.?$", re.IGNORECASE)
#: The trailing counterpart of the leading `(?P<condition>...)` group above -
#: Festerhide Boar's own Morbid clause (CR 207.2c, the ability word stripped
#: before this ever runs), "This creature enters with two +1/+1 counters on
#: it if a creature died this turn." CR 614.1c's "enters with" carries a
#: condition on either side of the sentence in the pool, the same way
#: `_ENTERS_TAPPED` already reads both a leading "If ..." and a trailing
#: "unless ..."; `_try_enters_with` folds whichever one matched into the
#: same `condition` field, and `_read_enters_condition` is what has to
#: recognise the text itself.
_ENTERS_WITH = re.compile(
    rf"^(?:If (?P<condition>[^,]+),\s*)?(?P<subject>[^,]+?) {_ENTERS}(?P<tapped> tapped)?"
    r" with (?P<what>.+?)"
    r"(?:\s+on it)?(?:,\s*(?P<tail>where .+?))?"
    r"(?:\s+(?:if (?P<trailing_condition>.+?)|(?P<trailing_unless>unless .+?)))?\.?$",
    re.IGNORECASE,
)
#: CR 702.138c: "An ability that reads "[This permanent] escapes with [one or
#: more of a kind of counter]" means "If this permanent escaped, it enters
#: with [those counters]"" - Chainweb Aracnir's "This creature escapes with
#: three +1/+1 counters on it.", read as the `ENTERS_WITH` it means, gated on
#: `ESCAPED_CONDITION` (`_escaped`, CR 702.138b).
_ESCAPES_WITH = re.compile(
    r"^(?P<subject>[^,]+?) escapes with (?P<what>.+?)(?:\s+on it)?(?:\s+instead)?\.?$",
    re.IGNORECASE,
)
#: The condition text CR 702.138c's own expansion states.
ESCAPED_CONDITION = "this permanent escaped"
#: What the plain "enters with" sentence in front of an "It escapes with ...
#: instead." sentence (Polukranos, Unchained) is gated on: the instead-sentence
#: replaces it, so it applies only to a permanent that did not escape.
NOT_ESCAPED_CONDITION = "this permanent didn't escape"
#: "for each time it was kicked" - `_read_counters` keeps the count phrase as
#: the `amount_expression` "time it was kicked"; CR 702.33d's kick count is
#: read off the spell's cast record as the permanent enters (`_kicked_count`).
_TIMES_KICKED_RE = re.compile(r"^times? it was kicked$", re.IGNORECASE)
_ENTERS_AS_COPY = re.compile(
    rf"^(?:You may have\s+)?(?P<subject>.+?) (?:{_ENTERS}|enter)(?P<tapped> tapped)?"
    r" as a copy of (?P<copy_of>.+?)(?:,\s*except\s+(?P<exception>.+?))?\.?$",
    re.IGNORECASE,
)


_AS_ENTERS = re.compile(
    rf"^As (?P<subject>.+?) {_ENTERS}(?P<also> or is turned face up)?,\s*(?P<effect>.+?)\.?$",
    re.IGNORECASE,
)


def _names_of_name(name: str) -> tuple[str, ...]:
    """`_names_of` for an object known only by its name - a copy's copiable
    name (CR 707.2), which has no `Card` of its own to read faces off. The
    full name and its comma-split head (CR 201.5c's shortened name), longest
    first."""
    names = {name.strip(), name.split(",")[0].strip()}
    return tuple(sorted((part for part in names if part), key=len, reverse=True))


def _refers_to_self(phrase: str | None, names: tuple[str, ...]) -> bool:
    if not phrase:
        return False
    phrase = phrase.strip().strip('"').lower()
    if _THIS.match(phrase):
        return True
    return any(phrase.startswith(name.lower()) for name in names)


def _try_as_enters(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _AS_ENTERS.match(sentence)
    if not match:
        return []
    subject = match.group("subject").strip()
    effect = match.group("effect").strip()
    shared = {
        "subject": subject,
        "replacement": effect,
        "optional": _is_optional(effect),
        "self_replacement": _refers_to_self(subject, names),
    }
    found = [_make(ReplacementKind.AS_ENTERS, sentence, **shared)]
    if match.group("also"):
        # Aquamorph Entity folds CR 614.1c and 614.1e into one sentence. It is
        # two replacement effects watching two different events, so report both.
        found.append(_make(ReplacementKind.AS_TURNED_FACE_UP, sentence, **shared))
    return found


def _try_enters_as_copy(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    if " as a copy of " not in sentence.lower():
        return []
    match = _ENTERS_AS_COPY.match(sentence)
    if not match:
        return []
    subject = match.group("subject").strip()
    raw_exception = match.group("exception")
    parsed_exception = _parse_copy_exception(raw_exception)
    # `raw_exception` is only truthy when the card actually printed an
    # "except ..." tail. `parsed_exception is None` is ambiguous on its own -
    # see `ReplacementEffect.copy_exception`'s docstring - so the two are
    # combined here, once, into the distinction every downstream reader needs:
    # a tail that existed and did not parse, kept as text rather than dropped.
    unparsed_exception = (
        raw_exception.strip() if raw_exception and parsed_exception is None else None
    )
    return [
        _make(
            ReplacementKind.ENTERS_AS_COPY,
            sentence,
            subject=subject,
            copy_of=match.group("copy_of").strip(),
            copy_exception=parsed_exception,
            copy_exception_unparsed=unparsed_exception,
            tapped=bool(match.group("tapped")),
            optional=sentence.lower().startswith("you may have"),
            self_replacement=_refers_to_self(subject, names),
        )
    ]


#: "Artifacts, creatures, and lands your opponents control enter tapped." (Frozen
#: Aether, Loxodon Gatekeeper) - `_ENTERS_TAPPED`'s subject cannot hold a comma
#: (its leading "If <condition>," needs that), so an unconditional comma list
#: of objects is read here.
_ENTERS_TAPPED_LIST = re.compile(
    rf"^(?P<subject>[A-Z][^.]*?,[^.]+?) {_ENTERS} tapped\.?$",
)
#: "This creature enters tapped and doesn't untap during your untap step."
#: (Grimgrin, Leviathan, Traxos) and "This artifact enters tapped and with
#: three charge counters on it." (Sphere of the Suns) - CR 614.1d's tapped half
#: plus a second clause: the untap restriction is the continuous effect
#: `layers.parse._SELF_DOESNT_UNTAP_RE` reads off the same line, the counters an
#: ordinary `ENTERS_WITH` (CR 614.1c).
_ENTERS_TAPPED_AND = re.compile(
    rf"^(?P<subject>[^,]+?) {_ENTERS} tapped and "
    r"(?:(?P<untap>doesn'?t untap during your untap step)|with (?P<what>.+?)(?: on it)?)\.?$",
    re.IGNORECASE,
)


def _try_enters_tapped(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    both = _ENTERS_TAPPED_AND.match(sentence)
    if both is not None:
        subject = both.group("subject").strip()
        tapped = _make(
            ReplacementKind.ENTERS_TAPPED,
            sentence,
            subject=subject,
            tapped=True,
            condition=None,
            self_replacement=_refers_to_self(subject, names),
        )
        if both.group("untap"):
            return [tapped]
        with_counters = _try_enters_with(
            f"{subject} enters with {both.group('what')} on it.", names
        )
        return [
            tapped,
            *(
                effect.model_copy(update={"text": sentence, "raw": sentence})
                for effect in with_counters
            ),
        ]
    listed = _ENTERS_TAPPED_LIST.match(sentence)
    if listed is not None and not sentence.lower().startswith("if "):
        subject = listed.group("subject").strip()
        return [
            _make(
                ReplacementKind.ENTERS_TAPPED,
                sentence,
                subject=subject,
                tapped=True,
                condition=None,
                self_replacement=_refers_to_self(subject, names),
            )
        ]
    match = _ENTERS_TAPPED.match(sentence)
    if not match:
        return []
    subject = match.group("subject").strip()
    condition = match.group("condition") or match.group("unless") or match.group("trailing_if")
    return [
        _make(
            ReplacementKind.ENTERS_TAPPED,
            sentence,
            subject=subject,
            tapped=True,
            condition=(condition or "").strip() or None,
            self_replacement=_refers_to_self(subject, names),
        )
    ]


def _try_enters_prepared(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _ENTERS_PREPARED.match(sentence)
    if not match:
        return []
    subject = match.group("subject").strip()
    condition = match.group("condition")
    return [
        _make(
            ReplacementKind.ENTERS_PREPARED,
            sentence,
            subject=subject,
            condition=(condition or "").strip() or None,
            self_replacement=_refers_to_self(subject, names),
        )
    ]


def _try_enters_untapped(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _ENTERS_UNTAPPED.match(sentence)
    if not match:
        return []
    subject = match.group("subject").strip()
    return [
        _make(
            ReplacementKind.ENTERS_UNTAPPED,
            sentence,
            subject=subject,
            tapped=False,
            self_replacement=_refers_to_self(subject, names),
        )
    ]


#: "two +1/+1 counters on it for each `<count>`" (Hamlet Vanguard, Clay
#: Champion, Vodalian Mindsinger) and "a +1/+1 counter on it plus an
#: additional +1/+1 counter on it for each `<count>`" (Sheriff of Safe
#: Passage): read as an `amount_expression` the count reader
#: (`keyword_counters.enters_count_reader`) understands - "`<n>` times
#: `<count>`" and "`<n>` plus `<count>`".
_MULTIPLE_PER_EACH = re.compile(
    rf"^(?P<n>{COUNT}) (?P<kind>[^ ]+) counters? on it for each (?P<each>.+)$", re.IGNORECASE
)
_PLUS_ADDITIONAL_PER_EACH = re.compile(
    rf"^(?P<n>{COUNT}) (?P<kind>[^ ]+) counters? on it plus an additional (?P=kind) counter"
    r" on it for each (?P<each>.+)$",
    re.IGNORECASE,
)


def _read_multiplied_counters(
    what: str,
) -> tuple[int | None, bool, str | None, str | None, int | None] | None:
    plus = _PLUS_ADDITIONAL_PER_EACH.match(what)
    if plus is not None:
        return None, True, plus.group("kind"), f"{plus.group('n')} plus {plus.group('each')}", None
    times = _MULTIPLE_PER_EACH.match(what)
    if times is not None and times.group("n").lower() not in ("a", "an"):
        return (
            None,
            True,
            times.group("kind"),
            f"{times.group('n')} times {times.group('each')}",
            None,
        )
    return None


#: "... and with haste" (Pouncing Wurm, Voidpouncer): CR 614.1c's "enters
#: with" also covers an ability the permanent enters with. Kept on the
#: effect's `replacement` text and read back by `_apply_self_enters`.
_AND_WITH_HASTE = re.compile(r"\s+and with haste$", re.IGNORECASE)
#: "two +1/+1 counters and a trample counter" - one `ENTERS_WITH` per kind.
_AND_ANOTHER_KIND = re.compile(
    rf"^(?P<first>.+? counters?) and (?P<second>(?:an?|{COUNT}) [^ ]+ counters?)$", re.IGNORECASE
)


#: CR 614.1c's "enters with your choice of a `<kind>` counter or a `<kind>`
#: counter" (Boot Nipper, Wingfold Pteron) and "your choice of two different
#: counters from among `<list>`" (Grimdancer): one counter per pick, picked
#: from the printed kinds as the permanent enters (CR 614.12a).
_CHOICE_OF_TWO_KINDS = re.compile(
    r"^your choice of an? (?P<a>.+?) counter or an? (?P<b>.+?) counter(?: on it)?$",
    re.IGNORECASE,
)
_CHOICE_OF_DIFFERENT = re.compile(
    rf"^your choice of (?P<n>{COUNT}) different counters(?: on it)? from among (?P<kinds>.+)$",
    re.IGNORECASE,
)
_WHERE_X_IS = re.compile(r"^where x is (?P<expression>.+)$", re.IGNORECASE)
_TRAILING_ON_IT = re.compile(r"\s+on (?:it|him|her|them)$", re.IGNORECASE)


def choice_counter_options(what: str) -> tuple[int, tuple[str, ...]] | None:
    """`(picks, kinds)` for a "your choice of ..." counter phrase, else None."""
    text = what.strip()
    pair = _CHOICE_OF_TWO_KINDS.match(text)
    if pair is not None:
        return 1, (pair.group("a").lower(), pair.group("b").lower())
    different = _CHOICE_OF_DIFFERENT.match(text)
    if different is not None:
        picks = parse_count(different.group("n"))
        kinds = tuple(
            part.strip().lower()
            for part in re.split(r",\s*(?:and |or )?|\s+(?:and|or)\s+", different.group("kinds"))
            if part.strip()
        )
        if picks is not None and 0 < picks <= len(kinds):
            return picks, kinds
    return None


def _enters_with_effects(
    sentence: str,
    names: tuple[str, ...],
    *,
    subject: str,
    what: str,
    condition: str | None,
    tapped: bool = False,
    tail: str | None = None,
) -> list[ReplacementEffect]:
    """The effects of one "[This] enters [tapped] with `what`" sentence:
    CR 614.1d's tapped entry when printed, then one `ENTERS_WITH` per counter
    kind (CR 614.1c), carrying a trailing "and with haste" rider."""
    effects: list[ReplacementEffect] = []
    if tapped:
        effects.append(
            _make(
                ReplacementKind.ENTERS_TAPPED,
                sentence,
                subject=subject,
                tapped=True,
                self_replacement=_refers_to_self(subject, names),
            )
        )
    shared = {
        "subject": subject,
        "condition": condition,
        "self_replacement": _refers_to_self(subject, names),
    }
    if choice_counter_options(what) is not None:
        effects.append(
            _make(ReplacementKind.ENTERS_WITH, sentence, replacement=what.strip(), **shared)
        )
        return effects
    parts = [what]
    haste = _AND_WITH_HASTE.search(what)
    if haste is not None:
        parts = [what[: haste.start()]]
    paired = _AND_ANOTHER_KIND.match(_TRAILING_ON_IT.sub("", parts[0]))
    if paired is not None:
        parts = [paired.group("first"), paired.group("second")]
    for index, part in enumerate(parts):
        part = _TRAILING_ON_IT.sub("", part)
        counters = _read_multiplied_counters(part) or _read_counters(part)
        if counters is None:
            # A counter count this cannot read fails closed as UNPARSED rather
            # than as an enters-with effect with a made-up amount or kind.
            return [ReplacementEffect(kind=ReplacementKind.UNPARSED, raw=sentence, text=sentence)]
        amount, variable, counter_kind, expression, that_many_multiplier = counters
        defined = _WHERE_X_IS.match(tail or "")
        if (
            defined is not None
            and variable
            and expression is None
            and amount is None
            and _TURNS_SINCE_FORETOLD_RE.search(defined.group("expression")) is None
        ):
            # "... X +1/+1 counters on him, where X is the mana value of the
            # returned creature": the count is the defined expression, not
            # CR 107.3m's announced X.
            expression = defined.group("expression").strip().rstrip(".")
        effects.append(
            _make(
                ReplacementKind.ENTERS_WITH,
                sentence,
                replacement=part + (" and with haste" if haste and index == 0 else ""),
                amount=amount,
                variable_amount=variable,
                counter_kind=counter_kind,
                amount_expression=expression,
                that_many_multiplier=that_many_multiplier,
                **shared,
            )
        )
    return effects


def _try_enters_with(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _ENTERS_WITH.match(sentence)
    if not match:
        return []
    condition = (
        match.group("condition")
        or match.group("trailing_condition")
        or match.group("trailing_unless")
        or ""
    ).strip() or None
    return _enters_with_effects(
        sentence,
        names,
        subject=match.group("subject").strip(),
        what=match.group("what").strip(),
        condition=condition,
        tapped=match.group("tapped") is not None,
        tail=match.group("tail"),
    )


def _try_escapes_with(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    """CR 702.138c's "escapes with": an `ENTERS_WITH` whose condition is
    "this permanent escaped" (CR 702.138b)."""
    match = _ESCAPES_WITH.match(sentence)
    if not match:
        return []
    return _enters_with_effects(
        sentence,
        names,
        subject=match.group("subject").strip(),
        what=match.group("what").strip(),
        condition=ESCAPED_CONDITION,
    )


def _escaped(game: "Game", entering: CardState) -> bool:
    """CR 702.138b: "A spell or permanent "escaped" if that spell or the spell
    that became that permanent as it resolved was cast from a graveyard with
    an escape ability." Read off the resolving spell's own cast record, which
    `Game.resolve_top` has not popped yet as the permanent enters; an object
    arriving any other way has no record and did not escape."""
    record = game.cast_record_of(entering)
    return record is not None and (record.keyword or "").lower() == "escape"


def _kicked_count(game: "Game", entering: CardState) -> int:
    """CR 702.33d: how many times the spell that became `entering` was kicked
    (`CastRecord.kicked`, fixed as it was cast). A permanent that was never
    cast was never kicked."""
    record = game.cast_record_of(entering)
    return record.kicked if record is not None else 0


# -- "if a [nontoken] creature would enter and it wasn't cast, exile it instead" --
#
# Containment Priest's static line; Mistcaller's and Hallowed Moonlight's
# "Until end of turn, ..." created form of the same sentence (`EnterUncastExile`
# is the one reader for both, see `created_replacement_spec`).

_ENTERS_UNCAST_EVENT_RE = re.compile(
    r"^an? (?P<nontoken>nontoken )?(?P<type>[a-z]+) would enter(?: the battlefield)?"
    r" and it wasn.?t cast$",
    re.IGNORECASE,
)


def read_enter_uncast_exile(effect: ReplacementEffect) -> "EnterUncastExile | None":
    """`EnterUncastExile`'s reader, shared by the static and created forms."""
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    if (effect.replacement or "").strip().rstrip(".").lower() != "exile it":
        return None
    match = _ENTERS_UNCAST_EVENT_RE.match((effect.event or "").strip())
    if match is None:
        return None
    wanted = _CARD_TYPE_WORDS.get(match.group("type").lower())
    if wanted is None:
        return None
    return EnterUncastExile(types=(wanted,), nontoken=match.group("nontoken") is not None)


def _compile_enters_uncast_exile(effect: ReplacementEffect) -> CardReplacement | None:
    spec = read_enter_uncast_exile(effect)
    return None if spec is None else _static_form(effect.text, spec)


# -- "lands you control enter untapped" (CR 614.1d, general and non-self) --


def _lands_you_control_enter_untapped_applies(
    game: "Game", source: CardState, event: ReplaceableEvent
) -> bool:
    """ "Lands you control enter untapped" - Spelunking's own second paragraph.

    Unlike `_ENTERS_TAPPED`'s self-only shockland shape, this watches every
    land entering under its controller's control, not only Spelunking's own
    arrival - CR 614.12's "may come from the permanent itself if [it affects]
    only that permanent" is exactly the case this is *not*: "lands you
    control" plainly affects other objects.
    """
    if event.kind is not EventKind.ENTERS_BATTLEFIELD or event.card is None:
        return False
    return (
        Type.LAND in event.card.types
        and event.card.controller is not None
        and event.card.controller == source.controller
    )


def _lands_you_control_enter_untapped(
    game: "Game", source: CardState, event: ReplaceableEvent
) -> None:
    """ "...enter untapped." Overrides whatever tapped state the event already
    carried - a search's own "tapped" (CR 614.1d applies alongside whatever
    other replacement effect already ran, CR 616.1), a shockland's own "enters
    tapped" - CR 110.5b's default the sentence restates rather than a new one.
    """
    event.tapped = False


def _compile_lands_you_control_enter_untapped(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.ENTERS_UNTAPPED:
        return None
    if effect.self_replacement:
        # A self-referential "this land enters untapped" would already be
        # read by `_self_enters_modifiers` instead (CR 614.12) - not printed
        # by any card in this pool, but excluded here so the two paths never
        # double up if one ever is.
        return None
    subject = (effect.subject or "").strip().lower()
    if subject != "lands you control":
        return None
    return CardReplacement(
        label=effect.text,
        applies=_lands_you_control_enter_untapped_applies,
        apply=_lands_you_control_enter_untapped,
    )


def _compile_opponents_permanents_enter_tapped(
    effect: ReplacementEffect,
) -> CardReplacement | None:
    """Kinjalli's Sunwing's "Creatures your opponents control enter tapped."

    CR 614.12: which of these applies is judged on the permanent "as it would
    exist on the battlefield" - `event.card.types` is read while
    `Game.put_onto_battlefield` holds `CardState._entering_battlefield`, so a
    card that is a creature only off the battlefield (CR 113.6c) is not one
    here.
    """
    if effect.kind is not ReplacementKind.ENTERS_TAPPED or effect.self_replacement:
        return None
    if effect.condition:
        return None
    if effect.replacement is not None:
        return None
    classes = _read_opponents_permanent_classes(effect.subject or "")
    if classes is None:
        return compile_group_enter_tapped(effect)

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        card = event.card
        if event.kind is not EventKind.ENTERS_BATTLEFIELD or card is None:
            return False
        if not _is_opponent(game, card.controller, source.controller):
            return False
        types = card.types
        return any(
            card_type in types and not (nonbasic and Supertype.BASIC in card.supertypes)
            for card_type, nonbasic in classes
        )

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.tapped = True

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


# --------------------------------------------------------------------------
# "Can't enter the battlefield" (CR 614.17d)
# --------------------------------------------------------------------------
#
# CR 614.17, verified this session: "Some effects state that something can't
# happen. These effects aren't replacement effects, but follow similar rules."
# CR 614.17d names this family in particular: "Some 'can't' effects modify how
# a permanent enters the battlefield or whether it can enter the battlefield.
# Such effects may come from the permanent itself if they affect only that
# permanent". Grafdigger's Cage's is the general kind - it watches every
# creature card in every graveyard and library, not itself.
#
# "Follow similar rules" is why this is carried on the same `ENTERS_BATTLEFIELD`
# event the real replacement effects use, and the docstring on `_cant_enter`
# says what that costs: CR 614.17c's "if an event can't happen, it can only be
# replaced by a self-replacement effect" is a *precedence* rule this machinery
# has no way to express, so a can't-enter effect here competes for CR 616.1's
# ordering rather than pre-empting it.
#
# The card does not say where the object goes, and CR 400.4a's sibling wording
# for a card that cannot enter - "it remains in its previous zone" - is what
# happens: the event's destination is set back to its origin.

_CANT_ENTER_RE = re.compile(
    r"^(?:non(?P<excluded>artifact|creature|enchantment|land|planeswalker) )?"
    r"(?P<filter>artifact|creature|enchantment|land|permanent|planeswalker) "
    r"cards in (?P<zones>[\w, ]+?) can'?t enter the battlefield\.?$",
    re.IGNORECASE,
)


def _cant_enter(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
    """The object does not enter; it stays where it was.

    CR 400.4a states the same outcome for the rules' own can't-enter case -
    "if an instant or sorcery card would enter the battlefield, it remains in
    its previous zone" - and CR 614.6's "the original event never happens" is
    what makes the rest follow: nothing enters, so no enters-the-battlefield
    ability triggers (CR 603.6a) and any counters or tapped state the event was
    carrying go with it. `Game.enter_the_battlefield` reads the destination
    back and returns the card to that zone.
    """
    if event.origin is not None:
        event.destination = event.origin


def _cant_enter_applies(
    wanted: Type | None, excluded: Type | None, zones: frozenset[Zone]
) -> Applies:
    """ "**Creature cards** in graveyards and libraries can't enter the battlefield."

    "Cards", so a token is excluded: CR 111.6, "a token isn't a card", and a
    token being created has no origin zone worth the name anyway. The type is
    read off the entering object's own types, and the origin off the event -
    which is why this refuses a creature entering from a hand, from exile, or
    as a resolving spell off the stack, all of which the Cage leaves alone.

    `wanted` is `None` for Soulless Jailer's "Permanent cards" - CR 110.1
    already excludes instants and sorceries from the only event this fires on,
    so a bare "permanent" filter is the same as no filter at all, the same
    reading `_copy_candidates` already gives that word. `excluded` is
    Weathered Runestone's "Nonland permanent" - the one negated type word a
    two-word filter may carry, checked the same way `_copy_candidates`'
    own `excluded` group is.
    """

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        card_state = event.card
        if event.kind is not EventKind.ENTERS_BATTLEFIELD or card_state is None:
            return False
        if event.origin not in zones or is_token(card_state):
            return False
        types = card_state.types
        if wanted is not None and wanted not in types:
            return False
        return excluded is None or excluded not in types

    return applies


def _cant_enter_replacements(card: Card) -> list[CardReplacement]:
    """Grafdigger's Cage's first line, and anything else printed to that shape.

    Read straight off the oracle text rather than through
    `parse_replacement_effects`: CR 614.17 says these are not replacement
    effects, so the parser at the top of this module correctly refuses to
    claim them (the sentence carries none of its cue words either).
    """
    found: list[CardReplacement] = []
    for line in (card.oracle_text or "").splitlines():
        rules_text, _ = strip_reminder_text(line)
        match = _CANT_ENTER_RE.match(rules_text.strip())
        if match is None:
            continue
        word = match.group("filter").lower()
        wanted = None if word == "permanent" else _CARD_TYPE_WORDS.get(word)
        if wanted is None and word != "permanent":
            continue
        excluded = _CARD_TYPE_WORDS.get((match.group("excluded") or "").lower())
        zones = _read_zone_list(match.group("zones"))
        if zones is None:
            continue
        found.append(
            CardReplacement(
                label=f"{rules_text.strip()} (CR 614.17d)",
                applies=_cant_enter_applies(wanted, excluded, zones),
                apply=_cant_enter,
            )
        )
    return found


def reads_cant_enter_line(text: str) -> bool:
    """Whether one printed static line is a "<type> cards in <zones> can't
    enter the battlefield" rule `_cant_enter_replacements` enforces in full
    (CR 614.17d) - its type word and every zone word read - which is
    `support.py`'s credit for it."""
    match = _CANT_ENTER_RE.match(strip_reminder_text(text)[0].strip())
    if match is None:
        return False
    word = match.group("filter").lower()
    if word != "permanent" and _CARD_TYPE_WORDS.get(word) is None:
        return False
    return _read_zone_list(match.group("zones")) is not None


# --------------------------------------------------------------------------
# Effects a permanent generates about itself (CR 614.12)
# --------------------------------------------------------------------------


#: "you may pay 2 life" - the optional half of a shockland's CR 614.12a choice.
_PAY_LIFE_CHOICE = re.compile(r"you may pay (\d+) life", re.IGNORECASE)

#: The other half: "If you don't, it enters tapped." The parser puts "you don't"
#: in `condition`, and it is a back-reference to the payment rather than a
#: condition about the board, which is what makes the pair one choice.
_IF_YOU_DONT = re.compile(r"^(?:if )?you don[’']?t$", re.IGNORECASE)


def _pay_life_or_tapped(amount: int, card_name: str) -> Apply:
    """The shockland branch, as one CR 614.12a choice made before it enters.

    CR 614.12a: "If a replacement effect that modifies how a permanent enters
    the battlefield requires a choice, that choice is made before the permanent
    enters the battlefield." This runs inside `apply_replacements`, which
    `Game.enter_the_battlefield` calls before the card is put onto the
    battlefield, so the timing is right by construction.

    CR 119.4 decides whether paying is even an option, and `Game.may_pay_life`
    asks it: below the life total the payment is illegal, CR 608.2d then forbids
    choosing it, and the land enters tapped with nobody having decided anything.
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        who = event.card.controller if event.card is not None else None
        if who is None:
            event.tapped = True
            return
        if not game.may_pay_life(who, amount, source=card_name, source_id=source_id_of(source)):
            event.tapped = True

    return apply


#: "you may reveal a Plains or Island card from your hand" - the optional half
#: of a reveal land's CR 614.12a choice. The part after "you may" is an
#: ordinary reveal cost, read by the same `total_cost_for_phrase` a spell's
#: "Reveal X white cards from your hand" is.
_REVEAL_CHOICE = re.compile(r"^you may (?P<cost>reveal .+ from your hand)\.?$", re.IGNORECASE)

#: "you may behold a Jace" (Theorist's Sanctum) - CR 701.4a's keyword action
#: as the optional half of the same CR 614.12a choice, read the same way
#: `_REVEAL_CHOICE` reads a reveal land's own offer.
_BEHOLD_CHOICE = re.compile(r"^you may (?P<cost>behold (?:a|an) .+)\.?$", re.IGNORECASE)


def _optional_enters_payment(effect: ReplacementEffect, card_name: str) -> Apply | None:
    """What an optional "As this enters, you may ..." (CR 614.1c) does as the
    permanent enters, or `None` when no reader claims its payment.

    Its caller pairs it with the "If you don't, it enters tapped" that
    follows, because the two sentences are one CR 614.12a choice. Three
    payments are read: paying life (the shocklands), revealing a card of a
    stated quality from hand (the reveal lands, whatever quality they print),
    and beholding a quality (Theorist's Sanctum, CR 701.4a).
    """
    replacement = (effect.replacement or "").strip()
    payment = _PAY_LIFE_CHOICE.search(replacement)
    if payment:
        return _pay_life_or_tapped(int(payment.group(1)), card_name)
    from ..cost import ComponentKind, total_cost_for_phrase

    behold = _BEHOLD_CHOICE.match(replacement)
    if behold is not None:
        phrase = behold.group("cost")
        cost = total_cost_for_phrase(phrase)
        if (
            cost is None
            or cost.mana.symbols
            or len(cost.components) != 1
            or cost.components[0].kind is not ComponentKind.BEHOLD
        ):
            return None
        return _behold_or_tapped(phrase, card_name)
    reveal = _REVEAL_CHOICE.match(replacement)
    if reveal is None:
        return None
    phrase = reveal.group("cost")
    cost = total_cost_for_phrase(phrase)
    if (
        cost is None
        or cost.mana.symbols
        or len(cost.components) != 1
        or cost.components[0].kind is not ComponentKind.REVEAL
        or cost.components[0].variable_count
    ):
        return None
    return _reveal_or_tapped(phrase, card_name)


def _or_you_control(choice: Apply, subtype: str) -> Apply:
    """A reveal land's "...unless you revealed a <type> card this way or you
    control a <type>" (CR 614.12a): the same optional reveal, then the land
    stays untapped anyway when its controller already controls the subtype."""
    controls = _controls_a_subtype(frozenset({subtype}))

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        was_tapped = event.tapped
        choice(game, source, event)
        if (
            not was_tapped
            and event.tapped
            and event.card is not None
            and controls(game, event.card)
        ):
            event.tapped = False

    return apply


def _reveal_or_tapped(phrase: str, card_name: str) -> Apply:
    """A reveal land's branch, as one CR 614.12a choice made before it enters.

    With no qualifying card in hand there is nothing to reveal (CR 118.3), so
    nobody is asked and the land enters tapped. Otherwise its controller is
    asked whether to reveal; yes asks which card (`Game.choose_cards_to_reveal`,
    the question a reveal cost on a spell asks) and pays the reveal, which
    shows the card to every player and leaves it in hand (CR 701.20a-b); no
    enters it tapped.
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        from ..cost import total_cost_for_phrase

        who = event.card.controller if event.card is not None else None
        cost = total_cost_for_phrase(phrase, who) if who is not None else None
        if who is None or cost is None:
            event.tapped = True
            return
        (component,) = cost.components
        component.source = card_name
        entering_id = event.card.id if event.card is not None else None
        eligible = [
            card
            for card in game.player(who).hand
            if card.id != entering_id
            and (
                component.requirement is None
                or component.requirement.why_not(card, game, who) is None
            )
        ]
        source_id = source_id_of(source)
        if not eligible or not game.may(
            who, phrase, source=card_name, source_id=source_id, cards=eligible
        ):
            event.tapped = True
            return
        game.choose_cards_to_reveal(component, who, source=card_name, source_id=source_id)
        if component.why_not(game) is not None:
            event.tapped = True
            return
        component.pay(game)

    return apply


def _behold_or_tapped(phrase: str, card_name: str) -> Apply:
    """Theorist's Sanctum's own branch, as one CR 614.12a choice made before
    it enters: "As this land enters, you may behold a Jace. If you don't,
    this land enters tapped."

    CR 701.4a's two halves both count as eligible objects here - a hand card
    to reveal, or a battlefield permanent already controlled - and the
    controller is asked which, if either, once at least one exists; no
    eligible object at all enters the land tapped with nobody asked
    (CR 118.3), the same as `_reveal_or_tapped`'s hand-only version.
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        from ..cost import total_cost_for_phrase

        who = event.card.controller if event.card is not None else None
        cost = total_cost_for_phrase(phrase, who) if who is not None else None
        if who is None or cost is None:
            event.tapped = True
            return
        (component,) = cost.components
        component.source = card_name
        entering_id = event.card.id if event.card is not None else None
        eligible = [
            card
            for card in list(game.player(who).hand) + list(game.permanents_controlled_by(who))
            if card.id != entering_id
            and (
                component.requirement is None
                or component.requirement.why_not(card, game, who) is None
            )
        ]
        source_id = source_id_of(source)
        if not eligible or not game.may(
            who, phrase, source=card_name, source_id=source_id, cards=eligible
        ):
            event.tapped = True
            return
        answer = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=who,
                prompt=f"choose what to behold for {card_name} (CR 701.4a)",
                source=card_name,
                source_id=source_id,
                amount=1,
                cards=tuple(card.id for card in eligible),
            )
        )
        by_id = {card.id: card for card in eligible}
        component.cards = [by_id[chosen_id] for chosen_id in answer]
        if component.why_not(game) is not None:
            event.tapped = True
            return
        component.pay(game)

    return apply


# --------------------------------------------------------------------------
# "As [this] enters, [you may] sacrifice any number of <description>. [If you
# do, ]it enters with [<multiplier>] that many <kind> counters on it."
# --------------------------------------------------------------------------
#
# CR 614.12a's choice again, the same two-sentences-as-one-choice shape
# `_pay_life_or_tapped` reads for the shockland - just paired with an
# ENTERS_WITH follower instead of an ENTERS_TAPPED one, and the payment is a
# count of sacrificed permanents rather than a fixed amount of life.
#
# Shimatsu the Bloodcloaked ("As Shimatsu enters, sacrifice any number of
# permanents. Shimatsu enters with that many +1/+1 counters on it.") is
# mandatory - the sacrifice is not itself a "you may" - and the follower
# carries no back-reference condition at all. Devouring Hellion ("As this
# creature enters, you may sacrifice any number of creatures and/or
# planeswalkers. If you do, it enters with twice that many +1/+1 counters on
# it.") is worded as a choice, and its follower's condition is the "you do"
# back-reference `_IF_YOU_DO` reads, the same way `_IF_YOU_DONT` reads the
# shockland's "you don't". Both are read the same way underneath: CR 107.1c's
# "any number of" already permits choosing zero on its own, so neither needs a
# separate yes/no question before the CHOOSE_CARDS one - see
# `_sacrifice_any_number_then_enter_with_counters`.

#: "If you do" - Devouring Hellion's back-reference to its own "you may
#: sacrifice" half, the same role `_IF_YOU_DONT` plays for the shockland's
#: "you don't".
_IF_YOU_DO = re.compile(r"^(?:if )?you do$", re.IGNORECASE)
#: A paragraph that is a Devour keyword line (CR 702.82a/c), which
#: `parse._expand_devour` spells out as the sacrifice-then-counters pair
#: below - the one source whose sacrifices are "devoured" (CR 702.82b).
_DEVOUR_LINE_RE = re.compile(r"^devour\b", re.IGNORECASE)

#: "sacrifice any number of <description>" (Shimatsu, mandatory) or "you may
#: sacrifice any number of <description>" (Devouring Hellion, optional) - read
#: off an `AS_ENTERS` effect's own `replacement` text. `description` is handed
#: to `machines/effects._sacrifice_restriction`, the same untargeted-
#: permanent-description reader CR 118.12's "you may sacrifice <restriction>.
#: If you do, ..." clause already uses, so "permanents" and "creatures and/or
#: planeswalkers" both read through the one shared grammar rather than a
#: second one built here.
_SACRIFICE_ANY_NUMBER_RE = re.compile(
    r"^(?P<optional>you may )?sacrifice (?P<restriction>any number of .+?)\.?$", re.IGNORECASE
)


def _sacrifice_any_number_choice(effect: ReplacementEffect) -> tuple[str, bool] | None:
    """`(restriction, optional)` off an `AS_ENTERS` "[you may ]sacrifice any
    number of <description>" replacement text, or `None` when it is not that
    shape at all. `restriction` keeps the "any number of" quantity phrase on
    the front - `machines.effects._sacrifice_restriction` reads the quantity
    and the description together, the same text CR 118.12's own "you may
    sacrifice <restriction>" clause hands it.
    """
    match = _SACRIFICE_ANY_NUMBER_RE.match((effect.replacement or "").strip())
    if match is None:
        return None
    return match.group("restriction").strip(), match.group("optional") is not None


def _action_then_enter_with_counters(
    action: "Action", follower: ReplacementEffect, card_name: str
) -> Apply:
    """CR 614.12a: an "As [this] enters" action (reveal, return, exile, put),
    then the counters the sentence after it sizes from how many objects it
    acted on (`as_enters_actions.counters_for`)."""
    kind = follower.counter_kind
    assert kind is not None

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        entering = event.card
        who = entering.controller if entering is not None else None
        if who is None or entering is None:
            return
        done = action(game, who, event, source, card_name)
        amount = counters_for(
            game,
            who,
            entering,
            done,
            amount=follower.amount,
            expression=follower.amount_expression,
            condition=follower.condition,
        )
        if amount > 0:
            event.counters[kind] = event.counters.get(kind, 0) + amount

    return apply


def _sacrifice_any_number_then_enter_with_counters(
    restriction: "_SacrificeRestriction",
    counter_kind: str,
    multiplier: int,
    card_name: str,
    *,
    devour: bool = False,
) -> Apply:
    """The combined CR 614.12a choice: sacrifice, then carry the count into
    the entering permanent's own counters.

    `restriction` is a `machines.effects._SacrificeRestriction`, imported for
    typing only: `effects` already imports this module.

    Runs entirely before `Game.enter_the_battlefield` puts the permanent onto
    the battlefield (CR 614.12a), against `restriction.candidates` - the
    controller's other permanents fitting the printed description, off the
    *computed* board (CR 613.5), which never includes the entering permanent
    itself: it is not in `game.battlefield` yet at this point (CR 614.12a
    again - the choice is made *before* it enters). One `CHOOSE_CARDS`
    question, `exact=False` (CR 107.1c's "any number of" - zero is always a
    legal answer, and an unscripted answer defaults to none per
    `machines/decisions.default_answer`), so neither Shimatsu's mandatory
    sacrifice nor Devouring Hellion's "you may" wording is asked a separate
    yes/no first - the range itself already carries the option. Each chosen
    permanent is sacrificed (`Game.sacrifice`, CR 701.21a), and the number
    actually sacrificed - zero included - times `multiplier` is the count
    `_apply_self_enters` elsewhere in this module would otherwise have needed
    a literal number for.
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        who = event.card.controller if event.card is not None else None
        if who is None:
            return
        player = game.player(who)
        source_id = source_id_of(source)
        candidates = restriction.candidates(game, player, source.id if source is not None else None)
        chosen_ids: tuple[UUID, ...] = ()
        if candidates:
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=who,
                    prompt=f"choose permanents to sacrifice as {card_name} enters",
                    source=card_name,
                    source_id=source_id,
                    amount=len(candidates),
                    exact=False,
                    cards=tuple(candidate.id for candidate in candidates),
                )
            )
            assert isinstance(answer, tuple)
            chosen_ids = answer
        by_id = {candidate.id: candidate for candidate in candidates}
        chosen = [by_id[card_id] for card_id in chosen_ids]
        if devour and event.card is not None:
            # CR 702.82b: what "it devoured" counts, each as it last existed
            # on the battlefield (CR 608.2h) - read before it is sacrificed.
            event.card.devoured = tuple(
                DevouredObject(
                    types=tuple(game.characteristics_of(permanent).types),
                    subtypes=tuple(game.characteristics_of(permanent).subtypes),
                )
                for permanent in chosen
            )
        for permanent in chosen:
            game.sacrifice(permanent)
        event.counters[counter_kind] = (
            event.counters.get(counter_kind, 0) + len(chosen) * multiplier
        )

    return apply


# --------------------------------------------------------------------------
# The condition on a self "enters tapped" line (CR 614.1d)
# --------------------------------------------------------------------------
#
# CR 614.1d is the bare "[This permanent] enters . . ." wording, and most of
# the pool's printings of it carry a condition about the board rather than
# about a choice: "unless you control a Mountain", "if you control two or more
# other lands", "unless a player has 13 or less life". The condition was parsed
# and then dropped, so Arena of Glory entered *untapped* on an empty board -
# a wrong board state, not a missing one.
#
# **Polarity.** A leading "If <cond>, this land enters tapped" taps when the
# condition holds; a trailing "... enters tapped unless <cond>" taps when it
# does not. `_ENTERS_TAPPED` keeps the literal word "unless" on the second
# form, so the two are told apart by the text itself and no extra field is
# needed on `ReplacementEffect`.
#
# **Fail closed.** A condition none of the readers below claims returns `None`
# and the effect is skipped entirely, exactly as every conditional line was
# before this - a land that is silently untapped is the same wrong answer it
# already gave, and it is better than taxing an unread clause into a guess.
# The shockland back-reference "you don't" is one of those: it is not about the
# board at all, it is the other half of the CR 614.12a choice that
# `_self_enters_modifiers` pairs up above, and no reader here matches it.

#: "does this condition hold right now", for the entering permanent.
EntersCondition = Callable[["Game", CardState], bool]

#: "unless you control a Mountain", "unless you control a Plains or an Island".
#: Land subtypes are proper nouns as printed (CR 205.3i, CR 305.5: "Land
#: subtypes are always a single word"), so the capital letter is required -
#: that is what keeps this from claiming an arbitrary "you control a ..."
#: noun phrase it cannot actually check.
_YOU_CONTROL_SUBTYPES_RE = re.compile(r"^you control (an? [A-Z][\w'-]*(?: or an? [A-Z][\w'-]*)*)$")
_A_SUBTYPE_RE = re.compile(r"an? ([A-Z][\w'-]*)")

#: "unless you control a planeswalker" (the fra "Annex"/"Commons" land
#: cycle's own shape) - CR 300.1's bare card type, told apart from
#: `_YOU_CONTROL_SUBTYPES_RE`'s subtype by the capital: Oracle text never
#: capitalises a card type the way it always capitalises a subtype
#: (CR 205.3), so the two shapes never collide.
_YOU_CONTROL_CARD_TYPE_RE = re.compile(
    r"^you control an? (?P<type>artifact|creature|enchantment|land|planeswalker)$",
    re.IGNORECASE,
)

#: Ba Sing Se's own "This land enters tapped unless you control a basic
#: land." CR 205.4c: "basic" is a supertype, not one of CR 305.6's five land
#: *types* - `_YOU_CONTROL_SUBTYPES_RE` above needs a capitalised proper noun
#: ("a Mountain") and would never match this lower-case supertype word, and
#: `_YOU_CONTROL_CARD_TYPE_RE` names only CR 300.1's card types, "land"
#: included but with no supertype qualifier - so this is its own reader
#: rather than a tweak to either.
_YOU_CONTROL_A_BASIC_LAND_RE = re.compile(r"^you control an? basic land$", re.IGNORECASE)

#: "you control two or more other lands", "you control two or fewer other lands",
#: the battle lands' "you control two or more basic lands" (CR 205.4c), and
#: "you control three or more other Mountains" (Dwarven Mine). A land subtype
#: is a capitalized single word (CR 305.5), so the capital is required even
#: under IGNORECASE - "other creatures" is a noun this cannot check.
_YOU_CONTROL_OTHER_LANDS_RE = re.compile(
    rf"^you control (?P<count>{COUNT}) or (?P<direction>more|fewer) "
    r"(?:(?P<other>other) )?(?:(?P<basic>basic) )?"
    r"(?:lands|(?P<subtype>(?-i:[A-Z])[\w'-]*))$",
    re.IGNORECASE,
)

#: "a player has 13 or less life" - any player at the table, not only the
#: entering permanent's controller (Lakeside Shack).
_A_PLAYER_HAS_LIFE_RE = re.compile(
    r"^a player has (?P<count>\d+) or (?P<direction>less|more) life$", re.IGNORECASE
)

#: "X is 2 or less" - Slumbering Trudge, whose tapped state is decided by the
#: value chosen for X as it was cast (CR 601.2b records the choice;
#: `Game.cast_records` is what holds it here, the same record CR 107.3m's
#: enters-with-X counters already read a few lines below).
_X_IS_RE = re.compile(r"^x is (?P<count>\d+) or (?P<direction>less|greater)$", re.IGNORECASE)


def _controls_a_subtype(subtypes: frozenset[str]) -> EntersCondition:
    def holds(game: "Game", entering: CardState) -> bool:
        controller = entering.controller
        if controller is None:
            return False
        # One board, hoisted out of the loop below (CR 613.5: `computed_board`
        # recomputes the whole battlefield every call) - a permanent's
        # *computed* subtypes are what "you control a Mountain" asks about, so
        # a nonbasic land Blood Moon (CR 305.7) already made a Mountain counts
        # even though it prints no subtype at all.
        board = game.computed_board()
        return any(
            subtype in subtypes
            for permanent in game.battlefield
            if permanent.controller == controller
            for subtype in board.of(permanent).subtypes
        )

    return holds


def _controls_a_card_type(card_type: Type) -> EntersCondition:
    """`_controls_a_subtype`'s twin over CR 300.1's card types instead of
    CR 205.3's subtypes - "you control a planeswalker", not "you control a
    Mountain".
    """

    def holds(game: "Game", entering: CardState) -> bool:
        controller = entering.controller
        if controller is None:
            return False
        board = game.computed_board()
        return any(
            card_type in board.of(permanent).types
            for permanent in game.battlefield
            if permanent.controller == controller
        )

    return holds


def _controls_a_basic_land() -> EntersCondition:
    """Ba Sing Se's own "unless you control a basic land" (CR 205.4c's
    supertype, not one of CR 305.6's five land types) - `_controls_a_
    subtype`'s and `_controls_a_card_type`'s twin over the "basic" supertype
    instead. `board.of(permanent).is_basic` is the identical CR 613.5
    computed-board read `_controls_other_lands`'s own "basic" qualifier
    already uses for the battle lands' "you control two or more basic
    lands" - a nonbasic land a Blood Moon-style effect already turned into a
    plain Mountain (CR 305.7 strips the "basic" supertype question not at
    all - the supertype is untouched by a type-setting effect, see CR 305.7's
    own "doesn't add or remove any ... supertypes") does not count, and a
    creature land some other effect made a land-and-something-else still
    does, since `is_basic` asks only about the supertype.
    """

    def holds(game: "Game", entering: CardState) -> bool:
        controller = entering.controller
        if controller is None:
            return False
        board = game.computed_board()
        return any(
            Type.LAND in board.of(permanent).types and board.of(permanent).is_basic
            for permanent in game.battlefield
            if permanent.controller == controller
        )

    return holds


#: Morbid's own condition (CR 207.2c, the ability word stripped before this
#: is ever reached) - "a creature died this turn", Festerhide Boar's own
#: enters-with gate. CR 700.4: "'Dies' means 'is put into a graveyard from
#: the battlefield.'" `Game.creatures_died_this_turn` is the running count
#: `machines/triggers.py`'s own `_creatures_died_this_turn_holds` already
#: reads for the *triggered*-ability shape of the same fact (Darklight
#: Phoenix's "two or more creatures died this turn"); this is the bare,
#: singular "a creature died" form - any death counts, not a threshold - for
#: a *replacement* effect's own condition instead of a triggered ability's
#: intervening if, which is why it is read here rather than imported from
#: that module (the fact is shared, the reading site is not).
def _a_creature_died_this_turn(game: "Game", entering: CardState) -> bool:
    return game.creatures_died_this_turn > 0


def _controls_other_lands(
    count: int, at_least: bool, basic: bool = False, subtype_plural: str | None = None
) -> EntersCondition:
    """ "you control [N] or more/fewer **other** [lands | Mountains]".

    `subtype_plural` is the printed plural of a land type (CR 205.3i), matched
    against each land's computed subtypes as that word or that word plus "s" -
    "Plains" is its own plural, "Mountains" is "Mountain" plus one.

    "Other" is why the entering permanent is excluded by id: CR 614.12's
    effects are read while the permanent is still on its way in
    (`Game.enter_the_battlefield` calls `apply_replacements` before putting it
    onto the battlefield), so it is not in `game.battlefield` yet - the
    exclusion is belt and braces against a caller that puts it there first.
    """

    def holds(game: "Game", entering: CardState) -> bool:
        controller = entering.controller
        if controller is None:
            return False
        # One board, hoisted the same way `_controls_a_subtype` does: a
        # permanent's *computed* types (CR 613.5) decide "land" here, so a
        # creature a layer-4 effect already made a land (CR 205.1b) counts.
        board = game.computed_board()
        lands = sum(
            1
            for permanent in game.battlefield
            if permanent.controller == controller
            and Type.LAND in board.of(permanent).types
            # CR 205.4c: "basic" is the supertype, never a basic land type.
            and (not basic or board.of(permanent).is_basic)
            and (
                subtype_plural is None
                or any(
                    subtype_plural in (subtype, f"{subtype}s")
                    for subtype in board.of(permanent).subtypes
                )
            )
            and permanent.id != entering.id
        )
        return lands >= count if at_least else lands <= count

    return holds


def _a_player_has_life(count: int, at_most: bool) -> EntersCondition:
    def holds(game: "Game", entering: CardState) -> bool:
        return any(
            (player.life <= count if at_most else player.life >= count)
            for player in game.players_in_game
        )

    return holds


def _x_is(count: int, at_most: bool) -> EntersCondition:
    def holds(game: "Game", entering: CardState) -> bool:
        record = game.cast_record_of(entering)
        if record is None or record.x_value is None:
            # No announcement to read X off (CR 601.2b) - the permanent got
            # here some other way, X is undefined, and there is nothing to
            # decide the tapped state with. Fail closed, as above.
            return False
        return record.x_value <= count if at_most else record.x_value >= count

    return holds


#: Eddymurk Crab's own "This creature enters tapped if it's not your turn." -
#: CR 102.1's active player, read the identical way `Game.alternative_cost_
#: options` already reads Force of Negation's/Force of Vigor's own "if it's
#: not your turn" CR 118.9 gate (`self.turn.active_player != caster`), just
#: for the entering permanent's own controller instead of a caster.
_NOT_YOUR_TURN_RE = re.compile(r"^it'?s not your turn$", re.IGNORECASE)
#: Horned Loch-Whale's own "This creature enters tapped **unless** it's your
#: turn." - the same CR 102.1 fact stated the other way round: `_ENTERS_
#: TAPPED`'s "unless" branch strips the word "unless" before this is ever
#: asked, so the bare condition here is the *positive* "it's your turn",
#: negated by that branch's own polarity (`_enters_tapped_condition`) into
#: exactly `_not_your_turn`'s own answer - the two printings differ only in
#: which polarity they spell out.
_YOUR_TURN_RE = re.compile(r"^it'?s your turn$", re.IGNORECASE)

#: Starting Town's own "unless it's your first, second, or third turn of the
#: game." - CR 500.7's own per-player turn count (`TurnMachine.turns_taken_by`,
#: read through `Game.turn.own_turns_taken`), the identical running total
#: Steam Vents' shockland siblings never needed because none of them counted
#: a *player's own* turns rather than the board. The ordinal list is CR
#: 103.8's first turn onward, spelled out the way English numbers them
#: rather than as digits - only the ordinals actually printed in the pool
#: (through "tenth") are read; a card that printed a numeral instead ("your
#: 1st turn") would need its own reader, and none does yet.
_ORDINAL_WORDS: dict[str, int] = {
    word: number
    for number, word in enumerate(
        (
            "first",
            "second",
            "third",
            "fourth",
            "fifth",
            "sixth",
            "seventh",
            "eighth",
            "ninth",
            "tenth",
        ),
        start=1,
    )
}
_ORDINAL_WORD_RE = "|".join(_ORDINAL_WORDS)
_YOUR_TURN_ORDINAL_RE = re.compile(
    rf"^it'?s your (?P<ordinals>(?:{_ORDINAL_WORD_RE})"
    rf"(?:,\s*(?:{_ORDINAL_WORD_RE}))*"
    rf"(?:,?\s*or\s+(?:{_ORDINAL_WORD_RE}))?) turns? of the game$",
    re.IGNORECASE,
)


def _is_your_turn(game: "Game", entering: CardState) -> bool:
    controller = entering.controller
    return (
        controller is not None and game.turn is not None and game.turn.active_player == controller
    )


def _not_your_turn(game: "Game", entering: CardState) -> bool:
    return not _is_your_turn(game, entering)


def _your_turn_ordinal_or_earlier(highest: int) -> EntersCondition:
    """ "it's your first, second, or third turn of the game" (Starting Town)
    - true through the controller's own `highest`th turn (CR 500.7's
    per-player count, extra turns included), false from then on."""

    def holds(game: "Game", entering: CardState) -> bool:
        controller = entering.controller
        if controller is None or game.turn is None:
            return False
        return game.turn.own_turns_taken(controller) <= highest

    return holds


def _enters_tapped_condition(effect: ReplacementEffect) -> EntersCondition | None:
    """Read an `ENTERS_TAPPED` condition into "does it enter tapped", or `None`.

    The returned predicate already folds in the polarity, so its caller only
    has to ask it.
    """
    condition = (effect.condition or "").strip().rstrip(".")
    if not condition:
        return None

    negated = False
    lowered = condition.lower()
    if lowered.startswith("unless "):
        negated = True
        condition = condition[len("unless ") :].strip()

    inner = _read_enters_condition(condition)
    if inner is None:
        return None
    if not negated:
        return inner

    def tapped_unless(game: "Game", entering: CardState) -> bool:
        return not inner(game, entering)

    return tapped_unless


def _enters_with_condition(effect: ReplacementEffect) -> EntersCondition | None:
    """The gate of an "enters with counters" line (CR 614.1c), as a predicate
    on the permanent as it enters: the board-only readers of
    `_enters_tapped_condition` first, else the shared condition registry
    (`Game.condition_holds`) asked with the entering permanent as the source,
    so a cast-record fact (CR 702.33d "was kicked", CR 601.2h "at least three
    white mana was spent", raid, "you cast it from your hand") is read off the
    spell that became this permanent and never live. A shape neither reads is
    `None`, and a shape the registry declines to read at the moment it is asked
    never performs (it is not silently treated as true).
    """
    holds = _enters_tapped_condition(effect)
    if holds is not None:
        return holds
    condition = (effect.condition or "").strip().rstrip(".")
    negated = condition.lower().startswith("unless ")
    if negated:
        condition = condition[len("unless ") :].strip()
    if not condition:
        return None

    def holds_shared(game: "Game", entering: CardState) -> bool:
        controller = entering.controller or entering.owner
        if controller is None:
            return False
        answer = game.condition_holds(controller, condition, entering)
        if answer is None:
            return False
        return answer != negated

    return holds_shared


def unread_self_enters_tapped_lines(card_state: CardState) -> list[str]:
    """The entering object's own "enters tapped" lines (CR 614.1d) that
    `_self_enters_modifiers` skips because it cannot read them.

    Two shapes are skipped there, and both are named here from the same parse:
    a condition none of `_read_enters_condition`'s readers claims (a count
    of a noun it cannot check), and an "If you don't" whose
    optional half is not a payment `_optional_enters_payment` reads. Only the
    face that is up is read, the same CR 712.8 filter `_self_enters_modifiers`
    applies. `hypothetical.predict_enters` reports a land with any of these
    tapped, with a notice, rather than repeating the engine's silent untapped
    guess.
    """
    up_face_name = card_state.up_face_name
    pending_payments = 0
    unread: list[str] = []
    for effect in parse_replacement_effects(card_state.card):
        if up_face_name is not None and effect.face not in (None, up_face_name):
            continue
        if not effect.self_replacement:
            continue
        if (
            effect.kind is ReplacementKind.AS_ENTERS
            and effect.optional
            and _optional_enters_payment(effect, card_state.card.name) is not None
        ):
            pending_payments += 1
            continue
        if effect.kind is not ReplacementKind.ENTERS_TAPPED:
            continue
        condition = (effect.condition or "").strip()
        if not condition:
            continue
        if _IF_YOU_DONT.match(condition) or REVEALED_OR_CONTROL_RE.match(condition.rstrip(".")):
            if pending_payments:
                pending_payments -= 1
            else:
                unread.append(effect.text)
            continue
        if _enters_tapped_condition(effect) is None:
            unread.append(effect.text)
    return unread


def _read_enters_condition(condition: str) -> EntersCondition | None:
    match = _YOU_CONTROL_CARD_TYPE_RE.match(condition)
    if match is not None:
        card_type = _CARD_TYPE_WORDS.get(match.group("type").lower())
        return _controls_a_card_type(card_type) if card_type is not None else None

    match = _YOU_CONTROL_SUBTYPES_RE.match(condition)
    if match is not None:
        subtypes = frozenset(_A_SUBTYPE_RE.findall(match.group(1)))
        return _controls_a_subtype(subtypes) if subtypes else None

    match = _YOU_CONTROL_OTHER_LANDS_RE.match(condition)
    if match is not None:
        count = parse_count(match.group("count"))
        if count is None:
            return None
        return _controls_other_lands(
            count,
            at_least=match.group("direction").lower() == "more",
            basic=match.group("basic") is not None,
            subtype_plural=match.group("subtype"),
        )

    if _YOU_CONTROL_A_BASIC_LAND_RE.match(condition) is not None:
        return _controls_a_basic_land()

    if _NOT_YOUR_TURN_RE.match(condition) is not None:
        return _not_your_turn

    if _YOUR_TURN_RE.match(condition) is not None:
        return _is_your_turn

    match = _YOUR_TURN_ORDINAL_RE.match(condition)
    if match is not None:
        words = re.findall(rf"{_ORDINAL_WORD_RE}", match.group("ordinals"), re.IGNORECASE)
        if not words:
            return None
        return _your_turn_ordinal_or_earlier(max(_ORDINAL_WORDS[word.lower()] for word in words))

    match = _A_PLAYER_HAS_LIFE_RE.match(condition)
    if match is not None:
        return _a_player_has_life(
            int(match.group("count")), at_most=match.group("direction").lower() == "less"
        )

    match = _X_IS_RE.match(condition)
    if match is not None:
        return _x_is(int(match.group("count")), at_most=match.group("direction").lower() == "less")

    if condition.strip().lower() == "a creature died this turn":
        return _a_creature_died_this_turn

    if condition.strip().lower() in _revolt_clauses():
        return _revolt_active

    if condition.strip().lower() == ESCAPED_CONDITION:
        return _escaped

    if condition.strip().lower() == NOT_ESCAPED_CONDITION:
        return lambda game, entering: not _escaped(game, entering)

    return read_extra_enters_condition(condition)


def _revolt_clauses() -> frozenset[str]:
    """CR 207.2c's Revolt/Disappear condition text, both printed phrasings -
    imported lazily from `machines/triggers.py` (which has no reverse import
    of this module, so this would be safe at module scope too, but every
    other cross-`machines/` reuse in this file is already lazy this way)
    rather than duplicated as a second literal pair here."""
    from ..triggers import _REVOLT_CLAUSES

    return _REVOLT_CLAUSES


def _revolt_active(game: "Game", entering: CardState) -> bool:
    """Putrid Pals' own Disappear (CR 207.2c, the ability word already
    stripped): "This creature enters with two +1/+1 counters on it if a
    permanent left the battlefield under your control this turn." Read off
    the identical `Game.revolt_active_for` running count Renegade Rallier's
    and Fatal Push's own *triggered*-ability intervening-if already reads for
    the same fact (`machines/triggers.py`'s own `_REVOLT_CLAUSES` branch) -
    the fact is shared, the reading site is not, the same division
    `_a_creature_died_this_turn` just above already states for its own
    Morbid counterpart.

    `entering`'s own controller: CR 614.12's replacement is judged as the
    permanent enters, whose eventual controller `Game.enter_the_battlefield`
    has already fixed by the time this runs (`entering.controller`), the
    identical read `_controls_a_card_type`/`_controls_a_subtype` above give
    every other "you control ..." enters-with condition in this module.
    """
    controller = entering.controller
    return controller is not None and game.revolt_active_for(controller)


#: "As [this] enters, choose a color/card name/creature type." (CR 614.1c).
#: Three fixed phrases, not a general "choose ..." reader - Kenrith's
#: Transformation's "choose a creature type" (naming an existing permanent's
#: new type, not a card carrying its own choice) is a *targeted* clause of a
#: different shape entirely and is never routed through here.
_CHOOSE_A_COLOR_RE = re.compile(r"^choose a color\.?$", re.IGNORECASE)
#: "choose a noncreature, nonland card name" (Council of the Absolute) - the
#: comma-joined form of the two-word quality `_CHOOSE_A_CARD_NAME_RE` reads.
_COMMA_QUALITY_RE = re.compile(r", non", re.IGNORECASE)
#: "choose two colors" (Tablet of the Guilds) - the same CR 614.12a choice made
#: that many times, each a color not already chosen.
_CHOOSE_N_COLORS_RE = re.compile(rf"^choose (?P<count>{COUNT}) colors\.?$", re.IGNORECASE)
#: "choose a card name" (Pithing Needle), and CR 201.4a's "choose a card name
#: with certain characteristics" - "choose a nonland card name" (Phyrexian
#: Revoker, Voidstone Gargoyle), "choose a nonbasic land card name" (Alpine
#: Moon): one or two supertype/card-type words, each optionally "non"-prefixed,
#: ahead of "card name". They are kept (`card_name_quality`) so the answer can
#: be checked against them.
_CHOOSE_A_CARD_NAME_RE = re.compile(
    r"^choose an? (?:(?P<quality>(?:non-?)?[a-z]+(?: (?:non-?)?[a-z]+)?) )?card name\.?$",
    re.IGNORECASE,
)

_CHOOSE_A_CREATURE_TYPE_RE = re.compile(r"^choose a creature type\.?$", re.IGNORECASE)
#: "choose odd or even" (Gollum, Riddle Master) - a fourth CR 614.12a choice
#: shape, verified against the pool printing.
_CHOOSE_ODD_OR_EVEN_RE = re.compile(r"^choose odd or even\.?$", re.IGNORECASE)
#: Multiversal Passage's own "As this land enters, choose a basic land
#: type." - a fifth CR 614.12a choice shape, CR 305.6's five names the only
#: legal answers (`_quality_options` below), read back by "This land is the
#: chosen type." (`machines/layers.py`'s own `chosen_basic_land_type_of`).
_CHOOSE_A_BASIC_LAND_TYPE_RE = re.compile(r"^choose a basic land type\.?$", re.IGNORECASE)

#: The five colors' letter codes (CR 105.1), the closed universe
#: `Game.ask` checks a color choice against. Card names and creature types
#: have no such closed universe here, so their `Decision.options` stays empty.
_COLOR_OPTIONS = tuple(
    color.value for color in (Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN)
)


def _classify_choice(replacement_text: str) -> ChoiceKind | None:
    """Which of the five "as [this] enters, choose ..." shapes this is, if any."""
    text = _COMMA_QUALITY_RE.sub(" non", replacement_text.strip())
    if _CHOOSE_A_COLOR_RE.match(text):
        return ChoiceKind.COLOR
    if _CHOOSE_A_CARD_NAME_RE.match(text):
        return ChoiceKind.CARD_NAME
    if _CHOOSE_A_CREATURE_TYPE_RE.match(text) or matches_restricted_creature_type_choice(text):
        return ChoiceKind.CREATURE_TYPE
    if _CHOOSE_ODD_OR_EVEN_RE.match(text):
        return ChoiceKind.ODD_OR_EVEN
    if _CHOOSE_A_BASIC_LAND_TYPE_RE.match(text):
        return ChoiceKind.BASIC_LAND_TYPE
    return None


#: A card's own line reads back the choice ("the chosen color/card name/
#: creature type") outside of the "As [this] enters, choose ..." sentence
#: that asked for it. `_UNWIRED_HINT_RE` tells such a line apart from the one
#: shape this wave *does* perform - "adds an additional ..." - by exclusion:
#: any other sentence naming the anaphora is an attempted consumer this wave
#: does not build, and gets a notice instead of silence.
#: "the chosen color/card name/creature type" and the shorter forms the same
#: cards' own *other* lines use for the same antecedent - Pithing Needle and
#: Disruptor Flute say "the chosen name" once they have already said "choose a
#: card name", and Cavern of Souls says "the chosen type" having already said
#: "choose a creature type". Same referent, shorter noun phrase the second
#: time it is used - ordinary English anaphora, not a fourth kind of choice.
_CHOSEN_QUALITY_ANAPHORA_RE = re.compile(
    r"\bthe chosen (?:color|card name|name|creature type|type)\b", re.IGNORECASE
)
_WIRED_MANA_CLAUSE_HINT_RE = re.compile(r"adds? an additional\b", re.IGNORECASE)
#: The second shape this engine now performs end to end: Disruptor Flute's
#: "Spells with the chosen name cost {3} more to cast.", read by
#: `machines/cost.cost_modifier_effect` as `CostModifierKind.NAMED_INCREASE`
#: and applied against `CardState.choice` in `Game.static_cost_modifiers_for`.
#: Excluded here so a wired consumer stops being reported as an unwired one.
_WIRED_NAMED_COST_INCREASE_HINT_RE = re.compile(
    r"spells with the chosen name cost \{\d+\} more to cast", re.IGNORECASE
)
#: "This creature has/gets/gains ..." (Voice of All) - the shape
#: `machines/layers.py`'s `_LOOKS_LIKE_LAYER_EFFECT_RE` already catches on its
#: own, recording a `LayerNotice` with no help from here. Excluded so a
#: permanent-targeted grant does not get *two* notices for the same gap, one
#: on each of two separate lists.
_LAYER_HANDLED_SUBJECT_RE = re.compile(
    r"^(?:this \w+|target creature|another target creature(?: you control)?)\s+"
    r"(?:has|have|gets?|gains?)\b",
    re.IGNORECASE,
)
#: The third shape this engine performs end to end: "{T}: Add [N] mana of
#: the chosen color." (Room of Refuge, Sunken Citadel), CR 614.12a's choice
#: bound straight into the mana ability itself rather than into a triggered
#: "adds an additional" rider - `machines/abilities.ManaAbility.uses_chosen_
#: color`, read against `CardState.choice` by both `Game.activate_ability`'s
#: own CR 605.3b fast path and `machines/cost.py`'s auto-tap solver
#: (`_mana_narrowings`), so a colour other than the chosen one is refused
#: and the chosen one is the only one ever produced. Excluded here so a
#: wired consumer stops being reported as an unwired one; "mana of the
#: chosen color" alone (no leading "add") is left unexcluded, since nothing
#: in the pool prints the anaphora that way without the mana verb in front
#: of it.
#: The fourth: "Activated abilities of sources with the chosen name can't be
#: activated [unless they're mana abilities]." (Pithing Needle, Disruptor
#: Flute, Phyrexian Revoker), read by `Game.activation_prohibition` against
#: `CardState.choice` on every activation, in every zone (CR 602.5, CR
#: 109.2c).
_WIRED_CHOSEN_NAME_PROHIBITION_HINT_RE = re.compile(
    r"^activated abilities of sources with the chosen name can't be activated\b",
    re.IGNORECASE,
)
_WIRED_CHOSEN_COLOR_MANA_HINT_RE = re.compile(
    r"\badds? (?:[a-z]+|\d+) mana of the chosen color\b", re.IGNORECASE
)


#: "Lands your opponents control with the chosen name lose all land types and
#: abilities, and they gain ..." (Alpine Moon) - read by `machines/layers.py`
#: against `CardState.choice`. Excluded so a wired consumer is not reported as
#: an unwired one.
_WIRED_CHOSEN_NAME_LAYER_HINT_RE = re.compile(
    r"^(?:lands|creatures|permanents)(?: your opponents control| you control)? "
    r"with the chosen name lose all\b",
    re.IGNORECASE,
)


def _unwired_choice_notices(card: Card, source_id: UUID) -> list[UnwiredChoiceNotice]:
    """Every sentence of `card`'s own text that reads back a CR 614.12a
    choice this wave does not perform - see `UnwiredChoiceNotice`.

    Read off the whole printed text rather than one line, since a card's
    reference to its own choice is never on the same line as the "As [this]
    enters, choose ..." sentence that asked for it.
    """
    found: list[UnwiredChoiceNotice] = []
    for line in (card.oracle_text or "").splitlines():
        sentence = line.strip()
        if not sentence or not _CHOSEN_QUALITY_ANAPHORA_RE.search(sentence):
            continue
        if (
            sentence.lower().startswith("as ")
            or _WIRED_MANA_CLAUSE_HINT_RE.search(sentence)
            or _WIRED_NAMED_COST_INCREASE_HINT_RE.search(sentence)
            or _WIRED_CHOSEN_COLOR_MANA_HINT_RE.search(sentence)
            or _WIRED_CHOSEN_NAME_PROHIBITION_HINT_RE.match(sentence)
            or _LAYER_HANDLED_SUBJECT_RE.match(sentence)
            or _WIRED_CHOSEN_NAME_LAYER_HINT_RE.match(sentence)
        ):
            continue
        found.append(UnwiredChoiceNotice(source_id=source_id, source_name=card.name, text=sentence))
    return found


def _quality_options(kind: ChoiceKind) -> tuple[str, ...]:
    """Every legal answer to CR 614.12a's choice, where the rules enumerate them.

    A color is one of CR 105.1's five. A creature type is one of CR 205.3m's
    list, read from the rules text (`data/creature_types.py`) - a land type
    such as "Island" is not one, and neither is an empty string. "Odd or
    even" (Gollum, Riddle Master) is exactly those two words. A basic land
    type is one of CR 305.6's five. A card name has no list to offer, so it
    stays open.
    """
    if kind is ChoiceKind.COLOR:
        return _COLOR_OPTIONS
    if kind is ChoiceKind.CREATURE_TYPE:
        return creature_types()
    if kind is ChoiceKind.ODD_OR_EVEN:
        return ("odd", "even")
    if kind is ChoiceKind.BASIC_LAND_TYPE:
        from ..layers import BASIC_LAND_TYPES

        return tuple(BASIC_LAND_TYPES)
    return ()


def card_name_quality(replacement_text: str) -> str | None:
    """The characteristics a "choose a <quality> card name" choice carries
    (CR 201.4a) - "nonland" for Phyrexian Revoker, "nonbasic land" for Alpine
    Moon - or None for a plain "choose a card name" or anything else."""
    match = _CHOOSE_A_CARD_NAME_RE.match(_COMMA_QUALITY_RE.sub(" non", replacement_text.strip()))
    if match is None or match.group("quality") is None:
        return None
    return match.group("quality").lower()


def _card_name_quality_refusal(value: str, quality: str) -> str | None:
    """Why `value` is not a legal answer to "choose a `quality` card name"
    (CR 201.4a: "the player must choose the name of a card whose Oracle text
    matches those characteristics"), or None.

    Each word of `quality` is a card type or supertype, optionally
    "non"-prefixed, and all of them must hold. Judged against the engine's own
    Scryfall printings (`data.printing_pool.resolve_printing`); a name the
    pool does not hold, or a word that is neither a type nor a supertype,
    cannot be judged here and is accepted rather than refused on a guess. A
    split card is judged by the half named (CR 201.4b), which `resolve_
    printing`'s own face lookup already gives.
    """
    from ...data.printing_pool import resolve_printing

    printing = resolve_printing(value)
    if printing is None:
        return None
    types = set(printing.types)
    for face in printing.card_faces or ():
        if face.name == value and face.type_line:
            types = set(types_of(face.type_line))
    supertypes = set(printing.supertypes)
    for word in quality.split():
        negated = word.startswith("non")
        bare = word.removeprefix("non").lstrip("-") if negated else word
        try:
            has = Type(bare) in types
        except ValueError:
            try:
                has = Supertype(bare) in supertypes
            except ValueError:
                return None
        if has == negated:
            return f"{value!r} is not {with_indefinite_article(quality)} card name (CR 201.4a)"
    return None


def _choose_a_quality(
    kind: ChoiceKind,
    card_name: str,
    name_quality: str | None = None,
    *,
    restricted_options: tuple[str, ...] | None = None,
) -> Apply:
    """Ask CR 614.12a's choice and record it on the entering object itself.

    "If a replacement effect that modifies how a permanent enters the
    battlefield requires a choice, that choice is made before the permanent
    enters the battlefield" - so this runs inside `apply_replacements`,
    before `Game.enter_the_battlefield` ever puts the card on the
    battlefield, exactly like the shockland's pay-life-or-tapped choice
    above. Unlike that one, nothing about *this* choice changes the
    `ReplaceableEvent` itself (no tapped flag, no counters) - the whole
    effect is recording an answer for later clauses to read back
    ("the chosen color"), which is why the only side effect is setting
    `source.choice`.

    The player asked is the entering permanent's own controller, who is set
    on `card_state.controller` by `Game.enter_the_battlefield` just before
    replacements are applied - not necessarily the same player who cast it
    (an Aura enchanting an opponent's permanent still asks *its own*
    controller, CR 303.4e), and there is no controller at all to ask if this
    is reached some other way, in which case nothing is recorded rather than
    guessing.

    `restricted_options` narrows `_quality_options(kind)`'s own full CR
    205.3m list to a printed enumeration - Dawn-Blessed Pennant's and
    Eclipsed Realms's own "choose Elemental, Elf, Faerie, Giant, Goblin,
    Kithkin, Merfolk, or Treefolk" (`chosen_type.RESTRICTED_TRIBAL_TYPES`) -
    the same way `name_quality` already narrows a card-name choice
    (CR 201.4a); an answer outside it is refused exactly like an
    out-of-characteristic card name is.
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        who = source.controller if source is not None else None
        if who is None:
            return
        quality = kind.value.replace("_", " ")
        if name_quality is not None:
            quality = f"{name_quality} {quality}"
        # "odd or even" (Gollum, Riddle Master) is a plain either/or, not a
        # counted noun the other three kinds are - "choose an odd or even"
        # would be wrong grammar for it, so it skips `with_indefinite_
        # article`'s own noun-phrase reading.
        prompt = (
            f"choose {quality}"
            if kind is ChoiceKind.ODD_OR_EVEN
            else (f"choose {with_indefinite_article(quality)}")
        )
        options = restricted_options if restricted_options is not None else _quality_options(kind)
        decision = Decision(
            kind=DecisionKind.CHOOSE_A_QUALITY,
            player=who,
            prompt=prompt,
            source=card_name,
            source_id=source_id_of(source),
            options=options,
            quality=kind.value,
        )
        value = game.ask(decision)
        assert isinstance(value, str)
        if name_quality is not None:
            refusal = _card_name_quality_refusal(value, name_quality)
            if refusal is not None:
                raise ValueError(f"{card_name}: {refusal}")
        if restricted_options is not None and value.lower() not in {
            option.lower() for option in restricted_options
        }:
            raise ValueError(
                f"{card_name}: {value!r} is not one of {', '.join(restricted_options)}"
            )
        source.choice = Choice(kind=kind, value=value)
        game.unwired_choice_notices.extend(_unwired_choice_notices(source.card, source.id))

    return apply


#: "choose a player" (Stuffy Doll), "choose an opponent" (Nyxathid), and the
#: compound "choose an opponent and a card name other than a basic land card
#: name" (Booby Trap): CR 614.12a's choice of a player, recorded on
#: `CardState.chosen_player`, with an optional card name (CR 201.4a) after it
#: recorded on `CardState.choice` as `_choose_a_quality` would.
_CHOOSE_A_PLAYER_RE = re.compile(
    r"^choose (?P<who>a player|an opponent)"
    r"(?: and a card name(?P<other_than> other than a basic land card name)?)?\.?$",
    re.IGNORECASE,
)


def _basic_land_name_refusal(value: str) -> str | None:
    """Why `value` is not "a card name other than a basic land card name"
    (CR 201.4a: the name must be one whose card does not have the named
    characteristics), or None. A name the engine's pool does not hold cannot
    be judged and is accepted, as `_card_name_quality_refusal` does."""
    from ...data.printing_pool import resolve_printing

    printing = resolve_printing(value)
    if printing is None:
        return None
    if Type.LAND in printing.types and Supertype.BASIC in printing.supertypes:
        return f"{value!r} is a basic land card name (CR 201.4a)"
    return None


def _choose_counters(picks: int, kinds: tuple[str, ...], card_name: str) -> Apply:
    """ "enters with your choice of a flying counter or a first strike counter"
    - CR 614.12a's choice, asked before the permanent enters, one question per
    pick over the printed kinds not yet picked; each pick is one counter (CR
    614.1c, CR 122.6)."""

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        who = source.controller if source is not None else None
        if who is None or source is None:
            return
        remaining = list(kinds)
        for _ in range(picks):
            value = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_QUALITY,
                    player=who,
                    prompt="choose a kind of counter",
                    source=card_name,
                    source_id=source_id_of(source),
                    options=tuple(remaining),
                )
            )
            assert isinstance(value, str)
            remaining.remove(value)
            event.counters[value] = event.counters.get(value, 0) + 1

    return apply


def _choose_a_player(replacement_text: str, card_name: str) -> Apply | None:
    """`_CHOOSE_A_PLAYER_RE`'s choice, asked before the permanent enters (CR
    614.12a) of its own controller: any player in the game for "a player",
    any of the controller's opponents for "an opponent" - asked only when
    there is more than one to pick between, Tribute's own convention. A
    compound "and a card name" asks the name next and records both."""
    match = _CHOOSE_A_PLAYER_RE.match(replacement_text.strip())
    if match is None:
        return None
    any_player = match.group("who").lower() == "a player"
    wants_name = "card name" in match.group(0).lower()
    other_than_basic = match.group("other_than") is not None

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        who = source.controller if source is not None else None
        if source is None or who is None:
            return
        candidates = tuple(
            player.username
            for player in game.players_in_game
            if any_player or player.username != who
        )
        if not candidates:
            return
        chosen = candidates[0]
        if len(candidates) > 1:
            quality = "player" if any_player else "opponent"
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_QUALITY,
                    player=who,
                    prompt=f"choose {with_indefinite_article(quality)} as {card_name} enters",
                    source=card_name,
                    source_id=source_id_of(source),
                    options=candidates,
                    quality=quality,
                )
            )
            assert isinstance(answer, str)
            if answer not in candidates:
                raise ValueError(f"{card_name}: {answer!r} is not one of {', '.join(candidates)}")
            chosen = answer
        source.chosen_player = chosen
        if not wants_name:
            return
        value = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=who,
                prompt=(
                    "choose a card name other than a basic land card name"
                    if other_than_basic
                    else "choose a card name"
                ),
                source=card_name,
                source_id=source_id_of(source),
                options=(),
                quality=ChoiceKind.CARD_NAME.value,
            )
        )
        assert isinstance(value, str)
        if other_than_basic and (refusal := _basic_land_name_refusal(value)) is not None:
            raise ValueError(f"{card_name}: {refusal}")
        source.choice = Choice(kind=ChoiceKind.CARD_NAME, value=value)

    return apply


def _choose_colors(count: int, card_name: str) -> Apply:
    """ "As [this] enters, choose two colors" - CR 614.12a's choice asked
    `count` times, each answer one of CR 105.1's colors not already chosen,
    recorded as one `ChoiceKind.COLORS` answer."""

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        who = source.controller if source is not None else None
        if who is None or source is None:
            return
        chosen: list[str] = []
        for _ in range(count):
            options = tuple(letter for letter in _COLOR_OPTIONS if letter not in chosen)
            if not options:
                break
            value = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_QUALITY,
                    player=who,
                    prompt="choose a color",
                    source=card_name,
                    source_id=source_id_of(source),
                    options=options,
                    quality=ChoiceKind.COLOR.value,
                )
            )
            assert isinstance(value, str)
            chosen.append(value)
        source.choice = Choice(kind=ChoiceKind.COLORS, value="".join(chosen))
        game.unwired_choice_notices.extend(_unwired_choice_notices(source.card, source.id))

    return apply


# --------------------------------------------------------------------------
# "[This permanent] enters as a copy of ..." (CR 614.1c, 616.1c)
# --------------------------------------------------------------------------
#
# Clone: "You may have this creature enter as a copy of any creature on the
# battlefield." CR 614.1c makes "[This permanent] enters as . . ." a
# replacement effect, and CR 614.12 lets it come from the permanent itself,
# which is why this is gathered by `_self_enters_modifiers` off the entering
# card rather than compiled into `_COMPILERS`: the Clone is not on the
# battlefield when it applies, so no battlefield scan would ever find it.
#
# CR 616.1c gives it its own step ahead of the ordinary free choice: "If any of
# the replacement and/or prevention effects would cause an object to become a
# copy of another object as it enters the battlefield, one of them must be
# chosen." `ApplicableEffect.copy_as_it_enters` carries that, and
# `order_effects` sorts on it.
#
# CR 614.12a is the choice itself: "If a replacement effect that modifies how a
# permanent enters the battlefield requires a choice, that choice is made
# before the permanent enters the battlefield" - both the "you may" and which
# creature, asked from inside `apply_replacements`, which every route onto the
# battlefield runs before the card is put there.
#
# What is copied is CR 707.2's copiable values, and `machines/layers.py`
# already builds exactly that layer-1 effect for "this creature becomes a copy
# of target creature"; `_become_a_copy_builder` is reused rather than
# reimplemented, so the two shapes cannot drift apart.

#: "any creature on the battlefield" (Clone) / "any creature card in a
#: graveyard" (Superior Spider-Man) - the object the entering permanent may
#: copy, and the zone to look for it in. CR 707.2 is written about copying an
#: *object*, not specifically a permanent, and CR 400.1 lists the graveyard as
#: a zone like any other, so "card in a graveyard" needs no special rule -
#: only a second place to look. The noun is "card" there and "permanent" on
#: the battlefield, which is CR 108.2/108.2b's own distinction ("a Magic card ... A
#: token isn't a card"), so the wording is admitted per zone rather than
#: interchangeably.
#:
#: Widened (ecl T5) to Moritte of the Frost's "a permanent you control" - the
#: battlefield, narrowed to what the entering permanent's controller controls
#: (CR 109.5: "you" on an object is its controller).
_COPY_CANDIDATES_RE = re.compile(
    r"^(?:any|an?) (?:non(?P<excluded>artifact|creature|enchantment|land|planeswalker) )?"
    r"(?P<filter>artifact|creature|enchantment|land|permanent|planeswalker)"
    r"(?P<zone> on the battlefield| card in a graveyard| you control)"
    r"(?: with mana value (?P<bound>.+))?$",
    re.IGNORECASE,
)

#: The mana value bound a copy candidate may carry - Mockingbird's "less than
#: or equal to the amount of mana spent to cast this creature" (CR 202.3 is
#: the mana value, CR 601.2h the payment that spends the mana). No printing
#: carries a numeric bound on this clause, so none is read: it fails closed.
_COPY_MANA_VALUE_BOUND_RE = re.compile(
    r"^less than or equal to the amount of mana spent to cast this "
    r"(?:creature|permanent|artifact|enchantment|land)$",
    re.IGNORECASE,
)


def _mana_spent_to_cast(game: "Game", entering: CardState) -> int:
    """The total mana spent to cast the spell that became `entering`.

    CR 601.2h is where the total cost is paid, and `CastRecord.mana_spent` is
    that payment by color - every mana, not only what went to {X} (the
    Mockingbird ruling: "counts all mana spent to cast Mockingbird, not just
    mana spent on {X}. If there are any additional costs to cast it, the mana
    spent to pay those costs counts as well."). A permanent that was not cast
    - put onto the battlefield by an effect - has no record, and no mana was
    spent to cast it: 0.
    """
    record = game.cast_record_of(entering)
    if record is None:
        return 0
    return sum(record.mana_spent.values())


def enters_as_copy_outcome(effect: ReplacementEffect) -> str:
    """What `_enters_as_copy` does with this "enter as a copy" clause, asked of
    the clause alone - "handled", "notice" or "silent".

    `scripts/sweep_pool.py` reads a copy clause's truth here rather than
    re-deriving it, so the tool and the engine cannot drift:

    - "notice": the "except ..." tail did not read, and `_enters_as_copy`
      records an `UnreadableCopyExceptionNotice` and skips the copy.
    - "silent": the candidate phrase (`_COPY_CANDIDATES_RE`, with its mana
      value bound) does not read, so `_copy_candidates` returns `None` and the
      permanent enters as itself with nothing logged - or a linked "When you
      do" sentence (CR 603.12) is one `_create_linked_reflexive_trigger`
      cannot perform.
    - "handled": every part of the clause is performed.
    """
    if effect.copy_exception_unparsed is not None:
        return "notice"
    match = _COPY_CANDIDATES_RE.match((effect.copy_of or "").strip().rstrip("."))
    if match is None:
        return "silent"
    bound = match.group("bound")
    if bound is not None and _COPY_MANA_VALUE_BOUND_RE.match(bound.strip()) is None:
        return "silent"
    if effect.linked_trigger is not None:
        linked = _REFLEXIVE_OPENER.match(effect.linked_trigger)
        if linked is None or not _EXILE_THAT_CARD_RE.match(linked.group("effect").strip()):
            return "silent"
    return "handled"


def _copy_mana_value_bound(game: "Game", bound: str, entering: CardState) -> int | None:
    """The highest mana value a candidate may have, or `None` if unreadable."""
    if _COPY_MANA_VALUE_BOUND_RE.match(bound.strip()) is None:
        return None
    return _mana_spent_to_cast(game, entering)


def _copy_candidates(game: "Game", phrase: str, entering: CardState) -> list[CardState] | None:
    """The objects this card may enter as a copy of, or None if the phrase
    is one this cannot read - fail closed, as everywhere else in this module.

    Two zones are read: the battlefield (Clone) and every graveyard (Superior
    Spider-Man's "any creature card in a graveyard" - "a graveyard", not "your
    graveyard", so every player's is searched).

    The type filter is one card type, "permanent" for any, and an optional
    "non<type>" in front of it (Clever Impersonator's "any nonland permanent
    on the battlefield"). An optional mana value bound follows it
    (`_COPY_MANA_VALUE_BOUND_RE`): Mockingbird's "with mana value less than
    or equal to the amount of mana spent to cast this creature", read against
    each candidate's mana value as it is on the battlefield (CR 202.3 - a
    Clone copying a two-drop has the two-drop's mana value, CR 707.2).

    The entering object is excluded: it is not on the battlefield yet, so this
    is belt and braces against a caller that put it there first.
    """
    cleaned = phrase.strip().rstrip(".")
    match = _COPY_CANDIDATES_RE.match(cleaned)
    if match is None:
        return None
    word = match.group("filter").lower()
    wanted = None if word == "permanent" else _CARD_TYPE_WORDS.get(word)
    if wanted is None and word != "permanent":
        return None
    excluded = _CARD_TYPE_WORDS.get((match.group("excluded") or "").lower())
    bound: int | None = None
    if match.group("bound") is not None:
        bound = _copy_mana_value_bound(game, match.group("bound"), entering)
        if bound is None:
            return None

    def admitted(types: Iterable[Type], mana_value: float) -> bool:
        kinds = set(types)
        if wanted is not None and wanted not in kinds:
            return False
        if excluded is not None and excluded in kinds:
            return False
        return bound is None or mana_value <= bound

    if "graveyard" in match.group("zone").lower():
        # A graveyard card has no continuous effect reaching it (CR 613.5
        # applies to the battlefield), so its printed types are the only
        # answer there is.
        pool: list[CardState] = []
        for player in game.players_in_game:
            pool.extend(player.graveyard)
        return [
            candidate
            for candidate in pool
            if candidate.id != entering.id and admitted(candidate.types, candidate.mana_value)
        ]
    # The battlefield half: the *selection* of what may be copied reads the
    # computed board (CR 613.5) - a land earthbend (CR 701.66a) already made
    # a creature is a candidate for "any creature on the battlefield", even
    # though the values actually copied stay the copiable ones (CR 707.2,
    # unaffected by this - `_enters_as_copy` copies the chosen candidate's
    # copiable values, not its computed characteristics).
    board = game.computed_board()
    yours = "you control" in match.group("zone").lower()
    return [
        candidate
        for candidate in game.battlefield
        if candidate.id != entering.id
        and admitted(board.of(candidate).types, board.of(candidate).mana_value)
        and (not yours or board.of(candidate).controller == entering.controller)
    ]


#: "exile that card" - the one reflexive instruction this module performs.
#: "That card" is anaphoric to the object the copy was made from, which is why
#: the copied object is passed in rather than looked up again by name.
_EXILE_THAT_CARD_RE = re.compile(r"^exile that card\.?$", re.IGNORECASE)


def _create_linked_reflexive_trigger(
    game: "Game",
    effect: ReplacementEffect,
    card_name: str,
    entering: CardState,
    copied: CardState,
) -> None:
    """CR 603.12's reflexive ability, now that the action it reflects happened.

    "A resolving spell or ability may allow or instruct a player to take an
    action and create a triggered ability that triggers 'when [a player] [does
    or doesn't]' take that action ... These reflexive triggered abilities
    follow the rules for delayed triggered abilities (see rule 603.7), except
    that they're checked immediately after being created and trigger based on
    whether the trigger event or events occurred earlier during the resolution
    of the spell or ability that created them."

    Superior Spider-Man's is "When you do, exile that card." - created only on
    this path, which runs only when the copy choice was actually taken, so
    "occurred earlier" is true by construction. It goes on the stack as an
    ordinary trigger, which is what lets the episode's ordering question exist
    at all: with Bringer of the Last Gift's own enters trigger waiting
    alongside it, CR 603.3b lets their controller put them on the stack in
    either order.

    **CR 400.7 is why the callback re-reads the zone.** "An object that moves
    from one zone to another becomes a new object with no memory of, or
    relation to, its previous existence" - so a card that has left the
    graveyard by the time this resolves is not "that card" any more and
    nothing is exiled. That is the whole ruling DDR#986 turns on, and it falls
    out of asking rather than of a special case.

    An instruction this cannot read creates nothing rather than a trigger that
    does something else - the module's fail-closed rule.
    """
    linked = effect.linked_trigger
    if linked is None or entering.controller is None:
        return
    match = _REFLEXIVE_OPENER.match(linked)
    if match is None or not _EXILE_THAT_CARD_RE.match(match.group("effect").strip()):
        return
    game.create_reflexive_trigger(
        text=linked,
        controller=entering.controller,
        source_id=entering.id,
        source_name=card_name,
        callback=ReflexiveExileCopiedCard(card_id=copied.id, zone_when_copied=copied.zone),
    )


def _enters_as_copy(effect: ReplacementEffect, card_name: str) -> Apply:
    """CR 614.1c's "enters as a copy of", as a thing to do before it enters.

    Nothing about the `ReplaceableEvent` changes - no tapped flag, no counters
    - exactly like `_choose_a_quality` above: what the effect does is register
    the layer-1 copy effect (CR 613.1a, CR 707.2) that decides what the
    permanent's characteristics will be once it is there. `CardState.power`
    already reads the computed characteristics first, so the copy is visible
    the moment the permanent is on the battlefield.

    A board with no legal candidate is not an error: CR 707.2 has nothing to
    copy, so the permanent simply enters as itself. An unreadable "except ..."
    tail is different - see `UnreadableCopyExceptionNotice` - and is checked
    first, ahead of even looking for candidates, because it is a defect in
    what this card's text says, not a fact about the board.
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        # Imported here rather than at module scope: `machines/layers.py` is a
        # sibling this module is imported by, the same reason `keywords` and
        # `casting` are imported inside `_stack_replacements`.
        from ..layers import (
            BecomeACopy,
            LayerContext,
            _become_a_copy_builder,
            copiable_characteristics,
            printed_characteristics,
        )

        entering = event.card
        if entering is None or entering.controller is None:
            return
        if effect.copy_exception_unparsed is not None:
            game.unreadable_copy_exception_notices.append(
                UnreadableCopyExceptionNotice(
                    source_id=entering.id,
                    source_name=card_name,
                    text=effect.copy_exception_unparsed,
                )
            )
            return
        candidates = _copy_candidates(game, effect.copy_of or "", entering)
        if not candidates:
            # CR 707.2 has nothing to copy: the permanent enters as itself,
            # and untapped - the printed "tapped" belongs to the copy choice
            # (Echoing Deeps ruling 2023-11-10: "If you choose to have Echoing
            # Deeps not copy anything, it enters the battlefield untapped.").
            return
        if effect.optional and not game.may(
            entering.controller,
            f"have {card_name} enter as a copy of {effect.copy_of}",
            source=card_name,
            source_id=source_id_of(source),
        ):
            # CR 614.12a's choice, declined. The permanent enters as itself.
            return
        chosen_id = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=entering.controller,
                prompt=f"choose {effect.copy_of} for {card_name} to enter as a copy of",
                source=card_name,
                source_id=source_id_of(source),
                amount=1,
                cards=tuple(candidate.id for candidate in candidates),
            )
        )
        by_id = {candidate.id: candidate for candidate in candidates}
        chosen = [by_id[card_id] for card_id in chosen_id if card_id in by_id]  # type: ignore[union-attr]
        if not chosen:
            return
        exception = effect.copy_exception or CopyException()
        # CR 707.2: "as modified by other copy effects" - a battlefield
        # candidate that is itself a copy is copied as what it copies. A
        # graveyard card has no copy effect on it (CR 613.5 is about the
        # battlefield), so its printed values are its copiable ones.
        copiable = (
            copiable_characteristics(chosen[0], game.continuous_effects.active(game))
            if chosen[0].zone is Zone.BATTLEFIELD
            else None
        )
        # CR 707.9f: a gated exception ("if it's a creature, ...") applies
        # only when the copy would have that type without it - every other
        # exception taken into account.
        copied_types = set(
            (copiable if copiable is not None else printed_characteristics(chosen[0])).types
        ) | set(exception.added_types)
        gate_holds = exception.if_type is None or exception.if_type in copied_types
        added_abilities = exception.added_abilities + (
            exception.if_type_abilities if gate_holds else ()
        )
        if gate_holds:
            # CR 707.9e: "it enters with ... additional counters" is an
            # additional effect of the replacement, not a copiable value.
            for kind, amount in exception.enters_with_counters:
                event.counters[kind] = event.counters.get(kind, 0) + amount
        # CR 306.5b / CR 714.3a / CR 310.4b: a planeswalker's loyalty, a
        # Saga's lore counter and a battle's defense are intrinsic "enters
        # with" abilities of what is copied, read off its copiable values
        # (CR 707.2) - never the copier's own printing, which
        # `Game.enter_the_battlefield` leaves unread for a copy.
        values = copiable if copiable is not None else printed_characteristics(chosen[0])
        copied_subtypes = set(values.subtypes) | set(exception.added_subtypes)
        for kind, amount in (
            (Counter.LOYALTY, values.loyalty if Type.PLANESWALKER in copied_types else None),
            (Counter.LORE, 1 if "Saga" in copied_subtypes else None),
            (Counter.DEFENSE, values.defense if Type.BATTLE in copied_types else None),
        ):
            if amount:
                event.counters[kind] = event.counters.get(kind, 0) + amount
        built_effects = _become_a_copy_builder(
            until_eot=False,
            name_override=exception.name,
            power_override=exception.power,
            toughness_override=exception.toughness,
            added_types=exception.added_types,
            added_subtypes=exception.added_subtypes,
            added_abilities=added_abilities,
            added_supertypes=exception.added_supertypes,
            added_colors=exception.added_colors,
            copiable_values=copiable,
        )(entering, game.continuous_effects.tick(), chosen, LayerContext())
        for built in built_effects:
            game.continuous_effects.add(built)
            if isinstance(built.modification, BecomeACopy):
                event.entering_as_copy = (built.modification.name, built.modification.abilities)
        if effect.tapped:
            # CR 614.1c: "enter tapped as a copy of" - one replacement, so the
            # permanent is tapped exactly when the copy choice was taken.
            event.tapped = True

        _create_linked_reflexive_trigger(game, effect, card_name, entering, chosen[0])

    return apply


#: "where X is the number of turns you've begun since it was foretold" -
#: Lupine Harbingers' own count, printed on the card in
#: `tests/fixtures/cards/` (`resolve_cards` has no entry for this printing, so
#: the fixture's real Scryfall text is the source read here). Matched on the
#: sentence rather than stored at parse time because `_ENTERS_WITH`'s "where
#: ..." tail is deliberately not routed into `amount_expression`: that field
#: feeds `_ENTERS_WITH_AMOUNT_RESOLVERS`, and its presence is what tells
#: CR 107.3m's announced X apart from an expression, which this is not either.
_TURNS_SINCE_FORETOLD_RE = re.compile(
    r"number of turns you'?ve begun since it was foretold", re.IGNORECASE
)


def _turns_begun_since_foretold(game: "Game", entering: CardState) -> int | None:
    """ "The number of turns you've begun since it was foretold", or `None`.

    CR 702.143a: "Foretell is a keyword that functions while the card with
    foretell is in a player's hand. Any time a player has priority during their
    turn, that player may pay {2} and exile a card with foretell from their
    hand face down." The turn that happened on is the only thing the count
    needs, and `ExileAnnotation.turn_exiled` is where the foretell pile records
    it - read here off `CastRecord.exile_annotation`, because CR 400.7 makes
    the spell a new object and `CardState.move_to` drops the annotation on the
    way to the stack.

    **The reading taken, and why.** The card says turns *you have begun*, not
    turns that have passed, so the count has to be per-player. This engine has
    two candidates and neither is that exactly:

    - `TurnMachine.turns_taken` counts every turn any player begins, so in a
      two-player game it would double the answer - bob's turns are not ones
      alice began.
    - `TurnMachine.turn_number` counts rounds of the table. Every player takes
      exactly one turn per round (CR 500.1 gives the turn its five phases;
      turn order is seating order), so the number of rounds elapsed *is* the
      number of turns the foretelling player has begun since.

    `turn_number` is therefore the right one, and the docstring on
    `TurnMachine.turns_taken` names the single case where it is not: an extra
    turn (CR 500.7) deliberately does not move `turn_number`, so a player given
    one would be counted a turn short. Recorded rather than guessed at - no
    card in the pool combines foretell with an extra turn, and inventing a
    per-player counter to cover it belongs to `machines/turn.py`, not here.

    `None` when there is nothing to count from: no cast record (the permanent
    arrived some other way), no exile annotation, or an annotation from a pile
    that is not foretell's. Fail closed, like every other unreadable count in
    this module - the effect is skipped and the permanent enters with no
    counters rather than with a guessed number.
    """
    record = game.cast_record_of(entering)
    if record is None or record.exile_annotation is None or game.turn is None:
        return None
    annotation = record.exile_annotation
    if annotation.marker is not ExileMarker.FORETOLD or annotation.turn_exiled is None:
        return None
    # Never negative: a stamp from the future is not a state this can reach,
    # and CR 122.1 has no notion of putting a negative number of counters on.
    return max(0, game.turn.turn_number - annotation.turn_exiled)


def _self_enters_modifiers(
    game: "Game",
    card_state: CardState,
    entering_as_copy: tuple[str, tuple[str, ...]] | None = None,
    *,
    turned_up: bool = False,
    entering_transformed: bool = False,
) -> list[tuple[str, Apply, str, bool]]:
    """The card's own "enters ..." replacement effects, as things to apply.

    `entering_as_copy` is `ReplaceableEvent.entering_as_copy`: once an "enter
    as a copy" replacement has applied, CR 614.12 reads "the characteristics
    of the permanent as it would exist on the battlefield, taking into account
    replacement effects that have already modified how it enters" - the
    copied object's own "enters with"/"as ... enters"/"enters tapped" lines,
    under `copy:` keys, and no longer the printed card's (Mockingbird ruling
    2024-07-26: "Any 'as [this creature] enters' or '[this creature] enters
    with' abilities of the copied creature will also work"). A second "enter
    as a copy" among the copied lines is not offered again: CR 616.1c has
    already had its one copy effect chosen for this event.

    CR 614.12: "Some replacement effects modify how a permanent enters the
    battlefield. Such effects may come from the permanent itself if they affect
    only that permanent." That is why these are read off the entering card while
    it is not yet on the battlefield, unlike every other entry in `REPLACEMENTS`.

    Four shapes are performed:

    - "[This] enters tapped" (CR 614.1d) and "[this] enters with N counters"
      (CR 614.1c), unconditional.
    - "[This] enters tapped unless you control a Mountain" / "If you control
      two or more other lands, this land enters tapped" - the same shape with
      a condition about the *board*, read by `_enters_tapped_condition` and
      evaluated here. A condition no reader there claims is skipped.
    - "As this land enters, you may pay N life. If you don't, it enters tapped"
      - one choice spread over two printed sentences, which the parser reads as
      an optional `AS_ENTERS` followed by an `ENTERS_TAPPED` whose condition is
      the back-reference "you don't". Joined back together here, because they
      are not two effects: CR 614.12a's choice is singular.
    - "As [this] enters, choose a color/card name/creature type" - CR 614.12a's
      choice recorded on the entering object itself (`CardState.choice`) rather
      than changing the `ReplaceableEvent`, since nothing about *this* choice
      is a tapped flag or a counter count. See `_choose_a_quality`.

    "[This] enters with X `<kind>` counters" (Walking Ballista, Hangarback
    Walker, Chalice of the Void, Engineered Explosives) is CR 107.3m's own
    named case: "If an object's enters-the-battlefield ... replacement effect
    refers to X, and the spell that became that object as it resolved had a
    value of X chosen for any of its costs, the value of X for that ... effect
    is that same value." `game.cast_records` still holds that record here -
    `Game.resolve_top` calls `enter_the_battlefield` before it pops the record,
    the same ordering `Wrath of the Skies`'s own X read relies on. A
    `card_state.id` with **no** record at all (put onto the battlefield by
    something other than its own resolution - Green Sun's Zenith finding a
    Walking Ballista, say) leaves X undefined by 107.3m and is still skipped,
    the same as before this fix; a real cast with X=0 is not skipped and
    correctly places zero counters (CR 704.5f then kills a 0/0 the next state-
    based check, which is the right outcome, not a bug to paper over).
    """
    # CR 712.8d/712.8e/712.8f: a double-faced permanent has only the
    # characteristics of the face that's up, and CR 109.3 counts abilities -
    # replacement effects among them - as characteristics. Witch Enchanter
    # cast for its creature front, `up_face_name` names "Witch Enchanter";
    # the back face's "As this land enters, you may pay 3 life" is printed on
    # Witch-Blessed Meadow and is not read here, exactly as a triggered or
    # activated ability off the other face is not (see `triggers.py`'s
    # `triggers_for` and `Game.activated_abilities` for the same filter).
    # `up_face_name` is `None` for an ordinary single-faced card, which keeps
    # every one of its own lines (`effect.face` is also `None` there).
    if card_state.face_down and not turned_up:
        # CR 708.2: a face-down permanent has no text, so no "enters"/"as ...
        # enters" line of the card applies to it (CR 614.12).
        return []
    up_face_name = card_state.up_face_name
    # CR 712.14a / CR 614.12: a transformed arrival has its back face up as it
    # enters, so that face's "as ... enters" lines apply (its other enters
    # lines are placed by the post-move path, `intrinsic_entering_counters`).
    back_face_name = (
        card_state.card.back_face.name
        if entering_transformed and card_state.card.back_face is not None
        else None
    )
    key = "self"
    if entering_as_copy is None:
        parsed = [
            effect
            for effect in parse_replacement_effects(card_state.card)
            if (
                effect.face == back_face_name
                if back_face_name is not None
                and effect.kind is ReplacementKind.AS_ENTERS
                and effect.face is not None
                else up_face_name is None or effect.face in (None, up_face_name)
            )
        ]
        if turned_up:
            # CR 614.1e: only the "as this is turned face up" effects, which
            # perform exactly as their "as this enters" twins do.
            parsed = [
                effect.model_copy(update={"kind": ReplacementKind.AS_ENTERS})
                for effect in parsed
                if effect.kind is ReplacementKind.AS_TURNED_FACE_UP
            ]
        if card_state.granted_ability_texts:
            # CR 113.10a: a granted ability text "functions exactly as if it
            # were printed on the object" - Wildgrowth Archaic's own cast
            # trigger ("Whenever you cast a creature spell, that creature
            # enters with X additional +1/+1 counters on it, where X is the
            # number of colors of mana spent to cast it.") writes exactly
            # such a sentence onto the *entering* object's own
            # `CardState.granted_ability_texts` (see `machines/effects.
            # _parse_grant_enters_with_colors_spent_counters_clause`) rather
            # than the printed card, since the printed card carries no such
            # line at all. `CardState.move_to`'s own docstring is why this
            # is still there to read: stack-to-battlefield is the one zone
            # change that keeps `granted_ability_texts` rather than clearing
            # it (CR 400.7a/400.7b, the same exception `_carry_cast_record`
            # relies on). Only an `ENTERS_WITH` line is read out of it - any
            # other granted text (a spell's own "can't be countered", say)
            # simply does not match `_ENTERS_WITH` and is ignored here, the
            # same as any ordinary sentence this dispatcher was never asked
            # about. Read *after* the card's own printed lines so a
            # duplicate raw sentence (extremely unlikely, but CR 608.2c has
            # no notion of merging two identical replacement effects into
            # one) still becomes two independent `ENTERS_WITH` effects,
            # which CR 616.1c's own "apply them in any order" already knows
            # how to stack.
            parsed = [
                *parsed,
                *(
                    effect
                    for text in card_state.granted_ability_texts
                    for effect in _parse_oracle_text(
                        text, face=None, names=_names_of(card_state.card)
                    )
                    if effect.kind is ReplacementKind.ENTERS_WITH
                ),
            ]
    else:
        key = "copy"
        copied_name, copied_lines = entering_as_copy
        parsed = [
            effect
            for effect in _parse_oracle_text(
                "\n".join(copied_lines), face=None, names=_names_of_name(copied_name)
            )
            if effect.kind is not ReplacementKind.ENTERS_AS_COPY
        ]
    #: (key suffix, what to do, label, CR 616.1c copy-as-it-enters).
    performable: list[tuple[str, Apply, str, bool]] = []
    consumed: set[int] = set()

    for index, effect in enumerate(parsed):
        if index in consumed or not effect.self_replacement:
            continue

        choice = (
            _optional_enters_payment(effect, card_state.card.name)
            if effect.kind is ReplacementKind.AS_ENTERS and effect.optional
            else None
        )
        if choice is not None:
            follower = next(
                (
                    other
                    for other, candidate in enumerate(parsed)
                    if other > index
                    and candidate.kind is ReplacementKind.ENTERS_TAPPED
                    and (
                        _IF_YOU_DONT.match((candidate.condition or "").strip())
                        or reveal_follow_up_subtype(candidate) is not None
                    )
                ),
                None,
            )
            if follower is not None:
                consumed.add(follower)
                subtype = reveal_follow_up_subtype(parsed[follower])
                if subtype is not None:
                    choice = _or_you_control(choice, subtype)
                performable.append(
                    (
                        f"{key}:{index}",
                        choice,
                        f"{effect.text} {parsed[follower].text}",
                        False,
                    )
                )
                continue

        if effect.kind is ReplacementKind.ENTERS_AS_COPY and effect.condition is None:
            # CR 614.1c / 616.1c. `_enters_as_copy` refuses a `copy_of` phrase
            # it cannot read, so a card whose candidates this cannot work out
            # enters as itself rather than as a guess.
            performable.append(
                (
                    f"{key}:{index}",
                    _enters_as_copy(effect, card_state.card.name),
                    effect.text,
                    True,
                )
            )
            continue

        if effect.kind is ReplacementKind.AS_ENTERS and effect.condition is None:
            counted_action = as_enters_action(effect.replacement or "")
            follower = next(
                (
                    other
                    for other, candidate in enumerate(parsed)
                    if other > index
                    and candidate.kind is ReplacementKind.ENTERS_WITH
                    and candidate.counter_kind is not None
                ),
                None,
            )
            if counted_action is not None and follower is not None:
                consumed.add(follower)
                performable.append(
                    (
                        f"{key}:{index}",
                        _action_then_enter_with_counters(
                            counted_action, parsed[follower], card_state.card.name
                        ),
                        f"{effect.text} {parsed[follower].text}",
                        False,
                    )
                )
                continue
            sacrifice_choice = _sacrifice_any_number_choice(effect)
            if sacrifice_choice is not None:
                restriction_text, optional = sacrifice_choice
                from ..effects import _sacrifice_restriction

                restriction = _sacrifice_restriction(restriction_text)
                if restriction is not None:
                    follower = next(
                        (
                            other
                            for other, candidate in enumerate(parsed)
                            if other > index
                            and candidate.kind is ReplacementKind.ENTERS_WITH
                            and candidate.counter_kind is not None
                            and candidate.that_many_multiplier is not None
                            and (
                                (not optional and candidate.condition is None)
                                or (
                                    optional
                                    and _IF_YOU_DO.match((candidate.condition or "").strip())
                                )
                            )
                        ),
                        None,
                    )
                    if follower is not None:
                        consumed.add(follower)
                        performable.append(
                            (
                                f"{key}:{index}",
                                _sacrifice_any_number_then_enter_with_counters(
                                    restriction,
                                    parsed[follower].counter_kind,
                                    parsed[follower].that_many_multiplier,
                                    card_state.card.name,
                                    devour=_DEVOUR_LINE_RE.match(effect.raw or "") is not None,
                                ),
                                f"{effect.text} {parsed[follower].text}",
                                False,
                            )
                        )
                        continue

            colors_wanted = _CHOOSE_N_COLORS_RE.match((effect.replacement or "").strip())
            if colors_wanted is not None and parse_count(colors_wanted.group("count")):
                performable.append(
                    (
                        f"{key}:{index}",
                        _choose_colors(
                            parse_count(colors_wanted.group("count")) or 0, card_state.card.name
                        ),
                        effect.text,
                        False,
                    )
                )
                continue

            player_choice = _choose_a_player(effect.replacement or "", card_state.card.name)
            if player_choice is not None:
                performable.append((f"{key}:{index}", player_choice, effect.text, False))
                continue

            extra_choice = enters_choice_apply(effect, card_state.card.name)
            if extra_choice is not None:
                performable.append((f"{key}:{index}", extra_choice, effect.text, False))
                continue

            choice_kind = _classify_choice(effect.replacement or "")
            if choice_kind is not None:
                performable.append(
                    (
                        f"{key}:{index}",
                        _choose_a_quality(
                            choice_kind,
                            card_state.card.name,
                            card_name_quality(effect.replacement or "")
                            if choice_kind is ChoiceKind.CARD_NAME
                            else None,
                            restricted_options=(
                                RESTRICTED_TRIBAL_TYPES
                                if matches_restricted_creature_type_choice(effect.replacement or "")
                                else None
                            ),
                        ),
                        effect.text,
                        False,
                    )
                )
                continue

        if effect.condition is not None:
            # CR 614.1d's conditional wordings - "unless you control a
            # Mountain", "if you control two or more other lands". Read into a
            # predicate and *evaluated* here, at gathering time, so an effect
            # whose condition does not hold never reaches CR 616.1's list at
            # all rather than being applied to no effect. A condition no reader
            # claims returns `None` and the effect is skipped, unchanged.
            holds = (
                _enters_with_condition(effect)
                if effect.kind is ReplacementKind.ENTERS_WITH
                else _enters_tapped_condition(effect)
            )
            if holds is None or not holds(game, card_state):
                continue
        if effect.kind is ReplacementKind.ENTERS_WITH and effect.counter_kind is None:
            choice_of_counters = choice_counter_options(effect.replacement or "")
            if choice_of_counters is not None:
                performable.append(
                    (
                        f"{key}:{index}",
                        _choose_counters(*choice_of_counters, card_state.card.name),
                        effect.text,
                        False,
                    )
                )
                continue
        amount = effect.amount
        if (
            effect.kind is ReplacementKind.ENTERS_WITH
            and effect.counter_kind is not None
            and amount is None
            and effect.variable_amount
            and _TURNS_SINCE_FORETOLD_RE.search(effect.text or "")
        ):
            # Ahead of CR 107.3m's X below on purpose: this card's X is not the
            # announced one (its cost has no {X} at all, so the announcement
            # records 0), it is the count its own sentence names.
            amount = _turns_begun_since_foretold(game, card_state)
        if (
            effect.kind is ReplacementKind.ENTERS_WITH
            and effect.counter_kind is not None
            and amount is None
            and _TIMES_KICKED_RE.match(effect.amount_expression or "")
        ):
            # CR 702.33d / CR 122.6: "a +1/+1 counter on it for each time it
            # was kicked" - the kicks the cast record holds, 0 when none.
            amount = _kicked_count(game, card_state)
        if (
            effect.kind is ReplacementKind.ENTERS_WITH
            and effect.counter_kind is not None
            and amount is None
            and effect.variable_amount
            # CR 107.3m is "if an object's ... replacement effect **refers to
            # X**". A count stated as an expression instead - Ulamog, the
            # Defiler's "equal to the greatest mana value among cards in
            # exile" - refers to no X at all, and must not be answered with
            # the announcement's own X, which for a card with no {X} in its
            # cost is recorded as 0 rather than left unset.
            and effect.amount_expression is None
        ):
            # CR 107.3m: only a spell that actually resolved into this object
            # defines X here - `game.cast_records` is popped once resolution
            # finishes, so its presence here is exactly that fact, and an
            # entry with no record at all (this object arrived some other
            # way) leaves `amount` `None` and the effect skipped, unchanged
            # from before.
            record = game.cast_record_of(card_state)
            if record is not None:
                amount = record.x_value
        if (
            effect.kind is ReplacementKind.ENTERS_WITH
            and effect.counter_kind is not None
            and amount is None
            and effect.amount_expression is not None
        ):
            # "...equal to [expression]" - a count worked out against the game
            # as the permanent enters. An X inside it is CR 107.3m's X of the
            # spell that became this object; with no such spell it cannot be
            # determined and CR 107.2 uses 0. An expression nobody can read
            # leaves `amount` None, skips the counters, and says so.
            from ..effects import UnreadableCounterAmountNotice, amount_expression

            reader = (
                fixed_enters_count_reader(effect.amount_expression)
                or amount_expression(effect.amount_expression)
                or enters_count_reader(effect.amount_expression)
            )
            if reader is None:
                game.unreadable_counter_amount_notices.append(
                    UnreadableCounterAmountNotice(
                        source_id=card_state.id,
                        source_name=card_state.name,
                        text=effect.text,
                        expression=effect.amount_expression,
                    )
                )
            else:
                record = game.cast_record_of(card_state)
                x_value = record.x_value if record is not None else 0
                controller = card_state.controller or card_state.owner
                amount = reader(game, controller, card_state, x_value)
        readable_counters = (
            effect.kind is ReplacementKind.ENTERS_WITH
            and effect.counter_kind is not None
            and amount is not None
        )
        if (
            effect.kind in (ReplacementKind.ENTERS_TAPPED, ReplacementKind.ENTERS_PREPARED)
            or readable_counters
        ):
            performable.append(
                (f"{key}:{index}", _apply_self_enters(effect, amount), effect.text, False)
            )

    sunburst = _sunburst_modifier(game, card_state, up_face_name)
    if sunburst is not None:
        performable.append(sunburst)

    compleated = _compleated_modifier(game, card_state)
    if compleated is not None:
        performable.append(compleated)

    tribute = _tribute_modifier(game, card_state)
    if tribute is not None:
        performable.append(tribute)

    enters_under_opponent = _enters_under_opponents_control_modifier(game, card_state)
    if enters_under_opponent is not None:
        performable.append(enters_under_opponent)

    performable.extend(_riot_modifiers(game, card_state))
    performable.extend(_cast_permission_rider_modifiers(game, card_state))
    performable.extend(_extra_mana_counter_modifiers(game, card_state))

    return performable


def _cast_permission_rider_modifiers(
    game: "Game", card_state: CardState
) -> list[tuple[str, Apply, str, bool]]:
    """A cast permission's own "If you cast a spell this way, that creature
    enters with a finality counter on it." (Leonardo, Sewer Samurai; Noctis,
    Prince of Lucis; Mikey & Don, Party Planners' "an additional +1/+1
    counter") - CR 614.1c's "enters with", applying to the permanent the
    spell cast under that permission becomes. The permission recorded which
    counters as the spell was cast (`CastRecord.enters_with_counters`), and
    that record follows the spell onto the battlefield (CR 400.7d), so the
    counters are on the permanent as it enters, not added a moment later."""
    record = game.cast_record_of(card_state)
    if record is None or not record.enters_with_counters:
        return []
    found: list[tuple[str, Apply, str, bool]] = []
    for index, kind in enumerate(record.enters_with_counters):

        def apply(
            game: "Game", source: CardState | None, event: ReplaceableEvent, kind: str = kind
        ) -> None:
            event.counters[kind] = event.counters.get(kind, 0) + 1

        found.append(
            (
                f"cast-permission-rider:{index}",
                apply,
                f"enters with a {kind} counter because it was cast this way (CR 614.1c)",
                False,
            )
        )
    return found


def _extra_mana_counter_modifiers(
    game: "Game", card_state: CardState
) -> list[tuple[str, Apply, str, bool]]:
    """CR 614.1c: the creature a spell becomes enters with as many additional
    +1/+1 counters as the "any amount of mana" additional cost paid for it
    (`CastRecord.extra_mana_counters`; Chorus of the Conclave)."""
    record = game.cast_record_of(card_state)
    if record is None or not record.extra_mana_counters:
        return []
    amount = record.extra_mana_counters

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        event.counters[Counter.PLUS_ONE] = event.counters.get(Counter.PLUS_ONE, 0) + amount

    return [
        (
            "extra-mana-counters",
            apply,
            f"enters with {amount} additional +1/+1 counters for the mana paid (CR 614.1c)",
            False,
        )
    ]


def _riot_modifiers(game: "Game", card_state: CardState) -> list[tuple[str, Apply, str, bool]]:
    """Riot, read off the keyword rather than off a sentence - its expansion is
    reminder text (CR 207.2): CR 702.136a: "Riot is a static ability. 'Riot'
    means 'You may have this permanent enter with an additional +1/+1 counter
    on it. If you don't, it gains haste.''"

    A CR 614.1c "enters with .../enters ..." replacement on the entering
    permanent itself (CR 614.12), cast or not, with the choice made before it
    is on the battlefield (CR 614.12a) and asked of its controller (CR
    608.2d). Taking the counter places it the same way every other "enters
    with" amount here does, through `event.counters`. Declining instead sets
    `event.grants_haste`, which `Game.enter_the_battlefield` turns into an
    indefinite (CR 611.2a's default, since riot's own reminder text states no
    duration), `only_this_incarnation`-scoped (CR 400.7) haste grant once the
    permanent is actually on the battlefield - the same shape dash's
    `Game._grant_dash_haste` (CR 702.109a) and unearth's `_unearth_effect`
    (CR 702.84a) already grant their own haste with, so a blinked or
    otherwise re-entering permanent is a new object and is asked again rather
    than inheriting a haste grant made for the incarnation before it.

    CR 702.136b: "If a permanent has multiple instances of riot, each works
    separately" - one performable entry per instance, each asked on its own,
    the same way `_bloodthirst_entering_counters` keeps its own per-instance
    amounts apart.
    """
    from ...models.card_state import Counter
    from ..abilities import keyword_abilities

    instance_count = sum(
        1 for ability in keyword_abilities(card_state.card) if ability.canonical.lower() == "riot"
    )
    if not instance_count:
        return []

    found: list[tuple[str, Apply, str, bool]] = []
    for index in range(instance_count):

        def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
            if source is None:
                return
            controller = source.controller or source.owner
            if controller is None:
                return
            took_counter = game.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=controller,
                    prompt=(
                        f"have {source.name} enter with an additional +1/+1 counter "
                        "instead of gaining haste (riot, CR 702.136a)"
                    ),
                    source=source.name,
                    source_id=source_id_of(source),
                )
            )
            if took_counter:
                event.counters[str(Counter.PLUS_ONE)] = (
                    event.counters.get(str(Counter.PLUS_ONE), 0) + 1
                )
            else:
                event.grants_haste = True

        found.append((f"self:riot:{index}", apply, "Riot (CR 702.136a)", False))
    return found


def _tribute_modifier(game: "Game", card_state: CardState) -> tuple[str, Apply, str, bool] | None:
    """Tribute (CR 702.104a), read off the keyword and its N rather than off a
    sentence - its expansion is reminder text (CR 207.2): "Tribute N" means
    "As this creature enters, choose an opponent. That player may put an
    additional N +1/+1 counters on it as it enters."

    A replacement effect on the entering event (CR 614.1c), so both choices
    are made before the creature is on the battlefield (CR 614.12a): its
    controller chooses the opponent, and that opponent is asked. The counters
    are placed with the opponent as their putter (`counters_put_by`), which
    is how "if tribute wasn't paid" (CR 702.104b) tells them from any other
    +1/+1 counter. It works however the creature enters, cast or not."""
    from ..abilities import keyword_abilities

    count = next(
        (
            ability.count
            for ability in keyword_abilities(card_state.card)
            if ability.canonical.lower() == "tribute" and ability.count
        ),
        None,
    )
    if count is None:
        return None
    amount = count

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        controller = source.controller if source is not None else None
        if source is None or controller is None:
            return
        opponents = [
            player.username for player in game.players_in_game if player.username != controller
        ]
        if not opponents:
            return
        opponent = opponents[0]
        if len(opponents) > 1:
            opponent = str(
                game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_A_QUALITY,
                        player=controller,
                        prompt=f"choose an opponent for {source.name}'s tribute (CR 702.104a)",
                        source=source.name,
                        source_id=source_id_of(source),
                        options=tuple(opponents),
                        quality="opponent",
                    )
                )
            )
        paid = game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=opponent,
                prompt=(
                    f"put {amount} +1/+1 counter{'s' if amount != 1 else ''} on "
                    f"{source.name} as it enters (tribute, CR 702.104a)"
                ),
                source=source.name,
                source_id=source_id_of(source),
            )
        )
        if paid:
            event.counters_put_by.append((str(Counter.PLUS_ONE), opponent, amount))

    return ("self:tribute", apply, f"Tribute {amount} (CR 702.104a)", False)


#: "This enchantment enters under the control of an opponent of your
#: choice." (Captive Audience). `noun` is read but not constrained to
#: "enchantment" - CR 201.5's self-reference ("this `<noun>`") the same way
#: `_EXILE_SELF_AND_LIFE_TOTAL_BECOMES_RE` reads "exile this `<noun>`".
_SELF_ENTERS_UNDER_OPPONENTS_CONTROL_RE = re.compile(
    r"^this (?P<noun>[a-z]+) enters under the control of an opponent of your choice\.?$",
    re.IGNORECASE,
)


def _enters_under_opponents_control_modifier(
    game: "Game", card_state: CardState
) -> tuple[str, Apply, str, bool] | None:
    """Captive Audience's own shape, read off the printed sentence rather
    than through the generic `IF_WOULD_INSTEAD`/bare-`ENTERS_TAPPED` shapes:
    "enters under the control of `<X>`" names no event this module's parser
    already reads, so this is hand-read the same way tribute and sunburst
    are above.

    CR 616.1b would put a control-changing effect ahead of every other CR
    614.12 modifier if two ever competed for the same permanent; nothing in
    the pool pairs this with another one, so that forced tier is not wired
    in here (`applicable_effects`'s own `ApplicableEffect.controls_entry`
    stays `False` for this suffix), and the ordinary "one candidate needs no
    question" shortcut in `choose_effect` already covers the case that
    matters.
    """
    text = card_state.card.front_oracle_text or card_state.card.oracle_text or ""
    for line in text.split("\n"):
        if _SELF_ENTERS_UNDER_OPPONENTS_CONTROL_RE.fullmatch(strip_reminder_text(line)[0].strip()):
            break
    else:
        return None

    def apply(game: "Game", source: CardState | None, event: "ReplaceableEvent") -> None:
        controller = source.controller if source is not None else None
        if source is None or controller is None or event.card is None:
            return
        opponents = [
            player.username for player in game.players_in_game if player.username != controller
        ]
        if not opponents:
            return
        opponent = opponents[0]
        if len(opponents) > 1:
            opponent = str(
                game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_A_QUALITY,
                        player=controller,
                        prompt=(
                            f"choose an opponent for {source.name} to enter under the "
                            "control of (CR 614.12)"
                        ),
                        source=source.name,
                        source_id=source_id_of(source),
                        options=tuple(opponents),
                        quality="opponent",
                    )
                )
            )
        event.card.controller = opponent

    return (
        "self:enters_under_opponent",
        apply,
        "This enters under the control of an opponent of your choice.",
        False,
    )


def reads_self_enters_under_opponents_control_line(text: str) -> bool:
    """Whether `text` is Captive Audience's own "This `<noun>` enters under
    the control of an opponent of your choice." shape `_self_enters_
    modifiers`'s `_enters_under_opponents_control_modifier` performs -
    `support.py`'s credit for it.

    Read directly against the sentence, not through `parse_replacement_
    effects`: CR 614.1d's bare "enters" templates the generic parser does
    read are a closed list (`ENTERS_TAPPED`/`ENTERS_WITH`/`ENTERS_AS_COPY`/
    `AS_ENTERS`/`ENTERS_PREPARED`) that does not include "enters under the
    control of", and this sentence carries none of the cue words ("instead",
    "prevent", "skip", "rather than") the parser's other templates need
    either - so it comes back with no `ReplacementEffect` at all, not even
    `UNPARSED`, and needs its own credit the same way tribute's and
    sunburst's keyword-read shapes already have one.
    """
    line = strip_reminder_text(text)[0].strip()
    return _SELF_ENTERS_UNDER_OPPONENTS_CONTROL_RE.fullmatch(line) is not None


def self_enters_effects_read(card: Card, effects: Sequence[ReplacementEffect]) -> bool:
    """Whether `_self_enters_modifiers` performs every one of `effects` - a
    card's own "enters ..." lines - whenever the game state its own gates
    read allows it, rather than only on the empty board `support.py` stages.

    The same gates, asked of the text instead of a board: a condition must be
    one `_enters_tapped_condition` reads (evaluated as the permanent enters,
    CR 614.1d); "enters with" counters need a count - printed, CR 107.3m's X
    of the spell that became the object, the foretold count, or an
    `amount_expression` a reader claims; and CR 614.12a's "you may pay N
    life. If you don't, it enters tapped." pair needs its payment read. That
    is what lets a fastland, a Walking Ballista or an MDFC's back-face land
    be credited without a synthetic cast or a board where the condition
    happens to hold.
    """
    from ..effects import amount_expression

    if not effects:
        return False
    parsed = parse_replacement_effects(card)
    for effect in effects:
        if effect.kind is ReplacementKind.AS_ENTERS:
            if not (effect.optional and _optional_enters_payment(effect, card.name) is not None):
                return False
            continue
        if effect.condition is not None:
            if _IF_YOU_DONT.match(effect.condition.strip()) or REVEALED_OR_CONTROL_RE.match(
                effect.condition.strip().rstrip(".")
            ):
                paired = any(
                    other.kind is ReplacementKind.AS_ENTERS
                    and other.optional
                    and other.face == effect.face
                    and _optional_enters_payment(other, card.name) is not None
                    for other in parsed
                )
                if not paired or effect.kind is not ReplacementKind.ENTERS_TAPPED:
                    return False
                continue
            if _enters_tapped_condition(effect) is None:
                return False
        if effect.kind in (ReplacementKind.ENTERS_TAPPED, ReplacementKind.ENTERS_PREPARED):
            continue
        if effect.kind is not ReplacementKind.ENTERS_WITH or effect.counter_kind is None:
            return False
        if effect.amount is not None:
            continue
        if effect.amount_expression is not None:
            if _TIMES_KICKED_RE.match(effect.amount_expression):
                continue  # CR 702.33d: `_kicked_count`.
            if (
                amount_expression(effect.amount_expression) is None
                and enters_count_reader(effect.amount_expression) is None
            ):
                return False
            continue
        if not effect.variable_amount:
            return False
    return True


def _sunburst_counter_amount(game: "Game", entering: CardState) -> int | None:
    """CR 702.44b's own count: distinct colors of mana spent paying the total
    cost of the spell that is resolving into `entering` - `None` when this is
    not that (Sunburst adds nothing to an object that reaches the battlefield
    some other way, and CR 702.44b says so in as many words: "only if the
    object with sunburst is entering the battlefield from the stack as a
    resolving spell").

    `CastRecord.mana_spent` already carries exactly this (CR 601.2h,
    `machines/cost.ManaPayment.spend`), "including additional or alternative
    costs" per the same rule - it is filled once, at payment, from whatever
    was actually spent, with no notion of which symbol on the printed cost
    each mana went to. `Color.COLORLESS` is excluded: CR 105.1 lists five
    colors and colorless mana is explicitly "not a color" (CR 105.2c).
    """
    record = game.cast_record_of(entering)
    if record is None:
        return None
    return sum(
        1
        for color, amount in record.mana_spent.items()
        if color is not Color.COLORLESS and amount > 0
    )


def _sunburst_modifier(
    game: "Game", card_state: CardState, up_face_name: str | None
) -> tuple[str, Apply, str, bool] | None:
    """Sunburst (CR 702.44a), read off the keyword rather than off a parsed
    sentence - its own CR 702.44a expansion is reminder text (CR 207.2),
    never a rules-text sentence `_ENTERS_WITH` could match, so it is handled
    here directly rather than through `parse_replacement_effects`.

    No printing in the pool carries Sunburst on a multifaced card, so
    `up_face_name` is accepted only to keep this call symmetric with the
    parsed-sentence loop above rather than to filter anything yet - `Card.
    keywords` is Scryfall's own per-printing summary and is already scoped to
    whichever card this `CardState` actually is.

    "If this object is entering **as a creature**, ignoring any type-changing
    effects that would affect it" (CR 702.44a) reads `Card.types` - the
    printed type, before any layer effect - which is exactly what CR 613.1's
    "ignoring type-changing effects" means and is why this never asks
    `Game.characteristics_of` the way an ordinary battlefield query would.
    """
    del up_face_name
    keywords = {k.lower() for k in card_state.card.keywords}
    if "sunburst" not in keywords:
        return None
    amount = _sunburst_counter_amount(game, card_state)
    if amount is None:
        return None
    is_creature = Type.CREATURE in card_state.card.types
    counter_kind = "+1/+1" if is_creature else "charge"
    effect = _make(
        ReplacementKind.ENTERS_WITH,
        "Sunburst",
        subject=card_state.card.name,
        replacement=f"{amount} {counter_kind} counters",
        amount=amount,
        counter_kind=counter_kind,
        self_replacement=True,
    )
    return ("self:sunburst", _apply_self_enters(effect, amount), "Sunburst (CR 702.44a)", False)


#: CR 702.150a's own life-payment count, per Phyrexian symbol.
_COMPLEATED_LIFE_PER_SYMBOL = 2


def _compleated_modifier(
    game: "Game", card_state: CardState
) -> tuple[str, Apply, str, bool] | None:
    """Compleated (CR 702.150a), read off the keyword rather than off a
    parsed sentence, the same way `_sunburst_modifier` is: "Compleated
    (`{.../P}` can be paid with `...` or 2 life. If life was paid, this
    planeswalker enters with two fewer loyalty counters.)" is reminder text
    (CR 207.2), never a rules-text sentence `_ENTERS_WITH` matches.

    CR 702.150a verbatim: "If this permanent would enter with one or more
    loyalty counters on it and the player who cast it chose to pay life for
    any part of its cost represented by Phyrexian mana symbols, it instead
    enters the battlefield with that many loyalty counters minus two for
    each of those mana symbols."

    Three conditions gate this, each one a corner this mechanic has to get
    right rather than a guess:

    - **"this permanent"** - only a planeswalker has loyalty counters to
      begin with (CR 205.2a gates `CardState.intrinsic_entering_counters` the same way), so a
      Compleated keyword on anything else (none in the pool, but nothing here
      assumes otherwise) does nothing.
    - **"would enter with one or more loyalty counters"** - read off the
      entering object's own printed loyalty (CR 306.5a) while it is still on
      its way in, before CR 306.5b has placed any. A planeswalker printed
      with no loyalty stat at all has none to reduce.
    - **"the player who cast it chose to pay life"** - CR 601.2h's settled
      payment, not "life was paid for any reason": `CastRecord.
      phyrexian_life_symbols_paid` is written only from the Phyrexian half of
      `PaymentOption` (`machines/cost.CostPayment.phyrexian_life_symbols_
      paid`), never from an unrelated `pay_life_cost` additional cost. No
      record at all - the permanent was put onto the battlefield some other
      way (Tooth and Nail, a blink), never cast, CR 400.7 - reads as "chose
      to pay life" being false, not true: `Game.cast_record_of` already fails
      closed the same way for every other CR 601.2b choice a permanent's
      entering event reads (`_x_is`, `_sunburst_counter_amount`). A **copy**
      of a compleated spell (CR 707.10, `Game.copy_spell`) carries a record
      too, but never one naming this field - `Game.copy_spell`'s own
      `note_cast` call does not pass it, the same exclusion its docstring
      already gives `mana_spent`/`spend_effects` - so a copy always enters at
      full printed loyalty regardless of how the original was paid for.
    """
    keywords = {k.lower() for k in card_state.card.keywords}
    if "compleated" not in keywords:
        return None
    # `CardState.loyalty` reads the printed number (CR 306.5a) whenever the
    # object is not on the battlefield - exactly where this runs, CR 614.12's
    # "while it is still on its way in". `is_planeswalker` is layer-aware and
    # falls back to the printed type off the battlefield too, the same gate
    # `CardState.intrinsic_entering_counters` itself uses.
    if not card_state.is_planeswalker or (card_state.loyalty or 0) < 1:
        return None
    record = game.cast_record_of(card_state)
    symbols_paid_with_life = record.phyrexian_life_symbols_paid if record is not None else 0
    if symbols_paid_with_life <= 0:
        return None
    reduction = _COMPLEATED_LIFE_PER_SYMBOL * symbols_paid_with_life

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        del game, source
        event.loyalty_reduction += reduction

    text = (
        f"Compleated: enters with {reduction} fewer loyalty counters "
        f"({symbols_paid_with_life} Phyrexian symbol"
        f"{'s' if symbols_paid_with_life != 1 else ''} paid with life, CR 702.150a)"
    )
    return ("self:compleated", apply, text, False)


def _apply_self_enters(effect: ReplacementEffect, amount: int | None) -> Apply:
    """`amount` is `effect.amount` for a fixed count, or CR 107.3m's resolved
    X for a variable one - `_self_enters_modifiers` has already worked out
    which, so this only ever sees a real number by the time it is called.
    """

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        if effect.kind is ReplacementKind.ENTERS_TAPPED:
            event.tapped = True
        elif effect.kind is ReplacementKind.ENTERS_PREPARED:
            event.prepared = True
        else:
            assert effect.counter_kind is not None and amount is not None
            if _AND_WITH_HASTE.search(effect.replacement or ""):
                event.grants_haste = True
            event.counters[effect.counter_kind] = (
                event.counters.get(effect.counter_kind, 0) + amount
            )

    return apply


# --------------------------------------------------------------------------
# Gathering, ordering, applying
# --------------------------------------------------------------------------


def _impending_entering_counters(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """CR 702.176a's second ability: "If you chose to pay this permanent's
    impending cost, it enters with N time counters on it."

    CR 702.176a makes it "a replacement effect that may apply to the permanent
    with impending as it enters the battlefield from the stack", and CR 614.1c
    makes "[this permanent] enters with ..." a replacement effect - so it
    changes the same entering event every other entering counter does, and
    `Game.enter_the_battlefield` places the counters through `add_counters`.

    "From the stack" and "you chose to pay" are one question here:
    `event.was_cast` (a resolving spell) and its own `CastRecord.keyword`,
    which `resolve_top` has not popped yet. A blinked or reanimated permanent
    enters with no cast behind it and gets nothing (CR 400.7). N is read off
    the printed keyword line (`KeywordAbility.count`), never off the card's
    name. CR 118.9a allows one alternative cost per spell, so only the first
    impending line counts even on a card that printed two.
    """
    # Imported here, beside their one use: casting imports this module's siblings.
    from ...models.card_state import Counter
    from ..abilities import keyword_abilities

    entering = event.card
    if entering is None or not event.was_cast:
        return []
    record = game.cast_record_of(entering)
    if record is None or (record.keyword or "").lower() != "impending":
        return []
    amount = next(
        (
            ability.count
            for ability in keyword_abilities(entering.card)
            if ability.canonical.lower() == "impending" and ability.count is not None
        ),
        None,
    )
    if amount is None:
        return []

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.counters[Counter.TIME] = event.counters.get(Counter.TIME, 0) + amount

    return [
        ApplicableEffect(
            key=f"{entering.id}:impending",
            source=entering,
            label=f"impending: enters with {amount} time counters (CR 702.176a)",
            apply=apply,
        )
    ]


def _bloodthirst_entering_counters(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """CR 702.54a: "'Bloodthirst N' means 'If an opponent was dealt damage
    this turn, this permanent enters with N +1/+1 counters on it.'" - a CR
    614.1c "enters with" replacement on the entering permanent itself, cast
    or not. The condition is the turn-history clause the condition reader
    already reads (`machines/conditions/history.py`), asked for the entering
    permanent's controller; N is the printed keyword's own count
    (`KeywordAbility.count`). Each instance applies separately."""
    from ...models.card_state import Counter
    from ..abilities import keyword_abilities
    from ..conditions import ConditionContext, read_condition

    entering = event.card
    if entering is None:
        return []
    amounts = [
        ability.count
        for ability in keyword_abilities(entering.card)
        if ability.canonical.lower() == "bloodthirst" and ability.count is not None
    ]
    if not amounts:
        return []
    controller = entering.controller or entering.owner
    context = ConditionContext(game=game, controller=controller, source=entering)
    if read_condition(context, "an opponent was dealt damage this turn") is not True:
        return []
    found = []
    for index, amount in enumerate(amounts):

        def apply(
            game: "Game", source: CardState, event: ReplaceableEvent, n: int = amount
        ) -> None:
            event.counters[Counter.PLUS_ONE] = event.counters.get(Counter.PLUS_ONE, 0) + n

        found.append(
            ApplicableEffect(
                key=f"{entering.id}:bloodthirst:{index}",
                source=entering,
                label=f"bloodthirst: enters with {amount} +1/+1 counters (CR 702.54a)",
                apply=apply,
            )
        )
    return found


def _vanishing_entering_counters(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """CR 702.63a's first ability: "'Vanishing N' means 'This permanent enters
    with N time counters on it,' ...' " - a CR 614.1c "enters with" replacement
    on the entering permanent itself, cast or not (unlike impending's own
    version of the same shape, which is gated on an alternative cost paid;
    vanishing's own wording carries no such condition, so a Deadly Grub
    reanimated or put onto the battlefield by any effect still enters with its
    time counters). CR 702.63b: vanishing printed with no number is only the
    other two abilities, so a printing whose `KeywordAbility.count` is `None`
    gets nothing here. CR 702.63c: each instance applies separately, the same
    per-instance loop `_bloodthirst_entering_counters` above already uses."""
    from ...models.card_state import Counter
    from ..abilities import keyword_abilities

    entering = event.card
    if entering is None:
        return []
    amounts = [
        ability.count
        for ability in keyword_abilities(entering.card)
        if ability.canonical.lower() == "vanishing" and ability.count is not None
    ]
    if not amounts:
        return []
    found = []
    for index, amount in enumerate(amounts):

        def apply(
            game: "Game", source: CardState, event: ReplaceableEvent, n: int = amount
        ) -> None:
            event.counters[Counter.TIME] = event.counters.get(Counter.TIME, 0) + n

        found.append(
            ApplicableEffect(
                key=f"{entering.id}:vanishing:{index}",
                source=entering,
                label=f"vanishing: enters with {amount} time counters (CR 702.63a)",
                apply=apply,
            )
        )
    return found


#: Gather Specimens' and Crafty Cutpurse's sentence, either event: "[If] a
#: creature would enter the battlefield under an opponent's control this turn,
#: it enters under your control instead." / "each token that would be created
#: under an opponent's control this turn is created under your control
#: instead."
_ENTER_UNDER_YOUR_CONTROL_RE = re.compile(
    r"^(?:if )?(?:an?|each) (?P<subject>[a-z ]+?)(?: that)? would "
    r"(?P<verb>enter(?: the battlefield)?|be created) under an opponent'?s control,?\s+"
    r"(?:it )?(?:enters|is created) under your control instead\.?$",
    re.IGNORECASE,
)


def _read_enter_under_your_control(sentence: str) -> EnterUnderYourControl | None:
    match = _ENTER_UNDER_YOUR_CONTROL_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    words = match.group("subject").lower().split()
    tokens_only = words[-1] == "token"
    type_words = words[:-1] if tokens_only else words
    types = [_CARD_TYPE_WORDS.get(word) for word in type_words]
    if any(wanted is None for wanted in types) or (not types and not tokens_only):
        return None
    on_creation = match.group("verb").lower() == "be created"
    if on_creation and not tokens_only:
        return None  # only a token is ever "created" (CR 111.1)
    return EnterUnderYourControl(
        on_creation=on_creation,
        types=tuple(wanted for wanted in types if wanted is not None),
        tokens_only=tokens_only,
    )


from ._common import _CARD_TYPE_WORDS, _REFLEXIVE_OPENER  # noqa: E402
from .model import (  # noqa: E402
    CopyException,
    EnterUncastExile,
    EventKind,
    ReplacementKind,
    UnreadableCopyExceptionNotice,
)
from .parse import (  # noqa: E402
    _is_opponent,
    _is_optional,
    _make,
    _names_of,
    _parse_copy_exception,
    _parse_oracle_text,
    _read_counters,
    _read_opponents_permanent_classes,
    _read_zone_list,
    _static_form,
    parse_replacement_effects,
    strip_reminder_text,
)

# -- "Each <group> you control enters with an additional <kind> counter" -----
#
# CR 614.1c: "[This permanent] enters with ..." is a replacement effect, and
# CR 614.12 lets a *static ability of another permanent* modify how a permanent
# enters when it affects the entering object. A battlefield permanent (or,
# for "as long as this creature is in your graveyard", a graveyard card) that
# prints such a line adds counters to every matching permanent of its
# controller's as it enters. The counters ride the entering event
# (`ReplaceableEvent.counters`) exactly like a self "enters with" does.

_GROUP_ENTERS_RE = re.compile(
    r"^(?:as long as (?P<lead>.+?), )?"
    r"(?P<subject>.+? you control(?: that(?:'s| has) [^,]+?| of the chosen type)?)"
    r" enters? with (?:an|(?P<n>\w+)) additional (?P<kind>[^ ]+) counters? on (?:it|them)"
    r"(?: for each (?P<each>.+?))?(?: if (?P<trail>its mana value is 4 or less))?\.?$",
    re.IGNORECASE,
)
_GROUP_OTHERWISE_RE = re.compile(
    r"^otherwise, it enters with (?P<n>\w+) additional (?P<kind>[^ ]+) counters? on it\.?$",
    re.IGNORECASE,
)
_GROUP_SUBJECT_RE = re.compile(
    r"^(?:(?P<each>each other|each|other) )?(?P<desc>.+?) you control(?P<tail> .+)?$",
    re.IGNORECASE,
)
_IN_YOUR_GRAVEYARD_RE = re.compile(
    r"^this (?:creature|card|permanent) is in your graveyard$", re.IGNORECASE
)


def adventure_face(card):
    from ..casting.permissions import adventure_face as read_adventure_face

    return read_adventure_face(card)


def _is_subtype(entering: CardState, word: str) -> bool:
    return any(subtype.lower() == word for subtype in entering.card.subtypes)


def _noun_matches(entering: CardState, word: str) -> bool:
    """One noun of a group subject: a card type ("creature", "vehicle" is a
    subtype, "planeswalker") or a creature/permanent subtype."""
    singular = word[:-1] if word.endswith("s") else word
    card_type = _CARD_TYPE_WORDS.get(singular)
    if card_type is not None:
        return card_type in entering.types
    return _is_subtype(entering, singular)


def _group_subject_predicate(subject: str):
    """`(other, predicate(source, entering) -> bool)` for the subject phrase of
    a group "enters with" line ("each other Rogue creature you control",
    "legendary creatures you control", "each other Vehicle and creature you
    control", "each creature you control that's a Wolf or a Werewolf"), or
    `None` when it names a group not read."""
    match = _GROUP_SUBJECT_RE.match(subject.strip())
    if match is None:
        return None
    other = (match.group("each") or "").lower() in ("each other", "other")
    words = match.group("desc").lower().split()
    tail = (match.group("tail") or "").strip().lower()
    any_of = " and " in f" {match.group('desc').lower()} "
    qualifiers = [w for w in words if w == "legendary" or w.startswith("non-")]
    nouns = [w for w in words if w not in qualifiers and w != "and"]
    if not nouns:
        return None
    wanted_subtypes: set[str] = set()
    adventure = False
    if tail.startswith(("that's a ", "that's an ")):
        wanted_subtypes = {
            part.strip().lower()
            for part in re.split(r",| or ", tail.split(" a", 1)[1])
            if part.strip()
        }
        wanted_subtypes = {
            w.removeprefix("a ").removeprefix("an ").strip() for w in wanted_subtypes
        }
    elif tail == "that has an adventure":
        adventure = True
    elif tail and tail != "of the chosen type":
        return None
    chosen_type = tail == "of the chosen type"

    def predicate(source: CardState, entering: CardState) -> bool:
        hits = [_noun_matches(entering, noun) for noun in nouns]
        if not (any(hits) if any_of else all(hits)):
            return False
        for word in qualifiers:
            if word == "legendary":
                if Supertype.LEGENDARY not in entering.card.supertypes:
                    return False
            elif _is_subtype(entering, word[4:]):
                return False
        if wanted_subtypes and not any(_is_subtype(entering, w) for w in wanted_subtypes):
            return False
        if adventure and adventure_face(entering.card) is None:
            return False
        if chosen_type:
            chosen = getattr(source.choice, "value", source.choice)
            return bool(chosen) and chosen in entering.card.subtypes
        return True

    return other, predicate


def _group_mana_value_cap(entering: CardState) -> bool:
    return entering.mana_value <= 4


def group_enters_specs(lines: Iterable[str]):
    """Each group "enters with additional counters" line among `lines`, as
    `(in_graveyard, lead_condition, other, predicate, kind, count, each)` -
    `count` the fixed number, `each` the "for each" description or `None`."""
    found = []
    pending = None
    for raw in lines:
        sentences = [part.strip() for part in re.split(r"(?<=\.)\s+", raw.strip()) if part.strip()]
        for sentence in sentences:
            otherwise = _GROUP_OTHERWISE_RE.match(sentence)
            if otherwise is not None and pending is not None:
                pending["otherwise"] = (
                    parse_count(otherwise.group("n")) or 1,
                    otherwise.group("kind"),
                )
                continue
            match = _GROUP_ENTERS_RE.match(sentence)
            if match is None:
                continue
            subject = _group_subject_predicate(match.group("subject"))
            if subject is None:
                continue
            lead = match.group("lead")
            in_graveyard = (
                lead is not None and _IN_YOUR_GRAVEYARD_RE.match(lead.strip()) is not None
            )
            pending = {
                "in_graveyard": in_graveyard,
                "lead": None if in_graveyard else lead,
                "other": subject[0],
                "predicate": subject[1],
                "kind": match.group("kind"),
                "count": parse_count(match.group("n")) if match.group("n") else 1,
                "each": match.group("each"),
                "cap": match.group("trail") is not None,
                "otherwise": None,
                "text": sentence,
            }
            found.append(pending)
    return found


def _group_apply(spec, controller: str):
    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        entering = event.card
        if entering is None:
            return
        if spec["cap"] and not _group_mana_value_cap(entering):
            kind_count = spec["otherwise"]
            if kind_count is None:
                return
            amount, kind = kind_count
        else:
            kind = spec["kind"]
            amount = spec["count"]
            if spec["each"] is not None:
                reader = enters_count_reader(spec["each"])
                if reader is None:
                    return
                amount = amount * reader(game, controller, entering, 0)
        if amount > 0:
            event.counters[kind] = event.counters.get(kind, 0) + amount

    return apply


def _group_entering_counters(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """Every battlefield permanent's (and graveyard card's "as long as this
    creature is in your graveyard") group "enters with an additional counter"
    line that applies to the permanent entering in `event` (CR 614.1c)."""
    entering = event.card
    if entering is None:
        return []
    found: list[ApplicableEffect] = []
    sources: list[CardState] = list(game.battlefield)
    for player in game.players:
        sources.extend(player.graveyard)
    board = None
    for source in sources:
        oracle = source.card.oracle_text or ""
        lowered = oracle.lower()
        if "additional" not in lowered or " enter" not in lowered or "counter" not in lowered:
            continue
        on_battlefield = source.zone is Zone.BATTLEFIELD
        if on_battlefield:
            if "Class" in source.card.subtypes:
                lines = (source.class_ability_text or "").splitlines()
            else:
                board = board or game.computed_board()
                lines = list(board.of(source).abilities)
        else:
            lines = oracle.splitlines()
        controller = source.controller or source.owner
        if controller is None or entering.controller != controller:
            continue
        for index, spec in enumerate(group_enters_specs(lines)):
            if spec["in_graveyard"] == on_battlefield:
                continue
            if spec["other"] and source.id == entering.id:
                continue
            if not spec["predicate"](source, entering):
                continue
            if spec["lead"] is not None:
                answer = game.condition_holds(controller, spec["lead"], source)
                if answer is not True:
                    continue
            found.append(
                ApplicableEffect(
                    key=f"{source.id}:group:{index}",
                    source=source,
                    label=spec["text"],
                    apply=_group_apply(spec, controller),
                )
            )
    return found
