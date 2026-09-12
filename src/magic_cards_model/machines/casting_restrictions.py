"""Continuous effects that change who may cast what, not any characteristic.

CR 611.1: "A continuous effect modifies characteristics of objects, modifies
control of objects, or affects players **or the rules of the game**, for a
fixed or indefinite period." Everything here is the third kind: it writes no
layer (CR 613 has nothing to compute for "you may cast spells only at sorcery
speed" or "you can't cast noncreature spells"), so it is read directly by
`machines/casting.py` instead - the same design `Game._activation_prohibition`
already uses for Karn, the Great Creator's activation-locking static.

Two shapes, told apart by whether they can be re-read off a live permanent:

- **A live static** - Teferi, Time Raveler's "Each opponent can cast spells
  only any time they could cast a sorcery." CR 604.2 / 611.3b: the effect
  lasts exactly as long as its source is on the battlefield, and CR 611.3a
  says it "isn't 'locked in'" - so `sorcery_speed_restriction_source` scans
  the battlefield fresh on every call instead of caching anything, and dies
  the instant Teferi does, with nothing to clean up.

- **A recorded `CastingRuleEffect`** - for the two shapes that outlive the
  instant they were created and so cannot be re-derived from a live board:
    - Ranger-Captain of Eos's "Sacrifice this creature: Your opponents can't
      cast noncreature spells this turn." The sacrifice is the ability's own
      *cost* (CR 602.1a), paid before the ability even goes on the stack, so
      by the time this resolves the source is already gone - a live scan
      would find nothing. Recorded instead, with a plain "until end of turn"
      duration (CR 500.5b, CR 514.2) dropped in `Game.cleanup_step`.
    - Teferi, Time Raveler's "+1: Until your next turn, you may cast sorcery
      spells as though they had flash." A *grant*, not a restriction, scoped
      to the activating player rather than to one card - `machines.casting.
      PlayPermission` names one specific object (CR 400.7) and is the wrong
      shape for a blanket "any sorcery you cast", so this reuses
      `Duration.UNTIL_YOUR_NEXT_TURN` (CR 800.4m) the same way
      `machines.layers.ContinuousEffect` already does for Karn's identically
      worded duration, and is dropped by `Game.begin_turn_for` the same way.

Three further live statics joined the first kind, each narrowing the question
along a different axis, and all three answered by a fresh battlefield scan for
the CR 611.3a reason above:

- **A turn window** - Voice of Victory's "Your opponents can't cast spells
  during your turn." (CR 102.1: the active player is the player whose turn it
  is.) `blanket_cant_cast_restriction`.
- **A count** - High Noon's "Each player can't cast more than one spell each
  turn.", counted off `Game.spells_cast_this_turn`.
  `blanket_cant_cast_restriction`.
- **An origin zone** - Grafdigger's Cage's "Players can't cast spells from
  graveyards or libraries." and Soulless Jailer's noncreature-and-exile
  variant. `zone_cast_prohibition_source`, which needs the spell and the zone
  it would be cast from and so cannot ride the blanket reader.

CR 601.3 is the rule all four express - "a player can begin to cast a spell
only if a rule or effect allows that player to cast it and no rule or effect
prohibits that player from casting it" - with CR 101.2 giving each "can't"
precedence over whatever permission would otherwise apply.

`cannot_be_countered` is the odd one out and deliberately kept here anyway:
it is a prohibition read off a *spell on the stack* rather than off a player
(CR 113.6g, CR 604.5), and it is what stops CR 701.6a's "counter" from doing
anything to Supreme Verdict.
"""

import re
from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..ids import new_id
from ..models.card import Card, Type
from ..models.zone import Zone
from .abilities import AbilityKind, parse_abilities
from .layers import Duration
from .triggers import AbilityOnStack


