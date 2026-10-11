import re
from collections.abc import Callable, Iterable, Sequence
from enum import StrEnum
from functools import lru_cache
from typing import Any, NamedTuple
from uuid import UUID

from pydantic import ConfigDict

from ...models.card import Card, Color, Layout, Type, types_of
from ...models.card_state import CardState
from ...models.mana import ManaCost
from ...models.zone import Zone
from ...numbers import COUNT, parse_count
from ...snapshot import EngineModel
from ..abilities import (
    AbilityKind,
    KeywordAbility,
    parse_abilities,
    parse_granted_ability_lines,
)
from ..cost import (
    TotalCost,
    total_cost_for_phrase,
)
from ..keywords import (
    printed_casualty_numbers,
    printed_conspire_count,
)
from ..layers import (
    ContinuousEffect,
    Layer,
    grant_ability,
    only_this_incarnation,
    plays_lands_from_graveyard_line,
)
from ..spell_grants import casualty_numbers, conspire_count
from ..turn import Step
from .options import KeywordCastOption, OptionalAdditionalCost

#: Detective's Phoenix: "You may cast this card from your graveyard using its
#: bestow ability." A CR 604.6 static ability of the card itself - "some static
#: abilities function while an object is in a zone other than the battlefield"
#: - naming both the zone it opens and the ability it opens it for, so the
#: keyword's own option is reused rather than a second cost invented for it.
_PRINTED_CAST_FROM_ZONE_USING_KEYWORD = re.compile(
    r"you may cast this card from your (?P<zone>graveyard|hand|exile) using its "
    r"(?P<keyword>[a-z]+) ability",
    re.IGNORECASE,
)

#: The zone words that sentence can name, as zones.
_PRINTED_PERMISSION_ZONES = {
    "graveyard": Zone.GRAVEYARD,
    "hand": Zone.HAND,
    "exile": Zone.EXILE,
}


def _printed_zone_permissions(
    card: Card, options: list[KeywordCastOption]
) -> list[KeywordCastOption]:
    """The extra zones a card's own printed text opens for a keyword it has
    (CR 604.6, CR 113.6f).

    One option per sentence and per matching keyword option, copied from the
    keyword's own so the cost, the CR 118.9 replacement and the "could not be
    read" flag are all identical - only the zone differs. That is what the
    printed sentence actually says: it names an ability the card already has
    and a zone to use it from, and not a new way to pay.

    A sentence naming a keyword the card does not have adds nothing, rather
    than inventing an option with no cost behind it.
    """
    text = (card.oracle_text or "").replace("\n", " ")
    extra: list[KeywordCastOption] = []
    for match in _PRINTED_CAST_FROM_ZONE_USING_KEYWORD.finditer(text):
        zone = _PRINTED_PERMISSION_ZONES[match.group("zone").lower()]
        keyword = match.group("keyword").lower()
        for option in options:
            if option.keyword.lower() != keyword or option.zone is zone:
                continue
            extra.append(
                option.model_copy(update={"zone": zone, "rule": f"CR 604.6, {option.rule}"})
            )
    return extra


#: "You may cast this card from your graveyard[ or from exile][, but not from
#: anywhere else][ by `<cost>` in addition to paying its other costs][ as long
#: as/if `<condition>`]." - the card's own CR 601.3 permission to be cast from
#: a zone (CR 604.6's "functions from" that zone), at its own mana cost plus
#: any additional cost (CR 601.2f), at its own timing: Quilled Greatwurm
#: ("by removing six counters from among creatures you control"), Rona and
#: Alien Symbiosis ("by discarding ..."), Wickerfolk Indomitable and Demonic
#: Embrace ("by paying ... and sacrificing/discarding ..."), Gravecrawler and
#: Marang River Prowler ("as long as you control ..."), Ebondeath, Dracolich
#: and Oathsworn Vampire ("if ..."), Squee ("from your graveyard or from
#: exile"), Misthollow Griffin ("from exile"), Haakon ("but not from anywhere
#: else", CR 601.3's prohibition on the hand), Lightwheel Enhancements ("Max
#: speed - ", CR 702.178a).
_PRINTED_SELF_ZONE_CAST_RE = re.compile(
    r"^you may cast this (?:card|spell) from (?:your )?(?P<z1>graveyard|exile)"
    r"(?: or from (?:your )?(?P<z2>graveyard|exile))?"
    r"(?P<only>, but not from anywhere else)?"
    r"(?: by (?P<extra>.+?) in addition to paying its other costs)?"
    r"(?: (?:as long as|if) (?P<cond>.+?))?\.?$",
    re.IGNORECASE,
)
_ZONE_WORDS_SELF = {"graveyard": Zone.GRAVEYARD, "exile": Zone.EXILE}


class PrintedSelfZoneCast(EngineModel):
    """One `_PRINTED_SELF_ZONE_CAST_RE` line, read."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    zones: tuple[Zone, ...]
    only_here: bool = False
    """"but not from anywhere else": the card may be cast from these zones
    and no other, the hand included."""
    cost: TotalCost | None = None
    condition: str | None = None
    replaces_mana_cost: bool = False
    """"by paying `<cost>` rather than paying its mana cost" (CR 118.9): `cost`
    stands in for the mana cost instead of being added to it."""


@lru_cache(maxsize=2048)
def printed_self_zone_cast(text: str) -> PrintedSelfZoneCast | None:
    line, word_condition = strip_ability_word(_REMINDER_TEXT_RE.sub("", " ".join(text.split())))
    match = _PRINTED_SELF_ZONE_CAST_RE.fullmatch(line)
    if match is None:
        return _printed_self_zone_cast_alternative(line)
    cost = None
    if match.group("extra") is not None:
        cost = additional_cost_for_gerunds(match.group("extra"))
        if cost is None:
            return None
    conditions = [c.strip() for c in (word_condition, match.group("cond")) if c]
    if any(not cast_condition_readable(c) for c in conditions):
        return None
    zones = [_ZONE_WORDS_SELF[match.group("z1").lower()]]
    if match.group("z2"):
        zones.append(_ZONE_WORDS_SELF[match.group("z2").lower()])
    return PrintedSelfZoneCast(
        zones=tuple(zones),
        only_here=match.group("only") is not None,
        cost=cost,
        condition=" and ".join(conditions) if conditions else None,
    )


#: "You may cast this card from your graveyard by paying {2}{W} rather than
#: paying its mana cost." (Raffine's Guidance) and "... by paying {3}{R} and
#: exiling four other cards from your graveyard rather than paying its mana
#: cost." (Squee, Dubious Monarch) - the same CR 604.6 permission with the cost
#: standing in for the mana cost (CR 118.9) rather than added to it.
_PRINTED_SELF_ZONE_CAST_ALTERNATIVE_RE = re.compile(
    r"^you may cast this card from your (?P<zone>graveyard|exile) by (?P<cost>.+?) "
    r"rather than paying its mana cost\.?$",
    re.IGNORECASE,
)


def _as_cost_phrase(extra: str) -> str:
    """ "paying {2}{W} and exiling four other cards" as the cost phrase
    `total_cost_for_phrase` reads ("pay {2}{W} and exile four other cards")."""
    extra = re.sub(r"^removing\b", "Remove", extra.strip(), flags=re.IGNORECASE)
    extra = re.sub(r"^paying\b", "Pay", extra, flags=re.IGNORECASE)
    extra = re.sub(r"^exiling\b", "Exile", extra, flags=re.IGNORECASE)
    return re.sub(r" and exiling\b", " and exile", extra, flags=re.IGNORECASE)


def _printed_self_zone_cast_alternative(line: str) -> "PrintedSelfZoneCast | None":
    match = _PRINTED_SELF_ZONE_CAST_ALTERNATIVE_RE.fullmatch(" ".join(line.split()))
    if match is None:
        return None
    cost = total_cost_for_phrase(_as_cost_phrase(match.group("cost")))
    if cost is None:
        return None
    zone = Zone.GRAVEYARD if match.group("zone").lower() == "graveyard" else Zone.EXILE
    return PrintedSelfZoneCast(zones=(zone,), cost=cost, replaces_mana_cost=True)


def _printed_self_zone_cast_additional_cost(text: str) -> tuple[Zone, TotalCost, bool] | None:
    """(zone, cost, whether the cost replaces the mana cost) for one line."""
    read = printed_self_zone_cast(text)
    if read is None or read.cost is None or len(read.zones) != 1:
        return None
    return read.zones[0], read.cost, read.replaces_mana_cost


_SEARCH_CAST_RE = re.compile(
    r"While you're searching your library, you may cast this card from your library\."
)


def reads_search_cast_permission_line(text: str) -> bool:
    """Panglacial Wurm's line: what `support.py` asks, and what
    `search_cast_candidates` consults while a library search is under way."""
    return _SEARCH_CAST_RE.fullmatch(" ".join(_REMINDER_TEXT_RE.sub("", text).split())) is not None


def search_cast_candidates(library: list[CardState]) -> list[CardState]:
    """The cards in `library` whose own text lets their owner cast them from
    the library while that library is being searched (CR 701.23a, CR 601.3)."""
    return [
        card
        for card in library
        if any(reads_search_cast_permission_line(line) for line in card.oracle_text.splitlines())
    ]


def reads_printed_self_zone_cast_line(text: str) -> bool:
    """What `support.py` asks before crediting the line."""
    return printed_self_zone_cast(text) is not None


def _printed_self_zone_cast_with_additional_cost(card: Card) -> list[KeywordCastOption]:
    found: list[KeywordCastOption] = []
    for line in (card.oracle_text or "").splitlines():
        read = printed_self_zone_cast(line)
        if read is None:
            continue
        for zone in read.zones:
            replaces = read.replaces_mana_cost
            found.append(
                KeywordCastOption(
                    keyword=CAST_PERMISSION,
                    rule="CR 601.3, CR 118.9" if replaces else "CR 601.3, CR 604.6",
                    zone=zone,
                    pays_mana_cost=not replaces,
                    timing=CastTiming.OWN,
                    cost=read.cost if replaces else None,
                    additional_cost=None if replaces else read.cost,
                    condition=read.condition,
                )
            )
    return found


#: "You may cast this card from your graveyard[ if `<condition>`][ by paying
#: `<cost>` rather than paying its mana cost]. If you do, it enters with `<n>`
#: `<kind>` counter[s] on it." (Undead Sprinter, Worldheart Phoenix,
#: Hundred-Battle Veteran) - the card's own CR 601.3 permission, functioning
#: from the graveyard (CR 604.6), with CR 614.1c's rider scoped to a spell cast
#: under it (`KeywordCastOption.enters_with_counters`, the record Leonardo's
#: grant already uses).
_PRINTED_SELF_ZONE_CAST_WITH_COUNTERS_RE = re.compile(
    r"^you may cast this card from your graveyard"
    r"(?: if (?P<condition>[^.]+?))?"
    r"(?: by paying (?P<cost>(?:\{[^}]+\})+) rather than paying its mana cost)?\. "
    rf"if you do, (?:it|this creature) enters with (?P<n>an?|{COUNT}) (?P<kind>\S+) counters? "
    r"on it\.?$",
    re.IGNORECASE,
)


def _printed_self_zone_cast_with_counters(card: Card) -> list[KeywordCastOption]:
    found: list[KeywordCastOption] = []
    for line in (card.oracle_text or "").splitlines():
        text = _REMINDER_TEXT_RE.sub("", " ".join(line.split())).strip()
        match = _PRINTED_SELF_ZONE_CAST_WITH_COUNTERS_RE.fullmatch(text)
        if match is None:
            continue
        count = 1 if match.group("n").lower() in ("a", "an") else parse_count(match.group("n"))
        cost = None
        if match.group("cost"):
            cost = total_cost_for_phrase(match.group("cost"))
            if cost is None:
                continue
        found.append(
            KeywordCastOption(
                keyword=CAST_PERMISSION,
                rule="CR 601.3, CR 604.6, CR 614.1c",
                zone=Zone.GRAVEYARD,
                cost=cost,
                pays_mana_cost=cost is None,
                timing=CastTiming.OWN,
                condition=match.group("condition"),
                enters_with_counters=(match.group("kind").lower(),) * (count or 1),
            )
        )
    return found


def reads_printed_self_zone_cast_with_counters_line(text: str) -> bool:
    """What `support.py` asks before crediting the line."""
    line = _REMINDER_TEXT_RE.sub("", " ".join(text.split())).strip()
    return _PRINTED_SELF_ZONE_CAST_WITH_COUNTERS_RE.fullmatch(line) is not None


def printed_cast_only_zones(card: Card) -> tuple[Zone, ...] | None:
    """The zones a card's own "but not from anywhere else" confines its casting
    to (Haakon, Stromgald Scourge), or None when it prints no such line."""
    for line in (card.oracle_text or "").splitlines():
        read = printed_self_zone_cast(line)
        if read is not None and read.only_here:
            return read.zones
    return None


def castable_from(card: Card, zone: Zone) -> list[KeywordCastOption]:
    """The keyword options that cast this card out of one zone."""
    return [option for option in keyword_cast_options(card) if option.zone is zone]


# --------------------------------------------------------------------------
# A keyword another permanent grants a spell as it is cast (CR 610.5)
# --------------------------------------------------------------------------

#: Ashling, the Limitless: "Elemental permanent spells you cast from your hand
#: gain evoke {4} as you cast them." CR 610.5's own shape - "Some static
#: abilities create one-shot effects that cause spells a player casts to gain
#: an ability as that player casts them" - so the keyword is not on the card
#: being cast and `keyword_cast_options` can never find it.
_GRANTED_KEYWORD_AS_YOU_CAST = re.compile(
    r"^(?P<what>[\w' -]+?) spells you cast from your (?P<zone>hand|graveyard) gain "
    r"(?P<keyword>[A-Za-z]+)(?P<cost>[^.]*?) as you cast them\.",
    re.IGNORECASE,
)

#: Herigast, Erupting Nullkite: "Each creature spell you cast has emerge. The
#: emerge cost is equal to its mana cost." CR 611.3d's own "grant an ability
#: to a permanent spell ... that allows it to be cast" shape, worded with
#: "has" rather than `_GRANTED_KEYWORD_AS_YOU_CAST`'s one-shot "gain ... as
#: you cast them" - and, unlike that shape, printed with no "from your
#: hand"/"from your graveyard" clause at all, so nothing here narrows which
#: zone the cast comes from beyond what the granted keyword's own rule
#: already casts from (CR 702.119a: emerge, the hand) - `_granted_option`'s
#: own zone check is what enforces that, exactly as it does for every other
#: grant here.
_GRANTED_KEYWORD_SPELL_YOU_CAST_HAS = re.compile(
    r"^each (?P<what>[\w' -]+?) spell you cast(?P<cond> that's one or more colors)? has "
    r"(?P<keyword>[A-Za-z-]+)(?P<cost>[^.]*)\.(?P<tail>.*)$",
    re.IGNORECASE | re.DOTALL,
)

#: "Assassin spells you cast have freerunning {B}{B}." (Ezio Auditore da
#: Firenze) - `_GRANTED_KEYWORD_SPELL_YOU_CAST_HAS`'s plural twin: the quality
#: may be empty ("Spells you cast have ...") and the cast may be "from exile".
_GRANTED_KEYWORD_SPELLS_YOU_CAST_HAVE = re.compile(
    r"^(?P<what>[\w' -]*?)\s*spells you cast(?: from (?P<zone>your hand|your graveyard|exile))? "
    r"have (?P<keyword>[A-Za-z-]+)(?P<cost>[^.]*)\.(?P<tail>.*)$",
    re.IGNORECASE | re.DOTALL,
)

#: CR 110.4: "There are six permanent types: artifact, battle, creature,
#: enchantment, land, and planeswalker." CR 110.4b's "permanent spell" is a
#: spell with one of them, which is what "Elemental **permanent** spells"
#: narrows Ashling's grant to.
_PERMANENT_TYPES = frozenset(
    {Type.ARTIFACT, Type.BATTLE, Type.CREATURE, Type.ENCHANTMENT, Type.LAND, Type.PLANESWALKER}
)

_ZONE_WORDS_FOR_GRANTS: dict[str, Zone] = {"hand": Zone.HAND, "graveyard": Zone.GRAVEYARD}

#: Iroh, Grand Lotus: "During your turn, each Lesson card in your graveyard has
#: flashback {1}." and "During your turn, each non-Lesson instant and sorcery
#: card in your graveyard has flashback. The flashback cost is equal to that
#: card's mana cost." CR 611.3d's own shape - "Continuous effects from static
#: abilities may allow a player to play a land or cast a permanent spell, or
#: may grant an ability to a permanent spell or card that allows it to be
#: cast" - and the granted keyword is what says which zone it may be cast from
#: (CR 113.6f, CR 702.34a).
#: Ninja Teen's level 3 prints the plural of the same shape: "Creature cards
#: in your graveyard have sneak {3}{B}."
_EXACT_COLOR_COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

#: Granted keywords whose rule names no cost of their own: CR 702.133a's
#: jump-start casts for the card's mana cost and adds a discard; CR 702.81a's
#: retrace ("Instant and sorcery cards in your graveyard have retrace.").
COSTLESS_GRANTED_KEYWORDS = frozenset({"jump-start", "retrace"})

_GRANTED_KEYWORD_ON_A_CARD_IN_A_ZONE = re.compile(
    r"^(?P<during>During your turn, )?(?:[Ee]ach (?P<what>[\w' -]+?) card in your "
    r"(?P<zone>hand|graveyard)(?: that's exactly (?P<ncolors>one|two|three|four|five) colors?)? has"
    r"|(?P<whats>[\w' -]+?) cards in your "
    r"(?P<zones>hand|graveyard) have) (?P<keyword>[A-Za-z-]+)(?P<cost>[^.]*)\.(?P<tail>.*)$",
    re.DOTALL,
)

#: "You may cast `<quality>` spells from your graveyard using their
#: `<keyword>` abilities." - Ninja Teen's level 3. CR 601.3's permission,
#: opening a zone to a keyword that on its own casts from somewhere else
#: (sneak casts from the hand, CR 702.190a): the keyword's cost and timing
#: are unchanged, only the zone the card may be in. It covers every instance
#: of the keyword the card has, printed or granted (the card's own ruling).
_CAST_USING_THEIR_KEYWORD_RE = re.compile(
    r"^you may cast (?P<what>[\w' ,-]+?) spells from your (?P<zone>graveyard|hand) "
    r"using their (?P<keyword>[a-z]+) abilities\.?$",
    re.IGNORECASE,
)


def class_gated_lines(permanent: CardState, lines: Sequence[str]) -> tuple[str, ...]:
    """A permanent's computed ability lines (CR 613.1f) with a Class's
    not-yet-reached levels taken out (CR 716.2a: a level-3 paragraph on a
    level-2 Class is printed but not in effect). The computed list carries
    every printed line whatever the level, so a printed line is kept only
    when `CardState.class_ability_text` - the level-gated printing - has it;
    a line some effect granted is not printed at all and is kept as is."""
    if not permanent.is_class:
        return tuple(lines)
    live = set(permanent.class_ability_text.split("\n"))
    printed = set((permanent.oracle_text or "").split("\n"))
    return tuple(line for line in lines if line in live or line not in printed)


class UsingKeywordPermission(EngineModel):
    """One `_CAST_USING_THEIR_KEYWORD_RE` line, read."""

    model_config = ConfigDict(frozen=True)

    quality: str
    zone: Zone
    keyword: str
    """Lower case, the keyword's canonical spelling."""


