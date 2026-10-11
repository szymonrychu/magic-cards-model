"""Conditional static abilities (EP-01 round 2, task 3).

"As long as `<condition>`, `<subject>` `<gets/has/is ...>`" in either order,
"During your turn, `<subject>` `<...>`", and the ability words that only
decorate one of those (CR 207.2c: Metalcraft, Delirium, Hellbent, Threshold
carry no rules meaning of their own). One reader for the whole template, split
into three independent parts so a new card is a new combination of existing
parts rather than a new regex:

- a **condition** (`_parse_condition`): a build-time gate over `LayerContext`
  (whose turn it is, the top card of a library, the graveyard, the hand) and/or
  board atoms (`ControlsAtom`, `SourceCountersAtom`, ...) that ride on the
  effect's selector (`ConditionedSelector`) so they are judged against the
  characteristics computed so far, on every CR 613.5 computation;
- a **subject** (`_parse_subject`): this permanent, the attached creature, a
  soulbond pair, or a filtered group;
- a **predicate** (`_parse_predicate`): a power/toughness change, base
  power/toughness, keywords, a quoted ability, a type change, loss of all
  abilities, or "all activated abilities of that card".

CR 611.3a: a continuous effect from a static ability "isn't 'locked in'; it
applies at any given moment to whatever its text indicates" - nothing here is
stored, the effects are rebuilt with the board. CR 604.2: they exist as long as
the source remains on the battlefield and has the ability.

A quoted ability a conditional static grants (CR 613.1f) is also reconciled
onto `CardState.granted_ability_texts` (`sync_conditional_grant_texts`) so it is
a real, activatable or triggering ability and not only a line of text.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Sequence
from typing import NamedTuple
from uuid import UUID

from ...data.subtypes import canonical_subtype
from ...models.card import Color, Type
from ...models.card_state import CardState
from ...numbers import COUNT, parse_count
from ..abilities import ActivatedAbility, parse_abilities, self_normalized_effect_text
from ._common import _COLOR_WORDS
from .apply import EffectBuilder, LayerContext
from .model import (
    AllPermanentsControlledBy,
    Characteristics,
    ConditionedSelector,
    ContinuousEffect,
    CountBoardWhere,
    ControlsAtom,
    CounterKindsAmongAtom,
    Layer,
    Modification,
    NotSourceAtom,
    Only,
    PairedPartners,
    PermanentsOfTypes,
    QualityTest,
    Selector,
    SetCreatureTypes,
    SetTypesAndSubtypes,
    SharesColorAtom,
    SourceAttachedAtom,
    SourceAttachedToAtom,
    SourceCountersAtom,
    StaticAtom,
    SubjectQualityAtom,
    Sublayer,
    grant_ability,
    lose_all_abilities,
    modify_power_toughness,
    modify_power_toughness_per,
    set_power_toughness,
)
from .parse import (
    _ABILITY_WORD_RE,
    _parse_layer_sentence_ungated,
    _self_static_gate,
    _source_line_for,
    _split_and_validate_keywords,
    printed_characteristics,
)

#: A build-time condition over what the layer engine cannot see on the board.
Gate = Callable[[CardState, LayerContext], bool]


class _Condition(NamedTuple):
    """One parsed condition: build-time gates, board atoms (possibly derived
    from the context, Crown of Convergence's top-card colours), and what a
    following bare "it" refers to ("attached" after "equipped creature is")."""

    gates: tuple[Gate, ...] = ()
    atoms: tuple[StaticAtom, ...] = ()
    refers_to: str | None = None

    def merged(self, other: _Condition) -> _Condition:
        return _Condition(
            self.gates + other.gates,
            self.atoms + other.atoms,
            self.refers_to or other.refers_to,
        )


class _Subject(NamedTuple):
    """Who a predicate applies to: a selector factory over the source plus
    extra board atoms on each object (a group's qualities)."""

    kind: str  # "self" | "attached" | "paired" | "group"
    selectors: Callable[[CardState], list[Selector]]
    atoms: tuple[StaticAtom, ...] = ()
    needs_attachment: bool = False
    includes_self: bool = False
    """The source is also affected, whatever the group's own atoms say ("this
    creature and other Vampire creatures you control")."""


class _Change(NamedTuple):
    """One modification in one layer, built from the source and context."""

    layer: Layer
    sublayer: Sublayer | None
    make: Callable[[CardState, LayerContext], Modification | None]
    description: str
    quoted: str | None = None


class _Parsed(NamedTuple):
    condition: _Condition
    subject: _Subject
    changes: tuple[_Change, ...]
    line: str
    inner: EffectBuilder | None = None
    """An already-parsed unconditional body ("nonbasic lands are Mountains"),
    wrapped by the condition instead of being read again here."""


# -- conditions ---------------------------------------------------------------

_SELF = r"(?:this (?:creature|permanent|artifact|enchantment|land|vehicle|token|equipment|aura))"
_ARTICLE = r"(?:another|an|a)"

_TOP_CARD_RE = re.compile(
    r"^the top card of your library is (?:an? )?(?P<quality>.+?)(?: card)?$", re.IGNORECASE
)
_SOURCE_COUNTER_RE = re.compile(
    rf"^(?:{_SELF}|it) has (?:(?P<count>{COUNT}) or more|an?|one or more) "
    r"(?P<kind>[a-z0-9+/ -]+?) counters? on (?:it|him|her|them)$",
    re.IGNORECASE,
)
_YOU_CONTROL_RE = re.compile(
    r"^(?P<who>you|an opponent|any player|your opponents?) controls? "
    rf"(?:(?P<count>{COUNT}) or more(?P<other_n> other)?"
    rf"|(?P<article>{_ARTICLE})\b"
    r"|(?P<none>no)\b"
    rf"|(?P<at_least>at least {COUNT})(?P<other_al> other)?) ?"
    r"(?P<quality>.+)$",
    re.IGNORECASE,
)
_GRAVEYARD_CARDS_RE = re.compile(
    rf"^(?:there are|you have) (?P<count>{COUNT}) or more cards? in your graveyard$", re.IGNORECASE
)
_GRAVEYARD_TYPES_RE = re.compile(
    rf"^there are (?P<count>{COUNT}) or more card types among cards in your graveyard$",
    re.IGNORECASE,
)
_COUNTER_KINDS_RE = re.compile(
    rf"^there are (?P<count>{COUNT}) or more different kinds of counters among "
    r"(?P<quality>.+?) you control$",
    re.IGNORECASE,
)
_NO_CARDS_IN_HAND_RE = re.compile(r"^you have no cards in hand$", re.IGNORECASE)
_THIS_IS_RE = re.compile(rf"^{_SELF} is (?P<state>equipped|enchanted|modified)$", re.IGNORECASE)
_ATTACHED_IS_RE = re.compile(
    r"^(?P<attached>equipped|enchanted) (?P<noun>creature|permanent) is (?:an? )?(?P<quality>.+)$",
    re.IGNORECASE,
)
_YOUR_TURN_RE = re.compile(r"^it(?:'s| is) your turn$", re.IGNORECASE)
_ATTACHED_TO_RE = re.compile(
    rf"^{_SELF} is attached to an? (?P<quality>.+)$", re.IGNORECASE
)
_PAIRED_RE = re.compile(rf"^{_SELF} is paired with another creature$", re.IGNORECASE)


def _subtype(word: str) -> str | None:
    canonical = canonical_subtype(word)
    return canonical.title() if canonical else None


def _card_type(word: str) -> Type | None:
    try:
        return Type(word.lower())
    except ValueError:
        return None


@functools.cache
def _quality(phrase: str) -> QualityTest | None:
    """ "creature with a counter on it" / "Demon" / "transformed permanent" /
    "legendary creature" / "black" / "artifact or creature" / "nonland
    permanent" -> the test it names, or None for any word not read."""
    text = re.sub(r"^(?:an?|another) ", "", phrase.strip(), flags=re.IGNORECASE)
    counter: str | None = None
    with_counter = re.search(
        r"\s+with (?:an? |one or more )?(?:(?P<kind>[a-z0-9+/-]+) )?counters? on (?:it|them)$",
        text,
        re.IGNORECASE,
    )
    if with_counter:
        counter = (with_counter.group("kind") or "").lower()
        text = text[: with_counter.start()]
    types: list[Type] = []
    not_types: list[Type] = []
    subtypes: list[str] = []
    colors: list[Color] = []
    legendary: bool | None = None
    token: bool | None = None
    transformed: bool | None = None
    alternatives = [part for part in re.split(r"\s+or\s+|,\s*(?:or\s+)?", text) if part]
    any_types: list[Type] = []
    for part in alternatives:
        for word in part.split():
            lowered = word.lower()
            if lowered in _COLOR_WORDS:
                colors.append(_COLOR_WORDS[lowered])
            elif lowered == "legendary":
                legendary = True
            elif lowered == "nonlegendary":
                legendary = False
            elif lowered == "token":
                token = True
            elif lowered == "nontoken":
                token = False
            elif lowered == "transformed":
                transformed = True
            elif lowered == "permanent":
                continue
            elif lowered.startswith("non") and _card_type(lowered[3:]) is not None:
                not_types.append(_card_type(lowered[3:]))  # type: ignore[arg-type]
            elif (card_type := _card_type(lowered)) is not None or (
                card_type := _card_type(lowered.rstrip("s"))
            ):
                (any_types if len(alternatives) > 1 else types).append(card_type)
            elif word[:1].isupper() and (subtype := _subtype(word)) is not None:
                subtypes.append(subtype)
            else:
                return None
    if len(alternatives) > 1 and any_types and not subtypes and not colors:
        # "artifact or creature": a card type alternative is not expressible as
        # one `QualityTest`; the caller expands it (`_quality_alternatives`).
        return None
    return QualityTest(
        types=tuple(types),
        not_types=tuple(not_types),
        subtypes_any=tuple(subtypes),
        colors_any=tuple(colors),
        legendary=legendary,
        token=token,
        transformed=transformed,
        counter=counter,
    )


@functools.cache
def _quality_alternatives(phrase: str) -> tuple[QualityTest, ...] | None:
    """`_quality`, or - for "artifact or creature" - one test per alternative."""
    single = _quality(phrase)
    if single is not None:
        return (single,)
    text = re.sub(r"^(?:an?|another) ", "", phrase.strip(), flags=re.IGNORECASE)
    parts = [part.strip() for part in re.split(r"\s+or\s+|,\s*(?:or\s+)?", text) if part.strip()]
    if len(parts) < 2:
        return None
    tests = [_quality(part) for part in parts]
    if any(test is None for test in tests):
        return None
    return tuple(test for test in tests if test is not None)


def _top_card_gate(quality: tuple[QualityTest, ...]) -> Gate:
    def gate(source: CardState, context: LayerContext) -> bool:
        top = context.top_card_of(source.controller)
        if top is None:
            return False
        chars = printed_characteristics(top)
        return any(test.matches(chars) for test in quality)

    return gate


def _count_of(raw: str | None, *, default: int = 1) -> int | None:
    if raw is None:
        return default
    return parse_count(raw, article=True)


def _parse_condition(text: str) -> _Condition | None:
    """One condition clause, or None for a clause not read. "A and B" is both."""
    clause = " ".join(text.strip().rstrip(".").split())
    lowered = clause.lower()
    if match := _YOUR_TURN_RE.fullmatch(clause):
        return _Condition(gates=(_your_turn_gate,))
    if match := _ATTACHED_TO_RE.fullmatch(clause):
        quality = _quality(match.group("quality"))
        if quality is None:
            return None
        return _Condition(atoms=(SourceAttachedToAtom(quality=quality),))
    if _PAIRED_RE.fullmatch(clause):
        # CR 702.95a-e: the pair itself is the condition - the paired-partners
        # selector (the subject) only matches while both creatures point at each
        # other under one controller, so nothing further is asked of the source.
        return _Condition()
    if match := _TOP_CARD_RE.fullmatch(clause):
        alternatives = _quality_alternatives(match.group("quality"))
        if alternatives is None:
            return None
        return _Condition(gates=(_top_card_gate(alternatives),))
    if match := _SOURCE_COUNTER_RE.fullmatch(clause):
        threshold = _count_of(match.group("count"))
        if threshold is None:
            return None
        return _Condition(
            atoms=(
                SourceCountersAtom(
                    counter=match.group("kind").strip().lower(), threshold=threshold
                ),
            )
        )
    if match := _THIS_IS_RE.fullmatch(clause):
        state = match.group("state").lower()
        if state == "modified":
            return _Condition(atoms=(SourceAttachedAtom(modified=True),))
        return _Condition(
            atoms=(SourceAttachedAtom(subtype="Equipment" if state == "equipped" else "Aura"),)
        )
    if match := _ATTACHED_IS_RE.fullmatch(clause):
        quality = _quality(match.group("quality"))
        if quality is None:
            return None
        return _Condition(
            atoms=(SubjectQualityAtom(of="target", quality=quality),), refers_to="attached"
        )
    if match := _GRAVEYARD_TYPES_RE.fullmatch(clause):
        needed = parse_count(match.group("count"), article=False)
        if needed is None:
            return None
        return _Condition(gates=(_graveyard_types_gate(needed),))
    if match := _GRAVEYARD_CARDS_RE.fullmatch(clause):
        needed = parse_count(match.group("count"), article=False)
        if needed is None:
            return None
        return _Condition(gates=(_graveyard_cards_gate(needed),))
    if _NO_CARDS_IN_HAND_RE.fullmatch(clause):
        return _Condition(gates=(_empty_hand_gate,))
    if match := _COUNTER_KINDS_RE.fullmatch(clause):
        needed = parse_count(match.group("count"), article=False)
        quality = _quality(match.group("quality"))
        if needed is None or quality is None:
            return None
        return _Condition(atoms=(CounterKindsAmongAtom(quality=quality, threshold=needed),))
    if match := _YOU_CONTROL_RE.fullmatch(clause):
        controls = _controls_atom(match)
        if controls is None:
            return None
        return _Condition(atoms=(controls,))
    gated = _self_static_gate(clause)
    if gated is not None:
        return _Condition(gates=(gated[0],))
    parts = re.split(r",? and ", clause)
    if len(parts) > 1:
        parsed = [_parse_condition(part) for part in parts]
        if all(each is not None for each in parsed):
            combined = _Condition()
            for each in parsed:
                combined = combined.merged(each)  # type: ignore[arg-type]
            return combined
    del lowered
    return None


def _controls_atom(match: re.Match[str]) -> ControlsAtom | None:
    who_word = match.group("who").lower()
    who = "you" if who_word == "you" else "any" if who_word == "any player" else "opponent"
    threshold = 1
    other = bool(match.group("article") and match.group("article").lower() == "another")
    if match.group("count"):
        counted = parse_count(match.group("count"), article=False)
        if counted is None:
            return None
        threshold = counted
        other = bool(match.group("other_n"))
    elif match.group("at_least"):
        counted = parse_count(match.group("at_least").split()[-1], article=False)
        if counted is None:
            return None
        threshold = counted
        other = bool(match.group("other_al"))
    quality = _quality(match.group("quality").strip())
    if quality is None:
        return None
    if match.group("none"):
        return ControlsAtom(who=who, quality=quality, threshold=0, maximum=0, other=other)
    return ControlsAtom(who=who, quality=quality, threshold=threshold, other=other)


def _your_turn_gate(source: CardState, context: LayerContext) -> bool:
    return source.controller is not None and context.active_player == source.controller


def _empty_hand_gate(source: CardState, context: LayerContext) -> bool:
    return context.hand_size_of(source.controller) == 0


def _graveyard_cards_gate(needed: int) -> Gate:
    def gate(source: CardState, context: LayerContext) -> bool:
        return len(context.graveyard_of(source.controller)) >= needed

    return gate


def _graveyard_types_gate(needed: int) -> Gate:
    def gate(source: CardState, context: LayerContext) -> bool:
        kinds: set[Type] = set()
        for card in context.graveyard_of(source.controller):
            kinds.update(printed_characteristics(card).types)
        return len(kinds) >= needed

    return gate


# -- subjects -----------------------------------------------------------------

_SELF_SUBJECT_RE = re.compile(rf"^(?:{_SELF}|it|he|she|they)$", re.IGNORECASE)
_ATTACHED_SUBJECT_RE = re.compile(r"^(?:equipped|enchanted) (?:creature|permanent)$", re.IGNORECASE)
_PAIRED_SUBJECT_RE = re.compile(
    r"^(?:both creatures|(?:both of )?(?:each of )?those creatures|each of those creatures)$",
    re.IGNORECASE,
)
_SELF_AND_OTHERS_RE = re.compile(
    rf"^(?P<self>{_SELF}) and other (?P<group>.+?) you control$", re.IGNORECASE
)
_GROUP_SUBJECT_RE = re.compile(
    r"^(?:each |all )?(?P<other>other )?(?P<group>.+?)(?P<mine> you control)?"
    r"(?: that (?:'s|is|are|share a color with that card)(?P<tail>.*))?$",
    re.IGNORECASE,
)
_THAT_SHARE_RE = re.compile(
    r"^(?P<group>.+?) you control that share a color with that card$", re.IGNORECASE
)


def _group_quality(noun: str) -> QualityTest | None:
    """ "creatures" / "Vampire creatures" / "Equipment" / "Slivers" -> test."""
    words = noun.split()
    singular = [
        word[:-1]
        if word.lower()
        in ("creatures", "artifacts", "lands", "permanents", "tokens", "enchantments", "planeswalkers")
        else word
        for word in words
    ]
    return _quality(" ".join(singular))


def _parse_subject(text: str, condition: _Condition) -> tuple[_Subject, _Condition] | None:
    """The subject of a predicate, plus the condition it contributes (a group
    that "shares a color with that card" adds the top card's colours)."""
    phrase = " ".join(text.strip().split())
    if _SELF_SUBJECT_RE.fullmatch(phrase):
        if phrase.lower() in {"it", "he", "she", "they"} and condition.refers_to == "attached":
            return _attached_subject(), condition
        return _Subject("self", lambda source: [Only(card_id=source.id)]), condition
    if _ATTACHED_SUBJECT_RE.fullmatch(phrase):
        return _attached_subject(), condition
    if _PAIRED_SUBJECT_RE.fullmatch(phrase):
        return _Subject("paired", lambda source: [PairedPartners(source_id=source.id)]), condition
    if match := _SELF_AND_OTHERS_RE.fullmatch(phrase):
        quality = _group_quality(match.group("group"))
        if quality is None:
            return None
        return _group_subject(quality, other=True, includes_self=True), condition
    if match := _THAT_SHARE_RE.fullmatch(phrase):
        quality = _group_quality(match.group("group"))
        if quality is None:
            return None
        return (
            _Subject(
                "group",
                lambda source: [AllPermanentsControlledBy(username=source.controller)],
                (SubjectQualityAtom(of="target", quality=quality),),
            ),
            condition._replace(refers_to="shares_color_with_top_card"),
        )
    if match := _GROUP_SUBJECT_RE.fullmatch(phrase):
        if match.group("tail"):
            quality = _group_quality(match.group("group"))
            if quality is None:
                return None
            tail = _quality_alternatives(re.sub(r"^(?:an?|the) ", "", match.group("tail").strip()))
            if tail is None or len(tail) != 1:
                return None
            merged = quality.model_copy(
                update={"subtypes_any": tail[0].subtypes_any or quality.subtypes_any}
            )
            return _group_subject(merged, other=bool(match.group("other"))), condition
        quality = _group_quality(match.group("group"))
        if quality is None:
            return None
        return (
            _group_subject(
                quality, other=bool(match.group("other")), anyone=not match.group("mine")
            ),
            condition,
        )
    return None


def _group_subject(
    quality: QualityTest, *, other: bool, includes_self: bool = False, anyone: bool = False
) -> _Subject:
    """A filtered group; `anyone` is "All Sliver creatures" with no "you control" -
    every permanent whoever controls it."""

    def selectors(source: CardState) -> list[Selector]:
        if anyone:
            return [PermanentsOfTypes(card_types=tuple(Type))]
        return [AllPermanentsControlledBy(username=source.controller)]

    atoms: list[StaticAtom] = [SubjectQualityAtom(of="target", quality=quality)]
    if other:
        atoms.append(NotSourceAtom())
    return _Subject("group", selectors, tuple(atoms), includes_self=includes_self)


def _attached_subject() -> _Subject:
    def selectors(source: CardState) -> list[Selector]:
        return [Only(card_id=source.attached_to)] if source.attached_to is not None else []

    return _Subject("attached", selectors, (), needs_attachment=True)


# -- predicates ---------------------------------------------------------------

_QUOTE_RE = re.compile(r'"([^"]+)"')
_COND_PUMP_RE = re.compile(
    r"^gets? (?:an additional )?(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)$", re.IGNORECASE
)
_PUMP_PER_RE = re.compile(
    r"^gets? (?P<power>[+-]X|[+-]\d+)/(?P<toughness>[+-]X|[+-]\d+), where X is the number of "
    r"(?P<what>.+?) you control$",
    re.IGNORECASE,
)
_BASE_PT_RE = re.compile(
    r"^(?:has|have) base power and toughness (?P<power>\d+)/(?P<toughness>\d+)$", re.IGNORECASE
)
_HAS_RE = re.compile(r"^(?:has|have) (?P<rest>.+)$", re.IGNORECASE)
_CANT_BE_ATTACKED_RE = re.compile(r"^can'?t be attacked$", re.IGNORECASE)
#: The line a "can't be attacked" predicate writes onto its subject, which
#: `machines/combat._defender_refusal` reads back off the computed board.
CANT_BE_ATTACKED_LINE = "This permanent can't be attacked."
_LOSES_ALL_RE = re.compile(r"^loses? all abilities$", re.IGNORECASE)
_ALL_ACTIVATED_RE = re.compile(
    r"^(?:has|have) all activated abilities of that card$", re.IGNORECASE
)


def _count_what(what: str) -> CountBoardWhere | None:
    """ "Mountains" / "artifacts" / "Goblins" -> the permanents you control that
    it counts (CR 205.2a card types, CR 205.3 subtypes), read off the board."""
    words = what.strip().split()
    if len(words) != 1:
        return None
    word = words[0]
    singular = word[:-1] if word.lower().endswith("s") else word
    if (card_type := _card_type(singular)) is not None:
        return CountBoardWhere(scope="you", types_any=(card_type,))
    if (subtype := _subtype(singular)) is not None or (subtype := _subtype(word)) is not None:
        return CountBoardWhere(scope="you", subtypes_any=(subtype.lower(),))
    return None


def _top_card_activated_texts(source: CardState, context: LayerContext) -> list[str]:
    """The activated abilities of the top card of the source's controller's
    library, as text for a grantee: the card's own name reads as the grantee
    (the "use this creature's name instead" reminder)."""
    top = context.top_card_of(source.controller)
    if top is None:
        return []
    texts = [
        self_normalized_effect_text(top.name, ability.raw)
        for ability in parse_abilities(top.card)
        if isinstance(ability, ActivatedAbility)
    ]
    return list(dict.fromkeys(texts))


def _parse_predicate(text: str) -> tuple[_Change, ...] | None:
    """What a conditional static does to its subject, or None if unread. A
    predicate is one or more clauses joined by " and "; a quoted ability is
    lifted out first so its own words are never split."""
    quotes: list[str] = []

    def lift(match: re.Match[str]) -> str:
        quotes.append(match.group(1))
        return f"\0{len(quotes) - 1}\0"

    lifted = _QUOTE_RE.sub(lift, text.strip().rstrip("."))
    changes: list[_Change] = []
    pieces = [piece for piece in re.split(r"\s+and\s+(?=gets?\b|has\b|have\b)", lifted) if piece]
    for piece in pieces:
        piece = piece.strip()
        if match := _COND_PUMP_RE.fullmatch(piece):
            power, toughness = int(match.group("power")), int(match.group("toughness"))
            changes.append(
                _Change(
                    Layer.POWER_TOUGHNESS,
                    Sublayer.MODIFY,
                    lambda source, context, p=power, t=toughness: modify_power_toughness(p, t),
                    f"{power:+d}/{toughness:+d}",
                )
            )
            continue
        if match := _PUMP_PER_RE.fullmatch(piece):
            counted = _count_what(match.group("what"))
            if counted is None:
                return None
            fixed = [0, 0]
            per = [0, 0]
            for index, part in enumerate((match.group("power"), match.group("toughness"))):
                if part[1:].upper() == "X":
                    per[index] = 1 if part[0] == "+" else -1
                else:
                    fixed[index] = int(part)
            changes.append(
                _Change(
                    Layer.POWER_TOUGHNESS,
                    Sublayer.MODIFY,
                    lambda source, context, c=counted, p=tuple(per): modify_power_toughness_per(
                        c, p[0], p[1]
                    ),
                    f"{match.group('power')}/{match.group('toughness')} for each {match.group('what')}",
                )
            )
            if any(fixed):
                changes.append(
                    _Change(
                        Layer.POWER_TOUGHNESS,
                        Sublayer.MODIFY,
                        lambda source, context, f=tuple(fixed): modify_power_toughness(f[0], f[1]),
                        f"{fixed[0]:+d}/{fixed[1]:+d}",
                    )
                )
            continue
        if match := _BASE_PT_RE.fullmatch(piece):
            base = (int(match.group("power")), int(match.group("toughness")))
            changes.append(
                _Change(
                    Layer.POWER_TOUGHNESS,
                    Sublayer.SET,
                    lambda source, context, b=base: set_power_toughness(*b),
                    f"base {base[0]}/{base[1]}",
                )
            )
            continue
        if match := _BECOMES_RE.fullmatch(piece):
            becomes = _parse_becomes(match)
            if becomes is None:
                return None
            changes.extend(becomes)
            continue
        if _CANT_BE_ATTACKED_RE.fullmatch(piece):
            changes.append(
                _Change(
                    Layer.ABILITY,
                    None,
                    lambda source, context: grant_ability(CANT_BE_ATTACKED_LINE),
                    "can't be attacked",
                )
            )
            continue
        if _LOSES_ALL_RE.fullmatch(piece):
            changes.append(
                _Change(
                    Layer.ABILITY,
                    None,
                    lambda source, context: lose_all_abilities,
                    "loses all abilities",
                )
            )
            continue
        if _ALL_ACTIVATED_RE.fullmatch(piece):
            changes.append(
                _Change(
                    Layer.ABILITY,
                    None,
                    lambda source, context: None,
                    "all activated abilities of the top card",
                    quoted="*top-card*",
                )
            )
            continue
        if match := _HAS_RE.fullmatch(piece):
            granted = _parse_grants(match.group("rest"), quotes)
            if granted is None:
                return None
            changes.extend(granted)
            continue
        return None
    return tuple(changes) or None


_BECOMES_RE = re.compile(
    r"^(?:is|are) an? (?P<head>.+?)(?: with base power and toughness (?P<bp>\d+)/(?P<bt>\d+))?$",
    re.IGNORECASE,
)
_PT_WORD_RE = re.compile(r"^(?P<power>\d+)/(?P<toughness>\d+)$")


def _parse_becomes(match: re.Match[str]) -> list[_Change] | None:
    """ "is a Bear [with base power and toughness 4/2]" / "is a 5/5 Golem
    artifact creature": the type line the subject has while the condition
    holds (CR 613.1d), its base power and toughness (CR 613.4b). Card types
    named replace the old ones (CR 205.1a); only creature types named replace
    the creature types and leave the card types alone (CR 205.3d)."""
    types: list[Type] = []
    subtypes: list[str] = []
    base: tuple[int, int] | None = None
    if match.group("bp"):
        base = (int(match.group("bp")), int(match.group("bt")))
    for word in match.group("head").split():
        if pt := _PT_WORD_RE.fullmatch(word):
            base = (int(pt.group("power")), int(pt.group("toughness")))
        elif (card_type := _card_type(word)) is not None:
            types.append(card_type)
        elif (subtype := _subtype(word)) is not None:
            subtypes.append(subtype)
        else:
            return None
    if not (types or subtypes or base):
        return None
    changes: list[_Change] = []
    if types:
        changes.append(
            _Change(
                Layer.TYPE,
                None,
                lambda source, context, t=tuple(types), s=tuple(subtypes): SetTypesAndSubtypes(
                    types=t, subtypes=s
                ),
                "becomes " + " ".join((*subtypes, *(each.value for each in types))),
            )
        )
    elif subtypes:
        changes.append(
            _Change(
                Layer.TYPE,
                None,
                lambda source, context, s=tuple(subtypes): SetCreatureTypes(subtypes=s),
                "becomes " + " ".join(subtypes),
            )
        )
    if base is not None:
        changes.append(
            _Change(
                Layer.POWER_TOUGHNESS,
                Sublayer.SET,
                lambda source, context, b=base: set_power_toughness(*b),
                f"base {base[0]}/{base[1]}",
            )
        )
    return changes


_EQUIP_GRANT_RE = re.compile(r"^equip (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def _parse_grants(raw: str, quotes: list[str]) -> list[_Change] | None:
    """ "flying and vigilance" / '\0 0\0' (one quoted ability) -> grants."""
    changes: list[_Change] = []
    for piece in [
        part.strip() for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", raw) if part.strip()
    ]:
        if quoted := re.fullmatch(r"\0(\d+)\0", piece):
            text = quotes[int(quoted.group(1))]
            changes.append(
                _Change(
                    Layer.ABILITY,
                    None,
                    lambda source, context, t=text: grant_ability(t),
                    f"has {text!r}",
                    quoted=text,
                )
            )
            continue
        if equip := _EQUIP_GRANT_RE.fullmatch(piece):
            text = f"Equip {equip.group('cost')}"
            changes.append(
                _Change(
                    Layer.ABILITY,
                    None,
                    lambda source, context, t=text: grant_ability(t),
                    f"has {text}",
                )
            )
            continue
        keywords = _split_and_validate_keywords(piece)
        if keywords is None:
            return None
        for keyword in keywords:
            changes.append(
                _Change(
                    Layer.ABILITY,
                    None,
                    lambda source, context, k=keyword: grant_ability(k),
                    f"has {keyword}",
                )
            )
    return changes or None


# -- the whole sentence -------------------------------------------------------

_LEADING_RE = re.compile(r"^as long as (?P<condition>.+?), (?P<body>.+)$", re.IGNORECASE)
_TRAILING_RE = re.compile(r"^(?P<body>.+?) as long as (?P<condition>[^,]+)$", re.IGNORECASE)
_DURING_YOUR_TURN_RE = re.compile(
    r"^during your (?P<phase>turn|end step|upkeep|draw step), (?P<rest>.+)$", re.IGNORECASE
)
#: The steps of the active player's turn each "during your `<phase>`" names.
_PHASE_STEPS: dict[str, frozenset[str]] = {
    "end step": frozenset({"end_step"}),
    "upkeep": frozenset({"upkeep"}),
    "draw step": frozenset({"draw"}),
}


def _your_step_gate(steps: frozenset[str]) -> Gate:
    def gate(source: CardState, context: LayerContext) -> bool:
        return _your_turn_gate(source, context) and context.current_step in steps

    return gate
_SUBJECT_PREDICATE_RE = re.compile(
    r"^(?P<subject>.+?) (?P<predicate>(?:gets?|has|have|loses?|is|are|can't|cannot) .+)$", re.IGNORECASE
)


def _split_subject_predicate(body: str) -> list[tuple[str, str]]:
    """Every way to cut `body` into subject and predicate at a verb, the
    longest subject first - a group subject ("creatures you control that share
    a color with that card") contains no verb of its own, so the first verb is
    always the cut."""
    match = _SUBJECT_PREDICATE_RE.fullmatch(body.strip())
    return [(match.group("subject"), match.group("predicate"))] if match else []


def _lift_quotes(text: str) -> tuple[str, list[str]]:
    """`text` with each quoted ability replaced by a placeholder, so a condition
    inside a quoted ability is never read as the sentence's own."""
    quotes: list[str] = []

    def lift(match: re.Match[str]) -> str:
        quotes.append(match.group(0))
        return f"\0{len(quotes) - 1}\0"

    return _QUOTE_RE.sub(lift, text), quotes


def _restore_quotes(text: str, quotes: list[str]) -> str:
    return re.sub(r"\0(\d+)\0", lambda match: quotes[int(match.group(1))], text)


@functools.lru_cache(maxsize=4096)
def _parse(sentence: str) -> _Parsed | None:
    line = (
        _ABILITY_WORD_RE.sub(lambda m: m.group("rest"), sentence.strip(), count=1)
        .strip()
        .rstrip(".")
    )
    full_line = line
    line, quotes = _lift_quotes(line)
    lowered = line.lower()
    if "as long as" not in lowered and not lowered.startswith("during your ") and not quotes:
        return None
    condition = _Condition()
    if match := _DURING_YOUR_TURN_RE.fullmatch(line):
        steps = _PHASE_STEPS.get(match.group("phase").lower())
        condition = _Condition(gates=(_your_step_gate(steps) if steps else _your_turn_gate,))
        line = match.group("rest")
    candidates: list[tuple[str | None, str]] = []
    if (condition.gates or quotes) and "as long as" not in line.lower():
        candidates.append((None, line))
    if match := _LEADING_RE.fullmatch(line):
        candidates.append((match.group("condition"), match.group("body")))
    if match := _TRAILING_RE.fullmatch(line):
        candidates.append((match.group("condition"), match.group("body")))
    for index in [m.start() for m in re.finditer(r", ", line)]:
        head, tail = line[:index], line[index + 2 :]
        if head.lower().startswith("as long as "):
            candidates.append((head[len("as long as ") :], tail))
    for condition_text, body in candidates:
        body = _restore_quotes(body, quotes)
        if condition_text is None:
            merged = condition
        else:
            parsed_condition = _parse_condition(_restore_quotes(condition_text, quotes))
            if parsed_condition is None:
                continue
            merged = condition.merged(parsed_condition)
        inner = _parse_layer_sentence_ungated(body[:1].upper() + body[1:] + ".")
        if inner is not None and (merged.gates or merged.atoms):
            return _Parsed(merged, _Subject("inner", lambda source: []), (), full_line, inner)
        for subject_text, predicate_text in _split_subject_predicate(body):
            subject = _parse_subject(subject_text, merged)
            changes = _parse_predicate(predicate_text)
            if subject is None or changes is None:
                continue
            return _Parsed(subject[1], subject[0], changes, full_line)
    return None


def parse_conditional_static(sentence: str) -> EffectBuilder | None:
    """The builder for one conditional static sentence, or None if it is not
    one this module reads."""
    parsed = _parse(sentence)
    if parsed is None:
        return None
    return _builder(parsed)


def reads_conditional_static(sentence: str) -> bool:
    """Whether `parse_conditional_static` reads `sentence` (the audit's question)."""
    return _parse(sentence) is not None


def _top_card_colors(source: CardState, context: LayerContext) -> tuple[Color, ...]:
    top = context.top_card_of(source.controller)
    return tuple(printed_characteristics(top).colors) if top is not None else ()


def _condition_atoms(
    parsed: _Parsed, source: CardState, context: LayerContext
) -> tuple[StaticAtom, ...]:
    atoms = parsed.condition.atoms
    if parsed.condition.refers_to == "shares_color_with_top_card":
        atoms = (*atoms, SharesColorAtom(colors=_top_card_colors(source, context)))
    return atoms


def _atoms_for(parsed: _Parsed, source: CardState, context: LayerContext) -> tuple[StaticAtom, ...]:
    return (*_condition_atoms(parsed, source, context), *parsed.subject.atoms)


def _gates_hold(parsed: _Parsed, source: CardState, context: LayerContext) -> bool:
    if parsed.condition.refers_to == "shares_color_with_top_card" and not _top_card_colors(
        source, context
    ):
        return False
    return all(gate(source, context) for gate in parsed.condition.gates)


def _builder(parsed: _Parsed) -> EffectBuilder:
    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        if not _gates_hold(parsed, source, context):
            return []
        if parsed.inner is not None:
            atoms = _condition_atoms(parsed, source, context)
            printed = _source_line_for(source, parsed.line)
            return [
                effect.model_copy(
                    update={
                        "source_ability": printed,
                        "selector": ConditionedSelector(
                            base=effect.selector, source_id=source.id, atoms=atoms
                        )
                        if atoms
                        else effect.selector,
                    }
                )
                for effect in parsed.inner(source, timestamp, targets, context)
            ]
        selectors = _selectors(parsed, source, context)
        effects: list[ContinuousEffect] = []
        for change in parsed.changes:
            modifications = _modifications(change, source, context)
            for modification in modifications:
                for selector in selectors:
                    effects.append(
                        ContinuousEffect(
                            description=f"{source.name}: {change.description} ({parsed.line})",
                            layer=change.layer,
                            sublayer=change.sublayer,
                            timestamp=timestamp,
                            source_id=source.id,
                            source_ability=_source_line_for(source, parsed.line),
                            selector=selector,
                            modification=modification,
                        )
                    )
        return effects

    return builder


def _selectors(parsed: _Parsed, source: CardState, context: LayerContext) -> list[Selector]:
    """The selectors a parsed sentence applies through: the subject's, wrapped
    with the board atoms of the condition and the subject's own qualities, and
    - for "this creature and other ..." - the source alone."""
    bases = parsed.subject.selectors(source)
    if not bases:
        return []
    atoms = _atoms_for(parsed, source, context)
    conditional = _condition_atoms(parsed, source, context)
    selectors: list[Selector] = [
        ConditionedSelector(base=base, source_id=source.id, atoms=atoms) if atoms else base
        for base in bases
    ]
    if parsed.subject.includes_self:
        alone = Only(card_id=source.id)
        selectors.append(
            ConditionedSelector(base=alone, source_id=source.id, atoms=conditional)
            if conditional
            else alone
        )
    return selectors


def _modifications(change: _Change, source: CardState, context: LayerContext) -> list[Modification]:
    if change.quoted == "*top-card*":
        return [grant_ability(text) for text in _top_card_activated_texts(source, context)]
    made = change.make(source, context)
    return [made] if made is not None else []


# -- quoted grants made real --------------------------------------------------


def _pseudo_board(permanents: Sequence[CardState]) -> dict[UUID, Characteristics]:
    return {permanent.id: printed_characteristics(permanent) for permanent in permanents}


def sync_conditional_grant_texts(permanents: Sequence[CardState], context: LayerContext) -> None:
    """Reconcile the quoted abilities conditional statics grant onto
    `CardState.granted_ability_texts` (the list activation and triggering read),
    the way `sync_granted_ability_texts` does for unconditional ones. The
    condition is judged on the printed board here - this runs before the layer
    engine has a board - and again, exactly, by the layer-6 grant itself."""
    grantable: set[str] = set()
    wanted: dict[UUID, set[str]] = {}
    board: dict[UUID, Characteristics] | None = None
    for source in permanents:
        text = source.class_ability_text
        if not text or '"' not in text or "as long as" not in text.lower():
            continue
        legendary = "Legendary" in source.card.type_line
        for sentence in _conditional_sentences(source, legendary):
            parsed = _parse(sentence)
            if parsed is None:
                continue
            quoted = [c.quoted for c in parsed.changes if c.quoted and c.quoted != "*top-card*"]
            if not quoted:
                continue
            grantable.update(quoted)
            if not _gates_hold(parsed, source, context):
                continue
            if board is None:
                board = _pseudo_board(permanents)
            for selector in _selectors(parsed, source, context):
                for permanent in permanents:
                    if selector(board[permanent.id], board):
                        wanted.setdefault(permanent.id, set()).update(quoted)
    if not grantable:
        return
    for permanent in permanents:
        mine = wanted.get(permanent.id, set())
        kept = tuple(
            text
            for text in permanent.granted_ability_texts
            if text not in grantable or text in mine
        )
        updated = kept + tuple(text for text in sorted(mine) if text not in kept)
        if updated != permanent.granted_ability_texts:
            permanent.granted_ability_texts = updated


def _conditional_sentences(source: CardState, legendary: bool) -> list[str]:
    from .parse import _effect_sentences

    return _effect_sentences(
        source.class_ability_text, static_only=True, card_name=source.name, legendary=legendary
    )