class CastingRuleKind:
    """What one recorded `CastingRuleEffect` does.

    Plain string constants rather than a `StrEnum` sub-namespace: the values
    themselves are never printed to a player, only compared, and a bare class
    keeps the two rows this wave needs from looking like a bigger registry
    than they are.
    """

    NONCREATURE_RESTRICTION = "noncreature_restriction"
    """Ranger-Captain of Eos: opponents of `controller` can't cast
    noncreature spells."""
    SORCERY_SPEED_FLASH_GRANT = "sorcery_speed_flash_grant"
    """Teferi, Time Raveler's +1: `controller` may cast sorcery spells as
    though they had flash."""
    TARGETED_CANT_CAST = "targeted_cant_cast"
    """Orim's Chant: `restricted_player` (a spell target, not "your
    opponents") can't cast spells at all this turn."""
    INSTANT_SORCERY_COST_REDUCTION_GRANT = "instant_sorcery_cost_reduction_grant"
    """Ral, Monsoon Mage's +1: "Until your next turn, instant and sorcery
    spells you cast cost {1} less to cast." Read by `Game.
    static_cost_modifiers_for` off `CastingRuleEffect.amount` rather than off
    any live permanent's text, the same reason Teferi's own +1 is recorded
    here rather than left to a battlefield scan: Ral may have transformed (or
    left the battlefield) since granting it, and the grant still applies."""
    TURN_WINDOW_CANT_CAST = "turn_window_cant_cast"
    """Voice of Victory: "Your opponents can't cast spells during your turn."
    Never recorded on `Game.casting_rule_effects` - synthesised fresh by
    `blanket_cant_cast_restriction` off the live battlefield, because the
    prohibition has to appear and vanish both with the permanent (CR 604.2,
    CR 611.3a) and with the turn boundary (CR 102.1: "the active player is the
    player whose turn it is")."""
    SPELL_COUNT_CANT_CAST = "spell_count_cant_cast"
    """High Noon: "Each player can't cast more than one spell each turn."
    Also synthesised live, counted off `Game.spells_cast_this_turn`."""
    ZONE_CANT_CAST = "zone_cant_cast"
    """Grafdigger's Cage and Soulless Jailer: "Players can't cast spells from
    graveyards or libraries." Scoped to the zone a cast would come from, so it
    is answered by `zone_cast_prohibition_source` - which takes the spell and
    its origin zone - rather than by the blanket reader below."""


class CastingRuleEffect(BaseModel):
    """One recorded CR 611.1 effect over who may cast what.

    Deliberately not a `machines.layers.ContinuousEffect`: that model exists
    to feed the layer system a characteristic modification (CR 613), and
    these two shapes write no characteristic at all - forcing one through
    the layer machinery to get its "until your next turn" expiry for free
    would be the same category error `Game._activation_prohibition`'s own
    docstring already warns against for activation prohibitions.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=new_id)
    kind: str
    controller: str
    """Whose effect this is. For a restriction, this is the source's
    controller when it was created - the "you" in "your opponents can't
    cast" - and every *other* player is the one restricted. For a grant,
    this is the player who received it directly."""
    source_name: str
    duration: Duration = Duration.UNTIL_END_OF_TURN
    until_next_turn_of: str | None = None
    """Set for `Duration.UNTIL_YOUR_NEXT_TURN`, mirroring `machines.layers.
    ContinuousEffect.until_next_turn_of`: CR 800.4m ends the effect the
    moment this player's next turn would begin, which `Game.begin_turn_for`
    already calls for every player, every turn."""
    restricted_player: str | None = None
    """Set only for `CastingRuleKind.TARGETED_CANT_CAST`: the one player a
    spell *targeted* (CR 115.1), as opposed to `controller`'s own "your
    opponents" reading for `NONCREATURE_RESTRICTION` above. Orim's Chant
    names a specific player, who may be the caster's own opponent, teammate,
    or (if somehow legally targeted) the caster - the restriction follows the
    target, not a fixed relationship to whoever cast the spell."""
    amount: int | None = None
    """`INSTANT_SORCERY_COST_REDUCTION_GRANT` only: the flat discount."""


def create_noncreature_cast_restriction(ability: AbilityOnStack) -> CastingRuleEffect:
    """Ranger-Captain of Eos's "Your opponents can't cast noncreature spells
    this turn." as a recorded effect, keyed to the ability's controller at
    the moment it resolves - not to any permanent, which is already gone
    (CR 602.1a: the sacrifice paid for this ability).
    """
    return CastingRuleEffect(
        kind=CastingRuleKind.NONCREATURE_RESTRICTION,
        controller=ability.controller,
        source_name=ability.source_name,
        duration=Duration.UNTIL_END_OF_TURN,
    )


def create_sorcery_speed_flash_grant(ability: AbilityOnStack) -> CastingRuleEffect:
    """Teferi, Time Raveler's "+1: Until your next turn, you may cast sorcery
    spells as though they had flash." as a recorded effect."""
    return CastingRuleEffect(
        kind=CastingRuleKind.SORCERY_SPEED_FLASH_GRANT,
        controller=ability.controller,
        source_name=ability.source_name,
        duration=Duration.UNTIL_YOUR_NEXT_TURN,
        until_next_turn_of=ability.controller,
    )


