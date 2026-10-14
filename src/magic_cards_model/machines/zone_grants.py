"""EP-01 round 2, task T1: static abilities that reach cards *off* the
battlefield - "Each creature card in your graveyard has unearth {2}{B}."
(Sedris, the Traitor King), "Each land card in your hand has cycling {R}."
(Tectonic Reformation), "Land cards in your graveyard have dredge 2." (The
Necrobloom), "Each creature card in your hand has ninjutsu {2}{U}{B}."
(Satoru Umezawa), "Creature cards you own that aren't on the battlefield have
flash." (Teferi, Mage of Zhalfir), "Creatures you control are every creature
type. The same is true for creature spells you control and creature cards you
own that aren't on the battlefield." (Maskwood Nexus).

CR 604.2 makes these static abilities that create continuous effects; CR
613.1f/613.1d say a keyword- or type-granting effect is a layer 6 / layer 4
effect, and CR 611.3a that it applies "at any given moment to whatever its
text indicates" - so every question below is asked of the board as it stands
when a consumer asks it, never stored. The layer system itself only computes
the battlefield (`Game.characteristics_of`), so this module is the same
question asked of one card in another zone:

- `zone_grant_lines(game, card)`: the keyword lines the battlefield grants
  `card` right now ("Unearth {2}{B}", "Cycling {R}", "Dredge 2", "Flash");
- `effective_card(game, card)`: the printing with those lines appended, which
  is what every keyword reader (`keyword_abilities`, `unearth_abilities`,
  `cycling_abilities`, `dredge_count`, ...) already takes - so a granted
  keyword goes through exactly the machine a printed one does and no keyword
  gets a second implementation here;
- `zone_characteristic_parts(game, card)`: the layer 4 / layer 5 changes the
  battlefield makes to the card (`Game.characteristics_of` applies them).

A source's subject is read by `group_grants.parse_group` - the same grammar
the battlefield statics use - with a zone phrase in front of it.
"""

from __future__ import annotations

import functools
import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..models.card import Card, Color
from ..models.card_state import CardState
from ..models.zone import Zone

if TYPE_CHECKING:
    from ..models.game import Game

#: Cheap lowercase gate: every sentence this module reads names one of these.
_GATES = (
    " in your hand",
    " in each player's hand",
    " in your graveyard",
    " in each graveyard",
    "aren't on the battlefield",
    "the same is true for",
    "spells you control and",
    "spells you cast have",
    "spells you control have",
)

_ZONE_PHRASES: dict[str, tuple[frozenset[Zone], str]] = {
    "in your hand": (frozenset({Zone.HAND}), "you"),
    "in each player's hand": (frozenset({Zone.HAND}), "each"),
    "in your graveyard": (frozenset({Zone.GRAVEYARD}), "you"),
    "in each graveyard": (frozenset({Zone.GRAVEYARD}), "each"),
    "in all graveyards": (frozenset({Zone.GRAVEYARD}), "each"),
    "you own that aren't on the battlefield": (
        frozenset({Zone.HAND, Zone.GRAVEYARD, Zone.EXILE, Zone.LIBRARY, Zone.COMMAND, Zone.STACK}),
        "you",
    ),
    "that aren't on the battlefield": (
        frozenset({Zone.HAND, Zone.GRAVEYARD, Zone.EXILE, Zone.LIBRARY, Zone.COMMAND, Zone.STACK}),
        "each",
    ),
}

_SUBJECT_RE = re.compile(
    r"^(?:each |all )?(?P<quality>.*?)\s*\b(?P<noun>cards?|spells?)\b\s*(?P<where>"
    + "|".join(re.escape(phrase) for phrase in sorted(_ZONE_PHRASES, key=len, reverse=True))
    + r"|you control|you cast)?(?P<tail>(?: that's exactly (?:one|two|three|four|five) colors?"
    r"| that's one or more colors)?)$"
)
_SAME_TRUE_RE = re.compile(r"^the same is true for (?P<subjects>.+)$")
_PREDICATE_RE = re.compile(r"^(?P<subject>.+?) (?P<verb>has|have|are|is) (?P<predicate>.+)$")

