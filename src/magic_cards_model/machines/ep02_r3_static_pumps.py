"""EP-02 R3 T1: static "gets +N/+N for each <thing>" and "power and toughness
each equal to <count>" readers (CR 613.4c, CR 613.4b, CR 604.3).

One reader, many subjects and counts. A permanent's own static ability sizes a
sublayer 7c pump (CR 613.4c) or a base P/T (CR 613.4b) by a count of something
on the board, and the layer engine recomputes it on every computation (CR 613.5,
CR 611.3a). The subject is the shared group reader (`layers.group_grants`) plus
the self / enchanted-creature words; the count is the existing character-
defining-ability count reader (`parse._cda_base_count`) first, then the
phrases it does not know:

- "Equipment attached to this creature / to it", "Aura and Equipment attached to
  Kellan" (CR 301.5, CR 303.4): the attachments of the source or of whichever
  creature the pump lands on.
- "other creature on the battlefield that shares at least one creature type
  with it" (CR 205.3m), "untapped permanent your opponents control"
  (CR 110.5), "transformed permanent you control" (CR 701.27), "snow permanent
  you control" (CR 205.4), "modified creature you control" (CR 700.9), "land you
  control but don't own" (CR 108.3), "Aura you control that's attached to a
  creature": `CountBoardWhere`'s qualifiers.
- "of its colors / creature types", "point of bushido it has", "white mana
  symbol in its mana cost", "time it has attacked this turn", "card exiled with
  it", "color among the exiled cards used to craft it": a number read off the
  pumped creature or off the source's own record.

`parse_static_pump` is tried last by `layers.parse._parse_layer_sentence`, so
every shape an older reader owns keeps its reading.
"""

import functools
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from magic_cards_model.text_norm import collapsed

from ..data.subtypes import subtype_vocabulary
from ..models.card import Color, Supertype, Type
from ..models.card_state import CardState

if TYPE_CHECKING:
    from .layers.apply import EffectBuilder, LayerContext
    from .layers.model import Count

CountFactory = "Callable[[CardState, LayerContext, bool], Count | None]"

_SELF_WORDS = {
    "this creature",
    "this permanent",
    "this artifact",
    "this enchantment",
    "this land",
    "this token",
    "it",
}
_THIS_AND_ENCHANTED = {
    "this creature and enchanted creature",
    "this permanent and enchanted creature",
    "this creature and enchanted permanent",
}

_PUMP_RE = re.compile(
    r"^(?P<subject>.+?)(?: each)? gets? (?P<rest>[+-]\d+/[+-]\d+ for each .+?)\.?$",
    re.IGNORECASE,
)
_CLAUSE_SPLIT_RE = re.compile(r" and (?=[+-]\d+/[+-]\d+ for each )", re.IGNORECASE)
_CLAUSE_RE = re.compile(
    r"^(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) for each (?P<each>.+?)"
    r"(?:, to a maximum of (?P<cap>\d+))?$",
    re.IGNORECASE,
)
_BASE_PT_RE = re.compile(
    r"^(?P<subject>.+?) (?:have|has) base power and toughness each equal to "
    r"(?P<count>the number of .+?)\.?$",
    re.IGNORECASE,
)
_CRAFT_PT_RE = re.compile(
    r"^(?P<subject>.+?)'s power and toughness are each equal to "
    r"the number of colors among the exiled cards used to craft it\.?$",
    re.IGNORECASE,
)
_ARTIFACT_CREATURE_RE = re.compile(
    r"^each (?P<group>noncreature artifact) is an artifact creature with power and "
    r"toughness each equal to its mana value\.?$",
    re.IGNORECASE,
)

# -- counts -------------------------------------------------------------------

_SELF_HOSTS = {"it", "him", "her", "them"}
_COLOR_WORD = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}
_MANA_SYMBOL_RE = re.compile(
    r"^(?P<color>white|blue|black|red|green) mana symbol in its mana cost$"
)
_UNSPENT_MANA_RE = re.compile(
    r"^unspent (?P<color>white|blue|black|red|green) mana you have$", re.IGNORECASE
)
_BOARD_RE = re.compile(
    r"^(?P<other>other )?(?P<adjectives>(?:(?:untapped|tapped|transformed|modified|snow) )*)"
    r"(?P<noun>[a-z]+)"
    r"(?: (?P<scope>you control|your opponents control|on the battlefield))?"
    r"(?P<tail>(?: but don't own| that's attached to a creature"
    r"| that shares (?:at least one|a) creature type with it))?$"
)
_TYPE_NOUNS = {
    "creature": Type.CREATURE,
    "artifact": Type.ARTIFACT,
    "enchantment": Type.ENCHANTMENT,
    "land": Type.LAND,
    "planeswalker": Type.PLANESWALKER,
    "battle": Type.BATTLE,
}


