import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ...data.creature_types import creature_types
from ...data.subtypes import canonical_subtype, subtype_vocabulary
from ...models.card import Color, Type
from ...models.card_state import (
    CardState,
    Counter,
    ExileMarker,
)
from ...models.mana import ManaRetentionScope
from ...models.player import Player
from ...models.token import (
    PREDEFINED,
    TokenDefinition,
    create_tokens,
    is_token,
)
from ...models.zone import Zone
from ...numbers import (
    AMOUNT,
    COUNT,
    count_pattern,
    parse_count,
    where_x_pattern,
)
from .. import combat as combat_rules
from ..abilities import (
    TriggeredAbility,
    TriggerEvent,
)
from ..casting import (
    annotate_exile,
)
from ..casting_restrictions import create_targeted_cant_cast_restriction
from ..combat import has_keyword
from ..decisions import Decision, DecisionKind, source_id_of
from ..delayed import (
    DelayedTrigger,
    DrawACardForController,
    return_earthbent_land,
)
from ..layers import (
    ContinuousEffect,
    CreaturesControlledByWhereToughnessExceedsPower,
    Duration,
    Layer,
    RemainsOnBattlefield,
    Sublayer,
    add_type,
    count_card_types,
    creatures_controlled_by,
    grant_ability,
    only_this_incarnation,
    parsed_layer_effects,
    set_power_toughness,
)
from ..targeting import (
    permanent_description,
    profile_for_text,
)
from ..triggers import (
    AbilityOnStack,
    ExtraTriggerEvent,
    is_ability,
)

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ..conditions import claims
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, MIXED_CLAUSES, SPELL_TEXT
from ._common import _OBJECT_ANAPHOR, AbilityEffect, Effect, GroupPredicate, TargetedClause


def deal_damage(amount: int) -> Effect:
    """Deal `amount` damage to each target, permanent or player (CR 119.3).

    "Any target" means what it says: the same Bolt hits a creature or a face
    depending only on what was chosen when it was cast.

    The **source** is the spell itself. CR 120.1: "An object that deals damage is
    the source of that damage", and CR 120.2b: "the spell or ability will specify
    which object deals that damage" - Lightning Bolt's text is "Lightning Bolt
    deals 3 damage", so the resolving `CardState` on the stack is the source.
    Naming it is what lets CR 702.16e's protection, CR 615.8's next-instance
    shield and CR 609.7b's source-quality recheck see spell damage at all.
    """

    def effect(game: "Game", spell: CardState) -> None:
        for target in game.resolve_targets(spell):
            game.deal_damage(target, amount, source=spell)

    return effect


def _deal_damage_equal_to_sacrificed_creature_power(game: "Game", spell: CardState) -> None:
    """Fling: "deals damage equal to the sacrificed creature's power to any
    target" (CR 119.3). The creature is long gone from the battlefield by
    resolution (CR 118.8a's additional cost is paid before the spell is even
    put on the stack), so its power has to be read off whichever card
    `Game.cast_record(spell).additional_cost_cards` says paid the additional
    cost, wherever paying it left that card - `Game.find_by_id` still finds
    it in the graveyard. A `None`/absent power (no card recorded, or the
    printed power is `*`, which this engine cannot resolve off a card no
    longer on the battlefield to compute) deals zero rather than guessing;
    CR 107.1b already floors damage at not-negative, so a negative printed
    power (there is no such thing in practice) would floor the same way.
    """
    record = game.cast_record(spell)
    power = 0
    if record.additional_cost_cards:
        sacrificed = game.find_by_id(record.additional_cost_cards[0])
        if sacrificed is not None and sacrificed.power is not None:
            power = max(sacrificed.power, 0)
    for target in game.resolve_targets(spell):
        game.deal_damage(target, power, source=spell)


def deal_damage_equal_to_expression(reader: "AmountReader") -> Effect:
    """Combustion Technique's own "deals damage equal to `<expr>` to target
    creature" - `reader` is `amount_expression`'s own general arithmetic
    reader, evaluated fresh at resolution (CR 608.2c fixes the amount as the
    ability resolves, not when it is announced) rather than once at parse
    time, the same way `_deal_damage_equal_to_sacrificed_creature_power`
    reads its own one specific expression live. `obj` is the spell itself:
    CR 700.7's "this [something]", the only object an "it"/"this `<noun>`" term
    (`_OBJECT_CHARACTERISTIC_RE`, `_OBJECT_COUNTER_COUNT_RE`) can name from a
    spell's own text.
    """

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell).username
        amount = max(reader(game, controller, spell, 0), 0)
        for target in game.resolve_targets(spell):
            game.deal_damage(target, amount, source=spell)

    return effect


def deal_divided_damage(total: int, *, even_split: bool = False) -> Effect:
    """Damage "divided as you choose among one or two targets" (CR 601.2d),
    or Fireball's own "divided evenly, rounded down" when `even_split`.

    "The player announces the division. Each of these targets must receive at
    least one of whatever is being divided." W13 gives that announcement
    somewhere to live - `spell.division`, set by `Casting.announce_division`
    - and `_deal_divided_damage_shares` reads it when it is there. A caster
    who never announces one (every scenario that predates this mechanism)
    still gets the old fallback: split as evenly as it goes with the
    remainder on the first target, which for Electrolyze's 2 damage is the
    whole of it on one target, or 1 each on two either way.

    `even_split` is a different card entirely dictating the split, not the
    caster (CR 601.2d only applies "if the spell requires the player to
    divide" the effect, and this one does not) - floor division with the
    remainder simply dropped, never handed to any target, so a target can
    receive zero of a total spread thinner than the target count.

    Only targets that are still legal on resolution are paid out (CR 608.2b),
    and the share the illegal ones would have had is simply not dealt: the
    division is locked in at announcement and cannot be re-divided.
    """

    def effect(game: "Game", spell: CardState) -> None:
        _deal_divided_damage_shares(game, spell, total, even_split=even_split)

    return effect


def _divided_damage_shares(
    total: int, chosen: int, announced: list[int] | None, *, even_split: bool = False
) -> list[int]:
    """The per-target shares a divided-damage effect pays out (CR 601.2d).

    `announced` is `spell.division` - the caster's real CR 601.2c/d
    announcement, recorded by `Casting.announce_division` and carried on the
    spell. When it is there and matches the target count, it is used exactly
    as announced. When it is not (no caller ever announced one - every
    scenario that predates this mechanism, and any that still does not use
    it), the total is split as evenly as it goes with the remainder on the
    first target, exactly `deal_divided_damage`'s original behaviour.

    `even_split` skips `announced` altogether - there is never anything to
    announce for this shape (`TargetingProfile.division` is never populated
    for it, see `_DIVIDED_DAMAGE_RE`'s own docstring) - and floor-divides
    with the remainder dropped rather than assigned to the first targets.
    """
    if even_split:
        return [total // chosen] * chosen
    if announced is not None and len(announced) == chosen:
        return list(announced)
    shares = [total // chosen] * chosen
    for index in range(total % chosen):
        shares[index] += 1
    return shares


def _deal_divided_damage_shares(
    game: "Game", spell: "StackObject", total: int, *, even_split: bool = False
) -> None:
    """Pay out `total` damage divided among `spell.targets` (CR 601.2d, CR
    608.2b). Shared by `deal_divided_damage` (a fixed printed amount) and
    Shatterskull Smashing's own X-based, conditionally doubled version.

    `spell` is CR 602.2b's own "identical process" naming: a `CardState`
    (an actual spell) or an `AbilityOnStack` (Ral, Monsoon Mage's own −2)
    both carry `targets` and `division`, and CR 120.1's "an object that
    deals damage is the source of that damage" means the *source passed to
    `deal_damage`* has to be a real permanent either way - `spell` itself
    for a spell, `spell.source(game)` for an ability, since an ability has
    no card of its own (CR 405.1).
    """
    chosen = len(spell.targets)
    if chosen == 0 or total <= 0:
        return
    source = spell if isinstance(spell, CardState) else spell.source_or_last_known(game)
    shares = _divided_damage_shares(total, chosen, spell.division, even_split=even_split)
    for reference, share in zip(spell.targets, shares, strict=True):
        target = game.legal_target(spell, reference)
        if target is not None and share > 0:
            game.deal_damage(target, share, source=source)


def delirium_damage(normal: int, with_delirium: int) -> Effect:
    """Unholy Heat: 2 damage, or 6 with delirium.

    "Unholy Heat deals 2 damage to target creature or planeswalker. *Delirium* -
    Unholy Heat deals 6 damage instead if there are four or more card types
    among cards in your graveyard."

    *Delirium* is an ability word, and CR 207.2c says an ability word has "no
    special rules meaning" - it only ties similar cards together. So there is no
    delirium machinery to build: the whole condition is the sentence after the
    word, counting card types (CR 205.2a) among the cards in the controller's
    graveyard. `count_card_types` in `machines/layers.py` already does that
    count for Tarmogoyf, and it is the same count here.

    Nothing about this is a choice, so unlike a scry or a "you may", this entry
    is the card's whole effect and not a policy standing in for a player.
    """

    def effect(game: "Game", spell: CardState) -> None:
        graveyard = game.controller_of(spell).graveyard
        amount = with_delirium if count_card_types(graveyard) >= 4 else normal
        for target in game.resolve_targets(spell):
            game.deal_damage(target, amount, source=spell)

    return effect


#: "<name> deals N damage to target <targets>. Delirium - <name> deals M
#: damage instead if there are four or more card types among cards in your
#: graveyard." - Unholy Heat's whole text (CR 207.2c: *Delirium* is an
#: ability word, so the sentence after it is the whole condition, not a
#: keyword this wave needs machinery for). The card's own name is captured
#: and matched again with a backreference rather than written literally, so a
#: future card sharing this exact template - with a different pair of damage
#: amounts - reads for free; `normal`/`with_delirium` are read through
#: `numbers.COUNT` rather than pinned to Unholy Heat's own "2"/"6".
#:
#: The label itself is optional here, not required: `_prepare_effect_
#: clauses`'s own ability-word strip (CR 207.2c, `_strip_ability_word_
#: labels`) already removes "Delirium — " from `whole` before this ever
#: sees it, the same way `_COUNTER_INSTEAD_IF_POWER_RE` already treats
#: Stubborn Denial's own "Ferocious — " as optional - kept optional rather
#: than dropped outright so this still matches text that reached it some
#: other way, unstripped.
_DELIRIUM_DAMAGE_INSTEAD_RE = re.compile(
    rf"^(?P<name>.+?) deals {count_pattern('normal', article=False)} damage to target "
    r"(?P<targets>[^.]+)\.\s*"
    rf"(?:delirium\s*(?:—|-)\s*)?(?P=name) deals {count_pattern('with_delirium', article=False)} "
    r"damage instead if there are four or more card types among cards in your graveyard\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s12")
def _parse_delirium_damage_instead_clause(text: str) -> Effect | None:
    """`_DELIRIUM_DAMAGE_INSTEAD_RE`'s shape - Unholy Heat's whole text.

    `targets` is not read further here: `Game.resolve_targets` already
    enforces whatever the spell's own declared targets were restricted to at
    announcement (CR 601.2c), the same trust `delirium_damage` itself already
    placed in its caller before this parser existed.
    """
    match = _DELIRIUM_DAMAGE_INSTEAD_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    normal = parse_count(match.group("normal"), article=False)
    with_delirium = parse_count(match.group("with_delirium"), article=False)
    if normal is None or with_delirium is None:
        return None
    return delirium_damage(normal, with_delirium)


# --------------------------------------------------------------------------
# Tokens (CR 111, CR 701.7)
# --------------------------------------------------------------------------
#
# `models/token.py` holds what a token *is* and how one is created. What lives
# here is the other half: the printed text of each card that says "create ...",
# turned into a `TokenDefinition`. CR 111.3 is why that is a faithful reading and
# not a hand-written card - "the spell or ability that creates a token may define
# the values of any number of characteristics for the token. This becomes the
# token's 'text.'" The definition below each card *is* that sentence.

#: "0/1 colorless Eldrazi Spawn creature token with 'Sacrifice this token: Add
#: {C}.'" - Malevolent Rumble, Drowner of Truth, Kozilek's Command.
ELDRAZI_SPAWN = TokenDefinition(
    subtypes=("Eldrazi", "Spawn"),
    power=0,
    toughness=1,
    rules_text="Sacrifice this token: Add {C}.",
)

#: "1/1 red Elemental creature token" - Seasoned Pyromancer.
ELEMENTAL = TokenDefinition(subtypes=("Elemental",), colors=(Color.RED,), power=1, toughness=1)

#: "1/1 white Monk creature token with prowess" - Cori-Steel Cutter. Prowess is
#: CR 702.108a, "Whenever you cast a noncreature spell, this creature gets +1/+1
#: until end of turn", and is printed on the token as the keyword it is.
MONK = TokenDefinition(
    subtypes=("Monk",), colors=(Color.WHITE,), power=1, toughness=1, keywords=("Prowess",)
)

#: "1/1 red Warrior creature token" - Dalkovan Encampment's, created tapped and
#: attacking (CR 508.4).
WARRIOR = TokenDefinition(subtypes=("Warrior",), colors=(Color.RED,), power=1, toughness=1)


def prevent_all_combat_damage(game: "Game", spell: CardState) -> None:
    """Fog and Angelsong: "Prevent all combat damage that would be dealt this turn."

    CR 615.1a: "Effects that use the word 'prevent' are prevention effects.
    Prevention effects use 'prevent' to indicate what damage will not be dealt."

    Named neither a permanent nor a player, so the shield protects everything -
    `card_id` and `player` both left None. It is a `ShieldKind.ALL`, which
    CR 615.3 distinguishes from the other two by how it ends: "Such effects last
    until they're used up or their duration has expired." This one is never used
    up. It expires, in the cleanup step (CR 514.2), which is what
    `until_end_of_turn` means.

    CR 615.4 is the reason this is all the spell does: "Prevention effects must
    exist before the appropriate damage event occurs - they can't 'go back in
    time'." A Fog cast after combat damage has been dealt prevents nothing, and
    that falls out of creating the shield now rather than needing a check.

    Angelsong's cycling is a way to *not* cast it (CR 702.29a) and is
    `machines/casting.py`'s business, not this function's.
    """
    from ...models.game import PreventionShield, ShieldKind

    game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.ALL,
            label="prevent all combat damage that would be dealt this turn",
            controller=game.controller_of(spell).username,
            combat_only=True,
        )
    )


#: ecl-T8: Morningtide's Light's own "Until your next turn, prevent all
#: damage that would be dealt to you." - CR 615.1a's prevention again, this
#: time named at the resolving spell's or ability's own controller ("you")
#: rather than at everything (`prevent_all_combat_damage` above) or at a
#: target, and lasting CR 611.2a's "until your next turn" instead of "this
#: turn" - `PreventionShield.until_next_turn_of`, ended by `Game.
#: begin_turn_for` the identical moment every other "until your next turn"
#: store on that method already ends through, rather than `until_end_of_turn`'s
#: cleanup-step ending.
_PREVENT_ALL_DAMAGE_TO_YOU_UNTIL_NEXT_TURN_RE = re.compile(
    r"^until your next turn, prevent all damage that would be dealt to you\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s6")
def _parse_prevent_all_damage_to_you_until_next_turn_clause(clause: str) -> TargetedClause | None:
    """`_PREVENT_ALL_DAMAGE_TO_YOU_UNTIL_NEXT_TURN_RE`'s shape, or `None`."""
    if _PREVENT_ALL_DAMAGE_TO_YOU_UNTIL_NEXT_TURN_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from ...models.game import PreventionShield, ShieldKind

        controller = game.controller_of(stack_object).username
        game.create_prevention_shield(
            PreventionShield(
                kind=ShieldKind.ALL,
                label="prevent all damage that would be dealt to you until your next turn",
                controller=controller,
                player=controller,
                until_end_of_turn=False,
                until_next_turn_of=controller,
            )
        )

    return effect


#: "Prevent all [combat ]damage that would be dealt to him this turn." - the
#: rider on Oko, the Trickster's copy and the Gideons' animations, and on
#: any ability naming its own source ("him"/"her", or "this creature"/
#: "this permanent", which `_self_normalized_effect_text` makes of the
#: card's own name, CR 201.5). CR 615.1a's prevention effect as a shield
#: around the ability's source, lasting CR 514.2's "this turn". A bare "it"
#: is not read: on Djeru's Resolve it is the spell's target, not a source.
_PREVENT_ALL_DAMAGE_TO_SELF_THIS_TURN_RE = re.compile(
    r"^prevent all (?P<combat>combat )?damage that would be dealt to "
    r"(?:him|her|this creature|this permanent) this turn\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s7", for_spell=FORWARD)