def using_keyword_permission(text: str) -> UsingKeywordPermission | None:
    """Read one static line as `_CAST_USING_THEIR_KEYWORD_RE`, or None."""
    match = _CAST_USING_THEIR_KEYWORD_RE.fullmatch(_REMINDER_TEXT_RE.sub("", text).strip())
    if match is None:
        return None
    zone = _ZONE_WORDS_FOR_GRANTS.get(match.group("zone").lower())
    if zone is None:
        return None
    return UsingKeywordPermission(
        quality=match.group("what").strip(),
        zone=zone,
        keyword=match.group("keyword").lower(),
    )


def _using_keyword_permissions(game: Any, caster: str) -> list[UsingKeywordPermission]:
    """Every "using their `<keyword>` abilities" permission `caster`'s
    permanents have right now, off their computed abilities (CR 613.1f) - a
    Class below the level printing it has none (CR 716.2a)."""
    if game is None:
        return []
    board = game.computed_board()
    found: list[UsingKeywordPermission] = []
    for permanent in game.permanents_controlled_by(caster):
        for ability in parse_granted_ability_lines(
            class_gated_lines(permanent, board.of(permanent).abilities)
        ):
            if ability.kind is not AbilityKind.STATIC:
                continue
            permission = using_keyword_permission(ability.text or "")
            if permission is not None:
                found.append(permission)
    return found


def _rezoned_by_using(
    option: KeywordCastOption,
    spell: CardState,
    zone: Zone,
    using: list[UsingKeywordPermission],
) -> KeywordCastOption | None:
    """`option` moved to `zone` when a "using their `<keyword>` abilities"
    permission opens that zone to this keyword for this spell, else None."""
    for permission in using:
        if (
            permission.zone is zone
            and permission.keyword == option.keyword.lower()
            and _spell_matches_grant_filter(spell, permission.quality)
        ):
            return option.model_copy(
                update={"zone": zone, "rule": f"CR 601.3, CR 611.3d, {option.rule}"}
            )
    return None


#: The second sentence a granted-keyword line's own cost completion prints
#: under the first: the granted cost is the *object's* own mana cost rather
#: than a printed one - Iroh, Grand Lotus's "The flashback cost is equal to
#: that card's mana cost." (a card sitting in a zone, `_grant_on_a_card_in_
#: a_zone`) and Herigast, Erupting Nullkite's "The emerge cost is equal to
#: its mana cost." (a spell being cast, `_grant_spell_you_cast_has_keyword`) -
#: the same rule (CR 611.3d) read off two different antecedent words, "that
#: card's" for one and "its" for the other, English grammar rather than a
#: rules difference.
_COST_IS_THE_CARDS_MANA_COST = re.compile(
    r"The (?P<keyword>[A-Za-z]+) cost is equal to (?:that card's|its) mana cost\.",
    re.IGNORECASE,
)