def _singular(word: str) -> str:
    return word[:-1] if word.endswith("s") else word


def _board_count(each: str, source: CardState) -> "Count | None":
    match = _BOARD_RE.fullmatch(each)
    if match is None:
        return None

    from .layers.model import CountBoardWhere

    noun = _singular(match["noun"])
    fields: dict[str, Any] = {}
    adjectives = match["adjectives"].split()
    if "untapped" in adjectives:
        fields["tapped"] = False
    if "tapped" in adjectives:
        fields["tapped"] = True
    if "transformed" in adjectives:
        fields["transformed"] = True
    if "modified" in adjectives:
        fields["modified"] = True
    if "snow" in adjectives:
        fields["supertype"] = Supertype.SNOW
    if noun in _TYPE_NOUNS:
        fields["types_any"] = (_TYPE_NOUNS[noun],)
    elif noun == "permanent":
        pass
    elif noun in subtype_vocabulary():
        fields["subtypes_any"] = (noun,)
    else:
        return None
    scope = match["scope"]
    fields["scope"] = {
        "you control": "you",
        "your opponents control": "opponents",
        "on the battlefield": "any",
        None: "any",
    }[scope]
    if match["tail"]:
        if "don't own" in match["tail"]:
            fields["not_owned_by_controller"] = True
        elif "attached" in match["tail"]:
            fields["attached_to_creature"] = True
        else:
            fields["shares_creature_type"] = True
    return CountBoardWhere(
        username=source.controller,
        exclude_asking=match["other"] is not None,
        **fields,
    )


def _attached_count(text: str, source: CardState) -> "Count | None":
    """ "Aura and Equipment attached to it / to this creature / to <name>"
    (CR 301.5a, CR 303.4): the shared reading of the wording
    (`ep02_r3_for_each_cards.attached_phrase`) as a layer `Count`, live on every
    computation - of the creature the pump lands on for "it", else of the source."""
    from .ep02_r3_for_each_cards import attached_phrase
    from .layers.model import CountAttachedWithAnySubtype

    phrase = attached_phrase(text)
    if phrase is None or phrase.past:
        return None
    return CountAttachedWithAnySubtype(
        subtypes=phrase.subtypes,
        host=None if phrase.host in _SELF_HOSTS else source.id,
    )


def _graveyard_and_board_count(
    each: str, source: CardState, context: "LayerContext"
) -> "Count | None":
    """ "other Assassin you control and each Assassin card in your graveyard"
    (CR 404.1): the board half is live, the graveyard half is read as the
    effect is built."""
    from .layers.model import CountControlledAndGraveyardCards

    match = re.fullmatch(
        r"(?P<other>other )?(?P<q>[a-z]+) you control and each (?P=q) cards? in your graveyard",
        each,
    )
    if match is None:
        return None
    word = _singular(match["q"])
    card_type = _TYPE_NOUNS.get(word)
    subtype = None if card_type is not None else word
    if card_type is None and word not in subtype_vocabulary():
        return None
    return CountControlledAndGraveyardCards(
        username=source.controller,
        card_type=card_type,
        subtype=subtype,
        exclude_asking=match["other"] is not None,
        graveyard_count=sum(
            1
            for card in context.graveyard_of(source.controller)
            if (
                card_type in card.types
                if card_type
                else any(w.lower() == subtype for w in card.subtypes)
            )
        ),
    )


def _zone_count(each: str, source: CardState, context: "LayerContext") -> "Count | None":
    """ "noncreature, nonland card in your graveyard" and the like: the shared
    zone reader, with the comma-separated qualifiers it spells "noncreature
    nonland"."""
    from .ep02_r2_cards_in_zone_counts import static_zone_count

    if " in " not in each:
        return None
    factory = static_zone_count(re.sub(r",\s*", " ", each))
    return None if factory is None else factory(source, context)