def create_targeted_cant_cast_restriction(
    controller: str, restricted_player: str, source_name: str
) -> CastingRuleEffect:
    """Orim's Chant's "Target player can't cast spells this turn." as a
    recorded effect - `controller` is the caster of Orim's Chant (recorded
    for parity with the other two rows, but unused by the reader below,
    which cares only about `restricted_player`), and `restricted_player` is
    the target itself.
    """
    return CastingRuleEffect(
        kind=CastingRuleKind.TARGETED_CANT_CAST,
        controller=controller,
        source_name=source_name,
        duration=Duration.UNTIL_END_OF_TURN,
        restricted_player=restricted_player,
    )


def blanket_cant_cast_restriction(game: Any, caster: str) -> CastingRuleEffect | None:
    """Whatever stops `caster` from casting *any* spell at all right now, or
    None (CR 601.3, CR 101.2).

    CR 601.3: "A player can begin to cast a spell only if a rule or effect
    allows that player to cast it and no rule or effect prohibits that player
    from casting it", and CR 101.2 gives the "can't" precedence over any
    permission that would otherwise let the cast through. Three sources, in
    the order they are cheapest to answer:

    - **Recorded** - Orim's Chant's "Target player can't cast spells this
      turn", already on `Game.casting_rule_effects`. Unlike
      `restricted_from_noncreature_casting`'s "your opponents" reading, this
      one names the restricted player directly, so the caster's own spell can
      restrict itself if it is somehow legally targeted at its own controller.
    - **Live, turn-scoped** - Voice of Victory's "Your opponents can't cast
      spells during your turn."
    - **Live, count-scoped** - High Noon's "Each player can't cast more than
      one spell each turn."

    The two live shapes are re-read off the battlefield on every call and
    never cached, per CR 611.3a: a continuous effect from a static ability
    "isn't 'locked in'; it applies at any given moment to whatever its text
    indicates". CR 611.1 is what makes both of them expressible at all - a
    continuous effect may "affect players or the rules of the game" - and
    CR 613.11 is why neither writes a layer.
    """
    for effect in getattr(game, "casting_rule_effects", []):
        if effect.kind != CastingRuleKind.TARGETED_CANT_CAST:
            continue
        if effect.restricted_player == caster:
            return effect
    return _live_blanket_cant_cast(game, caster)


def targeted_cant_cast_restriction(game: Any, caster: str) -> CastingRuleEffect | None:
    """The name `machines.casting.why_cannot_cast_restriction` imports.

    Kept as its own function rather than folded away because the *question*
    it asks - "is this player barred from casting anything at all?" - outgrew
    its Orim's-Chant-shaped name once Voice of Victory and High Noon joined
    it. `blanket_cant_cast_restriction` is the honest name; this is the
    call site's.
    """
    return blanket_cant_cast_restriction(game, caster)