def _parse_prevent_all_damage_to_self_this_turn_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_PREVENT_ALL_DAMAGE_TO_SELF_THIS_TURN_RE`'s shape, on an ability.

    The shield names the source *as this object* (CR 400.7): `lasts_while`
    holds only while that incarnation stays on the battlefield, so an Oko
    flickered out and back is a new object it never shielded."""
    if for_spell:
        return None
    match = _PREVENT_ALL_DAMAGE_TO_SELF_THIS_TURN_RE.fullmatch(" ".join(clause.split()))
    if match is None:
        return None
    combat_only = match.group("combat") is not None

    def effect(game: "Game", ability: "StackObject") -> None:
        from ...models.game import PreventionShield, ShieldKind

        if not isinstance(ability, AbilityOnStack):
            return
        source = ability.source(game)
        if (
            source is None
            or source.zone is not Zone.BATTLEFIELD
            or source.zone_change_stamp is None
            or ability.source_stamp not in (None, source.zone_change_stamp)
        ):
            return
        game.create_prevention_shield(
            PreventionShield(
                kind=ShieldKind.ALL,
                label=(
                    f"prevent all {'combat ' if combat_only else ''}damage that would be "
                    f"dealt to {source.name} this turn"
                ),
                controller=game.controller_of(ability).username,
                card_id=source.id,
                combat_only=combat_only,
                lasts_while=RemainsOnBattlefield(card_id=source.id, stamp=source.zone_change_stamp),
            )
        )

    return effect


def prevent_all_combat_damage_except(excluded: frozenset[str]) -> Effect:
    """Moonmist's second sentence: the Fog shield, minus the types it names.

    CR 615.1a's prevention effect again, but stated as an exclusion. The
    excluded types are handed to the shield as *words*, never resolved to a
    set of creatures here, because CR 609.7b rechecks the source's properties
    when the damage would be dealt: a Human that Moonmist has just transformed
    into a Werewolf is excluded when combat damage lands, and a creature that
    arrives after this resolves is still covered. Freezing a list of objects
    at resolution would get both of those wrong, and would fail open.
    """

    def effect(game: "Game", spell: CardState) -> None:
        from ...models.game import PreventionShield, ShieldKind

        game.create_prevention_shield(
            PreventionShield(
                kind=ShieldKind.ALL,
                label=(
                    "prevent all combat damage that would be dealt this turn "
                    f"by creatures other than {', '.join(sorted(excluded))}"
                ),
                controller=game.controller_of(spell).username,
                combat_only=True,
                excluded_source_subtypes=excluded,
            )
        )

    return effect  # type: ignore[return-value]


def prevent_next_damage_to_target(amount: int) -> Effect:
    """Bandage: "Prevent the next 1 damage that would be dealt to any target this
    turn." Then "Draw a card", which the registry sequences separately.

    CR 615.7 is this shield exactly: "Some prevention effects generated by the
    resolution of a spell or ability refer to a specific amount of damage - for
    example, 'Prevent the next 3 damage that would be dealt to any target this
    turn.' These work like shields. Each 1 damage that would be dealt to the
    'shielded' permanent or player is prevented. Preventing 1 damage reduces the
    remaining shield by 1 ... Once the shield has been reduced to 0, any
    remaining damage is dealt normally. Such effects count only the amount of
    damage; the number of events or sources dealing it doesn't matter."

    "Any target" is a permanent or a player (CR 115.1), which is why the shield
    is built with whichever of `card_id` and `player` the target turned out to be.
    A target that is no longer legal is skipped by CR 608.2b before this runs.
    """

    def effect(game: "Game", spell: CardState) -> None:
        from ...models.game import PreventionShield, ShieldKind

        controller = game.controller_of(spell).username
        for target in game.resolve_targets(spell):
            shielded = target if isinstance(target, CardState) else None
            game.create_prevention_shield(
                PreventionShield(
                    kind=ShieldKind.AMOUNT,
                    label=f"prevent the next {amount} damage that would be dealt "
                    f"to {getattr(target, 'name', None) or target.username} this turn",
                    controller=controller,
                    amount=amount,
                    card_id=None if shielded is None else shielded.id,
                    player=None if shielded is not None else target.username,
                )
            )

    return effect


def _prevent_next_damage_from_target(*, gains_life: bool) -> TargetedClause:
    """ "The next time target creature would deal damage this turn, prevent
    that damage[. You gain life equal to the damage prevented this way.]" -
    Awe Strike, read off the card's own text by `_merge_prevent_damage_from_
    target_clauses` rather than a table row.

    CR 615.8: "Some prevention effects generated by the resolution of a spell or
    ability refer to the next time a specific source would deal damage. These
    effects prevent the next instance of damage from that source, regardless of
    how much damage that is. Once an instance of damage from that source has been
    prevented, any subsequent instances of damage that would be dealt by that
    source are dealt normally."

    So the shield names a *source*, not a shielded object: `source_id` is the
    targeted creature and `card_id`/`player` stay None, because the damage is
    prevented wherever it was going.

    The rider is CR 615.5: "Some prevention effects also include an additional
    effect, which may refer to the amount of damage that was prevented. The
    prevention takes place at the time the original event would have happened;
    the rest of the effect takes place immediately afterward." "You gain life
    equal to the damage prevented this way" is such an effect, so `gains_life`
    - set only when the card's own second sentence says so - becomes the
    shield's `gains_life_when_prevented`, and `Game.apply_prevention_shield`
    performs it as the damage event is prevented.
    """

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from ...models.game import PreventionShield, ShieldKind

        for target in game.resolve_card_targets(stack_object):
            game.create_prevention_shield(
                PreventionShield(
                    kind=ShieldKind.NEXT_INSTANCE,
                    label=f"prevent the next damage {target.name} would deal this turn",
                    controller=game.controller_of(stack_object).username,
                    source_id=target.id,
                    gains_life_when_prevented=gains_life,
                )
            )

    return effect


# --------------------------------------------------------------------------
# The filtered fog family (CR 615.1a, CR 609.7b) - NW02-T2
# --------------------------------------------------------------------------
#
# "Prevent all [combat] damage that would be dealt [this turn] [to <who>]
# [this turn] [by <which sources>] [this turn]." - one shield per sentence,
# created as the spell resolves and ended by CR 514.2's cleanup. The
# recipient and the source filter travel to the `PreventionShield` as data
# (`players_only`, `player`, `card_id`, `ShieldSourceFilter`), never as a
# frozen list of objects: CR 609.7b rechecks the source as the damage would
# be dealt (the Moonmist precedent, `prevent_all_combat_damage_except`).

_FILTERED_FOG_RE = re.compile(
    r"^prevent all (?P<combat>combat )?damage that would be dealt"
    r"(?P<t1> this turn)?"
    r"(?: to (?P<recipient>[^.]+?))?"
    r"(?P<t2> this turn)?"
    r"(?: by (?P<sources>[^.]+?))?"
    r"(?P<t3> this turn)?\.?$",
    re.IGNORECASE,
)
#: "Prevent all [combat] damage that `<sources>` would deal [to `<who>`] this
#: turn." (Luminesce, Chameleon Blur, Haze Frog, Surge of Salvation) - the
#: same shield, its source filter named as the subject.
_FOG_WOULD_DEAL_RE = re.compile(
    r"^prevent all (?P<combat>combat )?damage that (?!would )(?P<sources>[^.]+?) would deal"
    r"(?: to (?P<recipient>[^.]+?))? this turn\.?$",
    re.IGNORECASE,
)
_FOG_COLOR_WORDS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}
_FOG_NONCOLOR_RE = re.compile(r"^non(?P<color>white|blue|black|red|green) creatures$")
_FOG_NO_COUNTER_RE = re.compile(r"^creatures with no (?P<counter>\S+) counters on them$")
_FOG_WITHOUT_KEYWORD_RE = re.compile(r"^creatures without (?P<keyword>[a-z]+(?: [a-z]+)?)$")
_FOG_MAX_POWER_RE = re.compile(
    rf"^creatures with power {count_pattern('n', article=False)} or less$"
)


@dataclass(frozen=True)
class _FogSpec:
    """One read "prevent all ..." sentence: what its shield protects, which
    sources it covers, and which of the spell's targets it names. A parse-time
    value only - the shield it builds is the persisted record."""

    text: str
    combat_only: bool
    recipient: str | None = None
    filter_fields: dict[str, Any] = field(default_factory=dict)
    opponents_of_you: bool = False
    source_target: str | None = None
    choose_source: bool = False
    recipient_types: tuple[Type, ...] = ()
    recipient_yours: bool = False
    you_and_permanents: bool = False
    recipient_count: int = 1
    excluded_subtypes: tuple[str, ...] = ()
    sources_not_yours: bool = False
    other_than_self: bool = False

    @property
    def targets(self) -> int:
        """How many of the spell's targets this sentence names (CR 601.2c)."""
        named = {"target creature": 1, "targets": self.recipient_count}.get(self.recipient or "", 0)
        return named + int(self.source_target is not None)


_FOG_SOURCE_COLORS_RE = re.compile(
    r"^(?P<first>white|blue|black|red|green)(?: sources)? (?:and|and/or|or) "
    r"(?P<second>white|blue|black|red|green) sources$"
)
_FOG_NON_SUBTYPE_SOURCES_RE = re.compile(r"^non-(?P<subtype>[a-z]+) sources$")


def _fog_source_spec(phrase: str, *, bare: bool = False) -> dict[str, Any] | None:
    """The `_FogSpec` fields a "by `<sources>`" (or "that `<sources>` would
    deal") phrase reads as, or None. `bare`: the sentence names no recipient
    and is in the "dealt by" form, where "by creatures" and "by `<quality>`
    sources" stay `replacement.parse.read_turn_damage_spec`'s."""
    from ..combat import Keyword

    lowered = " ".join(phrase.lower().split())
    if lowered == "creatures" and not bare:
        return {"filter_fields": {"creatures": True}}
    if lowered == "other creatures" and not bare:
        return {"filter_fields": {"creatures": True}, "other_than_self": True}
    if lowered == "colorless sources":
        # CR 105.2c: "A colorless object has no color."
        return {"filter_fields": {"creatures": False, "colorless": True}}
    if lowered == "sources you don't control":
        return {"filter_fields": {"creatures": False}, "sources_not_yours": True}
    if match := _FOG_SOURCE_COLORS_RE.fullmatch(lowered):
        colors = (_FOG_COLOR_WORDS[match.group("first")], _FOG_COLOR_WORDS[match.group("second")])
        return {"filter_fields": {"creatures": False, "colors_any": colors}}
    if not bare and (match := re.fullmatch(r"(?P<color>[a-z]+) sources", lowered)):
        color = _FOG_COLOR_WORDS.get(match.group("color"))
        if color is None:
            return None
        return {"filter_fields": {"creatures": False, "colors_any": (color,)}}
    if match := _FOG_NON_SUBTYPE_SOURCES_RE.fullmatch(lowered):
        wanted = match.group("subtype")
        subtype = next((kind for kind in creature_types() if kind.lower() == wanted), None)
        if subtype is None:
            return None
        return {"excluded_subtypes": (subtype,)}
    if lowered == "attacking creatures":
        return {"filter_fields": {"attacking": True}}
    if lowered == "creatures your opponents control":
        return {"opponents_of_you": True}
    if lowered == "creatures target opponent controls":
        return {"source_target": "opponent"}
    if lowered == "creatures other than target creature":
        return {"source_target": "creature"}
    if match := _FOG_NONCOLOR_RE.fullmatch(lowered):
        return {"filter_fields": {"excluded_colors": (_FOG_COLOR_WORDS[match.group("color")],)}}
    if match := _FOG_NO_COUNTER_RE.fullmatch(lowered):
        return {"filter_fields": {"without_counter": match.group("counter")}}
    if match := _FOG_WITHOUT_KEYWORD_RE.fullmatch(lowered):
        keyword = match.group("keyword")
        if keyword not in {member.value.lower() for member in Keyword}:
            return None
        return {"filter_fields": {"without_keyword": keyword}}
    if match := _FOG_MAX_POWER_RE.fullmatch(lowered):
        power = parse_count(match.group("n"), article=False)
        if power is None:
            return None
        return {"filter_fields": {"max_power": power}}
    return None


#: The card types a "to `<type>` creatures" recipient may add (Ethersworn
#: Shieldmage's "artifact creatures").
_FOG_RECIPIENT_TYPE_WORDS = {
    "artifact": Type.ARTIFACT,
    "enchantment": Type.ENCHANTMENT,
    "land": Type.LAND,
}
_FOG_TARGETS_RE = re.compile(
    rf"^(?P<upto>up to )?{count_pattern('n', article=False)} target creatures$"
)
#: "it" / "that creature" - CR 608.2c's anaphor back to a spell's own
#: earlier target ("Target creature gains flying until end of turn. Prevent
#: all damage that would be dealt to that creature this turn.").
_FOG_ANAPHOR_RE = re.compile(r"^(?:it|that creature)$")


def _fog_recipient_spec(phrase: str, *, for_spell: bool) -> dict[str, Any] | None:
    """The `_FogSpec` fields a "to `<who>`" phrase reads as, or None."""
    lowered = " ".join(phrase.lower().split())
    if lowered in ("players", "you", "target creature"):
        return {"recipient": lowered}
    if lowered == "you and permanents you control":
        return {"you_and_permanents": True}
    if lowered == "you and creatures you control":
        return {"you_and_permanents": True, "recipient_types": (Type.CREATURE,)}
    if lowered == "creatures you control":
        return {"recipient_types": (Type.CREATURE,), "recipient_yours": True}
    *qualifiers, noun = lowered.split()
    if noun == "creatures" and all(word in _FOG_RECIPIENT_TYPE_WORDS for word in qualifiers):
        types = tuple(_FOG_RECIPIENT_TYPE_WORDS[word] for word in qualifiers)
        return {"recipient_types": (*types, Type.CREATURE)}
    if _FOG_ANAPHOR_RE.fullmatch(lowered):
        # A spell's anaphor is its target (Djeru's Resolve); an ability's
        # "it" may be its own source (Favored Hoplite), read elsewhere.
        return {"recipient": "anaphor"} if for_spell else None
    if match := _FOG_TARGETS_RE.fullmatch(lowered):
        count = parse_count(match.group("n"), article=False)
        if count is None or count < 1:
            return None
        return {"recipient": "targets", "recipient_count": count}
    if lowered.startswith("target ") and "creature" in lowered and _targets_understood(phrase):
        # "target creature with power 5 or greater" (Godtoucher), "target
        # legendary creature" (Kitsune Healer): the restriction is the
        # targeting rule's (CR 601.2c); the shield names the chosen object.
        return {"recipient": "target creature"}
    return None


def _read_fog_sentence(
    sentence: str, *, allow_plain: bool = False, for_spell: bool = False
) -> _FogSpec | None:
    """`_FILTERED_FOG_RE`'s (or `_FOG_WOULD_DEAL_RE`'s) sentence, or None. A
    plain "Prevent all combat damage that would be dealt this turn." (Fog) is
    left to its own reader unless `allow_plain`, and "by creatures" / "by
    `<quality>` sources" alone to `replacement.parse.read_turn_damage_spec`'s
    created replacement."""
    text = " ".join(sentence.strip().split())
    if not text.lower().startswith("prevent all "):
        return None
    match = _FILTERED_FOG_RE.fullmatch(text)
    if match is not None:
        if sum(match.group(name) is not None for name in ("t1", "t2", "t3")) != 1:
            return None  # CR 611.2a: exactly one stated "this turn"
    else:
        match = _FOG_WOULD_DEAL_RE.fullmatch(text)
        if match is None:
            return None
    recipient = match.group("recipient")
    sources = match.group("sources")
    fields: dict[str, Any] = {}
    if recipient is not None:
        read = _fog_recipient_spec(recipient, for_spell=for_spell)
        if read is None:
            return None
        fields.update(read)
    if sources is not None:
        bare = recipient is None and "would deal" not in text.lower()
        read = _fog_source_spec(sources, bare=bare)
        if read is None:
            return None
        fields.update(read)
    elif recipient is None and not allow_plain:
        return None
    return _FogSpec(text=text.rstrip("."), combat_only=match.group("combat") is not None, **fields)


#: "Prevent all [combat] damage a source of your choice would deal this
#: turn." (Pay No Heed, Prahv, Spires of Order) - CR 609.7a's source, chosen
#: as the effect is created.
_SOURCE_OF_CHOICE_WOULD_DEAL_RE = re.compile(
    r"^prevent all (?P<combat>combat )?damage a source of your choice would deal this turn\.?$",
    re.IGNORECASE,
)


def _read_source_of_choice_sentence(sentence: str) -> _FogSpec | None:
    text = " ".join(sentence.strip().split())
    match = _SOURCE_OF_CHOICE_WOULD_DEAL_RE.fullmatch(text)
    if match is None:
        return None
    return _FogSpec(
        text=text.rstrip("."),
        combat_only=match.group("combat") is not None,
        choose_source=True,
    )


#: "Prevent all [combat] damage target creature would deal this turn." - one
#: sentence of a multi-sentence prevention spell (Azorius Ploy's first),
#: naming one target by its place in the text (CR 601.2c).
_TARGET_WOULD_DEAL_THIS_TURN_RE = re.compile(
    r"^prevent all (?P<combat>combat )?damage target (?:[a-z]+ )*?creature would deal "
    r"this turn\.?$",
    re.IGNORECASE,
)


def _read_target_would_deal_sentence(sentence: str) -> _FogSpec | None:
    text = " ".join(sentence.strip().split())
    match = _TARGET_WOULD_DEAL_THIS_TURN_RE.fullmatch(text)
    if match is None:
        return None
    phrase = text[text.lower().index("target ") : text.lower().index(" would deal")]
    if not _targets_understood(phrase):
        return None
    return _FogSpec(
        text=text.rstrip("."),
        combat_only=match.group("combat") is not None,
        source_target="dealer",
    )


def _create_fog_shield(
    game: "Game", stack_object: "StackObject", spec: _FogSpec, offset: int | None
) -> None:
    """Build `spec`'s shield as the spell or ability resolves.

    `offset` is the index of the sentence's first target among the creating
    object's targets (several prevention sentences, each naming its own -
    Azorius Ploy); None takes the first legal target of the right kind (a
    single sentence). A named target that is no longer legal leaves that
    shield uncreated (CR 608.2b)."""
    from ...models.game import PreventionShield, ShieldKind, ShieldSourceFilter

    controller = game.controller_of(stack_object).username
    refs = list(getattr(stack_object, "targets", ()) or ())
    position = offset

    def next_target(kind: str) -> Any:
        nonlocal position
        if position is not None:
            index = position
            position += 1
            if index >= len(refs):
                return None
            found = game.legal_target(stack_object, refs[index])
            return found if _is_kind(found, kind) else None
        for ref in refs:
            found = game.legal_target(stack_object, ref)
            if _is_kind(found, kind):
                return found
        return None

    fields: dict[str, Any] = {
        "kind": ShieldKind.ALL,
        "label": spec.text.lower(),
        "controller": controller,
        "combat_only": spec.combat_only,
    }
    filter_fields = dict(spec.filter_fields)
    # CR 601.2c: targets in the order the sentence names them.
    if spec.source_target == "dealer":
        dealer = next_target("creature")
        if dealer is None:
            return
        fields["source_id"] = dealer.id
        fields["source_stamp"] = dealer.zone_change_stamp
    elif spec.source_target == "spell":
        # CR 609.7a / CR 400.7c: a spell named as the source also covers the
        # permanent it becomes, so the shield holds no stamp.
        spell = next_target("card")
        if spell is None:
            return
        fields["source_id"] = spell.id
    shielded_objects: list[CardState] | None = None
    if spec.recipient == "players":
        fields["players_only"] = True
    elif spec.recipient == "you":
        fields["player"] = controller
    elif spec.recipient == "target creature":
        shielded = next_target("creature")
        if shielded is None:
            return
        fields["card_id"] = shielded.id
    elif spec.recipient in ("targets", "anaphor"):
        # "up to two target creatures" (CR 601.2c: any number up to two was
        # chosen) or "it"/"that creature" back to the spell's own target: one
        # shield per object still legal (CR 608.2b skips the rest).
        shielded_objects = [
            found
            for found in (game.legal_target(stack_object, ref) for ref in refs)
            if isinstance(found, CardState)
        ]
        if not shielded_objects:
            return
    if spec.you_and_permanents:
        fields["and_permanents_of"] = controller
    if spec.recipient_types:
        fields["recipient_types"] = spec.recipient_types
    if spec.recipient_yours:
        fields["recipient_controller"] = controller
    if spec.excluded_subtypes:
        fields["excluded_source_subtypes"] = frozenset(spec.excluded_subtypes)
    if spec.sources_not_yours:
        filter_fields["not_controlled_by"] = controller
    if spec.other_than_self:
        source = stack_object.source(game) if isinstance(stack_object, AbilityOnStack) else None
        if source is not None:
            filter_fields["excluded_card_id"] = source.id
            filter_fields["excluded_stamp"] = source.zone_change_stamp
    if spec.source_target == "opponent":
        opponent = next_target("player")
        if opponent is None:
            return
        filter_fields["controller"] = opponent.username
    elif spec.source_target == "creature":
        spared = next_target("creature")
        if spared is None:
            return
        filter_fields["excluded_card_id"] = spared.id
        filter_fields["excluded_stamp"] = spared.zone_change_stamp
    if spec.opponents_of_you:
        filter_fields["opponents_of"] = controller
    if spec.choose_source:
        from ..damage_modification import _choose_a_source

        chosen = _choose_a_source(game, controller, stack_object)
        if chosen is None:
            return
        fields["source_id"] = chosen.id
        # CR 609.7a: a permanent spell chosen on the stack also covers the
        # permanent it becomes, so only a permanent is held to its stamp.
        fields["source_stamp"] = (
            chosen.zone_change_stamp if chosen.zone is Zone.BATTLEFIELD else None
        )
    if filter_fields:
        fields["source_filter"] = ShieldSourceFilter(**filter_fields)
    if shielded_objects is None:
        game.create_prevention_shield(PreventionShield(**fields))
        return
    for shielded in shielded_objects:
        game.create_prevention_shield(
            PreventionShield(
                **fields
                | {"card_id": shielded.id, "label": f"{spec.text.lower()} ({shielded.name})"}
            )
        )


def _is_kind(found: Any, kind: str) -> bool:
    if found is None:
        return False
    if kind == "player":
        return isinstance(found, Player)
    return isinstance(found, CardState)


def _fog_clause(spec: _FogSpec, offset: int | None = None) -> TargetedClause:
    def effect(game: "Game", stack_object: "StackObject") -> None:
        _create_fog_shield(game, stack_object, spec, offset)

    return effect


@MIXED_CLAUSE.rung("s6")
def _parse_filtered_prevention_clause(clause: str) -> TargetedClause | None:
    """One filtered-fog or source-of-your-choice sentence, on a spell or an
    ability (Commencement of Festivities, Hunter's Ambush, Pay No Heed,
    Prahv's activated ability)."""
    if "prevent all " not in clause.lower():
        return None
    spec = _read_fog_sentence(clause) or _read_source_of_choice_sentence(clause)
    if spec is None or (spec.targets > 1 and spec.recipient != "targets"):
        return None
    if spec.recipient == "targets" and spec.source_target is not None:
        return None
    return _fog_clause(spec)


@MIXED_CLAUSE.rung("s7", for_spell=FORWARD)
def _parse_prevent_all_damage_to_spell_anaphor_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """A fog sentence whose recipient is "it" / "that creature" on a spell
    (Djeru's Resolve, Leap of Faith, Lithomancer's Focus, Fleeting Flight):
    CR 608.2c's anaphor back to the spell's own target, one shield per
    target still legal as it resolves (CR 608.2b). On an ability the same
    word can name the ability's source, so it is not read here."""
    if not for_spell or "prevent all " not in clause.lower():
        return None
    spec = _read_fog_sentence(clause, for_spell=True)
    if spec is None or spec.recipient != "anaphor" or spec.source_target is not None:
        return None
    return _fog_clause(spec)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_whole_fog_sentence_with_and_clauses(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """One fog sentence whose own recipient or source list carries an "and"
    ("to you and creatures you control", "that black sources and red sources
    would deal", "black and/or red sources"), read whole before the clause
    splitter cuts it at that "and" into two fragments neither reads alone."""
    lowered = text.lower()
    if " and" not in lowered or not lowered.lstrip().startswith("prevent all "):
        return None
    body = " ".join(text.strip().split())
    if len(_SENTENCE_BREAK_RE.split(body)) != 1:
        return None
    spec = _read_fog_sentence(body, for_spell=for_spell)
    if spec is None or spec.targets > 1:
        return None
    return [_fog_clause(spec)]


#: "If it's `<state>`, `<rider on it>`." after a spell's anaphor fog
#: (Enshrouding Mist's "If it's renowned, untap it."): CR 608.2c's anaphor
#: in both the condition and the rider is the fog's own referent, the
#: spell's target.
_FOG_REFERENT_CONDITION_RE = re.compile(
    r"^if (?:it's|it is|that creature is) (?P<state>[a-z ]+?), (?P<rider>[^.]+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_fog_on_spell_anaphor_then_state_rider_clauses(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """A spell's anaphor fog sentence (`_parse_prevent_all_damage_to_spell_
    anaphor_clause`'s) followed by `_FOG_REFERENT_CONDITION_RE`'s rider.

    The referents are the spell's targets still legal as it resolves (CR
    608.2b). Each gets the shield (CR 615.1a); then the condition is checked
    against that object as it is now (CR 608.2c, CR 702.112b for "renowned")
    and the rider runs on it only if the condition holds."""
    if not for_spell or "prevent all " not in text.lower() or "if it" not in text.lower():
        return None
    sentences = _SENTENCE_BREAK_RE.split(" ".join(text.strip().split()))
    if len(sentences) != 2:
        return None
    spec = _read_fog_sentence(sentences[0], for_spell=True)
    rider_match = _FOG_REFERENT_CONDITION_RE.fullmatch(sentences[1])
    if spec is None or spec.recipient != "anaphor" or rider_match is None:
        return None
    condition = f"this creature is {rider_match.group('state').strip()}"
    if not claims(condition):
        return None
    rider = _parse_referent_object_clause(rider_match.group("rider"))
    if rider is None:
        return None

    def clause(game: "Game", spell: "StackObject") -> None:
        referents = [
            found
            for found in (game.legal_target(spell, ref) for ref in spell.targets)
            if isinstance(found, CardState)
        ]
        _create_fog_shield(game, spell, spec, None)
        controller = game.controller_of(spell).username
        for referent in referents:
            if referent.zone is not Zone.BATTLEFIELD:
                continue
            if game.condition_holds(controller, condition, referent):
                rider(game, [referent], spell)

    return [clause]


_SENTENCE_BREAK_RE = re.compile(r"(?<=\.)\s+(?=[A-Z])")


def _read_prevention_sentence(sentence: str, *, allow_plain: bool = False) -> _FogSpec | None:
    return (
        _read_fog_sentence(sentence, allow_plain=allow_plain)
        or _read_target_would_deal_sentence(sentence)
        or _read_source_of_choice_sentence(sentence)
    )


#: Winds of Qal Sisma: "Prevent all combat damage that would be dealt this
#: turn. Ferocious - If you control a creature with power 4 or greater,
#: instead prevent all combat damage that would be dealt this turn by
#: creatures your opponents control." The ability word (CR 207.2c) carries
#: no rules meaning; the condition is read as the spell resolves and picks
#: one of the two shields - "instead" replaces the first instruction with the
#: second (CR 614.1a's word, a choice made on resolution).
_PREVENT_INSTEAD_IF_RE = re.compile(
    r"^(?P<first>prevent all [^.]+\.)\s*(?:[a-z][a-z' ]*?\s*(?:—|-)\s*)?"
    r"if (?P<condition>[^,]+), instead (?P<second>prevent all [^.]+\.?)$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s8")
def _parse_prevention_sentences_text(text: str) -> Effect | None:
    """A spell made only of prevention sentences, each read as its own
    shield with its own targets (Azorius Ploy: "Prevent all combat damage
    target creature would deal this turn. Prevent all combat damage that would
    be dealt to target creature this turn."), or the ability-word "instead"
    pair (Winds of Qal Sisma)."""
    body = " ".join(text.strip().split())
    if not body.lower().startswith("prevent all "):
        return None
    if match := _PREVENT_INSTEAD_IF_RE.fullmatch(body):
        first = _read_prevention_sentence(match.group("first"), allow_plain=True)
        second = _read_prevention_sentence(match.group("second"), allow_plain=True)
        condition = match.group("condition").strip()
        if first is None or second is None or first.targets or second.targets:
            return None
        if not claims(condition):
            return None

        def instead(game: "Game", spell: CardState) -> None:
            controller = game.controller_of(spell).username
            chosen = second if game.condition_holds(controller, condition, spell) else first
            _create_fog_shield(game, spell, chosen, None)

        return instead
    sentences = _SENTENCE_BREAK_RE.split(body)
    if len(sentences) < 2:
        return None
    specs = [_read_prevention_sentence(sentence) for sentence in sentences]
    if any(spec is None or spec.recipient == "targets" for spec in specs):
        return None
    clauses: list[TargetedClause] = []
    offset = 0
    for spec in specs:
        assert spec is not None
        clauses.append(_fog_clause(spec, offset))
        offset += spec.targets

    def sequence(game: "Game", spell: CardState) -> None:
        for clause in clauses:
            clause(game, spell)

    return sequence


#: CR 615.5's rider after a filtered fog: "If damage is prevented this way,
#: you may have `<this spell>` deal that much damage to target creature."
#: (Channel Harm). The prevention happens as the damage would be dealt; the
#: rider's damage immediately afterward, each time.
_FOG_REFLECT_RIDER_RE = re.compile(
    r"^if damage is prevented this way, (?:(?P<may>you may have) )?(?P<name>[^.]+?) "
    r"deals? that much damage to (?P<target>any target|target [^.]+?)\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s8")
def _parse_fog_then_reflect_rider_text(text: str) -> Effect | None:
    """A filtered-fog sentence followed by `_FOG_REFLECT_RIDER_RE`'s rider.

    The fog names no target of its own, so the spell's one target is the
    rider's (CR 601.2c), chosen as it is cast; a target no longer legal on
    resolution leaves the spell nothing to do (CR 608.2b)."""
    body = " ".join(text.strip().split())
    if "prevented this way" not in body.lower() or not body.lower().startswith("prevent all "):
        return None
    sentences = _SENTENCE_BREAK_RE.split(body)
    if len(sentences) != 2:
        return None
    spec = _read_fog_sentence(sentences[0])
    rider = _FOG_REFLECT_RIDER_RE.fullmatch(sentences[1])
    if spec is None or rider is None or spec.targets or spec.choose_source:
        return None
    if not _targets_understood(rider.group("target"), allow_player_targets=True):
        return None
    optional = rider.group("may") is not None

    def effect(game: "Game", spell: CardState) -> None:
        from ...models.game import ReflectedDamage

        targets = game.resolve_targets(spell)
        if not targets:
            return  # CR 608.2b
        target = targets[0]
        reflects = ReflectedDamage(
            source_id=spell.id,
            target_card_id=target.id if isinstance(target, CardState) else None,
            target_stamp=target.zone_change_stamp if isinstance(target, CardState) else None,
            target_player=target.username if isinstance(target, Player) else None,
            optional=optional,
        )
        before = len(game.prevention_shields)
        _create_fog_shield(game, spell, spec, None)
        for index in range(before, len(game.prevention_shields)):
            game.prevention_shields[index] = game.prevention_shields[index].model_copy(
                update={"reflects": reflects}
            )

    return effect


# --------------------------------------------------------------------------
# "Prevent the next N damage that [a source of your choice] would deal to
# you and/or permanents you control this turn. If damage is prevented this
# way, <this spell> deals that much damage to any target." (Refraction Trap,
# Divine Deflection) - CR 615.7's counting shield around a player and every
# permanent they control, with CR 615.5's damage rider.
# --------------------------------------------------------------------------

_PREVENT_NEXT_TO_YOU_AND_PERMANENTS_RE = re.compile(
    rf"^prevent the next (?:(?P<x>x)|{count_pattern('n', article=False)}) damage that "
    r"(?:(?P<choice>a source of your choice) would deal to|would be dealt to) "
    r"you and/or permanents you control this turn\."
    r"(?:\s*if damage is prevented this way, (?P<name>[^.]+?) deals that much damage to "
    r"(?P<target>any target)\.)?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s8")
def _parse_prevent_next_damage_to_you_and_permanents_text(text: str) -> Effect | None:
    """`_PREVENT_NEXT_TO_YOU_AND_PERMANENTS_RE`'s shape.

    The shield is `and_permanents_of` its controller: CR 615.7's "shielded"
    player and every permanent that player controls as the damage would be
    dealt. The source (if the text asks for one) is chosen as the spell
    resolves (CR 609.7a). The rider's target is chosen as the spell is cast,
    like every target it requires (CR 601.2c), and is dealt the prevented
    amount each time damage is prevented (CR 615.5)."""
    body = " ".join(text.strip().split())
    if "you and/or permanents you control" not in body.lower():
        return None
    match = _PREVENT_NEXT_TO_YOU_AND_PERMANENTS_RE.fullmatch(body)
    if match is None:
        return None
    fixed = None if match.group("x") else parse_count(match.group("n"), article=False)
    if match.group("x") is None and fixed is None:
        return None
    chooses = match.group("choice") is not None
    reflects = match.group("target") is not None

    def effect(game: "Game", spell: CardState) -> None:
        from ...models.game import PreventionShield, ReflectedDamage, ShieldKind
        from ..damage_modification import _choose_a_source

        controller = game.controller_of(spell).username
        amount = fixed if fixed is not None else (game.cast_record(spell).x_value or 0)
        if amount <= 0:
            return
        fields: dict[str, Any] = {}
        if reflects:
            targets = game.resolve_targets(spell)
            if not targets:
                return  # CR 608.2b
            target = targets[0]
            fields["reflects"] = ReflectedDamage(
                source_id=spell.id,
                target_card_id=target.id if isinstance(target, CardState) else None,
                target_stamp=target.zone_change_stamp if isinstance(target, CardState) else None,
                target_player=target.username if isinstance(target, Player) else None,
            )
        if chooses:
            chosen = _choose_a_source(game, controller, spell)
            if chosen is None:
                return
            fields["source_id"] = chosen.id
            fields["source_stamp"] = (
                chosen.zone_change_stamp if chosen.zone is Zone.BATTLEFIELD else None
            )
        game.create_prevention_shield(
            PreventionShield(
                kind=ShieldKind.AMOUNT,
                label=(
                    f"prevent the next {amount} damage that would be dealt to {controller} "
                    "and/or permanents they control this turn"
                ),
                controller=controller,
                amount=amount,
                and_permanents_of=controller,
                **fields,
            )
        )

    return effect


# --------------------------------------------------------------------------
# Next-N shields and CR 615.5's "prevented this way" payoffs - NW03-T7
# --------------------------------------------------------------------------
#
# "Prevent the next <N | X> damage that would be dealt to <you | any target |
# target ...> this turn[, where X is <amount>][ by a source of your choice]."
# (Festival of the Guildpact, Acolyte's Reward, Healing Grace, Reinforced
# Bulwark), "Prevent all damage that would be dealt to target <...> this
# turn." and "Prevent all damage target <...> spell would deal this turn."
# (Brace for Impact, Hallow, Dromoka's Command) - each optionally followed by
# one CR 615.5 payoff sentence that refers to the amount prevented:
#
# - "If damage is prevented this way, <self> deals that much damage to
#   <target>." (Acolyte's Reward, Vengeful Archon) - `ReflectedDamage`;
# - "For each 1 damage prevented this way, put a +1/+1 counter on that
#   creature." (Test of Faith, Brace for Impact) - `counters_when_prevented`;
# - "You gain life equal to the damage prevented this way." (Hallow,
#   Candles' Glow) - `gains_life_when_prevented`.
#
# The payoff travels on the persisted `PreventionShield` and is performed by
# `Game.apply_prevention_shield` "immediately afterward" (CR 615.5), each time
# the shield prevents damage.

_NEXT_N_SHIELD_RE = re.compile(
    rf"^prevent the next (?:(?P<x>x)|{count_pattern('n', article=False)}) damage that would be "
    r"dealt to (?P<recipient>you|any target|target [^.,]+?) this turn"
    r"(?:, where x is (?P<where_x>[^.]+?))?"
    r"(?P<choice> by a source of your choice)?\.?$",
    re.IGNORECASE,
)
#: "Prevent all [combat] damage target <...> spell would deal this turn."
#: (Hallow, Dromoka's Command): CR 609.7a's spell source, named by target.
_TARGET_SPELL_WOULD_DEAL_RE = re.compile(
    r"^prevent all (?P<combat>combat )?damage (?P<phrase>target (?:[a-z]+ (?:or [a-z]+ )?)?spell) "
    r"would deal this turn\.?$",
    re.IGNORECASE,
)
_PAYOFF_COUNTERS_RE = re.compile(
    r"^for each 1 damage prevented this way, put an? (?P<kind>[+-]\d+/[+-]\d+) counter on "
    r"(?:that creature|it)\.?$",
    re.IGNORECASE,
)
_PAYOFF_LIFE_RE = re.compile(
    r"^you gain life equal to the damage prevented this way\.?$", re.IGNORECASE
)
#: The `<self>` of "<self> deals that much damage": the object whose text
#: this is - "this creature", "this spell", or its own (capitalised) name.
_PAYOFF_SELF_RE = re.compile(r"^(?:this [a-z]+|(?-i:[A-Z])[^.]*)$", re.IGNORECASE)
_ANAPHOR_SUBJECT_RE = re.compile(r"^(?:that|those|it|they|each|target)\b", re.IGNORECASE)


@dataclass(frozen=True)
class _ShieldSentence:
    """One read shield sentence: a CR 615.7 next-N shield (`fog` None) or a
    prevent-all shield `_create_fog_shield` builds (`fog`). Parse-time only."""

    text: str
    targets: int
    fixed: int | None = None
    x_from_cost: bool = False
    where_x: str | None = None
    """"where X is `<amount>`": the amount phrase, read by
    `amount_expression` as the clause is built."""
    to_you: bool = False
    choose_source: bool = False
    fog: _FogSpec | None = None
    names_a_creature: bool = False
    """The shield protects a targeted creature - what "that creature" in a
    counters payoff can refer to."""
    read_elsewhere: bool = False
    """The sentence alone is already read by an older reader (Bandage's
    fixed next-N to a target, a plain fog to a target creature): claimed
    here only together with a payoff."""


@dataclass(frozen=True)
class _ShieldPayoff:
    reflect_target: str | None = None
    reflect_optional: bool = False
    counters: str | None = None
    gains_life: bool = False

    @property
    def targets(self) -> int:
        return int(self.reflect_target is not None)


def _read_shield_sentence(sentence: str) -> _ShieldSentence | None:
    text = " ".join(sentence.strip().split())
    lowered = text.lower()
    if lowered.startswith("prevent the next "):
        match = _NEXT_N_SHIELD_RE.fullmatch(text)
        if match is None:
            return None
        recipient = match.group("recipient")
        where_phrase = match.group("where_x")
        is_x = match.group("x") is not None
        fixed = None if is_x else parse_count(match.group("n"), article=False)
        if not is_x and (fixed is None or where_phrase is not None):
            return None
        if where_phrase is not None and amount_expression(where_phrase) is None:
            return None
        to_you = recipient.lower() == "you"
        if not to_you and not _targets_understood(recipient, allow_player_targets=True):
            return None
        choose_source = match.group("choice") is not None
        return _ShieldSentence(
            text=text.rstrip("."),
            targets=0 if to_you else 1,
            fixed=fixed,
            x_from_cost=is_x and where_phrase is None,
            where_x=where_phrase,
            to_you=to_you,
            choose_source=choose_source,
            names_a_creature=not to_you and "creature" in recipient.lower(),
            read_elsewhere=not to_you and not is_x and not choose_source,
        )
    if not lowered.startswith("prevent all "):
        return None
    if match := _TARGET_SPELL_WOULD_DEAL_RE.fullmatch(text):
        if not _targets_understood(match.group("phrase"), battlefield_only=False):
            return None
        spec = _FogSpec(
            text=text.rstrip("."),
            combat_only=match.group("combat") is not None,
            source_target="spell",
        )
        return _ShieldSentence(text=spec.text, targets=1, fog=spec)
    spec = _read_fog_sentence(text, for_spell=True)
    if spec is None or spec.recipient != "target creature" or spec.source_target is not None:
        return None
    return _ShieldSentence(
        text=spec.text, targets=1, fog=spec, names_a_creature=True, read_elsewhere=True
    )


def _read_shield_payoff(sentence: str, shield: _ShieldSentence) -> _ShieldPayoff | None:
    text = " ".join(sentence.strip().split())
    if "prevented this way" not in text.lower():
        return None
    if _PAYOFF_LIFE_RE.fullmatch(text):
        return _ShieldPayoff(gains_life=True)
    if match := _PAYOFF_COUNTERS_RE.fullmatch(text):
        # "that creature" is the shielded creature - only a shield that
        # protects one has a referent (CR 608.2c).
        return _ShieldPayoff(counters=match.group("kind")) if shield.names_a_creature else None
    if match := _FOG_REFLECT_RIDER_RE.fullmatch(text):
        name = match.group("name").strip()
        if _ANAPHOR_SUBJECT_RE.match(name) or not _PAYOFF_SELF_RE.fullmatch(name):
            return None
        target = match.group("target")
        if not _targets_understood(target, allow_player_targets=True):
            return None
        return _ShieldPayoff(reflect_target=target, reflect_optional=match.group("may") is not None)
    return None


def _announced_x(game: "Game", stack_object: "StackObject") -> int:
    """CR 107.3a: the X announced for this spell or activated ability."""
    if isinstance(stack_object, AbilityOnStack):
        return stack_object.x_value or 0
    return game.cast_record(stack_object).x_value or 0


def _reflected_damage(
    game: "Game", stack_object: "StackObject", payoff: _ShieldPayoff, index: int
) -> Any:
    """The `ReflectedDamage` for a payoff whose target sits at `index` of the
    object's targets, or None when that target is gone (CR 608.2b: the rest of
    the effect still happens without it)."""
    from ...models.game import ReflectedDamage

    refs = list(getattr(stack_object, "targets", ()) or ())
    if payoff.reflect_target is None or index >= len(refs):
        return None
    target = game.legal_target(stack_object, refs[index])
    source = _resolving_source(game, stack_object)
    if source is None or not isinstance(target, CardState | Player):
        return None
    return ReflectedDamage(
        source_id=source.id,
        target_card_id=target.id if isinstance(target, CardState) else None,
        target_stamp=target.zone_change_stamp if isinstance(target, CardState) else None,
        target_player=target.username if isinstance(target, Player) else None,
        optional=payoff.reflect_optional,
    )


def _create_payoff_shield(
    game: "Game",
    stack_object: "StackObject",
    shield: _ShieldSentence,
    payoff: _ShieldPayoff | None,
    where_x: "AmountReader | None",
) -> None:
    """Build `shield` as the spell or ability resolves, carrying `payoff`.

    Targets are read in the order the text names them (CR 601.2c): the
    shield's own first, then the payoff's. A shield whose own target is gone
    is not created (CR 608.2b); a payoff whose target is gone leaves the
    shield without that payoff."""
    from ...models.game import PreventionShield, ShieldKind
    from ..damage_modification import _choose_a_source

    fields: dict[str, Any] = {}
    if payoff is not None:
        reflects = _reflected_damage(game, stack_object, payoff, shield.targets)
        if reflects is not None:
            fields["reflects"] = reflects
        if payoff.counters is not None:
            fields["counters_when_prevented"] = payoff.counters
        if payoff.gains_life:
            fields["gains_life_when_prevented"] = True
    if shield.fog is not None:
        before = len(game.prevention_shields)
        _create_fog_shield(game, stack_object, shield.fog, 0)
        for index in range(before, len(game.prevention_shields)):
            game.prevention_shields[index] = game.prevention_shields[index].model_copy(
                update=fields
            )
        return
    controller = game.controller_of(stack_object).username
    if where_x is not None:
        source = _resolving_source(game, stack_object)
        if source is None:
            return
        # CR 608.2h: X is read once, as the shield is created.
        amount = where_x(game, controller, source, _announced_x(game, stack_object))
    elif shield.x_from_cost:
        amount = _announced_x(game, stack_object)
    else:
        amount = shield.fixed or 0
    if amount <= 0:
        return
    if shield.to_you:
        fields["player"] = controller
        shielded_name = controller
    else:
        refs = list(getattr(stack_object, "targets", ()) or ())
        target = game.legal_target(stack_object, refs[0]) if refs else None
        if isinstance(target, CardState):
            fields["card_id"] = target.id
            shielded_name = target.name
        elif isinstance(target, Player):
            fields["player"] = target.username
            shielded_name = target.username
        else:
            return  # CR 608.2b
    if shield.choose_source:
        chosen = _choose_a_source(game, controller, stack_object)
        if chosen is None:
            return
        fields["source_id"] = chosen.id
        # CR 609.7a: a permanent spell chosen on the stack also covers the
        # permanent it becomes, so only a permanent is held to its stamp.
        fields["source_stamp"] = (
            chosen.zone_change_stamp if chosen.zone is Zone.BATTLEFIELD else None
        )
    game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.AMOUNT,
            label=f"prevent the next {amount} damage that would be dealt to {shielded_name} "
            "this turn",
            controller=controller,
            amount=amount,
            **fields,
        )
    )


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_prevention_shield_with_payoff_clauses(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """A shield sentence (`_read_shield_sentence`), an optional CR 615.5
    payoff sentence right after it (`_read_shield_payoff`), and any further
    independent sentences read as ordinary clauses ("Draw a card.", "You gain
    3 life.") - see the banner above. A shield sentence an older reader
    already reads alone is claimed only together with its payoff."""
    if "prevent " not in text.lower():
        return None
    sentences = _plain_resolution_sentences(_strip_non_effect_preamble(text))
    if not sentences:
        return None
    shield = _read_shield_sentence(sentences[0])
    if shield is None:
        return None
    rest = sentences[1:]
    payoff = _read_shield_payoff(rest[0], shield) if rest else None
    if payoff is not None:
        rest = rest[1:]
    elif shield.read_elsewhere:
        return None
    elif rest and "prevented this way" in rest[0].lower():
        return None  # an unread payoff: never dropped silently
    tail: list[TargetedClause] = []
    if rest:
        read = _parse_mixed_clauses(" ".join(rest), for_spell=for_spell)
        if read is None:
            return None
        tail = read

    where_x = amount_expression(shield.where_x) if shield.where_x is not None else None

    def clause(game: "Game", stack_object: "StackObject") -> None:
        _create_payoff_shield(game, stack_object, shield, payoff, where_x)

    return [clause, *tail]


# --------------------------------------------------------------------------
# "<this spell> deals N damage to <target>. The damage can't be prevented.
# [If that player or that planeswalker's controller would gain life this
# turn, that player gains no life instead.]" (Flames of the Blood Hand,
# Combust) - CR 615.12 for this one damage event, and a turn-long CR 614.1a
# replacement of the damaged player's life gain.
# --------------------------------------------------------------------------

_UNPREVENTABLE_DAMAGE_RE = re.compile(
    rf"^(?P<name>[^.]+?) deals {count_pattern('n', article=False)} damage to "
    r"(?P<phrase>target [^.]+?)\. the damage can'?t be prevented\."
    r"(?P<ban> if that player or that planeswalker'?s controller would gain life this turn, "
    r"that player gains no life instead\.)?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s8")
def _parse_unpreventable_damage_text(text: str) -> Effect | None:
    """`_UNPREVENTABLE_DAMAGE_RE`'s shape. "The damage" is the sentence
    before's own damage, so it is dealt `unpreventable` (CR 615.12) rather than
    recorded as Skullcrack's turn-wide "Damage can't be prevented this turn.";
    the no-life-gain rider is a `GainNoLifeReplacement` on the player hit, or
    on the planeswalker's controller (CR 614.1a, CR 119.10), until cleanup."""
    body = " ".join(text.strip().split())
    if "the damage can" not in body.lower():
        return None
    match = _UNPREVENTABLE_DAMAGE_RE.fullmatch(body)
    if match is None:
        return None
    amount = parse_count(match.group("n"), article=False)
    phrase = match.group("phrase")
    if amount is None or not _targets_understood(phrase, allow_player_targets=True):
        return None
    bans_life_gain = match.group("ban") is not None

    def effect(game: "Game", spell: CardState) -> None:
        from ..replacement import CreatedReplacement, GainNoLifeReplacement

        controller = game.controller_of(spell).username
        for target in game.resolve_targets(spell):
            if isinstance(target, CardState) and target.zone is not Zone.BATTLEFIELD:
                continue
            game.deal_damage(target, amount, source=spell, unpreventable=True)
            if not bans_life_gain:
                continue
            player = (
                target.username
                if isinstance(target, Player)
                else game.controller_of(target).username
            )
            game.created_replacements.append(
                CreatedReplacement(
                    spec=GainNoLifeReplacement(player=player),
                    label=f"if {player} would gain life this turn, {player} gains no life instead",
                    controller=controller,
                    source_id=spell.id,
                    source_name=spell.name,
                )
            )

    return effect


def damage_each_opponent(amount: int) -> AbilityEffect:
    """Guttersnipe: "this creature deals 2 damage to each opponent" (CR 119.3).

    "This creature" is the source (CR 120.2b), and CR 113.7a lets it be gone by
    the time the ability resolves - the damage is then dealt by nothing this
    engine can point at, which `Game.deal_damage` accepts as `source=None`.
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        for opponent in _opponents(game, ability.controller):
            game.deal_damage(opponent, amount, source=source)

    return effect


def damage_to_itself(amount: int) -> AbilityEffect:
    """ "This creature/permanent deals N damage to itself" (CR 119.3, CR
    120.2b) - Goblin Kaboomist's own "this creature deals 2 damage to
    itself", the losing half of its coin flip.

    "Itself" is the ability's own source, still on the battlefield or this
    does nothing (CR 113.7a: gone by resolution is not a legal target for a
    non-targeted effect to still find).
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        game.deal_damage(source, amount, source=source)

    return effect


def damage_to_controller(amount: int) -> AbilityEffect:
    """ "This artifact/creature/permanent deals N damage to you" (CR 119.3,
    120.2b) - Mana Crypt's own "this artifact deals 3 damage to you", the
    losing half of its own upkeep coin flip.

    "You" (CR 105.3a is a player pronoun, not a search or count question) is
    the ability's own controller - the player who would flip the coin in the
    first place (CR 705.2: "the player that flips the coin").
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        game.deal_damage(game.player(ability.controller), amount, source=source)

    return effect


def damage_each_opponent_spell(amount: int) -> Effect:
    """The spell-side twin of `damage_each_opponent`: "[This spell] deals N
    damage to each opponent" (CR 119.3, CR 102.2), source and controller both
    the spell itself (CR 120.1, CR 120.2b) rather than an `AbilityOnStack` -
    Extended Absence's own second sentence and Dragon's Approach's own
    "Dragon's Approach deals 3 damage to each opponent." are both this same
    shape from a spell rather than a permanent's ability.
    """

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        for opponent in _opponents(game, controller.username):
            game.deal_damage(opponent, amount, source=spell)

    return effect


def damage_each_player(amount: int) -> AbilityEffect:
    """ "[Source] deals N damage to each player." (CR 119.3) - CR 102.1's
    "each player", the caster included, unlike `damage_each_opponent`'s CR
    102.2 subset.
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        for player in game.players_in_game:
            game.deal_damage(player, amount, source=source)

    return effect


def damage_each_player_spell(amount: int) -> Effect:
    """The spell-side twin of `damage_each_player` - Cast Away Doubt's own
    second sentence: "[This spell] deals N damage to each player."
    """

    def effect(game: "Game", spell: CardState) -> None:
        for player in game.players_in_game:
            game.deal_damage(player, amount, source=spell)

    return effect


#: "`<source>` deals N damage to that player." - Gideon the Oathless's own
#: two triggers ("Whenever a creature an opponent controls enters, ..."; the
#: real, off-set printing Fate Unraveler is "Whenever an opponent draws a
#: card, this creature deals 1 damage to that player."). "That player" is
#: CR 400.7 anaphora for whoever the trigger's own condition already named -
#: the entering creature's controller, the card's drawer, the ability's own
#: activator - never a target (CR 115.10a), so this reads the trigger's own
#: `GameEvent` the same way `_parse_untap_trigger_subject_clause` already
#: reads its subject: `event.player` when the event names an acting player
#: directly (loyalty activation, cast, draw), `event.subject_controller`
#: when it only names an object (a permanent entering).
#:
#: "That creature's controller" is the identical CR 400.7 anaphor, spelled
#: as Oracle templates it when the earlier condition named an *object*
#: rather than a player outright - Tetsuko Umezawa, Pursuer's own "Whenever
#: a creature an opponent controls with power or toughness 1 or less
#: blocks, Tetsuko Umezawa deals 1 damage to that creature's controller."
#: Both phrasings resolve through the same `event.player or event.subject_
#: controller` read below; there is no second mechanism here, only a second
#: way the same referent is printed.
#:
#: "Them" is the same anaphor again - Roiling Vortex's "At the beginning of
#: each player's upkeep, this enchantment deals 1 damage to them." (CR 603.2b:
#: the step's own `GameEvent.player` is the active player) - and the amount
#: may be counted for that player instead of printed: Karma's "deals damage
#: to that player equal to the number of Swamps they control", where "they"
#: is that player too, so the count is read off their board, not the
#: controller's.
#: `[^.]*` rather than a bare `.*`: this reader is tried against the *whole*
#: remaining effect text at several call sites (`_ability_effect_or_notice`,
#: `_spell_effect_or_notice`), not a pre-split single clause, and a bare
#: `.*` - greedy but not `DOTALL`, so it still crosses every ". " sentence
#: boundary in a single-line string - swallowed every earlier sentence of a
#: longer paragraph right along with its own subject clause. Vexing
#: Arcanix's whole `{3}, {T}` ability ("Target player chooses a card name,
#: then reveals the top card of their library. If that card has the chosen
#: name, ... Otherwise, they put it into their graveyard and this artifact
#: deals 2 damage to them.") is the reported shape: `_parse_damage_that_
#: player_clause` on its own still matches the whole paragraph and returns a
#: closure that only deals the trailing 2 damage, discarding the naming
#: choice, the reveal, and the hand branch outright - masked in the actual
#: dispatch chain only because `_parse_target_player_name_reveal_branch_
#: clause` is tried first and wins, not because this reader was safe. `[^.]*`
#: still reads every legitimate one-sentence subject clause this reader
#: already handled (Roiling Vortex's "this enchantment", Tetsuko Umezawa's
#: "Tetsuko Umezawa", Karma's identical single-sentence shape) - none of them
#: has an internal period - so nothing that used to match here stops
#: matching; only a match that had to cross a full stop to get there does,
#: and it now correctly fails through to the per-clause split instead.
_DAMAGE_THAT_PLAYER_RE = re.compile(
    rf"^[^.]*\bdeals? (?:(?P<n>{COUNT}) )?damage to "
    r"(?:that player|them|that creature'?s controller)"
    r"(?: equal to (?P<equal>[^.]+))?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s19", for_spell=False)