def count_for(
    each: str, source: CardState, context: "LayerContext", *, cap: int | None = None
) -> "Count | None":
    """The `Count` a "for each `<each>`" (or "the number of `<each>`") names, for
    `source`'s static ability, or `None` for wording nothing here reads."""
    from .layers.model import (
        CountByObjectId,
        CountOwnCharacteristic,
        CountOwnManaSymbols,
        FixedCount,
    )

    text = collapsed(each.lower().replace("’", "'")).removeprefix("the number of ")
    if text in ("of its colors", "of its color"):
        return CountOwnCharacteristic(measure="colors", cap=cap)
    if text == "of its creature types":
        return CountOwnCharacteristic(measure="creature_types", cap=cap)
    if text == "point of bushido it has":
        return CountOwnCharacteristic(measure="bushido", cap=cap)
    if cap is not None:
        return None
    if (match := _MANA_SYMBOL_RE.fullmatch(text)) is not None:
        return CountOwnManaSymbols(
            colors=(_COLOR_WORD[match["color"]],),
            costs=tuple((card_id, cost) for card_id, cost in context.mana_cost_by_id.items()),
        )
    if (unspent := _UNSPENT_MANA_RE.fullmatch(text)) is not None:
        # "for each unspent green mana you have" (Omnath, Locus of Mana): the
        # controller's floating mana of that colour (CR 106.4), read off the
        # pool at every computation (CR 613.5) - "you" is CR 109.5's controller.
        return FixedCount(
            value=context.unspent_mana_of(source.controller, _COLOR_WORD[unspent["color"]])
        )
    if text == "time it has attacked this turn":
        return CountByObjectId(counts=tuple(context.attack_count_by_id.items()))
    if text in ("card exiled with it", "card exiled with this creature"):
        return FixedCount(value=len(context.cards_exiled_with(source)))
    if " attached to " in text and (attached := _attached_count(text, source)) is not None:
        return attached
    if (counted := _graveyard_and_board_count(text, source, context)) is not None:
        return counted
    if (zoned := _zone_count(text, source, context)) is not None:
        return zoned
    if (board := _board_count(text, source)) is not None:
        return board
    from .layers.parse import _cda_base_count

    base = _cda_base_count(f"the number of {text}")
    return None if base is None else base(source, context)


# -- subjects -----------------------------------------------------------------


#: The permanent a pump's Aura or Equipment is attached to (CR 303.4, CR 301.5).
_ATTACHED_SUBJECTS = ("enchanted creature", "enchanted permanent", "equipped creature")


def _is_self(subject: str, source: CardState) -> bool:
    lowered = subject.strip().lower()
    names = {source.name.lower(), source.name.split(",")[0].lower(), source.name.split()[0].lower()}
    return lowered in _SELF_WORDS or lowered in names


def _selectors(subject: str, source: CardState) -> list[Any] | None:
    """The selectors a pump's subject names, `[]` when it names nobody right now
    (an unattached Aura), `None` for a subject nothing here reads."""
    from .layers.group_grants import _subject_selector
    from .layers.model import Only

    lowered = subject.strip().lower()
    if lowered in _THIS_AND_ENCHANTED:
        found: list[Any] = [Only(card_id=source.id)]
        if source.attached_to is not None:
            found.append(Only(card_id=source.attached_to))
        return found
    if _is_self(lowered, source):
        return [Only(card_id=source.id)]
    if lowered in _ATTACHED_SUBJECTS:
        return [] if source.attached_to is None else [Only(card_id=source.attached_to)]
    selector = _subject_selector(subject, source)
    return None if selector is None else [selector]


def _subject_readable(subject: str) -> bool:
    """Whether `subject` reads for any source (build-time probe on a placeholder
    is impossible, so this checks the words)."""
    from .layers.group_grants import _battlefield_part, parse_group

    lowered = subject.strip().lower()
    if lowered in _SELF_WORDS or lowered in _THIS_AND_ENCHANTED:
        return True
    if lowered in _ATTACHED_SUBJECTS:
        return True
    if parse_group(_battlefield_part(subject)) is not None:
        return True
    # A card's own name (one or more capitalised words) is the self subject.
    return bool(re.fullmatch(r"[A-Z][\w'-]*(?:,? [A-Za-z][\w'-]*)*", subject.strip()))


# -- builders -----------------------------------------------------------------


def _effect(source, timestamp, line, selector, layer, sublayer, modification, description, **extra):
    from .layers.model import ContinuousEffect
    from .layers.parse import _source_line_for

    return ContinuousEffect(
        description=f"{source.name}: {description}",
        layer=layer,
        sublayer=sublayer,
        timestamp=timestamp,
        source_id=source.id,
        source_ability=_source_line_for(source, line),
        selector=selector,
        modification=modification,
        **extra,
    )


@functools.cache
def _pump_builder(sentence: str) -> "EffectBuilder | None":
    match = _PUMP_RE.fullmatch(sentence.strip())
    if match is None:
        return None

    from .layers.model import Layer, Sublayer, modify_power_toughness_per

    subject = match["subject"].strip()
    clauses = []
    for piece in _CLAUSE_SPLIT_RE.split(match["rest"]):
        clause = _CLAUSE_RE.fullmatch(piece.strip())
        if clause is None:
            return None
        clauses.append(clause)
    if not _subject_readable(subject):
        return None

    def builder(
        source: CardState, timestamp: int, targets: Sequence[CardState], context: "LayerContext"
    ) -> list:
        selectors = _selectors(subject, source)
        if not selectors:
            return []
        built = []
        for selector in selectors:
            for clause in clauses:
                cap = int(clause["cap"]) if clause["cap"] else None
                count = count_for(clause["each"], source, context, cap=cap)
                if count is None:
                    return []
                power, toughness = int(clause["power"]), int(clause["toughness"])
                built.append(
                    _effect(
                        source,
                        timestamp,
                        sentence,
                        selector,
                        Layer.POWER_TOUGHNESS,
                        Sublayer.MODIFY,
                        modify_power_toughness_per(count, power, toughness),
                        f"{subject} gets {power:+d}/{toughness:+d} for each {clause['each']}",
                    )
                )
        return built

    return builder


