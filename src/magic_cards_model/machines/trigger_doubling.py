"""CR 603.2d trigger multipliers beyond Panharmonicon's entering cause, and the
statics that stop an event from causing triggers.

`machines/triggers/collect.additional_trigger_times` reads the "entering" cause
and the plain "of a <Subtype> you control" shapes; this module reads the rest of
the family, off each permanent's computed ability lines (CR 613.5):

- Cause shapes: "If a creature dying causes a triggered ability of a permanent
  you control to trigger, that ability triggers an additional time." (Teysa
  Karlov, Drivnod), "... a creature attacking ..." (Isshin), "... a legendary
  permanent or an artifact entering or leaving the battlefield ..." (Gandalf the
  White). "Dying" is one event; "leaving the battlefield" is every way out.
- Source shapes with a stat or colour qualifier: "If a triggered ability of a
  creature you control with power 2 or less triggers, ..." (Delney), "... of a
  colorless spell you control or another colorless permanent you control ..."
  (Echoes of Eternity: a spell's cast trigger counts), and a count gate "...
  of another Shrine you control triggers while you control six or more Shrines,
  ..." (Sanctum of All).
- "Room abilities of dungeons you own trigger an additional time." (Hama Pashar):
  `room_ability_times`.
- "Creatures entering or dying don't cause abilities to trigger." (Hushbringer):
  `without_suppressed` drops what the event would have caused.

A delayed or reflexive trigger is never multiplied (CR 603.2d): only what
`triggers_for` builds from a printed ability reaches here.
"""

import re
from functools import cache
from typing import TYPE_CHECKING, NamedTuple

from ..data.subtypes import subtype_vocabulary
from ..models.card import Color, Supertype, Type
from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import parse_count
from .abilities import TriggerEvent

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers.events import AbilityOnStack, GameEvent

_CAUSE_RE = re.compile(
    r"^if an? (?P<what>.+?) (?P<verb>entering or leaving the battlefield|entering the battlefield "
    r"or leaving the battlefield|entering|dying|attacking|leaving the battlefield) causes a "
    r"triggered ability of a permanent you control to trigger, that ability triggers an "
    r"additional time\.?$",
    re.IGNORECASE,
)
_WHOSE_RE = re.compile(
    r"^if a triggered ability of (?P<whose>.+?) triggers(?: while (?P<gate>.+?))?, "
    r"(?:that ability|it) triggers an additional time\.?$",
    re.IGNORECASE,
)
_ALTERNATIVE_RE = re.compile(
    r"^(?P<article>an?|another) (?P<words>[a-z]+(?: [a-z]+)*?) you control"
    r"(?: with (?P<stat>power|toughness) (?P<n>\d+) or (?P<cmp>less|greater))?$",
    re.IGNORECASE,
)
_GATE_RE = re.compile(r"^you control (?P<n>\w+) or more (?P<kind>[a-z]+)s$", re.IGNORECASE)
_ROOM_RE = re.compile(
    r"^room abilities of dungeons you own trigger an additional time\.?$", re.IGNORECASE
)
_SUPPRESS_RE = re.compile(
    r"^(?P<types>[a-z]+(?:, [a-z]+)*(?: and [a-z]+)?) (?P<verb>entering or dying|dying or entering|"
    r"dying|entering) don'?t cause abilities to trigger\.?$",
    re.IGNORECASE,
)

_LEAVING = frozenset(
    {
        TriggerEvent.DIES,
        TriggerEvent.LEAVES_THE_BATTLEFIELD,
        TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND,
        TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
    }
)
_VERB_EVENTS = {
    "entering": frozenset({TriggerEvent.ENTERS_THE_BATTLEFIELD}),
    "dying": frozenset({TriggerEvent.DIES}),
    "attacking": frozenset({TriggerEvent.ATTACKS}),
    "leaving the battlefield": _LEAVING,
    "entering or leaving the battlefield": _LEAVING | {TriggerEvent.ENTERS_THE_BATTLEFIELD},
    "entering the battlefield or leaving the battlefield": _LEAVING
    | {TriggerEvent.ENTERS_THE_BATTLEFIELD},
    "entering or dying": frozenset({TriggerEvent.ENTERS_THE_BATTLEFIELD, TriggerEvent.DIES}),
    "dying or entering": frozenset({TriggerEvent.ENTERS_THE_BATTLEFIELD, TriggerEvent.DIES}),
}
_COLORS = {c.value.lower(): c for c in Color} | {c.name.lower(): c for c in Color}