def _parse_damage_that_player_clause(text: str, *, for_spell: bool) -> AbilityEffect | None:
    """`_DAMAGE_THAT_PLAYER_RE`'s shape; see the banner above."""
    if for_spell:
        return None
    match = _DAMAGE_THAT_PLAYER_RE.fullmatch(text.strip())
    if match is None or (match.group("n") is None) == (match.group("equal") is None):
        return None
    if match.group("n") is not None:
        fixed = parse_count(match.group("n"))
        if fixed is None:
            return None

        def amount_for(game: "Game", username: str, fixed: int = fixed) -> int:
            return fixed

    else:
        expression = match.group("equal").strip()
        if _YOU_OR_YOUR_RE.search(expression):
            return None  # names the controller, not that player - fail closed
        counted = count_expression(_THEY_CONTROL_RE.sub("you control", expression))
        if counted is None:
            return None
        amount_for = counted

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None:
            return
        username = event.player or event.subject_controller
        if username is None:
            return
        amount = amount_for(game, username)  # CR 608.2h: read as it resolves
        if amount <= 0:
            return
        game.deal_damage(game.player(username), amount, source=ability.source_or_last_known(game))

    return effect


#: "<it/this creature> deals that much damage to <target phrase>.[ If a
#: player is dealt damage this way, <consequence>.]" - Boros Reckoner's and
#: Spitemare's "Whenever this creature is dealt damage, it deals that much
#: damage to any target.", and Screaming Nemesis's "... to any other target.
#: If a player is dealt damage this way, they can't gain life for the rest of
#: the game." "That much" points back at the triggering event's own amount
#: (`that_many`) - for a damage event, the damage actually dealt once
#: prevention has applied (CR 615.6: prevented damage never happens). The
#: prefix cannot cross a period, so an earlier instruction's own "that much"
#: (Divine Deflection's prevented amount) is never read as this one's; the
#: phrase is `_read_phrase`'s, which reads CR 115.4's "any other target" as
#: excluding the source.
_DAMAGE_THAT_MUCH_RE = re.compile(
    r"^(?:[^.\"“”'‘’]|(?<=\w)['’](?=\w))*?\bdeals? that much damage to "
    r"(?P<phrase>any (?:other )?target|[^.]*?\btargets?\b[^.]*?)\."
    r"(?:\s*if a player is dealt damage this way,\s*(?P<rider>[^.]+?)\.?)?$",
    re.IGNORECASE,
)

#: A target phrase narrowed by the triggering event's own player ("that
#: player controls", "they control") rather than by the ability's controller.
_EVENT_RELATIVE_TARGET_RE = re.compile(
    r"\bthat (?:player|opponent)\b|\bthey\b|\btheir\b", re.IGNORECASE
)

#: "they can't gain life for the rest of the game" - the player half of
#: `_DAMAGE_THAT_MUCH_RE`'s rider: CR 119.7's prohibition with CR 611.2a's
#: stated duration, recorded as `Player.cannot_gain_life` on each player the
#: damage actually reached.
_CANT_GAIN_LIFE_REST_OF_GAME_RE = re.compile(
    r"^(?:they|that player) can(?:'|’|no)?t gain life for the rest of the game$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s19", for_spell=False)
def _parse_damage_that_much_clause(text: str, *, for_spell: bool) -> AbilityEffect | None:
    """`_DAMAGE_THAT_MUCH_RE`'s shape; see the banner above.

    Ability-only: "that much" points back at a triggering event, which a
    spell never has. The amount is read when the ability resolves, and a
    trigger with no event amount to read fails closed with a notice
    (`_that_many_or_notice`) rather than dealing a guessed number. The
    source deals the damage as it last existed (CR 608.2h), so the ability
    still resolves after the damage that triggered it killed the creature.
    "If a player is dealt damage this way" is read off what `Game.deal_damage`
    reports actually landed, so a player whose damage was all prevented is
    not dealt damage this way.
    """
    if for_spell:
        return None
    match = _DAMAGE_THAT_MUCH_RE.fullmatch(text.strip())
    if match is None:
        return None
    phrase = match.group("phrase")
    if _EVENT_RELATIVE_TARGET_RE.search(phrase) is not None:
        # Questing Beast's "target planeswalker that player controls" is
        # restricted by the triggering event, which the target reader cannot
        # express - it would offer every planeswalker, so it stays unread.
        return None
    if not _targets_understood(phrase, allow_player_targets=True):
        return None
    rider = match.group("rider")
    if rider is not None and _CANT_GAIN_LIFE_REST_OF_GAME_RE.fullmatch(rider.strip()) is None:
        return None
    locks_life_gain = rider is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        amount = _that_many_or_notice(
            game,
            text,
            source_id=ability.source_id,
            source_name=ability.name,
            stack_object=ability,
        )
        if amount is None or amount <= 0:
            return
        source = ability.source_or_last_known(game)
        for target in game.resolve_targets(ability):
            dealt = game.deal_damage(target, amount, source=source)
            if locks_life_gain and isinstance(target, Player) and dealt > 0:
                target.cannot_gain_life = True

    return effect


def damage_each_creature(amount: int) -> AbilityEffect:
    """Extinguisher Battleship: "this Spacecraft deals 4 damage to each
    creature" (CR 119.3) - CR 102.2 has nothing to say here, since "each
    creature" names every creature on the battlefield, not a player group.

    Read off the *computed* board (CR 613.5): a noncreature permanent that
    became a creature only through a continuous effect still takes the
    damage, and one that stopped being a creature does not - the same
    correction `count_expression`'s "you control" reading already applies.
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        board = game.computed_board()
        for creature in list(game.battlefield):
            if Type.CREATURE in board.of(creature).types:
                game.deal_damage(creature, amount, source=source)

    return effect


def damage_each_creature_spell(amount: int) -> Effect:
    """The spell-side twin of `damage_each_creature`: "[This spell] deals N
    damage to each creature" (CR 119.3), source is the spell itself (CR
    120.1, CR 120.2b) rather than an `AbilityOnStack` - Fire Magic's Tiered
    modes are the first pool printing to reach this shape from a spell.
    """

    def effect(game: "Game", spell: CardState) -> None:
        board = game.computed_board()
        for creature in list(game.battlefield):
            if Type.CREATURE in board.of(creature).types:
                game.deal_damage(creature, amount, source=spell)

    return effect


def damage_the_attacked_player(amount: int) -> AbilityEffect:
    """Hellrider: "deals 1 damage to the player or planeswalker it's attacking".

    "It" is the creature that attacked, so the damage follows the *triggering*
    creature's defender rather than the source's - which is the whole point of
    Hellrider triggering once per attacker.

    Whichever kind of defender that is: the printed text says "the player or
    planeswalker it's attacking", and `Game.deal_damage` now knows what damage
    to a planeswalker does (CR 120.3c - that many loyalty counters removed).
    This used to return without dealing anything for a planeswalker defender,
    on the grounds that loyalty counters were not modelled, which silently
    dropped half the card.
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.defender is None:
            return
        target = game.resolve_target(event.defender)
        if target is not None:
            game.deal_damage(target, amount, source=ability.source_or_last_known(game))

    return effect


def damage_the_other_combatant(amount: int) -> AbilityEffect:
    """Ashmouth Hound: "deals 1 damage to that creature".

    "That creature" is the other half of the blocking pair: the attacker when the
    source blocked, the blocker when the source became blocked (CR 509.1a).
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None:
            return
        other_id = event.related_id if event.subject_id == ability.source_id else event.subject_id
        other = game.find_by_id(other_id) if other_id is not None else None
        if other is not None and other.zone is Zone.BATTLEFIELD:
            game.deal_damage(other, amount, source=ability.source_or_last_known(game))

    return effect


def damage_ability_targets(amount: int) -> AbilityEffect:
    """An activated or triggered ability that deals damage to what it targets.

    Goblin Bombardment's "This enchantment deals 1 damage to any target". The
    source is the permanent, and CR 120.7 says "the source of damage is the
    object that dealt it" - which matters for lifelink and for protection, both
    of which `Game.deal_damage` reads off the source. The sacrifice is part of
    the *cost* (CR 602.1a), paid before the ability is ever put on the stack, so
    nothing about it belongs in the resolution.

    Damage does not destroy anything by itself (CR 120.5): a creature dies to
    the state-based action that follows.
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        for target in game.resolve_targets(ability):
            game.deal_damage(target, amount, source=source)

    return effect


def damage_ability_targets_equal_to_expression(reader: "AmountReader") -> AbilityEffect:
    """An activated or triggered ability dealing damage "equal to `<expr>`" -
    Honden of Infinite Rage's "deals damage to any target equal to the number
    of Shrines you control", Ben-Ben, Akki Hermit's "... equal to the number of
    untapped Mountains you control". The ability-side twin of
    `deal_damage_equal_to_expression`: `reader` is `amount_expression`'s
    general reader, evaluated once as the ability resolves (CR 608.2h), for the
    ability's controller, with the source as "it"/"this `<noun>`" and the
    ability's own announced X. The source deals the damage, as in
    `damage_ability_targets` (CR 120.7).
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        amount = max(reader(game, ability.controller, source, ability.x_value), 0)
        for target in game.resolve_targets(ability):
            game.deal_damage(target, amount, source=source)

    return effect


def _self_deals_damage_equal_to_its_stat(stat: str) -> AbilityEffect:
    """`_SELF_DEALS_DAMAGE_EQUAL_TO_ITS_STAT_RE`'s effect: the source deals
    damage equal to its power (or toughness) to each target still legal (CR
    608.2b), the amount read once as the damage is dealt (CR 608.2h).

    A source still on the battlefield is read through the layer system (CR
    613.5, `Game.power_of`); one that has left it is read off its last known
    information (CR 608.2h, CR 113.7a), which `CardState.power`/`.toughness`
    already fall back to once the object is off the battlefield - the same
    read `triggers.event_subject_power` makes for a dying creature. A negative
    value deals no damage (CR 107.1b).
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        if source is None:
            return
        if source.zone is Zone.BATTLEFIELD:
            value = game.power_of(source) if stat == "power" else game.toughness_of(source)
        else:
            value = source.power if stat == "power" else source.toughness
        amount = max(value or 0, 0)
        for target in game.resolve_targets(ability):
            game.deal_damage(target, amount, source=source)

    return effect


#: "It deals 3 damage to each other creature and each opponent." (Avacyn, the
#: Purifier's own transform trigger): CR 120.1's non-targeted damage to every
#: permanent of one card type but the source itself, and to each opponent.
#: Widened (C02-T5) to "each creature" with no "other" (The Elder Dragon War's
#: chapter I), a "non-`<Subtype>`" exclusion (Avengers: Under Siege's "each
#: non-Villain creature and each opponent", CR 205.3) and "each player".
_DAMAGE_EACH_OTHER_TYPE_AND_EACH_OPPONENT_RE = re.compile(
    rf"^(?:it|this [a-z]+) deals {count_pattern('n', article=False)} damage to each "
    r"(?P<other>other )?(?:non-?(?P<excluded>(?-i:[A-Z][A-Za-z]+)) )?"
    r"(?P<type>[a-z]+) and each (?P<who>opponent|player)\.?$",
    re.IGNORECASE,
)


def _parse_damage_each_other_type_and_each_opponent_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_DAMAGE_EACH_OTHER_TYPE_AND_EACH_OPPONENT_RE`'s shape. The source
    deals the damage (CR 120.2b) - its last known information if it has
    gone (CR 113.7a) - to every permanent of the named type on the computed
    board (CR 613.5) other than itself, then to each opponent of the
    resolving object's controller (CR 102.2)."""
    match = _DAMAGE_EACH_OTHER_TYPE_AND_EACH_OPPONENT_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"), article=False)
    card_type = _singular_card_type(match.group("type"))
    excluded = match.group("excluded")
    if excluded is not None and canonical_subtype(excluded) is None:
        return None
    if amount is None or card_type is None:
        return None
    other_only = match.group("other") is not None
    every_player = match.group("who").lower() == "player"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object
            if isinstance(stack_object, CardState)
            else stack_object.source_or_last_known(game)
        )
        source_id = None if source is None else source.id
        controller = game.controller_of(stack_object).username
        board = game.computed_board()
        for permanent in list(game.battlefield):
            chars = board.of(permanent)
            if other_only and permanent.id == source_id:
                continue
            if card_type not in chars.types:
                continue
            if excluded is not None and any(
                subtype.lower() == excluded.lower() for subtype in chars.subtypes
            ):
                continue
            game.deal_damage(permanent, amount, source=source)
        players = game.players_in_game if every_player else _opponents(game, controller)
        for player in players:
            game.deal_damage(player, amount, source=source)

    return effect


def _damage_ability_targets_equal_to(
    count: Callable[["Game", str, str | None], int],
) -> AbilityEffect:
    """An ability dealing damage "equal to" a count taken off its own source
    to each target it still has (CR 120.3, CR 608.2h: the count is taken once,
    as the ability resolves). The source is the permanent (CR 120.7), as in
    `damage_ability_targets`."""

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        amount = max(count(game, ability.controller, source_id_of(ability)), 0)
        for target in game.resolve_targets(ability):
            game.deal_damage(target, amount, source=source)

    return effect


#: "card type(s) among [`<qualifier>`] spells you've cast this turn" - April
#: O'Neil, Hacktivist's "draw a card for each card type among spells you've
#: cast this turn" and Hurkyl, Master Wizard's "For each card type among
#: noncreature spells you've cast this turn, ...". CR 205.2a's card types of
#: every spell the player cast this turn (`Game.spells_cast_this_turn`, CR
#: 601.2i), each counted once however many spells share it; CR 205.2b gives
#: an artifact creature both.
_CARD_TYPES_AMONG_SPELLS_CAST_RE = re.compile(
    r"^card types? among (?:(?P<qualifier>[a-z-]+) )?spells you've cast this turn$",
    re.IGNORECASE,
)


def card_types_among_spells_cast_reader(
    phrase: str,
) -> Callable[["Game", str], set[Type]] | None:
    """`_CARD_TYPES_AMONG_SPELLS_CAST_RE`'s set of card types, as a
    `(game, player) -> set[Type]` reader, or None for a phrase it does not
    read. The qualifier is one card type, or "non" one ("noncreature"): a
    spell that fails it adds none of its types, so an artifact creature
    spell contributes nothing to Hurkyl's "noncreature spells"."""
    from ..casting import types_being_cast

    match = _CARD_TYPES_AMONG_SPELLS_CAST_RE.fullmatch(phrase.strip().rstrip("."))
    if match is None:
        return None
    qualifier = (match.group("qualifier") or "").lower()
    negated = qualifier.startswith("non")
    word = qualifier.removeprefix("non").lstrip("-")
    wanted: Type | None = None
    if word:
        try:
            wanted = Type(word)
        except ValueError:
            return None

    def read(game: "Game", player: str) -> set[Type]:
        found: set[Type] = set()
        for spell in game.spells_cast_this_turn.get(player, []):
            types = set(spell.types_as_a_spell(types_being_cast(spell.card, spell.face_played)))
            if wanted is not None and (wanted in types) is negated:
                continue
            found |= types
        return found

    return read


#: Polukranos, World Eater's own "becomes monstrous" trigger: CR 601.2d's
#: ordinary divided damage, immediately followed by CR 701.14a's own "deals
#: damage equal to its power" retaliation from every creature the division
#: actually reached - one CR 608.2c instruction across two sentences
#: ("those creatures" is CR 400.7's anaphora back to the first sentence's own
#: resolved targets), read the same "whole, unsplit text" way
#: `_parse_x_damage_divided_and_doubled_clause` already reads Shatterskull
#: Smashing's own two-sentence divided-damage shape. `phrase` is read the
#: same general way `_DIVIDED_DAMAGE_RE` reads its own target-list phrase -
#: `_targets_understood` vets it, not a literal string - so a differently
#: restricted printing of the identical mechanic ("... creatures an opponent
#: controls", "... creatures you don't control") reads exactly the same way,
#: not just the reported card's own "your opponents control". Matched
#: against `_self_normalized_effect_text`'s own "this permanent" rewrite of
#: the card's printed name (CR 700.7), the same normalisation `trigger_
#: effect_for`'s own fallback already tries once the raw, still-self-named
#: text fails every other reader.
_DIVIDED_DAMAGE_THEN_RETALIATE_RE = re.compile(
    r"^(?:it|this (?:creature|permanent)) deals (?P<n>\d+|x) damage divided as you choose "
    r"among (?P<phrase>.+?)\.\s*"
    r"each of those creatures deals damage equal to its power to "
    r"(?:it|this (?:creature|permanent))\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _deal_divided_damage_then_retaliate_shares(
    game: "Game", ability: "AbilityOnStack", total: int
) -> None:
    """Pay out `total` damage divided among `ability.targets` (CR 601.2d, CR
    608.2b), then have every creature that division actually reached deal
    damage back to the source equal to its own power (CR 701.14a) -
    `_DIVIDED_DAMAGE_THEN_RETALIATE_RE`'s own resolution half.

    Simultaneous with itself the way `_fight` already is: no zone recheck
    between the two payouts, since state-based actions are not performed
    until the whole ability has finished resolving (CR 704.3) - a creature
    the first payout reduces to lethal damage still deals its own retaliation
    damage back before anything checks whether it should already be dead.
    "Those creatures" is only the creatures the division actually reached -
    a target CR 608.2b removed before the first payout was never dealt
    damage and never retaliates either, the same restriction a `None` from
    `game.legal_target` already enforces for the first half.
    """
    chosen = len(ability.targets)
    if chosen == 0 or total <= 0:
        return
    source = ability.source_or_last_known(game)
    shares = _divided_damage_shares(total, chosen, ability.division)
    retaliators: list[CardState] = []
    for reference, share in zip(ability.targets, shares, strict=True):
        target = game.legal_target(ability, reference)
        if target is not None and share > 0:
            game.deal_damage(target, share, source=source)
            retaliators.append(target)
    if source is None:
        return
    for creature in retaliators:
        power = game.power_of(creature) or 0
        if power > 0:
            game.deal_damage(source, power, source=creature)