def _live_blanket_cant_cast(game: Any, caster: str) -> CastingRuleEffect | None:
    """The battlefield half of `blanket_cant_cast_restriction`.

    Both shapes here are statics on permanents, so CR 113.6's default applies
    - "abilities of all other objects usually function only while that object
    is on the battlefield" - and a scan of `game.battlefield` is the whole
    lookup. Nothing is exempted by controller for High Noon ("*each* player"),
    while Voice of Victory exempts its own controller twice over: "your
    opponents", and only while it is that controller's turn.
    """
    for source in list(getattr(game, "battlefield", [])):
        controller = game.controller_of(source).username
        for line in parse_abilities(source.card):
            if line.kind is not AbilityKind.STATIC:
                continue
            text = (line.text or "").strip()
            if _OPPONENTS_CANT_CAST_DURING_YOUR_TURN_RE.match(text):
                if caster == controller:
                    continue
                if getattr(getattr(game, "turn", None), "active_player", None) != controller:
                    continue
                return CastingRuleEffect(
                    kind=CastingRuleKind.TURN_WINDOW_CANT_CAST,
                    controller=controller,
                    source_name=source.name,
                    restricted_player=caster,
                )
            if _ONE_SPELL_EACH_TURN_RE.match(text):
                already_cast = len(getattr(game, "spells_cast_this_turn", {}).get(caster, []))
                if already_cast < 1:
                    continue
                return CastingRuleEffect(
                    kind=CastingRuleKind.SPELL_COUNT_CANT_CAST,
                    controller=controller,
                    source_name=source.name,
                    restricted_player=caster,
                )
    return None


def create_instant_sorcery_cost_reduction_grant(
    ability: AbilityOnStack, amount: int
) -> CastingRuleEffect:
    """Ral, Monsoon Mage's "+1: Until your next turn, instant and sorcery
    spells you cast cost {1} less to cast." as a recorded effect - the same
    shape as `create_sorcery_speed_flash_grant`, an amount added."""
    return CastingRuleEffect(
        kind=CastingRuleKind.INSTANT_SORCERY_COST_REDUCTION_GRANT,
        controller=ability.controller,
        source_name=ability.source_name,
        duration=Duration.UNTIL_YOUR_NEXT_TURN,
        until_next_turn_of=ability.controller,
        amount=amount,
    )


def restricted_from_noncreature_casting(game: Any, caster: str) -> CastingRuleEffect | None:
    """The recorded effect stopping `caster` from casting noncreature spells
    right now, or None.

    Only an opponent of the controller who created the restriction is
    caught - "your opponents can't cast", never "you can't cast" - so an
    effect whose own `controller` is `caster` is skipped.
    """
    for effect in getattr(game, "casting_rule_effects", []):
        if effect.kind != CastingRuleKind.NONCREATURE_RESTRICTION:
            continue
        if effect.controller == caster:
            continue
        return effect
    return None


def has_sorcery_speed_flash_grant(game: Any, caster: str) -> bool:
    """Whether `caster` may currently cast sorcery spells as though they had
    flash (Teferi, Time Raveler's +1)."""
    return any(
        effect.kind == CastingRuleKind.SORCERY_SPEED_FLASH_GRANT and effect.controller == caster
        for effect in getattr(game, "casting_rule_effects", [])
    )


#: Teferi, Time Raveler's exact printed static, verified against the pool
#: printing: "Each opponent can cast spells only any time they could cast a
#: sorcery." Matched narrowly - this shape is templated onto exactly this
#: card in the pool - rather than guessed at for some wider family.
_SORCERY_SPEED_ONLY_RE = re.compile(
    r"^each opponent can cast spells only any time they could cast a sorcery\.?$",
    re.IGNORECASE,
)


