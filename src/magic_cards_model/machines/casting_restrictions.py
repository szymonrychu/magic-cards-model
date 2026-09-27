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
      `Duration.UNTIL_YOUR_NEXT_TURN` (CR 611.2a) the same way
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

from pydantic import ConfigDict, Field

from ..data.subtypes import canonical_subtype
from ..ids import new_id
from ..models.card import Card, Type
from ..models.card_state import TargetKind
from ..models.zone import Zone
from ..numbers import count_pattern, parse_count
from ..snapshot import EngineModel
from .abilities import AbilityKind, parse_abilities, parse_granted_ability_lines
from .layers import Duration
from .triggers import AbilityOnStack
from .turn import Step


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
    PLAYERS_CANT_CAST = "players_cant_cast"
    """Bilbo's Gambit's own "If the gift was promised, players can't cast
    spells this turn." - every player, `controller` included (CR 601.3,
    611.2c), unlike `OPPONENTS_CANT_CAST`'s controller-exempt "your
    opponents"."""
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
    Also synthesised live, counted off `Game.spells_cast_this_turn`, with the
    printed cap on `CastingRuleEffect.amount` - Fires of Invention's "no more
    than two", Deafening Silence's "one noncreature spell"."""
    ZONE_CANT_CAST = "zone_cant_cast"
    """Grafdigger's Cage and Soulless Jailer: "Players can't cast spells from
    graveyards or libraries." Scoped to the zone a cast would come from, so it
    is answered by `zone_cast_prohibition_source` - which takes the spell and
    its origin zone - rather than by the blanket reader below."""
    OPPONENTS_CANT_CAST = "opponents_cant_cast"
    """Silence's and Revel in Silence's resolving "Your opponents can't cast
    spells this turn." - every opponent of `controller` is barred from
    casting any spell until the turn ends (CR 601.3, CR 514.2). Recorded,
    like Ranger-Captain of Eos's noncreature half, because the spell that
    made it is gone by the time anyone tries to cast (CR 611.2c)."""
    OPPONENTS_CANT_ACTIVATE_LOYALTY = "opponents_cant_activate_loyalty"
    """Revel in Silence's "... or activate planeswalkers' loyalty abilities
    this turn." - every opponent of `controller` is barred from activating
    a loyalty ability (CR 602.5, CR 606.3) until the turn ends. Read by
    `Game.why_cannot_activate` through `loyalty_activation_restriction`."""
    DRAW_COUNT_CANT_DRAW = "draw_count_cant_draw"
    """Narset, Parter of Veils's "Each opponent can't draw more than one card
    each turn." and Spirit of the Labyrinth's "each player" variant. Also
    synthesised live, the identical shape `SPELL_COUNT_CANT_CAST` already uses
    for casts, counted off `Game.cards_drawn_this_turn` instead of `Game.
    spells_cast_this_turn` (CR 121.2b in place of CR 601.3)."""
    SPELLS_CANT_BE_COUNTERED_GRANT = "spells_cant_be_countered_grant"
    """Veil of Summer's "Spells you control can't be countered this turn."
    and Determined's "Other spells you control can't be countered this
    turn." - CR 611.2c's second sentence: this effect modifies no
    characteristic and changes no object's controller, so it "modifies the
    rules of the game" and "can affect objects that weren't affected when
    that continuous effect began" - a spell `controller` casts *later* this
    turn is covered exactly as one already on the stack when the source
    resolved. Read by `spell_protected_from_countering` at the one place
    CR 113.6g's printed "can't be countered" is already enforced,
    `Game.counter`. `excluded_source_id` is Determined's own "Other": the
    resolving spell that granted this protects every *other* spell its
    controller casts, never itself."""
    GRAVEYARD_CAST_GRANT = "graveyard_cast_grant"
    """The Great Work's chapter III, "Until end of turn, you may cast instant
    and sorcery spells from any graveyard. If a spell cast this way would be
    put into a graveyard, exile it instead.", and Liliana, Untouched by
    Death's "-3: You may cast Zombie spells from your graveyard this turn." -
    CR 601.3's permission as a CR 611.2c rule of the game: it modifies no
    object, so a card that reaches a graveyard after it began is covered too.
    `machines/casting.granted_cast_options` reads it for `controller`, with
    `spell_quality`, `any_graveyard` and `exile_instead`."""

    PLAYERS_CANT_GAIN_LIFE = "players_cant_gain_life"
    """Skullcrack's "Players can't gain life this turn." - every player (CR
    119.7), recorded because the spell that made it is gone by the time
    anyone would gain life (CR 611.2c). Read by `Game.life_gain_prohibited`."""
    OPPONENTS_CANT_GAIN_LIFE = "opponents_cant_gain_life"
    """Roiling Vortex's and Atarka's Command's "Your opponents can't gain life
    this turn." - every opponent of `controller` (CR 119.7)."""
    DAMAGE_CANT_BE_PREVENTED = "damage_cant_be_prevented"
    """Skullcrack's, Stomp's and Impractical Joke's "Damage can't be
    prevented this turn." - CR 615.12, read by `Game.damage_cant_be_
    prevented`."""