@ABILITY_TEXT.rung("s14")
def _parse_divided_damage_then_retaliate_clause(text: str) -> AbilityEffect | None:
    """`_DIVIDED_DAMAGE_THEN_RETALIATE_RE`'s shape, or `None`."""
    match = _DIVIDED_DAMAGE_THEN_RETALIATE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    n = match.group("n")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if n.lower() == "x":
            total = ability.event.amount if ability.event is not None else None
            if total is None:
                total = ability.x_value
        else:
            total = int(n)
        if total is None or total <= 0:
            return
        _deal_divided_damage_then_retaliate_shares(game, ability, total)

    return effect


#: "you lose that much life. Then if your life total is less than or equal
#: to half your starting life total, untap this permanent and transform it."
#: - Cecil, Dark Knight's own "Darkness" ability-word trigger ("Whenever
#: Cecil deals damage, ..."; the ability word is already gone and the card's
#: own name already normalized to "this permanent" by the time this reads
#: it - see `trigger_effect_for`'s own fallback). "That much" is the damage
#: `TriggerEvent.DEALS_DAMAGE` carries as `GameEvent.amount` (CR 120.1); the
#: comparison is the resolving player's current life against half their own
#: `Player.starting_life` (CR 103.4/119.1), computed fresh after the loss so
#: the loss itself can cross the threshold; the transform is CR 701.27a's
#: ordinary self one, refused once the source has already left (CR 113.7a).
_DEALS_DAMAGE_LOSE_LIFE_THEN_TRANSFORM_IF_LOW_RE = re.compile(
    r"^you lose that much life\.\s*then if your life total is less than or equal to half your "
    r"starting life total, untap this (?:permanent|creature) and transform it\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s28")
def _parse_deals_damage_lose_life_then_transform_if_low_clause(text: str) -> AbilityEffect | None:
    """`_DEALS_DAMAGE_LOSE_LIFE_THEN_TRANSFORM_IF_LOW_RE`'s shape."""
    if _DEALS_DAMAGE_LOSE_LIFE_THEN_TRANSFORM_IF_LOW_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        amount = event.amount if event is not None else None
        if amount is None or amount <= 0:
            return
        player = game.controller_of(ability)
        game.lose_life(player, amount)
        if player.life > player.starting_life / 2:
            return
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            source.untap()
            source.transform()

    return effect


def _damage_recipient_is_its_subject(ability: AbilityOnStack) -> bool:
    """Whether a triggered ability's condition is the passive "`<X>` is dealt
    damage" (CR 120.1's recipient), so the bare "it" its effect then names is
    the creature that was dealt the damage (`GameEvent.target_id`), not the
    source of the damage (`GameEvent.subject_id`) - Rite of Passage's "Whenever
    a creature you control is dealt damage, put a +1/+1 counter on it."."""
    event = ability.event
    printed = ability.ability
    if event is None or event.target_id is None or not isinstance(printed, TriggeredAbility):
        return False
    return re.search(r"\b(?:is|are) dealt\b", (printed.condition or "").lower()) is not None


#: Burst Lightning: "<Source> deals N damage to any target. If this spell was
#: kicked, it deals M damage instead." CR 702.33a/d's kicker, read at
#: resolution off `Game.cast_record(spell).kicked` the same way
#: `_parse_x_life_mass_debuff` already reads its own additional-cost X - two
#: sentences read whole (ahead of `parse_mixed_effect_for_spell`, which would
#: otherwise split the second one off and find no clause shape for it,
#: refusing the *first* sentence's plain damage along with it).
_DAMAGE_TARGET_KICKED_INSTEAD_RE = re.compile(
    r"^.*\bdeals? (?P<n>\d+) damage to (?P<phrase>any target|.*target.+?)\.\s*"
    r"if this spell was kicked, it deals (?P<kicked_n>\d+) damage instead\.?$",
    re.IGNORECASE | re.DOTALL,
)


#: "`<source>` deals N damage to target creature. If `<condition>`, it also
#: deals M damage to that creature's controller." - Repulsor Blast's own
#: teamwork rider (`machines/teamwork.py`). Not `_CONDITION_INSTEAD_RE`'s
#: shape: "also" is CR 608.2c's additive reading (the rider adds to the base
#: instruction rather than replacing it, the same "also" `_RIDER_ALSO_RE`
#: strips for `_parse_conditional_referent_clause`), and the rider's own
#: object - "that creature's **controller**" - is a player derived from the
#: base clause's own already-resolved target, not the target itself, which
#: `_parse_referent_object_clause`'s "referent" shapes do not read. Read by
#: `condition_is_readable`/`Game.condition_holds` generically, the same as
#: every other printed condition, not pinned to "cast using teamwork".
#: The rider's subject is the spell itself however it is printed: "it", "this
#: spell", or the same name the first sentence's subject used (Blooming
#: Blast's "If the gift was promised, Blooming Blast also deals 3 damage to
#: that creature's controller.", Misthios's Fury's "If you control an
#: Equipment, Misthios's Fury also deals 2 damage ..."; CR 201.5, a card
#: naming itself means that object).
#: The same instruction printed unconditionally, in one sentence: "`<source>`
#: deals N damage to target creature and M damage to that creature's
#: controller." (Chandra, Flame's Fury's -2) - the rider's player is read off
#: the same resolved target the same way, just with no condition gating it.
#: The target noun may be any permanent type the anaphor repeats ("that
#: permanent's controller").
_DAMAGE_TARGET_ALSO_DAMAGES_CONTROLLER_RE = re.compile(
    rf"^(?P<subject>[^.]*?) deals? (?P<n>{COUNT}) damage to "
    r"(?P<phrase>[^.]*?target (?P<noun>creature|permanent|planeswalker|artifact|enchantment|land)"
    r"[^.]*?)"
    r"(?:\.\s*if (?P<condition>[^,]+), (?:it|this spell|(?P=subject)) also deals"
    r"|\.\s*(?:it|this spell|(?P=subject)) also deals|\s+and) "
    rf"{count_pattern('extra_n', x=True)} damage to that "
    r"(?:creature|permanent|planeswalker|artifact|enchantment|land|battle)'?s controller"
    rf"(?: if (?P<post_condition>[^.,]+?))?{where_x_pattern()}\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s42")
@SPELL_TEXT.rung("s18", after=["merges._parse_damage_then_followup_spell"])
def _parse_damage_target_also_damages_controller_clause(effect_text: str) -> Any:
    """`_DAMAGE_TARGET_ALSO_DAMAGES_CONTROLLER_RE`'s shape, on a spell or an
    activated or triggered ability, whose damage source is the ability's
    source or its last known information (CR 608.2h).

    CR 608.2b: the target is the only one, so with it illegal nothing - not
    even the controller's share - happens."""

    whole = _strip_non_effect_preamble(effect_text).strip()
    match = _DAMAGE_TARGET_ALSO_DAMAGES_CONTROLLER_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    condition_text = (
        match.group("condition") or match.group("post_condition") or ""
    ).strip() or None
    if condition_text is not None and not _effect_condition_is_readable(condition_text):
        return None
    base_amount = parse_count(match.group("n"))
    extra_reader = _fixed_or_where_x_amount(match.group("extra_n"), match.group("where_x"))
    if base_amount is None or extra_reader is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source: CardState | None
        if isinstance(stack_object, AbilityOnStack):
            source = stack_object.source_or_last_known(game)
            condition_source = stack_object.source(game)
            source_id, source_name = stack_object.source_id, stack_object.source_name
        else:
            source = condition_source = stack_object
            source_id, source_name = stack_object.id, stack_object.card.name
        held: bool | None = True
        if condition_text is not None:
            controller = game.controller_of(stack_object).username
            held = game.condition_holds(controller, condition_text, condition_source)
            if held is None:
                notice = ConditionalClauseNotice(
                    source_id=source_id, source_name=source_name, text=whole
                )
                if notice not in game.conditional_clause_notices:
                    game.conditional_clause_notices.append(notice)
                held = False
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState):
                continue
            # CR 608.2h: "that creature's controller" is read from last
            # known information if the base damage already killed it, so
            # the controller is captured before the base damage - not
            # re-derived, and never re-gated on the target's zone - after.
            controller_of_target = game.controller_of(target)
            game.deal_damage(target, base_amount, source=source)
            if held:
                extra_amount = max(
                    extra_reader(
                        game,
                        game.controller_of(stack_object).username,
                        source,
                        stack_object.x_value if isinstance(stack_object, AbilityOnStack) else 0,
                    ),
                    0,
                )
                game.deal_damage(
                    game.player(controller_of_target.username), extra_amount, source=source
                )

    return effect


@SPELL_TEXT.rung("s18", after=["merges._parse_damage_then_followup_spell"])
def _parse_damage_target_and_each_other_group_text(effect_text: str) -> Effect | None:
    """ "`<src>` deals N damage to target creature and each other creature
    with the same name as that creature." on a spell (Homing Lightning) - the
    group is read off the one target as the spell resolves (CR 608.2b: with
    the target illegal nothing happens), by `damage_backrefs`' shared reader
    that Izzet Staticaster's ability also uses."""
    if " and each other creature " not in effect_text:
        return None
    from ..damage_backrefs import damage_backref_spell_effect

    return damage_backref_spell_effect(effect_text)


@SPELL_TEXT.rung("s18")
def _parse_damage_target_kicked_instead_clause(effect_text: str) -> Effect | None:
    """`_DAMAGE_TARGET_KICKED_INSTEAD_RE`'s shape, or `None` if this is not it."""
    whole = _strip_non_effect_preamble(effect_text).strip()
    match = _DAMAGE_TARGET_KICKED_INSTEAD_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), allow_player_targets=True):
        return None
    base = int(match.group("n"))
    kicked_amount = int(match.group("kicked_n"))

    def effect(game: "Game", spell: CardState) -> None:
        record = game.cast_record(spell)
        amount = kicked_amount if record.kicked > 0 else base
        for target in game.resolve_targets(spell):
            game.deal_damage(target, amount, source=spell)

    return effect


def _lethal_amount_before_damage(game: "Game", target: CardState) -> int | None:
    """CR 120.10's per-type threshold for `target`, read *before* the damage
    that will be checked against it: a creature's remaining toughness (its
    toughness minus damage already marked), a planeswalker's loyalty. `None`
    for a permanent that is neither - CR 120.10 defines excess damage only
    for a creature, a planeswalker, or a battle (the third not modelled; see
    `docs/engine-coverage.md`) - and, per its closing sentence, "the greatest
    of the calculated amounts for each of the card types it has" when a
    permanent is more than one of them at once.
    """
    board = game.computed_board()
    chars = board.of(target)
    amounts: list[int] = []
    if Type.CREATURE in chars.types:
        amounts.append(max(chars.numeric_toughness - target.damage, 0))
    if Type.PLANESWALKER in chars.types:
        amounts.append(target.counter_count(Counter.LOYALTY))
    return max(amounts) if amounts else None


#: Violent Echoes: "<Source> deals N damage to target creature or
#: planeswalker. If excess damage was dealt to that permanent this way,
#: empower Jace X, where X is that excess damage." Read whole, the same
#: reason `_DAMAGE_TARGET_KICKED_INSTEAD_RE` just above is: the second
#: sentence refers back to how much the first one actually dealt
#: (CR 120.10), which `_parse_mixed_clauses`'s per-clause dispatch has no way
#: to carry from one clause to the next on its own.
_DAMAGE_THEN_EMPOWER_IF_EXCESS_RE = re.compile(
    r"^.*\bdeals? (?P<n>\d+) damage to (?P<phrase>any target|.*?target.+?)\.\s*"
    r"if excess damage was dealt to that permanent this way,\s*"
    r"empower jace [xX],\s*where\s+[xX]\s+is that excess damage\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s18")
def _parse_damage_then_empower_if_excess_clause(effect_text: str) -> Effect | None:
    """`_DAMAGE_THEN_EMPOWER_IF_EXCESS_RE`'s shape, or `None` if this is not
    it.

    `target`'s pre-damage threshold (`_lethal_amount_before_damage`) has to
    be read *before* `Game.deal_damage` runs, since that call is what marks
    the damage or removes the loyalty counters CR 120.10 measures against.
    `deal_damage`'s own return is the amount actually dealt - CR 609.7b's
    prevention and replacement effects already applied - which is what CR
    120.10's excess is measured against, not the printed N.
    """
    whole = _strip_non_effect_preamble(effect_text).strip()
    match = _DAMAGE_THEN_EMPOWER_IF_EXCESS_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    amount = int(match.group("n"))

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell).username
        for target in game.resolve_targets(spell):
            if not isinstance(target, CardState):
                continue
            pre_lethal = _lethal_amount_before_damage(game, target)
            dealt = game.deal_damage(target, amount, source=spell)
            if pre_lethal is None:
                continue
            excess = dealt - pre_lethal
            if excess > 0:
                empower_jace(game, excess, controller, spell.id, spell.name)

    return effect


def _parse_divided_damage_among_target_players_creatures_clause(clause: str) -> Effect | None:
    """`_DIVIDED_DAMAGE_AMONG_TARGET_PLAYERS_CREATURES_RE`'s shape.

    The recipients are read off the computed board (CR 613.5) at resolution,
    the same "fixed set now" convention `_parse_all_of_target_player_then_
    referent_pair` already uses for Settle the Wreckage's identical
    "all ... target player controls" grammar - `permanent_description`
    reused rather than a bare `.is_creature` check so an animated land
    counts here exactly the way it already does there.
    """
    match = _DIVIDED_DAMAGE_AMONG_TARGET_PLAYERS_CREATURES_RE.fullmatch(clause)
    if match is None:
        return None
    if not _targets_understood(f"target {match.group('whose')}", allow_player_targets=True):
        return None
    requirement = permanent_description("creatures")
    if requirement is None:
        return None
    where_x = match.group("where_x")
    n = match.group("n")
    even_split = match.group("evenly") is not None
    multiplier = count_expression(where_x) if where_x is not None else None
    if where_x is not None and multiplier is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        players = [target for target in game.resolve_targets(spell) if isinstance(target, Player)]
        if not players:
            return
        player = players[0]
        creatures = [
            permanent
            for permanent in game.permanents_controlled_by(player.username)
            if requirement.rejects(permanent, player.username, game) is None
        ]
        if not creatures:
            return
        if n.lower() == "x":
            total = (
                multiplier(game, game.controller_of(spell).username)
                if multiplier is not None
                else game.cast_record(spell).x_value
            )
        else:
            total = parse_count(n) or 0
        if total <= 0:
            return
        shares = _divided_damage_shares(total, len(creatures), None, even_split=even_split)
        for creature, share in zip(creatures, shares, strict=True):
            if share > 0:
                game.deal_damage(creature, share, source=spell)

    return effect


#: "`<this>` deals damage equal to that spell's mana value to any target." -
#: Thor, God of Thunder's own cast trigger. "That spell" is CR 400.7/607.1
#: anaphora back to the spell this ability's own `TriggerEvent.CAST_SPELL`
#: watched (`event.subject_card`), the identical "that spell" reading
#: `_TARGET_OPPONENT_DRAW_THEN_COPY_THAT_SPELL_RE` already gives elsewhere -
#: a magnitude, not `amount_expression`'s own vocabulary (which has no term
#: for a specific anaphoric object's mana value).
_DAMAGE_EQUAL_TO_THAT_SPELLS_MV_RE = re.compile(
    r"^(?:it |this [a-z]+ )deals damage equal to that spell'?s mana value to "
    r"(?P<phrase>any (?:other )?target|[^.]*?\btargets?\b[^.]*?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s10", for_spell=FORWARD)