_COLOR_WORDS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

#: The keywords a card in a hand or graveyard can be granted, each executed by
#: a machine that reads the granted line exactly as it reads a printed one.
ZONE_GRANTABLE_KEYWORDS = frozenset(
    {
        "unearth",
        "outlast",
        "ninjutsu",
        "cycling",
        "dredge",
        "flash",
        "jump-start",
        "convoke",
        "rebound",
        "ripple",
        "freerunning",
        "web-slinging",
        "affinity",
        "equip",
        "crew",
    }
)
_KEYWORD_ITEM_RE = re.compile(
    r"^(?P<keyword>[a-z]+(?:-[a-z]+)?)"
    r"(?: (?P<arg>(?:[a-z]+ )*(?:\{[^{}]+\})+|\d+|for [a-z ]+))?$"
)


def _keyword_line(item: str) -> str | None:
    match = _KEYWORD_ITEM_RE.fullmatch(item.strip())
    if match is None:
        return None
    keyword = match["keyword"]
    if keyword not in ZONE_GRANTABLE_KEYWORDS and not _is_cycling(keyword):
        return None
    line = keyword.capitalize()
    arg = match["arg"]
    if not arg:
        return line
    if arg[0] == "{":
        return f"{line} {arg.upper()}"
    if "{" in arg:
        # "equip Knight {0}": a quality word before the cost (CR 702.6a).
        return f"{line} " + " ".join(
            w.upper() if w[0] == "{" else w.capitalize() for w in arg.split()
        )
    return f"{line} {arg}"


def _is_cycling(keyword: str) -> bool:
    return keyword.endswith("cycling")


@dataclass(frozen=True)
class ZoneSubject:
    """Which cards (or spells) a sentence reaches."""

    noun: str
    """`"card"` or `"spell"`."""
    zones: frozenset[Zone]
    whose: str
    """`"you"` (owner is the source's controller for cards, caster for spells)
    or `"each"`."""
    quality: tuple[tuple[str, Any], ...]
    """The `parse_group` fields (frozen as items), `scope` ignored."""
    colors_exactly: int | None = None
    colored: bool = False

    def matches(self, source: CardState, card: CardState) -> bool:
        if self.noun == "spell":
            if card.zone is not Zone.STACK:
                return False
            if self.whose == "you" and card.controller != source.controller:
                return False
        else:
            if card.zone not in self.zones:
                return False
            if self.whose == "you" and card.owner != source.controller:
                return False
        return self._quality_matches(source, card)

    def _quality_matches(self, source: CardState, card: CardState) -> bool:
        from .layers.group_grants import group_selector
        from .layers.model import printed_characteristics

        chars = printed_characteristics(card)
        if self.colors_exactly is not None and len(chars.colors) != self.colors_exactly:
            return False
        if self.colored and not chars.colors:
            return False
        selector = group_selector({**dict(self.quality), "scope": "any"}, source)
        return bool(selector(chars, {}))


@dataclass(frozen=True)
class ZoneGrant:
    subject: ZoneSubject
    lines: tuple[str, ...] = ()
    """Keyword lines granted."""
    parts: tuple[str, ...] = ()
    """Characteristic changes: `"every_creature_type"`, `"chosen_type"`,
    `"color:white"`, `"colorless"`, `"subtype:Island"`, `"type:artifact"`."""