class CastingRuleEffect(EngineModel):
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
    ContinuousEffect.until_next_turn_of`: CR 611.2a ends the effect the
    moment this player's next turn would begin (its own stated duration),
    which `Game.begin_turn_for` already calls for every player, every
    turn."""
    restricted_player: str | None = None
    """Set only for `CastingRuleKind.TARGETED_CANT_CAST`: the one player a
    spell *targeted* (CR 115.1), as opposed to `controller`'s own "your
    opponents" reading for `NONCREATURE_RESTRICTION` above. Orim's Chant
    names a specific player, who may be the caster's own opponent, teammate,
    or (if somehow legally targeted) the caster - the restriction follows the
    target, not a fixed relationship to whoever cast the spell."""
    excluded_source_id: UUID | None = None
    """Set only for `CastingRuleKind.SPELLS_CANT_BE_COUNTERED_GRANT`:
    Determined's own "Other spells you control can't be countered this
    turn" - the resolving spell that granted the protection, excluded from
    the very protection it grants. `None` for Veil of Summer's plain
    "Spells you control", which excludes nothing."""
    spell_quality: str | None = None
    """`GRAVEYARD_CAST_GRANT`: the printed noun phrase naming which spells
    may be cast - "instant and sorcery" (The Great Work), "Zombie" (Liliana,
    Untouched by Death) - matched the way every other cast grant's phrase is
    (`machines/casting._spell_matches_grant_filter`)."""
    any_graveyard: bool = False
    """`GRAVEYARD_CAST_GRANT`: "from any graveyard" rather than "from your
    graveyard"."""
    exile_instead: bool = False
    """`GRAVEYARD_CAST_GRANT`: "If a spell cast this way would be put into a
    graveyard, exile it instead." (CR 614.1a)."""
    amount: int | None = None
    """`INSTANT_SORCERY_COST_REDUCTION_GRANT`: the flat discount.
    `SPELL_COUNT_CANT_CAST`: the printed cap that has been reached."""


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


def create_players_cant_cast_restriction(controller: str, source_name: str) -> CastingRuleEffect:
    """Bilbo's Gambit's own "If the gift was promised, players can't cast
    spells this turn." as a recorded effect - every player, `controller`
    included (CR 601.3, CR 611.2c: the spell that made it is gone by the
    time anyone tries to cast)."""
    return CastingRuleEffect(
        kind=CastingRuleKind.PLAYERS_CANT_CAST,
        controller=controller,
        source_name=source_name,
        duration=Duration.UNTIL_END_OF_TURN,
    )


def create_spells_cant_be_countered_grant(
    controller: str,
    source_name: str,
    *,
    excluded_source_id: UUID | None = None,
) -> CastingRuleEffect:
    """Veil of Summer's "Spells you control can't be countered this turn."
    and Determined's "Other spells you control can't be countered this
    turn." as a recorded effect - see `CastingRuleKind.
    SPELLS_CANT_BE_COUNTERED_GRANT`'s own docstring for why this is
    recorded at all rather than read off a live permanent (CR 611.2c)."""
    return CastingRuleEffect(
        kind=CastingRuleKind.SPELLS_CANT_BE_COUNTERED_GRANT,
        controller=controller,
        source_name=source_name,
        duration=Duration.UNTIL_END_OF_TURN,
        excluded_source_id=excluded_source_id,
    )


def spell_protected_from_countering(game: Any, spell: Any) -> bool:
    """Whether some *recorded* CR 611.2c effect - as opposed to
    `cannot_be_countered`'s printed-or-granted "This spell can't be
    countered" read directly off the spell itself - stops `spell` from
    being countered right now (CR 113.6g, CR 611.2c, CR 101.2).

    Consulted from `Game.counter` alongside `cannot_be_countered`, never on
    its own: the two are independent sources of the identical CR 701.6a
    refusal, exactly the way `blanket_cant_cast_restriction` reads a
    recorded effect and a live battlefield scan as two sources of the same
    "can't cast" refusal.

    Only a *spell* (an object with a `card`, per `cannot_be_countered`'s own
    convention) can be protected this way - CR 405.1: an ability on the
    stack has no card behind it, so `Ranger-Captain of Eos`-style abilities
    are never swept in by a blanket "spells you control" grant, matching CR
    113.6g's own "can't be countered" being a *spell's* ability in every
    printing that grants it this way.

    `excluded_source_id` is Determined's own "Other": the spell that
    granted the protection is not itself protected by it, read by identity
    (`spell.id`) rather than by name, so two different copies of the same
    card do not accidentally exclude each other.
    """
    if getattr(spell, "card", None) is None:
        return False
    controller = getattr(spell, "controller", None)
    if controller is None:
        return False
    if static_uncounterable_source(game, spell) is not None:
        return True
    spell_id = getattr(spell, "id", None)
    for effect in getattr(game, "casting_rule_effects", []):
        if effect.kind != CastingRuleKind.SPELLS_CANT_BE_COUNTERED_GRANT:
            continue
        if effect.controller != controller:
            continue
        if effect.excluded_source_id is not None and effect.excluded_source_id == spell_id:
            continue
        return True
    return False


#: A permanent's own static "`<Quality>` spells you control can't be
#: countered." - Hexing Squelcher's and Chimil, the Inner Sun's bare "Spells
#: you control ...", Rhythm of the Wild's "Creature spells ...", Destiny
#: Spinner's "Creature and enchantment spells ...", Sphinx of the Final
#: Word's "Instant and sorcery spells ...". Unlike Veil of Summer's resolving
#: "... this turn" (a recorded CR 611.2c effect), this is CR 604.2's static:
#: active exactly while its permanent is on the battlefield, so it is read
#: live off the board and never recorded.
_STATIC_SPELLS_CANT_BE_COUNTERED_RE = re.compile(
    r"^(?P<what>(?:[\w'-]+ )*?)spells you control can'?t be countered\.?$",
    re.IGNORECASE,
)


def _static_uncounterable_quality(line: str) -> str | None:
    """The quality phrase of a static "`<Quality>` spells you control can't
    be countered." line (`""` for any spell), or None when the line is not
    that shape or names a quality `next_spell.spell_has_quality` cannot read.
    CR 205.1's "and" in a type list names one spell that is either type."""
    from .next_spell import spell_quality_is_readable

    match = _STATIC_SPELLS_CANT_BE_COUNTERED_RE.fullmatch(line.strip())
    if match is None:
        return None
    quality = re.sub(r"\s+and\s+", " or ", match.group("what").strip().lower())
    if quality.startswith("other") or quality.endswith("this turn"):
        return None
    if quality and not spell_quality_is_readable(quality):
        return None
    return quality


def reads_static_spells_cant_be_countered_line(text: str) -> bool:
    """Whether one static line is a "`<Quality>` spells you control can't be
    countered." this module enforces - `support.py`'s credit for it."""
    return _static_uncounterable_quality(text) is not None


def static_uncounterable_source(game: Any, spell: Any) -> Any:
    """The permanent whose static "`<Quality>` spells you control can't be
    countered." covers `spell` right now, or None.

    CR 604.2: the effect is active as long as the permanent with the ability
    is on the battlefield and has it, so this scans the permanents `spell`'s
    controller controls fresh, reading each one's *computed* ability lines
    (CR 613.1f: a layer-6 loss removes the protection, a gain adds it). CR
    101.2 gives the "can't" precedence over the counterspell's instruction.
    """
    from .next_spell import spell_has_quality

    controller = getattr(spell, "controller", None)
    if controller is None or getattr(spell, "card", None) is None:
        return None
    board = game.computed_board()
    for permanent in game.permanents_controlled_by(controller):
        for line in board.of(permanent).abilities:
            if "countered" not in line:
                continue
            quality = _static_uncounterable_quality(line)
            if quality is None:
                continue
            if not quality or spell_has_quality(spell, quality):
                return permanent
    return None


def blanket_cant_cast_restriction(
    game: Any,
    caster: str,
    *,
    spell_types: Sequence[Type] | None = None,
    spell_subtypes: Sequence[str] | None = None,
) -> CastingRuleEffect | None:
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
      one spell each turn."; any count, subject and spell quality - `spell_types`
      and `spell_subtypes` are the spell being cast, for Deafening Silence's
      "more than one noncreature spell".

    The two live shapes are re-read off the battlefield on every call and
    never cached, per CR 611.3a: a continuous effect from a static ability
    "isn't 'locked in'; it applies at any given moment to whatever its text
    indicates". CR 611.1 is what makes both of them expressible at all - a
    continuous effect may "affect players or the rules of the game" - and
    CR 613.11 is why neither writes a layer.
    """
    for effect in getattr(game, "casting_rule_effects", []):
        if effect.kind == CastingRuleKind.TARGETED_CANT_CAST and effect.restricted_player == caster:
            return effect
        if effect.kind == CastingRuleKind.PLAYERS_CANT_CAST:
            # Bilbo's Gambit's own "players can't cast spells this turn" -
            # every player, the effect's own controller included.
            return effect
        # Silence's "Your opponents can't cast spells this turn" - the
        # effect's own controller is never among them.
        if effect.kind == CastingRuleKind.OPPONENTS_CANT_CAST and effect.controller != caster:
            return effect
    return _live_blanket_cant_cast(game, caster, spell_types, spell_subtypes)


def targeted_cant_cast_restriction(
    game: Any,
    caster: str,
    *,
    spell_types: Sequence[Type] | None = None,
    spell_subtypes: Sequence[str] | None = None,
) -> CastingRuleEffect | None:
    """The name `machines.casting.why_cannot_cast_restriction` imports.

    Kept as its own function rather than folded away because the *question*
    it asks - "is this player barred from casting anything at all?" - outgrew
    its Orim's-Chant-shaped name once Voice of Victory and High Noon joined
    it. `blanket_cant_cast_restriction` is the honest name; this is the
    call site's.
    """
    return blanket_cant_cast_restriction(
        game, caster, spell_types=spell_types, spell_subtypes=spell_subtypes
    )


def _live_blanket_cant_cast(
    game: Any,
    caster: str,
    spell_types: Sequence[Type] | None = None,
    spell_subtypes: Sequence[str] | None = None,
) -> CastingRuleEffect | None:
    """The battlefield half of `blanket_cant_cast_restriction`.

    Every shape here is a static on a permanent, so CR 113.6's default applies
    - "abilities of all other objects usually function only while that object
    is on the battlefield" - and a scan of `game.battlefield` is the whole
    lookup. Voice of Victory exempts its own controller twice over: "your
    opponents", and only while it is that controller's turn.

    A static may conjoin two restrictions in one sentence - Fires of
    Invention's "You can cast spells only during your turn and you can cast no
    more than two spells each turn" - so each "and <who> can ..." clause is
    read on its own (`_RESTRICTION_CLAUSE_SPLIT`). Who a clause restricts is
    read off its subject (`_restricts`): "each player", "each opponent" / "your
    opponents", "you", or CR 303.4m's "enchanted player" (Curse of
    Exhaustion). A spell-count cap counts the caster's own
    `Game.spells_cast_this_turn` - the whole turn, even spells cast before the
    permanent arrived, per Curse of Exhaustion's and Fires of Invention's
    rulings - that share the cap's quality, and applies only to a spell that
    has that quality itself.
    """
    turn = getattr(game, "turn", None)
    active_player = getattr(turn, "active_player", None)
    for source in list(getattr(game, "battlefield", [])):
        controller = game.controller_of(source).username
        for line in parse_abilities(source.card):
            if line.kind is not AbilityKind.STATIC:
                continue
            text = (line.text or "").strip()
            if _OPPONENTS_CANT_CAST_DURING_YOUR_TURN_RE.match(text):
                if caster == controller:
                    continue
                if active_player != controller:
                    continue
                return CastingRuleEffect(
                    kind=CastingRuleKind.TURN_WINDOW_CANT_CAST,
                    controller=controller,
                    source_name=source.name,
                    restricted_player=caster,
                )
            for clause in _RESTRICTION_CLAUSE_SPLIT.split(text.rstrip(".")):
                clause = clause.strip()
                window = _CAST_ONLY_DURING_TURN_RE.fullmatch(clause)
                if window is not None:
                    if not _restricts(window.group("who"), source, controller, caster):
                        continue
                    owner = controller if window.group("whose").lower() == "your" else caster
                    if active_player == owner:
                        continue
                    return CastingRuleEffect(
                        kind=CastingRuleKind.TURN_WINDOW_CANT_CAST,
                        controller=controller,
                        source_name=source.name,
                        restricted_player=caster,
                    )
                cap = _SPELL_COUNT_CAP_RE.fullmatch(clause)
                if cap is None:
                    continue
                if not _restricts(cap.group("who"), source, controller, caster):
                    continue
                limit = parse_count(cap.group("count"))
                has_quality = _spell_quality(cap.group("quality"))
                if limit is None:
                    continue
                if spell_types is not None and not has_quality(
                    tuple(spell_types), tuple(spell_subtypes or ())
                ):
                    continue
                already_cast = sum(
                    1
                    for spell in getattr(game, "spells_cast_this_turn", {}).get(caster, [])
                    if has_quality(tuple(spell.types), tuple(spell.subtypes))
                )
                if already_cast < limit:
                    continue
                return CastingRuleEffect(
                    kind=CastingRuleKind.SPELL_COUNT_CANT_CAST,
                    controller=controller,
                    source_name=source.name,
                    restricted_player=caster,
                    amount=limit,
                )
    return None


def _restricts(who: str, source: Any, controller: str, caster: str) -> bool:
    """Whether a casting restriction's printed subject is `caster`.

    "Each player" is everyone, its controller included; "each opponent" and
    "your opponents" are everyone but the controller; "you" is the controller
    alone; and "enchanted player" is whoever the permanent is attached to
    (CR 303.4m: "An ability of a permanent that refers to the 'enchanted
    [object or player]' refers to whatever object or player that permanent is
    attached to"), nobody when it is attached to none.
    """
    subject = who.lower()
    if subject == "each player":
        return True
    if subject in ("each opponent", "your opponents"):
        return caster != controller
    if subject == "you":
        return caster == controller
    attachment = getattr(source, "attachment", None)
    return (
        attachment is not None
        and attachment.kind is TargetKind.PLAYER
        and attachment.username == caster
    )


def _spell_quality(
    word: str | None,
) -> Callable[[tuple[Type, ...], tuple[str, ...]], bool]:
    """A spell-count cap's one-word quality as a test on a spell's types and
    subtypes: none printed is every spell, "noncreature" (a "non" prefix
    negates) a card type (CR 205.2a), "non-Phyrexian" a subtype (CR 205.3).

    A word that is neither is read as every spell - the stricter reading of a
    "can't", which counts more spells toward the cap rather than fewer.
    """
    if word is None:
        return lambda types, subtypes: True
    lowered = word.lower()
    negated = lowered.startswith("non")
    core = lowered.removeprefix("non").lstrip("-") if negated else lowered
    card_type = next((each for each in Type if each.value == core), None)
    subtype = None if card_type is not None else canonical_subtype(core)
    if card_type is None and subtype is None:
        return lambda types, subtypes: True

    def matches(types: tuple[Type, ...], subtypes: tuple[str, ...]) -> bool:
        if card_type is not None:
            found = card_type in types
        else:
            found = any(each.lower() == subtype for each in subtypes)
        return found != negated

    return matches


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


def loyalty_activation_restriction(game: Any, activator: str) -> CastingRuleEffect | None:
    """The recorded effect stopping `activator` from activating loyalty
    abilities right now (CR 602.5, CR 606.3), or None - Revel in Silence's
    "Your opponents can't ... activate planeswalkers' loyalty abilities this
    turn". Only an opponent of the effect's own controller is caught."""
    for effect in getattr(game, "casting_rule_effects", []):
        if effect.kind != CastingRuleKind.OPPONENTS_CANT_ACTIVATE_LOYALTY:
            continue
        if effect.controller == activator:
            continue
        return effect
    return None


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

#: The subject of a casting restriction, read by `_restricts`.
_RESTRICTED_WHO = r"(?P<who>each player|each opponent|your opponents|you|enchanted player)"

#: A spell-count cap, CR 601.3's "no rule or effect prohibits": High Noon's
#: and Archon of Emeria's "Each player can't cast more than one spell each
#: turn", Curse of Exhaustion's "Enchanted player can't cast more than one
#: spell each turn", Deafening Silence's "... more than one noncreature spell
#: ...", Fires of Invention's "you can cast no more than two spells each
#: turn". The count is `magic_cards_model.numbers`' `COUNT`; it is a count
#: over `Game.spells_cast_this_turn`, the running list that already excludes
#: copies put onto the stack, which are never cast (CR 707.10: "a copy of a
#: spell isn't cast"). "Spells this way" (Hedonist's Trove) is a different
#: restriction on a permission and does not match.
_SPELL_COUNT_CAP_RE = re.compile(
    rf"{_RESTRICTED_WHO} (?:can't cast more than|can cast no more than) "
    rf"{count_pattern('count')} (?:(?P<quality>[\w-]+) )?spells? each turn",
    re.IGNORECASE,
)

#: Fires of Invention's first half: "You can cast spells only during your
#: turn" - CR 102.1's active player is the window.
_CAST_ONLY_DURING_TURN_RE = re.compile(
    rf"{_RESTRICTED_WHO} can cast spells only during (?P<whose>your|their(?: own)?) turns?",
    re.IGNORECASE,
)

#: Where one static sentence conjoins two restrictions: "..., and you can cast
#: no more than two spells each turn".
_RESTRICTION_CLAUSE_SPLIT = re.compile(
    r",? and (?=(?:each player|each opponent|your opponents|you|enchanted player) can)",
    re.IGNORECASE,
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
#: The same static behind a condition - Exquisite Firecraft's spell mastery
#: line (CR 207.2c: the ability word is only a label), "If there are two or
#: more instant and/or sorcery cards in your graveyard, this spell can't be
#: countered."
_CONDITIONAL_CANT_BE_COUNTERED_RE = re.compile(
    r"^(?:[A-Z][A-Za-z' -]{2,30}? \u2014 )?if (?P<condition>[^,]+), "
    r"this spell can't be countered\.?$",
    re.IGNORECASE,
)

#: Ranger-Captain of Eos's exact printed sacrifice-ability effect (the cost,
#: "Sacrifice this creature:", is a separate `CostKind.SACRIFICE` piece the
#: activation-cost machinery already reads - this is only the sentence after
#: the colon).
_NONCREATURE_CAST_RESTRICTION_RE = re.compile(
    r"^your opponents can't cast noncreature spells this turn\.?$", re.IGNORECASE
)

#: Silence's "Your opponents can't cast spells this turn." and Revel in
#: Silence's "Your opponents can't cast spells or activate planeswalkers'
#: loyalty abilities this turn." - a resolving effect's CR 601.3 cast
#: prohibition over every opponent, with CR 602.5's loyalty-activation
#: prohibition (CR 606.3) as an optional second half. "this turn" is CR
#: 514.2's until-end-of-turn duration.
_OPPONENTS_CANT_CAST_THIS_TURN_RE = re.compile(
    r"^(?:your opponents|each opponent) can't cast spells"
    r"(?P<loyalty> or activate (?:planeswalkers' )?loyalty abilities)? this turn\.?$",
    re.IGNORECASE,
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


#: "[Until end of turn, ]you may cast <quality> spells from <your|any>
#: graveyard[ this turn]. [If a spell cast this way would be put into a/your
#: graveyard, exile it instead.]" - a duration is required, at the front or
#: the back: a sentence with neither is a static grant (Jaya Ballard's
#: emblem), read by `machines/casting` off the object that carries it.
_GRAVEYARD_CAST_GRANT_RE = re.compile(
    r"^(?P<front>until end of turn, )?you may cast (?P<what>[\w' -]+?) spells from "
    r"(?P<whose>your|any) graveyard(?P<back> this turn)?\.?"
    r"(?:\s*(?P<rider>if a spell cast this way would be put into (?:your|a) graveyard, "
    r"exile it instead)\.?)?$",
    re.IGNORECASE,
)


def graveyard_cast_grants_for(game: Any, caster: str) -> list[CastingRuleEffect]:
    """Every live `GRAVEYARD_CAST_GRANT` belonging to `caster`."""
    return [
        effect
        for effect in getattr(game, "casting_rule_effects", [])
        if effect.kind == CastingRuleKind.GRAVEYARD_CAST_GRANT and effect.controller == caster
    ]


def parse_casting_rule_clause(clause: str, *, for_spell: bool) -> Callable[[Any, Any], None] | None:
    """One clause that records a `CastingRuleEffect` when it resolves, or
    None.

    The turn-long "Your opponents can't cast spells [or activate
    planeswalkers' loyalty abilities] this turn" lock is read for a spell and
    an ability alike (Silence and Revel in Silence are instants). The other
    shapes read here - Ranger-Captain of Eos's sacrifice ability and Teferi,
    Time Raveler's +1 - are printed on activated abilities only, so
    `for_spell=True` misses them.
    """
    stripped = clause.strip()

    grant_match = _GRAVEYARD_CAST_GRANT_RE.fullmatch(stripped)
    if grant_match is not None and (grant_match.group("front") or grant_match.group("back")):
        quality = grant_match.group("what").strip()
        any_graveyard = grant_match.group("whose").lower() == "any"
        exile_instead = grant_match.group("rider") is not None

        def grant_graveyard_casting(game: Any, obj: Any) -> None:
            controller = (
                obj.controller
                if isinstance(obj, AbilityOnStack)
                else game.controller_of(obj).username
            )
            source_name = obj.source_name if isinstance(obj, AbilityOnStack) else obj.name
            game.casting_rule_effects.append(
                CastingRuleEffect(
                    kind=CastingRuleKind.GRAVEYARD_CAST_GRANT,
                    controller=controller,
                    source_name=source_name,
                    duration=Duration.UNTIL_END_OF_TURN,
                    spell_quality=quality,
                    any_graveyard=any_graveyard,
                    exile_instead=exile_instead,
                )
            )

        return grant_graveyard_casting

    lock_match = _OPPONENTS_CANT_CAST_THIS_TURN_RE.match(stripped)
    if lock_match is not None:
        also_loyalty = lock_match.group("loyalty") is not None

        def lock(game: Any, obj: Any) -> None:
            # A resolving spell (`CardState`) or ability (`AbilityOnStack`):
            # "your" is whoever controls it as it resolves (CR 109.5).
            controller = (
                obj.controller
                if isinstance(obj, AbilityOnStack)
                else game.controller_of(obj).username
            )
            source_name = obj.source_name if isinstance(obj, AbilityOnStack) else obj.name
            game.casting_rule_effects.append(
                CastingRuleEffect(
                    kind=CastingRuleKind.OPPONENTS_CANT_CAST,
                    controller=controller,
                    source_name=source_name,
                    duration=Duration.UNTIL_END_OF_TURN,
                )
            )
            if also_loyalty:
                game.casting_rule_effects.append(
                    CastingRuleEffect(
                        kind=CastingRuleKind.OPPONENTS_CANT_ACTIVATE_LOYALTY,
                        controller=controller,
                        source_name=source_name,
                        duration=Duration.UNTIL_END_OF_TURN,
                    )
                )

        return lock

    if for_spell:
        return None

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


#: Narset, Parter of Veils's and Spirit of the Labyrinth's exact printed
#: static, verified against both pool printings: "Each opponent/player can't
#: draw more than one card each turn." Reuses `_RESTRICTED_WHO` and the same
#: `count_pattern` `_SPELL_COUNT_CAP_RE` already uses for the identical shape
#: over casts (CR 121.2b's "individual card draws" in place of CR 601.3's
#: casts).
_DRAW_CAP_RE = re.compile(
    rf"^{_RESTRICTED_WHO} can'?t draw more than {count_pattern('count')} cards? each turn\.?$",
    re.IGNORECASE,
)


def draw_cap_restriction(game: Any, drawer: str) -> CastingRuleEffect | None:
    """Whatever stops `drawer` from drawing another card on *this specific
    draw*, or None (CR 121.2b).

    "Some effects say that a player can't draw more than one card each turn.
    Such an effect applies to individual card draws. Instructions to draw
    multiple cards may still be partially carried out." - so `Game.draw_cards`
    asks this once per individual draw inside its own CR 121.2 loop, not once
    per instruction: a "draw two cards" that would hit the cap on the second
    draw still performs the first.

    Read fresh off the battlefield on every call, per CR 611.3a, exactly like
    `_live_blanket_cant_cast`'s identical cap over casts - Narset, Parter of
    Veils's "each opponent" and Spirit of the Labyrinth's "each player" are the
    same shape with a different subject, told apart by `_restricts`.
    """
    for source in list(getattr(game, "battlefield", [])):
        controller = game.controller_of(source).username
        for line in parse_abilities(source.card):
            if line.kind is not AbilityKind.STATIC:
                continue
            match = _DRAW_CAP_RE.match((line.text or "").strip())
            if match is None:
                continue
            if not _restricts(match.group("who"), source, controller, drawer):
                continue
            limit = parse_count(match.group("count"))
            if limit is None:
                continue
            return CastingRuleEffect(
                kind=CastingRuleKind.DRAW_COUNT_CANT_DRAW,
                controller=controller,
                source_name=source.name,
                restricted_player=drawer,
                amount=limit,
            )
    return None


#: Ashiok, Dream Render's exact printed static, verified against the pool
#: printing: "Spells and abilities your opponents control can't cause their
#: controller to search their library." Narrow to this one sentence, matching
#: `_SORCERY_SPEED_ONLY_RE`'s own precedent for a shape no other pool printing
#: carries - CR 701.23 is Search, and CR 101.2's ordinary "can't" precedence
#: is what makes it bind; there is no rule narrower than that naming this
#: specific prohibition.
_SEARCH_PROHIBITION_RE = re.compile(
    r"^spells and abilities your opponents control can'?t cause their "
    r"controller to search their library\.?$",
    re.IGNORECASE,
)


def search_prohibition_source(game: Any, causer: str) -> str | None:
    """The name of a live permanent whose static text stops `causer` from
    being caused, by their own spell or ability, to search their own library,
    or None.

    "Their controller"/"their library" both name the same person - the
    controller of the spell or ability doing the causing - so this only ever
    stops a *self*-search: `Game.search_library`/`search_and_put` ask it only
    when the player being searched is that same causer. A Bribery-style
    "search target opponent's library" names a different searcher than the
    spell's own controller and is untouched, exactly as the printed grammar
    requires - Ashiok's own `-1` ("target player mills four cards") never
    searches anything and is unaffected either way.
    `causer` must be an opponent of the permanent's own controller ("your
    opponents"), read the same live, never-cached way (CR 611.3a) every other
    reader in this module already scans the battlefield.
    """
    for source in list(getattr(game, "battlefield", [])):
        controller = game.controller_of(source).username
        if controller == causer:
            continue
        for line in parse_abilities(source.card):
            if line.kind is not AbilityKind.STATIC:
                continue
            if _SEARCH_PROHIBITION_RE.match((line.text or "").strip()):
                return source.name
    return None


#: Yuriko, Blade of the Mighty: "During combat, players can't cast spells or
#: activate abilities that aren't mana abilities." A board-wide lockdown
#: with a time window instead of split second's "while this spell is on the
#: stack" one.
_DURING_COMBAT_LOCKDOWN_RE = re.compile(
    r"^during combat, players can'?t cast spells or activate abilities that "
    r"aren'?t mana abilities\.?$",
    re.IGNORECASE,
)

#: CR 506.1: "The combat phase has five steps, which proceed in order:
#: beginning of combat, declare attackers, declare blockers, combat damage,
#: and end of combat." "During combat" is this window, not the whole turn.
_COMBAT_STEPS = frozenset(
    {
        Step.BEGINNING_OF_COMBAT,
        Step.DECLARE_ATTACKERS,
        Step.DECLARE_BLOCKERS,
        Step.COMBAT_DAMAGE,
        Step.END_OF_COMBAT,
    }
)


def combat_lockdown_restriction_source(game: Any) -> str | None:
    """The name of a live permanent whose static text locks down casting and
    non-mana activation for as long as combat lasts, or None (CR 506.1).

    Read the same way `zone_cast_prohibition_source` reads Grafdigger's
    Cage's board-wide "Players can't cast spells from ..." - a battlefield
    scan for the matching static line - gated on `game.turn.step` being one
    of CR 506.1's five combat steps rather than on a zone.
    """
    step = getattr(getattr(game, "turn", None), "step", None)
    if step not in _COMBAT_STEPS:
        return None
    for source in list(getattr(game, "battlefield", [])):
        for line in parse_abilities(source.card):
            if line.kind is AbilityKind.STATIC and _DURING_COMBAT_LOCKDOWN_RE.match(
                (line.text or "").strip()
            ):
                return source.name
    return None


#: CR 113.6g's other half: "This spell can't be copied." (Choreographed
#: Sparks, See Double).
_CANT_BE_COPIED_RE = re.compile(r"^this spell can'?t be copied\.?$", re.IGNORECASE)


def cannot_be_copied(spell: Any) -> bool:
    """Whether this spell - or printing - says it can't be copied (CR
    113.6g: "An object's ability that states it can't be countered or can't
    be copied functions on the stack").

    What this makes impossible is CR 707.10's "to copy a spell ... means to
    put a copy of it onto the stack": `Game.copy_spell` puts nothing there
    for such a spell, whatever asked - storm, a "copy that spell" trigger,
    another copy spell targeting it. A cost paid to make the copy (Mica,
    Reader of Ruins' sacrifice) stays paid. An ability on the stack has no
    card behind it and answers False.
    """
    card = spell if isinstance(spell, Card) else getattr(spell, "card", None)
    if card is None:
        return False
    return any(
        line.kind is AbilityKind.STATIC and _CANT_BE_COPIED_RE.match((line.text or "").strip())
        for line in parse_abilities(card)
    )


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
    if any(
        line.kind is AbilityKind.STATIC and _CANT_BE_COUNTERED_RE.match((line.text or "").strip())
        for line in parse_abilities(card)
    ):
        return True
    # A *granted* "This spell can't be countered.", the same way a permanent's
    # layer-6 "gains an ability" grant lands on `CardState.granted_ability_
    # texts` rather than on the printed card - Theorist's Proxy's own "The
    # next spell you cast this turn can't be countered." resolves before the
    # spell exists, so `NextSpellCannotBeCountered` records the grant here
    # once that spell is actually cast (`machines/delayed.py`).
    granted = getattr(spell, "granted_ability_texts", ())
    return any(
        line.kind is AbilityKind.STATIC and _CANT_BE_COUNTERED_RE.match((line.text or "").strip())
        for line in parse_granted_ability_lines(granted)
    )