#: Voice of Victory's exact printed static, verified against the pool
#: printing: "Your opponents can't cast spells during your turn." Two
#: conditions in one sentence - who ("your opponents", so never the
#: controller) and when ("during your turn", CR 102.1's active player) - both
#: read live by `_live_blanket_cant_cast`.
_OPPONENTS_CANT_CAST_DURING_YOUR_TURN_RE = re.compile(
    r"^your opponents can't cast spells during your turn\.?$", re.IGNORECASE
)

#: High Noon's exact printed static, verified against the pool printing:
#: "Each player can't cast more than one spell each turn." "Each player"
#: includes its own controller, and "more than one" is a count over
#: `Game.spells_cast_this_turn` - the running list that already excludes
#: copies put onto the stack, which are never cast (CR 707.10: "a copy of a
#: spell isn't cast").
_ONE_SPELL_EACH_TURN_RE = re.compile(
    r"^each player can't cast more than one spell each turn\.?$", re.IGNORECASE
)

#: Grafdigger's Cage's "Players can't cast spells from graveyards or
#: libraries." and Soulless Jailer's "Players can't cast noncreature spells
#: from graveyards or exile." - one shape, verified against both pool
#: printings, differing only in the optional type filter and the zone list.
_ZONE_CAST_PROHIBITION_RE = re.compile(
    r"^players can't cast (?:(?P<filter>noncreature|creature|nonland|land) )?spells "
    r"from (?P<zones>[a-z ,]+?)\.?$",
    re.IGNORECASE,
)

#: The zone nouns those sentences use, in the plural they are printed in
#: ("graveyards", one per player) or the singular of the one shared holding
#: area ("exile", CR 406.1).
_ZONE_WORDS: dict[str, Zone] = {
    "graveyard": Zone.GRAVEYARD,
    "graveyards": Zone.GRAVEYARD,
    "library": Zone.LIBRARY,
    "libraries": Zone.LIBRARY,
    "exile": Zone.EXILE,
    "hand": Zone.HAND,
    "hands": Zone.HAND,
}

#: Supreme Verdict's exact printed first line. CR 113.6g: "An object's ability
#: that states it can't be countered or can't be copied functions on the
#: stack" - so unlike every other reader in this module, which asks about a
#: player, this one asks about one object while it is on the stack, and
#: CR 604.5 is what keeps it a live static there rather than an effect that
#: resolved.
_CANT_BE_COUNTERED_RE = re.compile(r"^this spell can't be countered\.?$", re.IGNORECASE)

#: Ranger-Captain of Eos's exact printed sacrifice-ability effect (the cost,
#: "Sacrifice this creature:", is a separate `CostKind.SACRIFICE` piece the
#: activation-cost machinery already reads - this is only the sentence after
#: the colon).
_NONCREATURE_CAST_RESTRICTION_RE = re.compile(
    r"^your opponents can't cast noncreature spells this turn\.?$", re.IGNORECASE
)

#: Teferi, Time Raveler's exact printed "+1" effect.
_SORCERY_FLASH_GRANT_RE = re.compile(
    r"^until your next turn, you may cast sorcery spells as though they had flash\.?$",
    re.IGNORECASE,
)

#: Ral, Monsoon Mage's exact printed "+1" effect (verified against the pool
#: printing): the same "Until your next turn" duration as Teferi's own +1
#: above, an instant/sorcery cost discount in place of a flash grant.
_INSTANT_SORCERY_COST_REDUCTION_GRANT_RE = re.compile(
    r"^until your next turn, instant and sorcery spells you cast cost "
    r"\{(?P<amount>\d+)\} less to cast\.?$",
    re.IGNORECASE,
)