def _subject(text: str) -> ZoneSubject | None:
    from .layers.group_grants import parse_group

    lowered = text.strip().lower()
    match = _SUBJECT_RE.fullmatch(lowered)
    if match is None:
        return None
    where = match["where"]
    noun = "spell" if match["noun"].startswith("spell") else "card"
    if noun == "card":
        if where is None or where in ("you control", "you cast"):
            return None
        zones, whose = _ZONE_PHRASES[where]
    else:
        zones, whose = frozenset({Zone.STACK}), ("you" if where else "each")
    colors_exactly, colored = None, False
    tail = match["tail"].strip()
    if tail:
        count = re.search(r"exactly (\w+) colors?", tail)
        if count:
            colors_exactly = _NUMBER_WORDS[count[1]]
        else:
            colored = True
    quality = match["quality"].strip()
    fields: dict[str, Any]
    if quality:
        read = parse_group(quality)
        if read is None:
            return None
        fields = dict(read)
    else:
        read = parse_group("permanents")
        if read is None:
            return None
        fields = dict(read)
    fields.pop("scope", None)
    if fields.get("other"):
        return None
    return ZoneSubject(
        noun=noun,
        zones=zones,
        whose=whose,
        quality=tuple(sorted(fields.items(), key=lambda item: item[0])),
        colors_exactly=colors_exactly,
        colored=colored,
    )