class Qualifier(NamedTuple):
    """One "a/another <words> you control [with power N or less]" alternative."""

    another: bool
    words: tuple[str, ...]
    stat: str | None
    bound: int
    at_most: bool


class Traits(NamedTuple):
    words: frozenset[str]
    power: int
    toughness: int
    is_spell: bool


@cache
def _vocabulary() -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    return (
        frozenset(t.value.lower() for t in Type),
        frozenset(s.value.lower() for s in Supertype),
        frozenset(s.lower() for s in subtype_vocabulary()),
    )


def _word_ok(word: str) -> bool:
    types, supertypes, subtypes = _vocabulary()
    return (
        word in types
        or word in supertypes
        or word in subtypes
        or word in ("permanent", "spell", "colorless", "token", "nontoken")
        or word in _COLORS
    )


@cache
def _cause(line: str) -> tuple[tuple[tuple[str, ...], ...], frozenset[TriggerEvent]] | None:
    match = _CAUSE_RE.match(" ".join(line.split()))
    if match is None:
        return None
    alternatives = []
    for part in re.split(r",\s*(?:or\s+)?|\s+or\s+an?\s+", match["what"].strip().lower()):
        words = tuple(part.removeprefix("a ").removeprefix("an ").split())
        if not words or not all(_word_ok(w) for w in words):
            return None
        alternatives.append(words)
    return tuple(alternatives), _VERB_EVENTS[match["verb"].lower()]


@cache
def _whose(line: str) -> tuple[tuple[Qualifier, ...], str | None, int] | None:
    match = _WHOSE_RE.match(" ".join(line.split()))
    if match is None:
        return None
    qualifiers = []
    for part in re.split(r",\s*(?:or\s+)?|\s+or\s+(?=an?\s|another\s)", match["whose"].strip()):
        alt = _ALTERNATIVE_RE.match(part.strip())
        if alt is None:
            return None
        words = tuple(alt["words"].lower().split())
        if not all(_word_ok(w) for w in words):
            return None
        qualifiers.append(
            Qualifier(
                alt["article"].lower() == "another",
                words,
                alt["stat"],
                int(alt["n"]) if alt["n"] else 0,
                (alt["cmp"] or "").lower() == "less",
            )
        )
    gate_kind, gate_n = None, 0
    if match["gate"]:
        gate = _GATE_RE.match(match["gate"].strip())
        count = parse_count(gate["n"], article=False) if gate else None
        if gate is None or count is None:
            return None
        gate_kind, gate_n = gate["kind"].lower(), count
    return tuple(qualifiers), gate_kind, gate_n


def reads_trigger_doubling_line(text: str) -> bool:
    """Whether `text` is a line this module performs."""
    lowered = text.lower()
    if "additional time" in lowered:
        line = " ".join(text.split())
        return (
            _cause(line) is not None or _whose(line) is not None or _ROOM_RE.match(line) is not None
        )
    return "cause abilities to trigger" in lowered and _suppress(" ".join(text.split())) is not None


@cache
def _suppress(line: str) -> tuple[tuple[str, ...], frozenset[TriggerEvent]] | None:
    match = _SUPPRESS_RE.match(line)
    if match is None:
        return None
    nouns = [n.strip() for n in re.split(r",\s*|\s+and\s+", match["types"].lower()) if n.strip()]
    singular = tuple(n[:-1] if n.endswith("s") else n for n in nouns)
    if not all(_word_ok(w) for w in singular):
        return None
    return singular, _VERB_EVENTS[match["verb"].lower()]


def _traits(game: "Game", obj: CardState) -> Traits:
    try:
        chars = game.characteristics_of(obj)
        types, subtypes = chars.types, chars.subtypes
        supertypes, colors = chars.supertypes, getattr(chars, "colors", obj.card.colors)
        power, toughness = chars.numeric_power, chars.numeric_toughness
    except KeyError:
        types, subtypes, supertypes = obj.types, obj.subtypes, obj.card.supertypes
        colors, power, toughness = obj.card.colors, obj.power or 0, obj.toughness or 0
    words = {t.value.lower() for t in types} | {s.lower() for s in subtypes}
    words |= {s.value.lower() for s in supertypes}
    words |= {c.value.lower() for c in colors} | {c.name.lower() for c in colors}
    if not colors:
        words.add("colorless")
    words.add("token" if obj.card.layout.value == "token" else "nontoken")
    return Traits(frozenset(words), power, toughness, obj.zone is Zone.STACK)