class GrantedCastOption(EngineModel):
    """One `KeywordCastOption` another permanent handed this spell (CR 610.5)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    source_name: str
    """The permanent whose static ability granted it."""
    option: KeywordCastOption


def _spell_matches_grant_filter(spell: CardState, what: str) -> bool:
    """Whether this spell is one the grant's noun phrase names.

    Every word has to be recognised, and a word this cannot place - a noun
    nobody parsed - makes the whole phrase unmatched rather than ignored, so an
    unread grant hands out nothing instead of handing out too much.

    Two shapes of word, read the way the templating uses them:

    - **card types are a disjunction.** "instant and sorcery card" is one card
      that is either, never one card that is both - CR 205.1 puts the types on
      one line and no card is an instant *and* a sorcery, so reading the "and"
      as a conjunction would match nothing at all. They are collected and the
      spell has to have at least one (CR 205.2b: an object with more than one
      card type "satisf[ies] the criteria for any effect that applies to any of
      their card types").
    - **everything else is a conjunction.** "Elemental permanent spells" wants
      both, and a subtype or supertype is simply had.

    A `non-` prefix negates the word it is attached to ("non-Lesson instant and
    sorcery card"): the spell must *not* match it.
    """
    types = set(spell.types)
    subtypes = {subtype.lower() for subtype in spell.subtypes}
    supertypes = {supertype.value.lower() for supertype in spell.supertypes}
    type_words = {type_.value.lower(): type_ for type_ in Type}
    wanted_types: set[Type] = set()
    for raw_word in what.split():
        word = raw_word.strip(",").lower()
        if not word or word in {"and", "or"}:
            continue
        # "non-Lesson" (hyphenated before a subtype) and "nonland" (one word
        # before a card type, CR 205.2) both negate the word after the prefix.
        negated = word.startswith("non-") or (
            word.startswith("non") and word[len("non") :].rstrip("s") in type_words
        )
        if negated:
            word = word[len("non-") :] if word.startswith("non-") else word[len("non") :]
        singular = word.rstrip("s")
        if word in {"permanent", "permanents"}:
            matched = bool(types & _PERMANENT_TYPES)
        elif singular in type_words:
            if not negated:
                # Held back and answered as a disjunction once the whole
                # phrase has been read.
                wanted_types.add(type_words[singular])
                continue
            matched = type_words[singular] in types
        elif word in supertypes or singular in subtypes:
            matched = True
        elif negated:
            # A negated word the spell plainly does not have: "non-Lesson"
            # against a card with no subtypes at all is satisfied, and there
            # is nothing to look up.
            matched = False
        else:
            return False
        if matched is negated:
            return False
    return not (wanted_types and not types & wanted_types)


def granted_cast_options(
    game: Any,
    spell: CardState,
    caster: str,
    origin_zone: Zone,
    *,
    library_top: bool | None = None,
) -> list[GrantedCastOption]:
    """Every cast option another permanent grants this spell right now
    (CR 610.5).

    "Some static abilities create one-shot effects that cause spells a player
    casts to gain an ability as that player casts them. These effects begin to
    apply to appropriate spells at the time the player proposes the casting of
    that spell" - which is why this is asked at announcement, off the board as
    it stands then, rather than read off the card being cast.

    Only the caster's own permanents are read ("spells **you** cast", "in
    **your** graveyard"), only genuine `AbilityKind.STATIC` lines (CR 113.3d's
    "Static abilities are written as statements. They're simply true."), and
    only when the zone the grant names is the zone this cast is coming from.
    The keyword itself is then expanded by
    `_option_from_keyword`, the same reader that expands a printed one, so a
    granted evoke costs and behaves exactly like a printed evoke (CR 702.74a)
    instead of becoming a second, parallel notion of the keyword.

    Two sentence shapes are read, and they are two different rules:

    - **as you cast it** (CR 610.5) - Ashling, the Limitless's "Elemental
      permanent spells you cast from your hand gain evoke {4} as you cast
      them.";
    - **while it sits in the zone** (CR 611.3d: "Continuous effects from static
      abilities ... may grant an ability to a permanent spell or card that
      allows it to be cast") - Iroh, Grand Lotus's "During your turn, each
      Lesson card in your graveyard has flashback {1}." The granted keyword is
      what names the zone it may be cast from (CR 113.6f), and CR 400.7g is
      what keeps the grant applying once CR 601.2a has moved the card to the
      stack.
    """
    if game is None:
        return []
    found: list[GrantedCastOption] = []
    # `computed_board()` recomputes the whole battlefield on every call
    # (CR 613.5 - "continually and automatically"), so one board is hoisted
    # here rather than one per permanent in the loop below.
    board = game.computed_board()
    for permanent in getattr(game, "battlefield", []):
        if permanent.controller != caster:
            continue
        up_face_name = permanent.up_face_name or permanent.card.name
        # A permanent's *computed* ability list (`Characteristics.abilities`,
        # CR 613.1f), not its printed oracle text: a static ability layer 6
        # already stripped no longer grants, and one layer 6 granted does.
        # `parse_granted_ability_lines` reads that list line by line the same
        # way `parse_abilities` reads a printing, and the result is already
        # scoped to the face that's up, so there is no separate `.face`
        # filter to apply here the way there was against `parse_abilities`.
        for ability in parse_granted_ability_lines(
            class_gated_lines(permanent, board.of(permanent).abilities)
        ):
            if ability.kind is not AbilityKind.STATIC:
                continue
            text = (ability.text or "").strip()
            option = _grant_as_you_cast(text, spell, origin_zone, up_face_name, ability.raw)
            if option is None:
                option = _grant_spell_you_cast_has_keyword(
                    text, spell, origin_zone, up_face_name, ability.raw
                )
            if option is None:
                option = _grant_on_a_card_in_a_zone(
                    text, game, spell, caster, origin_zone, up_face_name, ability.raw
                )
            if option is None:
                option = _once_each_turn_cast_from_graveyard(
                    text, spell, origin_zone, game, caster, permanent
                )
            static_options = (
                _static_zone_cast_options(
                    text, game, spell, caster, origin_zone, library_top, permanent
                )
                if option is None
                else []
            )
            found.extend(
                GrantedCastOption(source_name=permanent.name, option=static_option)
                for static_option in static_options
            )
            if option is None and not static_options:
                option = _linked_exile_static_cast_option(
                    text, game, spell, caster, origin_zone, permanent
                )
            if option is None:
                option = _opponents_exile_counter_cast_option(
                    text, game, spell, caster, origin_zone
                )
            if option is not None:
                found.append(GrantedCastOption(source_name=permanent.name, option=option))
    # "You may cast creature spells from your graveyard using their sneak
    # abilities." reaches a card's own printed keyword as well as a granted
    # one (Ninja Teen's ruling): each printed option for that keyword, moved
    # to the zone the permission opens.
    if origin_zone is not Zone.HAND and (spell.owner or caster) == caster:
        using = [
            permission
            for permission in _using_keyword_permissions(game, caster)
            if permission.zone is origin_zone
        ]
        if using:
            for printed in keyword_cast_options(spell.card):
                if printed.zone is origin_zone:
                    continue
                rezoned = _rezoned_by_using(printed, spell, origin_zone, using)
                if rezoned is not None:
                    found.append(GrantedCastOption(source_name=spell.name, option=rezoned))
    linked = _linked_exile_play_option(game, spell, caster, origin_zone)
    if linked is not None:
        found.append(GrantedCastOption(source_name=spell.name, option=linked))
    # CR 114.4: an emblem's abilities function in the command zone, so the
    # caster's own emblems grant exactly as a permanent's statics do.
    for emblem in game.emblems_of(caster):
        for ability in parse_abilities(emblem.card):
            if ability.kind is not AbilityKind.STATIC:
                continue
            text = (ability.text or "").strip()
            option = _cast_spells_from_a_zone(
                text, spell, origin_zone, game, caster
            ) or _grant_on_a_card_in_a_zone(
                text, game, spell, caster, origin_zone, emblem.name, ability.raw
            )
            if option is not None:
                found.append(GrantedCastOption(source_name=emblem.name, option=option))
    # CR 611.2c: a resolved "you may cast ... spells from <a> graveyard this
    # turn" is a rule of the game for the rest of the turn, recorded rather
    # than read off a permanent (The Great Work, Liliana, Untouched by Death).
    from ..casting_restrictions import graveyard_cast_grants_for

    for grant in graveyard_cast_grants_for(game, caster):
        option = _graveyard_cast_grant_option(grant, spell, origin_zone, caster)
        if option is not None:
            found.append(GrantedCastOption(source_name=grant.source_name, option=option))
    return found


#: The label a "You may cast `<quality>` spells from your `<zone>`" grant is
#: announced under (`Casting.use_keyword`) and recorded as (`CastRecord.
#: keyword`) - the permission is not a keyword, so it is named for what it is.
CAST_PERMISSION = "Cast permission"

#: "You may cast instant and sorcery spells from your graveyard." (Jaya
#: Ballard's emblem) - CR 601.3's "a rule or effect allows that player to cast
#: it", for a quality of spell and one zone, at the spell's own normal cost
#: and timing. The optional second sentence - "If a spell cast this way would
#: be put into your graveyard, exile it instead." - is the replacement
#: `machines/replacement.py` applies to a spell recorded as cast under this
#: permission (`exiles_spells_cast_this_way`).
_CAST_SPELLS_FROM_A_ZONE = re.compile(
    r"^You may cast (?P<what>[\w' -]+?) spells from your (?P<zone>hand|graveyard)\."
    r"(?P<tail>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_EXILE_SPELLS_CAST_THIS_WAY = re.compile(
    r"if a spell cast this way would be put into your graveyard, exile it instead",
    re.IGNORECASE,
)


def _cast_spells_from_a_zone(
    text: str, spell: CardState, origin_zone: Zone, game: Any, caster: str
) -> KeywordCastOption | None:
    match = _CAST_SPELLS_FROM_A_ZONE.match(text)
    if match is None:
        return None
    zone = _ZONE_WORDS_FOR_GRANTS.get(match.group("zone").lower())
    if zone is None or zone is not origin_zone:
        return None
    if not _spell_matches_grant_filter(spell, match.group("what")):
        return None
    # The spell's own timing: a sorcery still waits for its controller's main
    # phase with the stack empty (CR 307.1), an instant does not.
    timing = CastTiming.SORCERY if Type.SORCERY in spell.types else CastTiming.ANY
    return KeywordCastOption(
        keyword=CAST_PERMISSION, rule="CR 601.3", zone=zone, pays_mana_cost=True, timing=timing
    )


#: "Once during each of your turns, you may cast <a quality> spell from your
#: graveyard. [If a spell cast this way would be put into your graveyard,
#: exile it instead.]" - Rivaz of the Claw ("a Dragon creature spell"), Gisa
#: and Geralf ("a Zombie creature spell"), Kess, Dissident Mage ("an instant
#: or sorcery spell", with the exile rider). CR 601.3's permission, limited to
#: one use per turn of the permanent printing it, only during its controller's
#: own turn. A grant that charges something extra ("by sacrificing a creature
#: in addition to paying its other costs") is not this shape.
_ONCE_EACH_TURN_CAST_FROM_GRAVEYARD = re.compile(
    r"^Once during each of your turns, you may cast an? (?P<what>[\w' -]+?) spell "
    r"from your graveyard(?: by sacrificing (?P<sacrifice>a creature) in addition to paying "
    r"its other costs)?\.(?P<tail>.*)$",
    re.IGNORECASE | re.DOTALL,
)


def reads_as_graveyard_cast_permission_line(text: str) -> bool:
    """Whether one static line is `_ONCE_EACH_TURN_CAST_FROM_GRAVEYARD`'s
    shape, with nothing unread left in its tail - what `support.py` asks
    before calling the line handled."""
    match = _ONCE_EACH_TURN_CAST_FROM_GRAVEYARD.match(text.strip())
    if match is None:
        return False
    tail = match.group("tail").strip()
    return not tail or _EXILE_SPELLS_CAST_THIS_WAY_ANY.fullmatch(tail.rstrip(".")) is not None


#: The exile rider in either spelling: "your graveyard" (Jaya Ballard's
#: emblem, Kess) or "a graveyard" (The Great Work).
_EXILE_SPELLS_CAST_THIS_WAY_ANY = re.compile(
    r"if a spell cast this way would be put into (?:your|a) graveyard, exile it instead",
    re.IGNORECASE,
)


def once_per_turn_key(permanent: CardState) -> str:
    """The granting permanent as that object (CR 400.7)."""
    return f"{permanent.id}:{permanent.zone_change_stamp}"


def _once_each_turn_cast_from_graveyard(
    text: str,
    spell: CardState,
    origin_zone: Zone,
    game: Any,
    caster: str,
    permanent: CardState,
) -> KeywordCastOption | None:
    if not reads_as_graveyard_cast_permission_line(text):
        return None
    match = _ONCE_EACH_TURN_CAST_FROM_GRAVEYARD.match(text.strip())
    assert match is not None
    if origin_zone is not Zone.GRAVEYARD:
        return None
    # "your graveyard": the card has to be the caster's own.
    if (spell.owner or caster) != caster:
        return None
    # "during each of your turns": only while the caster is the active player.
    turn = getattr(game, "turn", None)
    if turn is None or turn.active_player != caster:
        return None
    key = once_per_turn_key(permanent)
    if key in getattr(game, "once_per_turn_cast_permissions_used", {}):
        return None
    if not _spell_matches_grant_filter(spell, match.group("what")):
        return None
    timing = CastTiming.SORCERY if Type.SORCERY in spell.types else CastTiming.ANY
    return KeywordCastOption(
        keyword=CAST_PERMISSION,
        rule="CR 601.3",
        zone=Zone.GRAVEYARD,
        pays_mana_cost=True,
        timing=timing,
        exile_instead_of_graveyard=bool(match.group("tail").strip()),
        once_per_turn_key=key,
        # Maestros Ascendancy: "by sacrificing a creature in addition to paying
        # its other costs" (CR 601.2f), the creature chosen at CR 601.2b.
        additional_cost=(
            total_cost_for_phrase(f"Sacrifice {match.group('sacrifice')}")
            if match.group("sacrifice")
            else None
        ),
    )


def _graveyard_cast_grant_option(
    grant: Any, spell: CardState, origin_zone: Zone, caster: str
) -> KeywordCastOption | None:
    """One recorded `CastingRuleKind.GRAVEYARD_CAST_GRANT` applied to `spell`:
    from a graveyard, the caster's own unless the grant says "any graveyard",
    and only a spell the grant's noun phrase names."""
    if origin_zone is not Zone.GRAVEYARD:
        return None
    if not grant.any_graveyard and (spell.owner or caster) != caster:
        return None
    if not _spell_matches_grant_filter(spell, grant.spell_quality or ""):
        return None
    timing = CastTiming.SORCERY if Type.SORCERY in spell.types else CastTiming.ANY
    return KeywordCastOption(
        keyword=CAST_PERMISSION,
        rule="CR 601.3, CR 611.2c",
        zone=Zone.GRAVEYARD,
        pays_mana_cost=True,
        timing=timing,
        exile_instead_of_graveyard=grant.exile_instead,
    )


# --------------------------------------------------------------------------
# A permanent's standing permission to cast out of the graveyard or off the
# top of the library (CR 601.3, CR 611.3d)
# --------------------------------------------------------------------------

#: A line's leading ability word and its em dash ("Coven - ", "Solved - ",
#: "Max speed - "): CR 207.2c gives it no rules meaning of its own, except
#: where the word stands for a condition the rules define (CR 702.178a's max
#: speed), which `_ABILITY_WORD_CONDITIONS` turns back into one.
_ABILITY_WORD_PREFIX_RE = re.compile(r"^(?P<word>[A-Z][A-Za-z' ]*?) — ")
_ABILITY_WORD_CONDITIONS = {
    "max speed": "you have max speed",
    "solved": "this Case is solved",
}


def strip_ability_word(text: str) -> tuple[str, str | None]:
    """The line without a leading ability word, and the condition that word
    stands for (None for the ordinary ones, CR 207.2c)."""
    match = _ABILITY_WORD_PREFIX_RE.match(text.strip())
    if match is None:
        return text.strip(), None
    return text.strip()[match.end() :], _ABILITY_WORD_CONDITIONS.get(match.group("word").lower())


_GERUNDS = {
    "paying": "Pay",
    "removing": "Remove",
    "discarding": "Discard",
    "sacrificing": "Sacrifice",
    "exiling": "Exile",
    "returning": "Return",
    "tapping": "Tap",
}
_GERUND_RE = re.compile(rf"(?:^|(?<=, )|(?<= and ))({'|'.join(_GERUNDS)})\b", re.IGNORECASE)


def additional_cost_for_gerunds(phrase: str) -> TotalCost | None:
    """CR 601.2f's additional cost a permission prints as "by paying 3 life
    and discarding a card in addition to paying its other costs", read as the
    cost phrase it stands for ("Pay 3 life, Discard a card")."""
    text = _GERUND_RE.sub(lambda m: _GERUNDS[m.group(1).lower()], phrase.strip())
    text = re.sub(r"\bfrom a creature you control\b", "from among creatures you control", text)
    text = re.sub(r"\band (?=[A-Z])", ", ", text)
    return total_cost_for_phrase(text)


# --------------------------------------------------------------------------
# A permission's printed condition, read live (CR 601.3)
# --------------------------------------------------------------------------

_CREATURE_NOT_NAMED_DIED_RE = re.compile(
    r"^a creature not named (?P<name>.+?) died this turn$", re.IGNORECASE
)
_ATTACKED_AND_CONTROL_RE = re.compile(
    r"^a creature is attacking you and you control an? (?P<first>\w+) and an? (?P<second>\w+)$",
    re.IGNORECASE,
)
_HAVE_MAX_SPEED_RE = re.compile(r"^you have max speed$", re.IGNORECASE)
_THIS_CASE_IS_SOLVED_RE = re.compile(r"^this case is solved$", re.IGNORECASE)


def cast_condition_holds(game: Any, caster: str, condition: str, source: CardState | None) -> bool:
    """Whether a permission's printed `condition` is true now for `caster`.

    Conditions `Game.condition_holds` reads go through it; the three it does
    not are read here off the records they name - the turn's graveyard
    arrivals (CR 700.4, `Game.turn_history`), the attackers of the combat in
    progress (CR 508.5's defending player), and the player's speed (CR
    702.178a). An unread condition is false: nothing is permitted by text
    nobody checked."""
    text = condition.strip().rstrip(".")
    if _THIS_CASE_IS_SOLVED_RE.fullmatch(text):
        # CR 719.3b: the designation is on the Case itself.
        return bool(source is not None and source.solved)
    if _HAVE_MAX_SPEED_RE.fullmatch(text):
        from ..speed import has_max_speed

        return has_max_speed(game.player(caster))
    named = _CREATURE_NOT_NAMED_DIED_RE.fullmatch(text)
    if named is not None:
        wanted = named.group("name").strip().lower()
        return any(
            entry.kind == "to_graveyard"
            and entry.characteristics is not None
            and Type.CREATURE in entry.characteristics.types
            and entry.characteristics.name.lower() != wanted
            for entry in game.turn_history
        )
    attacked = _ATTACKED_AND_CONTROL_RE.fullmatch(text)
    if attacked is not None:
        from ..combat import defending_player

        if not any(
            defending_player(game, attack.defender) == caster for attack in game.combat.attacks
        ):
            return False
        wanted_subtypes = {attacked.group("first").lower(), attacked.group("second").lower()}
        have = {
            subtype.lower()
            for permanent in game.permanents_controlled_by(caster)
            for subtype in game.characteristics_of(permanent).subtypes
        }
        return wanted_subtypes <= have
    return game.condition_holds(caster, text, source) is True


def cast_condition_readable(condition: str) -> bool:
    """Whether `cast_condition_holds` reads `condition` at all."""
    from ...models.game._conditions import condition_is_readable

    text = condition.strip().rstrip(".")
    return (
        _HAVE_MAX_SPEED_RE.fullmatch(text) is not None
        or _THIS_CASE_IS_SOLVED_RE.fullmatch(text) is not None
        or _CREATURE_NOT_NAMED_DIED_RE.fullmatch(text) is not None
        or _ATTACKED_AND_CONTROL_RE.fullmatch(text) is not None
        or condition_is_readable(text)
    )


# --------------------------------------------------------------------------
# A spell's quality phrase, as a permission prints it (CR 205, CR 700.6)
# --------------------------------------------------------------------------

_QUALITY_SPELLS_WORD_RE = re.compile(r"\s+spells?\b", re.IGNORECASE)
_QUALITY_ATOM_SPLIT_RE = re.compile(r",\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+")


def _normalized_spell_quality(what: str | None) -> str:
    """The quality phrase with CR 205.1's list punctuation evened out: "Mutant,
    Ninja, or Turtle" becomes "mutant, ninja, turtle", the comma list
    `next_spell.spell_has_quality` reads as a disjunction."""
    quality = (what or "").strip().lower()
    return re.sub(r",?\s+or\s+", ", ", quality)


def normalized_spell_quality(what: str | None) -> str:
    """The quality phrase with CR 205.1's list punctuation evened out and the
    "spells" word dropped: "Spider spells and noncreature" is "spider and
    noncreature", read by `spell_quality_predicate` as a disjunction."""
    quality = (what or "").strip().lower()
    return _QUALITY_SPELLS_WORD_RE.sub("", quality)


@lru_cache(maxsize=1024)
def spell_quality_predicate(quality: str) -> Callable[[CardState], bool] | None:
    """A predicate for a printed spell quality, or None when a word of it is
    not one this engine reads.

    The shared `next_spell` reader knows card types, subtypes, colours and
    historic; this adds colourless (CR 105.2c - no colour at all) and the
    legendary supertype (CR 205.4a) on their own, and joins the atoms of "A
    and B" / "A, B, or C" as the disjunction the permission means (a spell
    satisfies any one of its types, CR 205.2b), except a list made wholly of
    negations, which is a conjunction (the shared reader's own De Morgan)."""
    from ...models.card import Supertype
    from ..next_spell import spell_has_quality, spell_quality_is_readable

    text = quality.strip().lower()
    if not text:
        return lambda spell: True
    atoms = [atom.strip() for atom in _QUALITY_ATOM_SPLIT_RE.split(text) if atom.strip()]
    predicates: list[Callable[[CardState], bool]] = []
    for atom in atoms:
        if atom == "colorless":
            predicates.append(lambda spell: not spell.colors)
        elif atom == "legendary":
            predicates.append(lambda spell: Supertype.LEGENDARY in spell.supertypes)
        elif spell_quality_is_readable(atom):
            predicates.append(lambda spell, atom=atom: spell_has_quality(spell, atom))
        else:
            return None
    if len(atoms) > 1 and all(atom.startswith("non") for atom in atoms):
        return lambda spell: all(predicate(spell) for predicate in predicates)
    return lambda spell: any(predicate(spell) for predicate in predicates)


_SPELL_KEYWORD_WORDS = (
    "flash|flying|haste|trample|vigilance|lifelink|deathtouch|reach|menace|first strike"
    "|double strike|hexproof|indestructible"
)


def _spell_has_any_keyword(spell: CardState, keywords: tuple[str, ...]) -> bool:
    printed = {keyword.lower() for keyword in spell.card.keywords}
    return any(keyword in printed for keyword in keywords)


#: "[As long as `<condition>`, ][During your turn, ][Once each turn, ]you may
#: [look at the top card of your library any time, and you may ]`<act>`
#: [with `<stat>` N or less] [with `<keyword>` or `<keyword>`] [of the chosen
#: type] from your graveyard / the top of your library [by `<cost>` in
#: addition to paying its other costs] [if it shares a card type with a card
#: exiled with this `<noun>`]." - CR 601.3's "a rule or effect allows that
#: player to cast it", as a CR 611.3d static permission. The acts are the
#: ways a printing words what it opens: "play lands and cast `<quality>`
#: spells" (Mikey & Don), "play historic lands and cast historic spells"
#: (Crystal Skull), "play lands" (Radha), "cast `<quality>` spells" (Precognition
#: Field), "cast a `<quality>` spell" (Johann), and "play the top card of your
#: library" (The Lunar Whale), which is both of the first.
_STATIC_ZONE_CAST_BODY_RE = re.compile(
    r"^you may (?P<act>"
    r"play historic lands and cast historic spells"
    r"|play lands and cast (?:(?P<qlands>[\w' ,-]+?) )?spells"
    r"|play lands"
    r"|play cards"
    r"|cast (?:an? )?(?:(?P<q>[\w' ,-]+?) )?spells?)"
    r"(?: that have an? (?P<ability>[a-z]+) ability)?"
    r"(?: with (?P<stat>power or toughness|power|toughness|mana value) (?P<n>\d+) or "
    r"(?P<direction>less|greater))?"
    rf"(?: with (?P<kws>(?:{_SPELL_KEYWORD_WORDS})(?: or (?:{_SPELL_KEYWORD_WORDS}))*))?"
    r"(?P<chosen> of the chosen type)?"
    r" from (?P<zone>your graveyard|the top of your library)"
    r"(?: by (?P<extra>.+?) in addition to paying (?:its|their) other costs)?"
    r"(?: if (?P<iff>it shares a card type with a card exiled with this \w+))?"
    r"\.(?P<tail>.*)$",
    re.IGNORECASE | re.DOTALL,
)
#: Serra Paragon: "Once during each of your turns, you may play a land from
#: your graveyard or cast a permanent spell with mana value 3 or less from your
#: graveyard. If you do, it gains "..."." - one use of the turn, for either
#: half, and the permanent it makes gains the quoted ability.
_GRAVEYARD_LAND_OR_SPELL_RE = re.compile(
    r"^(?P<lead>once during each of your turns), you may play a land from your graveyard or "
    r"cast an? (?P<q>[\w' ,-]+?) spell(?: with (?P<stat>mana value) (?P<n>\d+) or "
    r"(?P<direction>less|greater))? from your graveyard\."
    r'(?: If you do, it gains "(?P<gain>[^"]+)")?\.?$',
    re.IGNORECASE,
)
#: Muldrotha: "During each of your turns, you may play a land and cast a
#: permanent spell of each permanent type from your graveyard."
_GRAVEYARD_EACH_PERMANENT_TYPE_RE = re.compile(
    r"^during each of your turns, you may play a land and cast a permanent spell of each "
    r"permanent type from your graveyard\.$",
    re.IGNORECASE,
)
_STATIC_ZONE_CAST_LEADS = (
    (re.compile(r"^as long as (?P<c>.+?), (?=you may )", re.IGNORECASE), "condition"),
    (re.compile(r"^if (?P<c>.+?), (?=you may )", re.IGNORECASE), "condition"),
    (re.compile(r"^during (?:your turn|each of your turns), ", re.IGNORECASE), "during"),
    (re.compile(r"^once each turn, ", re.IGNORECASE), "once"),
    (re.compile(r"^once during each of your turns, ", re.IGNORECASE), "once_during"),
)
_LOOK_AT_TOP_PREFIX_RE = re.compile(
    r"^you may look at the top card of your library any time, and (?=you may )", re.IGNORECASE
)
_PLAY_THE_TOP_CARD_RE = re.compile(r"\bplay the top card of your library", re.IGNORECASE)

#: "If you cast a[ `<type>`] spell this way, that `<noun>` enters with a[n
#: additional] `<kind>` counter on it." - the rider every printing above that
#: has one prints (CR 614.1c's "enters with", scoped to the spells cast under
#: the permission). A `<type>` narrows it: Mikey & Don's "If you cast a
#: creature spell this way" puts nothing on a Ninja sorcery.
_ENTERS_WITH_A_COUNTER_RIDER_RE = re.compile(
    r"^if you cast an? (?:(?P<type>[a-z]+) )?spell this way, that "
    r"(?:creature|artifact|enchantment|permanent) enters with (?:an additional|an?|one) "
    r"(?P<counter>\+1/\+1|[a-z]+) counter on it\.?$",
    re.IGNORECASE,
)

#: Reminder text (CR 207.2): "(If a creature with a finality counter on it
#: would die, exile it instead.)" has no game function of its own.
_REMINDER_TEXT_RE = re.compile(r"\s*\([^()]*\)")

#: Bolas's Citadel's rider: "If you cast a spell this way, pay life equal to its
#: mana value rather than pay its mana cost." (CR 118.9: life as the
#: alternative cost; CR 202.3e: X counts toward the mana value.)
_PAY_LIFE_FOR_MANA_VALUE_RIDER_RE = re.compile(
    r"^if you cast a spell this way, pay life equal to its mana value rather than pay "
    r"its mana cost\.?$",
    re.IGNORECASE,
)


class StaticZoneCastPermission(EngineModel):
    """One `_STATIC_ZONE_CAST_BODY_RE` line, read."""

    model_config = ConfigDict(frozen=True)

    zone: Zone
    """`Zone.GRAVEYARD` or `Zone.LIBRARY` (the top card only)."""
    quality: str = ""
    """The spell's quality phrase (`normalized_spell_quality`), `""` for
    "spells" of any kind."""
    during_your_turn: bool = False
    once_each_turn: bool = False
    """"Once each turn" / "Once during each of your turns": one use per turn of
    the permanent printing it (`once_per_turn_key`)."""
    plays_lands: bool = False
    """"You may play lands and cast ..." - CR 305.1's land drop opened to the
    same zone, read by `Game.land_from_top_of_library_permission`."""
    casts: bool = True
    """False for "You may play lands from ..." (Radha), which opens no cast."""
    lands_quality: str = ""
    """"historic" for "play historic lands" (Crystal Skull)."""
    looks_at_top: bool = False
    """The line also says "You may look at the top card of your library any
    time" (Radha, Case of the Locked Hothouse)."""
    conditions: tuple[str, ...] = ()
    """Every "as long as"/"if" condition and ability-word condition that has
    to hold (CR 611.3d)."""
    stat: str | None = None
    """"power or toughness", "power", "toughness" or "mana value"."""
    bound: int | None = None
    greater: bool = False
    has_ability: str | None = None
    """"spells that have a cycling ability": the keyword the spell must carry
    (CR 702.29f counts every `[type]cycling`)."""
    keywords: tuple[str, ...] = ()
    """"spells with flash or flying": any one of the printed keywords."""
    of_chosen_type: bool = False
    """"of the chosen type": a creature type chosen as the permanent entered
    (CR 614.12a)."""
    extra_cost: str | None = None
    """The gerund phrase of "by removing a counter ... in addition to paying
    their other costs" (CR 601.2f)."""
    shares_type_with_exiled: bool = False
    """Cemetery Illuminator: the spell shares a card type with a card exiled
    with the permanent (CR 607.2a)."""
    per_permanent_type: bool = False
    """Muldrotha: one land and one permanent spell of each permanent type (CR
    110.4) per turn - each type is its own use, a card of several types
    choosing one as it is played."""
    gained_line: str | None = None
    """Serra Paragon: the ability the permanent played or cast this way gains
    (CR 611.3d)."""
    rider_type: str | None = None
    """The card type the enters-with rider names ("If you cast a creature
    spell this way"), or None when it covers every spell cast this way."""
    rider_counter: str | None = None
    """The counter kind the rider puts on the permanent, or None: no rider."""
    pays_life_for_mana_value: bool = False
    """Bolas's Citadel: the spells cast this way are paid for with life equal to
    their mana value rather than their mana cost (CR 118.9)."""


@lru_cache(maxsize=4096)
def static_zone_cast_permission(text: str) -> StaticZoneCastPermission | None:
    """Read one static line as `_STATIC_ZONE_CAST_BODY_RE`, or None.

    Fails closed: an unreadable quality, condition or cost, a rider this does
    not read, or any other trailing sentence makes the whole line unread -
    Bolas's Citadel's "If you cast a spell this way, pay life equal to its
    mana value rather than pay its mana cost." is a different permission, not
    this one with a sentence ignored."""
    line, word_condition = strip_ability_word(_REMINDER_TEXT_RE.sub("", text))
    if not line or _ONCE_EACH_TURN_CAST_FROM_GRAVEYARD.match(line):
        return None  # the plain once-per-turn graveyard shape has its own reader
    conditions: list[str] = [word_condition] if word_condition else []
    whole_line = line
    during = once = False
    changed = True
    while changed:
        changed = False
        for pattern, kind in _STATIC_ZONE_CAST_LEADS:
            match = pattern.match(line)
            if match is None:
                continue
            changed = True
            line = line[match.end() :]
            if kind == "condition":
                conditions.append(match.group("c").strip())
            elif kind == "during":
                during = True
            elif kind == "once":
                once = True
            else:
                once = during = True
    serra = _GRAVEYARD_LAND_OR_SPELL_RE.fullmatch(whole_line)
    if serra is not None and not conditions:
        quality = normalized_spell_quality(serra.group("q"))
        if spell_quality_predicate(quality) is None:
            return None
        return StaticZoneCastPermission(
            zone=Zone.GRAVEYARD,
            quality=quality,
            during_your_turn=True,
            once_each_turn=True,
            plays_lands=True,
            stat=serra.group("stat").lower() if serra.group("stat") else None,
            bound=int(serra.group("n")) if serra.group("n") else None,
            greater=(serra.group("direction") or "").lower() == "greater",
            gained_line=serra.group("gain"),
        )
    if _GRAVEYARD_EACH_PERMANENT_TYPE_RE.fullmatch(whole_line) and not conditions:
        return StaticZoneCastPermission(
            zone=Zone.GRAVEYARD,
            quality="permanent",
            during_your_turn=True,
            plays_lands=True,
            per_permanent_type=True,
        )
    looks = _LOOK_AT_TOP_PREFIX_RE.match(line) is not None
    line = _LOOK_AT_TOP_PREFIX_RE.sub("", line)
    line = _PLAY_THE_TOP_CARD_RE.sub(
        "play lands and cast spells from the top of your library", line
    )
    match = _STATIC_ZONE_CAST_BODY_RE.fullmatch(line)
    if match is None:
        return None
    act = match.group("act").lower()
    historic_lands = act.startswith("play historic lands")
    plays_lands = act.startswith("play")
    casts = not act.startswith("play lands") or " and cast " in act or act == "play cards"
    quality = normalized_spell_quality(
        "historic" if historic_lands else match.group("qlands") or match.group("q")
    )
    if spell_quality_predicate(quality) is None:
        return None
    if any(not cast_condition_readable(condition) for condition in conditions):
        return None
    extra = match.group("extra")
    if extra is not None and additional_cost_for_gerunds(extra) is None:
        return None
    rider_type: str | None = None
    rider_counter: str | None = None
    tail = match.group("tail").strip()
    pays_life_for_mana_value = False
    if tail and _PAY_LIFE_FOR_MANA_VALUE_RIDER_RE.fullmatch(tail):
        pays_life_for_mana_value = True
    elif tail:
        rider = _ENTERS_WITH_A_COUNTER_RIDER_RE.fullmatch(tail)
        if rider is None:
            return None
        rider_type = (rider.group("type") or "").lower() or None
        if rider_type is not None and rider_type not in {type_.value for type_ in Type}:
            return None
        rider_counter = rider.group("counter").lower()
    zone = Zone.GRAVEYARD if "graveyard" in match.group("zone").lower() else Zone.LIBRARY
    if act == "play cards" and zone is not Zone.GRAVEYARD:
        return None
    return StaticZoneCastPermission(
        zone=zone,
        quality=quality,
        during_your_turn=during,
        once_each_turn=once,
        plays_lands=plays_lands,
        casts=casts,
        lands_quality="historic" if historic_lands else "",
        looks_at_top=looks,
        conditions=tuple(conditions),
        stat=match.group("stat").lower() if match.group("stat") else None,
        bound=int(match.group("n")) if match.group("n") else None,
        greater=(match.group("direction") or "").lower() == "greater",
        has_ability=(match.group("ability") or "").lower() or None,
        keywords=tuple(
            word.strip().lower()
            for word in (match.group("kws") or "").split(" or ")
            if word.strip()
        ),
        of_chosen_type=match.group("chosen") is not None,
        extra_cost=extra.strip() if extra else None,
        shares_type_with_exiled=match.group("iff") is not None,
        rider_type=rider_type,
        rider_counter=rider_counter,
        pays_life_for_mana_value=pays_life_for_mana_value,
    )


def reads_static_zone_cast_permission_line(text: str) -> bool:
    """What `support.py` asks before crediting the line: whether
    `static_zone_cast_permission` reads all of it."""
    return static_zone_cast_permission(text) is not None


def _has_keyword_ability(spell: CardState, ability: str) -> bool:
    """Whether the spell's card has a `<ability>` ability - CR 702.29f's "every
    typecycling ability is a cycling ability" included."""
    return any(
        keyword.lower() == ability or (ability == "cycling" and keyword.lower().endswith("cycling"))
        for keyword in spell.card.keywords
    )


def _within_bound(spell: CardState, permission: StaticZoneCastPermission) -> bool:
    """ "with power or toughness 1 or less" and its kin, off the spell's own
    characteristics (CR 208.1, CR 202.3) as it is being cast."""
    if permission.stat is None or permission.bound is None:
        return True
    values: list[float | None]
    if permission.stat == "power or toughness":
        values = [spell.power, spell.toughness]
    elif permission.stat == "power":
        values = [spell.power]
    elif permission.stat == "toughness":
        values = [spell.toughness]
    else:
        values = [spell.mana_value]
    bound = permission.bound
    return any(
        value is not None and (value >= bound if permission.greater else value <= bound)
        for value in values
    )


def is_top_of_library(game: Any, card: CardState, player: str) -> bool:
    """Whether `card` is the top card of `player`'s own library right now."""
    library = game.player(player).library if game is not None else []
    return bool(library) and library[0] is card


def static_permission_applies_now(
    permission: StaticZoneCastPermission, game: Any, caster: str, permanent: CardState | None
) -> bool:
    """The gates of a static permission that do not look at the spell: "during
    your turn" (CR 611.3a), every printed condition (read for the permanent
    that prints it), and the once-each-turn use of that incarnation (CR 400.7)."""
    if permission.during_your_turn:
        turn = getattr(game, "turn", None)
        if turn is None or turn.active_player != caster:
            return False
    if (
        permission.once_each_turn
        and permanent is not None
        and once_per_turn_key(permanent) in getattr(game, "once_per_turn_cast_permissions_used", {})
    ):
        return False
    return all(
        cast_condition_holds(game, caster, condition, permanent)
        for condition in permission.conditions
    )


def land_quality_allows(permission: StaticZoneCastPermission, land: CardState) -> bool:
    """The land a static permission's "play historic lands" names (CR 700.6:
    legendary, artifact or a Saga), or any land when it names no quality."""
    from ...models.card import Supertype

    if permission.lands_quality != "historic":
        return True
    return Supertype.LEGENDARY in land.supertypes or Type.ARTIFACT in land.types


def _shares_a_type_with_exiled(game: Any, spell: CardState, permanent: CardState | None) -> bool:
    if permanent is None:
        return False
    return any(
        set(state.types) & set(spell.types)
        for state in game.cards_exiled_with(permanent.id, permanent.zone_change_stamp)
    )


_PERMANENT_SPELL_TYPES = (
    Type.ARTIFACT,
    Type.CREATURE,
    Type.ENCHANTMENT,
    Type.PLANESWALKER,
    Type.BATTLE,
)


def _static_zone_cast_options(
    text: str,
    game: Any,
    spell: CardState,
    caster: str,
    origin_zone: Zone,
    library_top: bool | None,
    permanent: CardState | None = None,
) -> list[KeywordCastOption]:
    """`static_zone_cast_permission`'s grants for `spell`: none, one, or - for
    Muldrotha's "each permanent type" - one per permanent type the spell has
    whose use this turn is still unspent (a card of several types chooses one
    as it is cast, CR 110.4)."""
    permission = static_zone_cast_permission(text)
    if permission is None or permission.zone is not origin_zone or not permission.casts:
        return []
    if (spell.owner or caster) != caster:
        return []
    if origin_zone is Zone.LIBRARY:
        on_top = library_top if library_top is not None else is_top_of_library(game, spell, caster)
        if not on_top:
            return []
    if not static_permission_applies_now(permission, game, caster, permanent):
        return []
    predicate = spell_quality_predicate(permission.quality)
    if predicate is None or not predicate(spell):
        return []
    if permission.keywords and not _spell_has_any_keyword(spell, permission.keywords):
        return []
    if permission.has_ability and not _has_keyword_ability(spell, permission.has_ability):
        return []
    if permission.of_chosen_type:
        chosen = permanent.choice.value.lower() if permanent and permanent.choice else None
        if chosen is None or chosen not in {subtype.lower() for subtype in spell.subtypes}:
            return []
    if not _within_bound(spell, permission):
        return []
    if permission.shares_type_with_exiled and not _shares_a_type_with_exiled(
        game, spell, permanent
    ):
        return []
    counters: tuple[str, ...] = ()
    if permission.rider_counter is not None and (
        permission.rider_type is None or Type(permission.rider_type) in spell.types
    ):
        counters = (permission.rider_counter,)
    additional = (
        additional_cost_for_gerunds(permission.extra_cost) if permission.extra_cost else None
    )
    keys: list[str | None] = [None]
    if permanent is not None and permission.per_permanent_type:
        used = getattr(game, "once_per_turn_cast_permissions_used", {})
        keys = [
            f"{once_per_turn_key(permanent)}:{type_.value}"
            for type_ in _PERMANENT_SPELL_TYPES
            if type_ in spell.types and f"{once_per_turn_key(permanent)}:{type_.value}" not in used
        ]
    elif permanent is not None and permission.once_each_turn:
        keys = [once_per_turn_key(permanent)]
    return [
        KeywordCastOption(
            keyword=CAST_PERMISSION,
            rule="CR 601.3, CR 611.3d",
            zone=origin_zone,
            pays_mana_cost=not permission.pays_life_for_mana_value,
            timing=CastTiming.OWN,
            additional_cost=additional,
            enters_with_counters=counters,
            once_per_turn_key=key,
            granted_line=permission.gained_line,
            pays_life_for_mana_value=permission.pays_life_for_mana_value,
        )
        for key in keys
    ]


def _static_zone_cast_option(
    text: str,
    game: Any,
    spell: CardState,
    caster: str,
    origin_zone: Zone,
    library_top: bool | None,
    permanent: CardState | None = None,
) -> KeywordCastOption | None:
    """The first of `_static_zone_cast_options`, or None."""
    options = _static_zone_cast_options(
        text, game, spell, caster, origin_zone, library_top, permanent
    )
    return options[0] if options else None


def static_graveyard_land_source(
    game: Any, land: CardState, username: str
) -> tuple[CardState, StaticZoneCastPermission, str | None] | None:
    """The permanent whose static permission lets `username` play `land` out
    of their graveyard right now (CR 305.1, CR 611.3d) - Emet-Selch's "play
    cards from your graveyard", Serra Paragon's once-a-turn land or spell,
    Muldrotha's one land a turn - with the permission and the use it spends
    (None for an unlimited one). An unlimited permission is the one to claim
    when two apply."""
    if game is None or land.zone is not Zone.GRAVEYARD or (land.owner or username) != username:
        return None
    used = getattr(game, "once_per_turn_cast_permissions_used", {})
    board = game.computed_board()
    found: list[tuple[CardState, StaticZoneCastPermission, str | None]] = []
    for permanent in game.permanents_controlled_by(username):
        for line in class_gated_lines(permanent, board.of(permanent).abilities):
            permission = static_zone_cast_permission(line)
            if (
                permission is None
                or not permission.plays_lands
                or permission.zone is not Zone.GRAVEYARD
                or not static_permission_applies_now(permission, game, username, permanent)
            ):
                continue
            key: str | None = None
            if permission.per_permanent_type:
                key = f"{once_per_turn_key(permanent)}:{Type.LAND.value}"
            elif permission.once_each_turn:
                key = once_per_turn_key(permanent)
            if key is not None and key in used:
                continue
            found.append((permanent, permission, key))
    return min(found, key=lambda entry: entry[2] is not None, default=None)


def record_graveyard_land_use(game: Any, land: CardState, username: str) -> str | None:
    """Spend the use a static graveyard permission gave the land play (Serra
    Paragon's, Muldrotha's), and return the ability the land gains (CR 611.3d),
    for the caller to stamp once the land has entered (CR 400.7 gives the
    object that enters no memory of what it was granted in the graveyard). A
    land the older "You may play lands from your graveyard." grants is no use
    of either."""
    board = game.computed_board()
    if any(
        plays_lands_from_graveyard_line(line)
        for permanent in game.permanents_controlled_by(username)
        for line in board.of(permanent).abilities
    ):
        return None
    source = static_graveyard_land_source(game, land, username)
    if source is None:
        return None
    _permanent, permission, key = source
    if key is not None:
        game.once_per_turn_cast_permissions_used[key] = 1
    return permission.gained_line


# --------------------------------------------------------------------------
# A permanent's standing permission to play the cards exiled with it
# (CR 601.3, CR 607.2a)
# --------------------------------------------------------------------------

#: A permanent's standing permission to play (cast and/or land-drop) the cards
#: in a pile of exile (CR 601.3, CR 305.1, CR 607.2a), read after the object's
#: own name is normalised to "this `<noun>`" (CR 201.5):
#:
#: - "[During your turn, ]you may play cards exiled with `<this>`." (The
#:   Temporal Anchor) and "You may play lands and cast spells from among cards
#:   exiled with this creature." (Nightveil Specter);
#: - "You may play lands from among cards exiled with this enchantment."
#:   (Hedonist's Trove) - the land half alone;
#: - "You may look at the cards exiled with this enchantment, and you may play
#:   lands and cast spells from among those cards." (Colfenor's Plans);
#: - "During your turn, if an opponent lost life this turn, you may play lands
#:   and cast spells from among cards exiled with this enchantment." (Theater of
#:   Horrors);
#: - "Once during each of your turns, you may play a land or cast a spell from
#:   among the cards exiled with this permanent without paying its mana cost."
#:   (Jacob Hauken);
#: - "You may play lands and cast spells from among cards you own in exile with
#:   croak counters on them." (Grolnok) and "During your turn, you may play
#:   cards you don't own with stash counters on them from exile, and mana of
#:   any type can be spent to cast those spells." (Tinybones) - a pile named by
#:   a counter on the exiled card rather than by what exiled it;
#: - "During your turn, you may cast cards exiled with this permanent and you
#:   may cast them as though they had flash. Mana of any type can be spent to
#:   cast those spells." (Azula);
_PILE_PERMISSION_LEADS = (
    (re.compile(r"^as long as (?P<c>.+?), (?=you may )", re.IGNORECASE), "condition"),
    (re.compile(r"^if (?P<c>.+?), (?=you may )", re.IGNORECASE), "condition"),
    (re.compile(r"^during your turn, ", re.IGNORECASE), "during"),
    (re.compile(r"^once during each of your turns, ", re.IGNORECASE), "once_during"),
    (re.compile(r"^once each turn, ", re.IGNORECASE), "once"),
)
_PILE_PERMISSION_BODY_RE = re.compile(
    r"^you may (?P<look>look at the cards exiled with this \w+, and you may )?"
    r"(?P<act>"
    r"play cards exiled with this \w+"
    r"|play lands and cast spells from among (?P<pile>cards (?P<own>you own )?exiled with this \w+"
    r"|those cards"
    r"|cards you own in exile with (?P<counter>\w+) counters on them)"
    r"|play lands from among cards exiled with this \w+"
    r"|play a land or cast a spell from among the cards exiled with this \w+"
    r"|play cards you don't own with (?P<counter2>\w+) counters on them from exile"
    r"|play a card from exile with an? (?P<counter3>[\w-]+) counter on it "
    r"if it was exiled by an ability you controlled(?P<exiler>)"
    r"|cast cards exiled with this \w+(?P<flash> and you may cast them as though they had flash)?"
    r")"
    r"(?P<free> without paying its mana cost)?"
    r"(?P<any1>, and mana of any type can be spent to cast (?:that|those) spells?)?"
    r"(?P<anycolor>, and you may spend mana as though it were mana of any colou?r "
    r"to cast (?:those spells|it))?"
    r"\.(?P<any2> Mana of any type can be spent to cast those spells\.)?$",
    re.IGNORECASE,
)


class LinkedExilePlayGrant(NamedTuple):
    """`linked_exile_play_grant`'s answer: the permanent whose line lets the
    player play the card, and what that line says."""

    permanent: CardState
    line: "ExilePilePermission"


class ExilePilePermission(EngineModel):
    """One `_PILE_PERMISSION_BODY_RE` line, read."""

    model_config = ConfigDict(frozen=True)

    during_your_turn: bool = False
    once_each_turn: bool = False
    conditions: tuple[str, ...] = ()
    lands: bool = True
    casts: bool = True
    counter: str | None = None
    """The counter kind that names the pile ("croak", "stash"), or None when the
    pile is what the permanent exiled (CR 607.2a)."""
    own_cards_only: bool = False
    not_own_cards: bool = False
    free: bool = False
    any_mana: bool = False
    any_color: bool = False
    """"you may spend mana as though it were mana of any color to cast those
    spells" (Rogue Class, Evelyn; CR 609.4b)."""
    exiled_by_your_ability: bool = False
    """Evelyn: the card was exiled by an ability of a permanent the player
    controls (`ExileAnnotation.linked_permanent_id`)."""
    flash: bool = False
    looks: bool = False


@lru_cache(maxsize=2048)
def exile_pile_permission(
    permanent_name: str, text: str, legendary: bool
) -> ExilePilePermission | None:
    """Read one static line as `_PILE_PERMISSION_BODY_RE`, or None - failing
    closed on a condition this engine does not read."""
    from ..abilities import self_normalized_effect_text

    line, word_condition = strip_ability_word(_REMINDER_TEXT_RE.sub("", text))
    line = " ".join(
        self_normalized_effect_text(permanent_name, line.strip(), legendary=legendary).split()
    )
    conditions: list[str] = [word_condition] if word_condition else []
    during = once = False
    changed = True
    while changed:
        changed = False
        for pattern, kind in _PILE_PERMISSION_LEADS:
            match = pattern.match(line)
            if match is None:
                continue
            changed = True
            line = line[match.end() :]
            if kind == "condition":
                conditions.append(match.group("c").strip())
            elif kind == "during":
                during = True
            else:
                once = True
                during = during or kind == "once_during"
    match = _PILE_PERMISSION_BODY_RE.fullmatch(line)
    if match is None:
        return None
    if any(not cast_condition_readable(condition) for condition in conditions):
        return None
    act = match.group("act").lower()
    counter = (
        match.group("counter") or match.group("counter2") or match.group("counter3") or ""
    ).lower() or None
    return ExilePilePermission(
        during_your_turn=during,
        once_each_turn=once,
        conditions=tuple(conditions),
        lands=not act.startswith("cast"),
        casts=not act.startswith("play lands from"),
        counter=counter,
        own_cards_only=match.group("own") is not None or (counter is not None and "you own" in act),
        not_own_cards="you don't own" in act,
        free=match.group("free") is not None,
        any_mana=match.group("any1") is not None or match.group("any2") is not None,
        any_color=match.group("anycolor") is not None,
        exiled_by_your_ability=match.group("exiler") is not None,
        flash=match.group("flash") is not None,
        looks=match.group("look") is not None,
    )


def play_cards_exiled_with_line(
    permanent_name: str, text: str, *, legendary: bool = True
) -> tuple[bool] | None:
    """`(during_your_turn,)` for an `exile_pile_permission` line of the
    permanent named `permanent_name`, or None."""
    read = exile_pile_permission(permanent_name, text.strip(), legendary)
    return None if read is None else (read.during_your_turn,)


def reads_play_cards_exiled_with_line(card: Card, text: str) -> bool:
    """What `support.py` asks before crediting the line."""
    from ...models.card import Supertype

    return (
        exile_pile_permission(card.name, text, Supertype.LEGENDARY in card.supertypes) is not None
    )


def _pile_membership_holds(
    game: Any, card: CardState, permanent: CardState, read: ExilePilePermission, player: str
) -> bool:
    """Whether `card` is in the pile `read` names for `permanent`: exiled with
    that very object (CR 607.2a, CR 400.7 - `ExileAnnotation.links_to`), or
    bearing the named counter, owned (or not) by `player`."""
    if card.zone is not Zone.EXILE:
        return False
    if read.counter is not None:
        if card.counter_count(read.counter) <= 0:
            return False
        if read.exiled_by_your_ability:
            annotation = card.exile_annotation
            if annotation is None or annotation.linked_permanent_id is None:
                return False
            if not any(
                held.id == annotation.linked_permanent_id
                for held in game.permanents_controlled_by(player)
            ):
                return False
    else:
        annotation = card.exile_annotation
        if annotation is None or not annotation.links_to(permanent.id, permanent.zone_change_stamp):
            return False
    owner = card.owner or player
    if read.own_cards_only and owner != player:
        return False
    return not (read.not_own_cards and owner == player)


def _pile_permissions_for(
    game: Any, card: CardState, player: str
) -> list[tuple[CardState, ExilePilePermission]]:
    """Every `(permanent, permission)` of `player`'s that lets them play `card`
    out of exile right now (before the spell-versus-land and cost questions):
    the pile holds it, "during your turn", the printed conditions and the
    once-each-turn use all hold."""
    if game is None or card.zone is not Zone.EXILE:
        return []
    from ...models.card import Supertype

    found: list[tuple[CardState, ExilePilePermission]] = []
    board = game.computed_board()
    for permanent in game.permanents_controlled_by(player):
        legendary = Supertype.LEGENDARY in permanent.card.supertypes
        for line in class_gated_lines(permanent, board.of(permanent).abilities):
            read = exile_pile_permission(permanent.name, line, legendary)
            if read is None or not _pile_membership_holds(game, card, permanent, read, player):
                continue
            if read.during_your_turn:
                turn = getattr(game, "turn", None)
                if turn is None or turn.active_player != player:
                    continue
            if read.once_each_turn and once_per_turn_key(permanent) in getattr(
                game, "once_per_turn_cast_permissions_used", {}
            ):
                continue
            if not all(
                cast_condition_holds(game, player, condition, permanent)
                for condition in read.conditions
            ):
                continue
            found.append((permanent, read))
    return found


def linked_exile_play_grant(
    game: Any, card: CardState, player: str, *, land: bool = True
) -> "LinkedExilePlayGrant | None":
    """The pile permission of `player`'s that lets them play `card` (as a land
    when `land`, else cast it) out of exile right now, with the permanent that
    prints it; an unlimited permission is the one to claim when two apply."""
    options = [
        (permanent, read)
        for permanent, read in _pile_permissions_for(game, card, player)
        if (read.lands if land else read.casts)
    ]
    if options:
        permanent, read = min(options, key=lambda option: option[1].once_each_turn)
        return LinkedExilePlayGrant(permanent, read)
    return None


def linked_exile_play_source(game: Any, card: CardState, player: str) -> CardState | None:
    """`linked_exile_play_grant`'s permanent, or None."""
    grant = linked_exile_play_grant(game, card, player)
    return grant.permanent if grant is not None else None


#: A permanent's standing permission to cast from its own linked pile (CR
#: 601.3, CR 607.2a), read after the object's own name is normalised to
#: "this `<noun>`" (CR 201.5):
#:
#: - "Once each turn, you may cast a spell with mana value less than or equal
#:   to the number of Elves and Faeries you control from among cards exiled
#:   with Maralen this turn without paying its mana cost." (Maralen, Fae
#:   Ascendant - CR 118.9, and a once-each-turn limit on the permanent);
#: - "During your turn, you may cast creature spells from among cards you own
#:   exiled with this creature by removing three counters from among
#:   creatures you control in addition to paying their other costs." (Dawnhand
#:   Dissident - CR 601.2f's additional cost);
#: - "You may cast spells from among cards exiled with Rona." (Rona, Disciple
#:   of Gix) and Hedonist's Trove's "... You can't cast more than one spell
#:   this way each turn."
_LINKED_EXILE_STATIC_CAST_RE = re.compile(
    r"^(?P<once>once each turn, )?(?P<during>during your turn, )?you may cast "
    r"(?:an? )?(?:(?P<quality>[\w' ,-]+?) )?spells?"
    r"(?: with mana value (?:(?P<mv_n>\d+) or less|less than or equal to (?P<mv_expr>.+?)))?"
    r" from among cards (?P<own>you own )?exiled with this \w+(?P<this_turn> this turn)?"
    r"(?P<free> without paying (?:its|their) mana costs?)?"
    r"(?: by (?P<extra>.+?) in addition to paying (?:its|their) other costs)?"
    r"\.(?P<limit>\s*you can'?t cast more than one spell this way each turn\.)?"
    r"(?:\s*if you cast an? (?:[a-z]+ )?spell this way, that (?:creature|artifact|enchantment|"
    r"permanent) enters with (?:an additional|an?|one) "
    r"(?P<rider>\+1/\+1|[a-z]+) counter on it\.)?$",
    re.IGNORECASE,
)
#: "the number of Elves and Faeries you control" - a count of the permanents
#: carrying any of the listed subtypes (CR 205.3m), each counted once.
_NUMBER_OF_SUBTYPES_YOU_CONTROL_RE = re.compile(
    r"^the number of (?P<first>[A-Za-z]+)(?:,? (?:and|or) (?P<second>[A-Za-z]+))? you control$",
    re.IGNORECASE,
)


class LinkedExileStaticCast(EngineModel):
    """One `_LINKED_EXILE_STATIC_CAST_RE` line, read."""

    model_config = ConfigDict(frozen=True)

    once_each_turn: bool = False
    during_your_turn: bool = False
    quality: str = ""
    max_mana_value: int | None = None
    max_mana_value_expression: str | None = None
    you_own: bool = False
    this_turn: bool = False
    free: bool = False
    additional_cost: str | None = None
    rider_counter: str | None = None
    """The counter kind "If you cast a spell this way, that creature enters
    with a `<kind>` counter on it." puts on the permanent (CR 614.1c)."""


def _count_listed_subtypes(expression: str) -> Callable[[Any, str], int] | None:
    """`_NUMBER_OF_SUBTYPES_YOU_CONTROL_RE`'s count, or the general
    `effects.count_expression` for anything else it reads."""
    from ..effects import _singular_subtype_for_count_expression, count_expression

    match = _NUMBER_OF_SUBTYPES_YOU_CONTROL_RE.fullmatch(expression.strip())
    if match is not None and match.group("second") is not None:
        words = [match.group("first"), match.group("second")]
        subtypes = [_singular_subtype_for_count_expression(word) for word in words]
        if all(subtype is not None for subtype in subtypes):
            wanted = {subtype for subtype in subtypes if subtype is not None}

            def count(game: Any, controller: str) -> int:
                board = game.computed_board()
                return sum(
                    1
                    for permanent in game.permanents_controlled_by(controller)
                    if wanted & {word.lower() for word in board.of(permanent).subtypes}
                )

            return count
    return count_expression(expression)


@lru_cache(maxsize=2048)
def linked_exile_static_cast(
    permanent_name: str, text: str, legendary: bool
) -> LinkedExileStaticCast | None:
    """Read one static line as `_LINKED_EXILE_STATIC_CAST_RE`, or None -
    failing closed on a quality, a bound or an additional cost this cannot
    read."""
    from ..abilities import self_normalized_effect_text
    from ..next_spell import spell_quality_is_readable

    normalized = self_normalized_effect_text(permanent_name, text.strip(), legendary=legendary)
    match = _LINKED_EXILE_STATIC_CAST_RE.fullmatch(" ".join(normalized.split()))
    if match is None:
        return None
    quality = _normalized_spell_quality(match.group("quality"))
    if quality and not spell_quality_is_readable(quality):
        return None
    expression = match.group("mv_expr")
    if expression is not None and _count_listed_subtypes(expression) is None:
        return None
    extra = match.group("extra")
    if extra is not None:
        extra = re.sub(r"^removing\b", "Remove", extra.strip(), flags=re.IGNORECASE)
        extra = re.sub(r"^paying\b", "Pay", extra, flags=re.IGNORECASE)
        if total_cost_for_phrase(extra) is None:
            return None
    return LinkedExileStaticCast(
        once_each_turn=match.group("once") is not None or match.group("limit") is not None,
        during_your_turn=match.group("during") is not None,
        quality=quality,
        max_mana_value=int(match.group("mv_n")) if match.group("mv_n") else None,
        max_mana_value_expression=expression,
        you_own=match.group("own") is not None,
        this_turn=match.group("this_turn") is not None,
        free=match.group("free") is not None,
        additional_cost=extra,
        rider_counter=(match.group("rider") or "").lower() or None,
    )


def reads_linked_exile_static_cast_line(card: Card, text: str) -> bool:
    """What `support.py` asks before crediting the line."""
    from ...models.card import Supertype

    return (
        linked_exile_static_cast(card.name, text, Supertype.LEGENDARY in card.supertypes)
        is not None
    )


def _linked_exile_static_cast_option(
    text: str, game: Any, spell: CardState, caster: str, origin_zone: Zone, permanent: CardState
) -> KeywordCastOption | None:
    """`linked_exile_static_cast`'s grant for `spell`, or None: `spell` is
    face up in exile, exiled with `permanent` (that incarnation, CR 400.7,
    CR 607.2a) - "this turn" when the line says so - owned by the caster when
    it says "cards you own", of the quality named, within the mana value
    bound (CR 202.3, read now), and the once-each-turn use of `permanent`
    not yet spent."""
    from ...models.card import Supertype
    from ..next_spell import spell_has_quality

    if origin_zone is not Zone.EXILE:
        return None
    read = linked_exile_static_cast(
        permanent.name, text, Supertype.LEGENDARY in permanent.card.supertypes
    )
    if read is None or game is None:
        return None
    probe = spell if spell.zone is Zone.EXILE else None
    annotation = probe.exile_annotation if probe is not None else None
    if probe is None or annotation is None or not probe.face_up:
        return None
    if not annotation.links_to(permanent.id, permanent.zone_change_stamp):
        return None
    turn = getattr(game, "turn", None)
    if read.this_turn and (turn is None or annotation.turn_exiled != turn.turns_taken):
        return None
    if read.during_your_turn and (turn is None or turn.active_player != caster):
        return None
    if read.you_own and (spell.owner or caster) != caster:
        return None
    if read.quality and not spell_has_quality(spell, read.quality):
        return None
    if read.max_mana_value is not None and spell.mana_value > read.max_mana_value:
        return None
    if read.max_mana_value_expression is not None:
        counter = _count_listed_subtypes(read.max_mana_value_expression)
        if counter is None or spell.mana_value > counter(game, caster):
            return None
    key = None
    if read.once_each_turn:
        key = once_per_turn_key(permanent)
        if key in getattr(game, "once_per_turn_cast_permissions_used", {}):
            return None
    additional = total_cost_for_phrase(read.additional_cost) if read.additional_cost else None
    return KeywordCastOption(
        keyword=CAST_PERMISSION,
        rule="CR 601.3, CR 607.2a",
        zone=Zone.EXILE,
        pays_mana_cost=not read.free,
        timing=CastTiming.OWN,
        once_per_turn_key=key,
        additional_cost=additional,
        enters_with_counters=(read.rider_counter,) if read.rider_counter else (),
    )


#: "You may cast spells from among cards in exile your opponents own with ice
#: counters on them, and you may spend mana from snow sources as though it
#: were mana of any color to cast those spells." - Draugr Necromancer. CR
#: 601.3's permission over the cards, owned by an opponent (CR 108.3), that
#: carry the named counter, plus CR 609.4b's spend-as-any-color narrowed to
#: snow sources.
_OPPONENTS_EXILE_COUNTER_CAST_RE = re.compile(
    r"^you may cast spells from among cards in exile your opponents own with "
    r"(?P<counter>[a-z+/-]+) counters on them"
    r"(?P<snow>, and you may spend mana from snow sources as though it were mana of any "
    r"color to cast those spells)?\.?$",
    re.IGNORECASE,
)


class OpponentsExileCounterCast(EngineModel):
    """One `_OPPONENTS_EXILE_COUNTER_CAST_RE` line, read."""

    model_config = ConfigDict(frozen=True)

    counter: str
    snow_any_color: bool = False


@lru_cache(maxsize=512)
def opponents_exile_counter_cast(text: str) -> OpponentsExileCounterCast | None:
    match = _OPPONENTS_EXILE_COUNTER_CAST_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    return OpponentsExileCounterCast(
        counter=match.group("counter").lower(), snow_any_color=match.group("snow") is not None
    )


def reads_opponents_exile_counter_cast_line(text: str) -> bool:
    """What `support.py` asks before crediting the line."""
    return opponents_exile_counter_cast(text) is not None


def _opponents_exile_counter_cast_option(
    text: str, game: Any, spell: CardState, caster: str, origin_zone: Zone
) -> KeywordCastOption | None:
    """`opponents_exile_counter_cast`'s grant for `spell`, or None: `spell` is
    in exile, owned by an opponent of the caster, and carries the counter
    (read off the announced copy, since CR 122.2 strips counters when the
    card moves to the stack)."""
    read = opponents_exile_counter_cast(text)
    if (
        read is None
        or game is None
        or origin_zone is not Zone.EXILE
        or spell.zone is not Zone.EXILE
    ):
        return None
    owner = spell.owner or caster
    if owner == caster or read.counter not in spell.counters:
        return None
    return KeywordCastOption(
        keyword=CAST_PERMISSION,
        rule="CR 601.3, CR 609.4b",
        zone=Zone.EXILE,
        pays_mana_cost=True,
        timing=CastTiming.OWN,
        snow_any_color=read.snow_any_color,
    )


def _linked_exile_play_option(
    game: Any, spell: CardState, caster: str, origin_zone: Zone
) -> KeywordCastOption | None:
    """The pile permission's cast half: CR 601.3's permission to cast `spell`
    out of the pile - at its own cost and timing, or free (CR 118.9), or at
    any time (CR 702.8a, "as though they had flash"), or with mana of any type
    (CR 609.4b), as the line reads."""
    if origin_zone is not Zone.EXILE or spell.zone is not Zone.EXILE:
        return None
    options = [
        (permanent, read)
        for permanent, read in _pile_permissions_for(game, spell, caster)
        if read.casts
    ]
    if not options:
        return None
    # An unlimited permission is the one to claim when both apply.
    permanent, read = min(options, key=lambda option: option[1].once_each_turn)
    return KeywordCastOption(
        keyword=CAST_PERMISSION,
        rule="CR 601.3, CR 607.2a",
        zone=Zone.EXILE,
        pays_mana_cost=not read.free,
        timing=CastTiming.FLASH if read.flash else CastTiming.OWN,
        once_per_turn_key=once_per_turn_key(permanent) if read.once_each_turn else None,
        any_color=read.any_color,
        any_type_mana=read.any_mana,
    )


def exiles_spells_cast_this_way(game: Any, caster: str) -> bool:
    """Whether a static ability `caster` has (an emblem's, CR 114.4) says a
    spell cast under its permission is exiled instead of going to the
    graveyard."""
    for emblem in game.emblems_of(caster):
        for ability in parse_abilities(emblem.card):
            if ability.kind is AbilityKind.STATIC and _EXILE_SPELLS_CAST_THIS_WAY.search(
                ability.text or ""
            ):
                return True
    return False


def _granted_option(
    keyword: str,
    printed: str | None,
    zone: Zone,
    face: str,
    raw: str,
    rule: str,
    *,
    any_zone: bool = False,
) -> KeywordCastOption | None:
    """One granted keyword, expanded by the reader that expands printed ones.

    Returns None when the keyword is one `_option_from_keyword` does not hand
    out a cast option for, or when the zone its own rule casts from is not the
    zone the granting sentence named - either way the grant is dropped rather
    than a zone or a cost invented for it.
    """
    option = _option_from_keyword(
        KeywordAbility(
            raw=raw,
            text=raw,
            face=face,
            keyword=keyword,
            canonical=keyword.capitalize(),
            cost=printed,
            cost_is_mana=bool(printed) and _ONLY_MANA_SYMBOLS.match(printed or "") is not None,
        )
    )
    if option is None or (option.zone is not zone and not any_zone):
        return None
    # The keyword written back out the way a card would print it, so the object
    # can carry the grant itself once it is announced (CR 400.7b) - see
    # `KeywordCastOption.granted_line`.
    line = f"{keyword.capitalize()} {printed}" if printed else keyword.capitalize()
    # The granting rule and the keyword's own rule, in that order: one says why
    # this spell has the keyword at all, the other says what the keyword does.
    return option.model_copy(update={"rule": f"{rule}, {option.rule}", "granted_line": line})


def _grant_as_you_cast(
    text: str, spell: CardState, origin_zone: Zone, face: str, raw: str
) -> KeywordCastOption | None:
    """CR 610.5's shape: "... spells you cast from your hand gain evoke {4} as
    you cast them.\""""
    match = _GRANTED_KEYWORD_AS_YOU_CAST.match(text)
    if match is None:
        return None
    zone = _ZONE_WORDS_FOR_GRANTS.get(match.group("zone").lower())
    if zone is None or zone is not origin_zone:
        return None
    if not _spell_matches_grant_filter(spell, match.group("what")):
        return None
    return _granted_option(
        match.group("keyword"),
        match.group("cost").strip() or None,
        zone,
        face,
        raw,
        "CR 610.5",
    )


def _grant_spell_you_cast_has_keyword(
    text: str, spell: CardState, origin_zone: Zone, face: str, raw: str
) -> KeywordCastOption | None:
    """CR 611.3d's shape: "Each creature spell you cast has emerge. The
    emerge cost is equal to its mana cost." (Herigast, Erupting Nullkite) -
    `_grant_on_a_card_in_a_zone`'s own cost-completion tail (Iroh's "The
    flashback cost is equal to that card's mana cost."), read for a spell
    being cast rather than a card sitting in a zone, so there is no zone word
    in the sentence to match against `origin_zone` - the keyword's own rule
    (CR 702.119a: emerge casts from the hand) is what `_granted_option`'s
    own zone check narrows this to, exactly as it does for every grant here.
    """
    match = _GRANTED_KEYWORD_SPELL_YOU_CAST_HAS.match(text)
    plural = False
    if match is None:
        match = _GRANTED_KEYWORD_SPELLS_YOU_CAST_HAVE.match(text)
        plural = True
    if match is None:
        return None
    if plural:
        zone_word = (match.group("zone") or "").lower().removeprefix("your ")
        if zone_word and _ZONE_WORDS_FOR_GRANTS.get(zone_word, Zone.EXILE) is not origin_zone:
            return None
    elif match.group("cond") and not spell.colors:
        return None
    if not _spell_matches_grant_filter(spell, match.group("what")):
        return None
    keyword = match.group("keyword")
    printed = match.group("cost").strip() or None
    if printed is None:
        tail = _COST_IS_THE_CARDS_MANA_COST.search(match.group("tail") or "")
        if tail is None or tail.group("keyword").lower() != keyword.lower():
            return None
        printed = spell.mana_cost or spell.card.mana_cost or None
        if printed is None:
            return None
    return _granted_option(keyword, printed, origin_zone, face, raw, "CR 611.3d")


def _grant_on_a_card_in_a_zone(
    text: str,
    game: Any,
    spell: CardState,
    caster: str,
    origin_zone: Zone,
    face: str,
    raw: str,
) -> KeywordCastOption | None:
    """CR 611.3d's shape: "During your turn, each Lesson card in your graveyard
    has flashback {1}."

    "During your turn" is a condition on the whole continuous effect, so it is
    checked against the turn in progress; a sentence with no such prefix is
    unconditional. A granted keyword printed with no cost of its own takes the
    cost the next sentence names - Iroh's "The flashback cost is equal to that
    card's mana cost." is the only such sentence in this pool, and anything
    else leaves the keyword costless and therefore unread.
    """
    # CR 207.2c: an ability word ("Goblin Formula - ") has no rules meaning.
    line, _ability_word = strip_ability_word(_REMINDER_TEXT_RE.sub("", text))
    match = _GRANTED_KEYWORD_ON_A_CARD_IN_A_ZONE.match(line.strip())
    if match is None:
        return None
    zone = _ZONE_WORDS_FOR_GRANTS.get((match.group("zone") or match.group("zones")).lower())
    if zone is None or zone is not origin_zone:
        return None
    if match.group("during"):
        turn = getattr(game, "turn", None)
        if turn is None or turn.active_player != caster:
            return None
    if (spell.owner or caster) != caster:
        # "in **your** graveyard/hand": CR 108.3's owner, not whoever is
        # asking about an opponent's card.
        return None
    if not _spell_matches_grant_filter(spell, match.group("what") or match.group("whats")):
        return None
    if (
        match.group("ncolors")
        and len(spell.colors) != _EXACT_COLOR_COUNT_WORDS[match.group("ncolors")]
    ):
        return None
    keyword = match.group("keyword")
    printed = match.group("cost").strip() or None
    if printed is None and keyword.lower() not in COSTLESS_GRANTED_KEYWORDS:
        tail = _COST_IS_THE_CARDS_MANA_COST.search(match.group("tail") or "")
        if tail is None or tail.group("keyword").lower() != keyword.lower():
            return None
        printed = spell.mana_cost or spell.card.mana_cost or None
        if printed is None:
            return None
    option = _granted_option(
        keyword, printed, zone, face, raw, "CR 611.3d, CR 400.7g", any_zone=True
    )
    if option is None:
        return None
    if option.zone is zone:
        return option
    # A granted keyword whose own rule casts from another zone - sneak, from
    # the hand - does nothing where it sits unless a "using their
    # `<keyword>` abilities" permission opens this zone to it.
    return _rezoned_by_using(option, spell, zone, _using_keyword_permissions(game, caster))


def reads_granted_zone_keyword_line(card: Card, text: str) -> bool:
    """What `support.py` asks before crediting a `_GRANTED_KEYWORD_ON_A_CARD_
    IN_A_ZONE` line: the keyword expands to a cast option `_option_from_
    keyword` really builds (its cost read, or Iroh's "The flashback cost is
    equal to that card's mana cost." standing in for one), with nothing else
    left unread after it - and the option casts from the zone the line names,
    or the same card prints the "using their `<keyword>` abilities"
    permission that opens that zone to it (Ninja Teen's level 3 pair).
    Without either, a keyword granted to cards in a zone it never casts
    from does nothing, and is not credited."""
    # CR 207.2c: an ability word ("Goblin Formula - ") has no rules meaning,
    # and the live reader sees the line without it (`parse_abilities`).
    line, _ability_word = strip_ability_word(_REMINDER_TEXT_RE.sub("", text))
    match = _GRANTED_KEYWORD_ON_A_CARD_IN_A_ZONE.match(line.strip())
    if match is None:
        return False
    zone = _ZONE_WORDS_FOR_GRANTS.get((match.group("zone") or match.group("zones")).lower())
    if zone is None:
        return False
    keyword = match.group("keyword")
    printed = match.group("cost").strip() or None
    tail = (match.group("tail") or "").strip()
    if printed is None and keyword.lower() in COSTLESS_GRANTED_KEYWORDS:
        if tail:
            return False
    elif printed is None:
        cost_tail = _COST_IS_THE_CARDS_MANA_COST.fullmatch(tail)
        if cost_tail is None or cost_tail.group("keyword").lower() != keyword.lower():
            return False
        printed = "{0}"
    elif tail:
        return False
    option = _granted_option(keyword, printed, zone, card.name, text, "CR 611.3d", any_zone=True)
    if option is None or not option.understood:
        return False
    if option.zone is zone:
        return True
    return any(
        (permission := using_keyword_permission(ability.text or "")) is not None
        and permission.zone is zone
        and permission.keyword == option.keyword.lower()
        for ability in parse_abilities(card)
        if ability.kind is AbilityKind.STATIC
    )


def reads_granted_cast_spell_keyword_line(text: str) -> bool:
    """What `support.py` asks before crediting a `_GRANTED_KEYWORD_SPELL_YOU_
    CAST_HAS` line: the keyword expands to a cast option `_option_from_
    keyword` really builds, its cost either printed inline or completed by a
    second sentence naming the spell's own mana cost (Herigast, Erupting
    Nullkite's "The emerge cost is equal to its mana cost."), with nothing
    else left unread after it. There is no zone word in this shape to check
    against a live spell's `origin_zone` the way `reads_granted_zone_keyword_
    line` does, so this only confirms the keyword itself builds an
    understood option - `granted_cast_options` is what narrows it to the
    keyword's own casting zone at runtime."""
    match = _GRANTED_KEYWORD_SPELL_YOU_CAST_HAS.match(_REMINDER_TEXT_RE.sub("", text).strip())
    if match is None:
        return False
    keyword = match.group("keyword")
    printed = match.group("cost").strip() or None
    tail = (match.group("tail") or "").strip()
    if printed is None:
        cost_tail = _COST_IS_THE_CARDS_MANA_COST.fullmatch(tail)
        if cost_tail is None or cost_tail.group("keyword").lower() != keyword.lower():
            return False
        printed = "{0}"
    elif tail:
        return False
    option = _granted_option(keyword, printed, Zone.HAND, "", text, "CR 611.3d", any_zone=True)
    return option is not None and option.understood


def reads_using_keyword_permission_line(text: str) -> bool:
    """What `support.py` asks before crediting "You may cast `<quality>`
    spells from your graveyard using their `<keyword>` abilities.": the
    quality reads and the keyword is one `_option_from_keyword` builds a cast
    option for (`granted_cast_options` then moves it to the zone)."""
    permission = using_keyword_permission(text)
    if permission is None:
        return False
    option = _granted_option(
        permission.keyword, "{0}", Zone.HAND, "", text, "CR 601.3", any_zone=True
    )
    return option is not None


#: A printed cost that is nothing but mana symbols, the same test
#: `machines/cost.py` makes before handing a phrase to `ManaCost.parse`.
_ONLY_MANA_SYMBOLS = re.compile(r"^(?:\{[^{}]+\}|\s)+$")


# --------------------------------------------------------------------------
# A permission handed out by a resolving effect (CR 601.3, CR 701.18b)
# --------------------------------------------------------------------------


class PlayAction(StrEnum):
    """What an effect's permission actually allows.

    CR 601.1a: "Some effects still refer to 'playing' a card. 'Playing a card'
    means playing that card as a land or casting that card as a spell,
    whichever is appropriate." CR 701.18b says the same thing as a keyword
    action, and CR 701.5b: "To cast a card is to cast it as a spell."

    So the two are **not** interchangeable, which is why they are two values
    rather than one flag: `PLAY` covers CR 701.18a's land drop as well as a
    cast, and `CAST` covers only the cast. Ugin, Eye of the Storms' −11 and
    Ragavan, Nimble Pilferer's combat-damage trigger both print *cast*;
    CR 715.3d's Adventure and CR 702.170's plot-adjacent wordings print
    *play*, and a land found under one of those consumes the land drop
    (CR 305.2a) while a card cast under the other never can.
    """

    CAST = "cast"
    PLAY = "play"


class PlayPermission(EngineModel):
    """CR 601.3's "a rule or effect allows that player to [play] it", handed
    out by a resolving effect to **one specific card**, for a bounded time.

    "A player can begin to cast a spell only if a rule or effect allows that
    player to cast it and no rule or effect prohibits that player from casting
    it." `KeywordCastOption` above is the *static* half of that rule - a grant
    read off a card's own printed keyword, true of every copy of that printing
    forever. This is the other half: a grant a resolving ability creates, that
    names particular objects and then stops.

    Four things the rules keep separate, kept separate here:

    - **which object**, by `card_id` *and* `zone_change_stamp`. CR 400.7: "an
      object that moves from one zone to another becomes a new object", so a
      card that leaves exile and comes back is not the card the permission was
      granted to, and the stamp is what says so. This is also why the
      permission is not a blanket "cards in exile are castable": it names
      instances, so an opponent's card exiled by something else is untouched.
    - **which player**, by `player`. Not the owner: Ragavan exiles the top card
      of the *damaged player's* library, and CR 108.3 leaves that card owned by
      that player while the Ragavan controller is the one permitted to cast it.
    - **cast or play**, by `action` - see `PlayAction`.
    - **what is paid**, by `pays_mana_cost`. False is CR 118.9's "without
      paying its mana cost", which CR 107.3b keeps distinct from an
      alternative cost of some other shape.

    Nothing here loosens timing. CR 117.1a still decides *when* the spell may
    be cast and CR 305.1 still decides when a land may be played, so a sorcery
    under this permission is still a sorcery.
    """

    model_config = ConfigDict(frozen=True)

    card_id: UUID
    zone_change_stamp: UUID
    """CR 400.7's identity check: the value `CardState.zone_change_stamp` held
    when the permission was granted. A new stamp means a new object."""
    player: str
    """Who may play it - CR 108.3's owner is a different question."""
    zone: Zone = Zone.EXILE
    action: PlayAction = PlayAction.CAST
    pays_mana_cost: bool = True
    """False is CR 118.9's "without paying its mana cost"."""
    flashback: bool = False
    """Whether this grant *is* CR 702.34a's flashback, handed out as a
    `PlayPermission` rather than read off a printed keyword line - Past in
    Flames' "Each instant and sorcery card in your graveyard gains flashback
    until end of turn. The flashback cost is equal to its mana cost." and the
    spell Flashback's "Target instant or sorcery card in your graveyard gains
    flashback ..." (both texts confirmed with `resolve_cards`) each mint one
    of these (`machines/effects.py`'s `_parse_grant_flashback_clause` and
    `_parse_each_graveyard_instant_sorcery_gains_flashback_clause`).

    Underworld Breach is **not** one of these and must not be added here: its
    text grants *escape*, not flashback - "Each nonland card in your graveyard
    has escape. The escape cost is equal to the card's mana cost plus exile
    three other cards from your graveyard." - which is a different keyword
    with a different cost shape, and it is banned in Modern besides.

    CR 702.34a is one clause naming two static abilities together: "'Flashback
    [cost]' means 'You may cast this card from your graveyard ... by paying
    [cost] rather than paying its mana cost' and 'If the flashback cost was
    paid, exile this card instead of putting it anywhere else any time it
    would leave the stack.'" CR 611.3d is what lets a static ability *grant*
    "an ability to a permanent spell or card that allows it to be cast" at
    all - it says nothing narrows the grant to only the first half of what the
    keyword means, so a granted flashback is still flashback, second clause
    included, once `pays_mana_cost=True` here means the flashback cost (equal
    to the mana cost, by both grants' own second sentence) was in fact what
    was paid. `Casting.cast()` reads this to write `CastRecord.keyword =
    "Flashback"` even though no keyword was announced, which is the only
    thing `machines/replacement.py`'s exile-on-leaving-the-stack check
    (`_stack_replacements`) actually looks at."""
    source_name: str = ""
    """The card whose ability handed this out, for the error message."""
    rule: str = "CR 601.3"
    cost_increase: ManaCost | None = None
    """"A spell cast this way costs {N} more to cast." - Elite Spellbinder's
    and Invasion of Gobakhan's own rider on this exact permission shape (CR
    601.2f's cost increase, CR 118.7), scoped to *this one grant* rather than
    a board-wide static (`Game.static_cost_modifiers_for`, which nothing
    permanent-specific like this belongs in): the exiled card costs more
    only when cast under this permission, not from any other zone it might
    somehow also be legally cast from. Read by `Casting.total_cost`, folded
    into its `increases` the same way `cost_increases` already is, only when
    `permission_used` is this grant."""
    any_type_mana: bool = False
    """"... and mana of any type can be spent to cast it/that spell/them" -
    Null Summoner's, Hostage Taker's, Gonti, Lord of Luxury's, and roughly
    three dozen other real printings' own trailing rider on this exact grant
    shape. Read by `Casting._determine_cost`, which - only when this is set -
    prices the payment against the total's own *mana value* (CR 202.3, every
    colored/generic symbol collapsed to one count) rather than the printed
    colors, so any color in the pool can pay any symbol; the spell's own
    printed mana cost is untouched everywhere else (CR 202.3b: what a card
    "would cost" is still what is printed)."""
    exile_instead_of_graveyard: bool = False
    """"If that spell would be put into a graveyard, exile it instead." -
    Dire Fleet Daredevil's, Nita, Forum Conciliator's own rider on this exact
    grant shape (CR 604.5). Read by `machines/replacement._stack_
    replacements` off `CastRecord.exile_instead_of_graveyard`, which
    `Casting.cast()` copies from here the same way it already copies
    `flashback` onto `CastRecord.keyword`."""
    condition: str | None = None
    """A live board condition this permission is only usable while true -
    Null Summoner's own "Threshold — As long as there are seven or more
    cards in your graveyard, you may cast the exiled card". `None` for an
    unconditional grant (every other printing this project already reads).
    Checked by `why_not` through `Game.condition_holds`, the same reader
    "Activate only if <condition>" (CR 602.5b) already shares - an
    unrecognised condition refuses the cast rather than allowing it
    unchecked, the same fail-closed default that reader already gives."""
    until_end_of_turn: bool = True
    """CR 514.2: "all 'until end of turn' and 'this turn' effects end" in the
    cleanup step. `Game.cleanup_step` drops these there."""
    granted_turns_taken: int | None = None
    """`TurnMachine.turns_taken` when it was granted, so the permission can
    tell "this turn" from "a later turn" even in a game driven step by step
    without ever reaching a cleanup step. CR 500.7's extra turn is why this is
    `turns_taken` and not the turn number or the active seat."""
    expires_end_of_next_turn: bool = False
    """"Until the end of your next turn" (Wrenn's Resolve, Reckless Impulse) -
    a longer sibling of the plain `until_end_of_turn` above: the grant
    survives the granting turn's own cleanup, survives every turn in between
    that is not `player`'s, and only actually drops at the cleanup of the
    *next* turn `player` is active for. When this is set, `until_end_of_turn`
    is left `False` so `Game.cleanup_step`'s ordinary CR 514.2 sweep leaves
    the permission alone; `Game.begin_turn_for` and `Game.cleanup_step` drop
    it themselves, keyed off `owner_next_turn_started` below, rather than off
    a precomputed `turns_taken` target - CR 500.7's extra turns and
    multiplayer's uneven rotation both mean "two turns from now" is not a
    fixed number of turns, but "the next time it is `player`'s turn" is
    always answerable by watching whose turn is beginning.
    `PlayPermission.expired` never reports this kind expired on its own
    (list membership is what removes it); this is why `expired` below simply
    returns `False` for it rather than trying to recompute the same answer
    two ways."""
    owner_next_turn_started: bool = False
    """Set by `Game.begin_turn_for` the moment `player`'s own next turn
    begins (CR 500.7-safe: watches for `player` becoming active again, not a
    turn count) - `Game.cleanup_step` drops the permission once this is set
    and `player` is active again at a *later* cleanup step, i.e. that same
    turn's own cleanup. Meaningless unless `expires_end_of_next_turn` is."""
    immediate: bool = False
    """Whether this grant is CR 117.2e's "instructed by a resolving ability"
    shape rather than an explicit "until end of turn" duration printed on a
    card.

    CR 117.1's own preamble: "**Unless a spell or ability is instructing a
    player to take an action**, which player can take actions at any given
    time is determined by a system of priority." CR 117.2e: "Resolving spells
    and abilities may instruct players to make choices or take actions...
    Even if a player is doing so, no player has priority while a spell or
    ability is resolving." Suspend's third ability (CR 702.62a) is exactly
    that shape - "you may play it... If you don't, it remains exiled" is the
    ability's own resolution instructing the cast, not a standing grant that
    survives into the ordinary priority system afterward, unlike Ugin, Eye of
    the Storms' "−11" and Ragavan, Nimble Pilferer's trigger, which both print
    the words "**Until end of turn**" and so *do* hand out a permission good
    for the rest of the priority-driven turn (CR 514.2 is what ends those).
    An `immediate` grant is good only for the step it was granted in
    (`granted_step`) - once the game has moved on to another step, whatever
    priority the instructing ability's own resolution briefly stood in for
    has already passed, and CR 702.62a's own "if you don't, it remains
    exiled" has already taken effect."""
    granted_step: Step | None = None
    """The `TurnMachine.step` `immediate` is scoped to - meaningless unless
    `immediate` is set."""
    until_next_turn_of: str | None = None
    """Set for CR 611.2a's "until the end of your next turn" duration (Hex
    Magic) rather than a plain "until end of turn" - names whose next turn
    ends the grant, mirroring `machines.layers.ContinuousEffect.
    until_next_turn_of` and `machines.casting_restrictions.CastingRuleEffect.
    until_next_turn_of`, both of which already reuse `Duration.
    UNTIL_YOUR_NEXT_TURN` for the identical wording elsewhere.

    Dropped by `Game.begin_turn_for` the instant that player's next turn
    would begin (CR 611.2a, its own stated duration), the same moment those
    other two stores drop theirs - not by `expired()`'s own `granted_turns_
    taken` comparison, which only ever measures "the turn it was granted on
    is over" (CR 514.2) and has no notion of *whose* turn is next. A
    permission with this set also
    carries `until_end_of_turn=False`, so `Game.cleanup_step`'s own "until
    end of turn" sweep leaves it alone on the turn it was granted."""

    until_next_end_step_of: str | None = None
    """Set for "until your next end step" (Riveteers Charm's second mode,
    Haste Magic) - names whose end step ends the grant. CR 611.2a: the
    effect "lasts as long as stated", and what is stated is the *beginning*
    of that player's next end step, not a cleanup: the grant is gone the
    moment that step begins (`Game._note_step_began`, and `expired` below for
    a game whose pointer was moved without that hook). An opponent's end
    step never ends it, and an end step that had already begun when the
    grant was made (`granted_turns_taken`/`granted_step`) is not the "next"
    one. Carries `until_end_of_turn=False`, so `Game.cleanup_step`'s CR 514.2
    sweep leaves it alone on the turn it was granted."""

    pays_life_for_mana_value: bool = False
    """"If you cast a spell this way, pay life equal to its mana value rather
    than pay its mana cost." (Inside Information, Nashi, Moon Sage's Scion) -
    CR 118.9's alternative cost, one the permission requires (CR 118.9b), so
    `pays_mana_cost` is `False` beside it: the mana cost is replaced, not
    waived. `Casting.total_cost` adds the life (CR 119.4) from the spell's
    mana value on the stack (CR 202.3e) when the total cost is determined
    (CR 601.2f). A land played under the same grant pays nothing."""
    choice_group: UUID | None = None
    """"You may play **one of** those cards" (Nashi, Moon Sage's Scion): every
    permission handed out by the one instruction carries the same id, and the
    first card played or cast under any of them ends the rest
    (`Game.spend_play_permission_choice`). `None` for a grant that covers
    each card on its own ("those cards")."""
    while_controlling: str | None = None
    """"For as long as you control this creature" (Taster of Wares) - the
    permanent as that object (`once_per_turn_key`'s `"<id>:<stamp>"`, CR
    400.7) that `player` has to control for the permission to be usable
    (CR 611.2b); once it leaves, or changes control, the card is no longer
    castable this way. `None` for every other grant. Carries
    `until_end_of_turn=False`: it is not a one-turn grant."""
    bottom_if_unused: bool = False
    """Always `False` now, kept because consumers read it. Cascade used to set
    it for a hit left in exile under a permission; cascade now casts the hit
    during its own resolution (`Game.cast_during_resolution`, CR 608.2g) and
    bottoms what was not cast at once (CR 702.85a), so no grant sets it."""

    def names(self, card: CardState) -> bool:
        """Whether this permission is about that exact object (CR 400.7)."""
        return card.id == self.card_id and card.zone_change_stamp == self.zone_change_stamp

    def expired(self, game: Any = None) -> bool:
        """CR 514.2: whether the turn it was granted on is over, or - for an
        `immediate` grant - whether CR 117.2e's own resolution-instructed
        window (scoped to `granted_step`) has already closed."""
        turn = getattr(game, "turn", None)
        if self.immediate and self.granted_step is not None:
            if turn is None:
                return False
            return turn.step is not self.granted_step
        if self.expires_end_of_next_turn:
            # Never expired by this lazy check - removal is entirely
            # `Game.begin_turn_for`/`Game.cleanup_step`'s job, per
            # `expires_end_of_next_turn`'s own docstring.
            return False
        if self.until_next_end_step_of is not None:
            return self.reached_next_end_step(game)
        if not self.until_end_of_turn or self.granted_turns_taken is None:
            return False
        if turn is None:
            return False
        return int(turn.turns_taken) != self.granted_turns_taken

    def reached_next_end_step(self, game: Any = None) -> bool:
        """Whether the end step `until_next_end_step_of` names has begun: that
        player is active, the turn is in its end step (or past it, in
        cleanup), and that end step is not one the grant was made during."""
        turn = getattr(game, "turn", None)
        if self.until_next_end_step_of is None or turn is None:
            return False
        if turn.active_player != self.until_next_end_step_of:
            return False
        if turn.step not in (Step.END_STEP, Step.CLEANUP):
            return False
        granted_in_this_ending_phase = self.granted_turns_taken == int(
            turn.turns_taken
        ) and self.granted_step in (Step.END_STEP, Step.CLEANUP)
        return not granted_in_this_ending_phase

    def why_not(
        self,
        card: CardState,
        player: str,
        game: Any = None,
        *,
        action: PlayAction = PlayAction.CAST,
    ) -> str | None:
        """Why this permission does not allow that player that action, or None.

        Mirrors `KeywordCastOption.why_not`: CR 601.3's permission first,
        everything else after. Timing is deliberately **not** asked here - a
        permission to play is not a permission to ignore CR 117.1a - and is
        left to `why_cannot_cast_now` and `Game.why_cannot_play_land`.
        """
        if not self.names(card):
            return f"{self.source_name}'s permission is not about this copy of {card.name}"
        if self.player != player:
            return (
                f"{self.source_name} let {self.player} {self.action.value} {card.name}, "
                f"not {player} ({self.rule})"
            )
        if card.zone is not self.zone:
            return (
                f"{self.source_name} let {self.player} {self.action.value} {card.name} from "
                f"the {self.zone.value}, but it is in the {card.zone.value} ({self.rule})"
            )
        if self.expired(game):
            if self.immediate:
                return (
                    f"{self.source_name}'s permission to {self.action.value} {card.name} was "
                    f"CR 117.2e's own resolution-instructed window, not a standing grant, and "
                    f"the game has since moved past the step it was granted in"
                )
            if self.until_next_end_step_of is not None:
                return (
                    f"{self.source_name}'s permission to {self.action.value} {card.name} lasted "
                    f"until {self.until_next_end_step_of}'s next end step, which has begun "
                    f"(CR 611.2a)"
                )
            return (
                f"{self.source_name}'s permission to {self.action.value} {card.name} lasted "
                f"until end of turn and that turn is over (CR 514.2)"
            )
        if self.while_controlling is not None and not _controls_that_object(
            game, player, self.while_controlling
        ):
            return (
                f"{self.source_name}'s permission to {self.action.value} {card.name} lasts only "
                f"for as long as {player} controls {self.source_name} (CR 611.2b)"
            )
        if self.condition is not None:
            held = (
                None if game is None else game.condition_holds(player, self.condition, source=card)
            )
            if held is None:
                return (
                    f'{self.source_name}\'s condition "as long as {self.condition}" is not '
                    f"read by this engine, so the permission is refused rather than allowed "
                    f"unchecked ({self.rule})"
                )
            if not held:
                return (
                    f"{self.source_name}'s permission to {self.action.value} {card.name} "
                    f"only applies as long as {self.condition}, which is not true right now "
                    f"({self.rule})"
                )
        if action is PlayAction.PLAY and self.action is PlayAction.CAST:
            # CR 701.5b's "cast it as a spell" is narrower than CR 701.18b's
            # "play that card as a land or cast that card as a spell": a
            # permission that says *cast* never reaches the land drop.
            return (
                f"{self.source_name} let {self.player} cast {card.name}, which is not "
                f"permission to play it as a land (CR 601.1a, CR 701.18b)"
            )
        return None


def _controls_that_object(game: Any, player: str, key: str) -> bool:
    """Whether `player` controls, on the battlefield, the object `key`
    (`once_per_turn_key`'s `"<id>:<stamp>"`) names - that incarnation of it
    (CR 400.7)."""
    if game is None:
        return False
    for permanent in game.permanents_controlled_by(player):
        if once_per_turn_key(permanent) == key:
            return True
    return False


def play_permissions_on(game: Any, card: CardState) -> list[PlayPermission]:
    """Every permission recorded against that exact object (CR 400.7)."""
    if game is None:
        return []
    return [
        permission for permission in getattr(game, "play_permissions", []) if permission.names(card)
    ]


def usable_play_permission(
    game: Any,
    card: CardState,
    player: str,
    action: PlayAction = PlayAction.CAST,
) -> PlayPermission | None:
    """The first permission that lets `player` take `action` with `card`, or None."""
    for permission in play_permissions_on(game, card):
        if permission.why_not(card, player, game, action=action) is None:
            return permission
    return None


#: One printed hexproof ability: plain (CR 702.11b) when it names no quality,
#: or CR 702.11d's "hexproof from [quality]" when it does. The quality run stops
#: at the end of the sentence, so a line that continues past it does not bleed
#: into the list.
_HEXPROOF_ABILITY = re.compile(r"\bhexproof\b(?:\s+from\s+(?P<qualities>[^.;\n]+))?", re.IGNORECASE)

#: CR 207.2 reminder text, which restates the ability in words that would parse
#: as a second copy of it.
_REMINDER_TEXT = re.compile(r"\([^)]*\)")

#: CR 702.11f's shorthand, in either printed spelling: "from A and from B", and
#: the list form "from A, B, and C" that Nevinyrral, Urborg Tyrant prints.
_QUALITY_SEPARATOR = re.compile(r",\s*|\s+and\s+from\s+|\s+and\s+|\s+or\s+", re.IGNORECASE)

#: What is left at the front of a list item once the comma took the separator:
#: "artifacts, creatures, and enchantments" splits on the commas, so the last
#: item still carries its conjunction.
_QUALITY_PREFIX = re.compile(r"^(?:and|or|from)\s+", re.IGNORECASE)

#: The colour each quality word names (CR 105.1). Colorless is not a colour
#: (CR 105.2c) and is deliberately absent.
_COLOR_WORDS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}

#: CR 105.2a "A monocolored object is exactly one of the five colors." and
#: CR 105.2b "A multicolored object is two or more of the five colors." - a
#: colour *count*, not a colour word, so a Dragonfire Blade-equipped creature
#: ("hexproof from monocolored") is checked against the spell's own colour
#: count rather than `_COLOR_WORDS`. Kept as its own small copy here, the same
#: way `_split_protection_qualities` in `machines/layers.py` keeps its own
#: rather than importing `machines/effects.py`'s `_COLOR_COUNT_WORDS`: that
#: module imports from this one, so a reverse import would cycle.
_COLOR_COUNT_WORDS: dict[str, Callable[[int], bool]] = {
    "monocolored": lambda count: count == 1,
    "multicolored": lambda count: count >= 2,
}


def hexproof_abilities_in(
    lines: Iterable[str], *, keyword_lines_only: bool = True
) -> tuple[bool, list[str]]:
    """Whether these ability lines carry plain hexproof, and every quality
    they carry hexproof from (CR 702.11b, CR 702.11d, CR 702.11f).

    Read off ability *text*, never off Scryfall's flattened `keywords` array:
    that array lists a bare "Hexproof" alongside "Hexproof from" on
    Nevinyrral, Urborg Tyrant, whose only printed hexproof is "Hexproof from
    artifacts, creatures, and enchantments". Trusting it granted CR 702.11b's
    full hexproof to a permanent that never had it.

    CR 702.11f splits "from A and from B" (and the list form "from A, B, and
    C") into one ability per quality; CR 702.11h makes a repeated quality
    redundant, so each appears once.

    Only a CR 702.1 keyword line - "only the name of the ability", no
    sentence - is hexproof the object itself has. A statement that merely
    mentions the word is a static ability (CR 604.1) granting or removing it
    elsewhere: Kaito, Bane of Nightmares' "During your turn, ... he's a 3/4
    Ninja creature and has hexproof.", Asceticism's "Creatures you control
    have hexproof.", Shadowspear's "... lose hexproof ...". Whatever such a
    statement does grant reaches the permanent as its own keyword line on the
    computed board (layer 6), which this then reads. `keyword_lines_only=False`
    is for the card-support audit, which asks what qualities a printing
    mentions at all.
    """
    plain = False
    qualities: list[str] = []
    for line in lines:
        # Reminder text spells the ability out again in a form that would be
        # parsed as a second, wrong copy of it (CR 207.2).
        text = _REMINDER_TEXT.sub("", line).strip()
        if keyword_lines_only and (":" in text or "." in text):
            continue
        for match in _HEXPROOF_ABILITY.finditer(text):
            raw = match.group("qualities")
            if raw is None:
                plain = True
                continue
            for quality in hexproof_qualities_in(raw):
                if quality not in qualities:
                    qualities.append(quality)
    return plain, qualities


#: "You have hexproof." (Leyline of Sanctity, Aegis of the Gods), "You have
#: shroud." (True Believer, Ivory Mask) - a static ability granting its
#: controller CR 702.11c's hexproof or CR 702.18a's shroud "or player", with
#: CR 702.11d's "from [quality]" read too. Matched after reminder text is gone.
_PLAYER_KEYWORD_GRANT_LINE = re.compile(
    r"^you have (?P<keyword>hexproof|shroud)(?: from (?P<qualities>[^.;]+))?\.?$",
    re.IGNORECASE,
)


def player_keyword_grant_of_line(line: str) -> tuple[str, list[str]] | None:
    """The player hexproof or shroud a static line grants its controller -
    ("hexproof", []) for plain hexproof, ("hexproof", [qualities]) for CR
    702.11d's variant, ("shroud", []) - or None for any other line."""
    match = _PLAYER_KEYWORD_GRANT_LINE.fullmatch(_REMINDER_TEXT.sub("", line).strip())
    if match is None:
        return None
    keyword = match.group("keyword").lower()
    raw = match.group("qualities")
    if keyword == "shroud":
        return ("shroud", []) if raw is None else None
    return keyword, [] if raw is None else hexproof_qualities_in(raw)


#: CR 702.11g: "'Hexproof from each [characteristic]' is shorthand for
#: 'hexproof from [quality A],' 'hexproof from [quality B],' and so on for each
#: possible quality the listed characteristic could have" - Breaker of
#: Creation's "Hexproof from each color" is one hexproof per colour (CR 105.1;
#: colorless is not a colour, CR 105.2c).
_EACH_COLOR_QUALITIES = ("white", "blue", "black", "red", "green")


def hexproof_qualities_in(raw: str) -> list[str]:
    """CR 702.11f's shorthand, split: "blue and from black" -> blue, black;
    "artifacts, creatures, and enchantments" -> each of the three; and CR
    702.11g's "each color" -> each of the five colours."""
    qualities: list[str] = []
    for part in _QUALITY_SEPARATOR.split(raw):
        quality = _QUALITY_PREFIX.sub("", part.strip().strip(",.").strip()).strip()
        expanded = _EACH_COLOR_QUALITIES if quality.lower() == "each color" else (quality,)
        for each in expanded:
            if each and each not in qualities:
                qualities.append(each)
    return qualities


def has_quality(
    quality: str,
    *,
    colors: Iterable[Color],
    types: Iterable[Type],
    subtypes: Iterable[str] = (),
    supertypes: Iterable[object] = (),
) -> bool:
    """Whether an object with these characteristics is of the stated quality
    (CR 702.11d's "[quality] spells" and "[quality] sources").

    A quality "is usually a color ... but can be any characteristic value or
    information" (CR 702.16a, protection's own wording for the same idea).
    Card types, subtypes and supertypes are stated in the plural on the card
    ("hexproof from creatures"), so the trailing "s" comes off first; a colour
    count ("monocolored") is CR 105.2a/105.2b's. Anything else comes back
    False and is not enforced.
    """
    word = quality.strip().lower().removesuffix("s")
    color_list = list(colors)
    try:
        card_type = Type(word)
    except ValueError:
        card_type = None
    if card_type is not None:
        return card_type in tuple(types)
    color = _COLOR_WORDS.get(word)
    if color is not None:
        return color in color_list
    color_count = _COLOR_COUNT_WORDS.get(word)
    if color_count is not None:
        return color_count(len(color_list))
    if any(word == subtype.lower() for subtype in subtypes):
        return True
    return any(word == str(supertype).lower() for supertype in supertypes)


def granted_optional_additional_costs(
    game: Any, card: CardState, caster: str
) -> list[OptionalAdditionalCost]:
    """The optional additional costs another permanent's grant gives `card`
    if `caster` cast it from where it is now - casualty from "Each instant
    and sorcery spell you cast has casualty 1." (`machines/spell_grants.py`).
    `optional_additional_costs`' game-aware twin: the printed half cannot
    know what the board grants."""
    if game is None:
        return []
    printed = len(printed_casualty_numbers(card.card))
    granted_conspire = conspire_count(game, card, caster, card.zone) - printed_conspire_count(
        card.card
    )
    from .granted_life_costs import granted_life_costs

    return (
        [
            casualty_cost_option(number)
            for number in casualty_numbers(game, card, caster, card.zone)[printed:]
        ]
        + [conspire_cost_option() for _ in range(max(granted_conspire, 0))]
        + [
            OptionalAdditionalCost(keyword=None, cost=f"pay {grant.life} life", rule="CR 118.8b")
            for grant in granted_life_costs(game, card, caster)
        ]
    )


def has_flash(card: Card) -> bool:
    """Whether this printing has flash (CR 702.8a).

    "Flash is a static ability that functions in any zone from which you could
    play the card it's on. 'Flash' means "You may play this card any time you
    could cast an instant.""

    Read off the printing's own Scryfall `keywords`, like every other keyword in
    this engine - nothing grants or removes it, because there are no layers for
    keywords.
    """
    return any(keyword.lower() == "flash" for keyword in card.keywords)


#: Bard's Company's own "You may cast this spell as though it had flash if
#: you control a Human." - CR 702.8a's flash exception, worded as a
#: conditional grant on the spell's own printed text rather than the bare
#: "Flash" keyword `has_flash` reads. The condition is captured whole and
#: handed to `Game.condition_holds`, the same reader every other "if
#: `<condition>`" clause in this engine already goes through (Ghalta the
#: Immovable's own self cost reduction among them) - a condition that reader
#: does not know is simply not a grant, never a guessed permission.
_CONDITIONAL_FLASH_RES = (
    re.compile(
        r"^you may cast this (?:spell|creature) as though it had flash if (?P<condition>[^.]+)\.?$",
        re.IGNORECASE,
    ),
    # Dragon Grip (Ferocious), Serpent of the Pass: "If `<condition>`, you may
    # cast this spell as though it had flash." and Hungering Yeti's "As long as
    # `<condition>`, ..." - the same grant, the condition first.
    re.compile(
        r"^(?:if|as long as) (?P<condition>.+?), you may cast this (?:spell|creature) "
        r"as though it had flash\.?$",
        re.IGNORECASE,
    ),
    # Qasali Ambusher: the same grant, riding on a free cast.
    re.compile(
        r"^if (?P<condition>.+?), you may cast this (?:spell|creature) without paying its "
        r"mana cost and as though it had flash\.?$",
        re.IGNORECASE,
    ),
    # Supernatural Rescue: "This spell has flash as long as you control a
    # Spirit." - the grant worded as the spell's own static ability (CR 604.2,
    # CR 702.8a), so the same cast-time condition read as the others above.
    re.compile(
        r"^this (?:spell|creature) has flash as long as (?P<condition>[^.]+)\.?$",
        re.IGNORECASE,
    ),
)
_CONDITIONAL_FREE_CAST_AND_FLASH_RE = _CONDITIONAL_FLASH_RES[2]


def conditional_flash_condition(text: str) -> str | None:
    """The condition of a "You may cast this spell as though it had flash if
    `<condition>`." line (or its "If `<condition>`, you may cast this spell as
    though it had flash." / "As long as `<condition>`, ..." / "Ferocious - If
    ..." wordings) printed on this spell's own text, or `None` if the text
    carries no such line.

    Read one printed line at a time (never the whole multi-line text as one
    regex) the same way `machines/cost.py`'s per-line self-reduction reader
    does, since the grant is always its own sentence.
    """
    for line in (text or "").split("\n"):
        stripped, _ability_word = strip_ability_word(_REMINDER_TEXT_RE.sub("", line))
        for pattern in _CONDITIONAL_FLASH_RES:
            match = pattern.fullmatch(stripped)
            if match is not None:
                return match.group("condition").strip()
    return None


def conditional_free_cast_condition(text: str) -> str | None:
    """Qasali Ambusher's "If `<condition>`, you may cast this creature without
    paying its mana cost and as though it had flash." - the condition, or
    None: CR 118.9's alternative cost of nothing, offered while it holds
    (`Casting.alternative_costs`)."""
    for line in (text or "").split("\n"):
        match = _CONDITIONAL_FREE_CAST_AND_FLASH_RE.fullmatch(
            strip_ability_word(_REMINDER_TEXT_RE.sub("", line))[0]
        )
        if match is not None:
            return match.group("condition").strip()
    return None


def conditional_free_cast_unavailable(
    game: Any, caster: str, spell: CardState, origin_zone: Zone, condition: str
) -> str | None:
    """Why Qasali Ambusher's conditional free cast is not offered right now
    (CR 118.9, CR 604.6), or None: the spell is in the zone it is cast from
    and the printed condition holds."""
    if spell.zone is not origin_zone:
        return (
            f"{spell.name} is in the {spell.zone.value}, not the {origin_zone.value} it is "
            f"being cast from (CR 604.6)"
        )
    if not cast_condition_holds(game, caster, condition, spell):
        return f"{spell.name} can be cast for free only if {condition}, and that is not so"
    return None


#: "You may cast `<quality>` spells as though they had flash." (Vivien,
#: Champion of the Wilds: creature spells; Raff Capashen: historic spells;
#: Gandalf the White: "legendary spells and artifact spells") - CR 702.8a's
#: flash, granted to a quality of the controller's spells by a static ability
#: (CR 611.3d), optionally "As long as `<condition>`, ...". The unqualified
#: "You may cast spells as though they had flash." is `Game.
#: has_static_spells_flash_grant`'s.
_QUALITY_FLASH_GRANT_RE = re.compile(
    r"^(?:as long as (?P<condition>.+?), )?you may cast (?P<quality>[\w' ,-]+?) spells "
    r"as though they had flash\.?$",
    re.IGNORECASE,
)


@lru_cache(maxsize=1024)
def quality_flash_grant(text: str) -> tuple[Callable[[CardState], bool], str | None] | None:
    """The spell predicate and the optional condition of a
    `_QUALITY_FLASH_GRANT_RE` line, or None (also for a quality or condition
    this engine does not read)."""
    line, word_condition = strip_ability_word(_REMINDER_TEXT_RE.sub("", text))
    match = _QUALITY_FLASH_GRANT_RE.fullmatch(line)
    if match is None:
        return None
    predicate = spell_quality_predicate(normalized_spell_quality(match.group("quality")))
    if predicate is None:
        return None
    conditions = [c.strip() for c in (word_condition, match.group("condition")) if c]
    if any(not cast_condition_readable(c) for c in conditions):
        return None
    return predicate, " and ".join(conditions) if conditions else None


def reads_quality_flash_grant_line(text: str) -> bool:
    """What `support.py` asks before crediting the line."""
    return quality_flash_grant(text) is not None


def has_quality_flash_grant(game: Any, caster: str, spell: CardState) -> bool:
    """Whether a permanent `caster` controls lets `spell` be cast as though it
    had flash right now (CR 702.8a, CR 611.3d): a `quality_flash_grant` line on
    its computed abilities (CR 613.1f) whose quality the spell has and whose
    condition holds."""
    if game is None:
        return False
    board = game.computed_board()
    for permanent in game.permanents_controlled_by(caster):
        for line in board.of(permanent).abilities:
            read = quality_flash_grant(line)
            if read is None:
                continue
            predicate, condition = read
            if predicate(spell) and (
                condition is None or cast_condition_holds(game, caster, condition, permanent)
            ):
                return True
    return False


#: "If this spell was kicked, it has split second." (Molten Disaster) - the
#: conditional grant of CR 702.61a's keyword, a static ability of the spell
#: itself that functions while it is on the stack (CR 604.5).
_CONDITIONAL_SPLIT_SECOND_RE = re.compile(
    r"^if (?P<condition>[^.,]+), (?:it|this spell) has split second\.?$", re.IGNORECASE
)


def conditional_split_second_condition(text: str) -> str | None:
    """The condition of an "If `<condition>`, it has split second." sentence
    printed on this spell's own text, or `None` if the text carries none.
    Read one printed line at a time, like `conditional_flash_condition`."""
    for line in (text or "").split("\n"):
        match = _CONDITIONAL_SPLIT_SECOND_RE.fullmatch(re.sub(r"\s*\([^)]*\)", "", line).strip())
        if match is not None:
            return match.group("condition").strip()
    return None


def _has_conditional_split_second(game: Any, spell: CardState) -> bool:
    """Whether `spell`, on the stack, holds a conditional split second grant
    whose condition is true now (read off its cast record like any other
    "this spell was kicked" condition)."""
    text = spell.card.oracle_text or ""
    if "split second" not in text.lower():
        return False
    condition = conditional_split_second_condition(text)
    if condition is None or spell.controller is None:
        return False
    return game.condition_holds(spell.controller, condition, spell) is True


def has_split_second(card: Card) -> bool:
    """Whether this printing has split second (CR 702.61a), read the same
    way `has_flash` reads its own keyword - off the printing's own Scryfall
    `keywords`, never granted or removed by a layer."""
    return any(keyword.lower() == "split second" for keyword in card.keywords)


def split_second_restriction_source(game: Any) -> str | None:
    """The name of a spell on the stack with split second, or None.

    CR 702.61a: "Split second is a static ability that functions only while
    the spell with split second is on the stack. 'Split second' means 'As
    long as this spell is on the stack, players can't cast other spells or
    activate abilities that aren't mana abilities.'" CR 604.5 is the general
    permission a static ability has to apply while its own spell sits on the
    stack - the same permission `cannot_be_countered` reads for "This spell
    can't be countered." Every object on the stack is checked, not only the
    top one: nothing in CR 702.61a privileges the top of a LIFO stack for a
    condition about being "on the stack" at all.

    Two ways a spell on the stack ends up with split second, one keyword
    vocabulary: `has_split_second` reads the printing's own keyword line
    (Ricochet Trap and friends), and `Game.controls_split_second_grant`
    reads Samut, Tyrant of Naktamun's own "Instant and sorcery spells you
    control have split second." group grant off the computed board
    (CR 613.5) for the spell's controller - its own docstring names this
    exact combination as the caller it was built for. A granted instance is
    still an instant or sorcery spell's own split second the moment it is
    on the stack (CR 613.1f puts a layer 6 grant on the same footing as a
    printed line), so both are checked here rather than the printed-only
    half alone.
    """
    if game is None:
        return None
    for obj in getattr(game, "stack", []):
        obj_card = getattr(obj, "card", None)
        if obj_card is not None and has_split_second(obj_card):
            return getattr(obj, "name", None) or obj_card.name
        if isinstance(obj, CardState) and _has_conditional_split_second(game, obj):
            return obj.name
        if (
            isinstance(obj, CardState)
            and obj_card is not None
            and {Type.INSTANT, Type.SORCERY} & set(obj_card.types)
            and obj.controller is not None
            and getattr(game, "controls_split_second_grant", None) is not None
            and game.controls_split_second_grant(obj.controller)
        ):
            return getattr(obj, "name", None) or obj_card.name
    return None


def castable_faces(card: Card) -> tuple[str | None, ...]:
    """Every face a cast of this card could still name (CR 709.3, CR 715.3),
    as the `Casting.face` value each choice would set - `None` meaning "no
    face named", the card's own characteristics.

    A split card offers both halves and nothing else (CR 709.3: the caster
    "chooses which half of a split card they are casting"). An adventurer
    card offers its own creature half, cast the ordinary way with no face
    named, plus the Adventure (CR 715.3: "the player chooses whether they
    play the card normally or as an Adventure"). A modal double-faced card
    offers its front face the same way, plus a nonland back face (CR
    712.11b, `modal_dfc_spell_back_faces`). Every other layout offers
    only `None`: a transforming card is cast as its front face (CR 712.11)
    and an Omen half is not castable by this engine at all.

    The same set `machines/legal_actions._base_cost_options` enumerates rows
    for, without that function's cost arithmetic - this exists because
    `Casting.model_post_init` has to ask CR 709.3a's question of every option
    *before* CR 601.2a moves the card, and it has no `Action` to read.
    """
    faces = card.card_faces or []
    if card.layout is Layout.SPLIT and faces:
        return tuple(face.name for face in faces)
    if card.layout is Layout.ADVENTURE and faces:
        inset = adventure_face(card)
        return (None,) if inset is None else (None, inset.name)
    if card.layout is Layout.MODAL_DFC and faces:
        return (None, *(face.name for face in modal_dfc_spell_back_faces(card)))
    return (None,)


def modal_dfc_spell_back_faces(card: Card) -> tuple[Any, ...]:
    """The back face(s) a modal double-faced card may be cast as (CR
    712.11b: "A player casting a modal double-faced card or a copy of a
    modal double-faced card as a spell chooses which face they are casting
    before putting it onto the stack.").

    The front face is the default cast (CR 712.11: "A double-faced spell is
    cast with its front face up by default"), named by no face at all, the
    same way an adventurer card's creature half is. A land back face is
    played, never cast (CR 712.12). A permanent back face (Esika, God of the
    Tree // The Prismatic Bridge) is offered too: CR 712.13 puts it onto the
    battlefield with that face up, which `CardState.move_to` records.
    """
    if card.layout is not Layout.MODAL_DFC:
        return ()
    return tuple(
        face
        for face in (card.card_faces or [])[1:]
        if Type.LAND not in types_of(face.type_line or "")
    )


# --------------------------------------------------------------------------
# Adventure (CR 715)
# --------------------------------------------------------------------------


def adventure_face(card: Card) -> Any:
    """The Adventure half of an adventurer card, or None (CR 715.1).

    CR 715.1: "Adventurer cards have a two-part card frame, with a smaller frame
    inset within their text box." The inset half is the one whose type line says
    Adventure.
    """
    for face in card.card_faces or []:
        if "adventure" in (face.type_line or "").lower():
            return face
    return None


def grant_suspend_haste(game: Any, permanent: CardState) -> None:
    """The back half of CR 702.62a's third ability: "If you cast a creature
    spell this way, it gains haste until you lose control of the spell or the
    permanent it becomes."

    Applied the same way Postmortem Lunge's own no-duration-stated haste is
    (`machines/effects._parse_delayed_reanimate_haste_exile_clauses`):
    `Duration.INDEFINITE` (CR 611.2a's default when no duration is printed),
    scoped with `only_this_incarnation` to the exact object that just entered,
    so a later object with the same id (returned again some other way) does
    not inherit it. "Until you lose control" is not separately timed -
    losing control ordinarily also means a zone change (CR 400.7 makes the
    permanent that arrives under a new controller a new object), which
    `only_this_incarnation`'s stamp check already ends the effect for.

    Not driven automatically, for the same reason `remove_suspend_time_
    counter` is not: nothing here knows a resolving spell "was cast this way"
    except the caller who called `finish_suspend` and then
    `Casting.use_permission()` - a scenario calls this once the resolved
    spell's `CardState` reaches the battlefield, mirroring the hand-driven
    shape every other delayed or off-stack trigger in this engine already
    takes.
    """
    with game._id_allocator_scope():  # noqa: SLF001
        store = game.continuous_effects
        timestamp = store.tick()
        store.add(
            ContinuousEffect(
                description=f"{permanent.name}: suspend grants haste (CR 702.62a)",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                modification=grant_ability("Haste"),
            )
        )


def reads_printed_zone_permission_line(card: Card, text: str) -> bool:
    """Whether one printed line is wholly "You may cast this card from your
    <zone> using its <keyword> ability." and `keyword_cast_options` really
    offers that keyword from that zone, understood (CR 604.6) - `support.py`'s
    credit for it."""
    match = _PRINTED_CAST_FROM_ZONE_USING_KEYWORD.fullmatch(text.strip().rstrip("."))
    if match is None:
        return False
    zone = _PRINTED_PERMISSION_ZONES[match.group("zone").lower()]
    keyword = match.group("keyword").lower()
    return any(
        option.keyword.lower() == keyword and option.zone is zone and option.understood
        for option in keyword_cast_options(card)
    )


#: Names the pre-EP-01 readers exported; the surface manifest keeps them.
_PRINTED_SELF_ZONE_CAST_WITH_ADDITIONAL_COST_RE = _PRINTED_SELF_ZONE_CAST_RE
_STATIC_ZONE_CAST_PERMISSION_RE = _STATIC_ZONE_CAST_BODY_RE
_CONDITIONAL_FLASH_RE = _CONDITIONAL_FLASH_RES[0]
_PLAY_CARDS_EXILED_WITH_STATIC_RE = _PILE_PERMISSION_BODY_RE

from .options import (  # noqa: E402
    CastTiming,
    _option_from_keyword,
    casualty_cost_option,
    conspire_cost_option,
    keyword_cast_options,
)