def _parse_damage_equal_to_that_spells_mv_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_DAMAGE_EQUAL_TO_THAT_SPELLS_MV_RE`'s shape, or `None`.

    Ability-only: `GameEvent.subject_card` is a triggered ability's own
    event attribute.
    """
    if for_spell:
        return None
    match = _DAMAGE_EQUAL_TO_THAT_SPELLS_MV_RE.fullmatch(text.strip())
    if match is None:
        return None
    phrase = match.group("phrase")
    if not _targets_understood(phrase, allow_player_targets=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object) or stack_object.event is None:
            return
        ability = stack_object
        card = ability.event.subject_card
        if card is None:
            return
        amount = int(card.cmc)
        if amount <= 0:
            return
        source = ability.source_or_last_known(game)
        for target in game.resolve_targets(ability):
            game.deal_damage(target, amount, source=source)

    return effect


def _deal_damage_for_each(
    amount_fn: Callable[["Game", str], int], *, for_spell: bool
) -> TargetedClause:
    """`deal_damage`/`damage_ability_targets`'s twin for a multiplied amount -
    the base times the "for each"/X reader is computed once, then dealt to
    every target the same way the fixed-amount builders already do.
    """

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        amount = amount_fn(game, controller.username)
        source = stack_object if for_spell else stack_object.source_or_last_known(game)  # type: ignore[union-attr]
        for target in game.resolve_targets(stack_object):
            game.deal_damage(target, amount, source=source)

    return effect


def _deal_divided_damage_for_expression(
    multiplier: Callable[["Game", str], int], *, even_split: bool = False
) -> Effect:
    """`deal_divided_damage`'s twin for a "where X is <expr>" total - Ureni's
    "X damage divided as you choose ..., where X is the number of lands you
    control" and Rolling Thunder's identical shape. `_deal_divided_damage_
    shares` still does the actual payout, exactly as it does for a fixed
    total: only how the total itself is read differs.
    """

    def effect(game: "Game", spell: "StackObject") -> None:
        controller = game.controller_of(spell)
        total = multiplier(game, controller.username)
        _deal_divided_damage_shares(game, spell, total, even_split=even_split)

    return effect


def _deal_x_divided_damage(*, even_split: bool = False) -> Effect:
    """`deal_divided_damage`'s twin for CR 107.3's plain X - no "where X is
    <expr>" definition anywhere in the sentence, so X is the caster's own
    announced {X} in the mana cost (CR 601.2b), read the same way
    `_parse_x_damage_divided_and_doubled_clause` already reads Shatterskull
    Smashing's X rather than through `where_x_pattern`'s expression group,
    which stays empty for this shape.
    """

    def effect(game: "Game", spell: CardState) -> None:
        x_value = game.cast_record(spell).x_value
        _deal_divided_damage_shares(game, spell, x_value, even_split=even_split)

    return effect


def _damage_each_opponent_for_expression(
    amount_fn: Callable[["Game", str], int],
) -> AbilityEffect:
    """`damage_each_opponent`'s twin for a "where X is <expr>" amount."""

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        amount = amount_fn(game, ability.controller)
        for opponent in _opponents(game, ability.controller):
            game.deal_damage(opponent, amount, source=source)

    return effect


def _damage_each_creature_for_expression(
    amount_fn: Callable[["Game", str], int], *, for_spell: bool
) -> TargetedClause:
    """`damage_each_creature`/`damage_each_creature_spell`'s twin for a
    "where X is <expr>" amount."""

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        amount = amount_fn(game, controller.username)
        source = stack_object if for_spell else stack_object.source_or_last_known(game)  # type: ignore[union-attr]
        board = game.computed_board()
        for creature in list(game.battlefield):
            if Type.CREATURE in board.of(creature).types:
                game.deal_damage(creature, amount, source=source)

    return effect


#: "Prevent all damage that would be dealt by up to one target creature for
#: as long as this Saga remains on the battlefield." (Old Fat Spider Can't
#: See Me's chapter II) and "Prevent all combat damage that would be dealt by
#: target attacking or blocking creature this turn[. If {R} was spent to cast
#: this spell, <this spell> deals damage to that creature's controller equal
#: to the creature's power.]" (Boros Fury-Shield). CR 615.1a: a prevention
#: effect, stored as a shield (CR 615.4) keyed to the one object targeted -
#: its id *and* its zone-change stamp, since that creature leaving and coming
#: back is a new object (CR 400.7). The duration is CR 514.2's "this turn" or
#: CR 611.2b's "for as long as" the resolving ability's own source remains.
#: Gideon of the Trials' "+1: Until your next turn, prevent all damage target
#: permanent would deal." is the same shield in the other word order, with
#: CR 611.2a's leading "until your next turn" (`until_next_turn_of`).
_PREVENT_DAMAGE_DEALT_BY_TARGET_RE = re.compile(
    r"^(?P<next_turn>until your next turn, )?prevent all (?P<combat>combat )?damage "
    r"(?:that would be dealt by (?P<phrase>(?:up to one )?target [a-z ]*?(?:creature|permanent))"
    r"|(?P<subject>(?:up to one |one or two )?target [a-z ]*?(?:creatures?|permanents?))"
    r" would deal)"
    r"(?: (?P<this_turn>this turn)| for as long as (?P<remains>this (?:saga|creature|enchantment|"
    r"artifact|permanent|land)) remains on the battlefield)?\."
    r"(?:\s*if \{(?P<color>[wubrg])\} was spent to cast this spell, (?:this spell|[^,.]+?) "
    r"deals damage to that creature['’]s controller equal to the creature['’]s power\.)?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s8")
@SPELL_TEXT.rung("s8")
def _parse_prevent_damage_dealt_by_target_clause(text: str) -> TargetedClause | None:
    """`_PREVENT_DAMAGE_DEALT_BY_TARGET_RE`'s shape, on a spell or an ability."""
    match = _PREVENT_DAMAGE_DEALT_BY_TARGET_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    phrase = match.group("phrase") or match.group("subject")
    if not _targets_understood(phrase, count_agnostic=True):
        return None
    durations = ("next_turn", "this_turn", "remains")
    if sum(match.group(name) is not None for name in durations) != 1:
        return None
    combat_only = match.group("combat") is not None
    lasts_while_source = match.group("remains") is not None
    until_next_turn = match.group("next_turn") is not None
    spent_color = Color(match.group("color").upper()) if match.group("color") else None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from ...models.game import PreventionShield, ShieldKind

        is_spell = isinstance(stack_object, CardState)
        source = stack_object if is_spell else stack_object.source(game)  # type: ignore[union-attr]
        condition: RemainsOnBattlefield | None = None
        if lasts_while_source:
            # CR 611.2b: the source (the Saga) must still be the object the
            # ability came from; one already gone never starts the duration.
            if (
                source is None
                or source.zone is not Zone.BATTLEFIELD
                or source.zone_change_stamp is None
                or (
                    not is_spell
                    and stack_object.source_stamp is not None  # type: ignore[union-attr]
                    and source.zone_change_stamp != stack_object.source_stamp  # type: ignore[union-attr]
                )
            ):
                return
            condition = RemainsOnBattlefield(card_id=source.id, stamp=source.zone_change_stamp)
        controller = game.controller_of(stack_object).username
        targets = [
            target
            for target in game.resolve_card_targets(stack_object)
            if target.zone is Zone.BATTLEFIELD
        ]
        for target in targets:
            game.create_prevention_shield(
                PreventionShield(
                    kind=ShieldKind.ALL,
                    label=(
                        f"prevent all {'combat ' if combat_only else ''}damage that would be "
                        f"dealt by {target.name}"
                    ),
                    controller=controller,
                    source_id=target.id,
                    source_stamp=target.zone_change_stamp,
                    combat_only=combat_only,
                    until_end_of_turn=not (lasts_while_source or until_next_turn),
                    until_next_turn_of=controller if until_next_turn else None,
                    lasts_while=condition,
                )
            )
        if spent_color is None or not is_spell or not targets:
            return
        if game.cast_record(stack_object).mana_of_color_spent(spent_color) <= 0:  # type: ignore[arg-type]
            return
        for target in targets:
            # CR 608.2h: the creature's power as this part of the effect runs.
            power = game.characteristics_of(target).numeric_power
            if power > 0:
                game.deal_damage(game.controller_of(target), power, source=stack_object)  # type: ignore[arg-type]

    return effect


#: CR 702.189a's firebending ability, written out: "Firebending is a triggered
#: ability. 'Firebending N' means 'Whenever this creature attacks, add N {R}.
#: Until end of combat, you don't lose this mana as steps and phases end.'"
#:
#: `N` is written as a bare number by most printings and as an `X` the card
#: defines in its own words by Firebending Student ("Firebending X, where X is
#: this creature's power"), which is why the "where X is ..." tail is part of
#: this shape rather than something resolved before the ability ever resolves:
#: **CR 608.2h**, "If an effect requires information from the game (such as the
#: number of creatures on the battlefield), the answer is determined only once,
#: when the effect is applied." Applied is as this ability resolves, so a
#: creature pumped while the trigger waits on the stack makes more mana.
#:
#: The second sentence is carried out too: keeping mana through a step or
#: phase ending is a replacement effect on CR 500.5/703.4q's turn-based
#: action (CR 500.5a - "until end of combat" expires at the end of the combat
#: phase), modelled generally by `ManaRetentionScope`/`ManaPool.retained` -
#: see `models/mana.py`'s own docstring for the family this and Photon,
#: Mighty Marvel's trigger both belong to.
_FIREBENDING_ADD_MANA_RE = re.compile(
    r"^add (?P<amount>x|\d+)\s*(?P<mana>(?:\{[wubrgc]\}\s*)+)"
    r"(?:,\s*where x is (?P<expr>[^.]+?))?\.\s*"
    r"until end of combat, you don'?t lose this mana as steps and phases end\.?$",
    re.IGNORECASE,
)

#: The only "where X is ..." definition firebending prints in the pool. Read
#: off the resolving ability's own source (CR 113.7a: the ability is
#: independent of it, so a source that has left makes no mana rather than
#: raising) through `Game.power_of`, which is the computed power (CR 613.5,
#: CR 613.4c) rather than the printed one.
_FIREBENDING_X_IS_POWER_RE = re.compile(r"^this creature'?s power$", re.IGNORECASE)


@ABILITY_TEXT.rung("s22")
def _parse_firebending_add_mana(text: str) -> AbilityEffect | None:
    """CR 702.189a's "add N {R}", off the triggered ability keyword expansion.

    Not a mana ability: CR 605.1b requires a triggered mana ability to trigger
    "from the activation or resolution of an activated mana ability", and
    attacking is neither, so this goes on the stack and can be responded to -
    which is the whole point of DDR#988's question about when X is read.
    """
    match = _FIREBENDING_ADD_MANA_RE.fullmatch(text.strip())
    if match is None:
        return None
    symbols = _MANA_SYMBOL_RE.findall(match.group("mana"))
    if not symbols:
        return None
    colors = [Color(symbol.upper()) for symbol in symbols]
    amount = match.group("amount")
    expr = match.group("expr")
    if amount.lower() == "x":
        if expr is None or _FIREBENDING_X_IS_POWER_RE.fullmatch(expr.strip()) is None:
            # An X this parser cannot read is not guessed at.
            return None
        fixed: int | None = None
    else:
        if expr is not None:
            return None
        fixed = int(amount)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if fixed is not None:
            count = fixed
        else:
            source = ability.source(game)
            count = (game.power_of(source) or 0) if source is not None else 0
        pool = game.player(ability.controller).mana_pool
        for _ in range(max(count, 0)):
            for color in colors:
                pool.add(color, retain_until=ManaRetentionScope.END_OF_COMBAT)
        # CR 702.189b: "An ability that triggers whenever a player firebends
        # triggers whenever a firebending ability they control resolves" -
        # whatever it added, this one just did.
        _record_bending(game, "firebent", ExtraTriggerEvent.FIREBENDS, ability.controller)

    return effect


def _record_bending(game: "Game", fact: str, event: ExtraTriggerEvent, player: str) -> None:
    """One bending action done by `player`: the per-turn fact Avatar Aang's
    "if you've done all four this turn" reads, and the event its "whenever
    you ... bend" trigger watches (CR 701.65b, 701.66b, 702.189b)."""
    from ..triggers import GameEvent

    game.record_turn_fact(fact, player)
    game.emit(GameEvent(event=event, player=player))


#: "Whenever `<this>` attacks, `<pronoun>` deals damage equal to `<count>`
#: to any target[/to each opponent]." - Smaug the Magnificent's own
#: "Whenever Smaug attacks, he deals damage equal to the number of
#: Treasures you control to any target." and Eivor, Battle-Ready's real,
#: modern-legal "Whenever Eivor attacks, it deals damage equal to the
#: number of Equipment you control to each opponent." - the identical
#: magnitude grammar with two different printed recipients, read the CR
#: 201.5-self-normalized way (the printed name/pronoun is rewritten to
#: "it"/"he"/"she" before `trigger_effect_for`'s fallback ever reaches a
#: clause parser, so the literal pronouns are read directly here rather
#: than needing yet another normalization pass). `count_expression` already
#: reads "the number of `<qualifier>` you control" whole - this is that
#: same expression grammar, just reached from a "deals damage equal to ..."
#: opening instead of a "for each" one.
_SELF_DAMAGE_EQUAL_TO_COUNT_RE = re.compile(
    r"^(?P<subject>it|he|she|this [a-z]+) deals damage equal to (?P<expr>.+?) to "
    r"(?P<recipient>any (?:other )?target|each opponent)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s19", for_spell=FORWARD)
def _parse_self_damage_equal_to_count_clause(text: str, *, for_spell: bool) -> AbilityEffect | None:
    """`_SELF_DAMAGE_EQUAL_TO_COUNT_RE`'s shape; see the banner above.

    Ability-only: the bare pronoun/"this `<noun>`" subject only ever names a
    permanent's own ability, the same restriction `_parse_damage_that_much_
    clause` already holds itself to for the identical reason.

    A bare pronoun ("it"/"he"/"she") is CR 400.7's ordinary anaphora back to
    whichever object the trigger's own *condition* clause named as having
    done something (CR 603.2's "subject" of the event) - Smaug the
    Magnificent's and Eivor's own "Whenever `<self>` attacks, `<pronoun>`
    deals damage ..." happens to name the source itself only because the
    condition is *also* self-referential ("Smaug attacks"); Champion of the
    Path's "Whenever another Elemental you control enters, it deals damage
    equal to its power to each opponent" names a genuinely different
    object - CR 208.1's own "its power" is the entering Elemental's, not
    Champion's. `event_subject_power`/`ability.event.subject_id` already
    name exactly that antecedent for *any* of these event kinds (including
    the purely self-referential ones, where the event's own subject and the
    ability's source are simply the same object), so a bare-pronoun subject
    reads through it uniformly rather than defaulting to the source - a
    printed "this `<noun>`" subject is left alone (the source is genuinely
    what that phrasing names, CR 201.5).
    """
    if for_spell:
        return None
    match = _SELF_DAMAGE_EQUAL_TO_COUNT_RE.fullmatch(text.strip())
    if match is None:
        return None
    is_bare_pronoun = match.group("subject").lower() in ("it", "he", "she")
    expr = match.group("expr")
    counted = count_expression(expr)
    # "its power"/"his power"/"her power" (Iron Fist, Living Weapon's own
    # granted "{T}: this permanent deals damage equal to his power to any
    # other target") is `amount_expression`'s own vocabulary (CR 208.1's
    # power/toughness), not `count_expression`'s ("the number of `<quality>`
    # you control") - tried second, since `count_expression`'s own
    # "the number of ... power ..." phrasings (none in the pool) would
    # otherwise never get a chance to match first.
    # Red Hulk's reflexive "... equal to the number of +1/+1 counters on him"
    # - an amount read off the dealer itself (CR 608.2h), not a count of
    # something its controller controls.
    magnitude = (
        amount_expression(re.sub(r"\bon (?:him|her)\b", "on it", expr, flags=re.IGNORECASE))
        if counted is None
        else None
    )
    if counted is None and magnitude is None:
        return None
    recipient = match.group("recipient").lower()
    each_opponent = recipient == "each opponent"
    if not each_opponent and not _targets_understood(recipient, allow_player_targets=True):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        if is_bare_pronoun:
            event = ability.event
            subject = game.find_by_id(event.subject_id) if event is not None else None
            if isinstance(subject, CardState):
                source = subject
        if counted is not None:
            amount = counted(game, ability.controller)
        else:
            assert magnitude is not None
            amount = magnitude(game, ability.controller, source, ability.x_value)
        if amount <= 0:
            return
        if each_opponent:
            for opponent in _opponents(game, ability.controller):
                game.deal_damage(opponent, amount, source=source)
            return
        for target in game.resolve_targets(ability):
            game.deal_damage(target, amount, source=source)

    return effect


@MIXED_CLAUSE.rung("s35", before=["damage._parse_damage_each_filtered_clause"])
def _parse_damage_each_group_clause(clause: str) -> TargetedClause | None:
    """`_DAMAGE_EACH_GROUP_RE`'s shape: simultaneous, non-targeted damage
    (CR 120.1) to every permanent presently on the battlefield matching one of
    the named card types - no target at all, so CR 608.2b's legality recheck
    never applies, only the board as it stands when this runs.

    Calamitous Cave-In's own "X damage to each creature and each
    planeswalker, where X is the number of Caves you control plus the number
    of Cave cards in your graveyard" is CR 107.3f's X, read through
    `_fixed_or_where_x_amount` the same way earthbend's and amass's own X are
    just above - an "X" this clause cannot evaluate leaves the whole
    instruction unread (CR 608.2c) rather than dealing zero.
    """
    match = _DAMAGE_EACH_GROUP_RE.fullmatch(clause.strip())
    if match is None:
        return None
    reader = _fixed_or_where_x_amount(match.group("n"), match.group("where_x"))
    if reader is None:
        return None
    words = re.split(r"\s+and\s+each\s+", match.group("groups"))
    types: set[Type] = set()
    players = False
    for word in words:
        if word.lower() == "player":
            players = True  # CR 102.1: "each creature and each player" (Inferno)
            continue
        card_type = _singular_card_type(word)
        if card_type is None:
            return None
        types.add(card_type)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object
            if isinstance(stack_object, CardState)
            else stack_object.source_or_last_known(game)
        )
        controller = game.controller_of(stack_object).username
        x_value = stack_object.x_value if isinstance(stack_object, AbilityOnStack) else 0
        amount = reader(game, controller, source, x_value)
        board = game.computed_board()
        recipients = [
            permanent
            for permanent in list(game.battlefield)
            if types & set(board.of(permanent).types)
        ]
        for permanent in recipients:
            game.deal_damage(permanent, amount, source=source)
        if players:
            for player in game.players_in_game:
                game.deal_damage(player, amount, source=source)

    return effect


#: "<Source> deals N damage to target <player> and each creature <they
#: control>." - one CR 608.2c instruction whose second recipient group is
#: named by the first one's target, so the clause splitter's bare " and "
#: cut would leave "each creature they control" with no player to read
#: "they" against:
#:
#:   The Great Work I   "This Saga deals 3 damage to target opponent and each
#:                      creature they control."
#:   Flame Wave         "Flame Wave deals 4 damage to target player or
#:                      planeswalker and each creature that player or that
#:                      planeswalker's controller controls."
#:
#: The target is a player (or, where printed, a planeswalker, whose
#: controller then owns the "each creature" half - CR 120.3c: the
#: planeswalker takes the damage, not its controller).
_DAMAGE_TARGET_PLAYER_AND_THEIR_CREATURES_RE = re.compile(
    rf"^.*\bdeals? (?P<n>{AMOUNT}) damage to "
    r"(?P<phrase>target (?:player|opponent)(?: or planeswalker)?) and each "
    r"(?P<groups>[a-z]+(?:\s+and\s+[a-z]+)*) "
    r"(?:they control|that player controls"
    r"|that player or that planeswalker(?:'|\u2019)s controller controls)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
@SPELL_TEXT.rung("s10")
def _parse_damage_target_player_and_their_creatures_clause(
    text: str,
) -> TargetedClause | None:
    """`_DAMAGE_TARGET_PLAYER_AND_THEIR_CREATURES_RE`'s shape, for a spell and
    an ability alike.

    CR 608.2b: the target is rechecked as this resolves; an illegal one means
    no player to name, so nothing is dealt at all. The amount is read once
    (CR 608.2h) and dealt to the target first, then to each creature of the
    group it names - one source (CR 120.2b), one resolution.
    """
    match = _DAMAGE_TARGET_PLAYER_AND_THEIR_CREATURES_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    if not _targets_understood(
        match.group("phrase"), battlefield_only=False, allow_player_targets=True
    ):
        return None
    amount_of = _resolve_multiplied_amount(match.group("n"), None, None)
    if amount_of is None:
        return None
    types: set[Type] = set()
    for word in re.split(r"\s+and\s+", match.group("groups")):
        card_type = _singular_card_type(word.strip())
        if card_type is None:
            return None
        types.add(card_type)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object
            if isinstance(stack_object, CardState)
            else stack_object.source_or_last_known(game)
        )
        controller = game.controller_of(stack_object).username
        targets = game.resolve_targets(stack_object)
        if not targets:
            return  # CR 608.2b
        target = targets[0]
        if isinstance(target, CardState):
            if target.zone is not Zone.BATTLEFIELD:
                return
            victim = game.controller_of(target).username
        else:
            victim = target.username
        amount = max(amount_of(game, controller), 0)
        if amount <= 0:
            return
        board = game.computed_board()
        recipients = [
            permanent
            for permanent in list(game.battlefield)
            if permanent.controller == victim and types & set(board.of(permanent).types)
        ]
        game.deal_damage(target, amount, source=source)
        for permanent in recipients:
            if permanent.zone is Zone.BATTLEFIELD:
                game.deal_damage(permanent, amount, source=source)

    return effect


#: "each opponent and each <types> they control" - End the Festivities - or
#: "... you don't control" - Omnath, Locus of Creation's "each opponent and
#: each planeswalker you don't control". The players are damaged too (CR
#: 119.2: "Damage dealt to a player normally causes that player to lose that
#: much life"), which is what makes this different from every other filter
#: here. "They control" is the named opponents' own permanents; "you don't
#: control" is every permanent whose controller is not the effect's "you"
#: (CR 109.5).
_DAMAGE_EACH_OPPONENT_AND_THEIRS_RE = re.compile(
    r"^opponent and each (?P<groups>[a-z]+(?:\s+and\s+(?:each\s+)?[a-z]+)*) "
    r"(?P<whose>they control|you don(?:'|\u2019)t control)$",
    re.IGNORECASE,
)

#: "<type list> you control" / "<type list> your opponents control" /
#: "<type list> you don't control" - Fulminous Forte's own "each creature and
#: planeswalker your opponents control", Barrage of Boulders' "each creature
#: you don't control": the same bare CR 205.2a type list `_parse_mass_type_qualifier`
#: already reads, with a controller restriction appended. Read as its own
#: whole-clause shape rather than folded into `_parse_damage_group_filter`'s
#: predicate, since a controller check needs the resolving object's own
#: controller (CR 102.2's "you"/"opponent"), which that predicate's
#: `(game, permanent)` signature has no way to reach.
_DAMAGE_GROUP_TYPES_AND_CONTROLLER_RE = re.compile(
    r"^(?P<types>[a-z]+(?:(?:,\s*| and | or )[a-z]+)*) "
    r"(?P<whose>you control|your opponents control|you don(?:'|\u2019)t control)$",
    re.IGNORECASE,
)

#: "<type> with <keyword>" / "<type> without <keyword>" - CR 702's keyword
#: abilities as a filter on an otherwise plain type group.
_DAMAGE_GROUP_KEYWORD_RE = re.compile(
    r"^(?P<group>[a-z]+) (?P<sense>with|without) (?P<keyword>[a-z]+)$", re.IGNORECASE
)


def _parse_damage_group_filter(
    phrase: str,
) -> Callable[["Game", CardState], bool] | None:
    """A predicate over permanents for `_DAMAGE_EACH_FILTERED_RE`'s filter
    half, read off the *computed* board (CR 613.5) so a type change in layer 4
    or a keyword granted or removed in layer 6 is honoured.

    Two grammars, both narrow on purpose:

    - a keyword filter, "<type> with <keyword>" / "<type> without <keyword>";
    - `_parse_mass_type_qualifier`'s own type grammar, which already reads a
      "non<type>" negation prefix.

    `None` for anything else.
    """
    text = phrase.strip().lower()

    keyword_match = _DAMAGE_GROUP_KEYWORD_RE.fullmatch(text)
    if keyword_match is not None:
        group_type = _singular_card_type(keyword_match.group("group"))
        if group_type is None:
            return None
        keyword = keyword_match.group("keyword").lower()
        if keyword not in _DAMAGE_FILTER_KEYWORDS:
            return None
        wanted = keyword_match.group("sense").lower() == "with"

        def keyword_predicate(game: "Game", permanent: CardState) -> bool:
            chars = game.characteristics_of(permanent)
            if group_type not in chars.types:
                return False
            return has_keyword(permanent, keyword, game) is wanted

        return keyword_predicate

    type_matches = _parse_mass_type_qualifier(text)
    if type_matches is None:
        return None

    def type_predicate(game: "Game", permanent: CardState) -> bool:
        return type_matches(game.characteristics_of(permanent))

    return type_predicate


#: "<group> except for <group>" - Flame Sweep's "each creature except for
#: creatures you control with flying", Ajani Unrelenting's "each creature
#: except for tokens you control": the first group, less every member of the
#: second.
_DAMAGE_GROUP_EXCEPT_RE = re.compile(r"^(?P<base>.+?) except for (?P<excluded>.+)$", re.IGNORECASE)

#: A controller qualifier (CR 109.5) on a group, with an optional keyword
#: qualifier printed after it: "creatures you control with flying" (Flame
#: Sweep) as well as the keyword-first "creature with flying your opponents
#: control" (Sagittars' Volley), which reaches this with the keyword still
#: inside `group`.
_GROUP_CONTROLLER_RE = re.compile(
    r"^(?P<group>.+?) (?P<whose>you control|your opponents control|you don(?:'|\u2019)t control)"
    r"(?: (?P<sense>with|without) (?P<keyword>[a-z]+(?: [a-z]+)?))?$",
    re.IGNORECASE,
)

#: "non-<Subtype> <group>" - Fiery Cannonade's "each non-Pirate creature": a
#: CR 205.3m creature type negated, hyphenated the way Oracle text prints a
#: subtype negation (a card-type negation is unhyphenated, "nonartifact", and
#: is `_parse_mass_type_qualifier`'s own).
_GROUP_NONTOKEN_RE = re.compile(r"^nontoken (?P<group>.+)$", re.IGNORECASE)

#: "creature dealt damage this turn" - a turn-history qualifier (Inflame),
#: answered off `Game.damage_dealt_this_turn` when the effect applies (CR 120.1).
_GROUP_DEALT_DAMAGE_THIS_TURN_RE = re.compile(
    r"^(?P<group>.+?) (?:that (?:was|were) )?dealt damage this turn$", re.IGNORECASE
)

_GROUP_NON_SUBTYPE_RE = re.compile(
    r"^non-(?P<subtype>[a-z]+(?:-[a-z]+)*) (?P<group>.+)$", re.IGNORECASE
)


#: "attacking creature", "tapped creature" - a combat or tapped-state
#: adjective ahead of a group (Marrow Shards' and Rain of Blades' "each
#: attacking creature", The Akroan War's "each tapped creature"). Not
#: characteristics (CR 109.3): the answer is on the game's combat or the
#: permanent, so it is read when the effect applies (CR 608.2h).
_GROUP_STATE_RE = re.compile(
    r"^(?P<state>attacking or blocking|attacking|blocking|tapped|untapped) (?P<group>.+)$",
    re.IGNORECASE,
)


def _in_group_state(game: "Game", permanent: CardState, state: str) -> bool:
    if state == "tapped":
        return permanent.tapped
    if state == "untapped":
        return not permanent.tapped
    attacking = game.is_attacking(permanent)
    blocking = game.is_blocking(permanent)
    if state == "attacking":
        return attacking
    if state == "blocking":
        return blocking
    return attacking or blocking


def _permanent_subtype_noun(text: str) -> str | None:
    """A bare permanent subtype used as a whole group - "Aura", "Equipment",
    "Saga" (Aura Barbs' "each Aura attached to a creature") - or None."""
    word = text.strip().lower()
    if word in {"creature", "permanent", "land", "artifact", "enchantment", "planeswalker"}:
        return None
    return canonical_subtype(word)


def _parse_damage_group_phrase(phrase: str) -> GroupPredicate | None:
    """A mass-damage group (CR 115.10a, no target) with any of its printed
    qualifiers, read off the computed board (CR 613.5) at the moment the
    effect is applied (CR 608.2h):

    - "<group> except for <group>" - every member of the first that is not a
      member of the second;
    - a controller qualifier, "you control" / "your opponents control" /
      "you don't control" (CR 109.5), with an optional keyword after it;
    - "non-<Subtype>" ahead of the group (CR 205.3m);
    - "token(s)" as the group (CR 111.1);
    - otherwise `_parse_damage_group_filter`'s type and keyword grammar.

    `None` for anything else, so an unread qualifier fails the clause rather
    than widening the damage to creatures the card never named.
    """
    text = phrase.strip()
    union_parts = re.split(r"\s+and\s+each\s+", text, flags=re.IGNORECASE)
    if len(union_parts) > 1:
        # "each creature and each non-Bolas planeswalker" (Hour of
        # Devastation), "each non-Giant creature and each planeswalker"
        # (Battle of Frost and Fire): every permanent in any of the groups.
        members = [_parse_damage_group_phrase(part) for part in union_parts]
        if any(member is None for member in members):
            return None

        def union_predicate(game: "Game", permanent: CardState, controller: str) -> bool:
            return any(
                member is not None and member(game, permanent, controller) for member in members
            )

        return union_predicate
    except_match = _DAMAGE_GROUP_EXCEPT_RE.fullmatch(text)
    if except_match is not None:
        base = _parse_damage_group_phrase(except_match.group("base"))
        excluded = _parse_damage_group_phrase(except_match.group("excluded"))
        if base is None or excluded is None:
            return None

        def except_predicate(game: "Game", permanent: CardState, controller: str) -> bool:
            return base(game, permanent, controller) and not excluded(game, permanent, controller)

        return except_predicate

    whose: str | None = None
    controller_match = _GROUP_CONTROLLER_RE.fullmatch(text)
    if controller_match is not None:
        whose = controller_match.group("whose").lower()
        text = controller_match.group("group").strip()
        if controller_match.group("sense") is not None:
            text = f"{text} {controller_match.group('sense')} {controller_match.group('keyword')}"

    state: str | None = None
    state_match = _GROUP_STATE_RE.fullmatch(text)
    if state_match is not None:
        state = state_match.group("state").lower()
        text = state_match.group("group").strip()

    nontoken = False
    nontoken_match = _GROUP_NONTOKEN_RE.fullmatch(text)
    if nontoken_match is not None:
        nontoken = True  # CR 111.1: a token is a marker, not a card
        text = nontoken_match.group("group").strip()

    dealt_damage_this_turn: Callable[[Game, CardState], bool] | None = None
    dealt_match = _GROUP_DEALT_DAMAGE_THIS_TURN_RE.fullmatch(text)
    if dealt_match is not None:
        dealt_test = object_dealt_damage_clause_test("was dealt damage this turn")
        if dealt_test is None:
            return None
        text = dealt_match.group("group").strip()

        def dealt_damage_this_turn(game: "Game", permanent: CardState) -> bool:
            return dealt_test(game, permanent, None)

    excluded_subtype: str | None = None
    subtype_match = _GROUP_NON_SUBTYPE_RE.fullmatch(text)
    if subtype_match is not None:
        excluded_subtype = subtype_match.group("subtype").lower()
        if excluded_subtype not in subtype_vocabulary():
            return None
        text = subtype_match.group("group").strip()

    member: Callable[[Game, CardState], bool] | None
    if text.lower() in {"token", "tokens"}:

        def member(game: "Game", permanent: CardState) -> bool:
            return permanent.token

    elif (own_subtype := _permanent_subtype_noun(text)) is not None:

        def member(game: "Game", permanent: CardState) -> bool:
            return own_subtype in {
                subtype.lower() for subtype in game.characteristics_of(permanent).subtypes
            }

    else:
        member = _parse_damage_group_filter(text)
        if member is None:
            return None
    in_group = member

    def predicate(game: "Game", permanent: CardState, controller: str) -> bool:
        if not in_group(game, permanent):
            return False
        if nontoken and permanent.token:
            return False
        if dealt_damage_this_turn is not None and not dealt_damage_this_turn(game, permanent):
            return False
        if state is not None and not _in_group_state(game, permanent, state):
            return False
        if excluded_subtype is not None and excluded_subtype in {
            subtype.lower() for subtype in game.characteristics_of(permanent).subtypes
        }:
            return False
        if whose is None:
            return True
        opponent_names = {opponent.username for opponent in _opponents(game, controller)}
        return _controlled_by_whose(permanent, whose, controller, opponent_names)

    return predicate


#: The keywords a "with <keyword>" / "without <keyword>" damage filter is
#: allowed to name. Deliberately a short list of evasion and combat keywords
#: whose presence `machines/combat.has_keyword` genuinely answers off the
#: computed board, rather than any word at all - an unknown word must fail the
#: parse, not silently answer "no permanent has it" and sweep the whole type.
_DAMAGE_FILTER_KEYWORDS = frozenset(
    {
        "flying",
        "reach",
        "trample",
        "vigilance",
        "haste",
        "menace",
        "defender",
        "lifelink",
        "deathtouch",
        "first strike",
        "double strike",
        "indestructible",
        "hexproof",
        "shroud",
    }
)


_AND_EACH_PLAYER = " and each player"


@MIXED_CLAUSE.rung("s35")
def _parse_damage_each_filtered_clause(clause: str) -> TargetedClause | None:
    """`_DAMAGE_EACH_FILTERED_RE`'s shape: simultaneous, non-targeted damage
    (CR 120.1, CR 608.2f) to every permanent on the battlefield matching the
    filter - and, for the "each opponent and ..." wording, to those opponents
    as well (CR 119.2).

    The recipient set is snapshotted before any damage is dealt, for the same
    CR 608.2f reason `_destroy_matching` documents: "in most cases, each such
    action is processed simultaneously", so a creature dying to an earlier
    step of this loop cannot change who the rest of it hits.
    """
    match = _DAMAGE_EACH_FILTERED_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount_of = _resolve_multiplied_amount(match.group("n"), None, match.group("where_x"))
    if amount_of is None:
        return None
    phrase = match.group("filter").strip()

    opponents_match = _DAMAGE_EACH_OPPONENT_AND_THEIRS_RE.fullmatch(phrase)
    if opponents_match is not None:
        types: set[Type] = set()
        for word in re.split(r"\s+and\s+(?:each\s+)?", opponents_match.group("groups")):
            card_type = _singular_card_type(word.strip())
            if card_type is None:
                return None
            types.add(card_type)
        whose = opponents_match.group("whose").lower()

        def opponents_effect(game: "Game", stack_object: "StackObject") -> None:
            source = (
                stack_object
                if isinstance(stack_object, CardState)
                else stack_object.source_or_last_known(game)
            )
            controller = game.controller_of(stack_object).username
            amount = max(amount_of(game, controller), 0)  # CR 608.2h, once
            if amount <= 0:
                return
            opponents = _opponents(game, controller)
            names = {opponent.username for opponent in opponents}
            board = game.computed_board()
            recipients = [
                permanent
                for permanent in list(game.battlefield)
                if _controlled_by_whose(permanent, whose, controller, names)
                and types & set(board.of(permanent).types)
            ]
            for opponent in opponents:
                game.deal_damage(opponent, amount, source=source)
            for permanent in recipients:
                if permanent.zone is Zone.BATTLEFIELD:
                    game.deal_damage(permanent, amount, source=source)

        return opponents_effect

    controller_match = _DAMAGE_GROUP_TYPES_AND_CONTROLLER_RE.fullmatch(phrase)
    if controller_match is not None:
        types = set()
        for word in re.split(r",\s*|\s+and\s+|\s+or\s+", controller_match.group("types")):
            card_type = _singular_card_type(word.strip())
            if card_type is None:
                return None
            types.add(card_type)
        whose = controller_match.group("whose").lower()

        def controller_scoped_effect(game: "Game", stack_object: "StackObject") -> None:
            source = (
                stack_object
                if isinstance(stack_object, CardState)
                else stack_object.source_or_last_known(game)
            )
            controller = game.controller_of(stack_object).username
            amount = max(amount_of(game, controller), 0)  # CR 608.2h, once
            if amount <= 0:
                return
            opponent_names = {opponent.username for opponent in _opponents(game, controller)}
            board = game.computed_board()
            recipients = [
                permanent
                for permanent in list(game.battlefield)
                if _controlled_by_whose(permanent, whose, controller, opponent_names)
                and types & set(board.of(permanent).types)
            ]
            for permanent in recipients:
                if permanent.zone is Zone.BATTLEFIELD:
                    game.deal_damage(permanent, amount, source=source)

        return controller_scoped_effect

    # "each creature without flying and each player" (CR 102.1's players are
    # a second recipient group of the one instruction, Earthquake).
    players = False
    if phrase.lower().endswith(_AND_EACH_PLAYER):
        phrase = phrase[: -len(_AND_EACH_PLAYER)].strip()
        players = True
    predicate = _parse_damage_group_phrase(phrase)
    if predicate is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object
            if isinstance(stack_object, CardState)
            else stack_object.source_or_last_known(game)
        )
        controller = game.controller_of(stack_object).username
        amount = max(amount_of(game, controller), 0)
        if amount <= 0:
            return
        recipients = [
            permanent
            for permanent in list(game.battlefield)
            if predicate(game, permanent, controller)
        ]
        for permanent in recipients:
            if permanent.zone is Zone.BATTLEFIELD:
                game.deal_damage(permanent, amount, source=source)
        if players:
            for player in game.players_in_game:
                game.deal_damage(player, amount, source=source)

    return effect


#: "If a creature dealt damage this way would die this turn, exile it
#: instead." - Anger of the Gods' closing sentence; Underworld Fires' "a
#: permanent", Serpentine Spike's and Pillar of Flame's "a creature" after a
#: targeted rather than a group damage clause. CR 614.1a: a replacement effect
#: the resolving spell creates, naming exactly the permanents its own damage
#: clause dealt damage to (CR 120.3 - damage prevented is never dealt).
#:
#: The same rider also reads "dealt damage by `<this spell's name>`" (Torch the
#: Tower's "If a permanent dealt damage by Torch the Tower would die this turn,
#: exile it instead."), where the source is the resolving spell itself - the
#: rider is printed on that spell, so a capitalised name or "this spell" can
#: only mean it; a lower-case group ("creatures you control") is not read.
_DEALT_DAMAGE_THIS_WAY_DIE_TO_EXILE_RE = re.compile(
    r"^(?P<rest>.+?\.)\s+if an? (?P<quality>[a-z]+(?: or [a-z]+)*) dealt damage "
    r"(?:this way|by (?:this spell|(?-i:[A-Z][\w',\- ]*))) "
    r"would die this turn, exile it instead\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: The quality words that rider names: CR 110.4's permanent types, or
#: "permanent" for any of them.
_DEALT_DAMAGE_QUALITY_TYPES: dict[str, Type] = {
    "creature": Type.CREATURE,
    "planeswalker": Type.PLANESWALKER,
    "artifact": Type.ARTIFACT,
    "enchantment": Type.ENCHANTMENT,
    "land": Type.LAND,
    "battle": Type.BATTLE,
}


@SPELL_TEXT.rung("s6")
def _parse_dealt_damage_this_way_die_to_exile(text: str) -> Effect | None:
    """A damage-dealing spell followed by "If a `<quality>` dealt damage this
    way would die this turn, exile it instead." (CR 614.1a, CR 700.4).

    The leading text is read by the ordinary spell dispatcher; its damage is
    recorded by source (`Game.recording_damage_from`) while it runs, and every
    permanent of the named quality it actually dealt damage to is put on
    `Game.die_to_exile_this_turn` - the same marker Essence Burn's targeted
    "If that permanent would die this turn" uses, read by `machines/
    replacement.py`'s `_die_to_exile_this_turn_effects` and ended by CR
    514.2's cleanup. A leading text the dispatcher cannot read leaves this
    unread too (fail closed).
    """
    match = _DEALT_DAMAGE_THIS_WAY_DIE_TO_EXILE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    words = match.group("quality").lower().split(" or ")
    if words == ["permanent"]:
        wanted: frozenset[Type] | None = None
    elif all(word in _DEALT_DAMAGE_QUALITY_TYPES for word in words):
        wanted = frozenset(_DEALT_DAMAGE_QUALITY_TYPES[word] for word in words)
    else:
        return None
    rest = _spell_effect_or_notice(match.group("rest"))
    if rest is None or _is_notice_only(rest):
        return None

    def dealt_damage_this_way_die_to_exile(game: "Game", spell: CardState) -> None:
        with game.recording_damage_from(spell) as damaged:
            rest(game, spell)
        for permanent_id in damaged:
            permanent = game.find_by_id(permanent_id)
            if not isinstance(permanent, CardState) or permanent.zone is not Zone.BATTLEFIELD:
                continue
            if wanted is not None and not (wanted & set(game.characteristics_of(permanent).types)):
                continue
            if permanent.id not in game.die_to_exile_this_turn:
                game.die_to_exile_this_turn.append(permanent.id)

    return dealt_damage_this_way_die_to_exile


# --------------------------------------------------------------------------
# Fight (CR 701.14) and Kraul Harpooner's own pump-then-fight shape
# --------------------------------------------------------------------------


def _fight(game: "Game", a: CardState, b: CardState) -> None:
    """CR 701.14a: "Each of those creatures deals damage equal to its power to
    the other creature." Simultaneous - neither call below sees the other's
    result, since state-based actions are not checked until both are done -
    and CR 701.14d: "The damage dealt when a creature fights isn't combat
    damage," so nothing here touches `machines/combat.py`.

    CR 701.14b: "If one or both creatures instructed to fight are no longer on
    the battlefield or are no longer creatures, neither of them fights or
    deals damage" - checked by every caller before this is reached, not
    re-checked here, the same division of labour `destroy_ability_targets`
    already draws between "is this still legal" and "do the thing".

    Recorded on `Game.turn_history` (`conditions.history.record_fight`) for
    every fight through this one function, regardless of which parser called
    it - Boxing Ring's own "Activate only if you control a creature that
    fought this turn" (CR 602.5b) reads that ledger generically, for any
    quality, rather than this fight in particular.
    """
    from ..conditions.history import record_fight

    power_a = game.power_of(a) or 0
    power_b = game.power_of(b) or 0
    game.deal_damage(b, power_a, source=a)
    game.deal_damage(a, power_b, source=b)
    record_fight(game, a, b)


# --------------------------------------------------------------------------
# Fight and bite (CR 701.14), untargeted/independently-targeted shapes
# --------------------------------------------------------------------------
#
# `_RIDER_FIGHTS_TARGET_RE`/`_parse_pump_then_fight_clause_pair` above already
# read a fight whose first participant is a referent an antecedent clause
# just pumped or put a counter on. Three more shapes are ordinary templating
# with no antecedent sentence at all:
#
#   "[this creature/it] fights up to one target creature ..."  - CR 109.2's
#       plain self-reference, no antecedent (Mind Meanderer's own ETB).
#   "<target X> fights <target Y>."                              - both
#       fighters are this one clause's own targets (Yoshimaru, Scrappy
#       Stray's own ETB; the real, off-set printing Struggle reads the
#       identical grammar - "Target creature you control fights target
#       creature you don't control.").
#   "<target creature/planeswalker> you control deals damage equal to its
#   power/loyalty to <target X>."                                - CR
#       701.14's keyword action is never invoked here (the word "fights" is
#       never printed): only CR 119.2's ordinary damage event, amount read
#       off a targeted source. Prey Upon is the real, off-set printing
#       ("Target creature you control deals damage to target creature you
#       don't control equal to the first creature's power."); Compel
#       Brutality's own two modes fold source and amount into one clause,
#       with "loyalty" standing in for "power" on the planeswalker mode.

_SELF_FIGHTS_TARGET_RE = re.compile(
    # "up to one other target creature" (Ifrit, Warden of Inferno's Lunge) and
    # "another target creature" are the same target with the source itself
    # excluded - `profile_for_text` reads "other"/"another" as
    # `excludes_source`, so the fight can never be the creature against itself.
    r"^(?:it|this (?:creature|permanent)) fights "
    r"(?P<phrase>(?:up to \S+ )?(?:other )?target .+|another target .+)$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s13", for_spell=FORWARD)
def _parse_self_fights_target_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "[It/This creature] fights up to one target creature ..." with no
    antecedent sentence to derive a referent from - CR 109.2's plain
    self-reference (the resolving ability's own source), a different
    question from `_referent_reader`'s "it", which exists for a *different*
    clause's own target. Permanents only (CR 109.2 names an object, and a
    resolving spell is never itself a permanent to fight with, CR 300.1) -
    the same restriction `_parse_untap_self_clause` and its neighbours
    already draw.
    """
    if for_spell:
        return None
    match = _SELF_FIGHTS_TARGET_RE.fullmatch(clause.strip().rstrip(".").strip())
    if match is None:
        return None
    phrase = match.group("phrase").strip()
    if not _targets_understood(phrase, count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return  # CR 115.6: "up to one" chose none.
        opponent = targets[0]
        if not game.characteristics_of(source).is_creature:
            return  # CR 701.14b
        if not game.characteristics_of(opponent).is_creature:
            return  # CR 701.14b
        _fight(game, source, opponent)

    return effect


#: "Enchanted creature fights up to one target creature an opponent
#: controls." (Pitiless Fists, CR 701.14a) - `_SELF_FIGHTS_TARGET_RE`'s
#: Aura-attachment twin ("equipped creature", Novel Nunchaku, is the same
#: sentence for an Equipment, CR 301.5): CR 303.4b's "enchanted" names
#: whatever the Aura (`source.attached_to`) is attached to, never the Aura itself (which is
#: never a creature able to fight in the first place, CR 701.14b).
_ENCHANTED_CREATURE_FIGHTS_TARGET_RE = re.compile(
    r"^(?:enchanted|equipped) creature fights "
    r"(?P<phrase>(?:up to \S+ )?(?:other )?target .+|another target .+)$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s13", for_spell=FORWARD)
def _parse_enchanted_creature_fights_target_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_ENCHANTED_CREATURE_FIGHTS_TARGET_RE`'s shape; see the banner above."""
    if for_spell:
        return None
    match = _ENCHANTED_CREATURE_FIGHTS_TARGET_RE.fullmatch(clause.strip().rstrip(".").strip())
    if match is None:
        return None
    phrase = match.group("phrase").strip()
    if not _targets_understood(phrase, count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        if source is None or source.attached_to is None:
            return
        enchanted = game.find_by_id(source.attached_to)
        if enchanted is None or enchanted.zone is not Zone.BATTLEFIELD:
            return
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return  # CR 115.6: "up to one" chose none.
        opponent = targets[0]
        if not game.characteristics_of(enchanted).is_creature:
            return  # CR 701.14b
        if not game.characteristics_of(opponent).is_creature:
            return  # CR 701.14b
        _fight(game, enchanted, opponent)

    return effect


_TARGET_FIGHTS_TARGET_RE = re.compile(
    r"^(?P<first>(?:another )?target .+?) fights (?P<second>(?:up to \S+ )?target .+)$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s13", for_spell=FORWARD)
def _parse_target_fights_target_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "<target X> fights <target Y>." - both fighters this clause's own,
    independent targets (Yoshimaru, Scrappy Stray's own ETB; the real,
    off-set printing Struggle). Told apart by controller, the same way
    `_parse_pump_then_fight_clause_pair` already tells its pump target and
    its fight target apart, since `targets` carries no positional guarantee
    once CR 608.2b removes an illegal one.
    """
    match = _TARGET_FIGHTS_TARGET_RE.fullmatch(clause.strip().rstrip(".").strip())
    if match is None:
        return None
    first_phrase = match.group("first").strip()
    second_phrase = match.group("second").strip()
    if not _targets_understood(first_phrase, count_agnostic=True):
        return None
    if not _targets_understood(second_phrase, count_agnostic=True):
        return None
    first_yours = bool(
        re.search(r"\byou control\b", first_phrase, re.IGNORECASE)
    ) and not re.search(r"don'?t control", first_phrase, re.IGNORECASE)
    second_yours = bool(
        re.search(r"\byou control\b", second_phrase, re.IGNORECASE)
    ) and not re.search(r"don'?t control", second_phrase, re.IGNORECASE)
    if first_yours == second_yours:
        # Both name the same controller, or neither does: no way to tell the
        # two fighters apart once targeting removes an illegal one.
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        mine = [t for t in targets if game.controller_of(t).username == controller.username]
        theirs = [t for t in targets if game.controller_of(t).username != controller.username]
        fighter, opponent = (mine, theirs) if first_yours else (theirs, mine)
        if not fighter or not opponent:
            return  # CR 115.6's "up to one" chose none, or CR 608.2b removed one.
        a, b = fighter[0], opponent[0]
        if not game.characteristics_of(a).is_creature:
            return  # CR 701.14b
        if not game.characteristics_of(b).is_creature:
            return  # CR 701.14b
        _fight(game, a, b)

    return effect


_BITE_DAMAGE_RE = re.compile(
    r"^target (?P<subject_kind>creature|planeswalker) you control deals damage equal to "
    r"its (?P<stat>power|loyalty) to (?P<object>target .+)$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s13", for_spell=FORWARD)
def _parse_bite_damage_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Target creature you control deals damage equal to its power to
    target `<X>`." / "... planeswalker you control deals damage equal to its
    loyalty to target `<X>`." - see the banner above. Both participants are
    this clause's own, independent targets; the anaphoric-object twin
    (Flourishing Grapple's "... to that permanent.") is
    `_parse_bite_damage_clause_pair`'s shape, not this one.
    """
    match = _BITE_DAMAGE_RE.fullmatch(clause.strip().rstrip(".").strip())
    if match is None:
        return None
    subject_phrase = f"target {match.group('subject_kind')} you control"
    object_phrase = match.group("object").strip()
    if not _targets_understood(subject_phrase, count_agnostic=False):
        return None
    if not _targets_understood(object_phrase, count_agnostic=True):
        return None
    stat = match.group("stat").lower()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        _resolve_bite_damage(game, stack_object, stat)

    return effect


def _resolve_bite_damage(game: "Game", stack_object: "StackObject", stat: str) -> None:
    """The shared body `_parse_bite_damage_clause` and
    `_parse_bite_damage_clause_pair` both call: the biter is whichever
    resolved target its controller controls, the victim is whichever target
    (or referent) is not, and the amount is CR 119.2's ordinary damage event
    for `stat`'s current value (CR 613.5's own "continually" for power,
    CR 306.5c's loyalty-counter count for loyalty) - CR 701.14 is never
    invoked, so a biter that stopped being a creature, or a planeswalker
    biter at 0 loyalty, still deals its damage; only CR 608.2b's own
    legal-target recheck governs whether either side is still there at all.
    """
    controller = game.controller_of(stack_object)
    targets = [
        target
        for target in game.resolve_targets(stack_object)
        if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
    ]
    mine = [t for t in targets if game.controller_of(t).username == controller.username]
    theirs = [t for t in targets if game.controller_of(t).username != controller.username]
    if not mine or not theirs:
        return
    source, victim = mine[0], theirs[0]
    amount = (game.power_of(source) or 0) if stat == "power" else (source.loyalty or 0)
    if amount <= 0:
        return
    game.deal_damage(victim, amount, source=source)


_BITE_DAMAGE_RIDER_RE = re.compile(
    r"^target (?P<subject_kind>creature|planeswalker) you control deals damage equal to "
    r"its (?P<stat>power|loyalty) to " + _OBJECT_ANAPHOR + r"$",
    re.IGNORECASE,
)


def _parse_bite_damage_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "`<antecedent>`. Target creature you control deals damage equal to
    its power to that permanent." - Flourishing Grapple's own two sentences.
    Its own pair parser rather than a `_parse_referent_object_clause` rider,
    for the identical reason `_parse_pump_then_fight_clause_pair` is its own
    function: the rider names a target of its own (the biter), which the
    general referent reader would conflate with the antecedent's.
    """
    stripped_second = second.strip().rstrip(".").strip()
    rider = _BITE_DAMAGE_RIDER_RE.fullmatch(stripped_second)
    if rider is None:
        return None
    referent_of = _referent_reader(first)
    if referent_of is None:
        return None
    antecedent = _parse_mixed_clause(first, for_spell=for_spell)
    if antecedent is None:
        # `_prepare_effect_clauses` hands clauses over with their terminal
        # period already stripped, but `is_resolution_layer_effect_text`
        # (through `_effect_sentences`) only recognises a sentence that ends
        # in one - so the fallback needs one put back, the same way a
        # printed clause always carries it.
        first_sentence = first.strip()
        if not first_sentence.endswith("."):
            first_sentence = f"{first_sentence}."
        antecedent = _layer_antecedent_clause(first_sentence, referent_of)
    if antecedent is None:
        return None
    subject_phrase = f"target {rider.group('subject_kind')} you control"
    if not _targets_understood(subject_phrase, count_agnostic=False):
        return None
    stat = rider.group("stat").lower()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        referents = referent_of(game, stack_object)
        antecedent(game, stack_object)
        if not referents:
            return  # nothing for "that permanent" to refer to (CR 115.6/608.2b).
        victim = referents[0]
        if victim.zone is not Zone.BATTLEFIELD:
            return
        controller = game.controller_of(stack_object)
        biters = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState)
            and target.zone is Zone.BATTLEFIELD
            and game.controller_of(target).username == controller.username
            and target.id != victim.id
        ]
        if not biters:
            return
        source = biters[0]
        amount = (game.power_of(source) or 0) if stat == "power" else (source.loyalty or 0)
        if amount <= 0:
            return
        game.deal_damage(victim, amount, source=source)

    return effect


# --------------------------------------------------------------------------
# Group-sourced, multi-target and filtered damage (NW-01, T3)
# --------------------------------------------------------------------------
#
# Several objects each dealing their own damage (CR 120.2b: "The spell or
# ability will specify which object deals that damage"), one spell dealing a
# different amount to each of its several targets, and damage to a group read
# off a target's controller. Each is its own whole-text rung: the clause
# splitter cuts a sentence like "deals 1 damage to any target, 2 damage to
# another target, and 3 damage to a third target" at its commas and bare
# "and"s into fragments no per-clause reader can put back together.


def _resolving_source(game: "Game", stack_object: "StackObject") -> CardState | None:
    """The object whose text this is (CR 120.2b's source for "<Name> deals")."""
    if isinstance(stack_object, CardState):
        return stack_object
    return stack_object.source_or_last_known(game)


def _deal_all(game: "Game", deals: list[tuple[CardState | None, Any, int]]) -> None:
    """Apply `(source, recipient, amount)` triples whose amounts were all fixed
    before the first lands (CR 608.2h: information is read once as the effect
    applies; CR 120.3 + 120.4: each is its own damage event, and state-based
    actions wait until all are done)."""
    for source, recipient, amount in deals:
        if amount <= 0:
            continue
        if isinstance(recipient, CardState) and recipient.zone is not Zone.BATTLEFIELD:
            continue
        game.deal_damage(recipient, amount, source=source)


#: "<sources> each deal damage equal to their power to <victim>." - Allies at
#: Last, Graceful Takedown, Band Together, Friendly Rivalry. The sources are
#: every target announced before the last one; the last is the victim (it is
#: the final, mandatory requirement of every printing, so an "up to N" or
#: "any number of" source list that chose fewer still leaves it last).
_GROUP_SOURCES_DEAL_POWER_RE = re.compile(
    r"^(?P<sources>[^.]+?) each deal damage equal to their power to "
    r"(?P<victim>(?:another )?target [^.,]+)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
@SPELL_TEXT.rung("s10")
def _parse_damage_group_sources_deal_power_text(text: str) -> TargetedClause | None:
    """`_GROUP_SOURCES_DEAL_POWER_RE`'s shape.

    CR 608.2b: each source is rechecked as the effect resolves and an illegal
    one deals nothing, the rest still do; an illegal victim means none of
    them has anything to hit. CR 608.2h: a source's power is read as the
    spell resolves, all of them before any damage lands.
    """
    match = _GROUP_SOURCES_DEAL_POWER_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    profile = profile_for_text(match.group("sources"))
    if not profile.understood or not profile.requirements:
        return None
    if any(not r.allows_cards or r.allows_players for r in profile.requirements):
        return None
    if not _targets_understood(match.group("victim").strip(), count_agnostic=False):
        return None
    return _group_sources_deal_power_effect(
        f"{match.group('sources')}, {match.group('victim')}", before=None
    )


def _group_sources_deal_power_effect(
    slot_text: str,
    *,
    before: Callable[["Game", "StackObject", list[CardState]], None] | None,
) -> TargetedClause | None:
    """The shared resolution of "<sources> each deal damage equal to their
    power to <victim>": `slot_text` is the sources' targets then the victim's,
    whose last requirement is the victim. `before` is an earlier sentence of
    the same instruction that acts on the sources still legal for the
    requirement they were announced under (CR 608.2b) - the pump or tap of
    "Tap one or two target untapped creatures you control. They each deal ..."
    (CR 608.2c: in order) - and runs ahead of the damage whether or not the
    victim is still legal.
    """
    slot_profile = profile_for_text(slot_text)
    if not slot_profile.understood or len(slot_profile.requirements) < 2:
        return None
    victim_slot = len(slot_profile.requirements) - 1

    def effect(game: "Game", stack_object: "StackObject") -> None:
        refs = list(stack_object.targets)
        if not refs:
            return
        # Which target played the victim is the requirement it filled at
        # announcement (CR 601.2c), not where it sits in the list: a victim
        # the caster named first is still the victim.
        things = [game.resolve_target(ref) for ref in refs]
        if all(ref.slot is not None for ref in refs):
            slots = [ref.slot for ref in refs]
        else:
            slots = slot_profile.assign_slots(
                things, game.controller_of(stack_object).username, game, source_id_of(stack_object)
            )
        victim: CardState | None = None
        sources: list[CardState] = []
        for ref, thing, slot in zip(refs, things, slots, strict=True):
            legal = game.legal_target(stack_object, ref) if thing is not None else None
            if not isinstance(legal, CardState) or legal.zone is not Zone.BATTLEFIELD:
                continue
            # CR 608.2b: legal for the requirement it was announced under, not
            # merely for some other one of the spell's (an unenchanted creature
            # is a fine "other" target but no longer an enchanted one).
            if (
                slot is not None
                and slot_profile.requirements[slot].rejects(
                    legal, game.controller_of(stack_object).username, game
                )
                is not None
            ):
                continue
            if slot == victim_slot:
                victim = legal
            elif slot is not None:
                sources.append(legal)
        if before is not None:
            before(game, stack_object, sources)
        if victim is None:
            return
        _deal_all(game, [(source, victim, game.power_of(source) or 0) for source in sources])

    return effect


#: "<sources> each get +N/+M until end of turn. They each deal damage equal to
#: their power to <victim>." (Tandem Takedown, Terrific Team-Up) and "Tap
#: <sources>. They each deal damage equal to their power to <victim>."
#: (Coordinated Clobbering): the first sentence acts on the same targets the
#: second one names with "They".
_SOURCES_ACT_THEN_DEAL_POWER_RE = re.compile(
    r"^(?:(?P<pumped>[^.]+?) each get (?P<pump>[+-]\d+/[+-]\d+) until end of turn"
    r"|tap (?P<tapped>[^.]+?))\.\s+"
    r"they each deal damage equal to their power to (?P<victim>(?:another )?target [^.]+?)\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s10")
def _parse_damage_sources_act_then_deal_power_text(text: str) -> TargetedClause | None:
    """`_SOURCES_ACT_THEN_DEAL_POWER_RE`'s shape.

    CR 608.2c: the pump or tap happens first, so the power each source deals
    is read after it (CR 608.2h); CR 608.2b: an illegal source is neither
    pumped nor tapped nor deals damage, and an illegal victim leaves the
    sources' first sentence still done.
    """
    match = _SOURCES_ACT_THEN_DEAL_POWER_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    sources = match.group("pumped") or match.group("tapped")
    profile = profile_for_text(sources)
    if not profile.understood or not profile.requirements:
        return None
    if any(not r.allows_cards or r.allows_players for r in profile.requirements):
        return None
    if not _targets_understood(match.group("victim").strip(), count_agnostic=False):
        return None
    pump = match.group("pump")
    if pump is not None:
        sentence = f"Target creature gets {pump} until end of turn."
        if not _is_layer_effect_text(sentence) or parsed_layer_effects(sentence) is None:
            return None

        def act(game: "Game", stack_object: "StackObject", sources: list[CardState]) -> None:
            if not sources:
                return
            source = _resolving_source(game, stack_object)
            if source is None:
                return
            continuous_effects(game).create(
                source,
                targets=sources,
                context=layer_context_for(game, game.controller_of(stack_object)),
                ability_text=sentence,
                game=game,
            )

    else:

        def act(game: "Game", stack_object: "StackObject", sources: list[CardState]) -> None:
            for source in sources:
                game.tap_permanent(source)

    return _group_sources_deal_power_effect(f"{sources}, {match.group('victim')}", before=act)


#: "<Name> deals N damage to each <group> and M damage to you and each <group>
#: you control." (Hail Storm): two recipient sets read off the board as it
#: stands, plus the controller.
_DAMAGE_GROUP_AND_YOU_AND_GROUP_RE = re.compile(
    rf"^.*?\bdeals? (?P<n>{COUNT}) damage to each (?P<first>[^.]+?) and "
    rf"(?P<m>{COUNT}) damage to you and each (?P<second>[^.]+?)\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s10")
def _parse_damage_group_and_you_and_group_text(text: str) -> TargetedClause | None:
    """`_DAMAGE_GROUP_AND_YOU_AND_GROUP_RE`'s shape.

    CR 608.2h: both amounts are fixed once; CR 120.2b: one source; CR 120.4:
    every recipient is set before any damage lands, so a creature in both
    groups takes both amounts.
    """
    match = _DAMAGE_GROUP_AND_YOU_AND_GROUP_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    first = parse_count(match.group("n"))
    second = parse_count(match.group("m"))
    first_group = _parse_damage_group_phrase(match.group("first"))
    second_group = _parse_damage_group_phrase(match.group("second"))
    if first is None or second is None or first_group is None or second_group is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = _resolving_source(game, stack_object)
        controller = game.controller_of(stack_object)
        board = list(game.battlefield)
        deals: list[tuple[CardState | None, Any, int]] = [
            (source, permanent, first)
            for permanent in board
            if first_group(game, permanent, controller.username)
        ]
        deals.append((source, controller, second))
        deals.extend(
            (source, permanent, second)
            for permanent in board
            if second_group(game, permanent, controller.username)
        )
        _deal_all(game, deals)

    return effect


#: "Each <group> deals damage to itself equal to its power." (Solar Blaze, The
#: Akroan War's chapter III) and "Target creature deals damage to itself equal
#: to its power." (Justice Strike, Kiku's Shadow) - every named permanent is
#: its own source and its own recipient.
_EACH_DEALS_DAMAGE_TO_ITSELF_RE = re.compile(
    r"^each (?P<group>[^.]+?) deals damage to itself equal to its power\.?$", re.IGNORECASE
)
_TARGET_DEALS_DAMAGE_TO_ITSELF_RE = re.compile(
    r"^(?P<phrase>target [^.]+?) deals damage to itself equal to its power\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s9")
@SPELL_TEXT.rung("s10")
def _parse_damage_to_itself_equal_to_its_power_text(text: str) -> TargetedClause | None:
    """The two "deals damage to itself equal to its power" shapes above.

    CR 608.2h: the amount is the power as it resolves. A group deals all its
    damage as one event batch (CR 120.4), so a creature killed by its own
    damage does not change what the others deal.
    """
    whole = _strip_non_effect_preamble(text).strip()
    each = _EACH_DEALS_DAMAGE_TO_ITSELF_RE.fullmatch(whole)
    if each is not None:
        predicate = _parse_damage_group_phrase(each.group("group"))
        if predicate is None:
            return None

        def group_effect(game: "Game", stack_object: "StackObject") -> None:
            controller = game.controller_of(stack_object).username
            members = [
                permanent
                for permanent in list(game.battlefield)
                if predicate(game, permanent, controller)
            ]
            _deal_all(game, [(member, member, game.power_of(member) or 0) for member in members])

        return group_effect
    targeted = _TARGET_DEALS_DAMAGE_TO_ITSELF_RE.fullmatch(whole)
    if targeted is None or not _targets_understood(targeted.group("phrase"), count_agnostic=False):
        return None

    def target_effect(game: "Game", stack_object: "StackObject") -> None:
        _deal_all(
            game,
            [
                (target, target, game.power_of(target) or 0)
                for target in game.resolve_targets(stack_object)
                if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
            ],
        )

    return target_effect


#: "Each <group> deals N damage to its controller" (Aura Barbs, Rakdos Charm)
#: and "each <group> attached to a <host> deals N damage to the <host> it's
#: attached to" (Aura Barbs) - the permanents of the group are the sources;
#: their controllers, or what they are attached to, the recipients.
_EACH_DEALS_TO_ITS_CONTROLLER_RE = re.compile(
    rf"^each (?P<group>[^.,]+?) deals (?P<n>{COUNT}) damage to its controller$", re.IGNORECASE
)
_EACH_ATTACHED_DEALS_TO_HOST_RE = re.compile(
    rf"^each (?P<group>[^.,]+?) attached to an? (?P<host>creature|permanent|land|artifact) "
    rf"deals (?P<n>{COUNT}) damage to the (?P=host) it(?:'|’)s attached to$",
    re.IGNORECASE,
)
_THEN_SEPARATOR_RE = re.compile(r",\s*then\s+|\.\s+(?:then\s+)?", re.IGNORECASE)


@ABILITY_TEXT.rung("s9")
@SPELL_TEXT.rung("s10")
def _parse_damage_each_to_its_controller_or_host_text(text: str) -> TargetedClause | None:
    """One or more of the two shapes above, run in printed order (CR 608.2c).

    The groups are re-read off the board for each part, so an Aura the first
    part's damage already sent to the graveyard (its enchanted creature died to
    an earlier instruction) is not there for the next - nothing is cached
    across parts.
    """
    if "damage to" not in text.lower():  # both shapes print it
        return None
    whole = _strip_non_effect_preamble(text).strip().rstrip(".")
    steps: list[tuple[Callable[..., None], GroupPredicate, int, str | None]] = []
    for sentence in _THEN_SEPARATOR_RE.split(whole):
        sentence = sentence.strip()
        if not sentence:
            continue
        to_controller = _EACH_DEALS_TO_ITS_CONTROLLER_RE.fullmatch(sentence)
        attached = _EACH_ATTACHED_DEALS_TO_HOST_RE.fullmatch(sentence)
        if to_controller is not None:
            predicate = _parse_damage_group_phrase(to_controller.group("group"))
            amount = parse_count(to_controller.group("n"))
            host = None
        elif attached is not None:
            predicate = _parse_damage_group_phrase(attached.group("group"))
            amount = parse_count(attached.group("n"))
            host = attached.group("host").lower()
        else:
            return None
        if predicate is None or amount is None:
            return None
        steps.append(
            (_deal_to_controller if host is None else _deal_to_host, predicate, amount, host)
        )
    if not steps:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        for deal, predicate, amount, host in steps:
            deal(game, controller, predicate, amount, host)

    return effect


def _deal_to_controller(
    game: "Game", controller: str, predicate: GroupPredicate, amount: int, host: str | None
) -> None:
    sources = [p for p in list(game.battlefield) if predicate(game, p, controller)]
    _deal_all(game, [(source, game.controller_of(source), amount) for source in sources])


def _deal_to_host(
    game: "Game", controller: str, predicate: GroupPredicate, amount: int, host: str | None
) -> None:
    deals: list[tuple[CardState | None, Any, int]] = []
    for source in list(game.battlefield):
        if not predicate(game, source, controller) or source.attached_to is None:
            continue
        attached = game.find_by_id(source.attached_to)
        if not isinstance(attached, CardState) or attached.zone is not Zone.BATTLEFIELD:
            continue
        if host != "permanent" and Type(host) not in game.characteristics_of(attached).types:
            continue
        deals.append((source, attached, amount))
    _deal_all(game, deals)


#: "<Name> deals 1 damage to any target, 2 damage to another target, and 3
#: damage to a third target." (Cone of Flame) and "... 2 damage to target
#: creature, 3 damage to another target creature, and 4 damage to a third
#: target creature." (Serpentine Spike): a different fixed amount for each of
#: several distinct targets, in the order the targets were announced.
_MULTI_TARGET_DAMAGE_SPLIT_RE = re.compile(rf",\s*(?:and\s+)?|\s+and\s+(?={COUNT} damage to )")
_MULTI_TARGET_DAMAGE_ITEM_RE = re.compile(
    rf"^(?P<n>{COUNT}) damage to (?P<phrase>(?:any|another|a (?:second|third|fourth)) target"
    r"(?: [a-z ]+)?|target [a-z ]+)$",
    re.IGNORECASE,
)
_MULTI_TARGET_DAMAGE_RE = re.compile(r"^.*?\bdeals? (?P<items>\S.*)$", re.IGNORECASE)


@SPELL_TEXT.rung("s10")
def _parse_damage_amount_to_each_of_several_targets_text(text: str) -> TargetedClause | None:
    """`_MULTI_TARGET_DAMAGE_RE`'s shape - only when at least one item names
    "another"/"a second/third" target, the CR 115.3 distinct-target idiom (the
    plain "N damage to target X and M damage to target Y" is not this rung's).

    CR 608.2b: a target that is illegal on resolution takes nothing and the
    rest still do. Damage is dealt in printed order (CR 608.2c) by the one
    source, the spell (CR 120.2b).
    """
    match = _MULTI_TARGET_DAMAGE_RE.fullmatch(_strip_non_effect_preamble(text).strip().rstrip("."))
    if match is None:
        return None
    items = _MULTI_TARGET_DAMAGE_SPLIT_RE.split(match.group("items"))
    amounts: list[int] = []
    distinct = False
    for item in items:
        parsed = _MULTI_TARGET_DAMAGE_ITEM_RE.fullmatch(item.strip())
        if parsed is None:
            return None
        amount = parse_count(parsed.group("n"))
        if amount is None:
            return None
        amounts.append(amount)
        distinct = distinct or not parsed.group("phrase").lower().startswith(("any ", "target "))
    if len(amounts) < 2 or not distinct:
        return None
    profile = profile_for_text(", ".join(items))
    if (
        not profile.understood
        or len(profile.requirements) != len(amounts)
        or any(r.count != 1 or r.minimum != 1 or r.unbounded for r in profile.requirements)
    ):
        return None

    def effect(game: "Game", spell: "StackObject") -> None:
        source = _resolving_source(game, spell)
        refs = list(spell.targets)
        if len(refs) != len(amounts):
            return
        for ref, amount in zip(refs, amounts, strict=True):
            victim = game.legal_target(spell, ref)
            if victim is None or isinstance(victim, AbilityOnStack):
                continue
            _deal_all(game, [(source, victim, amount)])

    return effect


#: "<Name> deals N damage to target <player|opponent|planeswalker|creature>
#: and M damage to each [other] <group> <that target's controller controls>."
#: (Chandra's Fury, Radiating Lightning, Fear, Fire, Foes!), optionally led by
#: "Damage can't be prevented this turn." (CR 615.12). The group is read off
#: the target's controller as the spell resolves; "other" leaves the target
#: itself out of it.
_DAMAGE_TARGET_AND_GROUP_RE = re.compile(
    r"^(?P<ban>damage can(?:'|’)?t be prevented this turn\.\s*)?"
    rf".*?\bdeals? (?P<n>{COUNT}) damage to "
    r"(?P<phrase>target (?:player|opponent)(?: or planeswalker)?|target creature) and "
    rf"(?P<m>{COUNT}) damage to each (?P<other>other )?"
    r"(?P<groups>[a-z]+(?:\s+and\s+[a-z]+)*) "
    r"(?:they control|that player controls|with the same controller"
    r"|that (?:creature|planeswalker|player or that planeswalker)(?:'|’)s controller controls)"
    r"\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
@SPELL_TEXT.rung("s10")
def _parse_damage_target_and_group_of_its_controller_text(text: str) -> TargetedClause | None:
    """`_DAMAGE_TARGET_AND_GROUP_RE`'s shape.

    CR 608.2b: the target is rechecked as this resolves; with its one target
    illegal the spell does not resolve at all, so nothing - the group
    included - is dealt damage. The amounts are fixed once (CR 608.2h) and
    dealt to the target first, then to the group, all by the one source.
    """
    match = _DAMAGE_TARGET_AND_GROUP_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    phrase = match.group("phrase")
    if not _targets_understood(phrase, battlefield_only=False, allow_player_targets=True):
        return None
    first = parse_count(match.group("n"))
    second = parse_count(match.group("m"))
    if first is None or second is None:
        return None
    types: set[Type] = set()
    for word in re.split(r"\s+and\s+", match.group("groups")):
        card_type = _singular_card_type(word.strip())
        if card_type is None:
            return None
        types.add(card_type)
    excludes_target = match.group("other") is not None
    unpreventable = match.group("ban") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = _resolving_source(game, stack_object)
        targets = game.resolve_targets(stack_object)
        if not targets:
            return  # CR 608.2b
        target = targets[0]
        if isinstance(target, CardState):
            if target.zone is not Zone.BATTLEFIELD:
                return
            owner = game.controller_of(target).username
        else:
            owner = target.username
        if unpreventable:
            _record_damage_cant_be_prevented(game, stack_object)
        board = game.computed_board()
        recipients = [
            permanent
            for permanent in list(game.battlefield)
            if game.controller_of(permanent).username == owner
            and types & set(board.of(permanent).types)
            and not (excludes_target and permanent.id == getattr(target, "id", None))
        ]
        deals: list[tuple[CardState | None, Any, int]] = [(source, target, first)]
        deals.extend((source, permanent, second) for permanent in recipients)
        _deal_all(game, deals)

    return effect


def _record_damage_cant_be_prevented(game: "Game", stack_object: "StackObject") -> None:
    """CR 615.12: the "Damage can't be prevented this turn." sentence, applied
    exactly as `_parse_turn_rules_ban_clause` records it for any spell."""
    _parse_turn_rules_ban_clause(
        "Damage can't be prevented this turn", for_spell=isinstance(stack_object, CardState)
    )(game, stack_object)  # type: ignore[misc]


# --------------------------------------------------------------------------
# Lyra, Tolarian Archangel's own "Until end of turn, whenever [self] deals
# combat damage to a player, draw N cards" granted delayed trigger
# --------------------------------------------------------------------------
#
# "{3}{U}{U}: Until end of turn, whenever Lyra deals combat damage to a
# player, draw two cards." CR 603.7a: activating this creates a *delayed*
# triggered ability watching `TriggerEvent.DEALS_DAMAGE` (the same event an
# ordinary printed "Whenever this creature deals combat damage to a player"
# trigger already watches, unchanged by this stream's own recipient-side
# work on that same event) for the rest of the turn. `DelayedTrigger.matches`
# has no string condition to read "combat"/"to a player" off the way the
# printed-ability matcher does, so `combat_only`/`to_player_only` are the
# purpose-built filter fields this pattern needs, alongside `subject_id`
# pinning it to Lyra herself (CR 603.7c).
#
# The "who" is read loosely rather than checked against the card's own
# name (`activated_effect_for`'s own dispatch chain never receives
# `card_name`, only `effect_text`) - every printing of this exact template
# names the granting permanent itself, the only sensible reading of a
# self-granted delayed trigger, so `ability.source_id` is used directly
# without re-deriving who was named. A negative lookahead rules out the
# differently shaped, non-self "a/another creature you control deals combat
# damage to a player" template (Subira, Tulzidi Caravanner's own printing)
# so this parser does not silently mis-scope that one.

_UNTIL_END_OF_TURN_SELF_COMBAT_DAMAGE_DRAW_RE = re.compile(
    r"^Until end of turn, whenever (?!a |an |another |target |each |you )"
    r"(?:this (?:creature|permanent)|[A-Z][\w'-]*(?: [A-Z][\w'-]*)*) "
    r"deals combat damage to a player, draw (?P<count>[a-z]+|\d+) cards?\.?$"
)


@ABILITY_TEXT.rung("s20", before=["tokens._parse_created_trigger_ability_text"])
def _parse_until_end_of_turn_self_combat_damage_draw_clause(text: str) -> AbilityEffect | None:
    match = _UNTIL_END_OF_TURN_SELF_COMBAT_DAMAGE_DRAW_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    count = parse_count(match.group("count"))
    if count is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=match.group(0),
                event=TriggerEvent.DEALS_DAMAGE,
                controller=controller.username,
                source_id=source_id,
                source_name=source_name,
                subject_id=source_id,
                combat_only=True,
                to_player_only=True,
                remaining=None,
                expires_end_of_turn=True,
                effect=DrawACardForController(count=count),
            )
        )

    return effect


# --------------------------------------------------------------------------
# Airbend (CR 701.65a)
# --------------------------------------------------------------------------
#
# The same shape as earthbend below: a CR 701 keyword *action*, embedded in
# some other ability's effect text (Aang, Swift Savior's "When Aang enters,
# airbend up to one other target creature or spell."), so it is written here
# rather than in `machines/keywords.py`. `machines/keywords.executes` already
# knows the word, so the pool sweeper does not report it as silently ignored.
#
# CR 701.65a: "Certain spells and abilities instruct a player to airbend one or
# more permanents and/or spells. To do so, that player exiles those objects.
# For each card exiled this way, for as long as it remains exiled, its owner
# may cast it for {2} rather than its mana cost."
#
# Two halves, and only the first is here. The exile is this clause. The {2}
# permission is `machines/casting.marker_cast_options`, read back off the pile
# the card landed in (CR 406.4) rather than off anything printed on it - which
# is the whole reason `ExileMarker.AIRBENT` exists.
#
# The annotation goes on **cards only**. CR 701.65a says "for each *card*
# exiled this way", and a token is not a card (CR 111.6: "A token
# isn't a card"), so an airbent token receives no permission - and
# never could use one anyway, because CR 111.7 / CR 704.5d have it cease to
# exist as a state-based action the moment it is anywhere but the battlefield,
# which is before any player next receives priority (CR 704.3).
#
# CR 701.65b: "An ability that triggers whenever a player airbends triggers
# when that player exiles one or more objects as a result of an instruction to
# airbend." `airbend` raises `ExtraTriggerEvent.AIRBENDS` once per instruction
# (never per object) and records the "airbent" turn fact Avatar Aang's "if
# you've done all four this turn" reads - both only when something actually
# reached exile, since exiling nothing is not "one or more objects". The
# ordinary battlefield-departure events `Game.exile_permanent` raises are
# unaffected.

#: "Airbend up to one other target creature or spell.", "airbend any number of
#: other target nonland permanents you control.", "Airbend target nonland
#: permanent." - the airbend instruction, whatever its count. The count, the
#: "other" and the controller are already enforced by `machines/targeting.py`
#: off the same printed words (CR 107.1c's "any number" included), so nothing
#: here has to re-read them; this only has to recognise that the instruction
#: *is* an airbend.
_AIRBEND_RE = re.compile(
    r"^airbend (?:up to (?:\w+|\d+) |any number of |(?:\w+|\d+) (?=(?:other |another )?target))?"
    r"(?:other |another )?target\b.*$",
    re.IGNORECASE,
)


def airbend(game: "Game", objects: list[CardState], player: str | None = None) -> None:
    """CR 701.65a's exile, plus CR 406.4's note on each *card* that lands.

    One instruction, so `Game.exile_cards` rather than a loop of
    `exile_permanent` - CR 603.2c's "one event containing multiple
    occurrences" is the difference, and it is what a "whenever one or more
    cards leave your graveyard" ability would read.

    An object the move refused (CR 111.8's token that has already left the
    battlefield) never reaches exile, so it is never annotated: the check is on
    where the object actually ended up, not on what was asked for.

    `player` is who airbent (the instruction's controller) - CR 701.65b's
    "that player" - and `None` only for a caller with no player to name, which
    then raises no airbend event.
    """
    exiled_any = False
    for exiled in game.exile_cards(objects):
        if exiled.zone is not Zone.EXILE:
            continue
        exiled_any = True
        if is_token(exiled):
            continue
        annotate_exile(exiled, ExileMarker.AIRBENT, exiled.owner, game)
    if player is None or not exiled_any:
        return
    _record_bending(game, "airbent", ExtraTriggerEvent.AIRBENDS, player)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_airbend_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Airbend ... target ..." - see `_AIRBEND_RE` and the section note.

    Reads only the targets the spell or ability already chose (CR 601.2c /
    603.3d ran long before this resolves), rechecked by `Game.resolve_targets`
    for CR 608.2b. "Up to one" and "any number of" (CR 107.1c) both allow an
    announcement of none, which is legal and simply does nothing - that falls
    out of the empty list rather than needing a case.
    """
    if _AIRBEND_RE.fullmatch(" ".join(clause.strip().rstrip(".").split())) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targets = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
        ]
        if not targets:
            return
        airbend(game, targets, game.controller_of(stack_object).username)

    return effect


# --------------------------------------------------------------------------
# Earthbend (CR 701.66a)
# --------------------------------------------------------------------------
#
# "Earthbend N" is a CR 701 keyword *action*, not a CR 702 keyword ability, so
# it is written out here rather than in `machines/keywords.py` - it is never
# the whole of an ability the way cycling or equip are; it is embedded in
# another ability's effect text (Badgermole Cub's "When this creature enters,
# earthbend 1."). `machines/keywords.executes` is still told about it, so the
# pool sweeper does not report it as silently ignored.
#
# Not keyed on reminder text: Bumi, Unleashed prints "earthbend 4." with no
# reminder at all, and this module's callers already strip reminder text
# before a clause ever reaches here.

#: "Earthbend N." - never printed with the word "target" (that is CR 701.66a's
#: own wording, not the card's); `targeting.profile_for_text` is taught the
#: keyword's implied target so this only has to read the number.
_EARTHBEND_RE = re.compile(
    rf"^earthbend {count_pattern('n', x=True)}{where_x_pattern()}$", re.IGNORECASE
)


def earthbend(
    game: "Game",
    land: CardState,
    amount: int,
    controller: str,
    source_id: UUID | None,
    source_name: str,
) -> None:
    """CR 701.66a: "Earthbend N" means "Target land you control becomes a 0/0
    land creature with haste in addition to its other types. Put N +1/+1
    counters on it. When that land dies or is put into exile, return it to
    the battlefield tapped under your control."

    Three simultaneous changes, all created now (CR 608.2c has no notion of
    running half an instruction) and all scoped to *this* incarnation of
    `land` (`layers.only_this_incarnation`) rather than its bare id:

    - Layer 4: the creature type is *added* (CR 205.1b's "in addition to its
      other types") with `layers.add_type` - never `layers.set_basic_land_type`,
      which is CR 305.7's "sets a land's subtype" path and would strip the
      land's own mana ability along with its old types.
    - Sublayer 7b: power and toughness are *set* to 0/0 (CR 613.4b) with
      `layers.set_power_toughness`. The `amount` +1/+1 counters that follow
      land in sublayer 7c (CR 613.4c) through `Game.add_counters` instead of a
      second continuous effect - `layers._counter_effects` already turns real
      counters into that sublayer's effect, and CR 613.4 fixes 7b-before-7c
      regardless of timestamp, so a freshly set 0/0 plus one counter is
      unconditionally a 1/1. CR 704.3/117.5 only check state-based actions
      when a player would receive priority, never mid-resolution, so the land
      is never briefly a legal-to-die 0/0 between the two.
    - Layer 6: haste, granted with the ordinary `layers.grant_ability`.

    `Duration.INDEFINITE` (CR 611.2a) is correct - earthbend states no
    end - and is exactly why the scoping matters: `ContinuousEffects.
    end_the_turn` never removes an `INDEFINITE` effect, so one scoped only to
    `land.id` would still match after CR 603.7's own delayed return sent this
    same id back as a plain, unanimated land (CR 400.7's "new object"),
    silently re-animating it for free and forever.

    The delayed return is created twice, once per half of "dies or is put
    into exile" - `TriggerEvent.DIES` and `TriggerEvent.LEAVES_BATTLEFIELD_
    TO_EXILE` are two different events, so CR 603.7a's one ability needs one
    `DelayedTrigger` per event it watches. Whichever fires first consumes its
    own one-shot `remaining` (CR 603.7b) and returns the land; the other is
    dropped by `machines/delayed.py`'s shared `_drop_sibling_triggers` rather than left to spend
    itself uselessly (harmlessly, since its `expected_stamp` can never match
    again once the land has moved on - but tidiness, not correctness, is why
    it is dropped). Both watch `still_affects` at *resolution* (CR 603.7c),
    which is what stops a land that was, say, bounced to hand instead from
    being affected at all.
    """
    stamp = land.zone_change_stamp
    effects = game.continuous_effects
    for description, layer, sublayer, modification in (
        (
            f"earthbend: {land.name} becomes a land creature",
            Layer.TYPE,
            None,
            add_type(Type.CREATURE),
        ),
        (
            f"earthbend: {land.name} is 0/0",
            Layer.POWER_TOUGHNESS,
            Sublayer.SET,
            set_power_toughness(0, 0),
        ),
        (f"earthbend: {land.name} has haste", Layer.ABILITY, None, grant_ability("Haste")),
    ):
        effects.add(
            ContinuousEffect(
                description=description,
                layer=layer,
                sublayer=sublayer,
                timestamp=effects.tick(),
                duration=Duration.INDEFINITE,
                selector=only_this_incarnation(land, stamp),
                modification=modification,
            )
        )
    game.add_counters(land, Counter.PLUS_ONE, amount)

    siblings: list[DelayedTrigger] = []
    for event, zone in (
        (TriggerEvent.DIES, Zone.GRAVEYARD),
        (TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE, Zone.EXILE),
    ):
        siblings.append(
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=(
                        "When that land dies or is put into exile, return it "
                        "to the battlefield tapped under your control."
                    ),
                    event=event,
                    controller=controller,
                    source_id=source_id,
                    source_name=source_name,
                    subject_id=land.id,
                    expected_zone=zone,
                    # No `expected_stamp` here, unlike the blink idiom's use of
                    # this same field: those triggers are created *after* the
                    # object has already arrived in `expected_zone`, so the
                    # stamp they capture is that arrival's own stamp, and it
                    # only changes if the object leaves and comes back before
                    # the trigger resolves (CR 603.7c's parenthetical). This
                    # trigger is created *before* the land has died or been
                    # exiled - CR 603.7a fires it the moment earthbend
                    # resolves - so `land.zone_change_stamp` right now is its
                    # *battlefield* incarnation's stamp, and CR 400.7 always
                    # reassigns a new one the instant it actually dies or is
                    # exiled. Capturing it here would make `still_affects`
                    # compare against a stamp the object can never wear again,
                    # so the return would never fire at all. `expected_zone`
                    # plus `subject_id` alone already give CR 603.7c's real
                    # guarantee for this shape: if something else moves the
                    # land out of that zone again first, `still_affects`
                    # correctly stops affecting it.
                    effect=return_earthbent_land,
                )
            )
        )
    for trigger in siblings:
        trigger.sibling_ids = tuple(other.id for other in siblings if other is not trigger)
    # CR 701.66b: "An ability that triggers whenever a player earthbends
    # triggers when the delayed triggered ability described in rule 701.66a is
    # created" - just now, above.
    _record_bending(game, "earthbent", ExtraTriggerEvent.EARTHBENDS, controller)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_earthbend_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Earthbend N." or "Earthbend X, where X is `<expr>`." - the whole of
    a spell's or an ability's effect text once any trigger condition ("When
    this creature enters, ") has been split off.

    Reads only the target the *stack object* chose (CR 601.2c/603.3d already
    ran by the time this resolves, using the restriction `targeting.profile_
    for_text` supplies for any text containing the word "earthbend") - there
    is nothing left for this clause to parse out of the card's own words
    beyond the number. Rockalanche's own "Earthbend X, where X is the number
    of Forests you control" - printed directly on a sorcery, unlike
    Badgermole Cub's ability - is why this reads both `for_spell=True` and
    `for_spell=False` alike: CR 701.66a names no difference between the two,
    and `earthbend` itself only wants a controller, a source id and a source
    name, all of which a resolving `CardState` spell carries exactly as an
    `AbilityOnStack` does. X is CR 107.3f's, read through `_fixed_or_where_x_
    amount` exactly as `_parse_put_counters_equal_to_clause`'s "equal to
    `<expr>`" tail is; an "X" this clause cannot evaluate is refused rather
    than treated as zero, so the whole instruction goes unread instead of
    earthbending for nothing (CR 608.2c).
    """
    match = _EARTHBEND_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    reader = _fixed_or_where_x_amount(match.group("n"), match.group("where_x"))
    if reader is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targets = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
        ]
        if not targets:
            return  # CR 608.2b: no legal target left, earthbend does nothing.
        if isinstance(stack_object, AbilityOnStack):
            controller = stack_object.controller
            source_id = stack_object.source_id
            source_name = stack_object.source_name
            x_value = stack_object.x_value
        else:
            controller = game.controller_of(stack_object).username
            source_id = stack_object.id
            source_name = stack_object.name
            x_value = 0
        amount = reader(game, controller, targets[0], x_value)
        earthbend(game, targets[0], amount, controller, source_id, source_name)

    return effect


def empower_jace(
    game: "Game",
    amount: int,
    controller: str,
    source_id: "UUID | None",
    source_name: str,
) -> None:
    """CR 701.71a's whole instruction - see the section note above for the
    three steps.

    `amount <= 0` (a "where X is ..." expression that evaluates to 0, or
    lower) still runs the first two steps - CR 701.71a's "if you don't
    control one, first create" is unconditional on N - but `Game.add_counters`
    already treats a non-positive amount as a no-op (CR 107.1b), so nothing
    further is needed to make "empower Jace 0" legal and inert.
    """
    board = game.computed_board()

    def jace_tokens() -> list[CardState]:
        return [
            permanent
            for permanent in game.battlefield
            if is_token(permanent)
            and board.of(permanent).controller == controller
            and Type.PLANESWALKER in board.of(permanent).types
            and any(subtype.lower() == "jace" for subtype in board.of(permanent).subtypes)
        ]

    candidates = jace_tokens()
    if not candidates:
        candidates = create_tokens(game, PREDEFINED["Jace"], controller)
    if len(candidates) == 1:
        chosen = candidates[0]
    else:
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller,
                prompt="choose a Jace planeswalker token to put loyalty counters on",
                source=source_name,
                source_id=source_id_of(source_id),
                amount=1,
                cards=tuple(candidate.id for candidate in candidates),
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {candidate.id: candidate for candidate in candidates}
        chosen = by_id[chosen_ids[0]]
    game.add_counters(chosen, Counter.LOYALTY, amount)


#: "This creature deals N damage to that spell's controller." - Bonecrusher
#: Giant's own "becomes the target of a spell" trigger (CR 702.21a's own
#: event, `TriggerEvent.BECOMES_TARGET`, generic and not ward-specific -
#: `Casting._emit_becomes_target` raises it for *any* spell that targets a
#: permanent). "That spell" here is `GameEvent.targeted_by` (CR 702.21a: "the
#: spell ... that's targeting" the subject), not `event.subject_id` - the
#: subject of a BECOMES_TARGET event is the permanent that got targeted
#: (Bonecrusher Giant itself), and the spell that did the targeting is a
#: second, separate object the event carries under its own field. Reading
#: `event.subject_id` here, the way `_parse_counter_that_spell_clause` reads
#: it for a *CAST_SPELL* condition's "that spell", would ask who controls
#: Bonecrusher Giant instead of who cast the spell that targeted it.
_DAMAGE_TO_THAT_SPELLS_CONTROLLER_RE = re.compile(
    r"^this (?:creature|permanent) deals (?P<n>\d+) damage to that spell'?s controller\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s35")
def _parse_damage_to_that_spells_controller_clause(text: str) -> AbilityEffect | None:
    """`_DAMAGE_TO_THAT_SPELLS_CONTROLLER_RE`'s shape - Bonecrusher Giant's
    whole trigger (CR 120.1, 120.3a: damage to a player)."""
    match = _DAMAGE_TO_THAT_SPELLS_CONTROLLER_RE.fullmatch(text.strip())
    if match is None:
        return None
    amount = int(match.group("n"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.targeted_by is None:
            return
        spell = game.find_by_id(event.targeted_by)
        if spell is None:
            return
        controller = game.controller_of(spell)
        game.deal_damage(controller, amount, source=ability.source_or_last_known(game))

    return effect


#: Master of Cruelties' own rider on the same trigger: "This creature
#: assigns no combat damage this combat." CR 700.7's "this creature" is the
#: ability's own source; the flag lasts only for the combat under way right
#: now (`CardState.assigns_no_combat_damage_this_combat`, cleared at the top
#: of the next `declare_attackers_step`, the way `exerted` is cleared at the
#: next untap), read by `machines.combat._assignment_power_of`.
_SELF_ASSIGNS_NO_COMBAT_DAMAGE_THIS_COMBAT_RE = re.compile(
    r"^this (?:creature|permanent) assigns no combat damage this combat\.?$", re.IGNORECASE
)


def _parse_self_assigns_no_combat_damage_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SELF_ASSIGNS_NO_COMBAT_DAMAGE_THIS_COMBAT_RE`'s shape. Ability-only:
    a spell is never itself a combat participant."""
    if for_spell:
        return None
    if _SELF_ASSIGNS_NO_COMBAT_DAMAGE_THIS_COMBAT_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        source = ability.source_or_last_known(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            source.assigns_no_combat_damage_this_combat = True

    return effect


#: "`<target X>` fights up to one other target `<Y>`." - The Super Hero Civil
#: War's chapter III ("Target creature you control fights up to one other
#: target creature."). Unlike `_TARGET_FIGHTS_TARGET_RE`, the two fighters
#: cannot be told apart by controller ("other" names no controller), so they
#: are read by announcement position: the first target is the first fighter.
#: CR 701.14b: if either is no longer a legal target, on the battlefield, or
#: a creature, neither fights; CR 115.6: "up to one" chose none, no fight.
_TARGET_FIGHTS_OTHER_TARGET_RE = re.compile(
    r"^(?P<first>target .+?) fights (?P<second>(?:up to one )?(?:other|another) target .+?)\.?$",
    re.IGNORECASE,
)


def _parse_target_fights_other_target_clause(
    text: str,
) -> Callable[["Game", "StackObject"], None] | None:
    """`_TARGET_FIGHTS_OTHER_TARGET_RE`'s shape, or `None`."""
    match = _TARGET_FIGHTS_OTHER_TARGET_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    if not _targets_understood(match.group("first").strip(), count_agnostic=True):
        return None
    if not _targets_understood(match.group("second").strip(), count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        announced = list(stack_object.targets)
        if len(announced) < 2:
            return  # CR 115.6: no second fighter chosen.
        legal = {
            target.id: target
            for target in game.resolve_card_targets(stack_object)
            if target.zone is Zone.BATTLEFIELD
        }
        first = legal.get(announced[0].card_id) if announced[0].is_card else None
        second = legal.get(announced[1].card_id) if announced[1].is_card else None
        if first is None or second is None or first.id == second.id:
            return  # CR 701.14b
        if not game.characteristics_of(first).is_creature:
            return  # CR 701.14b
        if not game.characteristics_of(second).is_creature:
            return  # CR 701.14b
        _fight(game, first, second)

    return effect


#: "until end of turn, creatures you control with toughness greater than
#: their power assign combat damage equal to their toughness rather than
#: their power." (The Kingpin of Crime's paid rider); "Until end of turn,
#: target creature you control assigns combat damage equal to its toughness
#: rather than its power." (Bill the Pony) - CR 510.1a's "equal to its power"
#: replaced for the group or target, for CR 611.2a's stated duration. The
#: group form modifies the rules of the game rather than any characteristic,
#: so it is not fixed when it begins (CR 611.2c): the live
#: `CreaturesControlledByWhereToughnessExceedsPower` selector judges each
#: creature as it assigns.
_UNTIL_EOT_ASSIGNS_TOUGHNESS_RE = re.compile(
    r"^until end of turn,\s*(?:(?P<group>creatures you control(?P<exceeds> with toughness "
    r"greater than their power)?) assign|(?P<target>target creature you control) assigns) "
    r"combat damage equal to (?:its|their) toughness rather than (?:its|their) power\.?$",
    re.IGNORECASE,
)


def _parse_until_eot_assigns_toughness(text: str) -> AbilityEffect | None:
    """`_UNTIL_EOT_ASSIGNS_TOUGHNESS_RE`'s shape, or `None`."""
    match = _UNTIL_EOT_ASSIGNS_TOUGHNESS_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    group = match.group("group") is not None
    exceeds = match.group("exceeds") is not None
    grant = grant_ability(combat_rules.ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        store = game.continuous_effects
        if group:
            store.add(
                ContinuousEffect(
                    description=f"{ability.source_name}: assigns combat damage equal to "
                    "toughness this turn",
                    layer=Layer.ABILITY,
                    timestamp=store.tick(),
                    duration=Duration.UNTIL_END_OF_TURN,
                    source_id=ability.source_id,
                    selector=(
                        CreaturesControlledByWhereToughnessExceedsPower(username=ability.controller)
                        if exceeds
                        else creatures_controlled_by(ability.controller)
                    ),
                    modification=grant,
                )
            )
            return
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            store.add(
                ContinuousEffect(
                    description=f"{target.name} assigns combat damage equal to its toughness",
                    layer=Layer.ABILITY,
                    timestamp=store.tick(),
                    duration=Duration.UNTIL_END_OF_TURN,
                    source_id=ability.source_id,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=grant,
                )
            )

    return effect


#: "Whenever `<this>` deals combat damage to a player, put up to one target
#: creature card from that player's graveyard onto the battlefield under your
#: control. It enters tapped and attacking that player." - Shark Shredder,
#: Killer Clone's own combat-damage trigger (CR 120.2a, CR 508.4). Read whole
#: for the same "tapped and attacking" bare-"and" reason
#: `_RETURN_TARGET_FROM_GRAVEYARD_TAPPED_AND_ATTACKING_RE`'s own merger
#: exists, plus a second sentence ("It enters ...") that reads a live pronoun
#: back to whatever the first sentence actually put onto the battlefield -
#: nothing a per-clause parser can carry across on its own.
_COMBAT_DAMAGE_REANIMATE_FROM_THAT_PLAYERS_GRAVEYARD_ATTACKING_RE = re.compile(
    r"^put up to one target creature card from that player'?s graveyard onto the "
    r"battlefield under your control\.\s*it enters tapped and attacking that player\.?$",
    re.IGNORECASE,
)


def _parse_combat_damage_reanimate_from_that_players_graveyard_attacking_clause(
    text: str,
) -> AbilityEffect | None:
    """`_COMBAT_DAMAGE_REANIMATE_FROM_THAT_PLAYERS_GRAVEYARD_ATTACKING_RE`'s
    shape.

    "That player" is the trigger event's own player (CR 120.2a: whoever the
    combat damage was dealt to), bound into the target restriction by
    `TargetingProfile.for_event_player`/`models.game._that_player_of` - both
    extended alongside this reader to recognise "that player's graveyard" as
    well as the "that player controls" phrasing they already read, since the
    restriction here is a graveyard **card**'s owner (CR 108.4a/109.4's
    fallback to owner for an object with no controller), not a permanent's
    controller.

    The reanimated card goes onto the battlefield tapped (CR 508.4's own
    "tapped and attacking" says nothing about *this* creature's controller
    being tapped by it, only that it is put onto the battlefield tapped) and
    already attacking the very player it was taken from - `TargetRef.coerce`
    accepts a plain username directly, so `event.player` is handed straight
    to `_put_onto_the_battlefield_attacking` with no lookup through combat.
    "Up to one" (CR 115.6) makes a decline, or an empty/creature-less
    graveyard, a legal answer that puts nothing onto the battlefield at all.
    """
    if (
        _COMBAT_DAMAGE_REANIMATE_FROM_THAT_PLAYERS_GRAVEYARD_ATTACKING_RE.fullmatch(
            " ".join(text.split())
        )
        is None
    ):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        from ...models.token import _put_onto_the_battlefield_attacking

        event = ability.event
        if event is None or event.player is None:
            return
        controller = game.controller_of(ability).username
        for target in game.resolve_card_targets(ability):
            if target.zone is not Zone.GRAVEYARD:
                continue
            permanent = game.put_onto_battlefield(target, controller, tapped=True)
            if permanent is None or permanent.zone is not Zone.BATTLEFIELD:
                continue
            _put_onto_the_battlefield_attacking(game, permanent, event.player)  # type: ignore[arg-type]

    return effect


#: "`<this>` deals `<n>` damage to any target and `<n2>` damage to you." -
#: Spicy Oatmeal Pizza's own enters trigger, printed after the CR 603.6a
#: "When this artifact enters," condition (already split off by the time this
#: reads it) - the subject there is a bare "it". Char's own printing carries
#: no condition at all and keeps its own literal name as the subject ("Char
#: deals ..."), CR 201.5's self-reference, so the subject is a generic
#: non-greedy wildcard here rather than a fixed "it" - the same convention
#: this file's own plain "deals `<n>` damage to target `<X>`" reader already
#: uses to read a literal self-name with no special case for it.
_ETB_DAMAGE_ANY_TARGET_AND_SELF_RE = re.compile(
    r"^.+? deals (?P<any_amount>" + COUNT + r") damage to any target and "
    r"(?P<self_amount>" + COUNT + r") damage to you\.?$",
    re.IGNORECASE,
)


def _parse_etb_damage_any_target_and_self_clause(
    text: str, *, for_spell: bool = False
) -> TargetedClause | None:
    """`_ETB_DAMAGE_ANY_TARGET_AND_SELF_RE`'s shape.

    Read whole rather than through `split_effect_clauses`'s bare-"and" cut,
    which would otherwise slice "damage to any target" from "3 damage to
    you" into two fragments - the second missing the verb ("deals") the first
    already carries, so no per-clause parser reads it back on its own.

    The source is read through `AbilityOnStack.source_or_last_known` (CR
    608.2h) for an ability; a spell just resolving is always its own current
    object (CR 608.2g), read the ordinary way every other spell-side clause
    in this file does.
    """
    match = _ETB_DAMAGE_ANY_TARGET_AND_SELF_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    any_amount = parse_count(match.group("any_amount"))
    self_amount = parse_count(match.group("self_amount"))
    if any_amount is None or self_amount is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = (
            stack_object if for_spell else stack_object.source_or_last_known(game)  # type: ignore[union-attr]
        )
        for target in game.resolve_targets(stack_object):
            game.deal_damage(target, any_amount, source=source)
        game.deal_damage(controller, self_amount, source=source)

    return effect


# --------------------------------------------------------------------------
# NW-01 T5: a named player's group, and riders on what was dealt damage
# --------------------------------------------------------------------------

#: CR 105.1's colour words, as a group qualifier ahead of the group: "each
#: white and/or blue creature that player controls" (Ember Gale).
_COLOR_WORDS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}
_COLORED_GROUP_RE = re.compile(
    r"^(?P<colors>(?:white|blue|black|red|green)"
    r"(?:(?:,\s*|\s+)(?:and/or\s+|or\s+|and\s+)?(?:white|blue|black|red|green))*)\s+(?P<group>.+)$",
    re.IGNORECASE,
)


def _parse_colored_group_phrase(phrase: str) -> GroupPredicate | None:
    """`_parse_damage_group_phrase`, with an optional leading colour list -
    "white and/or blue creature": a member of the group that is at least one
    of those colours (CR 105.2, computed per CR 613.5)."""
    match = _COLORED_GROUP_RE.fullmatch(phrase.strip())
    if match is None:
        return _parse_damage_group_phrase(phrase)
    colors = {
        _COLOR_WORDS[word.lower()]
        for word in re.findall(r"white|blue|black|red|green", match.group("colors"), re.I)
    }
    member = _parse_damage_group_phrase(match.group("group"))
    if member is None:
        return None

    def colored(game: "Game", permanent: CardState, controller: str) -> bool:
        if not member(game, permanent, controller):
            return False
        return bool(colors & set(game.characteristics_of(permanent).colors))

    return colored


#: "`<source>` deals N damage to each `<group>` {target player|target
#: opponent|that player} controls." - Aggravate's "each creature target
#: player controls", Ember Gale's "each white and/or blue creature that
#: player controls". No permanent is targeted (CR 115.10a): the player is,
#: and the group is that player's permanents as this resolves (CR 608.2h).
_DAMAGE_EACH_GROUP_NAMED_PLAYER_CONTROLS_RE = re.compile(
    rf"^.*\bdeals? (?P<n>{AMOUNT}) damage to each (?P<group>.+?) "
    r"(?:(?P<target>target (?:player|opponent)) controls|that player controls)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s1", for_spell=FORWARD, before=["dispatch._parse_targeted_clause"])
def _parse_damage_each_group_named_player_controls_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_DAMAGE_EACH_GROUP_NAMED_PLAYER_CONTROLS_RE`'s shape. Read ahead of
    the generic targeted clause, which would otherwise deal the damage to the
    player the sentence only uses to name a group. The recipients are
    snapshotted before any damage is dealt (CR 608.2f's simultaneity); a
    player target no longer legal names nobody and nothing is dealt (CR
    608.2b)."""
    text = " ".join(clause.split())
    if " damage to each " not in text.lower():
        return None
    match = _DAMAGE_EACH_GROUP_NAMED_PLAYER_CONTROLS_RE.fullmatch(text)
    if match is None:
        return None
    target_phrase = match.group("target")
    if target_phrase is None and not for_spell:
        # An ability's "that player" is whoever its trigger event names (Siege
        # Dragon's defending player), not a target this reader can read.
        return None
    if target_phrase is not None and not _targets_understood(
        target_phrase, battlefield_only=False, allow_player_targets=True
    ):
        return None
    amount_of = _resolve_multiplied_amount(match.group("n"), None, None)
    if amount_of is None:
        return None
    member = _parse_colored_group_phrase(match.group("group"))
    if member is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = _named_player_of(game, stack_object)
        if player is None:
            return
        source = (
            stack_object
            if isinstance(stack_object, CardState)
            else stack_object.source_or_last_known(game)
        )
        controller = game.controller_of(stack_object).username
        amount = max(amount_of(game, controller), 0)
        if amount <= 0:
            return
        recipients = [
            permanent
            for permanent in list(game.battlefield)
            if game.controller_of(permanent).username == player
            and member(game, permanent, controller)
        ]
        for permanent in recipients:
            if permanent.zone is Zone.BATTLEFIELD:
                game.deal_damage(permanent, amount, source=source)

    return effect


#: What a "dealt damage this way" rider sentence does to the objects and
#: players its own damage reached (CR 120.3: damage prevented is never
#: dealt, so a creature the damage did not reach is not one of them):
#:
#:   Aggravate         "Each creature dealt damage this way attacks this turn
#:                     if able." (CR 508.1d)
#:   Aurelia's Fury    "Tap each creature dealt damage this way. Players
#:                     dealt damage this way can't cast noncreature spells
#:                     this turn." (CR 701.26a, CR 601.3)
#:   Huatli, Warrior   "Creatures dealt damage this way can't block this
#:   Poet's -X         turn." (CR 509.1b)
_THIS_WAY_CREATURES = r"(?:each creature|creatures|a creature)"
_THIS_WAY_PLAYERS = r"(?:each player|players|a player)"
_THIS_WAY_ATTACKS_RE = re.compile(
    rf"^{_THIS_WAY_CREATURES} dealt damage this way attacks? this turn if able$", re.IGNORECASE
)
_THIS_WAY_CANT_BLOCK_RE = re.compile(
    rf"^{_THIS_WAY_CREATURES} dealt damage this way can(?:'|’)?t block this turn$",
    re.IGNORECASE,
)
_THIS_WAY_CANT_REGENERATE_RE = re.compile(
    rf"^{_THIS_WAY_CREATURES} dealt damage this way can(?:'|’)?t be regenerated this turn$",
    re.IGNORECASE,
)
_THIS_WAY_TAP_RE = re.compile(r"^tap each creature dealt damage this way$", re.IGNORECASE)
_THIS_WAY_CANT_CAST_RE = re.compile(
    rf"^{_THIS_WAY_PLAYERS} dealt damage this way can(?:'|’)?t cast "
    r"(?P<noncreature>noncreature )?spells this turn$",
    re.IGNORECASE,
)

#: (game, stack object, creatures dealt damage, players dealt damage)
_ThisWayRider = Callable[["Game", "StackObject", list[CardState], list[str]], None]


def _source_name_of(stack_object: "StackObject") -> str:
    return (
        stack_object.card.name if isinstance(stack_object, CardState) else stack_object.source_name
    )


def _grant_line_until_end_of_turn(
    game: "Game", stack_object: "StackObject", creatures: list[CardState], line: str
) -> None:
    store = continuous_effects(game)
    for creature in creatures:
        if creature.zone is not Zone.BATTLEFIELD:
            continue
        if not game.characteristics_of(creature).is_creature:
            continue
        store.add(
            ContinuousEffect(
                description=f"{_source_name_of(stack_object)}: {creature.name}: {line}",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=only_this_incarnation(creature, creature.zone_change_stamp),
                modification=grant_ability(line),
            )
        )


def _this_way_rider(sentence: str) -> _ThisWayRider | None:
    """One "dealt damage this way" rider sentence, or `None`."""
    text = " ".join(sentence.split()).rstrip(".")
    if _THIS_WAY_ATTACKS_RE.fullmatch(text):

        def attacks(
            game: "Game",
            stack_object: "StackObject",
            creatures: list[CardState],
            players: list[str],
        ) -> None:
            _grant_line_until_end_of_turn(
                game, stack_object, creatures, "This creature attacks each combat if able."
            )

        return attacks
    if _THIS_WAY_CANT_BLOCK_RE.fullmatch(text):

        def cant_block(
            game: "Game",
            stack_object: "StackObject",
            creatures: list[CardState],
            players: list[str],
        ) -> None:
            _grant_line_until_end_of_turn(
                game, stack_object, creatures, "This creature can't block."
            )

        return cant_block
    if _THIS_WAY_CANT_REGENERATE_RE.fullmatch(text):

        def cant_regenerate(
            game: "Game",
            stack_object: "StackObject",
            creatures: list[CardState],
            players: list[str],
        ) -> None:
            # CR 701.19c: regeneration shields are not applied (an unspent one
            # stays) - `replacement._regeneration_effects` reads this line.
            _grant_line_until_end_of_turn(game, stack_object, creatures, CANT_BE_REGENERATED_LINE)

        return cant_regenerate
    if _THIS_WAY_TAP_RE.fullmatch(text):

        def tap(
            game: "Game",
            stack_object: "StackObject",
            creatures: list[CardState],
            players: list[str],
        ) -> None:
            for creature in creatures:
                if creature.zone is Zone.BATTLEFIELD:
                    game.tap_permanent(creature)

        return tap
    if cant_cast := _THIS_WAY_CANT_CAST_RE.fullmatch(text):
        noncreature_only = cant_cast.group("noncreature") is not None

        def cant_cast_spells(
            game: "Game",
            stack_object: "StackObject",
            creatures: list[CardState],
            players: list[str],
        ) -> None:
            controller = game.controller_of(stack_object).username
            for player in players:
                game.casting_rule_effects.append(
                    create_targeted_cant_cast_restriction(
                        controller,
                        player,
                        _source_name_of(stack_object),
                        noncreature_only=noncreature_only,
                    )
                )

        return cant_cast_spells
    return None


def _split_this_way_riders(text: str) -> tuple[str, list[_ThisWayRider]] | None:
    """`text` as its leading instructions and the trailing "dealt damage this
    way" rider sentences, or `None` when it ends in none."""
    if "dealt damage this way" not in " ".join(text.split()).lower():
        return None
    sentences = _plain_resolution_sentences(" ".join(_strip_non_effect_preamble(text).split()))
    riders: list[_ThisWayRider] = []
    while len(sentences) > 1:
        rider = _this_way_rider(sentences[-1])
        if rider is None:
            break
        riders.insert(0, rider)
        sentences = sentences[:-1]
    if not riders:
        return None
    return " ".join(sentences), riders


def _dealt_damage_this_way_effect(
    rest: Callable[["Game", Any], None], riders: list[_ThisWayRider]
) -> Callable[["Game", Any], None]:
    def dealt_damage_this_way(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object
            if isinstance(stack_object, CardState)
            else stack_object.source_or_last_known(game)
        )
        start = len(game.damage_dealt_this_turn)
        rest(game, stack_object)
        creatures: list[CardState] = []
        players: list[str] = []
        for record in game.damage_dealt_this_turn[start:]:
            if source is None or record.source_id != source.id or record.amount <= 0:
                continue
            if record.recipient_id is not None:
                found = game.find_by_id(record.recipient_id)
                if isinstance(found, CardState) and found not in creatures:
                    creatures.append(found)
            elif record.recipient_player is not None and record.recipient_player not in players:
                players.append(record.recipient_player)
        for rider in riders:
            rider(game, stack_object, creatures, players)

    return dealt_damage_this_way


@SPELL_TEXT.rung("s6")
def _parse_dealt_damage_this_way_riders_spell(text: str) -> Effect | None:
    """A damage-dealing spell followed by "dealt damage this way" riders
    (`_this_way_rider`). The leading text is read by the ordinary spell
    dispatcher and run first (CR 608.2c); the riders act on exactly what its
    damage reached, read off `Game.damage_dealt_this_turn` by source (CR
    120.1). A leading text the dispatcher cannot read leaves this unread too
    (fail closed)."""
    split = _split_this_way_riders(text)
    if split is None:
        return None
    rest = _spell_effect_or_notice(split[0])
    if rest is None or _is_notice_only(rest):
        return None
    return _dealt_damage_this_way_effect(rest, split[1])


@ABILITY_TEXT.rung("s9")
def _parse_dealt_damage_this_way_riders_ability(text: str) -> AbilityEffect | None:
    """`_parse_dealt_damage_this_way_riders_spell` on a resolving ability -
    Huatli, Warrior Poet's -X."""
    split = _split_this_way_riders(text)
    if split is None:
        return None
    rest = _ability_effect_or_notice(split[0])
    if rest is None or _is_notice_only(rest):
        return None
    return _dealt_damage_this_way_effect(rest, split[1])


# --------------------------------------------------------------------------
# NW-02 T1: a target's controller as the second recipient, a spell's controller,
# and "<n> damage to any target and <m> damage to you" in a sequence
# --------------------------------------------------------------------------

#: "`<src>` deals N damage to target creature an opponent controls. Then `<src>`
#: deals M damage to each other creature that player controls if you control a
#: creature with power 4 or greater." (Flames of the Raze-Boar) - CR 608.2c's
#: order: the second instruction names "that player", the first target's
#: controller (read from last known information, CR 608.2h), and its "if" is
#: checked when that instruction is reached.
_DAMAGE_TARGET_THEN_EACH_OTHER_OF_ITS_CONTROLLER_RE = re.compile(
    rf"^(?P<subject>[^,.]+?) deals (?P<n>{COUNT}) damage to "
    r"(?P<phrase>target [^.]*?)\.\s*then (?:(?P=subject)|it) deals "
    rf"(?P<m>{COUNT}) damage to each other (?P<group>[a-z]+(?: [a-z]+)*?) "
    r"that player controls(?: if (?P<condition>[^.]+))?\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s18")
def _parse_damage_target_then_each_other_of_its_controller_text(
    effect_text: str,
) -> Effect | None:
    """`_DAMAGE_TARGET_THEN_EACH_OTHER_OF_ITS_CONTROLLER_RE`'s shape on a spell."""
    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    if ". then " not in whole.lower() or "that player controls" not in whole.lower():
        return None
    match = _DAMAGE_TARGET_THEN_EACH_OTHER_OF_ITS_CONTROLLER_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    first = parse_count(match.group("n"))
    second = parse_count(match.group("m"))
    group = _parse_damage_group_phrase(match.group("group"))
    condition_text = (match.group("condition") or "").strip() or None
    if first is None or second is None or group is None:
        return None
    if condition_text is not None and not _effect_condition_is_readable(condition_text):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        caster = game.controller_of(spell).username
        targets = [
            target
            for target in game.resolve_targets(spell)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return  # CR 608.2b: the only target is illegal
        target = targets[0]
        owner_of_group = game.controller_of(target).username  # CR 608.2h, before damage
        game.deal_damage(target, first, source=spell)
        if (
            condition_text is not None
            and game.condition_holds(caster, condition_text, spell) is not True
        ):
            return
        recipients = [
            permanent
            for permanent in list(game.battlefield)
            if permanent is not target
            and game.controller_of(permanent).username == owner_of_group
            and group(game, permanent, caster)
        ]
        for permanent in recipients:
            if permanent.zone is Zone.BATTLEFIELD:
                game.deal_damage(permanent, second, source=spell)

    return effect


#: "`<src>` deals damage to target spell's controller equal to that spell's
#: mana value." (Parallectric Feedback, Refuse) - the target is a spell on the
#: stack (CR 115.1), the damage goes to its controller, and with the spell gone
#: the target is illegal and nothing happens (CR 608.2b).
_DAMAGE_TO_TARGET_SPELLS_CONTROLLER_EQUAL_TO_MV_RE = re.compile(
    r"^(?P<subject>[^,.]+?) deals damage to target spell'?s controller equal to "
    r"that spell'?s mana value\.?$",
    re.IGNORECASE,
)


def _mana_value_on_the_stack(game: "Game", spell: CardState) -> int:
    """A spell's mana value as it sits on the stack (CR 202.3): the printed
    mana cost's value with each {X} counted as the value announced for it
    (CR 107.3a)."""
    from ...models.mana import ManaCost

    value = int(spell.mana_value)
    cost = spell.mana_cost
    if cost:
        x_count = ManaCost.parse(cost).x_count
        if x_count:
            value += x_count * game.cast_record(spell).x_value
    return value


@SPELL_TEXT.rung("s18")
def _parse_damage_to_target_spells_controller_text(effect_text: str) -> Effect | None:
    """`_DAMAGE_TO_TARGET_SPELLS_CONTROLLER_EQUAL_TO_MV_RE`'s shape."""
    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    if "spell's controller" not in whole.lower() and "spell\u2019s controller" not in whole.lower():
        return None
    if _DAMAGE_TO_TARGET_SPELLS_CONTROLLER_EQUAL_TO_MV_RE.fullmatch(whole) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        for reference in spell.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if not isinstance(target, CardState):
                continue  # CR 608.2b: it left the stack; the target is illegal
            amount = _mana_value_on_the_stack(game, target)
            game.deal_damage(game.controller_of(target), amount, source=spell)

    return effect


#: "`<src>` deals damage to each opponent equal to the number of cards that
#: player has drawn this turn." (Molten Psyche's metalcraft rider) - each
#: opponent's own total, read off `Game.cards_drawn_this_turn` when the damage
#: is dealt (CR 608.2h, CR 120.3a).
_DAMAGE_EACH_OPPONENT_EQUAL_TO_THEIR_DRAWS_RE = re.compile(
    r"^[^,.]+? deals damage to each opponent equal to the number of cards that player "
    r"has drawn this turn\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s35", for_spell=FORWARD)
def _parse_damage_each_opponent_equal_to_their_draws_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_DAMAGE_EACH_OPPONENT_EQUAL_TO_THEIR_DRAWS_RE`'s shape, spell or ability."""
    if "has drawn this turn" not in clause:
        return None
    if _DAMAGE_EACH_OPPONENT_EQUAL_TO_THEIR_DRAWS_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = _resolving_source(game, stack_object)
        controller = game.controller_of(stack_object).username
        for opponent in _opponents(game, controller):
            amount = game.cards_drawn_this_turn.get(opponent.username, 0)
            if amount > 0:
                game.deal_damage(opponent, amount, source=source)

    return effect


def _damage_any_target_and_you_then(
    effect_text: str, *, for_spell: bool, run_rest: Callable[[str], Any]
) -> Any:
    if "damage to any target and" not in effect_text.lower():
        return None
    head_and_rest = _split_first_sentence(effect_text)
    if head_and_rest is None:
        return None
    head_text, rest_text = head_and_rest
    if "damage to any target and" not in head_text.lower():
        return None
    head = _parse_etb_damage_any_target_and_self_clause(head_text, for_spell=for_spell)
    if head is None:
        return None
    rest = run_rest(rest_text)
    if rest is None or _is_notice_only(rest):
        return None
    return head, rest


def _split_first_sentence(effect_text: str) -> tuple[str, str] | None:
    sentences = _plain_resolution_sentences(
        " ".join(_strip_non_effect_preamble(effect_text).split())
    )
    if len(sentences) < 2:
        return None
    return sentences[0], " ".join(sentences[1:])


@SPELL_TEXT.rung("s18")
def _parse_damage_any_target_and_you_then_spell(effect_text: str) -> Effect | None:
    """ "`<src>` deals N damage to any target and M damage to you. `<rest>`"
    (Orcish Cannonade's "Draw a card.") - CR 608.2c's order: the paired damage
    first, then the following instructions, read by the ordinary dispatcher."""
    parts = _damage_any_target_and_you_then(
        effect_text, for_spell=True, run_rest=_spell_effect_or_notice
    )
    if parts is None:
        return None
    head, rest = parts

    def effect(game: "Game", spell: CardState) -> None:
        head(game, spell)
        rest(game, spell)

    return effect


@ABILITY_TEXT.rung("s42")
def _parse_damage_any_target_and_you_then_ability(effect_text: str) -> AbilityEffect | None:
    """`_parse_damage_any_target_and_you_then_spell` on a resolving ability."""
    parts = _damage_any_target_and_you_then(
        effect_text, for_spell=False, run_rest=_ability_effect_or_notice
    )
    if parts is None:
        return None
    head, rest = parts

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        head(game, ability)
        rest(game, ability)

    return effect


# --------------------------------------------------------------------------
# Group damage "equal to" an amount - NW03-T7
# --------------------------------------------------------------------------
#
# "<self> deals damage to each <group> equal to <amount>." (Skyreaping,
# Structural Assault): one amount, read once as the effect is applied (CR
# 608.2h), dealt by the one source to every member of the group (CR 120.1).
# A per-recipient amount ("equal to the number of cards in that player's
# hand") is a different shape and is not read here.

_DAMAGE_EACH_EQUAL_TO_RE = re.compile(
    r"^(?P<name>[^.]+?) deals? damage to each (?P<group>[^.]+?) equal to (?P<amount>[^.]+?)\.?$",
    re.IGNORECASE,
)
_PER_RECIPIENT_AMOUNT_RE = re.compile(
    r"\b(?:that player|that creature|its|their|them|it|those|each)\b", re.IGNORECASE
)
#: "the number of <type>s that were put into graveyards from the battlefield
#: this turn" (Structural Assault): `GraveyardArrival`s off the battlefield
#: this turn whose permanent had that card type (CR 400.6, CR 613.5).
_PUT_INTO_GRAVEYARDS_FROM_BATTLEFIELD_RE = re.compile(
    r"^the number of (?P<types>[a-z]+?)s? that were put into graveyards from the battlefield "
    r"this turn$",
    re.IGNORECASE,
)


def _put_into_graveyards_from_battlefield_count(
    phrase: str,
) -> "Callable[[Game, str], int] | None":
    match = _PUT_INTO_GRAVEYARDS_FROM_BATTLEFIELD_RE.fullmatch(phrase.strip())
    if match is None:
        return None
    card_type = _singular_card_type(match.group("types"))
    if card_type is None:
        return None

    def count(game: "Game", _controller: str) -> int:
        return sum(
            1
            for arrival in game.graveyard_arrivals_this_turn
            if arrival.origin_zone is Zone.BATTLEFIELD
            and card_type in (arrival.permanent_types or ())
        )

    return count


def _group_damage_amount(phrase: str) -> "AmountReader | None":
    """`amount_expression`'s reader for `phrase`, or the graveyard-history
    count above as an `AmountReader`."""
    reader = amount_expression(phrase)
    if reader is not None:
        return reader
    count = _put_into_graveyards_from_battlefield_count(phrase)
    if count is None:
        return None
    return lambda game, controller, _obj, _x: count(game, controller)


@MIXED_CLAUSE.rung("s35", after=["damage._parse_damage_each_filtered_clause"])
def _parse_damage_each_group_equal_to_clause(clause: str) -> TargetedClause | None:
    """`_DAMAGE_EACH_EQUAL_TO_RE`'s shape - see the banner above."""
    if " equal to " not in clause.lower() or "damage to each " not in clause.lower():
        return None
    match = _DAMAGE_EACH_EQUAL_TO_RE.fullmatch(" ".join(clause.strip().split()))
    if match is None:
        return None
    name = match.group("name").strip()
    if not _PAYOFF_SELF_RE.fullmatch(name) or _ANAPHOR_SUBJECT_RE.match(name):
        return None
    phrase = match.group("amount").strip()
    if _PER_RECIPIENT_AMOUNT_RE.search(phrase):
        return None
    amount_of = _group_damage_amount(phrase)
    if amount_of is None:
        return None
    group = match.group("group").strip()
    players: str | None = None
    predicate: GroupPredicate | None = None
    if group.lower() in ("opponent", "player"):
        players = group.lower()
    else:
        predicate = _parse_damage_group_phrase(group)
        if predicate is None:
            return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = _resolving_source(game, stack_object)
        if source is None:
            return
        controller = game.controller_of(stack_object).username
        amount = amount_of(game, controller, source, _announced_x(game, stack_object))
        if players == "opponent":
            recipients: list[Any] = list(_opponents(game, controller))
        elif players == "player":
            recipients = list(game.players_in_game)
        else:
            assert predicate is not None
            recipients = [
                permanent
                for permanent in list(game.battlefield)
                if predicate(game, permanent, controller)
            ]
        _deal_all(game, [(source, recipient, amount) for recipient in recipients])

    return effect


# --------------------------------------------------------------------------
# Group bite: "[Put a +1/+1 counter on target creature you control, then]
# each <group> you control deals damage equal to its power to <target>."
# (Signature Slam, Bartz and Boko) - NW03-T7
# --------------------------------------------------------------------------
#
# Each qualifying creature, read off the board as the damage is dealt, is its
# own source (CR 120.1) dealing its own power (CR 608.2h: all powers read
# before any lands). "modified" is CR 700.9's: a counter, an Equipment, or
# an Aura its controller controls - the creature that just got the counter
# included (CR 608.2c: in the order written). "other" leaves out the
# object whose text this is.

_GROUP_BITE_TARGET_RE = re.compile(
    r"^(?:put an? \+1/\+1 counter on (?P<countered>target [^,]+?),? then )?"
    r"each (?P<other>other )?(?P<modified>modified )?(?P<group>[^.]+?) you control deals "
    r"damage equal to its power to (?P<victim>(?:another )?target [^.]+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_group_bite_target_clauses(text: str, *, for_spell: bool) -> list[TargetedClause] | None:
    """`_GROUP_BITE_TARGET_RE`'s shape - see the banner above.

    CR 608.2b: an illegal counter target gets no counter and the rest still
    bites; an illegal victim takes nothing while the counter is still put."""
    if "deals damage equal to its power to" not in text.lower():
        return None
    sentences = _plain_resolution_sentences(_strip_non_effect_preamble(text))
    if len(sentences) != 1:
        return None
    match = _GROUP_BITE_TARGET_RE.fullmatch(sentences[0])
    if match is None:
        return None
    countered = match.group("countered")
    if countered is not None and not _targets_understood(countered):
        return None
    if not _targets_understood(match.group("victim")):
        return None
    group = match.group("group").strip()
    member = _parse_damage_group_phrase(group)
    if member is None:
        return None
    modified_only = match.group("modified") is not None
    other = match.group("other") is not None

    def clause(game: "Game", stack_object: "StackObject") -> None:
        from ..conditions.board import permanent_is_modified

        controller = game.controller_of(stack_object).username
        refs = list(getattr(stack_object, "targets", ()) or ())
        index = 0
        if countered is not None:
            index = 1
            first = game.legal_target(stack_object, refs[0]) if refs else None
            if isinstance(first, CardState) and first.zone is Zone.BATTLEFIELD:
                game.add_counters(first, "+1/+1", 1, putter=controller)
        victim = game.legal_target(stack_object, refs[index]) if len(refs) > index else None
        if not isinstance(victim, CardState) or victim.zone is not Zone.BATTLEFIELD:
            return
        source = _resolving_source(game, stack_object)
        biters = [
            permanent
            for permanent in list(game.battlefield)
            if game.controller_of(permanent).username == controller
            and game.characteristics_of(permanent).is_creature
            and member(game, permanent, controller)
            and not (other and source is not None and permanent.id == source.id)
            and (
                not modified_only
                or permanent_is_modified(game, permanent, game.characteristics_of(permanent))
            )
        ]
        _deal_all(game, [(biter, victim, game.power_of(biter) or 0) for biter in biters])

    return [clause]


from ..conditions.history import object_dealt_damage_clause_test  # noqa: E402
from ..replacement.model import CANT_BE_REGENERATED_LINE  # noqa: E402
from ._common import (  # noqa: E402
    _DAMAGE_EACH_FILTERED_RE,
    _DAMAGE_EACH_GROUP_RE,
    _DIVIDED_DAMAGE_AMONG_TARGET_PLAYERS_CREATURES_RE,
    _MANA_SYMBOL_RE,
    _THEY_CONTROL_RE,
    _YOU_OR_YOUR_RE,
    AmountReader,
    ConditionalClauseNotice,
    _effect_condition_is_readable,
    _opponents,
    _parse_mass_type_qualifier,
    _permanent_id_and_name,
    _targets_understood,
)
from .amounts import (  # noqa: E402
    _fixed_or_where_x_amount,
    _resolve_multiplied_amount,
    _that_many_or_notice,
    amount_expression,
    count_expression,
)
from .continuous import (  # noqa: E402
    _is_layer_effect_text,
    _layer_antecedent_clause,
    _named_player_of,
    continuous_effects,
    layer_context_for,
)
from .control_copy import _controlled_by_whose  # noqa: E402
from .dispatch import (  # noqa: E402
    _ability_effect_or_notice,
    _parse_mixed_clause,
    _parse_mixed_clauses,
    _parse_turn_rules_ban_clause,
    _spell_effect_or_notice,
)
from .text import (  # noqa: E402
    _parse_referent_object_clause,
    _plain_resolution_sentences,
    _referent_reader,
    _singular_card_type,
    _strip_non_effect_preamble,
)
from .tokens import _is_notice_only  # noqa: E402