def _event_traits(game: "Game", event: "GameEvent") -> Traits | None:
    subject = game.find_by_id(event.subject_id) if event.subject_id is not None else None
    if isinstance(subject, CardState):
        base = _traits(game, subject)
        words = set(base.words)
        if event.subject_types is not None:
            words |= {t.value.lower() for t in event.subject_types}
        if event.subject_subtypes is not None:
            words |= {s.lower() for s in event.subject_subtypes}
        return Traits(frozenset(words | {"permanent"}), base.power, base.toughness, False)
    if event.subject_card is not None:
        card = event.subject_card
        words = {t.value.lower() for t in card.types} | {s.lower() for s in card.subtypes}
        words |= {s.value.lower() for s in card.supertypes} | {"permanent"}
        return Traits(frozenset(words), 0, 0, False)
    return None


def _matches(qualifier: Qualifier, traits: Traits, *, multiplier_id, source_id) -> bool:
    if qualifier.another and source_id == multiplier_id:
        return False
    words = set(qualifier.words)
    if "spell" in words:
        if not traits.is_spell:
            return False
        words.discard("spell")
    elif traits.is_spell:
        return False
    words.discard("permanent")
    if not words <= traits.words:
        return False
    if qualifier.stat is None:
        return True
    value = traits.power if qualifier.stat == "power" else traits.toughness
    return value <= qualifier.bound if qualifier.at_most else value >= qualifier.bound


def _lines(game: "Game", permanent: CardState) -> tuple[str, ...]:
    from .triggers.collect import _computed_ability_lines

    return _computed_ability_lines(game, permanent)


def extra_trigger_times(
    game: "Game", ability: "AbilityOnStack", source: CardState, event: "GameEvent"
) -> int:
    """Extra times `ability` triggers by the shapes above (CR 603.2d)."""
    from .triggers.collect import is_additional_trigger_line

    extra = 0
    source_traits: Traits | None = None
    event_traits: Traits | None = None
    for permanent in list(game.battlefield):
        controller = permanent.controller
        if controller is None or controller != ability.controller:
            continue
        for printed in _lines(game, permanent):
            if "additional time" not in printed.lower() or is_additional_trigger_line(printed):
                continue
            line = " ".join(printed.split())
            if (cause := _cause(line)) is not None:
                alternatives, events = cause
                if event.event not in events:
                    continue
                if event.event not in _LEAVING and source.zone is not Zone.BATTLEFIELD:
                    continue
                event_traits = event_traits or _event_traits(game, event)
                if event_traits is not None and any(
                    set(words) - {"permanent"} <= event_traits.words for words in alternatives
                ):
                    extra += 1
            elif (whose := _whose(line)) is not None:
                qualifiers, gate_kind, gate_n = whose
                # CR 603.10a: a leaves-the-battlefield ability looks back at the
                # permanent it was on, which is already in another zone.
                looked_back = event.event in _LEAVING and event.subject_id == source.id
                if source.zone not in (Zone.BATTLEFIELD, Zone.STACK) and not looked_back:
                    continue
                if gate_kind is not None and (
                    sum(
                        1
                        for p in game.permanents_controlled_by(controller)
                        if gate_kind in _traits(game, p).words
                    )
                    < gate_n
                ):
                    continue
                source_traits = source_traits or _traits(game, source)
                if any(
                    _matches(q, source_traits, multiplier_id=permanent.id, source_id=source.id)
                    for q in qualifiers
                ):
                    extra += 1
    return extra


def room_ability_times(game: "Game", player: str) -> int:
    """How many times a room ability of a dungeon `player` owns triggers."""
    return 1 + sum(
        1
        for permanent in game.permanents_controlled_by(player)
        for line in _lines(game, permanent)
        if "room abilities" in line.lower() and _ROOM_RE.match(" ".join(line.split()))
    )


def without_suppressed(
    game: "Game", event: "GameEvent", triggered: "list[AbilityOnStack]"
) -> "list[AbilityOnStack]":
    """`triggered` less what a "<things> entering or dying don't cause abilities
    to trigger" static stops (CR 603.2): the whole batch, whoever controls it."""
    if not triggered or event.event not in (TriggerEvent.ENTERS_THE_BATTLEFIELD, TriggerEvent.DIES):
        return triggered
    traits: Traits | None = None
    for permanent in game.battlefield:
        for printed in _lines(game, permanent):
            if "cause abilities" not in printed.lower():
                continue
            read = _suppress(" ".join(printed.split()))
            if read is None or event.event not in read[1]:
                continue
            traits = traits or _event_traits(game, event)
            if traits is not None and any(w in traits.words for w in read[0]):
                return []
    return triggered