def parse_casting_rule_clause(
    clause: str, *, for_spell: bool
) -> Callable[[Any, AbilityOnStack], None] | None:
    """One activated-ability clause that records a `CastingRuleEffect` when it
    resolves, or None.

    Never matches spell text: both shapes read here - Ranger-Captain of Eos's
    sacrifice ability and Teferi, Time Raveler's +1 - are printed on activated
    abilities, so `for_spell=True` always misses.
    """
    if for_spell:
        return None
    stripped = clause.strip()

    if _NONCREATURE_CAST_RESTRICTION_RE.match(stripped):

        def restrict(game: Any, ability: AbilityOnStack) -> None:
            game.casting_rule_effects.append(create_noncreature_cast_restriction(ability))

        return restrict

    if _SORCERY_FLASH_GRANT_RE.match(stripped):

        def grant(game: Any, ability: AbilityOnStack) -> None:
            game.casting_rule_effects.append(create_sorcery_speed_flash_grant(ability))

        return grant

    cost_reduction_match = _INSTANT_SORCERY_COST_REDUCTION_GRANT_RE.match(stripped)
    if cost_reduction_match is not None:
        amount = int(cost_reduction_match.group("amount"))

        def grant_reduction(game: Any, ability: AbilityOnStack) -> None:
            game.casting_rule_effects.append(
                create_instant_sorcery_cost_reduction_grant(ability, amount)
            )

        return grant_reduction

    return None


def sorcery_speed_restriction_source(game: Any, caster: str) -> str | None:
    """The name of a live permanent whose static text restricts `caster` to
    sorcery-speed casting, or None.

    Read fresh off the battlefield on every call and never cached, per
    CR 611.3a: a continuous effect from a static ability "isn't 'locked
    in'; it applies at any given moment to whatever its text indicates."
    The permanent's own controller is exempt - "each *opponent*" - the same
    "your opponents control" carve-out `Game._activation_prohibition` already
    reads for Karn, the Great Creator.
    """
    for source in list(getattr(game, "battlefield", [])):
        if game.controller_of(source).username == caster:
            continue
        for line in parse_abilities(source.card):
            if line.kind is not AbilityKind.STATIC:
                continue
            if _SORCERY_SPEED_ONLY_RE.match((line.text or "").strip()):
                return source.name
    return None


def _matches_type_filter(types: Sequence[Type], type_filter: str | None) -> bool:
    """Whether a spell with these card types is caught by a zone
    prohibition's optional type word.

    No word at all catches every spell (Grafdigger's Cage). "noncreature" is
    Soulless Jailer's, and the negatives are read off the *types* (CR 205.2a)
    rather than off a type line, because a card with several types - a
    creature artifact, a land creature - has to answer for all of them.

    Takes the types rather than the `Card` so the caller can supply the
    **chosen face's** types instead of the printing's (CR 601.3e: "Some rules
    and effects state that an alternative set of characteristics or a subset
    of characteristics are considered to determine if a card or copy of a card
    is legal to cast. These alternative characteristics replace the object's
    characteristics for this determination."). `Card.types` reads
    `Card.front_type_line`, so asking the card would have an adventurer card's
    Adventure half answer with its creature front's types - measured live,
    Stomp was castable out of a graveyard under Soulless Jailer's "Players
    can't cast noncreature spells from graveyards or exile". The substitution
    belongs to the caller because only it knows which face is being cast, and
    because this module cannot import `machines/casting.py` - the dependency
    runs the other way.
    """
    if type_filter is None:
        return True
    word = type_filter.lower()
    if word == "creature":
        return Type.CREATURE in types
    if word == "noncreature":
        return Type.CREATURE not in types
    if word == "land":
        return Type.LAND in types
    if word == "nonland":
        return Type.LAND not in types
    return False