@functools.cache
def _base_pt_builder(sentence: str) -> "EffectBuilder | None":
    from .layers.model import Layer, Sublayer, define_power_toughness

    match = _BASE_PT_RE.fullmatch(sentence.strip())
    if match is None or not _subject_readable(match["subject"]):
        return None
    subject, number = match["subject"].strip(), match["count"]

    def builder(
        source: CardState, timestamp: int, targets: Sequence[CardState], context: "LayerContext"
    ) -> list:
        selectors = _selectors(subject, source)
        count = count_for(number, source, context)
        if not selectors or count is None:
            return []
        return [
            _effect(
                source,
                timestamp,
                sentence,
                selector,
                Layer.POWER_TOUGHNESS,
                Sublayer.SET,
                define_power_toughness(count),
                f"{subject} have base power and toughness each equal to {number}",
            )
            for selector in selectors
        ]

    return builder


@functools.cache
def _craft_pt_builder(sentence: str) -> "EffectBuilder | None":
    """CR 702.167c: "the exiled cards used to craft it" are the ones recorded on
    the crafted permanent (`CardState.crafted_with`); a colour counts once
    however many of them have it (CR 105.1)."""
    from .layers.model import FixedCount, Layer, Only, Sublayer, define_power_toughness

    match = _CRAFT_PT_RE.fullmatch(sentence.strip())
    if match is None or not _subject_readable(match["subject"]):
        return None

    def builder(
        source: CardState, timestamp: int, targets: Sequence[CardState], context: "LayerContext"
    ) -> list:
        used = set(source.crafted_with)
        colors = {color for card in context.exile if card.id in used for color in card.colors}
        return [
            _effect(
                source,
                timestamp,
                sentence,
                Only(card_id=source.id),
                Layer.POWER_TOUGHNESS,
                Sublayer.CHARACTERISTIC_DEFINING,
                define_power_toughness(FixedCount(value=len(colors))),
                "power and toughness equal to the colors among the exiled cards used to craft it",
                characteristic_defining=True,
            )
        ]

    return builder


@functools.cache
def _artifact_creature_builder(sentence: str) -> "EffectBuilder | None":
    """ "Each noncreature artifact is an artifact creature with power and
    toughness each equal to its mana value." (CR 613.1d adds the type, CR 613.4b
    sets the P/T from the mana value, CR 202.3): the group is fixed when the
    effect is built, so layer 7b still reaches what layer 4 made a creature
    (CR 613.6)."""
    from .layers.model import (
        GroupMatch,
        Layer,
        PermanentIds,
        Sublayer,
        add_type,
        set_power_toughness_to_mana_value,
    )

    if _ARTIFACT_CREATURE_RE.fullmatch(sentence.strip()) is None:
        return None

    def builder(
        source: CardState, timestamp: int, targets: Sequence[CardState], context: "LayerContext"
    ) -> list:
        game = source._board_source
        ids = tuple(
            sorted(
                (
                    permanent.id
                    for permanent in (() if game is None else game.battlefield)
                    if Type.ARTIFACT in permanent.printed_types
                    and Type.CREATURE not in permanent.printed_types
                ),
                key=str,
            )
        )
        group = GroupMatch(scope="any", all_types=(Type.ARTIFACT,), not_types=(Type.CREATURE,))
        return [
            _effect(
                source,
                timestamp,
                sentence,
                group,
                Layer.TYPE,
                None,
                add_type(Type.CREATURE),
                "noncreature artifacts are artifact creatures",
            ),
            _effect(
                source,
                timestamp,
                sentence,
                PermanentIds(ids=ids),
                Layer.POWER_TOUGHNESS,
                Sublayer.SET,
                set_power_toughness_to_mana_value,
                "their power and toughness equal their mana values",
            ),
        ]

    return builder


@functools.cache
def parse_static_pump(sentence: str) -> "EffectBuilder | None":
    """The builder for one static sentence of this family, or `None`."""
    from .layers.parse import _strip_ability_word

    sentence = _strip_ability_word(sentence)
    lowered = sentence.lower()
    if " for each " in lowered:
        return _pump_builder(sentence)
    if "base power and toughness each equal to the number of" in lowered:
        return _base_pt_builder(sentence)
    if "exiled cards used to craft it" in lowered:
        return _craft_pt_builder(sentence)
    if "is an artifact creature with power and toughness each equal to its mana value" in lowered:
        return _artifact_creature_builder(sentence)
    return None
