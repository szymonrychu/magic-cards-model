import re
from collections.abc import Callable, Iterable, Sequence
from enum import StrEnum
from functools import lru_cache
from typing import Any
from uuid import UUID

from pydantic import ConfigDict

from ...models.card import Card, Color, Layout, Type, types_of
from ...models.card_state import CardState
from ...models.mana import ManaCost
from ...models.zone import Zone
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
from ..layers import ContinuousEffect, Layer, grant_ability, only_this_incarnation
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


#: "You may cast this card from your graveyard by removing six counters from
#: among creatures you control in addition to paying its other costs."
#: (Quilled Greatwurm) - the card's own CR 601.3 permission to be cast from
#: a zone (CR 604.6's "functions from" that zone), at its own mana cost plus
#: an additional cost (CR 601.2f), at its own timing.
_PRINTED_SELF_ZONE_CAST_WITH_ADDITIONAL_COST_RE = re.compile(
    r"^you may cast this card from your (?P<zone>graveyard|exile) by (?P<extra>.+?) in addition "
    r"to paying its other costs\.?$",
    re.IGNORECASE,
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


def _printed_self_zone_cast_additional_cost(text: str) -> tuple[Zone, TotalCost, bool] | None:
    """(zone, cost, whether the cost replaces the mana cost) for one line."""
    line = " ".join(text.split())
    match = _PRINTED_SELF_ZONE_CAST_WITH_ADDITIONAL_COST_RE.fullmatch(line)
    replaces = False
    if match is None:
        match = _PRINTED_SELF_ZONE_CAST_ALTERNATIVE_RE.fullmatch(line)
        replaces = match is not None
    if match is None:
        return None
    extra = _as_cost_phrase(match.group("cost" if replaces else "extra"))
    cost = total_cost_for_phrase(extra)
    if cost is None:
        return None
    zone = Zone.GRAVEYARD if match.group("zone").lower() == "graveyard" else Zone.EXILE
    return zone, cost, replaces


def reads_printed_self_zone_cast_line(text: str) -> bool:
    """What `support.py` asks before crediting the line."""
    return _printed_self_zone_cast_additional_cost(text) is not None


def _printed_self_zone_cast_with_additional_cost(card: Card) -> list[KeywordCastOption]:
    found: list[KeywordCastOption] = []
    for line in (card.oracle_text or "").splitlines():
        read = _printed_self_zone_cast_additional_cost(line)
        if read is None:
            continue
        zone, cost, replaces = read
        found.append(
            KeywordCastOption(
                keyword=CAST_PERMISSION,
                rule="CR 601.3, CR 118.9" if replaces else "CR 601.3, CR 601.2f",
                zone=zone,
                pays_mana_cost=not replaces,
                timing=CastTiming.OWN,
                cost=cost if replaces else None,
                additional_cost=None if replaces else cost,
            )
        )
    return found


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
    r"^each (?P<what>[\w' -]+?) spell you cast has "
    r"(?P<keyword>[A-Za-z]+)(?P<cost>[^.]*)\.(?P<tail>.*)$",
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
_GRANTED_KEYWORD_ON_A_CARD_IN_A_ZONE = re.compile(
    r"^(?P<during>During your turn, )?(?:[Ee]ach (?P<what>[\w' -]+?) card in your "
    r"(?P<zone>hand|graveyard) has|(?P<whats>[\w' -]+?) cards in your "
    r"(?P<zones>hand|graveyard) have) (?P<keyword>[A-Za-z]+)(?P<cost>[^.]*)\.(?P<tail>.*)$",
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
        negated = word.startswith("non-")
        if negated:
            word = word[len("non-") :]
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
            if option is None:
                option = _static_zone_cast_option(
                    text, game, spell, caster, origin_zone, library_top
                )
            if option is None:
                option = _linked_exile_static_cast_option(
                    text, game, spell, caster, origin_zone, permanent
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
            option = _cast_spells_from_a_zone(
                (ability.text or "").strip(), spell, origin_zone, game, caster
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
    r"from your graveyard\.(?P<tail>.*)$",
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

#: "[During your turn, ]you may [play lands and ]cast `<quality>` spells[ with
#: `<stat>` N or less/greater] from your graveyard / the top of your library[
#: by paying N life in addition to paying their other costs].[ `<rider>`]" -
#: Leonardo, Sewer Samurai ("creature spells with power or toughness 1 or
#: less from your graveyard"), Noctis, Prince of Lucis ("artifact spells from
#: your graveyard by paying 3 life in addition to paying their other costs"),
#: Mikey & Don, Party Planners ("play lands and cast Mutant, Ninja, or Turtle
#: spells from the top of your library"), Vivien, Monsters' Advocate
#: ("creature spells from the top of your library"), Traveling Chocobo
#: ("play lands and cast Bird spells ..."). CR 601.3's "a rule or effect
#: allows that player to cast it", as a CR 611.3d static permission.
_STATIC_ZONE_CAST_PERMISSION_RE = re.compile(
    r"^(?P<during>during your turn, )?you may (?P<lands>play lands and )?cast "
    r"(?:(?P<what>[\w' ,-]+?) )?spells"
    r"(?: with (?P<stat>power or toughness|power|toughness|mana value) (?P<n>\d+) or "
    r"(?P<direction>less|greater))?"
    r" from (?P<zone>your graveyard|the top of your library)"
    r"(?: by paying (?P<life>\d+) life in addition to paying their other costs)?\."
    r"(?P<tail>.*)$",
    re.IGNORECASE | re.DOTALL,
)

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


class StaticZoneCastPermission(EngineModel):
    """One `_STATIC_ZONE_CAST_PERMISSION_RE` line, read."""

    model_config = ConfigDict(frozen=True)

    zone: Zone
    """`Zone.GRAVEYARD` or `Zone.LIBRARY` (the top card only)."""
    quality: str = ""
    """The spell's quality phrase, `""` for "spells" of any kind."""
    during_your_turn: bool = False
    plays_lands: bool = False
    """"You may play lands and cast ..." - CR 305.1's land drop opened to the
    same zone, read by `Game.land_from_top_of_library_permission`."""
    stat: str | None = None
    """"power or toughness", "power", "toughness" or "mana value"."""
    bound: int | None = None
    greater: bool = False
    life: int = 0
    """Life paid in addition to the spell's other costs (CR 601.2f, CR 119.4)."""
    rider_type: str | None = None
    """The card type the enters-with rider names ("If you cast a creature
    spell this way"), or None when it covers every spell cast this way."""
    rider_counter: str | None = None
    """The counter kind the rider puts on the permanent, or None: no rider."""


def _normalized_spell_quality(what: str | None) -> str:
    """The quality phrase with CR 205.1's list punctuation evened out: "Mutant,
    Ninja, or Turtle" becomes "mutant, ninja, turtle", the comma list
    `next_spell.spell_has_quality` reads as a disjunction."""
    quality = (what or "").strip().lower()
    return re.sub(r",?\s+or\s+", ", ", quality)


@lru_cache(maxsize=2048)
def static_zone_cast_permission(text: str) -> StaticZoneCastPermission | None:
    """Read one static line as `_STATIC_ZONE_CAST_PERMISSION_RE`, or None.

    Fails closed: an unreadable quality, a rider this does not read, or any
    other trailing sentence makes the whole line unread - Bolas's Citadel's
    "If you cast a spell this way, pay life equal to its mana value rather
    than pay its mana cost." is a different permission, not this one with a
    sentence ignored."""
    from ..next_spell import spell_quality_is_readable

    line = _REMINDER_TEXT_RE.sub("", text).strip()
    match = _STATIC_ZONE_CAST_PERMISSION_RE.fullmatch(line)
    if match is None:
        return None
    quality = _normalized_spell_quality(match.group("what"))
    if quality and not spell_quality_is_readable(quality):
        return None
    rider_type: str | None = None
    rider_counter: str | None = None
    tail = match.group("tail").strip()
    if tail:
        rider = _ENTERS_WITH_A_COUNTER_RIDER_RE.fullmatch(tail)
        if rider is None:
            return None
        rider_type = (rider.group("type") or "").lower() or None
        if rider_type is not None and rider_type not in {type_.value for type_ in Type}:
            return None
        rider_counter = rider.group("counter").lower()
    zone = Zone.GRAVEYARD if "graveyard" in match.group("zone").lower() else Zone.LIBRARY
    if match.group("lands") is not None and zone is Zone.GRAVEYARD:
        # The land half is read for the top of the library only
        # (`Game.land_from_top_of_library_permission`); a graveyard one would
        # be credited with a land drop nothing performs.
        return None
    return StaticZoneCastPermission(
        zone=zone,
        quality=quality,
        during_your_turn=match.group("during") is not None,
        plays_lands=match.group("lands") is not None,
        stat=match.group("stat").lower() if match.group("stat") else None,
        bound=int(match.group("n")) if match.group("n") else None,
        greater=(match.group("direction") or "").lower() == "greater",
        life=int(match.group("life") or 0),
        rider_type=rider_type,
        rider_counter=rider_counter,
    )


def reads_static_zone_cast_permission_line(text: str) -> bool:
    """What `support.py` asks before crediting the line: whether
    `static_zone_cast_permission` reads all of it."""
    return static_zone_cast_permission(text) is not None


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


def _static_zone_cast_option(
    text: str,
    game: Any,
    spell: CardState,
    caster: str,
    origin_zone: Zone,
    library_top: bool | None,
) -> KeywordCastOption | None:
    """`static_zone_cast_permission`'s grant for `spell`, or None.

    "your graveyard" / "your library" are the caster's own (CR 108.3's owner);
    the library permission reaches its top card only - `library_top` is the
    announcing `Casting`'s own record of that, taken before CR 601.2a moved
    the card, and None asks the library as it stands. "During your turn" is
    checked against the turn in progress (CR 611.3a). Timing is the spell's
    own (`CastTiming.OWN`)."""
    from ..next_spell import spell_has_quality

    permission = static_zone_cast_permission(text)
    if permission is None or permission.zone is not origin_zone:
        return None
    if (spell.owner or caster) != caster:
        return None
    if origin_zone is Zone.LIBRARY:
        on_top = library_top if library_top is not None else is_top_of_library(game, spell, caster)
        if not on_top:
            return None
    if permission.during_your_turn:
        turn = getattr(game, "turn", None)
        if turn is None or turn.active_player != caster:
            return None
    if permission.quality and not spell_has_quality(spell, permission.quality):
        return None
    if not _within_bound(spell, permission):
        return None
    counters: tuple[str, ...] = ()
    if permission.rider_counter is not None and (
        permission.rider_type is None or Type(permission.rider_type) in spell.types
    ):
        counters = (permission.rider_counter,)
    additional = total_cost_for_phrase(f"Pay {permission.life} life") if permission.life else None
    return KeywordCastOption(
        keyword=CAST_PERMISSION,
        rule="CR 601.3, CR 611.3d",
        zone=origin_zone,
        pays_mana_cost=True,
        timing=CastTiming.OWN,
        additional_cost=additional,
        enters_with_counters=counters,
    )


# --------------------------------------------------------------------------
# A permanent's standing permission to play the cards exiled with it
# (CR 601.3, CR 607.2a)
# --------------------------------------------------------------------------

#: "[During your turn, ]you may play cards exiled with `<this>`." (The
#: Temporal Anchor) and "You may play lands and cast spells from among cards
#: exiled with this creature." (Nightveil Specter) - CR 601.1a's "play" (a
#: land drop or a cast) opened to CR 607.2a's linked pile, read after the
#: object's own name is normalised to "this `<noun>`" (CR 201.5).
_PLAY_CARDS_EXILED_WITH_STATIC_RE = re.compile(
    r"^(?P<during>during your turn, )?you may play (?:cards|lands and cast spells from among "
    r"cards) exiled with this \w+\.?$",
    re.IGNORECASE,
)


def play_cards_exiled_with_line(
    permanent_name: str, text: str, *, legendary: bool = True
) -> tuple[bool] | None:
    """`(during_your_turn,)` for a `_PLAY_CARDS_EXILED_WITH_STATIC_RE` line
    of the permanent named `permanent_name`, or None."""
    from ..abilities import self_normalized_effect_text

    normalized = self_normalized_effect_text(permanent_name, text.strip(), legendary=legendary)
    match = _PLAY_CARDS_EXILED_WITH_STATIC_RE.fullmatch(normalized.strip())
    if match is None:
        return None
    return (match.group("during") is not None,)


def reads_play_cards_exiled_with_line(card: Card, text: str) -> bool:
    """What `support.py` asks before crediting the line."""
    from ...models.card import Supertype

    return (
        play_cards_exiled_with_line(
            card.name, text, legendary=Supertype.LEGENDARY in card.supertypes
        )
        is not None
    )


def linked_exile_play_source(game: Any, card: CardState, player: str) -> CardState | None:
    """The permanent `player` controls whose "you may play cards exiled with
    `<this>`" lets them play `card` right now, or None: `card` is face up in
    exile (CR 406.3b), exiled with that very object (CR 607.2a, CR 400.7 -
    `ExileAnnotation.links_to`), and the line's "during your turn" holds."""
    if game is None or card.zone is not Zone.EXILE or not card.face_up:
        return None
    annotation = card.exile_annotation
    if annotation is None:
        return None
    from ...models.card import Supertype

    board = game.computed_board()
    for permanent in game.permanents_controlled_by(player):
        if not annotation.links_to(permanent.id, permanent.zone_change_stamp):
            continue
        legendary = Supertype.LEGENDARY in permanent.card.supertypes
        for line in class_gated_lines(permanent, board.of(permanent).abilities):
            read = play_cards_exiled_with_line(permanent.name, line, legendary=legendary)
            if read is None:
                continue
            (during_your_turn,) = read
            if during_your_turn:
                turn = getattr(game, "turn", None)
                if turn is None or turn.active_player != player:
                    continue
            return permanent
    return None


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
    r"\.(?P<limit>\s*you can'?t cast more than one spell this way each turn\.)?$",
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
    )


def _linked_exile_play_option(
    game: Any, spell: CardState, caster: str, origin_zone: Zone
) -> KeywordCastOption | None:
    """`linked_exile_play_source`'s cast half: CR 601.3's permission to cast
    `spell` out of the pile, at its own cost and its own timing."""
    if origin_zone is not Zone.EXILE:
        return None
    probe = spell if spell.zone is Zone.EXILE else None
    if probe is None or linked_exile_play_source(game, probe, caster) is None:
        return None
    return KeywordCastOption(
        keyword=CAST_PERMISSION,
        rule="CR 601.3, CR 607.2a",
        zone=Zone.EXILE,
        pays_mana_cost=True,
        timing=CastTiming.OWN,
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
    if match is None:
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
    match = _GRANTED_KEYWORD_ON_A_CARD_IN_A_ZONE.match(text)
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
    keyword = match.group("keyword")
    printed = match.group("cost").strip() or None
    if printed is None:
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
    match = _GRANTED_KEYWORD_ON_A_CARD_IN_A_ZONE.match(_REMINDER_TEXT_RE.sub("", text).strip())
    if match is None:
        return False
    zone = _ZONE_WORDS_FOR_GRANTS.get((match.group("zone") or match.group("zones")).lower())
    if zone is None:
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
_CONDITIONAL_FLASH_RE = re.compile(
    r"^you may cast this spell as though it had flash if (?P<condition>[^.]+)\.?$",
    re.IGNORECASE,
)


def conditional_flash_condition(text: str) -> str | None:
    """The condition of a "You may cast this spell as though it had flash if
    `<condition>`." line printed on this spell's own text, or `None` if the
    text carries no such line.

    Read one printed line at a time (never the whole multi-line text as one
    regex) the same way `machines/cost.py`'s per-line self-reduction reader
    does, since the grant is always its own sentence.
    """
    for line in (text or "").split("\n"):
        match = _CONDITIONAL_FLASH_RE.fullmatch(line.strip())
        if match is not None:
            return match.group("condition").strip()
    return None


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


from .options import (  # noqa: E402
    CastTiming,
    _option_from_keyword,
    casualty_cost_option,
    conspire_cost_option,
    keyword_cast_options,
)