def _prohibited_zones(printed: str) -> frozenset[Zone]:
    """The zones a "from ..." tail names, or an empty set if any word in it is
    not one this module knows.

    Fails closed on an unknown word rather than prohibiting the zones it did
    recognise: a sentence this module cannot fully read is not one it may
    half-enforce, and half a prohibition makes legal casts illegal.
    """
    words = [word for word in re.split(r",|\bor\b|\band\b", printed) if word.strip()]
    zones: set[Zone] = set()
    for word in words:
        zone = _ZONE_WORDS.get(word.strip().lower())
        if zone is None:
            return frozenset()
        zones.add(zone)
    return frozenset(zones)


def zone_cast_prohibition_source(
    game: Any, card: Card, origin: Zone, *, types: Sequence[Type] | None = None
) -> str | None:
    """The name of a live permanent whose static text forbids casting `card`
    from `origin`, or None (CR 601.3).

    Grafdigger's Cage's "Players can't cast spells from graveyards or
    libraries." and Soulless Jailer's "Players can't cast noncreature spells
    from graveyards or exile." Both are ordinary battlefield statics
    (CR 113.6, CR 604.1) whose continuous effect "affects players or the rules
    of the game" (CR 611.1, CR 613.11) rather than any characteristic, and
    CR 101.2 is why they beat the very permission that put the card in reach -
    flashback, or Underworld Breach, or an "you may cast it" exile grant.

    Note this is **not** CR 113.6f. That rule is about an ability restricting
    "what zones **that particular object** can be played or cast from" -
    flashback's own zone clause on the card that has it. The Cage restricts
    every *other* object, from the battlefield, which is why it is read here
    off a battlefield scan and not off the spell.

    No player argument: "players" is every player, the Cage's own controller
    included.

    `types` is the CR 601.3e substitution: the card types actually being
    evaluated for this cast, which for a split half (CR 709.3a) or an
    Adventure (CR 715.3a) are the chosen face's and not the printing's.
    Defaults to `card.types` - correct for every single-faced card and for
    any cast that named no face - and `_matches_type_filter`'s own docstring
    carries the printing that measured the difference. The `card` argument
    stays, because the zone scan and the CR 113.6f note below are about the
    object rather than its types.
    """
    evaluated = tuple(card.types) if types is None else tuple(types)
    for source in list(getattr(game, "battlefield", [])):
        for line in parse_abilities(source.card):
            if line.kind is not AbilityKind.STATIC:
                continue
            match = _ZONE_CAST_PROHIBITION_RE.match((line.text or "").strip())
            if match is None:
                continue
            if not _matches_type_filter(evaluated, match.group("filter")):
                continue
            if origin in _prohibited_zones(match.group("zones")):
                return source.name
    return None


def cannot_be_countered(spell: Any) -> bool:
    """Whether this object on the stack says it can't be countered
    (CR 113.6g).

    "An object's ability that states it can't be countered or can't be copied
    functions on the stack" - so unlike everything else in this module, which
    reads a permanent on the battlefield, this reads the spell itself while it
    is the thing being asked about. CR 604.5 is the general permission for a
    static ability to apply while its own spell is on the stack: "Some static
    abilities apply while a spell is on the stack. These are often abilities
    that refer to countering the spell."

    What this makes false is CR 701.6a's verb: "to counter a spell or ability
    means to cancel it, removing it from the stack." A counterspell aimed at
    an uncounterable spell is not refused at announcement and its target does
    not become illegal - CR 608.2b's legality check knows nothing about
    counterability - so it still resolves, still finds its target, and simply
    fails to do the one thing it says.

    An ability on the stack (`machines.triggers.AbilityOnStack`) has no card
    behind it (CR 405.1) and answers False; CR 603.1a's "or state that it
    can't be countered" tail on a triggered ability is a separate shape this
    does not yet read.
    """
    card = getattr(spell, "card", None)
    if card is None:
        return False
    return any(
        line.kind is AbilityKind.STATIC and _CANT_BE_COUNTERED_RE.match((line.text or "").strip())
        for line in parse_abilities(card)
    )