def _split_items(text: str) -> list[str]:
    return [part for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", text.strip()) if part]


def _predicate(verb: str, predicate: str) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """`(keyword lines, characteristic parts)` for the predicate of a sentence."""
    predicate = predicate.strip().rstrip(".")
    if verb in ("has", "have"):
        lines = []
        for item in _split_items(predicate):
            line = _keyword_line(item)
            if line is None:
                return None
            lines.append(line)
        return tuple(lines), ()
    cleaned = re.sub(r" in addition to (?:their|its) other (?:creature )?types$", "", predicate)
    if cleaned in ("every creature type", "all creature types"):
        return (), ("every_creature_type",)
    if cleaned == "the chosen type":
        return (), ("chosen_type",)
    if cleaned == "permanents":
        return (), ()
    if cleaned == "colorless":
        return (), ("colorless",)
    if cleaned in _COLOR_WORDS:
        return (), (f"color:{cleaned}",)
    return None


@functools.cache
def parse_zone_line(line: str) -> tuple[ZoneGrant, ...]:
    """Every grant a static line makes to cards off the battlefield; empty when
    the line makes none (fail closed, never a guessed group)."""
    lowered = line.strip().lower()
    if not any(gate in lowered for gate in _GATES):
        return ()
    sentences = [s.strip() for s in re.split(r"(?<=\.)\s+", lowered) if s.strip()]
    grants: list[ZoneGrant] = []
    previous: tuple[tuple[str, ...], tuple[str, ...]] | None = None
    for sentence in sentences:
        text = sentence.rstrip(".")
        same = _SAME_TRUE_RE.fullmatch(text)
        if same is not None:
            if previous is None:
                return ()
            subjects = [_subject(item) for item in _split_subjects(same["subjects"])]
            if not subjects or any(subject is None for subject in subjects):
                return ()
            grants.extend(
                ZoneGrant(subject, previous[0], previous[1])
                for subject in subjects
                if subject is not None
            )
            continue
        found = _PREDICATE_RE.fullmatch(text)
        if found is None:
            previous = None
            continue
        predicate = _predicate(found["verb"], found["predicate"])
        if predicate is None:
            previous = None
            continue
        previous = predicate
        subjects = [_subject(item) for item in _split_subjects(found["subject"])]
        if all(subject is not None for subject in subjects) and subjects:
            grants.extend(
                ZoneGrant(subject, predicate[0], predicate[1])
                for subject in subjects
                if subject is not None
            )
        elif found["verb"] in ("has", "have") and len(subjects) == 1 and subjects[0] is None:
            continue
    return tuple(grants)


_NOUN_RE = re.compile(r"\b(?:cards?|spells?)\b")


def _split_subjects(text: str) -> list[str]:
    """ "cards that aren't on the battlefield, spells, and permanents" and
    "creature spells you control and creature cards you own that aren't on the
    battlefield" as separate subjects, but "instant and sorcery cards in your
    graveyard" as one."""
    parts: list[str] = []
    for piece in re.split(r",\s*(?:and\s+)?|\s+and\s+", text.strip()):
        # A piece with no "card"/"spell" noun is the front of a type list
        # ("instant" in "instant and sorcery card in your graveyard"): it joins
        # the piece after it rather than standing as a subject of its own.
        if parts and not _NOUN_RE.search(parts[-1]) and _NOUN_RE.search(piece):
            parts[-1] = f"{parts[-1]} and {piece}"
        else:
            parts.append(piece)
    items = [re.sub(r"^(?:and|all|each)\s+", "", part.strip()) for part in parts if part]
    # A bare "permanents" is the battlefield half of the sentence
    # (`layers/group_grants._battlefield_part`), not an off-battlefield group.
    return [item for item in items if item not in ("permanents", "permanent")]


def line_grants_off_zone(line: str) -> bool:
    """Whether `line` is a static ability this module reads (asked by
    `static_audit/anthems_grants`)."""
    return bool(parse_zone_line(line))


@functools.cache
def _printing_has_zone_grant(oracle_text: str) -> bool:
    return any(parse_zone_line(line) for line in oracle_text.splitlines())


def _sources(game: Game) -> list[CardState]:
    return [
        permanent
        for permanent in game.battlefield
        if _printing_has_zone_grant(permanent.card.oracle_text or "")
    ]


def _grants_for(game: Game, card: CardState) -> list[tuple[CardState, ZoneGrant]]:
    sources = _sources(game)
    if not sources:
        return []
    board = game.computed_board()
    found: list[tuple[CardState, ZoneGrant]] = []
    for source in sources:
        for line in board.of(source).abilities:
            for grant in parse_zone_line(line):
                if grant.subject.matches(source, card):
                    found.append((source, grant))
    return found


def zone_grant_lines(game: Game | None, card: CardState) -> tuple[str, ...]:
    """The keyword lines the battlefield grants `card` while it is off the
    battlefield (CR 613.1f), in battlefield order."""
    if game is None:
        return ()
    if card.zone is Zone.BATTLEFIELD:
        return _battlefield_granted_lines(game, card)
    return (
        *(line for _source, grant in _grants_for(game, card) for line in grant.lines),
        *_resolution_granted_lines(game, card),
    )


def _resolution_granted_lines(game: Game, card: CardState) -> tuple[str, ...]:
    """The keyword lines a resolved effect handed this one object with a
    duration - Cursecloth Wrappings' "Target creature card in your graveyard gains
    embalm until end of turn." (CR 611.2, CR 613.1f). The store keeps them as
    layer 6 grants selecting the object's incarnation (CR 400.7); the layer engine
    only computes the battlefield, so this reads them for an object elsewhere and
    the duration ends them (CR 514.2)."""
    from .layers.model import printed_characteristics

    effects = [
        effect
        for effect in game.continuous_effects.effects
        if effect.modification.kind == "grant_ability"
    ]
    if not effects:
        return ()
    chars = printed_characteristics(card)
    return tuple(effect.modification.text for effect in effects if effect.selector(chars, {}))


def _battlefield_granted_lines(game: Game, card: CardState) -> tuple[str, ...]:
    """The keyword lines layer 6 added to a permanent beyond its printed ones
    (CR 613.1f) - what "Other Sliver creatures you control have outlast {2}"
    gives a Sliver, for the keyword readers that take a printing."""
    from .layers.model import printed_characteristics

    printed = list(printed_characteristics(card).abilities)
    extras: list[str] = []
    for line in game.computed_board().of(card).abilities:
        if line in printed:
            printed.remove(line)
        elif _keyword_line(line.lower()) is not None:
            extras.append(line)
    return tuple(extras)


def granted_instance_count(game: Game, card: CardState, keyword: str) -> int:
    """How many instances of `keyword` the battlefield's group grants give
    `card` as it would enter the battlefield (CR 614.12: a permanent's
    replacement effects see the characteristics it would have there), e.g.
    "Other Spiders you control have riot" for a Spider entering under the
    grant's controller."""
    from .layers.model import printed_characteristics
    from .layers.registry import effects_for

    chars = printed_characteristics(card).with_(controller=card.controller or card.owner)
    count = 0
    for source in game.battlefield:
        if keyword not in (source.card.oracle_text or "").lower() or source.id == card.id:
            continue
        for effect in effects_for(source, 0, static_only=True):
            modification = effect.modification
            if (
                modification.kind in ("grant_ability", "grant_ability_instance")
                and modification.text.lower() == keyword
                and effect.selector(chars, {})
            ):
                count += 1
    return count


_EFFECTIVE: dict[tuple[Any, ...], Card] = {}


def effective_card(game: Game | None, card: CardState) -> Card:
    """`card.card` with the keyword lines the battlefield grants it appended -
    the printing every keyword reader takes."""
    lines = zone_grant_lines(game, card)
    if not lines:
        return card.card
    key = (card.card.id, lines)
    cached = _EFFECTIVE.get(key)
    if cached is None:
        keywords = list(card.card.keywords)
        for line in lines:
            word = re.split(r" (?=[{\d])| for ", line)[0]
            if word not in keywords:
                keywords.append(word)
        cached = card.card.model_copy(
            update={
                # `parse_abilities` memoises on `Card.id`, so the printing
                # that carries extra lines must not share the printed id.
                "id": uuid.uuid5(card.card.id, "|".join(lines)),
                "oracle_text": "\n".join([card.card.oracle_text or "", *lines]).strip(),
                "keywords": keywords,
            }
        )
        _EFFECTIVE[key] = cached
    return cached


def zone_characteristic_parts(game: Game | None, card: CardState) -> list[tuple[CardState, str]]:
    """`(source, part)` for every layer 4 / layer 5 change the battlefield makes
    to `card` while it is off the battlefield (see `ZoneGrant.parts`)."""
    if game is None or card.zone is Zone.BATTLEFIELD:
        return []
    return [(source, part) for source, grant in _grants_for(game, card) for part in grant.parts]


def apply_zone_characteristics(game: Game | None, card: CardState, chars: Any) -> Any:
    """`chars` (an off-battlefield object's printed characteristics) with the
    battlefield's layer 4 then layer 5 changes applied (CR 613.1d, 613.1e)."""
    from .layers.model import (
        AddEveryCreatureType,
        SetColors,
        SetCreatureTypes,
        add_subtype,
    )

    parts = zone_characteristic_parts(game, card)
    if not parts:
        return chars
    from .layers.parse import chosen_creature_type_of

    board: dict[Any, Any] = {}
    for source, part in parts:
        if part == "every_creature_type":
            chars = AddEveryCreatureType()(chars, board)
        elif part == "chosen_type":
            chosen = chosen_creature_type_of(source)
            if chosen is not None:
                chars = SetCreatureTypes(subtypes=(chosen.title(),))(chars, board)
        elif part.startswith("subtype:"):
            chars = add_subtype(part.split(":", 1)[1])(chars, board)
    for _source, part in parts:
        if part == "colorless":
            chars = SetColors(colors=())(chars, board)
        elif part.startswith("color:"):
            chars = SetColors(colors=(_COLOR_WORDS[part.split(":", 1)[1]],))(chars, board)
    return chars


def _quality_fields(quality: str) -> dict[str, Any] | None:
    from .layers.group_grants import parse_group

    read = parse_group(quality)
    if read is None or read["other"] or read["chosen"]:
        return None
    return {key: value for key, value in read.items() if key not in ("scope", "other", "chosen")}


def group_quality_is_readable(quality: str) -> bool:
    """Whether the group grammar reads a spell quality ("artifact creature",
    "legendary", "nonland") that `next_spell`'s closed one does not."""
    return _quality_fields(quality) is not None


def group_quality_matches(state: CardState, quality: str) -> bool:
    """Whether `state` (a spell) has `quality` under the group grammar, asked of
    its printed characteristics (CR 109.3)."""
    from .layers.model import GroupMatch, printed_characteristics

    fields = _quality_fields(quality)
    if fields is None:
        return False
    return bool(GroupMatch(scope="any", **fields)(printed_characteristics(state), {}))
