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
"""

import re
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

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

    id: UUID = Field(default_factory=uuid4)
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


def targeted_cant_cast_restriction(game: Any, caster: str) -> CastingRuleEffect | None:
    """The recorded effect stopping `caster` from casting any spell at all
    right now (Orim's Chant), or None.

    Unlike `restricted_from_noncreature_casting`'s "your opponents" reading,
    this one names the restricted player directly, so the caster's own spell
    can restrict itself if it is somehow legally targeted at its own
    controller.
    """
    for effect in getattr(game, "casting_rule_effects", []):
        if effect.kind != CastingRuleKind.TARGETED_CANT_CAST:
            continue
        if effect.restricted_player == caster:
            return effect
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