def conditionally_cannot_be_countered(game: Any, spell: Any) -> bool:
    """Whether this spell's own "If `<condition>`, this spell can't be
    countered." holds right now (CR 113.6g, CR 604.5).

    Checked when something tries to counter it (CR 701.6a), so the condition
    is read at that moment, for the spell's controller, by the same
    `Game.condition_holds` every other printed condition goes through. An
    unread condition (`None`) does not protect the spell.
    """
    card = getattr(spell, "card", None)
    controller = getattr(spell, "controller", None)
    if card is None or controller is None:
        return False
    for line in parse_abilities(card):
        if line.kind is not AbilityKind.STATIC:
            continue
        match = _CONDITIONAL_CANT_BE_COUNTERED_RE.match((line.text or "").strip())
        if match is None:
            continue
        if game.condition_holds(controller, match.group("condition"), spell) is True:
            return True
    return False


def reads_player_rule_static_line(text: str) -> bool:
    """Whether one printed static line is a player rule this module's
    battlefield readers enforce in full - `support.py`'s credit for it.

    Mirrors the scans above shape for shape, so a line is vouched for only
    when the reader that enforces it would read all of it: a cast window or
    spell-count cap (`_live_blanket_cant_cast`, every conjoined clause read),
    Voice of Victory's turn window, Teferi, Time Raveler's sorcery-speed limit
    (`sorcery_speed_restriction_source`), a zone cast prohibition whose every
    zone word is known (`zone_cast_prohibition_source`, CR 601.3), a draw cap
    (`draw_cap_restriction`, CR 121.2b), the search prohibition
    (`search_prohibition_source`) and the combat lockdown
    (`combat_lockdown_restriction_source`).
    """
    line = text.strip()
    if (
        _OPPONENTS_CANT_CAST_DURING_YOUR_TURN_RE.match(line)
        or _SORCERY_SPEED_ONLY_RE.match(line)
        or _SEARCH_PROHIBITION_RE.match(line)
        or _DURING_COMBAT_LOCKDOWN_RE.match(line)
    ):
        return True
    draw_cap = _DRAW_CAP_RE.match(line)
    if draw_cap is not None:
        return parse_count(draw_cap.group("count")) is not None
    zone_ban = _ZONE_CAST_PROHIBITION_RE.match(line)
    if zone_ban is not None:
        return bool(_prohibited_zones(zone_ban.group("zones")))
    clauses = [clause.strip() for clause in _RESTRICTION_CLAUSE_SPLIT.split(line.rstrip("."))]
    for clause in clauses:
        if _CAST_ONLY_DURING_TURN_RE.fullmatch(clause):
            continue
        cap = _SPELL_COUNT_CAP_RE.fullmatch(clause)
        if cap is None or parse_count(cap.group("count")) is None:
            return False
    return bool(clauses)
