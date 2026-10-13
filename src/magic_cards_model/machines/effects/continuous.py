import re
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from magic_cards_model.phrases import with_indefinite_article

from ...data.subtypes import canonical_subtype, creature_type_vocabulary
from ...models.card import Color, Supertype, Type, types_of
from ...models.card_state import (
    CardState,
    Counter,
)
from ...models.mana import ManaCost
from ...models.player import Player
from ...models.token import (
    PREDEFINED,
    create_tokens,
    is_token,
)
from ...models.zone import Zone
from ...numbers import (
    COUNT,
    count_pattern,
    parse_count,
)
from .. import (
    mass_pump_conditions,
    mass_pump_followups,
)
from ..abilities import (
    AbilityKind,
    ActivatedAbility,
    TriggeredAbility,
    TriggerEvent,
    parse_abilities,
)
from ..casting import (
    PlayAction,
    hexproof_qualities_in,
    once_per_turn_key,
)
from ..casting_restrictions import create_targeted_cant_cast_restriction
from ..combat import (
    ASSIGN_AS_THOUGH_UNBLOCKED_TEXT,
    ATTACK_WITHOUT_DEFENDER_TEXT,
    BLOCKED_BY_AT_MOST_ONE_GRANT_TEXT,
    KEYWORDS_OUTSIDE_COMBAT,
    Keyword,
    has_keyword,
)
from ..converge import colors_of_mana_spent
from ..cost import (
    cost_announces_x,
)
from ..decisions import Decision, DecisionKind, source_id_of
from ..delayed import (
    AddManaWhenLandTapped,
    CombatDamageToPlayerDraw,
    CountersAndKeywordsEventSubject,
    CreateAttackingTokens,
    CreateTokensForController,
    DelayedTrigger,
    PayOrLoseTheGame,
    PumpEventSubject,
    ReflexiveConsequence,
    ReflexiveDamageEqualToSubjectPowerConsequence,
    RevokeGrantedAbility,
    parse_anaphoric_delayed_clause,
)
from ..ep02_r1_controller_recipients import attach_may_then_rider_effect
from ..land_animation import (
    retained_animation_effect,
    retained_animation_sentence,
)
from ..layers import (
    BASIC_LAND_TYPES,
    CANT_ACTIVATE_ABILITIES_TEXT,
    KNOWN_KEYWORDS,
    Condition,
    ContinuousEffect,
    ContinuousEffects,
    Duration,
    Layer,
    LayerContext,
    LayerNotice,
    RemainsOnBattlefield,
    Sublayer,
    YouStillControl,
    _only,
    _split_and_validate_keywords,
    activated_ability_lines,
    add_subtype,
    all_permanents_controlled_by,
    creatures_controlled_by,
    creatures_controlled_by_opponents_of,
    creatures_controlled_by_with_subtype,
    every_creature,
    genuine_resolution_layer_text,
    grant_ability,
    is_genuine_resolution_layer_sentence,
    is_resolution_layer_effect_text,
    is_x_substituted_layer_sentence,
    lose_all_abilities,
    lose_keyword,
    modify_power_toughness,
    only_this_incarnation,
    other_creatures_controlled_by,
    parsed_layer_effects,
    qualified_creatures,
    set_colors,
    set_power_toughness,
    split_and_validate_keywords,
)
from ..modes import (
    substitute_x,
)
from ..replacement import (
    exile_instead_of_leaving,
    is_leave_exile_line,
)
from ..targeting import (
    permanent_description,
    profile_for_text,
)
from ..triggers import (
    AbilityOnStack,
    batched_attackers,
    is_ability,
)
from ..turn import COMBAT_PHASE_STEPS, Step
from ..turn_scoped_riders import (
    run_layer_then_rider,
    run_with_antecedent,
    turn_scoped_rider,
)

if TYPE_CHECKING:
    from ...models.game import CastRecord, Game, StackObject
    from ..layers import Characteristics
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, MIXED_CLAUSES, SPELL_TEXT
from ._common import (
    _ANAPHOR_NOUN,
    _OBJECT_ANAPHOR,
    _SELF_ANAPHOR,
    AbilityEffect,
    ClauseEffect,
    Effect,
    ReferentObjectClause,
    ReferentReader,
    TargetedClause,
)


def sequence(*effects: Effect) -> Effect:
    """Do several things in the order the card lists them (CR 608.2c)."""

    def effect(game: "Game", spell: CardState) -> None:
        for step in effects:
            step(game, spell)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


def continuous_effects(game: "Game") -> ContinuousEffects:
    """The game's store of continuous effects with a duration (CR 611.2).

    `Game` holds the store now and ends its "until end of turn" effects in the
    cleanup step (CR 514.2, CR 703.4p), so a spell whose whole effect is a
    continuous one - Giant Growth, Mutagenic Growth, Twisted Image, Monstrous
    Rage's pump - reaches the layer engine and actually changes the board.
    """
    return game.continuous_effects


#: "Switch target creature's power and toughness until end of turn. Draw N
#: cards." - Twisted Image's whole text (CR 613.4d's switch, sublayer 7d, is
#: `layers._twisted_image`'s own `LAYER_EFFECTS` row - unaffected by this
#: parser, which only wires the draw after it). Read whole, ahead of
#: `parse_mixed_effect_for_spell`'s per-clause split: `_CLAUSE_SEPARATOR`
#: cuts any bare " and ", including the one inside "power and toughness",
#: into two fragments neither `_parse_targeted_clause` nor any other clause
#: shape can read back together. The draw count is read through
#: `numbers.COUNT` rather than pinned to Twisted Image's own "a", so a future
#: card sharing this exact template with a different draw count reads for
#: free.
_SWITCH_POWER_TOUGHNESS_THEN_DRAW_RE = re.compile(
    rf"^switch target creature['’]s power and toughness until end of turn\.\s*"
    rf"draw {count_pattern('n')} cards?\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s12")
def _parse_switch_power_toughness_then_draw_clause(text: str) -> Effect | None:
    """`_SWITCH_POWER_TOUGHNESS_THEN_DRAW_RE`'s shape - Twisted Image's whole
    text (CR 608.2c orders the draw after the switch, the order printed).
    """
    match = _SWITCH_POWER_TOUGHNESS_THEN_DRAW_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None
    return sequence(create_continuous_effect, draw_cards(count))


def layer_context_for(game: "Game", controller: Player) -> LayerContext:
    """The graveyards a resolving effect may need to count (CR 205.2a card types)."""
    everyone: list[CardState] = []
    for player in game.players_in_game:
        everyone.extend(player.graveyard)
    return LayerContext(
        graveyards=tuple(everyone),
        your_graveyard=tuple(controller.graveyard),
        condition_holds=lambda condition, source: game.condition_holds(
            controller.username, condition, source
        ),
    )


def _cast_trigger_record(game: "Game", ability: AbilityOnStack) -> "CastRecord | None":
    """The `CastRecord` of the spell that triggered `ability` via a
    cast-trigger event (CR 601.2i), or `None` when there is no cast-trigger
    event or no record of it.

    The cast trigger sits *above* the spell that made it (CR 603.3), so it
    can still be waiting to resolve after that spell was countered in
    response - and the Oracle rulings for every card built on this shape
    (Hydroid Krasis, Genesis Hydra, Old Stickfingers, Geometer's Arthropod)
    agree the trigger still resolves with the cast X even then. `Game.find_
    by_id` still finds the same card object once countered - CR 400.7's "new
    object" is about the permanent that would have entered, not the id this
    engine mints - but `Game.cast_record_of` is keyed by the object's
    *current* `zone_change_stamp`, which a counter's own zone change (CR
    701.6a: to the graveyard) has already moved past, and `Game.counter`
    (deliberately, per its own docstring) calls `forget_cast_record` right
    after, which drops the stale stack-side entry entirely so a later
    intervening *if* fails closed rather than misreading it.

    So this reads it the same way `Game.copy_spell_as_last_known` already
    does for CR 707.10's "copy that spell" naming a spell that may have left
    the stack: still on the stack, `cast_record_of` answers directly; gone,
    `CardState.last_known_spell.cast_record` is the copy `forget_cast_record`
    preserved there *before* dropping the live one (CR 608.2h). `event.
    subject_stamp` - the stack-side stamp `Game._put_on_stack` captured once,
    at the `CAST_SPELL` event itself - is the last resort, for a spell this
    engine somehow never gave a `last_known_spell` snapshot (a copy, CR
    707.10a, never had one to begin with) or one this event's own stamp does
    not match (a same-named recast in between)."""
    from ...models.game import CastRecord

    event = ability.event
    if event is None or event.event is not TriggerEvent.CAST_SPELL or event.subject_id is None:
        return None
    spell = game.find_by_id(event.subject_id)
    if not isinstance(spell, CardState):
        return None
    if spell in game.stack:
        return game.cast_record_of(spell)
    last_known = spell.last_known_spell
    if last_known is not None:
        if last_known.cast_record is not None:
            return CastRecord.model_validate(last_known.cast_record)
        return game.cast_record_as_last_known(last_known.stamp)
    if event.subject_stamp is not None:
        return game.cast_record_as_last_known(event.subject_stamp)
    return None


#: "Discard a card: This creature gets +1/+1 and becomes the color of your
#: choice until end of turn." (Wild Mongrel) and "{T}: Target creature you
#: control gains protection from the color of your choice until end of turn."
#: (Mother of Runes) both name a colour CR 608.2d leaves to the resolving
#: ability's controller, not the printed text - `parsed_layer_effects`' own
#: `LAYER_EFFECTS`/text-driven builders have no channel for a choice made at
#: resolution, so these two are built by hand through `ContinuousEffects.add`
#: (the escape hatch its own docstring names for "a caller that is not going
#: through the registry") rather than routed through `create_continuous_
#: effect_of_ability`.
_PUMP_AND_BECOMES_CHOSEN_COLOR_RE = re.compile(
    r"^this creature gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) and becomes the color of "
    r"your choice until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_pump_and_becomes_chosen_color_clause(text: str) -> AbilityEffect | None:
    """Wild Mongrel's own shape - see `_PUMP_AND_BECOMES_CHOSEN_COLOR_RE`.

    CR 613.1e is layer 5, colour-changing; the pump is layer 7c (CR 613.4c).
    Both are timestamped and stored as one "until end of turn" batch
    (CR 611.2a), same as any other resolving ability's continuous effect,
    just built directly rather than parsed a second time off printed text.
    """
    match = _PUMP_AND_BECOMES_CHOSEN_COLOR_RE.fullmatch(text.strip())
    if match is None:
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        controller = game.controller_of(ability)
        color = _choose_a_color(
            game,
            controller,
            source.name,
            f"choose a color for {source.name}",
            source_id=source_id_of(ability),
        )
        store = continuous_effects(game)
        timestamp = store.tick()
        store.add(
            ContinuousEffect(
                description=f"{source.name}: gets {power:+d}/{toughness:+d}",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_only(source.id),
                modification=modify_power_toughness(power, toughness),
            )
        )
        store.add(
            ContinuousEffect(
                description=f"{source.name}: becomes {color.value}",
                layer=Layer.COLOR,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_only(source.id),
                modification=set_colors(color),
            )
        )

    return effect


#: "It gains trample until end of turn." (Primaris Chaplain: "Whenever this
#: creature attacks, it gains indestructible until end of turn.", the effect
#: clause split off its own trigger condition) - CR 601.2c's pronoun reaching
#: back to the ability's own subject. A no-target triggered or activated
#: ability's *own* effect clause never reaches `parsed_layer_effects`' "this
#: creature"/named-self shapes (`create_continuous_effect_of_ability` derives
#: what to parse from the source's full printed text, not from this already
#: trigger-condition-stripped clause), so this is built by hand instead, one
#: keyword-grant `ContinuousEffect` per keyword, the same escape hatch
#: `_parse_pump_and_becomes_chosen_color_clause` uses above.
#:
#: "this permanent" alongside "it" - The Vision's own modal bullet "The
#: Vision gains double strike until end of turn." reaches this reader only
#: after `_resolve_modal_triggered_ability_clause`'s own fallback runs
#: `_self_normalized_effect_text` on it (CR 201.5's self-reference by printed
#: name, rewritten to CR 700.7's "this permanent" - `abilities.py`'s own
#: rewrite, not this reader's), so the subject this reader sees is never the
#: literal printed name.
_SELF_KEYWORD_GRANT_UNTIL_EOT_RE = re.compile(
    r"^(?:it|this permanent) gains "
    r"(?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*) "
    r"until end of turn\.?$",
    re.IGNORECASE,
)

#: "It gains your choice of trample or deathtouch until end of turn."
#: (Hunter's Axe's granted attack trigger) - the shape above with CR 608.2d's
#: "of your choice" ahead of a fixed, enumerated list rather than a single
#: named keyword, read the same `DecisionKind.CHOOSE_A_QUALITY` way
#: `_choose_a_color` reads a colour choice, narrowed to the two-or-more
#: keywords the sentence itself names instead of the five colours. "this
#: permanent" alongside "it" for the same self-normalized-name reason as
#: `_SELF_KEYWORD_GRANT_UNTIL_EOT_RE` above.
_SELF_CHOICE_KEYWORD_GRANT_UNTIL_EOT_RE = re.compile(
    r"^(?:it|this permanent) gains your choice of "
    r"(?P<options>[a-z]+(?: [a-z]+)?(?:,\s*[a-z]+(?: [a-z]+)?)*"
    r"(?:,)?\s*or\s+[a-z]+(?: [a-z]+)?) until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36", before=["continuous._parse_event_subject_pump_clause"])
def _parse_self_keyword_grant_until_eot_clause(text: str) -> AbilityEffect | None:
    """`_SELF_KEYWORD_GRANT_UNTIL_EOT_RE`/`_SELF_CHOICE_KEYWORD_GRANT_UNTIL_
    EOT_RE`'s two shapes - see either regex's own docstring. Tried as one
    function, the choice shape first, since a plain "it gains X" text never
    contains "your choice of" and the two can never both match the same
    sentence.
    """
    stripped = text.strip()
    if match := _SELF_CHOICE_KEYWORD_GRANT_UNTIL_EOT_RE.fullmatch(stripped):
        raw_options = [
            option.strip()
            for option in re.split(r",\s*|\s+or\s+", match.group("options"))
            if option.strip()
        ]
        options: list[str] = []
        for option in raw_options:
            validated = _split_and_validate_keywords(option)
            if validated is None or len(validated) != 1:
                return None
            options.append(validated[0])

        def choice_effect(game: "Game", ability: AbilityOnStack) -> None:
            source = ability.source(game)
            if source is None or source.zone is not Zone.BATTLEFIELD:
                return
            controller = game.controller_of(ability)
            decision = Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=controller.username,
                prompt=f"choose which keyword {source.name} gains until end of turn",
                source=source.name,
                options=tuple(options),
                source_id=source_id_of(ability),
            )
            answer = game.ask(decision)
            assert isinstance(answer, str)
            store = continuous_effects(game)
            store.add(
                ContinuousEffect(
                    description=f"{source.name}: gains {answer} until end of turn",
                    layer=Layer.ABILITY,
                    timestamp=store.tick(),
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=_only(source.id),
                    modification=grant_ability(answer),
                )
            )

        return choice_effect
    if match := _SELF_KEYWORD_GRANT_UNTIL_EOT_RE.fullmatch(stripped):
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None

        def plain_effect(game: "Game", ability: AbilityOnStack) -> None:
            source = ability.source(game)
            if source is None or source.zone is not Zone.BATTLEFIELD:
                return
            store = continuous_effects(game)
            timestamp = store.tick()
            for keyword in keywords:
                store.add(
                    ContinuousEffect(
                        description=f"{source.name}: gains {keyword} until end of turn",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=_only(source.id),
                        modification=grant_ability(keyword),
                    )
                )

        return plain_effect
    return None


#: "This creature gains protection from red until end of turn." (Thick-Skinned
#: Goblin's `{R}:` ability) - the self-grant of a named protection quality,
#: CR 702.16a's "protection from [quality]" (and CR 702.16g's "and from")
#: added in layer 6 (CR 613.1f) until end of turn (CR 611.2a). The quality
#: vocabulary is `machines/protection_statics.parse_protection_qualities`'s,
#: the one the static grants read, so "each color" and a chosen quality mean
#: the same here.
_SELF_PROTECTION_GRANT_UNTIL_EOT_RE = re.compile(
    r"^(?:it|this permanent|this creature) gains protection from "
    r"(?P<qualities>(?!the color of your choice).+?) until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_self_protection_grant_until_eot_clause(text: str) -> AbilityEffect | None:
    """`_SELF_PROTECTION_GRANT_UNTIL_EOT_RE`'s shape - see its docstring."""
    match = _SELF_PROTECTION_GRANT_UNTIL_EOT_RE.fullmatch(text.strip())
    if match is None:
        return None
    from ..protection_statics import parse_protection_qualities, resolve_qualities

    qualities = parse_protection_qualities(match.group("qualities"))
    if qualities is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        resolved = resolve_qualities(qualities, source)
        if resolved is None:
            return
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{source.name}: gains protection from {', '.join(resolved)}",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_only(source.id),
                modification=grant_ability("protection from " + " and from ".join(resolved)),
            )
        )

    return effect


#: "Target creature you control gains protection from the color of your
#: choice until end of turn." (Mother of Runes). The phrase itself is checked
#: through `_targets_understood` the same as every other targeted clause;
#: `_MOTHER_OF_RUNES_PROTECTION_RE` only reads past "target creature you
#: control" to confirm the rest is this exact chosen-colour protection shape.
#:
#: Widened (NW-04 T2) to "protection from colorless or from the color of your
#: choice" (Giver of Runes, Angelic Intervention): the choice made as it
#: resolves (CR 608.2d) offers colorless (CR 105.2c) beside the five colours,
#: and the grant is "Protection from colorless" or "Protection from <colour>"
#: (CR 702.16a).
_PROTECTION_FROM_CHOSEN_COLOR_RE = re.compile(
    r"^(?P<phrase>(?:another )?target .+) gains protection from "
    r"(?P<colorless>colorless or from )?the color of your choice "
    r"until end of turn\.?$",
    re.IGNORECASE,
)
#: The choice `_grant_chosen_color_protection` offers when colorless is
#: printed beside "the color of your choice".
_COLORLESS_CHOICE = "colorless"


@ABILITY_TEXT.rung("s36")
def _parse_protection_from_chosen_color_clause(text: str) -> AbilityEffect | None:
    """Mother of Runes' own shape - see `_PROTECTION_FROM_CHOSEN_COLOR_RE`.

    CR 702.16a: "Protection is a static ability, written 'Protection from
    [quality].'" Granting one line of that text in layer 6 (CR 613.1f) is
    exactly what `machines/layers._indefinite_keyword_grant_builder` already
    does for Akroma's Memorial's *un*-chosen "protection from black and from
    red" - this is the same `grant_ability("Protection from <color>")` shape,
    just aimed at whichever target was chosen and whichever colour the
    activating player names, so it is built by hand rather than read off
    static printed text a second time. `docs/engine-coverage.md` already
    records that a *granted* colour quality is read on the damage side
    (`Game._effective_protection_qualities`, consulted by both `protection_
    from_damage` and `protection_refusal`) but not yet on the targeting side
    for a card-type quality's own reason - unrelated to this card, and not
    widened here.
    """
    match = _PROTECTION_FROM_CHOSEN_COLOR_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=False):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if targets:
            _grant_chosen_color_protection(
                game, ability, targets[0], allow_colorless=allow_colorless
            )

    allow_colorless = match.group("colorless") is not None
    return effect


#: "If it's a creature, put a +1/+1 counter on it." / "Put a +1/+1 counter
#: on it." after a protection grant (Angelic Intervention) - "it" is the
#: grant's own target (CR 608.2c), and the type condition is checked against
#: that object as the spell resolves.
_PROTECTION_COUNTER_RIDER_RE = re.compile(
    r"^(?:if it'?s an? (?P<type>creature|planeswalker|artifact|enchantment|land), )?"
    r"put (?P<amount>an?|one|two|three|\d+) (?P<kind>[+-]1/[+-]1|[a-z]+) counters? on it\.?$",
    re.IGNORECASE,
)


def _protection_counter_rider(
    text: str,
) -> "Callable[[Game, CardState], None] | None":
    """`_PROTECTION_COUNTER_RIDER_RE`'s shape as an action on the grant's
    target, or `None`."""
    match = _PROTECTION_COUNTER_RIDER_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    amount = parse_count(match.group("amount"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))
    required = Type(match.group("type").lower()) if match.group("type") else None

    def rider(game: "Game", target: CardState) -> None:
        if target.zone is not Zone.BATTLEFIELD:
            return
        if required is not None and required not in game.characteristics_of(target).types:
            return
        game.add_counters(target, kind, amount)

    return rider


@SPELL_TEXT.rung("s10")
def _parse_protection_from_chosen_color_spell(text: str) -> Effect | None:
    """A spell whose first sentence is `_PROTECTION_FROM_CHOSEN_COLOR_RE`'s
    clause (Gods Willing, Center Soul), with the sentences after it (Gods
    Willing's "Scry 1.") read as the ordinary instructions that follow it (CR
    608.2c). Without this the spell went to `create_continuous_effect`, which
    cannot name a colour chosen at resolution and recorded a `LayerNotice`."""
    if "the color of your choice" not in text.lower() or "protection from" not in text.lower():
        return None
    sentences = _plain_resolution_sentences(" ".join(_strip_non_effect_preamble(text).split()))
    if not sentences:
        return None
    protection = _parse_protection_from_chosen_color_clause(sentences[0])
    if protection is None:
        return None
    if len(sentences) == 1:
        return protection  # type: ignore[return-value]
    if len(sentences) == 2 and (rider := _protection_counter_rider(sentences[1])) is not None:

        def protection_then_counter(game: "Game", spell: CardState) -> None:
            protection(game, spell)  # type: ignore[arg-type]
            for target in game.resolve_targets(spell):
                if isinstance(target, CardState):
                    rider(game, target)

        return protection_then_counter
    rest = _spell_effect_or_notice(" ".join(sentences[1:]))
    if rest is None or _is_notice_only(rest):
        return None
    return sequence(protection, rest)  # type: ignore[arg-type]


def _grant_chosen_color_protection(
    game: "Game", stack_object: "StackObject", target: CardState, *, allow_colorless: bool = False
) -> None:
    """CR 608.2d: the resolving spell's or ability's controller names a colour,
    and `target` gains "Protection from <that colour>" (CR 702.16a) in layer 6
    (CR 613.1f) until end of turn (CR 611.2a). Shared by the targeted "gains
    protection from the color of your choice" clause above and the anaphoric
    "It gains protection from the color of your choice" rider."""
    if isinstance(stack_object, CardState):
        source_name = stack_object.name
    else:
        source = stack_object.source(game)
        source_name = source.name if source is not None else stack_object.source_name
    if allow_colorless:
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=game.controller_of(stack_object).username,
                prompt=f"choose colorless or a color for {source_name}'s protection",
                source=source_name,
                options=(_COLORLESS_CHOICE, *_COLOR_LETTERS),
                source_id=source_id_of(stack_object),
            )
        )
        assert isinstance(chosen, str)
        quality = _COLORLESS_CHOICE if chosen == _COLORLESS_CHOICE else _COLOR_NAME[Color(chosen)]
    else:
        color = _choose_a_color(
            game,
            game.controller_of(stack_object),
            source_name,
            f"choose a color for {source_name}'s protection",
            source_id=source_id_of(stack_object),
        )
        quality = _COLOR_NAME[color]
    store = continuous_effects(game)
    store.add(
        ContinuousEffect(
            description=f"{source_name}: {target.name} has protection from {quality}",
            layer=Layer.ABILITY,
            timestamp=store.tick(),
            duration=Duration.UNTIL_END_OF_TURN,
            selector=_only(target.id),
            modification=grant_ability(f"Protection from {quality}"),
        )
    )


#: "Until end of turn, Mondo Gecko becomes the color of your choice and gains
#: hexproof from that color." (Mondo Gecko, its name already CR 201.5's "this
#: permanent"); "Target permanent becomes the color of your choice until end
#: of turn." (Distorting Lens) - the colour CR 608.2d leaves to the
#: resolving ability's controller, set in layer 5 (CR 613.1e, CR 105.3's
#: "the new color replaces all previous colors"), with an optional "gains
#: hexproof from that color" rider (CR 702.11d's "hexproof from [quality]")
#: granted in layer 6 (CR 613.1f). The duration prints either first or last,
#: never both.
#:
#: Widened (ecl T5) to Puca's Eye's "choose a color. This artifact becomes
#: the chosen color." - the choice spelled as its own sentence (CR 608.2d
#: still: made as the ability resolves), any "this <permanent type>" as the
#: subject, and no duration at all, which CR 611.2a reads as until the end of
#: the game. Without the "choose a color." sentence a durationless form is
#: never read here: "the chosen color" would then name some other choice.
_BECOMES_CHOSEN_COLOR_RE = re.compile(
    r"^(?P<lead>until end of turn,\s*)?(?P<choose>choose a colou?r\.\s*)?"
    r"(?P<subject>this (?:creature|permanent|artifact|enchantment|land)|target [^.]+?) "
    r"becomes the (?:colou?r of your choice|(?P<chosen>chosen colou?r))"
    r"(?: and gains (?P<keyword>hexproof) from that color)?"
    r"(?P<trail> until end of turn)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_becomes_chosen_color_clause(text: str) -> AbilityEffect | None:
    """`_BECOMES_CHOSEN_COLOR_RE`'s shape, or `None`.

    Built by hand through `ContinuousEffects.add` for the same reason
    Wild Mongrel's and Mother of Runes' own chosen colours are (see
    `_PUMP_AND_BECOMES_CHOSEN_COLOR_RE`): the colour is not in the printed
    text. The colour and the grant share one timestamp and last until
    cleanup (CR 514.2), each keyed to the object as it is now (CR 400.7)."""
    match = _BECOMES_CHOSEN_COLOR_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    lead, trail = match.group("lead") is not None, match.group("trail") is not None
    if lead and trail:
        return None
    chooses = match.group("choose") is not None
    if (match.group("chosen") is not None) != chooses:
        return None
    if not (lead or trail) and not chooses:
        return None
    duration = Duration.UNTIL_END_OF_TURN if lead or trail else Duration.INDEFINITE
    subject = match.group("subject")
    targeted = subject.lower().startswith("target ")
    if targeted and not _targets_understood(subject, count_agnostic=False):
        return None
    keyword = match.group("keyword")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        source_name = source.name if source is not None else ability.source_name
        if targeted:
            chosen = [
                target
                for target in game.resolve_targets(ability)
                if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
            ]
        else:
            chosen = [source] if source is not None and source.zone is Zone.BATTLEFIELD else []
        if not chosen:
            return
        color = _choose_a_color(
            game,
            game.controller_of(ability),
            source_name,
            f"choose a color for {source_name}",
            source_id=source_id_of(ability),
        )
        store = continuous_effects(game)
        timestamp = store.tick()
        for permanent in chosen:
            selector = only_this_incarnation(permanent, permanent.zone_change_stamp)
            store.add(
                ContinuousEffect(
                    description=f"{source_name}: {permanent.name} becomes {color.value}",
                    layer=Layer.COLOR,
                    timestamp=timestamp,
                    duration=duration,
                    selector=selector,
                    modification=set_colors(color),
                )
            )
            if keyword is not None:
                granted = f"{keyword.capitalize()} from {_COLOR_NAME[color]}"
                store.add(
                    ContinuousEffect(
                        description=f"{source_name}: {permanent.name} gains {granted}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=duration,
                        selector=selector,
                        modification=grant_ability(granted),
                    )
                )

    return effect


_COLOR_NAME: dict[Color, str] = {
    Color.WHITE: "white",
    Color.BLUE: "blue",
    Color.BLACK: "black",
    Color.RED: "red",
    Color.GREEN: "green",
}


# --------------------------------------------------------------------------
# P5: a duration-bearing team-wide pump with no target, magnitude fixed at
# resolution (CR 611.2, CR 611.2c)
# --------------------------------------------------------------------------
#
# `create_continuous_effect`/`create_continuous_effect_of_ability` above
# default an untargeted ability's affected object to its own source ("this
# creature gets +2/+2"), which is right for Basking Rootwalla and wrong for
# "creatures you control get +N/+N until end of turn." - Violent Outburst's
# own pump, and Craterhoof Behemoth's "creatures you control gain trample and
# get +X/+X until end of turn, where X is the number of creatures you
# control." `docs/engine-coverage.md` used to carry this row as a recorded
# gap ("the actual continuous effect for a team-wide temporary pump is still
# not built"); `machines/layers.py`'s `_MASS_PUMP_UNTIL_EOT_RE`/
# `_mass_pump_until_eot_builder` build the effect once handed the concrete,
# already-resolved group, and everything below computes that group and (when
# the card prints one) the "where X is ..." magnitude.
#: "Other creatures get -2/-2 until end of turn." (Harvester of Misery) /
#: "all other creatures get -2/-2 until end of turn." (Shefet Archfiend) -
#: every creature but the source, whoever controls it (`_MASS_OTHER_
#: CREATURES_RE`), a whole-board subject like "all creatures".
_MASS_OTHER_CREATURES_RE = re.compile(r"^(?:all )?other creatures (?=get |gain )", re.IGNORECASE)
_MASS_SUBJECT_RE = re.compile(
    r"^(?:(?:all )?other creatures (?=get |gain )"
    r"|(?:other )?creatures (?:you control|your opponents control)"
    r"|creature tokens (?:you control|your opponents control)|permanents you control"
    r"|all creatures|creatures that are (?:white|blue|black|red|green)\b)\b",
    re.IGNORECASE,
)
#: History of Benalia's own chapter III: "Knights you control get +2/+1
#: until end of turn." - CR 205.3m's bare creature-type word standing in for
#: the elided "creatures", the mass-pump twin of `machines/targeting.
#: _is_bare_subtype_word`'s reading of the same shape for a *target*.
#: Deliberately case-sensitive (no `re.IGNORECASE`) rather than folded into
#: `_MASS_SUBJECT_RE` above: Oracle text only ever capitalizes a subtype, so
#: requiring the capital is what tells a genuine "Knights you control" apart
#: from a sentence merely starting with some other lowercase-elsewhere noun -
#: `_MASS_SUBJECT_RE`'s own literal "creatures" is tried first and always
#: wins when it matches, so this never intercepts "Creatures you control ..."
#: (Violent Outburst), capitalized only because it opens the sentence.
#: Along the Crooked Way's own "Goblins and Orcs you control gain menace
#: until end of turn." - `_MASS_SUBTYPE_SUBJECT_RE`'s single bare CR 205.3m
#: subtype, widened to a joined list the same way `_SUBTYPE_LIST` already
#: reads one for `machines/layers.py`'s own static anthem subject (Warg
#: Rider's "Orcs and Goblins you control have menace", a *permanent* CR
#: 611.3 version of the identical two-subtype grammar) - membership in *any*
#: one of the list is enough, the plain CR 205.2b reading a card with two
#: creature types already gets from a bare type list everywhere else in this
#: file.
_MASS_SUBTYPE_SUBJECT_RE = re.compile(
    r"^(?![Cc]reatures?\b)(?!(?:Artifacts|Enchantments|Lands|Planeswalkers|Battles)\b)"
    r"(?P<subtypes>[A-Z][a-z]+(?:(?:,\s*(?:and )?| and )[A-Z][a-z]+)*) "
    r"(?P<whose>you control|your opponents control)\b"
)
#: "Artifacts and planeswalkers you control gain indestructible until end of
#: turn." (Urza, Planeswalker), "Creatures and Vehicles you control gain
#: trample until end of turn." (Boom Scholar): a group of card types (CR 205.2a)
#: read by the one subject grammar the static anthems use
#: (`layers/group_grants.parse_group`), fixed once as the effect begins.
_MASS_GROUP_SUBJECT_RE = re.compile(
    r"^(?P<subject>[A-Za-z][A-Za-z' -]*? (?P<whose>you control|your opponents control)) "
    r"(?P<verb>gains?|gets?|becomes?)\b"
)


def _mass_group_filter(
    text: str,
) -> "tuple[re.Match[str], Callable[[Characteristics], bool]] | None":
    """`_MASS_GROUP_SUBJECT_RE`'s subject and the `GroupMatch` it names, when
    that subject names a card type other than the bare "creatures" (which the
    ordinary mass subjects above already read)."""
    from ..layers.group_grants import parse_group
    from ..layers.model import GroupMatch

    match = _MASS_GROUP_SUBJECT_RE.match(text.strip())
    if match is None:
        return None
    spec = parse_group(match.group("subject"))
    if (
        spec is None
        or spec["chosen"]
        or spec["other"]
        or spec.get("named")
        or spec.get("enchanted_player")
        or spec.get("attached_to_scope")
    ):
        return None
    if not (spec["all_types"] or spec["any_types"]) or (
        spec["all_types"] == (Type.CREATURE,)
        and not any(value for key, value in spec.items() if key not in ("scope", "all_types"))
    ):
        return None
    # Whose permanents is the caller's question (`group_match["whose"]`).
    fields = {
        key: value
        for key, value in spec.items()
        if key not in ("other", "chosen", "scope", "enchanted_player")
    }
    selector = GroupMatch(username=None, scope="any", **fields)

    def matches(chars: "Characteristics") -> bool:
        return selector(chars, None)  # type: ignore[arg-type]

    return match, matches


#: Ravenous Robots: "Creature tokens you control gain haste until end of
#: turn." - CR 111.1's token-ness narrowing the ordinary "creatures [you|your
#: opponents] control" subject, read the identical "known only here, off the
#: literal text" way `_MASS_SUBTYPE_SUBJECT_RE` already reads a bare subtype
#: standing in for "creatures".
_MASS_TOKEN_SUBJECT_RE = re.compile(
    r"^creature tokens (?P<whose>you control|your opponents control)\b", re.IGNORECASE
)
#: "Creatures you control with power `<n>` or greater gain `<keyword(s)>`
#: until end of turn." (Smuggler's Surprise's third Spree mode: "gain
#: hexproof and indestructible"; Gustrider Exuberant's own sacrifice
#: ability: "gain flying") - `_MASS_SUBJECT_RE`'s bare "creatures you
#: control" subject narrowed by a power filter. CR 611.2c: "the set of
#: objects [a one-shot effect] affects is determined when that continuous
#: effect begins to exist" - so the filter is read **once**, here, against
#: the board as it stands right now (`_mass_creature_group_targets`), the
#: same fixed-set-now convention the plain mass subject already gets; a
#: creature whose power changes later in the turn, or that enters after
#: this resolves, is never swept in or dropped.
_MASS_POWER_FILTER_RE = re.compile(
    rf"^(?P<other>other )?creatures (?P<whose>you control|your opponents control) "
    rf"with power {count_pattern('power', article=False)} or greater\b",
    re.IGNORECASE,
)
#: "Artifact creatures you control" / "... your opponents control" - CR
#: 205.2a's card type narrowing the ordinary "creatures [you|your opponents]
#: control" subject the identical way `_MASS_COLOR_FILTER_RE`'s colour and
#: `_MASS_POWER_FILTER_RE`'s power already do. Age of Ultron's own chapter
#: III: "Artifact creatures you control gain deathtouch until end of turn.
#: Put a +1/+1 counter on each of them." - the second real printing of
#: Summon: Knights of Round's "counter on each of them" shape, narrowed by a
#: type this reader had no branch for at all before this card needed one.
_MASS_TYPE_FILTER_RE = re.compile(
    r"^(?P<type>artifact|enchantment|land|planeswalker|battle) creatures "
    r"(?P<whose>you control|your opponents control)\b",
    re.IGNORECASE,
)
#: "Vampire creatures you control get +2/+0 and gain first strike until end
#: of turn." (Vampiric Fury), "Elf creatures you control get +3/+3 ..."
#: (Ezuri, Renegade Leader), "colorless creatures you control gain "..."" (Gruesome
#: Slaughter) - one qualifying word in front of the ordinary "creatures [you
#: control|your opponents control]" subject: a CR 205.3m creature type, a
#: colour (CR 105.1) or "colorless" (CR 105.2c: an object with no colour).
#: The word is validated by `_mass_word_filter`, so "Other"/"Attacking" and
#: the CR 205.2a card types `_MASS_TYPE_FILTER_RE` reads never pass as one.
_MASS_WORD_FILTER_SUBJECT_RE = re.compile(
    r"^(?P<word>[A-Za-z][a-z-]*) creatures (?P<whose>you control|your opponents control)\b"
)
_MASS_FILTER_COLORS = ("white", "blue", "black", "red", "green")
#: "Attacking creatures get +1/+0 until end of turn." (Thunderstaff), "Other
#: modified creatures you control get +X/+X until end of turn, where X is this
#: creature's power." (Golden-Tail Trainer) - a combat-state or modified
#: adjective in front of "creatures", optionally narrowed by controller (no
#: controller phrase means every player's). Fixed once as the effect begins
#: (CR 611.2c); "attacking" is CR 508.1k's, "modified" CR 700.9's.
_MASS_STATE_SUBJECT_RE = re.compile(
    r"^(?P<other>other )?(?P<state>attacking|blocking|modified|tapped|untapped) creatures"
    r"(?: (?P<whose>you control|your opponents control))?(?= (?:get|gain)\b)",
    re.IGNORECASE,
)


def _is_mass_state_subject(text: str) -> bool:
    """Cheap literal gate before `_MASS_STATE_SUBJECT_RE` (hot on the pool)."""
    head = text[:30].lower()
    return " creatures" in head and head.startswith(
        ("attacking", "blocking", "modified", "tapped", "untapped", "other ")
    )


def _mass_state_group(game: "Game", controller: str, source_id: UUID, match) -> list[CardState]:
    """The creatures `_MASS_STATE_SUBJECT_RE` names, on the board right now."""
    from ..conditions.board import permanent_is_modified

    state = match.group("state").lower()
    whose = (match.group("whose") or "").lower()
    board = game.computed_board()
    group = []
    for permanent in game.battlefield:
        chars = board.of(permanent)
        if not chars.is_creature:
            continue
        if whose == "you control" and chars.controller != controller:
            continue
        if whose == "your opponents control" and chars.controller in (None, controller):
            continue
        if match.group("other") and permanent.id == source_id:
            continue
        if state == "attacking" and not game.is_attacking(permanent):
            continue
        if state == "blocking" and not game.is_blocking(permanent):
            continue
        if state == "modified" and not permanent_is_modified(game, permanent, chars):
            continue
        if state == "tapped" and not permanent.tapped:
            continue
        if state == "untapped" and permanent.tapped:
            continue
        group.append(permanent)
    return group


def _mass_word_filter(
    text: str,
) -> "tuple[re.Match[str], Callable[[Characteristics], bool]] | None":
    """`_MASS_WORD_FILTER_SUBJECT_RE`'s subject and the predicate its word
    names on a creature's computed characteristics, or `None` when the word
    is no colour, not "colorless" and no creature type."""
    match = _MASS_WORD_FILTER_SUBJECT_RE.match(text.strip())
    if match is None:
        return None
    word = match.group("word").lower()
    if word == "colorless":
        return match, lambda chars: not chars.colors
    if word in _MASS_FILTER_COLORS:
        color = _TOKEN_COLOR_WORDS[word]
        return match, lambda chars: color in chars.colors
    if not match.group("word")[0].isupper():
        return None
    subtype = canonical_subtype(match.group("word"))
    if subtype is None:
        return None
    return match, lambda chars: subtype.lower() in {name.lower() for name in chars.subtypes}


#: The two whole-board subjects `_MASS_SUBJECT_RE` reads that also open
#: sentences which are not a pump at all - see `_parse_mass_pump_clause`.
_MASS_WHOLE_BOARD_SUBJECT_RE = re.compile(
    r"^(?:all creatures|all (?:non)?snow creatures|creatures that are"
    r"|(?:all )?other creatures (?=get |gain ))\b",
    re.IGNORECASE,
)
#: "Creatures that are green and/or white" - Glistening Deluge's second
#: sentence: every creature on the battlefield, narrowed by colour (CR 105.2:
#: an object is one or more of the five colours, so "and/or" admits a
#: creature that is either or both, once). Read once, against the computed
#: board, when the effect begins (CR 611.2c) - the same fixed-set-now
#: convention the other mass subjects here already get.
_MASS_COLOR_FILTER_RE = re.compile(
    r"^creatures that are (?P<colors>(?:white|blue|black|red|green)"
    r"(?:(?:,\s*|\s+and/or\s+|\s+or\s+)(?:white|blue|black|red|green))*)\b",
    re.IGNORECASE,
)
#: "All nonsnow creatures get -X/-X until end of turn" (Dead of Winter), "All
#: snow creatures ..." - the whole board narrowed by CR 205.4g's snow supertype,
#: read once against the computed board as the effect begins (CR 611.2c). A
#: controller qualifier narrows it further: "Snow creatures you control get
#: +1/+1 until end of turn" (Diamond Faerie).
_MASS_SUPERTYPE_SUBJECT_RE = re.compile(
    r"^(?:all )?(?P<negated>non)?snow creatures"
    r"(?P<whose> you control| your opponents control)?\b(?= (?:get|gain)\b)",
    re.IGNORECASE,
)
#: The trailing computed-magnitude clause - "..., where X is <expr>." - split
#: off so the rest of the sentence can be handed to `machines/layers.py`'s
#: parser once "X" is replaced by a literal number.
_WHERE_X_IS_RE = re.compile(r",?\s*where x is (?P<expr>.+?)\.?$", re.IGNORECASE)

#: "each other Hero you control gets +X/+X until end of turn" (Captain
#: America, Wings of Freedom), "each other creature you control gets ..."
#: (Wild Beastmaster) - the singular "each" subject of a one-shot group pump,
#: a creature type (CR 205.3m) or plain "creature", fixed once as the effect
#: begins (CR 611.2c).
#: Widened (NW-04 T2) to a keyword qualifier and the "gains" verb - Plague
#: Nurse's "Each other creature you control with toxic gains toxic 1 until
#: end of turn." (CR 702.164a): only creatures that have the named keyword
#: as the effect begins are in the group (CR 611.2c).
_MASS_EACH_SUBJECT_RE = re.compile(
    r"^[Ee]ach (?P<other>other )?(?P<noun>creature|[A-Z][a-z]+) "
    r"(?P<whose>you control|your opponents control)"
    r"(?: with (?:power (?P<min_power>\d+) or greater|(?P<with_keyword>[a-z]+(?: [a-z]+)?)))?"
    r" (?P<verb>gets|gains)\b"
)


def _source_characteristic_magnitude(expr: str) -> "MassPumpMagnitude | None":
    """`_SOURCE_CHARACTERISTIC_RE` as a mass pump's magnitude reader."""
    match = _SOURCE_CHARACTERISTIC_RE.fullmatch(expr.strip().rstrip("."))
    if match is None:
        return None
    characteristic = match.group("characteristic").lower()

    def read(game: "Game", controller: str, source_id: str | None) -> int:
        source = game.find_by_id(UUID(source_id)) if source_id else None
        return _source_characteristic(game, source, characteristic)

    return read


def _mass_creature_group_targets(
    game: "Game", controller: str, source_id: UUID, text: str
) -> list[CardState] | None:
    """The concrete creatures a mass, untargeted "creatures you control" /
    "other creatures you control" / "creatures your opponents control"
    resolution effect affects, fixed **now** (CR 611.2c: "the set of objects
    it affects is determined when that continuous effect begins ... any
    objects that come under [that] control later aren't affected") rather
    than a live `Selector` that would keep re-including whoever is on the
    battlefield the next time CR 613.5 recomputes it - which is exactly right
    for a *static* ability's own anthem (`_anthem_builder`) and exactly wrong
    here. `None` if `text`'s subject is none of the three - the caller's
    ordinary target resolution stays in charge for everything else.
    """
    state_match = (
        _MASS_STATE_SUBJECT_RE.match(text.strip()) if _is_mass_state_subject(text) else None
    )
    if state_match is not None:
        return _mass_state_group(game, controller, source_id, state_match)
    each_match = _MASS_EACH_SUBJECT_RE.match(text.strip())
    if each_match is not None:
        noun = each_match.group("noun")
        wanted_subtype = None if noun == "creature" else canonical_subtype(noun)
        if noun != "creature" and wanted_subtype is None:
            return None
        base = (
            creatures_controlled_by(controller)
            if each_match.group("whose") == "you control"
            else creatures_controlled_by_opponents_of(controller)
        )
        with_keyword = each_match.group("with_keyword")
        min_power = each_match.group("min_power")
        if with_keyword is not None and with_keyword.lower() not in {k.value for k in Keyword}:
            return None
        board = game.computed_board()
        return [
            permanent
            for permanent in game.battlefield
            if base(board.of(permanent), board.characteristics)
            and not (each_match.group("other") and permanent.id == source_id)
            and (with_keyword is None or has_keyword(permanent, with_keyword.lower(), game))
            and (min_power is None or (board.of(permanent).power or 0) >= int(min_power))
            and (
                wanted_subtype is None
                or wanted_subtype in {word.lower() for word in board.of(permanent).subtypes}
            )
        ]
    subtype_match = _MASS_SUBTYPE_SUBJECT_RE.match(text.strip())
    if subtype_match is not None:
        # History of Benalia's "Knights you control" - CR 205.3m's subtype
        # narrows the ordinary "creatures [you|opponents] control" selectors
        # above by one more check, added on top rather than a fifth selector
        # function in `machines/layers.py` since the subtype word is only
        # known here, off the literal sentence text.
        # "Knights" (CR 205.3m plurals with a bare "s") against the subtype as
        # it is actually stored, singular - `board.of(...).subtypes` holds
        # "Knight", never "Knights".
        subtypes = {
            part.strip().lower().removesuffix("s")
            for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", subtype_match.group("subtypes"))
            if part.strip()
        }
        # A subtype word names every permanent carrying it, not only
        # creatures: Sapling Nursery's "Treefolk and Forests you control"
        # reaches the Forests (a CR 205.3i land type) as well as the Treefolk
        # (a CR 205.3m creature type), so the controller check carries no
        # creature requirement.
        you = subtype_match.group("whose") == "you control"
        board = game.computed_board()
        return [
            permanent
            for permanent in game.battlefield
            if (
                board.of(permanent).controller == controller
                if you
                else board.of(permanent).controller not in (None, controller)
            )
            and subtypes & {word.lower() for word in board.of(permanent).subtypes}
        ]
    supertype_match = _MASS_SUPERTYPE_SUBJECT_RE.match(text.strip())
    if supertype_match is not None:
        board = game.computed_board()
        wants_snow = supertype_match.group("negated") is None
        whose = (supertype_match.group("whose") or "").strip()
        return [
            permanent
            for permanent in game.battlefield
            if board.of(permanent).is_creature
            and (Supertype.SNOW in board.of(permanent).supertypes) == wants_snow
            and (
                not whose
                or (board.of(permanent).controller == controller) == (whose == "you control")
            )
        ]
    color_filter_match = _MASS_COLOR_FILTER_RE.match(text.strip())
    if color_filter_match is not None:
        wanted = {
            _TOKEN_COLOR_WORDS[word.lower()]
            for word in re.findall(
                r"white|blue|black|red|green", color_filter_match.group("colors"), re.IGNORECASE
            )
        }
        board = game.computed_board()
        return [
            permanent
            for permanent in game.battlefield
            if board.of(permanent).is_creature and wanted & set(board.of(permanent).colors)
        ]
    type_filter_match = _MASS_TYPE_FILTER_RE.match(text.strip())
    if type_filter_match is not None:
        wanted_type = Type(type_filter_match.group("type").lower())
        base_selector = (
            creatures_controlled_by(controller)
            if type_filter_match.group("whose") == "you control"
            else creatures_controlled_by_opponents_of(controller)
        )
        board = game.computed_board()
        return [
            permanent
            for permanent in game.battlefield
            if base_selector(board.of(permanent), board.characteristics)
            and wanted_type in board.of(permanent).types
        ]
    word_filter = _mass_word_filter(text)
    if word_filter is not None:
        word_match, matches = word_filter
        base_selector = (
            creatures_controlled_by(controller)
            if word_match.group("whose") == "you control"
            else creatures_controlled_by_opponents_of(controller)
        )
        board = game.computed_board()
        return [
            permanent
            for permanent in game.battlefield
            if base_selector(board.of(permanent), board.characteristics)
            and matches(board.of(permanent))
        ]
    power_filter_match = _MASS_POWER_FILTER_RE.match(text.strip())
    if power_filter_match is not None:
        # Smuggler's Surprise / Gustrider Exuberant's own "with power N or
        # greater" - read **before** the plain-prefix `startswith` chain
        # below, which would otherwise treat this filtered subject as if it
        # read the bare "creatures you control" (a startswith match) and
        # silently drop the power restriction, sweeping in every creature
        # rather than only the big ones.
        minimum_power = parse_count(power_filter_match.group("power"), article=False)
        if minimum_power is None:
            return None
        base_selector = (
            other_creatures_controlled_by(source_id, controller)
            if power_filter_match.group("other")
            else (
                creatures_controlled_by(controller)
                if power_filter_match.group("whose") == "you control"
                else creatures_controlled_by_opponents_of(controller)
            )
        )
        board = game.computed_board()
        return [
            permanent
            for permanent in game.battlefield
            if base_selector(board.of(permanent), board.characteristics)
            and (board.of(permanent).power or 0) >= minimum_power
        ]
    group_filter = _mass_group_filter(text)
    if group_filter is not None:
        group_match, matches = group_filter
        board = game.computed_board()
        you = group_match.group("whose") == "you control"
        return [
            permanent
            for permanent in game.battlefield
            if (
                board.of(permanent).controller == controller
                if you
                else board.of(permanent).controller not in (None, controller)
            )
            and matches(board.of(permanent))
        ]
    if _MASS_OTHER_CREATURES_RE.match(text.strip()) is not None:
        # Harvester of Misery's "other creatures" / Shefet Archfiend's "all
        # other creatures": every creature on the battlefield but the source,
        # fixed now (CR 611.2c).
        board = game.computed_board()
        return [
            permanent
            for permanent in game.battlefield
            if board.of(permanent).is_creature and permanent.id != source_id
        ]
    opening = text.strip().lower()
    # Ravenous Robots: "Creature tokens you control gain haste until end of
    # turn." - CR 111.1's token-ness (`is_token`) narrowing the ordinary
    # "creatures [you|your opponents] control" selectors, the identical
    # "one more check on top, known only here off the literal text" shape
    # `_MASS_SUBTYPE_SUBJECT_RE`'s own subtype filter already uses. Checked
    # ahead of the plain "creatures ..." `startswith` chain below, whose
    # narrower literal ("creatures", not "creature tokens") never matches
    # this subject anyway, but is kept in its own branch rather than folded
    # in for the same reason the subtype filter above is: a token filter is a
    # second, independent narrowing, not a fifth base selector.
    if opening.startswith("creature tokens you control"):
        base_selector = creatures_controlled_by(controller)
        board = game.computed_board()
        return [
            permanent
            for permanent in game.battlefield
            if base_selector(board.of(permanent), board.characteristics) and is_token(permanent)
        ]
    if opening.startswith("creature tokens your opponents control"):
        base_selector = creatures_controlled_by_opponents_of(controller)
        board = game.computed_board()
        return [
            permanent
            for permanent in game.battlefield
            if base_selector(board.of(permanent), board.characteristics) and is_token(permanent)
        ]
    if opening.startswith("other creatures you control"):
        selector = other_creatures_controlled_by(source_id, controller)
    elif opening.startswith("creatures you control"):
        selector = creatures_controlled_by(controller)
    elif opening.startswith("creatures your opponents control"):
        selector = creatures_controlled_by_opponents_of(controller)
    elif opening.startswith("all creatures"):
        # Toxic Deluge's own "All creatures get -X/-X until end of turn." -
        # no controller restriction at all, unlike the three shapes above.
        selector = every_creature
    elif opening.startswith("permanents you control"):
        # Veil of Summer's own group half, once its compound "You and
        # permanents you control" subject is split (CR 403.3: every object
        # on the battlefield is a permanent) - the identical selector
        # `Game.condition_holds`'s own "you control a [quality]" branch
        # reaches for a whole-board count, not narrowed to creatures the
        # way every subject above it is.
        selector = all_permanents_controlled_by(controller)
    else:
        return None
    board = game.computed_board()
    return [
        permanent
        for permanent in game.battlefield
        if selector(board.of(permanent), board.characteristics)
    ]


#: A mass pump's magnitude, read once at resolution: `(game, controller,
#: source_id) -> int`.
MassPumpMagnitude = Callable[["Game", str, str | None], int]

#: "Until end of turn, creatures you control ..." (Nissa, Ascended Animist's
#: -7, Tromp the Domains) - the duration printed first, moved to the end so
#: the sentence reads the way every other mass pump here is templated.
_MASS_PUMP_DURATION_FIRST_RE = re.compile(r"^until end of turn,\s*(?P<rest>.+?)\.?$", re.IGNORECASE)
#: "get +1/+1 for each Forest you control" inside a mass pump (Nissa's -7) -
#: the pump scaled by a count taken once as it resolves (CR 608.2h), read by
#: `_for_each_multiplier`. The count ends where the sentence's next predicate
#: ("and gain ...") or its duration begins.
_MASS_PUMP_FOR_EACH_RE = re.compile(
    r"\bget (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) for each (?P<each>.+?)"
    r"(?= and gain | until end of turn)",
    re.IGNORECASE,
)
#: The scaled placeholder `_MASS_PUMP_FOR_EACH_RE` leaves in a template -
#: "+1*X" - substituted with the per-unit amount times the count.
_SCALED_X_RE = re.compile(r"(?P<unit>[+-]\d+)\*x", re.IGNORECASE)


def _substitute_mass_pump_magnitude(template: str, magnitude: int) -> str:
    """ "+X/+X" and "+N*X" placeholders written out for `magnitude`."""
    literal = re.sub(r"\+x/\+x", f"{magnitude:+d}/{magnitude:+d}", template, flags=re.IGNORECASE)
    return _SCALED_X_RE.sub(lambda m: f"{int(m.group('unit')) * magnitude:+d}", literal)


def _parse_mass_pump_clause(
    effect_text: str,
) -> tuple[str, MassPumpMagnitude | None, str] | None:
    """The mass-pump sentence, as a template with a literal "+N/+N" already in
    it (`magnitude_expr` is `None`) or with "+X/+X" still in it and a
    `count_expression` to resolve it later (`magnitude_expr` is not `None`),
    plus whatever sibling sentence follows it (`""` when there is none) - or
    `None` if `effect_text`'s own first sentence is not this shape at all, or
    names a "where X is ..." expression `count_expression` cannot read.

    Requires an explicit "until end of turn": without it, "Creatures you
    control get +1/+1." is Glorious Anthem's own CR 611.3 anthem - a
    permanent's forever-lasting static ability, not a CR 611.2 one-shot
    effect - and `Game.resolve_top` calls `effect_for` for *every* resolving
    spell, permanents included, so returning an effect here for that shape
    would store a second, durational copy of the same anthem on top of the
    one `effects_for`'s per-permanent battlefield sweep already reapplies on
    its own every time the board is computed (CR 613.5), doubling the bonus -
    exactly the trap `is_resolution_layer_effect_text`'s own docstring
    documents for why it excludes the anthem shape.

    Read off `effect_text`'s own **first sentence only** - not the whole,
    unsplit text the way this used to work, whose subject and duration checks
    were unanchored substring tests rather than a whole-text match: Artifist
    Acumen's own "Creatures you control gain first strike until end of turn.
    Draw a card." used to fold the trailing "Draw a card." silently into the
    returned template string, so the draw was never read by anything and
    never recorded as unread either. The caller (`_mass_pump_spell_effect`/
    `_mass_pump_ability_effect`) composes the returned remainder the same way
    `_compose_layer_effect_with_remainder` composes any other layer
    sentence's own sibling.
    """
    sentences = _plain_resolution_sentences(effect_text)
    text = sentences[0].strip() if sentences else effect_text.strip()
    remainder = " ".join(sentences[1:]) if len(sentences) > 1 else ""
    # A duration-first sentence is only claimed when the rest is a pump or
    # grant `machines/layers.py` reads (checked below) - "Until end of turn,
    # creatures you control gain "{1}: ..."" (Grand Evolution's chapter III)
    # belongs to the quoted-grant reader, not here.
    if duration_first := _MASS_PUMP_DURATION_FIRST_RE.fullmatch(text):
        text = f"{duration_first.group('rest')} until end of turn."
    if (
        _MASS_SUBJECT_RE.match(text) is None
        and _MASS_SUBTYPE_SUBJECT_RE.match(text) is None
        and _MASS_EACH_SUBJECT_RE.match(text) is None
        and _MASS_SUPERTYPE_SUBJECT_RE.match(text) is None
        and _MASS_TYPE_FILTER_RE.match(text) is None
        and _mass_word_filter(text) is None
        and _mass_group_filter(text) is None
        and not _is_mass_state_subject(text)
    ):
        return None
    if Duration.UNTIL_END_OF_TURN not in text.lower():
        return None
    where_match = _WHERE_X_IS_RE.search(text)
    for_each = _MASS_PUMP_FOR_EACH_RE.search(text)
    magnitude_expr: MassPumpMagnitude | None
    if where_match is not None:
        counted = count_expression(where_match.group("expr"))
        own = _source_characteristic_magnitude(where_match.group("expr"))
        if counted is None and own is None:
            return None
        if counted is not None:
            magnitude_expr = lambda game, controller, _source_id: counted(game, controller)  # noqa: E731
        else:
            magnitude_expr = own
        template = text[: where_match.start()].rstrip(", ").rstrip(".") + "."
        if "+x/+x" not in template.lower():
            return None
    elif for_each is not None:
        multiplier = _for_each_multiplier(for_each.group("each"))
        if multiplier is None:
            return None
        magnitude_expr = multiplier
        template = (
            text[: for_each.start()]
            + f"get {for_each.group('power')}*X/{for_each.group('toughness')}*X"
            + text[for_each.end() :]
        )
    else:
        template, magnitude_expr = text, None
    if duration_first is not None or _MASS_WHOLE_BOARD_SUBJECT_RE.match(template) is not None:
        # "All creatures ..." / "Creatures that are <colour> ..." (Glistening
        # Deluge) are claimed here only when the rest is a pump or grant
        # `machines/layers.py` reads: the same subject also opens sentences
        # that are no pump at all ("All creatures lose all abilities until
        # end of turn.", Final Showdown), which must keep failing closed
        # where they always have rather than pass as read.
        probe = _substitute_mass_pump_magnitude(template, 1)
        if parsed_layer_effects(_mass_pump_parseable(probe)) is None:
            return None
    return template, magnitude_expr, remainder


def _mass_pump_parseable(literal: str) -> str:
    """The mass-pump sentence `literal` as `machines/layers.py`'s own parser
    reads it: the group's filter (subtype, power, colour) stripped off the
    subject, since `_mass_creature_group_targets` has already applied it."""
    # `targets` is already the concrete, subtype-filtered group (CR 611.2c) -
    # `machines/layers.py`'s own parser only needs to recognise the *shape*
    # of what follows ("get +N/+N ... until end of turn"), which is templated
    # on the literal "creatures" subject. A bare CR 205.3m subtype standing
    # in for it (History of Benalia's "Knights you control") is rewritten to
    # that literal subject here, once, rather than teaching `machines/
    # layers.py` a second subject grammar it would then have to keep in step
    # with `_MASS_SUBTYPE_SUBJECT_RE` above.
    subtype_match = _MASS_SUBTYPE_SUBJECT_RE.match(literal.strip())
    power_filter_match = _MASS_POWER_FILTER_RE.match(literal.strip())
    color_filter_match = _MASS_COLOR_FILTER_RE.match(literal.strip())
    type_filter_match = _MASS_TYPE_FILTER_RE.match(literal.strip())
    each_match = _MASS_EACH_SUBJECT_RE.match(literal.strip())
    other_match = _MASS_OTHER_CREATURES_RE.match(literal.strip())
    state_match = (
        _MASS_STATE_SUBJECT_RE.match(literal.strip()) if _is_mass_state_subject(literal) else None
    )
    if state_match is not None:
        # The group (state, "other", controller) is already `targets`.
        parseable = "all creatures" + literal.strip()[state_match.end() :]
    elif other_match is not None:
        # "(All) other creatures get ..." - `targets` already excludes the
        # source, so the layer parser only needs the whole-board shape.
        parseable = "all creatures " + literal.strip()[other_match.end() :]
    elif each_match is not None:
        # The group (and its "other") is already `targets`; the layer parser
        # only needs the plural group shape.
        # "gets +1/+1 and gains trample" agrees with its plural subject.
        parseable = (
            f"creatures {each_match.group('whose')} {each_match.group('verb')[:-1]}"
            + re.sub(r"\bgains\b", "gain", literal.strip()[each_match.end() :])
        )
    elif (supertype_match := _MASS_SUPERTYPE_SUBJECT_RE.match(literal.strip())) is not None:
        # The snow filter is already applied to `targets`.
        parseable = "all creatures" + literal.strip()[supertype_match.end() :]
    elif color_filter_match is not None:
        # The colour filter, like the power filter below, is already applied
        # to `targets`; `machines/layers.py` only needs the group shape.
        parseable = "all creatures" + literal.strip()[color_filter_match.end() :]
    elif power_filter_match is not None:
        # The same rewrite, for a "with power N or greater" filter instead
        # of a subtype: `targets` already carries only the creatures that
        # met it (`_mass_creature_group_targets` above), so the filter
        # phrase itself is stripped before `machines/layers.py` ever sees
        # the sentence - its own `_MASS_PUMP_UNTIL_EOT_RE` knows the bare
        # "creatures you control"/"other creatures you control" subject, not
        # this one.
        prefix = "other creatures " if power_filter_match.group("other") else "creatures "
        parseable = (
            prefix + power_filter_match.group("whose") + literal.strip()[power_filter_match.end() :]
        )
    elif subtype_match is not None:
        parseable = "creatures " + literal.strip()[subtype_match.start("whose") :]
    elif type_filter_match is not None:
        # The card-type filter, like the power filter above: `targets`
        # already carries only the creatures of that type
        # (`_mass_creature_group_targets`), so the filter word itself is
        # stripped before `machines/layers.py` ever sees the sentence.
        parseable = "creatures " + literal.strip()[type_filter_match.start("whose") :]
    elif (word_filter := _mass_word_filter(literal)) is not None:
        # The colour/colorless/creature-type word is already applied to
        # `targets` (`_mass_creature_group_targets`), the same rewrite the
        # card-type filter above needs.
        parseable = "creatures " + literal.strip()[word_filter[0].start("whose") :]
    elif (group_filter := _mass_group_filter(literal)) is not None:
        # The card-type group is already `targets`; the layer parser only
        # needs the plural "creatures" shape.
        parseable = "creatures " + literal.strip()[group_filter[0].start("whose") :]
    elif (token_match := _MASS_TOKEN_SUBJECT_RE.match(literal.strip())) is not None:
        # Ravenous Robots: "Creature tokens you control gain haste until end
        # of turn." - `targets` (`_mass_creature_group_targets`) already
        # carries only the tokens (CR 111.1); `machines/layers.py`'s own
        # `_MASS_PUMP_UNTIL_EOT_RE` only knows the bare "creatures ..."
        # subject, the same rewrite the subtype filter above already needs.
        parseable = "creatures " + literal.strip()[token_match.start("whose") :]
    else:
        parseable = literal
    # `parsed_layer_effects` reads `_effect_sentences`, which needs a real
    # sentence terminator to recognise anything at all - fine for a whole,
    # unsplit ability effect (still carries its own printed period), but
    # `literal` can also arrive here already trimmed of one: `_parse_mass_
    # pump_group_clause` calls this on a single clause `split_effect_
    # clauses` has already cut apart (and that splitter always strips a
    # trailing "."), Ingris Stingerquill's "Then creatures you control gain
    # haste until end of turn." among them.
    if not parseable.rstrip().endswith("."):
        parseable = parseable.rstrip() + "."
    return parseable


def _run_mass_pump(
    game: "Game",
    source: CardState,
    controller: str,
    template: str,
    magnitude_expr: MassPumpMagnitude | None,
    restrict: Callable[[CardState], bool] | None = None,
) -> list[CardState]:
    """Resolve one mass-pump clause: substitute its magnitude (if it has one),
    fix the group of creatures it affects, and hand the literal sentence to
    `machines/layers.py`'s own parser - the same `parsed_layer_effects` every
    other continuous effect in this file goes through, not a second
    ContinuousEffect-building path (Craterhoof's trample grant still lives or
    dies by `_KNOWN_KEYWORDS`'s whitelist there).

    Returns the group the sentence's own antecedent found (CR 611.2c fixes it
    once, right here) - empty when there was nobody to affect at all, but
    still the group when the sentence's own predicate could not be built
    (recorded as a `LayerNotice` instead), so a caller composing a sibling
    "... on each of them" instruction (Summon: Knights of Round's chapter V)
    can still find who "them" is even on that path.

    Trap: the magnitude is read **once**, right here, into a plain `int` -
    never carried forward as `magnitude_expr` itself - so a creature that
    enters after this resolves cannot retroactively grow Craterhoof's own
    pump the way `set_power_toughness_to_mana_value`'s live re-read
    deliberately does for Karn's ability (CR 611.2c fixes both the group and
    the number the moment the effect begins).
    """
    literal = template
    if magnitude_expr is not None:
        literal = _substitute_mass_pump_magnitude(
            literal, magnitude_expr(game, controller, str(source.id))
        )
    targets = _mass_creature_group_targets(game, controller, source.id, literal)
    if targets and restrict is not None:
        targets = [creature for creature in targets if restrict(creature)]
    if not targets:
        return []
    parseable = _mass_pump_parseable(literal)
    builder = parsed_layer_effects(parseable)
    if builder is None:
        # A keyword outside `_KNOWN_KEYWORDS`'s whitelist, or some other shape
        # this wave's parser cannot read - fail closed rather than silently
        # doing nothing (the same "unreadable is not the same as no effect"
        # rule every other `LayerNotice` site in this file already keeps).
        continuous_effects(game).layer_notices.append(
            LayerNotice(source_id=source.id, source_name=source.name, text=literal)
        )
        return targets
    store = continuous_effects(game)
    timestamp = store.tick()
    context = layer_context_for(game, game.player(controller))
    for built in builder(source, timestamp, targets, context):
        if built.holds(game):
            store.add(built)
    return targets


#: "If `<condition>`, those creatures get `<A>`/`<B>` until end of turn
#: instead." - Pride of Conquerors' own city's-blessing upgrade ("Creatures
#: you control get +1/+1 until end of turn. If you have the city's blessing,
#: those creatures get +2/+2 until end of turn instead.") and Dauntless
#: Unity's identically shaped kicker one ("... get +1/+1 until end of turn.
#: If this spell was kicked, those creatures get +2/+1 until end of turn
#: instead."). The mass-pump twin of `_parse_layer_counter_instead_upgrade`'s
#: single-target "put N counters on it instead" (CR 614.1a: "instead"
#: replaces the whole preceding sentence's effect, never adds to it) - here
#: the replacement is a bigger pump on the *same* group the leading
#: sentence's own antecedent found, never a counter. `Game.condition_holds`
#: already answers the condition itself; this only reads which magnitude
#: applies to the group `_run_mass_pump` already knows how to find.
_MASS_PUMP_INSTEAD_UPGRADE_RE = re.compile(
    r"^if (?P<condition>.+?),\s*those creatures get "
    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of turn instead$",
    re.IGNORECASE,
)

#: A literal "+N/+N" pump already substituted into a mass-pump template
#: (never the still-unsubstituted "+X/+X" placeholder, which only a `where X
#: is ...`/`for each` clause leaves behind and which `_MASS_PUMP_INSTEAD_
#: UPGRADE_RE`'s own caller never reaches for - see its `magnitude_expr is
#: None` guard) - replaced once, by the upgrade's own numbers.
_MASS_PUMP_LITERAL_PT_RE = re.compile(r"[+-]\d+/[+-]\d+")


def _parse_mass_pump_instead_upgrade(remainder_text: str) -> tuple[str, int, int] | None:
    """`_MASS_PUMP_INSTEAD_UPGRADE_RE`'s shape, or `None`."""
    match = _MASS_PUMP_INSTEAD_UPGRADE_RE.fullmatch(remainder_text.strip().rstrip(".").strip())
    if match is None:
        return None
    return (
        match.group("condition").strip(),
        int(match.group("power")),
        int(match.group("toughness")),
    )


def _mass_pump_instead_upgrade_template(template: str, power: int, toughness: int) -> str:
    """`template`'s own literal pump, replaced by the upgrade's `power`/
    `toughness` - the same group `_mass_creature_group_targets` finds either
    way, since nothing about who is affected changes, only how much."""
    return _MASS_PUMP_LITERAL_PT_RE.sub(f"{power:+d}/{toughness:+d}", template, count=1)


#: "Put `<n>` `<kind>` counter(s) on each of them." after a mass pump or
#: grant - Summon: Knights of Round's own chapter V ("Other creatures you
#: control get +2/+2 until end of turn. Put an indestructible counter on
#: each of them.") and Age of Ultron's chapter III ("Artifact creatures you
#: control gain deathtouch until end of turn. Put a +1/+1 counter on each of
#: them."). Additive (CR 608.2c: a further instruction, not a CR 614.1a
#: "instead" swap) - the counters land on the exact group the leading
#: sentence's own antecedent already found (`_run_mass_pump`'s own return),
#: whatever that group's subject or filter, never re-derived from the
#: rider's own words.
_MASS_PUMP_COUNTER_ON_EACH_RE = re.compile(
    rf"^put {count_pattern('n')} (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on each of them$",
    re.IGNORECASE,
)


def _parse_mass_pump_counter_on_each(remainder_text: str) -> tuple[int, "Counter | str"] | None:
    """`_MASS_PUMP_COUNTER_ON_EACH_RE`'s shape, or `None`."""
    match = _MASS_PUMP_COUNTER_ON_EACH_RE.fullmatch(remainder_text.strip().rstrip(".").strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    return amount, _counter_kind(match.group("kind"))


@ABILITY_TEXT.rung("s36", before=["amounts._parse_where_x_is_continuous_effect"])
def _mass_pump_ability_effect(effect_text: str) -> AbilityEffect | None:
    """Craterhoof Behemoth's own ETB shape: a mass pump read whole off a
    resolving *ability's* text, with `ability.controller` and its own source.

    A sibling sentence after the pump (`remainder`) is composed the same way
    `_compose_layer_effect_with_remainder_for_ability` composes any other
    layer sentence's own remainder - run in printed order (CR 608.2c) when it
    parses, recorded as a `LayerRemainderNotice` when it does not, rather
    than silently folded into (and lost inside) the pump's own template the
    way it used to be. Two shapes are read ahead of that ordinary "any other
    instruction" fallback: a "those creatures get ... instead" magnitude
    upgrade (`_parse_mass_pump_instead_upgrade`) and a "counter on each of
    them" addition (`_parse_mass_pump_counter_on_each`), both keyed to the
    exact same group the pump itself already found rather than to a second,
    independently-resolved one.
    """
    parsed = _parse_mass_pump_clause(effect_text)
    if parsed is None:
        return None
    template, magnitude_expr, remainder = parsed

    gated = mass_pump_conditions.rider_effect(template, remainder, magnitude_expr, _run_mass_pump)
    if gated is not None:

        def gated_ability_effect(game: "Game", ability: AbilityOnStack) -> None:
            source = ability.source(game)
            if source is not None:
                gated(game, source, ability.controller, ability)

        return gated_ability_effect

    instead_upgrade = (
        _parse_mass_pump_instead_upgrade(remainder)
        if remainder and magnitude_expr is None
        else None
    )
    if instead_upgrade is not None:
        condition_text, up_power, up_toughness = instead_upgrade
        upgraded_template = _mass_pump_instead_upgrade_template(template, up_power, up_toughness)

        def instead_effect(game: "Game", ability: AbilityOnStack) -> None:
            source = ability.source(game)
            if source is None:
                return
            holds = game.condition_holds(
                ability.controller,
                condition_text,
                source,
                ability=ability.ability,
                event=ability.event,
                source_stamp=ability.source_stamp,
            )
            chosen = upgraded_template if holds else template
            _run_mass_pump(game, source, ability.controller, chosen, None)
            if holds is None:
                game.layer_remainder_notices.append(
                    LayerRemainderNotice(
                        source_id=ability.source_id,
                        source_name=ability.source_name,
                        text=remainder,
                    )
                )

        from .. import conditions

        if conditions.claims(condition_text):
            return instead_effect
        return _with_unparsed_remainder(instead_effect, remainder)

    counter_on_each = _parse_mass_pump_counter_on_each(remainder) if remainder else None
    if counter_on_each is not None:
        counter_amount, counter_kind = counter_on_each

        def counter_effect(game: "Game", ability: AbilityOnStack) -> None:
            source = ability.source(game)
            if source is None:
                return
            targets = _run_mass_pump(game, source, ability.controller, template, magnitude_expr)
            for target in targets:
                if target.zone is Zone.BATTLEFIELD:
                    game.add_counters(target, counter_kind, counter_amount)

        return counter_effect

    if followup := mass_pump_followups.ability_effect(remainder, template, magnitude_expr):
        return followup

    remainder_effect = (
        (turn_scoped_rider(remainder, for_spell=False) or parse_mixed_effect(remainder))
        if remainder
        else None
    )

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        pumped = _run_mass_pump(game, source, ability.controller, template, magnitude_expr)
        if not remainder:
            return
        if remainder_effect is not None:
            run_with_antecedent(game, ability, remainder_effect, pumped)
        else:
            game.layer_remainder_notices.append(
                LayerRemainderNotice(
                    source_id=ability.source_id, source_name=ability.source_name, text=remainder
                )
            )

    if remainder and remainder_effect is None:
        return _with_unparsed_remainder(effect, remainder)
    return effect


#: Converge (CR 207.2c), a mass-pump trigger scaled by "that spell"'s own
#: colors spent: Magmablood Archaic's own "Whenever you cast an instant or
#: sorcery spell, creatures you control get +1/+0 until end of turn for each
#: color of mana spent to cast that spell." Read as its own whole-text shape,
#: ahead of `_mass_pump_ability_effect` (`_parse_mass_pump_clause`'s own
#: "get +N/+N for each `<count>`" reader, `_MASS_PUMP_FOR_EACH_RE`), because
#: this prints the duration *before* the "for each" tail rather than after
#: it - the one word order `_MASS_PUMP_FOR_EACH_RE`'s lookahead does not
#: reach - and because `MassPumpMagnitude`'s own `(game, controller,
#: source_id) -> int` signature has no way to name "that spell" at all: its
#: only handle on the board is the *ability's* own source (Magmablood
#: itself), never the spell whose casting triggered it. Generalised over the
#: printed subject ("creatures you control" / "other creatures you
#: control") and the per-color unit pump, not fixed to +1/+0.
_PUMP_FOR_EACH_COLOR_SPENT_ON_THAT_SPELL_RE = re.compile(
    r"^(?P<subject>other creatures you control|creatures you control) get "
    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of turn for each color of mana spent "
    r"to cast (?:that|this) spell\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s35")
def _parse_pump_for_each_color_spent_on_that_spell_clause(effect_text: str) -> AbilityEffect | None:
    """`_PUMP_FOR_EACH_COLOR_SPENT_ON_THAT_SPELL_RE`'s shape, or `None`.

    The magnitude is worked out once, here, off "that spell"'s own
    `CastRecord` (`ability.event.subject_id`, `machines/converge.colors_of_
    mana_spent`) while it is still on the stack (CR 603.3b: the trigger
    resolves before the spell that caused it), then handed to `_run_mass_
    pump` as an already-substituted literal template - the identical
    "compute it myself, then reuse the shared applier" shape `Toxic Deluge`'s
    own additional-cost-X mass debuff already uses for a magnitude
    `MassPumpMagnitude` cannot express.
    """
    match = _PUMP_FOR_EACH_COLOR_SPENT_ON_THAT_SPELL_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    unit_power = int(match.group("power"))
    unit_toughness = int(match.group("toughness"))
    subject = match.group("subject").lower()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if not isinstance(spell, CardState):
            return
        colors_spent = colors_of_mana_spent(game, spell)
        if colors_spent <= 0:
            return
        source = ability.source(game)
        if source is None:
            return
        template = (
            f"{subject} get {unit_power * colors_spent:+d}/{unit_toughness * colors_spent:+d} "
            "until end of turn."
        )
        _run_mass_pump(game, source, ability.controller, template, None)

    return effect


#: Threaten's whole effect: "Untap target creature and gain control of it
#: until end of turn. That creature gains haste until end of turn."
#:
#: Three instructions in two sentences, and the first sentence is the reason
#: this has to be read whole: it carries a one-shot untap (CR 701.26b, "to
#: untap a permanent, rotate it back to the upright position") *and* a layer 2
#: continuous effect (CR 613.1b, "Layer 2: Control-changing effects are
#: applied") joined by a bare "and". `split_effect_clauses` cuts there, and
#: the resulting "gain control of it until end of turn" names its object with
#: a pronoun no clause parser can resolve on its own - so the sentence is
#: matched here and each half handed to the parser that owns it.
_UNTAP_AND_GAIN_CONTROL_RE = re.compile(
    r"^untap (?P<phrase>target creature[^.]*?) and gain control of it until end of turn\.\s*"
    r"that creature gains (?P<keywords>[a-z][a-z, ]*?) until end of turn\.?$",
    re.IGNORECASE,
)


#: Act of Treason's order of the same three instructions: "Gain control of
#: target creature until end of turn. Untap that creature. It gains haste until
#: end of turn." Printed on spells (Claim the Firstborn; Hijack's "Untap it.";
#: Metallic Mastery's "Untap that artifact."), activated abilities (Captivating
#: Crew) and triggered ones (Conquering Manticore) alike. `parsed_layer_effects`
#: read only the first sentence of it and skipped the other two without a
#: notice, so the stolen creature stayed tapped and never gained haste.
#:
#: Eldrazi Obligator prints the identical three instructions inside one
#: comma-joined sentence rather than Act of Treason's three full stops -
#: "gain control of target creature until end of turn, untap that creature,
#: and it gains haste until end of turn." (it is the *consequence* half of
#: its own "you may pay `{1}{C}`. If you do, ..." cast trigger, CR 118.12,
#: read by `pay_consequence_effect` below) - so each separator between the
#: three clauses accepts either punctuation: a full stop, or a comma with an
#: optional "and".
_GAIN_CONTROL_THEN_UNTAP_RE = re.compile(
    r"^gain control of (?P<phrase>target [^.,]*?) until end of turn(?:\.\s*|,\s*)"
    r"untap (?:it|that (?:creature|permanent|artifact))(?:\.\s*|,\s*(?:and\s+)?)"
    r"(?:it|that (?:creature|permanent|artifact)) gains (?P<keywords>[a-z][a-z, ]*?) "
    r"until end of turn\.?$",
    re.IGNORECASE,
)

#: Reminder text and an activated ability's own timing instruction are not
#: part of the effect (CR 207.2a reminder text; CR 602.5d "Activate only as a
#: sorcery").
_REMINDER_OR_ACTIVATION_RULE_RE = re.compile(r"\([^)]*\)|\bactivate only [^.]*\.", re.IGNORECASE)


def _gain_control_untap_grant(effect_text: str) -> tuple[str, str] | None:
    """The two layer sentences of either word order - Threaten's
    (`_UNTAP_AND_GAIN_CONTROL_RE`) or Act of Treason's
    (`_GAIN_CONTROL_THEN_UNTAP_RE`) - or `None` if `effect_text` is neither.

    The continuous halves are rewritten back into the sentences
    `machines/layers.py` reads on their own - "gain control of target creature
    until end of turn." and "target creature gains haste until end of turn."
    - and built against the targets actually chosen (CR 611.2c fixes that set
    now). "it" and "that creature" are anaphora back to the one target the
    first instruction named, and that object is already in hand at resolution.
    """
    text = " ".join(_REMINDER_OR_ACTIVATION_RULE_RE.sub(" ", effect_text).split())
    for pattern in (_UNTAP_AND_GAIN_CONTROL_RE, _GAIN_CONTROL_THEN_UNTAP_RE):
        match = pattern.fullmatch(text)
        if match is not None:
            break
    else:
        return None
    if not _targets_understood(match.group("phrase").strip()):
        return None
    # The printed phrase was checked at announcement (CR 601.2c) and the
    # builders act on the targets handed to them, so the sentences only need a
    # subject `machines/layers.py` reads: "target creature with mana value 3
    # or less" and "target artifact or creature" would each read as nothing.
    return (
        "gain control of it until end of turn.",
        f"target creature gains {match.group('keywords').strip()} until end of turn.",
    )


def _untap_and_apply_control_sentences(
    game: "Game",
    source: CardState,
    controller: "Player",
    targets: Sequence[CardState],
    sentences: tuple[str, str],
) -> None:
    """Untap each target still on the battlefield (CR 701.26b), then create the
    control change (CR 613.1b) and the keyword grant against them. A sentence
    the layer parser cannot read leaves a `LayerNotice` rather than silently
    doing nothing."""
    targets = [target for target in targets if target.zone is Zone.BATTLEFIELD]
    if not targets:
        return  # CR 608.2b: no legal target left, so none of this happens.
    for target in targets:
        target.untap()  # CR 701.26b
    store = continuous_effects(game)
    context = layer_context_for(game, controller)
    for sentence in sentences:
        builder = parsed_layer_effects(sentence)
        if builder is None:
            store.layer_notices.append(
                LayerNotice(source_id=source.id, source_name=source.name, text=sentence)
            )
            continue
        timestamp = store.tick()
        for built in builder(source, timestamp, targets, context):
            if built.holds(game):
                store.add(built)


def _apply_layer_sentences(
    game: "Game",
    source: CardState,
    controller: "Player",
    targets: Sequence[CardState],
    sentence: str,
) -> None:
    """Build `sentence`'s continuous effects over `targets` (fixed now, CR 611.2c)
    and keep them; one the layer parser cannot read leaves a `LayerNotice`."""
    store = continuous_effects(game)
    builder = parsed_layer_effects(sentence)
    if builder is None:
        store.layer_notices.append(
            LayerNotice(source_id=source.id, source_name=source.name, text=sentence)
        )
        return
    context = layer_context_for(game, controller)
    for built in builder(source, store.tick(), targets, context):
        if built.holds(game):
            store.add(built, game)


#: "Target artifact becomes an artifact creature. If it isn't a Vehicle, it has
#: base power and toughness 4/4." (Tezzeret, Betrayer of Flesh) - a type change
#: and a conditional base power and toughness. The condition is one instruction
#: checked as the ability resolves (CR 608.2c), against the target as it then
#: is, so a Vehicle keeps the power and toughness it prints (CR 301.7) while
#: any other artifact is set to the stated base (CR 613.4b). Neither half names
#: a duration, so both last (CR 611.2a).
_BECOMES_THEN_BASE_PT_UNLESS_SUBTYPE_RE = re.compile(
    r"^(?P<first>target [a-z]+ becomes an? [a-z ]+?)\.\s*"
    r"if it isn't an? (?P<subtype>[a-z]+), it has base power and toughness "
    r"(?P<power>\d+)/(?P<toughness>\d+)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s14")
def _parse_becomes_then_base_pt_unless_subtype(effect_text: str) -> AbilityEffect | None:
    """`_BECOMES_THEN_BASE_PT_UNLESS_SUBTYPE_RE`'s shape."""
    match = _BECOMES_THEN_BASE_PT_UNLESS_SUBTYPE_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    first = match.group("first") + "."
    power, toughness = match.group("power"), match.group("toughness")
    second = f"Target creature has base power and toughness {power}/{toughness}."
    if parsed_layer_effects(first) is None or parsed_layer_effects(second) is None:
        return None
    subtype = canonical_subtype(match.group("subtype"))
    if subtype is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        targets = [t for t in game.resolve_card_targets(ability) if t.zone is Zone.BATTLEFIELD]
        if source is None or not targets:
            return  # CR 608.2b: no legal target left
        controller = game.controller_of(ability)
        _apply_layer_sentences(game, source, controller, targets, first)
        board = game.computed_board()
        others = [
            t
            for t in targets
            if subtype.lower() not in {name.lower() for name in board.of(t).subtypes}
        ]
        if others:
            _apply_layer_sentences(game, source, controller, others, second)

    return effect


#: "Target land you control becomes the basic land type of your choice until end
#: of turn." (Pixie Illusionist) - the choice is made as the ability resolves
#: (CR 608.2d), then it is "becomes an Island until end of turn": CR 305.7's
#: setting effect, so the land keeps no old land type or rules-text ability.
_BECOMES_CHOSEN_BASIC_LAND_TYPE_RE = re.compile(
    r"^(?P<subject>target land(?: you control)?) becomes the basic land type of your choice"
    r"(?P<until> until end of turn)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s14")
def _parse_becomes_chosen_basic_land_type(effect_text: str) -> AbilityEffect | None:
    """`_BECOMES_CHOSEN_BASIC_LAND_TYPE_RE`'s shape."""
    match = _BECOMES_CHOSEN_BASIC_LAND_TYPE_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    until = match.group("until") or ""

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        targets = [t for t in game.resolve_card_targets(ability) if t.zone is Zone.BATTLEFIELD]
        if source is None or not targets:
            return
        controller = game.controller_of(ability)
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=controller.username,
                prompt="choose a basic land type",
                source=ability.source_name,
                source_id=source_id_of(ability),
                options=tuple(BASIC_LAND_TYPES),
                quality="basic land type",
            )
        )
        if chosen not in BASIC_LAND_TYPES:
            return
        sentence = f"Target land becomes {with_indefinite_article(str(chosen))}{until}."
        _apply_layer_sentences(game, source, controller, targets, sentence)

    return effect


@SPELL_TEXT.rung("s14")
def _parse_untap_and_gain_control_clause(effect_text: str) -> Effect | None:
    """A spell printing either word order of "gain control of target creature
    until end of turn, untap it, it gains haste until end of turn" - Threaten,
    Act of Treason, Claim the Firstborn, Hijack - or `None`."""
    sentences = _gain_control_untap_grant(effect_text)
    if sentences is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        targets = [
            target for target in game.resolve_targets(spell) if isinstance(target, CardState)
        ]
        _untap_and_apply_control_sentences(
            game, spell, game.controller_of(spell), targets, sentences
        )

    return effect


@ABILITY_TEXT.rung("s14")
def _parse_untap_and_gain_control_ability(effect_text: str) -> AbilityEffect | None:
    """The same effect printed on an activated or triggered ability -
    Captivating Crew's "{3}{R}: ...", Conquering Manticore's "When this
    creature enters, ..." - or `None`. The ability's source card is what the
    continuous effects are recorded against; the targets are rechecked on
    resolution (CR 608.2b) the way a spell's are."""
    sentences = _gain_control_untap_grant(effect_text)
    if sentences is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        # CR 113.7a: the ability does not need its source to still exist; the
        # continuous effects are recorded against its last known information.
        source = ability.source_or_last_known(game)
        if source is None:
            continuous_effects(game).layer_notices.append(
                LayerNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=f"{effect_text} (its source and its last known information are both gone)",
                )
            )
            return
        _untap_and_apply_control_sentences(
            game, source, game.controller_of(ability), game.resolve_card_targets(ability), sentences
        )

    return effect


#: "Gain control of all artifacts your opponents control until end of turn.
#: Untap them. They gain haste until end of turn." (Broadcast Takeover);
#: "Gain control of all creatures with power 4 or greater until end of turn.
#: Untap those creatures. They gain haste until end of turn." (Mob Rule's
#: modes) - Act of Treason's three instructions over an untargeted group
#: (CR 115.10a) rather than one target. The anaphors ("them", "those
#: `<nouns>`", "they") all name the group the first sentence took.
_MASS_GAIN_CONTROL_UNTAP_RE = re.compile(
    r"^gain control of all (?P<group>[^.]+?) until end of turn\.\s*"
    r"untap (?:them|those [a-z]+)\.\s*"
    r"(?:they|those [a-z]+) gain (?P<keywords>[a-z][a-z, ]*?) until end of turn\.?$",
    re.IGNORECASE,
)


def _parse_mass_gain_control_untap(
    effect_text: str,
) -> Callable[["Game", CardState, "Player"], None] | None:
    """`_MASS_GAIN_CONTROL_UNTAP_RE`'s shape as `(game, source, controller)`,
    or `None`.

    The group is read once, off the computed board, as the spell or ability
    resolves (CR 611.2c: the set a control-changing continuous effect affects
    "is determined when that continuous effect begins. After that point, the
    set won't change"), then handed to `_untap_and_apply_control_sentences` -
    Act of Treason's own untap (CR 701.26b), layer 2 control change
    (CR 613.1b) and layer 6 keyword grant (CR 613.1f), each until end of turn
    (CR 514.2), applied to that fixed set exactly as it applies them to a
    chosen target.
    """
    text = " ".join(_REMINDER_OR_ACTIVATION_RULE_RE.sub(" ", effect_text).split())
    match = _MASS_GAIN_CONTROL_UNTAP_RE.fullmatch(text)
    if match is None:
        return None
    predicate = _mass_control_group(match.group("group"))
    if predicate is None:
        return None
    sentences = (
        "gain control of it until end of turn.",
        f"target creature gains {match.group('keywords').strip()} until end of turn.",
    )

    def apply(game: "Game", source: CardState, controller: "Player") -> None:
        group = [
            permanent
            for permanent in list(game.battlefield)
            if predicate(game, permanent, controller.username)
        ]
        _untap_and_apply_control_sentences(game, source, controller, group, sentences)

    return apply


@SPELL_TEXT.rung("s14")
def _parse_mass_gain_control_untap_clause(effect_text: str) -> Effect | None:
    """`_parse_mass_gain_control_untap` on a resolving spell (Broadcast
    Takeover, each of Mob Rule's modes)."""
    apply = _parse_mass_gain_control_untap(effect_text)
    if apply is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        apply(game, spell, game.controller_of(spell))

    return effect


@ABILITY_TEXT.rung("s14")
def _parse_mass_gain_control_untap_ability(effect_text: str) -> AbilityEffect | None:
    """The same effect on an activated or triggered ability (a planeswalker's
    "-9: Gain control of all creatures until end of turn. Untap them. They
    gain haste until end of turn."), recorded against the source's last known
    information (CR 113.7a) the way `_parse_untap_and_gain_control_ability`
    records its own."""
    apply = _parse_mass_gain_control_untap(effect_text)
    if apply is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        if source is None:
            return
        apply(game, source, game.controller_of(ability))

    return effect


@SPELL_TEXT.rung("s21")
def _mass_pump_spell_effect(effect_text: str) -> Effect | None:
    """Violent Outburst's own pump line, the spell-side twin of
    `_mass_pump_ability_effect` above - its cascade half is unaffected (CR
    702.85a's exile-hit-free-cast pipeline reads no part of this sentence).

    Composes a sibling sentence after the pump the same way
    `_mass_pump_ability_effect` does - Artifist Acumen's own "Draw a card." -
    including that function's own two group-scoped shapes ahead of the
    ordinary fallback: Pride of Conquerors' and Dauntless Unity's own "those
    creatures get ... instead" magnitude upgrade, and a "counter on each of
    them" addition (neither reported for a pool spell yet, but the identical
    sentence shape a spell prints exactly as an ability does - `_parse_mass_
    pump_clause`/`_run_mass_pump` are already shared between the two, so the
    read is too).
    """
    parsed = _parse_mass_pump_clause(effect_text)
    if parsed is None:
        return None
    template, magnitude_expr, remainder = parsed

    gated = mass_pump_conditions.rider_effect(template, remainder, magnitude_expr, _run_mass_pump)
    if gated is not None:

        def gated_spell_effect(game: "Game", spell: CardState) -> None:
            gated(game, spell, game.controller_of(spell).username, None)

        return gated_spell_effect

    instead_upgrade = (
        _parse_mass_pump_instead_upgrade(remainder)
        if remainder and magnitude_expr is None
        else None
    )
    if instead_upgrade is not None:
        condition_text, up_power, up_toughness = instead_upgrade
        upgraded_template = _mass_pump_instead_upgrade_template(template, up_power, up_toughness)

        def instead_effect(game: "Game", spell: CardState) -> None:
            controller = game.controller_of(spell).username
            holds = game.condition_holds(controller, condition_text, spell)
            chosen = upgraded_template if holds else template
            _run_mass_pump(game, spell, controller, chosen, None)
            if holds is None:
                game.layer_remainder_notices.append(
                    LayerRemainderNotice(
                        source_id=spell.id, source_name=spell.card.name, text=remainder
                    )
                )

        from .. import conditions

        if conditions.claims(condition_text):
            return instead_effect
        return _with_unparsed_remainder(instead_effect, remainder)

    counter_on_each = _parse_mass_pump_counter_on_each(remainder) if remainder else None
    if counter_on_each is not None:
        counter_amount, counter_kind = counter_on_each

        def counter_effect(game: "Game", spell: CardState) -> None:
            targets = _run_mass_pump(
                game, spell, game.controller_of(spell).username, template, magnitude_expr
            )
            for target in targets:
                if target.zone is Zone.BATTLEFIELD:
                    game.add_counters(target, counter_kind, counter_amount)

        return counter_effect

    if followup := mass_pump_followups.spell_effect(remainder, template, magnitude_expr):
        return followup

    remainder_effect = (
        (turn_scoped_rider(remainder, for_spell=True) or parse_mixed_effect_for_spell(remainder))
        if remainder
        else None
    )

    def effect(game: "Game", spell: CardState) -> None:
        pumped = _run_mass_pump(
            game, spell, game.controller_of(spell).username, template, magnitude_expr
        )
        if not remainder:
            return
        if remainder_effect is not None:
            run_with_antecedent(game, spell, remainder_effect, pumped)
        else:
            game.layer_remainder_notices.append(
                LayerRemainderNotice(
                    source_id=spell.id, source_name=spell.card.name, text=remainder
                )
            )

    if remainder and remainder_effect is None:
        return _with_unparsed_remainder(effect, remainder)
    return effect


def _with_unparsed_remainder[F](effect: F, remainder: str) -> F:
    """`effect`, marked as a closure that only notices `remainder` at runtime
    (CR 608.2c: an instruction it skips leaves the clause half-played) - the
    `unparsed_remainder` attribute `support.unparsed_remainder` reads, so the
    support oracle never scores such a clause `handled`."""
    effect.unparsed_remainder = remainder  # type: ignore[attr-defined]
    return effect


#: "Each opponent skips their next untap step." - Brine Elemental's own
#: "turned face up" trigger (CR 702.37e, CR 614.10, CR 502.3).
_EACH_OPPONENT_SKIPS_NEXT_UNTAP_RE = re.compile(
    r"^each opponent skips their next untap step\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s35")
def _parse_each_opponent_skips_next_untap_clause(text: str) -> AbilityEffect | None:
    """`_EACH_OPPONENT_SKIPS_NEXT_UNTAP_RE`'s shape - Brine Elemental's whole
    trigger. `Game.untap_step` is what actually consumes
    `players_skipping_next_untap` (CR 614.10a: the skip waits for the first
    occurrence that isn't itself skipped)."""
    if _EACH_OPPONENT_SKIPS_NEXT_UNTAP_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for opponent in _opponents(game, ability.controller):
            game.players_skipping_next_untap[opponent.username] = (
                game.players_skipping_next_untap.get(opponent.username, 0) + 1
            )

    return effect


def become_prepared_ability_targets(game: "Game", ability: AbilityOnStack) -> None:
    """CR 722.3a: give the prepared designation to each permanent this
    ability still legally targets - Hexhaven Dueling Arena's own "Target
    creature becomes prepared" and "Target creature that attacked this turn
    becomes prepared." (the second half read entirely by `machines/
    targeting.py`'s `must_have_attacked_this_turn`, not here).

    `Game.become_prepared` is CR 722.3a's own two refusals already: a
    creature with no prepare spell, or one already prepared, is a silent
    no-op rather than an error - exactly right for a target restriction that
    names no such requirement at all.
    """
    for target in game.resolve_targets(ability):
        if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
            game.become_prepared(target)


#: When "at the beginning of `<timing>`" is, for a delayed "transform this
#: `<noun>` at ..." (CR 603.7): the step, and whether only its controller's own
#: turn counts ("your next upkeep").
_DELAYED_TRANSFORM_TIMINGS: dict[str, tuple[Step, bool]] = {
    "the beginning of the next upkeep": (Step.UPKEEP, False),
    "the beginning of the next turn's upkeep": (Step.UPKEEP, False),
    "the beginning of your next upkeep": (Step.UPKEEP, True),
    "the beginning of the next end step": (Step.END_STEP, False),
}

#: "Transform `<this>` at the beginning of the next upkeep." - Aang, at the
#: Crossroads' and Archangel Avacyn's own printed name normalized to CR
#: 700.7's "this permanent" by `_self_normalized_effect_text` before any
#: parser sees it.
_TRANSFORM_SELF_AT_NEXT_STEP_RE = re.compile(
    r"^transform this (?:creature|permanent|artifact|enchantment|land|planeswalker) at "
    r"(?P<timing>" + "|".join(re.escape(timing) for timing in _DELAYED_TRANSFORM_TIMINGS) + r")"
    r"\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_transform_self_at_next_step_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TRANSFORM_SELF_AT_NEXT_STEP_RE`'s shape: the ability creates a
    delayed triggered ability (CR 603.7a) that transforms its source at the
    named step (`machines/delayed.TransformSubject`).

    The source must still be the object the ability triggered from (CR
    400.7): if it left the battlefield - even to come straight back - before
    this resolves, "this creature" names an object that no longer exists and
    no delayed trigger is created. Once created, CR 603.7c keeps the delayed
    trigger off a permanent that leaves afterwards, and CR 701.27f off one
    that has transformed since - `TransformSubject` checks both."""
    if for_spell:
        return None
    match = _TRANSFORM_SELF_AT_NEXT_STEP_RE.fullmatch(clause.strip())
    if match is None:
        return None
    step, yours_only = _DELAYED_TRANSFORM_TIMINGS[match.group("timing").lower()]
    printed = clause.strip()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from ..delayed import TransformSubject

        assert isinstance(stack_object, AbilityOnStack)
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if (
            stack_object.source_stamp is not None
            and source.zone_change_stamp != stack_object.source_stamp
        ):
            return
        game.create_delayed_trigger(
            DelayedTrigger(
                text=printed,
                effect=TransformSubject(times_transformed=source.times_transformed),
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=step,
                controller=stack_object.controller,
                source_id=source.id,
                source_name=stack_object.source_name,
                subject_id=source.id,
                expected_zone=Zone.BATTLEFIELD,
                expected_stamp=source.zone_change_stamp,
                only_when_active=stack_object.controller if yours_only else None,
            )
        )

    return effect


#: Oketra's Last Mercy's own rider: "Lands you control don't untap during
#: your next untap step." - the group-of-permanents twin of `_THAT_
#: PERMANENT_NO_UNTAP_RE`'s single anaphoric one (Vorinclex, Voice of
#: Hunger's "that land"), both reusing `CardState.exerted` (CR 701.43a-b) as
#: the shared "does not untap next untap step" flag - it is not CR 701.43's
#: Exert keyword action either time, only the identical mechanical effect a
#: card can print without the word "exert" at all.
_LANDS_DONT_UNTAP_NEXT_STEP_RE = re.compile(
    r"^lands you control (?:don'?t|do not) untap during your next untap step\.?$",
    re.IGNORECASE,
)


def _parse_lands_dont_untap_next_step_clause(clause: str) -> ClauseEffect | None:
    """`_LANDS_DONT_UNTAP_NEXT_STEP_RE`'s shape, or `None`."""
    if _LANDS_DONT_UNTAP_NEXT_STEP_RE.fullmatch(clause.strip()) is None:
        return None

    def lands_dont_untap(game: "Game", player: Player, source: str, source_id: str | None) -> None:
        for permanent in game.battlefield:
            if (
                permanent.controller == player.username
                and Type.LAND in game.characteristics_of(permanent).types
            ):
                permanent.exerted = True

    return lands_dont_untap


def _untap_all_qualifier_matches(game: "Game", state: CardState, noun: str, nonland: bool) -> bool:
    chars = game.characteristics_of(state)
    if nonland and Type.LAND in chars.types:
        return False
    if noun == "permanents":
        return True
    if noun == "lands":
        return Type.LAND in chars.types
    if noun == "artifacts":
        return Type.ARTIFACT in chars.types
    if noun == "creatures":
        return Type.CREATURE in chars.types
    if noun == "tokens":
        return chars.is_token
    return False


def _player_gains_hexproof_clause(match: re.Match[str]) -> ClauseEffect | None:
    """`_PLAYER_GAINS_HEXPROOF_RE`'s clause: record the grant on the player
    through `Game.grant_player_hexproof`/`grant_player_shroud`, which keep it
    on `Player.targeting_grants` and end it at CR 611.2a's stated boundary."""
    keyword = match.group("keyword").lower()
    raw = match.group("qualities")
    qualities = tuple(hexproof_qualities_in(raw)) if raw is not None else ()
    if raw is not None and (keyword == "shroud" or not qualities):
        return None
    duration = (
        Duration.UNTIL_END_OF_TURN
        if match.group("duration").lower() == "end of turn"
        else Duration.UNTIL_YOUR_NEXT_TURN
    )

    def gain(game: "Game", player: Player, source: str, source_id: str | None) -> None:
        if keyword == "shroud":
            game.grant_player_shroud(player.username, duration=duration, source_name=source)
        else:
            game.grant_player_hexproof(
                player.username, qualities, duration=duration, source_name=source
            )

    return gain


#: A keyword-ability line, recognised by its *shape* rather than by its
#: keyword. CR 702.1: "Most abilities describe exactly what they do in the
#: card's rules text. Some, though, are very common or would require too much
#: space to define on the card. In these cases, the object lists only the name
#: of the ability as a 'keyword'" - so a keyword line is the ability's *name*
#: (plus its cost or parameter, if it has one) and nothing else. It is one of
#: CR 113.3's ability categories in its own right, never one of the resolving
#: spell's CR 608.2c instructions, which is why it has to come off before the
#: text is split into clauses: left in, `split_effect_clauses` reads it as an
#: unparseable clause and `_parse_mixed_clauses`'s fail-closed-per-clause rule
#: takes the spell's real sentence down with it.
#:
#: This replaces what was a **whitelist** - one hand-written regex per keyword
#: (`_REPLICATE_LINE_RE`, `_CYCLING_LINE_RE`, ...). The whitelist worked only
#: for keywords somebody had already met: Consign to Memory read correctly
#: because replicate had a row, while **Metallic Rebuke** ("Improvise\nCounter
#: target spell unless its controller pays {3}.", CR 702.126a) and **Lórien
#: Revealed** ("Draw three cards.\nIslandcycling {1}", CR 702.29e) returned
#: `None` for the whole card, because improvise and typecycling did not. A
#: shape rule has no such per-keyword hole.
#:
#: The shape, measured against every printing in `tests/fixtures/cards/`:
#:
#: - **bare form** - a line with no sentence-ending full stop and no colon:
#:   `Flying`, `Flying, ward {2}`, `Improvise`, `Islandcycling {1}`,
#:   `Suspend 3—{2}{B}{B}`, `Enchant creature`, `Hexproof from artifacts,
#:   creatures, and enchantments`. Rules text is written in sentences, so a
#:   line carrying neither is not an instruction; the same "no full stop, no
#:   colon" test is what `machines/abilities._parse_keywords` already uses to
#:   tell a keyword line from `Flying creatures you control get +1/+1.`
#: - **em-dash cost form** - `Evoke—Exile a black card from your hand.`,
#:   `Ward—Pay 3 life.` - which does end in a full stop, and is told apart by
#:   the em dash carrying no space in front of it. That spacing is exactly the
#:   distinction `machines/abilities._KEYWORD_COST` already draws between a
#:   keyword cost and a CR 207.2c ability word (`Landfall — Whenever ...`).
#:
#: A line containing " —" is therefore never stripped: that covers CR 700.2's
#: modal header (`Choose one —`) and every ability word, both of which do
#: introduce real instructions.
#:
#: Nor is a line carrying a double quote: a keyword line never quotes
#: anything, while a CR 113.10 grant sentence whose quoted ability holds its
#: own full stop ("... gain menace and "Whenever ... discards a card."")
#: carries no full stop *outside* the quote, and would otherwise pass for a
#: bare keyword line once that quote is blanked (Driven // Despair's
#: aftermath half, after its "Aftermath" line).
_KEYWORD_ABILITY_BARE_LINE_RE = re.compile(r'^[A-Za-z][^.:"]*$')
_KEYWORD_ABILITY_COST_LINE_RE = re.compile(r"^[A-Z][A-Za-z'’]*(?: [A-Za-z'’]+)*(?: \d+)?—\S[^:]*$")


def _is_keyword_ability_line(line: str) -> bool:
    """Whether `line` is a keyword-ability line - see the two regexes above."""
    line = line.strip()
    if not line or " —" in line:
        return False
    return bool(
        _KEYWORD_ABILITY_BARE_LINE_RE.fullmatch(line)
        or _KEYWORD_ABILITY_COST_LINE_RE.fullmatch(line)
    )


def tap_ability_targets(game: "Game", stack_object: "StackObject") -> None:
    """Tap each permanent this still legally targets (CR 701.26a)."""
    for target in game.resolve_targets(stack_object):
        if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
            game.tap_permanent(target)


def untap_ability_targets(game: "Game", stack_object: "StackObject") -> None:
    """Untap each permanent this still legally targets (CR 701.26b)."""
    for target in game.resolve_targets(stack_object):
        if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
            target.untap()


#: Tamiyo, Compleated Sage's `+1`: "Tap up to one target artifact or
#: creature. It doesn't untap during its controller's next untap step." Two
#: sentences, not one clause: the second's "it" is anaphoric (CR 400.7) for
#: whatever the first named, so this is read whole rather than through
#: `_parse_targeted_clauses`'s independent per-clause dispatch, the same
#: reason `_X_DAMAGE_DIVIDED_DOUBLED_RE` reads Shatterskull Smashing's own
#: two sentences together.
#:
#: The old shape hardcoded "up to \S+" ahead of "target" and a singular "it"
#: pronoun, so it read only Tamiyo's own exact wording. Frost Breath's real
#: printing - "Tap up to two target creatures. Those creatures don't untap
#: during their controller's next untap step." - has neither: a plural count
#: with no "it" at all. Chill of the Grave's real printing has the opposite
#: gap - no "up to" prefix, a single mandatory target ("Tap target creature.
#: It doesn't untap ..."). The count word itself is read entirely by
#: `_targets_understood(count_agnostic=True)` below, same as before; the
#: phrase only has to admit an optional leading count and the plural pronoun
#: pair `_targets_understood` already knows how to size (one target, several,
#: or "up to" any of them). "That `<noun>` doesn't untap ..." (Chandra's
#: Revolution's "Tap target land. That land doesn't untap during its
#: controller's next untap step.", Stensia Innkeeper's trigger) is the same
#: anaphora with a noun in place of the pronoun (CR 502.3).
_TAP_TARGET_THEN_NO_UNTAP_RE = re.compile(
    rf"^tap (?P<phrase>(?:up to )?(?:{COUNT} )?target .+?)\.\s*"
    r"(?:(?:it|that [a-z]+) doesn'?t|(?:those \w+|they) don'?t) untap during "
    r"(?:its|their) controller'?s next untap step\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s36")
def _parse_tap_target_then_no_untap_clause(text: str) -> AbilityEffect | None:
    """`_TAP_TARGET_THEN_NO_UNTAP_RE`'s shape.

    CR 701.43a's exert wording - "you choose to have it not untap during your
    controller's next untap step" - is exactly what this sentence asks for,
    just imposed on a target by another permanent's ability rather than paid
    as the target's own activation cost, so `CardState.exerted`/`.untap`'s
    existing CR 701.43a-b machinery is reused rather than duplicated: setting
    the flag directly skips only the *target's* controller's next untap step,
    whoever that is, exactly as the printed "its controller's" reads.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _TAP_TARGET_THEN_NO_UNTAP_RE.fullmatch(whole)
    if match is None:
        return None
    phrase = match.group("phrase")
    if not _targets_understood(phrase, count_agnostic=True):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for target in _own_phrase_targets(game, ability, phrase):
            game.tap_permanent(target)
            target.exerted = True

    return effect


#: "Tap that creature and it doesn't untap during its controller's next untap
#: step." (Kashi-Tribe Warriors, Matsu-Tribe Sniper, Frostwalk Bastion, ...) -
#: `_TAP_TARGET_THEN_NO_UNTAP_RE`'s anaphoric twin for a *trigger*: nothing is
#: targeted, "that creature" is the one the trigger's own event names (CR 603.2,
#: CR 607.1) - the creature that was dealt the damage for a "deals damage to a
#: creature" event (`GameEvent.target_id`), else the event's subject. Read
#: whole because the bare "and" would otherwise cut "it doesn't untap ..." away
#: from the tap it refers back to.
_TAP_THAT_THEN_NO_UNTAP_RE = re.compile(
    r"^tap that (?P<noun>[a-z]+)(?:,? and |\.\s*)(?:it|that (?P=noun)) doesn'?t untap "
    r"during its controller'?s next untap step\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_tap_that_then_no_untap_clause(text: str) -> AbilityEffect | None:
    """`_TAP_THAT_THEN_NO_UNTAP_RE`'s shape.

    Reuses the CR 701.43a-b `CardState.exerted` flag exactly as
    `_parse_tap_target_then_no_untap_clause` does: the creature skips only its
    controller's next untap step (CR 502.3). Ability-only by construction - a
    spell has no `ability.event` to read "that creature" from - and a
    referent that has since left the battlefield is simply not tapped
    (CR 608.2b - nothing to act on).
    """
    whole = _strip_non_effect_preamble(text).strip()
    if _TAP_THAT_THEN_NO_UNTAP_RE.fullmatch(whole) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None:
            return
        referent_id = event.target_id or event.subject_id
        if referent_id is None:
            return
        permanent = game.find_by_id(referent_id)
        if isinstance(permanent, CardState) and permanent.zone is Zone.BATTLEFIELD:
            game.tap_permanent(permanent)
            permanent.exerted = True

    return effect


def _own_phrase_targets(game: "Game", stack_object: "StackObject", phrase: str) -> list[CardState]:
    """The targets still legal on the battlefield (CR 608.2b) that `phrase` -
    this one clause's own "target ..." words - was announced for, when the
    resolving object targets for other clauses too (Chandra's Revolution:
    "deals 4 damage to target creature. Tap target land. ...", CR 601.2c).

    A spell's targets carry the requirement each filled at announcement
    (`TargetRef.slot`); the requirement whose phrase is this clause's own is
    this clause's slot. Without a slot to read (an ability, or one phrase
    printed twice), every legal target the phrase itself accepts is this
    clause's - which is every target when the clause is the only one.
    """
    own = profile_for_text(phrase)
    controller = game.controller_of(stack_object).username
    wanted = own.requirements[0] if own.understood and own.requirements else None
    slot: int | None = None
    if isinstance(stack_object, CardState) and wanted is not None:
        full = game._resolution_profile(stack_object)
        hits = [
            index
            for index, requirement in enumerate(full.requirements)
            if requirement.phrase.lower() == wanted.phrase.lower()
        ]
        if len(full.requirements) > 1 and len(hits) == 1:
            slot = hits[0]
    found: list[CardState] = []
    for ref in stack_object.targets:
        if slot is not None and ref.slot is not None and ref.slot != slot:
            continue
        thing = game.legal_target(stack_object, ref)
        if not isinstance(thing, CardState) or thing.zone is not Zone.BATTLEFIELD:
            continue
        if wanted is not None and wanted.rejects(thing, controller, game) is not None:
            continue
        found.append(thing)
    return found


#: CR 722.3b, Infinite Coursework's own Aura shape: "When this Aura enters,
#: tap enchanted creature. It becomes unprepared." CR 400.7/603.10's
#: anaphoric "it" points back at "enchanted creature" - the object this Aura
#: is attached to (`CardState.attached_to`), not a second target of its
#: own: CR 303.4b's whole reason an Aura's continuous "enchant" ability
#: names an object at all is so its other abilities can refer back to it
#: without targeting it a second time.
_TAP_ENCHANTED_THEN_UNPREPARED_RE = re.compile(
    r"^tap enchanted (?:creature|permanent)\.\s*it becomes unprepared\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_tap_enchanted_then_unprepared_clause(text: str) -> AbilityEffect | None:
    """`_TAP_ENCHANTED_THEN_UNPREPARED_RE`'s shape - see its own docstring."""
    whole = _strip_non_effect_preamble(text).strip()
    if _TAP_ENCHANTED_THEN_UNPREPARED_RE.fullmatch(whole) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        aura = ability.source(game)
        if aura is None:
            return
        enchanted_id = aura.attached_to
        if enchanted_id is None:
            return
        enchanted = game.find_by_id(enchanted_id)
        if enchanted is None or enchanted.zone is not Zone.BATTLEFIELD:
            return
        game.tap_permanent(enchanted)
        game.become_unprepared(enchanted)

    return effect


#: "they get that many poison counters" - Etali, Primal Sickness's "Whenever
#: Etali deals combat damage to a player, they get that many poison
#: counters." CR 122.1f's poison counters, given to the player the event
#: names ("they", CR 120.2a's damaged player) in the amount the event carried
#: ("that many", `that_many`).
_EVENT_PLAYER_GETS_THAT_MANY_POISON_RE = re.compile(
    r"^(?:they|that player) gets? that many poison counters\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s3", for_spell=FORWARD)
def _parse_event_player_gets_that_many_poison_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EVENT_PLAYER_GETS_THAT_MANY_POISON_RE`. Ability-only: "they" and
    "that many" both point at a triggering event. No count to read gives a
    notice and no counters (`_that_many_or_notice`)."""
    if for_spell or _EVENT_PLAYER_GETS_THAT_MANY_POISON_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not isinstance(stack_object, AbilityOnStack) or stack_object.event is None:
            return
        username = stack_object.event.player
        if username is None:
            return
        amount = _that_many_or_notice(
            game,
            clause,
            source_id=stack_object.source_id,
            source_name=stack_object.source_name,
            stack_object=stack_object,
        )
        if amount is None or amount <= 0:
            return
        game.add_player_counters(game.player(username), Counter.POISON, amount)

    return effect


#: "each player this creature attacked this turn loses the game" - Angel of
#: Destiny's own end-step trigger, its leading "if you have at least 15 life
#: more than your starting life total" already split off and checked by
#: `machines.triggers.intervening_if_holds` before this clause is ever read
#: (the same order `_YOU_WIN_THE_GAME_RE`'s own docstring describes).
#: CR 104.3e's "an effect may state that a player loses the game"
#: (`Game.player_loses_the_game`, `_parse_if_condition_you_win_the_game_
#: clause`'s winning twin) applied to every player `Game.
#: attacked_players_this_turn` recorded for this permanent's own id - CR
#: 508.1a's historical fact, not this combat's live attacking status, since
#: an end-step trigger reads it well after combat has ended.
_EACH_PLAYER_THIS_CREATURE_ATTACKED_LOSES_RE = re.compile(
    r"^each player this (?:creature|permanent) attacked this turn loses the game\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s4", for_spell=FORWARD)
def _parse_each_player_this_creature_attacked_loses_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EACH_PLAYER_THIS_CREATURE_ATTACKED_LOSES_RE`'s shape. Ability-only:
    "this creature" and the per-turn attack record it reads have no spell
    equivalent."""
    if for_spell or _EACH_PLAYER_THIS_CREATURE_ATTACKED_LOSES_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not isinstance(stack_object, AbilityOnStack) or stack_object.source_id is None:
            return
        attacked = game.attacked_players_this_turn.get(stack_object.source_id, ())
        for username in list(attacked):
            game.player_loses_the_game(username)

    return effect


#: "You may have creatures you control assign their combat damage this turn as
#: though they weren't blocked." (Predatory Focus) - the permission Rhox's own
#: line states (`machines/combat.ASSIGN_AS_THOUGH_UNBLOCKED_TEXT`), granted
#: until end of turn to the creatures its controller has as this resolves (CR
#: 611.2c) and still asked of that controller creature by creature when each
#: blocked attacker assigns (CR 608.2d).
_CREATURES_YOU_CONTROL_ASSIGN_AS_THOUGH_UNBLOCKED_RE = re.compile(
    r"^you may have creatures you control assign their combat damage this turn "
    r"as though they weren'?t blocked\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s4", for_spell=FORWARD)
def _parse_creatures_you_control_assign_as_though_unblocked_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_CREATURES_YOU_CONTROL_ASSIGN_AS_THOUGH_UNBLOCKED_RE`'s shape: one
    layer-6 grant (CR 613.1f) per creature, scoped to that very object (CR
    400.7), expiring in the cleanup step (CR 514.2)."""
    if "as though they weren" not in clause.lower():
        return None
    if _CREATURES_YOU_CONTROL_ASSIGN_AS_THOUGH_UNBLOCKED_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        store = continuous_effects(game)
        for permanent in list(game.permanents_controlled_by(controller)):
            if not game.characteristics_of(permanent).is_creature:
                continue
            store.add(
                ContinuousEffect(
                    description=(
                        f"{permanent.name}: may assign its combat damage as though it "
                        "weren't blocked this turn"
                    ),
                    layer=Layer.ABILITY,
                    timestamp=store.tick(),
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                    modification=grant_ability(ASSIGN_AS_THOUGH_UNBLOCKED_TEXT),
                ),
                game,
            )

    return effect


#: "that player loses the game" - Vraska, Scheming Gorgon's -10 grants
#: "Whenever this creature deals damage to an opponent, that player loses the
#: game." CR 104.3e's effect-stated loss, applied to the player the
#: triggering event names (the damaged opponent), the same `event.player`
#: referent every other triggered "that player ..." clause reads.
_THAT_PLAYER_LOSES_THE_GAME_RE = re.compile(
    r"^(?:that player loses|they lose) the game\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s4", for_spell=FORWARD)
def _parse_that_player_loses_the_game_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_THAT_PLAYER_LOSES_THE_GAME_RE`'s shape. Ability-only: a spell has no
    triggering event to name "that player"."""
    if for_spell or _THAT_PLAYER_LOSES_THE_GAME_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not isinstance(stack_object, AbilityOnStack):
            return
        event = stack_object.event
        if event is None or event.player is None:
            return
        game.player_loses_the_game(event.player)

    return effect


#: "Untap this creature." (Devoted Druid) - CR 701.26b's untap with no target
#: at all, the source's own cost-side counter placement having already been
#: paid by `cost.py`'s `PLACE_COUNTERS` component by the time this runs.
_UNTAP_SELF_RE = re.compile(r"^untap this \w+\.?$", re.IGNORECASE)


@ABILITY_TEXT.rung("s28")
def _parse_untap_self_clause(text: str) -> AbilityEffect | None:
    """`_UNTAP_SELF_RE`'s shape - Devoted Druid's "Put a -1/-1 counter on this
    creature: Untap this creature." (CR 701.26b).

    The Devoted Druid + Vizier of Remedies loop this enables terminates on its
    own: nothing here prevents the state-based action CR 704.5f already
    performs once enough -1/-1 counters bring toughness to 0 - this function
    only ever reads whether the source is *still* on the battlefield before
    untapping it, the same check `_parse_put_counters_on_self_clause` makes.
    """
    if _UNTAP_SELF_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            source.untap()

    return effect


#: CR 722.3a/722.3b, the self-referential shape most prepare creatures print:
#: "At the beginning of your upkeep, if this creature isn't prepared, **it
#: becomes prepared**." (Woodwork Prodigy, Stingerquill Voxmancer, Paradox
#: Shaper) and "... this creature becomes prepared." (Bloodline Recollector,
#: no anaphora at all). "It" here is CR 603.10's ordinary read-back to the
#: ability's own subject - the ability's source, since every printing in the
#: pool triggers off its own creature - not a second target to announce.
_BECOMES_PREPARED_SELF_RE = re.compile(r"^(?:it|this \w+) becomes prepared\.?$", re.IGNORECASE)
_BECOMES_UNPREPARED_SELF_RE = re.compile(r"^(?:it|this \w+) becomes unprepared\.?$", re.IGNORECASE)


def _parse_becomes_prepared_self_clause(text: str) -> AbilityEffect | None:
    """`_BECOMES_PREPARED_SELF_RE`'s shape - see its own docstring."""
    if _BECOMES_PREPARED_SELF_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            game.become_prepared(source)

    return effect


def _parse_becomes_unprepared_self_clause(text: str) -> AbilityEffect | None:
    """`_BECOMES_UNPREPARED_SELF_RE`'s shape (CR 722.3b)."""
    if _BECOMES_UNPREPARED_SELF_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            game.become_unprepared(source)

    return effect


#: "Each creature you control becomes prepared" (Codie, Ravenous Codex).
#: CR 722.3a's own "can't gain this designation unless it has a prepare
#: spell" is why this needs no filter of its own: most creatures swept up by
#: "each creature you control" have no prepare spell at all, and `Game.
#: become_prepared` already refuses them silently, one at a time.
_BECOMES_PREPARED_GROUP_RE = re.compile(
    r"^each creature you control becomes prepared\.?$", re.IGNORECASE
)


def _parse_becomes_prepared_group_clause(text: str) -> AbilityEffect | None:
    """`_BECOMES_PREPARED_GROUP_RE`'s shape, read off the *computed* board
    (CR 613.5) the same way `_parse_double_counters_on_group_clause` already
    reads "each creature you control" - a permanent turned into a creature
    this turn is swept up, one that stopped being one is not."""
    if _BECOMES_PREPARED_GROUP_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        board = game.computed_board()
        for permanent in game.permanents_controlled_by(ability.controller):
            if Type.CREATURE in board.of(permanent).types:
                game.become_prepared(permanent)

    return effect


#: "Untap `<Name>`." - CR 109.2's plain self-reference, spelled out with the
#: permanent's own printed name instead of "this creature": Hydro-Man, Fluid
#: Felon's "At the beginning of your end step, untap Hydro-Man." (the "he/
#: she" pronoun family prints this way rather than "this creature" once it
#: has already used a pronoun for itself elsewhere in the same ability).
#: `name` is read generically and checked against the resolving ability's
#: own source at runtime, never pinned to one card's literal name.
_UNTAP_NAMED_SELF_RE = re.compile(r"^untap (?P<name>[A-Z][A-Za-z',.\- ]*?)\.?$")


def _parse_untap_named_self_clause(text: str) -> AbilityEffect | None:
    """`_UNTAP_NAMED_SELF_RE`'s shape - the named-self twin of
    `_parse_untap_self_clause`."""
    match = _UNTAP_NAMED_SELF_RE.fullmatch(text.strip())
    if match is None:
        return None
    name = match.group("name").strip()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD and source.name == name:
            source.untap()

    return effect


#: "Untap all `<group>` you control." (Jiang Yanggu, Never Alone's own end
#: step: "untap all tokens you control") - CR 111.1's token-ness for "tokens",
#: or CR 205.2a's card type for "creatures"/"artifacts"/"lands", read off the
#: *computed* board (CR 613.5) the same way `_parse_put_counters_on_group_
#: clause`'s own "each `<group>` you control" already is. `_UNTAP_GROUP_WORDS`
#: is deliberately narrow (only the shapes this wave's own cards print) -
#: never a fallback that guesses at an unlisted word.
_UNTAP_ALL_GROUP_RE = re.compile(
    r"^untap all (?P<group>tokens|permanents|creatures|artifacts|lands) "
    r"you control\.?$",
    re.IGNORECASE,
)

#: "When this creature enters, untap each other Merfolk you control." (Deepway
#: Navigator) - the subtype-filtered twin of `_UNTAP_ALL_GROUP_RE`'s own
#: closed card-type list, generalised over any CR 205.3 creature type
#: `canonical_subtype` recognises rather than a hand-picked word. "Each" and
#: "other" are printed together on every proof this wave found - the source
#: is the entering Merfolk itself, so "other" is what keeps it from untapping
#: its own tapped-on-entry self.
_UNTAP_EACH_OTHER_SUBTYPE_RE = re.compile(
    r"^untap each (?P<other>other )?(?P<subtype>[A-Z][a-zA-Z-]*) you control\.?$"
)


@MIXED_CLAUSE.rung("s17", for_spell=FORWARD)
def _parse_untap_each_subtype_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_UNTAP_EACH_OTHER_SUBTYPE_RE`'s shape - see the banner above."""
    match = _UNTAP_EACH_OTHER_SUBTYPE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    subtype = canonical_subtype(match.group("subtype"))
    if subtype is None:
        return None
    excludes_source = match.group("other") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        board = game.computed_board()
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        source_id = source.id if source is not None else None
        for permanent in list(game.battlefield):
            if excludes_source and permanent.id == source_id:
                continue
            if board.of(permanent).controller != controller:
                continue
            if not any(word.lower() == subtype for word in board.of(permanent).subtypes):
                continue
            permanent.untap()

    return effect


@MIXED_CLAUSE.rung("s17", for_spell=FORWARD)
def _parse_untap_all_group_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_UNTAP_ALL_GROUP_RE`'s shape; see the banner above."""
    match = _UNTAP_ALL_GROUP_RE.fullmatch(clause.strip())
    if match is None:
        return None
    group = match.group("group").lower()
    group_type = {
        "creatures": Type.CREATURE,
        "artifacts": Type.ARTIFACT,
        "lands": Type.LAND,
    }.get(group)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        board = game.computed_board()
        for permanent in list(game.battlefield):
            if game.controller_of(permanent).username != controller:
                continue
            if group == "tokens" and not permanent.token:
                continue
            if group_type is not None and group_type not in board.of(permanent).types:
                continue
            permanent.untap()

    return effect


#: "After this main phase, there is an additional combat phase followed by
#: an additional main phase." - Aggravated Assault's own second instruction,
#: and every other printing of the same reminder-free "extra combat" shape
#: (World at War, Savage Beating's own mode, Seize the Day's descendants).
#: CR 500.8: "Some effects can add phases to a turn. They do this by adding
#: the phases directly after the specified phase." - "this main phase" is
#: always the one the ability/spell resolves during, so nothing here has to
#: read which main phase that was; `TurnMachine.insert_extra_phase` (CR
#: 505.1a: an additional main phase is a postcombat one regardless) is where
#: the actual insertion happens. Read generically by shape, not by card
#: name - any future card printing this identical sentence is read the same
#: way with no new row.
_ADDITIONAL_COMBAT_AND_MAIN_PHASE_RE = re.compile(
    r"^after this main phase,\s*there is an additional combat phase "
    r"followed by an additional main phase\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s18")
def _parse_additional_combat_and_main_phase_clause(clause: str) -> AbilityEffect | None:
    """`_ADDITIONAL_COMBAT_AND_MAIN_PHASE_RE`'s shape; see the banner above."""
    if _ADDITIONAL_COMBAT_AND_MAIN_PHASE_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert game.turn is not None
        # One call, the whole combat-then-main run: `insert_extra_phase`
        # prepends each call's own steps ahead of whatever is already
        # queued (CR 500.8's "most recently created phase ... first"), so
        # two separate calls here would need to run in the *reverse* of
        # their printed order to land correctly - a single call with both
        # phases' steps already concatenated is the plain, unambiguous way
        # to queue "combat, then main".
        game.turn.insert_extra_phase(COMBAT_PHASE_STEPS + (Step.POSTCOMBAT_MAIN,))

    return effect


#: "Untap all attacking creatures." (Desert Were-Worm's own attack trigger,
#: Hellkite Charger's identical real-world shape) - CR 508.1f's tap undone in
#: bulk, off `Game.attacking_creatures` at resolution (a creature removed
#: from combat between the trigger and its resolution is no longer among
#: them, and stays as it is). No "you control" qualifier is printed because
#: CR 508.1 already lets only the active player declare attackers, so every
#: currently-attacking creature is this ability's own controller's.
_UNTAP_ALL_ATTACKING_RE = re.compile(r"^untap all attacking creatures\.?$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s18")
def _parse_untap_all_attacking_clause(clause: str) -> AbilityEffect | None:
    """`_UNTAP_ALL_ATTACKING_RE`'s shape; see the banner above."""
    if _UNTAP_ALL_ATTACKING_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for creature in list(game.attacking_creatures()):
            creature.untap()

    return effect


#: "After this phase, there is an additional combat phase." - Desert
#: Were-Worm's and Hellkite Charger's own second sentence: CR 500.8's phase
#: insertion again, but with no additional main phase riding along the way
#: `_ADDITIONAL_COMBAT_AND_MAIN_PHASE_RE`'s "after this **main** phase ...
#: followed by an additional main phase" always does. "This phase" is
#: whichever phase (an ordinary combat phase, or an earlier extra one) the
#: resolving ability's own trigger fired during - always the phase this
#: effect resolves in, the same "no need to track which one" reading
#: `_parse_additional_combat_and_main_phase_clause` already gives "this main
#: phase".
_ADDITIONAL_COMBAT_PHASE_ONLY_RE = re.compile(
    r"^after this phase,\s*there is an additional combat phase\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s20")
def _parse_additional_combat_phase_only_clause(clause: str) -> AbilityEffect | None:
    """`_ADDITIONAL_COMBAT_PHASE_ONLY_RE`'s shape; see the banner above."""
    if _ADDITIONAL_COMBAT_PHASE_ONLY_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert game.turn is not None
        game.turn.insert_extra_phase(COMBAT_PHASE_STEPS)

    return effect


#: "Whenever a permanent you control enters tapped, untap it." (Amulet of
#: Vigor). CR 603.10's "it" points back at whatever the trigger's own
#: condition named - the permanent `TriggerEvent.ENTERS_THE_BATTLEFIELD`
#: recorded as `GameEvent.subject_id` - not a "target permanent" (CR 115.1):
#: the ability's own printed text never says "target", so there is nothing
#: for `machines/targeting.py` to check and nothing on `AbilityOnStack.
#: targets` to read. This is the *general* shape ("it" naming the trigger's
#: own subject with no target and no source-only "this"), not an Amulet of
#: Vigor-only row, so any future "Whenever ..., untap it." prints on this
#: same shape without a new entry.
_UNTAP_TRIGGER_SUBJECT_RE = re.compile(r"^untap it\.?$", re.IGNORECASE)


@ABILITY_TEXT.rung("s28")
def _parse_untap_trigger_subject_clause(text: str) -> AbilityEffect | None:
    """`_UNTAP_TRIGGER_SUBJECT_RE`'s shape - Amulet of Vigor's "Whenever a
    permanent you control enters tapped, untap it."

    Untapping here is CR 701.26b, unconditional: CR 701.43a's exert only
    withholds *the untap step's own* untap (CR 701.43b), never one an effect
    performs, so `exert_applies=False` is used - the same choice
    `machines/effects.py` already makes for its other non-untap-step untaps.
    Two copies of Amulet of Vigor each carry their own `TriggeredAbility` and
    each independently matches the same entering-tapped event
    (`machines/triggers.condition_matches`'s ordinary CR 603.3b handling), so
    two Amulets untapping the same permanent twice falls out of the existing
    multi-trigger machinery with no special case needed here.
    """
    if _UNTAP_TRIGGER_SUBJECT_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.subject_id is None:
            return
        subject = game.find_by_id(event.subject_id)
        if subject is not None and subject.zone is Zone.BATTLEFIELD:
            subject.untap(exert_applies=False)

    return effect


#: "untap it and scry `<n>`." - S.H.I.E.L.D. Spy Kit's own "Whenever
#: equipped creature attacks alone, untap it and scry 1." The identical
#: "it" anaphor `_UNTAP_TRIGGER_SUBJECT_RE` reads alone above, joined to
#: CR 701.22a's scry by the printed "and" - read as its own combined clause
#: rather than through the general clause splitter, because the untap half
#: needs the trigger's own event subject (`AbilityOnStack`), not a spell,
#: which is not a shape `parse_mixed_effect`'s ordinary "X and Y" pairing
#: reaches for.
_UNTAP_TRIGGER_SUBJECT_AND_SCRY_RE = re.compile(
    rf"^untap it and scry (?P<n>{COUNT})\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s28")
def _parse_untap_trigger_subject_and_scry_clause(text: str) -> AbilityEffect | None:
    """`_UNTAP_TRIGGER_SUBJECT_AND_SCRY_RE`'s shape - see the banner above."""
    match = _UNTAP_TRIGGER_SUBJECT_AND_SCRY_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is not None and event.subject_id is not None:
            subject = game.find_by_id(event.subject_id)
            if subject is not None and subject.zone is Zone.BATTLEFIELD:
                subject.untap(exert_applies=False)
        game.scry(
            game.controller_of(ability),
            count,
            source=ability.source_name,
            source_id=source_id_of(ability),
        )

    return effect


#: "This Saga gains "{T}: Add {C}."" (Urza's Saga, chapter I) and "This Saga
#: gains "{2}, {T}: Create a 0/0 colorless Construct artifact creature token
#: with 'This token gets +1/+1 for each artifact you control.'"" (chapter
#: II) - CR 113.10's own "gains" wording for an added ability, self-
#: referential ("this Saga") rather than Urza's Saga-only, so any future
#: "This <noun> gains "<ability>"." grant reads through this same parser.
#: The `[a-z]+` subject is deliberately unconstrained to a whitelist: CR
#: 113.10 does not care what kind of object gains the ability, only that the
#: quoted text is the whole of it.
_GAINS_ABILITY_RE = re.compile(
    r'^this [a-z]+ gains "(?P<ability>.+)"\.?$', re.IGNORECASE | re.DOTALL
)


@ABILITY_TEXT.rung("s28")
def _parse_gains_ability_clause(text: str) -> AbilityEffect | None:
    """`_GAINS_ABILITY_RE`'s shape.

    CR 113.10a: "An effect that adds an activated ability may include
    activation instructions for that ability. These instructions become part
    of the ability that's added to the object" - the quoted text is stored
    verbatim on `CardState.granted_ability_texts` and read back by
    `machines/abilities.parse_granted_ability_lines` exactly as
    `machines/abilities.parse_abilities` reads a card's own printed line, so
    whatever shape that line is (a mana ability, an ordinary activated
    ability) comes out the other side the same way a printed one would.

    Idempotent - a repeat grant of text already present is not appended
    twice - though nothing in the pool actually re-triggers this (a Saga's
    own chapter abilities each fire once, CR 714.4/704.5s).
    """
    match = _GAINS_ABILITY_RE.fullmatch(text.strip())
    if match is None:
        return None
    granted_text = match.group("ability").strip()
    if not granted_text:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if granted_text not in source.granted_ability_texts:
            source.granted_ability_texts = (*source.granted_ability_texts, granted_text)

    return effect


#: "Target land gains "{T}: Add {C}{C}" until this card is cast from
#: exile." - Emrakul, the Exigent Doom's own exile-activated ability. CR
#: 113.10's grant is the same one `_GAINS_ABILITY_RE` already reads for a
#: self-referential "This <noun> gains", widened here to a *targeted*
#: permanent, with an expiry tied to a game event ("this card is cast from
#: exile") instead of the ordinary "until end of turn". The `[a-z]+` type
#: word after "target" is unconstrained the same way `_GAINS_ABILITY_RE`'s
#: own subject is, so any future "Target <type> gains "<ability>" until this
#: card is cast from exile." printing reads through this same parser.
_TARGET_GAINS_ABILITY_UNTIL_CAST_FROM_EXILE_RE = re.compile(
    r'^(?P<phrase>target [a-z]+) gains "(?P<ability>.+)" until this '
    r"(?:card|permanent) is cast from exile\.?$",
    re.IGNORECASE | re.DOTALL,
)


@MIXED_CLAUSE.rung("s35")
def _parse_target_gains_ability_until_cast_from_exile_clause(text: str) -> AbilityEffect | None:
    """`_TARGET_GAINS_ABILITY_UNTIL_CAST_FROM_EXILE_RE`'s shape.

    The grant itself (CR 113.10a) happens immediately, exactly as
    `_parse_gains_ability_clause` does it. The expiry is a `DelayedTrigger`
    watching `TriggerEvent.CAST_SPELL` with its own `subject_id` set to the
    *exiled card* (`ability.source_id` - CR 113.7a's source is still findable
    by id across its own hand-to-exile move, confirmed the same way
    `_grant_cast_exiled_card_permission_from_sibling_static` already relies
    on it), not the land: the event this waits for and the permanent this
    changes are two different objects, the same split `StaticPrisonReturn`'s
    own docstring explains for its own delayed trigger.
    """
    match = _TARGET_GAINS_ABILITY_UNTIL_CAST_FROM_EXILE_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), battlefield_only=True):
        return None
    granted_text = match.group("ability").strip()
    if not granted_text:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            if granted_text not in target.granted_ability_texts:
                target.granted_ability_texts = (*target.granted_ability_texts, granted_text)
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=(
                        f'{target.name} gains "{granted_text}" until '
                        f"{source.name} is cast from exile."
                    ),
                    event=TriggerEvent.CAST_SPELL,
                    controller=ability.controller,
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    subject_id=source.id,
                    remaining=1,
                    expires_end_of_turn=False,
                    effect=RevokeGrantedAbility(
                        land_id=target.id,
                        land_stamp=target.zone_change_stamp,
                        granted_text=granted_text,
                    ),
                )
            )

    return effect


#: Suncleanser's second mode: "Target opponent loses all counters. That
#: player can't get counters for as long as this creature remains on the
#: battlefield." - CR 122.1's counters a player has, all removed, then a
#: recorded CR 611.1 rule effect (`CastingRuleKind.PLAYER_CANT_GET_COUNTERS`)
#: read by `Game.player_counters_prohibited`. The second sentence is optional,
#: so a bare "Target player loses all counters." reads too.
_PLAYER_LOSES_ALL_COUNTERS_RE = re.compile(
    r"^(?P<phrase>target (?:opponent|player)) loses all counters\."
    r"(?:\s*that player can'?t get counters for as long as this"
    r" (?P<noun>creature|permanent|artifact|enchantment|land|saga) remains on the battlefield\.)?$",
    re.IGNORECASE,
)


def _parse_player_loses_all_counters_clause(text: str) -> TargetedClause | None:
    """`_PLAYER_LOSES_ALL_COUNTERS_RE`'s shape; see the banner above."""
    match = _PLAYER_LOSES_ALL_COUNTERS_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    lasting = match.group("noun") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from ..casting_restrictions import CastingRuleEffect, CastingRuleKind

        players = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, Player)
        ]
        for player in players:
            for kind in list(player.counters):
                present = player.counter_count(kind)
                if present:
                    player.remove_counters(kind, present)
        if not lasting:
            return
        source = _source_still_here(game, stack_object)
        if source is None:
            return
        for player in players:
            game.casting_rule_effects.append(
                CastingRuleEffect(
                    kind=CastingRuleKind.PLAYER_CANT_GET_COUNTERS,
                    controller=game.controller_of(stack_object).username,
                    source_name=source.name,
                    duration=Duration.FOR_AS_LONG_AS,
                    restricted_player=player.username,
                    while_source_id=source.id,
                    while_source_stamp=source.zone_change_stamp,
                )
            )

    return effect


#: "Tap/Untap [up to one ]target X and [up to one ]target Y." - Kiora, Master
#: of the Depths' +1 ("Untap up to one target creature and up to one target
#: land."). `_DESTROY_TWO_TARGETS_RE`'s shape with the tap/untap verbs: two
#: instances of "target" in one instruction (CR 115.3), each chosen on its
#: own, which `_CLAUSE_SEPARATOR`'s bare-"and" split would otherwise cut into
#: a verbless "up to one target land" fragment. `tap_ability_targets`/
#: `untap_ability_targets` already act on every target still legal
#: (CR 608.2b), so nothing new happens at resolution.
_TAP_UNTAP_TWO_TARGETS_RE = re.compile(
    r"^(?P<verb>tap|untap) (?P<phrase>(?:up to one )?target [^.]+? and "
    r"(?:up to one )?target [^.]+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
@SPELL_TEXT.rung("s18")
def _parse_tap_untap_two_targets_clause(effect_text: str) -> Effect | None:
    """`_TAP_UNTAP_TWO_TARGETS_RE`'s shape, on a spell or an ability - both
    resolve through the same stack-object-generic target effects."""
    match = _TAP_UNTAP_TWO_TARGETS_RE.fullmatch(_strip_non_effect_preamble(effect_text).strip())
    if match is None:
        return None
    if not _two_battlefield_targets_understood(match.group("phrase"), up_to_one=True):
        return None
    if match.group("verb").lower() == "tap":
        return tap_ability_targets
    return untap_ability_targets


def remove_ability_targets_from_combat_and_untap(game: "Game", stack_object: "StackObject") -> None:
    """Remove each still-legal target from combat and untap it (CR 506.4, 701.26b)."""
    for target in game.resolve_targets(stack_object):
        if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
            game.combat.remove(target.id)
            target.untap()


#: Orim's Chant: "Target player can't cast spells this turn. If this spell
#: was kicked, creatures can't attack this turn." Read whole (ahead of
#: `_parse_mixed_clauses`, which has no shape for either sentence on its
#: own): the first is `machines.casting_restrictions.CastingRuleKind.
#: TARGETED_CANT_CAST`, a targeted cousin of Ranger-Captain of Eos's own
#: "your opponents can't cast noncreature spells" row (CR 611.1); the second
#: is CR 702.33d/g's kicker-conditional clause, read off `Game.cast_record
#: (spell).kicked` the same way `_parse_damage_target_kicked_instead_clause`
#: already reads Burst Lightning's, and gated behind `Game.
#: creatures_cant_attack_until_turns_taken` (CR 508.1c) rather than any
#: per-permanent grant, since the restriction touches every creature any
#: player controls, not one named object.
_TARGET_PLAYER_CANT_CAST_KICKED_ATTACK_RE = re.compile(
    r"^target player can'?t cast spells this turn\.\s*"
    r"if this spell was kicked, creatures can'?t attack this turn\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s18")
def _parse_target_player_cant_cast_kicked_attack_clause(effect_text: str) -> Effect | None:
    """`_TARGET_PLAYER_CANT_CAST_KICKED_ATTACK_RE`'s shape, or `None`."""
    whole = _strip_non_effect_preamble(effect_text).strip()
    if _TARGET_PLAYER_CANT_CAST_KICKED_ATTACK_RE.fullmatch(whole) is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        for target in game.resolve_targets(spell):
            if isinstance(target, Player):
                game.casting_rule_effects.append(
                    create_targeted_cant_cast_restriction(
                        controller.username, target.username, spell.name
                    )
                )
        record = game.cast_record(spell)
        if record.kicked > 0 and game.turn is not None:
            game.creatures_cant_attack_until_turns_taken = int(game.turn.turns_taken)

    return effect


#: "Flashback" (the spell, not the keyword): "Target instant or sorcery card
#: in your graveyard gains flashback until end of turn. The flashback cost
#: is equal to its mana cost." CR 702.34a's keyword is two static abilities
#: this engine builds nothing for as a *granted* ability - `machines/casting.
#: keyword_cast_options`/`_keyword` only ever read a keyword printed on the
#: `Card` itself, never one a resolving spell handed out at runtime, and
#: `Card` is deliberately immutable (see this module's own header comment on
#: `docs/` conventions) so there is nowhere on the object to stamp a granted
#: keyword even if `keyword_cast_options` did look for one.
#:
#: The *observable* effect is close enough to CR 601.3's ordinary "you may
#: cast/play [that card] this turn" permission - which **is** built, as
#: `machines/casting.PlayPermission`/`Game.grant_play_permission` - that this
#: reuses it rather than the keyword machinery: `zone=Zone.GRAVEYARD` lets
#: the permission reach a card that never left the graveyard,
#: `pays_mana_cost=True` matches "the flashback cost is equal to its mana
#: cost" exactly. CR 702.34a's "then exile it instead of putting it anywhere
#: else" is the same grant's second half, and `flashback=True` below is what
#: tells `Casting.cast()` to write `CastRecord.keyword = "Flashback"` even
#: though no keyword was announced - the only thing
#: `machines/replacement.py`'s exile-on-leaving-the-stack check
#: (`_stack_replacements`) actually reads. See `PlayPermission.flashback`'s
#: own docstring.
#:
#: The identical sentence is also a creature's ETB trigger consequence
#: rather than a whole spell's only instruction - Stingcaster Mage: "When
#: this creature enters, target instant or sorcery card in your graveyard
#: gains flashback until end of turn. The flashback cost is equal to its
#: mana cost." Same regex, same effect, read by `_ability_effect_or_notice`
#: (triggered/activated abilities) as well as `_spell_effect_or_notice`
#: (a spell's own resolution) - CR 601.3's grant does not care which kind
#: of resolving object handed it out.
_GRANT_FLASHBACK_RE = re.compile(
    r"^(?P<phrase>target instant or sorcery card in your graveyard) gains flashback "
    r"until end of turn\.\s*the flashback cost is equal to its mana cost\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s13")
@SPELL_TEXT.rung("s21")
def _parse_grant_flashback_clause(effect_text: str) -> Effect | None:
    """`_GRANT_FLASHBACK_RE`'s shape, or `None` if this is not it."""
    match = _GRANT_FLASHBACK_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), battlefield_only=False):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        for target in game.resolve_targets(spell):
            if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD:
                game.grant_play_permission(
                    target,
                    controller.username,
                    action=PlayAction.CAST,
                    pays_mana_cost=True,
                    flashback=True,
                    source_name=spell.name,
                    zone=Zone.GRAVEYARD,
                    rule="CR 601.3",
                )

    return effect


#: Past in Flames: "Each instant and sorcery card in your graveyard gains
#: flashback until end of turn. The flashback cost is equal to its mana
#: cost." The same CR 601.3-shaped grant `_GRANT_FLASHBACK_RE` already reads
#: for the "Flashback" spell above, generalised from one chosen target to
#: every qualifying card in the graveyard - CR 608.2c runs the sentence over
#: the whole set at once, not once per card with a fresh choice. The same
#: `flashback=True` applies here too, for the same reason
#: `_parse_grant_flashback_clause`'s own comment gives.
_EACH_GRAVEYARD_INSTANT_SORCERY_GAINS_FLASHBACK_RE = re.compile(
    r"^each instant and sorcery card in your graveyard gains flashback "
    r"until end of turn\.\s*the flashback cost is equal to its mana cost\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s21")
def _parse_each_graveyard_instant_sorcery_gains_flashback_clause(effect_text: str) -> Effect | None:
    """`_EACH_GRAVEYARD_INSTANT_SORCERY_GAINS_FLASHBACK_RE`'s shape, or `None`."""
    if _EACH_GRAVEYARD_INSTANT_SORCERY_GAINS_FLASHBACK_RE.fullmatch(effect_text.strip()) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        for card in list(controller.graveyard):
            if card is spell:
                continue
            if Type.INSTANT not in card.types and Type.SORCERY not in card.types:
                continue
            game.grant_play_permission(
                card,
                controller.username,
                action=PlayAction.CAST,
                pays_mana_cost=True,
                flashback=True,
                source_name=spell.name,
                zone=Zone.GRAVEYARD,
                rule="CR 601.3",
            )

    return effect


def _is_layer_effect_text(text: str) -> bool:
    """True if `text` - a resolving ability's or spell's own effect text - is
    one of `machines.layers`'s one-shot resolution shapes (CR 611.2), or
    looks like one that did not fully parse. The static-only anthem shape (CR
    611.3) never counts, however cleanly it parses:
    `is_resolution_layer_effect_text` is the function that draws that line,
    because a plain "Creatures you control get +N/+N." belongs to the
    permanent's own static ability and never to a spell's or ability's
    resolution - routing it here too would create a second, permanent copy
    on top of what the battlefield sweep already reapplies (CR 613.5).

    Checked on the **raw, unsplit** text rather than after `split_effect_
    clauses` has cut it into clauses: that splitter cuts on every bare " and "
    (`_CLAUSE_SEPARATOR`), which is right for "gets +N/+N and gains
    <keyword>" but wrong for an "and" that is not a clause boundary at all -
    "power **and** toughness each equal to its mana value" (Karn, the Great
    Creator's +1) splits into two unreadable halves that way. `machines.
    layers._effect_sentences` only splits on line breaks and ". ", so reading
    the whole text through `is_resolution_layer_effect_text` keeps a sentence
    like that one piece.
    """
    return is_resolution_layer_effect_text(text)


def _layer_remainder_or_composed(
    remainder_text: str, *, for_spell: bool, layer_text: str | None = None
) -> TargetedClause | None:
    """Whatever `parse_mixed_effect_for_spell`/`parse_mixed_effect` reads out
    of `remainder_text`, or `None` when neither can - in which case the
    caller records a `LayerRemainderNotice` instead. Shared by every layer-
    fallback call site (whole spell, whole ability, one mode of either) so
    the remainder is always read the same way, regardless of which shape
    carries the layer sentence beside it.
    """
    from ..becomes import counter_list_on_anaphor, counters_on_what_became_this_way

    # Abigale, Eloquent First-Year's "Put a flying counter, a first strike
    # counter, and a lifelink counter on that creature." - one instruction
    # the clause splitter would cut at its commas (`machines/becomes.py`).
    counters = counter_list_on_anaphor(remainder_text)
    if counters is not None:
        return counters
    # Rise and Shine's "Put four +1/+1 counters on each artifact that became a
    # creature this way." - the layer sentence's own target, checked.
    became = counters_on_what_became_this_way(remainder_text)
    if became is not None:
        return became
    # Malicious Eclipse's "If a creature an opponent controls would die this
    # turn, exile it instead.", Death Frenzy's "Whenever a creature dies this
    # turn, ...", Predatory Rampage's "... blocks this turn if able." - the
    # riders that last the turn (`machines/turn_scoped_riders.py`).
    turn_scoped = turn_scoped_rider(remainder_text, for_spell=for_spell)
    if turn_scoped is not None:
        return turn_scoped
    read = (
        parse_mixed_effect_for_spell(remainder_text)
        if for_spell
        else parse_mixed_effect(remainder_text)
    )
    if read is not None or layer_text is None:
        return read
    # Crash Landing's "<self> deals damage to that creature equal to ..."
    # after "Target creature with flying loses flying until end of turn.":
    # CR 608.2c's "that creature" is the layer sentence's one target.
    if len(re.findall(r"\btarget\b", layer_text, re.IGNORECASE)) != 1:
        return None
    return damage_to_layer_target_rider(remainder_text)


#: CR 702.96a: overload rewrites "target" to "each" - read by
#: `machines/overload.py` off the printed sentences, so the keyword line is
#: resolution-neutral here like any other (kept as the name of that keyword).
_TEXT_CHANGING_KEYWORD_LINE_RE = re.compile(r"^overload\b", re.IGNORECASE)


def _is_resolution_neutral_keyword_line(sentence: str) -> bool:
    """Whether `sentence` is a keyword-ability line printed beside a spell's
    resolution text rather than part of it - Startling Development's own
    "Cycling {1}" (CR 702.29a: an activated ability that works from the
    hand, never an instruction of the resolving spell). `_plain_resolution_
    sentences` keeps such a line as a sentence of its own, and
    `_compose_layer_effect_with_remainder` would otherwise record it as an
    unread remainder of a spell whose every instruction it applied. Overload
    (CR 702.96a) is one too: its cost is paid at casting, and what it changes
    ("target" to "each") is read by `machines/overload.py` off the printed
    sentences, never off this line."""
    return _is_keyword_ability_line(sentence)


@SPELL_TEXT.rung("s24")
def _compose_layer_effect_with_remainder(effect_text: str) -> Effect | None:
    """A whole resolving spell's own effect text, when some sentence of it is
    a CR 611.2 layer shape (`_is_layer_effect_text`) but the text as a whole
    did not parse through `parse_mixed_effect_for_spell` - `_spell_effect_or_
    notice`'s own fallback, widened to compose rather than to silently drop
    whatever sentence is not the layer shape (see `LayerRemainderNotice`).

    `None` when `effect_text` carries no *genuinely* readable layer sentence
    at all (`parsed_layer_effects` finds none) and does not even loosely
    resemble one (`is_resolution_layer_effect_text` is also false) - the
    caller's cue to keep trying its own other fallbacks (an unreadable
    conditional, an unreadable search, an unreadable anaphoric clause, ...)
    exactly as before this existed. When it carries no genuine layer sentence
    but does loosely resemble one, the bare sentinel is returned unchanged -
    `create_continuous_effect` already answers that case correctly on its
    own, through `effects_for`'s own `LayerNotice` channel, and there is
    nothing genuine here to compose a remainder around: Kraul Harpooner's
    *permanent spell* reads its own Undergrowth trigger's condition and body
    as if they were sibling instructions of a spell resolution this way, and
    neither is one.
    """
    if not genuine_resolution_layer_text(effect_text):
        return create_continuous_effect if is_resolution_layer_effect_text(effect_text) else None
    sentences = _plain_resolution_sentences(effect_text)
    remainder = [
        sentence
        for sentence in sentences
        if not is_genuine_resolution_layer_sentence(sentence)
        and not is_x_substituted_layer_sentence(sentence)
        and not _is_resolution_neutral_keyword_line(sentence)
        # Strive's per-target cost increase (Setessan Tactics) is CR 601.2f's
        # cost, already charged as the spell was cast - never an instruction
        # of its resolution (`_strip_non_effect_preamble` drops the same line).
        and not _COST_INCREASE_PER_TARGET_LINE_RE.match(sentence.strip())
    ]
    if remainder and any(_looks_like_embedded_ability_line(sentence) for sentence in remainder):
        # `effect_text` is not one clean resolution paragraph at all - it is
        # a *permanent's* whole raw printed text (CR 608.3a: there is no
        # spell resolution to run for one in the first place), with a
        # genuine layer sentence from a *different*, already-separately-read
        # ability (an activated ability's own cost-and-effect line, a
        # triggered ability's own condition) embedded beside it. Ingris
        # Stingerquill's own "{4}: Create a Cadet. Then creatures you
        # control gain haste until end of turn." is read correctly through
        # `activated_effect_for`; reaching the identical group-haste
        # sentence again from here, with its own cost line as the
        # "remainder", would both double the credit and misreport this
        # permanent spell's own (nonexistent) resolution as an unread gap.
        return None
    if not remainder:
        # Every sentence is a layer shape (or the text could not be split
        # into sentences at all - `_plain_resolution_sentences` then comes
        # back empty, and there is nothing to compose either way): unchanged
        # behaviour, the bare sentinel `create_continuous_effect` is
        # returned so `scripts/sweep_pool.py`'s `_dispatch_category` still
        # reads the whole-card verdict off `_layer_category` the way it
        # always has.
        return create_continuous_effect
    remainder_text = " ".join(remainder)
    layer_text = " ".join(sentence for sentence in sentences if sentence not in remainder)
    remainder_effect = _layer_remainder_or_composed(
        remainder_text, for_spell=True, layer_text=layer_text
    )
    if remainder_effect is not None:

        def layer_and_remainder_effect(game: "Game", spell: CardState) -> None:
            run_layer_then_rider(game, spell, create_continuous_effect, remainder_effect)

        return layer_and_remainder_effect

    def layer_effect_with_remainder_notice(game: "Game", spell: CardState) -> None:
        create_continuous_effect(game, spell)
        game.layer_remainder_notices.append(
            LayerRemainderNotice(
                source_id=spell.id, source_name=spell.card.name, text=remainder_text
            )
        )

    return _with_unparsed_remainder(layer_effect_with_remainder_notice, remainder_text)


#: "If `<condition>`, put `<n>` `<kind>` counter(s) on it/that creature/this
#: creature instead." - Desperate Futurescribe's own combat trigger ("...
#: gets +1/+1 until end of turn. If you've scried or surveilled this turn,
#: put a +1/+1 counter on that creature instead") and Power Plant Worker's
#: real, off-set activated ability ("... gets +2/+2 until end of turn. If
#: you control creatures named Mine Worker and Tower Worker, put two +1/+1
#: counters on this creature instead"). CR 614.1a: "instead" replaces the
#: whole preceding sentence's effect rather than adding to it, so this is an
#: exclusive swap - at resolution either the layer pump runs (CR 611.2) or
#: the counter(s) land on the same object(s) the pump would have affected,
#: never both and never neither. `Game.condition_holds` already answers the
#: condition itself (it is what reads "you've scried or surveilled this
#: turn" for every other card printing it); this only adds the swap on top.
_LAYER_COUNTER_INSTEAD_UPGRADE_RE = re.compile(
    rf"^if (?P<condition>.+?),\s*put {count_pattern('n')} "
    r"(?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    r"(?:it|that creature|that permanent|that artifact|that enchantment|that land|that token|"
    r"that card|this creature|this permanent) instead$",
    re.IGNORECASE,
)


def _parse_layer_counter_instead_upgrade(
    remainder_text: str,
) -> tuple[str, int, "Counter | str"] | None:
    """`_LAYER_COUNTER_INSTEAD_UPGRADE_RE`'s shape, or `None` when the
    remainder is not that shape at all (a genuinely unreadable condition
    still reaches this - it is answered at resolution by `Game.condition_
    holds` returning `None`, not refused here, so an unread condition still
    fails closed with a `LayerRemainderNotice` the same way it always has)."""
    match = _LAYER_COUNTER_INSTEAD_UPGRADE_RE.fullmatch(remainder_text.strip().rstrip(".").strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))
    return match.group("condition").strip(), amount, kind


#: "target artifact you control gains "{T}: This artifact deals 2 damage to any
#: target" for as long as you control this creature." (Quicksmith Rebel),
#: "... gains "{T}: Draw a card" for as long as you control this creature."
#: (Quicksmith Spy) - a layer 6 grant of a *quoted* ability (CR 613.1f) lasting
#: CR 611.2b's "for as long as": the duration is the *source's* - here, that the
#: ability's controller still controls this creature, or that this permanent
#: remains on the battlefield - never the target's. The ability is a CR 113.1c
#: object of its own once on the stack, so the grant is built off the resolving
#: ability's source as it resolves: a source already gone (or one that left and
#: came back, CR 400.7) means the duration never starts, and per CR 611.2b the
#: effect then does nothing. The until-end-of-turn twin is
#: `blight_effects.parse_target_gains_quoted_ability_until_eot_clause`.
_TARGET_GAINS_QUOTED_FOR_AS_LONG_RE = re.compile(
    r'^(?P<phrase>target .+?) gains ["“](?P<ability>[^"”]+)["”] for as long as '
    r"(?:you control (?P<controls>this [a-z]+)|(?P<remains>this [a-z]+) remains on the battlefield)"
    r"\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_target_gains_quoted_ability_for_as_long_as_clause(
    effect_text: str,
) -> AbilityEffect | None:
    """`_TARGET_GAINS_QUOTED_FOR_AS_LONG_RE`'s shape - see the banner above."""
    stripped = " ".join(effect_text.split())
    if " gains " not in stripped or "for as long as" not in stripped:
        return None
    match = _TARGET_GAINS_QUOTED_FOR_AS_LONG_RE.fullmatch(stripped)
    if match is None:
        return None
    granted_text = match.group("ability").strip()
    if not granted_text or not _targets_understood(match.group("phrase"), count_agnostic=False):
        return None
    while_controlled = match.group("controls") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if (
            source is None
            or source.zone is not Zone.BATTLEFIELD
            or source.zone_change_stamp is None
            or (
                ability.source_stamp is not None
                and source.zone_change_stamp != ability.source_stamp
            )
        ):
            return
        condition: Condition
        if while_controlled:
            controller = source.controller
            if controller is None:
                return
            condition = YouStillControl(
                card_id=source.id, stamp=source.zone_change_stamp, controller=controller
            )
        else:
            condition = RemainsOnBattlefield(card_id=source.id, stamp=source.zone_change_stamp)
        store = continuous_effects(game)
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            store.add(
                ContinuousEffect(
                    description=(
                        f'{source.name}: {target.name} gains "{granted_text}" '
                        f"for as long as {match.group('controls') or match.group('remains')}"
                    ),
                    layer=Layer.ABILITY,
                    timestamp=store.tick(),
                    duration=Duration.FOR_AS_LONG_AS,
                    condition=condition,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=grant_ability(granted_text),
                ),
                game,
            )

    return effect


#: "This creature gains all activated abilities of target creature until end
#: of turn." (Quicksilver Elemental): CR 613.1f's layer 6 copy of the target's
#: whole activated abilities (CR 602.1), each with the target's own name
#: rewritten to "this permanent" (CR 201.5b) and fixed as the ability
#: resolves. The target keeps its own; the grant ends in the cleanup step.
_GAINS_ALL_ACTIVATED_ABILITIES_UNTIL_EOT_RE = re.compile(
    r"^this (?:creature|permanent) gains all activated abilities of (?P<phrase>target .+?) "
    r"until end of turn\.?(?: \(.*\))?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_gains_all_activated_abilities_of_target_until_eot_clause(
    effect_text: str,
) -> AbilityEffect | None:
    """`_GAINS_ALL_ACTIVATED_ABILITIES_UNTIL_EOT_RE`'s shape - see the banner."""
    stripped = " ".join(effect_text.split())
    if "all activated abilities of" not in stripped:
        return None
    match = _GAINS_ALL_ACTIVATED_ABILITIES_UNTIL_EOT_RE.fullmatch(stripped)
    if match is None or not _targets_understood(match.group("phrase"), count_agnostic=False):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        store = continuous_effects(game)
        board = game.computed_board()
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            for order, text in enumerate(
                activated_ability_lines(board.of(target).abilities, target.name)
            ):
                store.add(
                    ContinuousEffect(
                        description=f'{source.name}: gains "{text}" until end of turn',
                        layer=Layer.ABILITY,
                        timestamp=store.tick(),
                        order=order,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=only_this_incarnation(source, source.zone_change_stamp),
                        modification=grant_ability(text),
                    ),
                    game,
                )

    return effect


#: "That creature/permanent gets +N/+N[ and gains `<keyword>`] until end of
#: turn." (or "it", CR 400.7's bare pronoun) with no "target" anywhere in the
#: ability's own text - the plain anaphor back to the *triggering event's own
#: subject*, not the ability's own source: Ardoz, Cobbler of War's "Whenever
#: Ardoz or another creature you control enters, that creature gets +2/+0
#: until end of turn." fires on *any* qualifying creature entering, not only
#: Ardoz himself, so `create_continuous_effect_of_ability`'s own "names no
#: target -> the source" fallback (Basking Rootwalla's own shape) is the
#: wrong default here. Rewritten to "target `<noun>`" before reaching
#: `machines/layers.py`, the same "textual stand-in only, the real object is
#: supplied separately" contract `_RIDER_LAYER_SUBJECT_RE`'s own "It gets
#: +N/+N ..." rider already relies on - `parsed_layer_effects` never
#: re-derives who is affected from the sentence's own wording, only which
#: shape of sentence this is - so `targets` is supplied straight from
#: `AbilityOnStack.event.subject_id` (the same field `event_subject_power`
#: already reads for a dying creature's power) instead of from `Game.
#: resolve_card_targets`.
#:
#: "The blocking creature" (Flanking, CR 702.25a) is the identical anaphor,
#: one noun phrase over: CR 509.1a's blocking creature is exactly what a
#: `TriggerEvent.BLOCKS` event's own `subject_id` already names, whichever
#: side of the block declared the trigger's own "this creature" - so it needs
#: no noun captured at all, only the `creature` default below.
_EVENT_SUBJECT_PUMP_RE = re.compile(
    r"^(?:that (?P<noun>creature|permanent)|the blocking creature|it)\b(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s36")
def _parse_event_subject_pump_clause(effect_text: str) -> AbilityEffect | None:
    """`_EVENT_SUBJECT_PUMP_RE`'s shape - see the banner above.

    Refused (never claimed) when the ability's own text mentions "target"
    anywhere: that shape is `create_continuous_effect_of_ability`'s own
    ordinary target-resolution path, already correct.
    """
    stripped = effect_text.strip()
    if "target" in stripped.lower():
        return None
    match = _EVENT_SUBJECT_PUMP_RE.match(stripped)
    if match is None:
        return None
    noun = match.group("noun") or "creature"
    rewritten = f"target {noun}{match.group('rest')}".rstrip()
    if not rewritten.endswith("."):
        # A keyword's own `_TRIGGER_EXPANSIONS` effect text (Flanking's "the
        # blocking creature gets -1/-1 until end of turn") carries no
        # trailing period - `_expansion` never adds one - unlike a printed
        # oracle sentence, which always keeps its own. `parsed_layer_effects`
        # reads by sentence (`_effect_sentences`) and needs one to see this
        # as a complete sentence rather than nothing at all.
        rewritten += "."
    if not is_genuine_resolution_layer_sentence(rewritten):
        return None
    builder = parsed_layer_effects(rewritten)
    if builder is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        event = ability.event
        if event is None or event.subject_id is None:
            return
        subject = game.find_by_id(event.subject_id)
        if subject is None or subject.zone is not Zone.BATTLEFIELD:
            return
        effects = continuous_effects(game)
        for built in builder(
            source,
            effects.tick(),
            [subject],
            layer_context_for(game, game.controller_of(ability)),
        ):
            effects.add(built, game)

    return effect


#: "it gets +2/+0 until end of turn and this enchantment deals 1 damage to
#: you." (Anthem of Rakdos) - `_EVENT_SUBJECT_PUMP_RE`'s anaphoric pump of the
#: trigger event's subject, then the source's own damage as a second
#: instruction in the same sentence (CR 608.2c: in the order written). Only the
#: source's own "this <noun>" may be the dealer - a bare "it" after "and" would
#: name the pumped creature, which this reader does not guess.
_EVENT_SUBJECT_PUMP_THEN_SELF_DEALS_RE = re.compile(
    r"^(?P<pump>(?:that (?:creature|permanent)|the blocking creature|it) gets [^.]+?) and "
    r"(?P<deal>this [a-z]+ deals [^.]+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36", before=["continuous._parse_event_subject_pump_clause"])
def _parse_event_subject_pump_then_self_damage_clause(effect_text: str) -> AbilityEffect | None:
    """`_EVENT_SUBJECT_PUMP_THEN_SELF_DEALS_RE`'s shape - see the banner above."""
    stripped = " ".join(effect_text.split())
    if " deals " not in stripped or "target" in stripped.lower():
        return None
    match = _EVENT_SUBJECT_PUMP_THEN_SELF_DEALS_RE.fullmatch(stripped)
    if match is None:
        return None
    pump = _parse_event_subject_pump_clause(match.group("pump") + ".")
    deal = parse_mixed_effect(match.group("deal") + ".")
    if pump is None or deal is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        pump(game, ability)
        deal(game, ability)

    return effect


#: Gloom Ripper: "target creature you control gets +X/+0 until end of turn
#: and up to one target creature an opponent controls gets -0/-X until end of
#: turn, where X is `<expr>`." Two *different* target descriptions sharing one
#: "and", the identical CR 608.2c single-instruction shape `_EXILE_SEVERAL_
#: UP_TO_ONE_TARGETS_THEN_RETURN_RE` already reads for its own two-target
#: exile - only here the two targets get two different effects, not the same
#: one, and one of the two is mandatory rather than "up to one" on both
#: sides. `expr` is read the ordinary way, through `amount_expression`.
_TARGET_PLUS_X_MINUS_X_RE = re.compile(
    r"^target creature you control gets \+x/\+0 until end of turn and "
    r"up to one target creature an opponent controls gets -0/-x until end of turn,"
    r" where x is (?P<expr>.+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_target_plus_x_minus_x_clause(effect_text: str) -> AbilityEffect | None:
    """`_TARGET_PLUS_X_MINUS_X_RE`'s shape, or `None`.

    Which resolved target is which is read off each target's own live
    controller (CR 613.5), not off `resolve_targets`' position - an earlier
    target can be skipped as illegal (CR 608.2b) without shifting a later
    one out of place, and "you control" versus "an opponent controls" are
    mutually exclusive by construction, so a target's own controller always
    settles it correctly regardless of order.
    """
    match = _TARGET_PLUS_X_MINUS_X_RE.fullmatch(" ".join(effect_text.strip().split()))
    if match is None:
        return None
    reader = amount_expression(match.group("expr"))
    if reader is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = ability.controller
        source = ability.source(game)
        amount = reader(game, controller, source, ability.x_value)
        if amount <= 0:
            return
        board = game.computed_board()
        store = continuous_effects(game)
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            target_controller = board.of(target).controller
            if target_controller == controller:
                power, toughness = amount, 0
            elif target_controller is not None:
                power, toughness = 0, -amount
            else:
                continue
            description = f"{ability.source_name}: {target.name} gets {power:+d}/{toughness:+d}"
            store.add(
                ContinuousEffect(
                    description=description,
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=store.tick(),
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=_only(target.id),
                    modification=modify_power_toughness(power, toughness),
                )
            )

    return effect


#: A base power and toughness *set* (CR 613.4b, sublayer 7b) a triggered
#: ability applies until end of turn, in three wordings of one mechanic:
#:
#: - Galion, Elvenking's Butler: "choose up to one other target creature you
#:   control. Its base power and toughness become equal to Galion's power and
#:   toughness until end of turn." - the target, a value copied off the source;
#: - Mirkwood Meditator: "you may have this creature's base power and
#:   toughness become 4/2 until end of turn." - optional (CR 608.2d), the
#:   source, a printed value;
#: - Eldrazi Mimic: "you may have this creature's base power and toughness
#:   become equal to that creature's power and toughness until end of turn." -
#:   optional, the source, a value copied off the trigger's own subject.
#:
#: A copied value is read once, as the ability resolves (CR 608.2h), and then
#: fixed - a later pump on the object copied does not move it. The subject is
#: fixed then too (CR 611.2c).
_SELF_WORDS = r"this creature|this permanent"
_BASE_PT_BECOME_RE = re.compile(
    r"^(?:(?P<choose>choose (?:up to one |one |a )?(?:other |another )?target creature"
    r"(?: you control)?)\. its"
    rf"|(?P<may>you may have )?(?P<subject>{_SELF_WORDS}|that creature)['’]s)"
    r" base power and toughness become "
    r"(?:(?P<power>\d+)/(?P<toughness>\d+)"
    rf"|equal to (?P<reference>{_SELF_WORDS}|that creature)['’]s power and toughness)"
    r" until end of turn\.?$",
    re.IGNORECASE,
)


def _base_pt_become_object(game: "Game", ability: AbilityOnStack, word: str) -> CardState | None:
    """ "this creature" is the ability's source, "that creature" the trigger's
    own event subject (CR 603.2) - each only while it is still the object the
    ability knew (a permanent that left the battlefield is a new object, CR
    400.7, and has no current characteristics to set)."""
    if word.lower() == "that creature":
        event = ability.event
        if event is None or event.subject_id is None:
            return None
        return game.find_by_id(event.subject_id)
    return ability.source(game)


@ABILITY_TEXT.rung("s8")
def _parse_base_pt_become_clause(effect_text: str) -> AbilityEffect | None:
    """`_BASE_PT_BECOME_RE`'s shape - see the banner above."""
    match = _BASE_PT_BECOME_RE.fullmatch(" ".join(effect_text.strip().split()))
    if match is None:
        return None
    optional = match.group("may") is not None
    fixed = (
        (int(match.group("power")), int(match.group("toughness")))
        if match.group("power") is not None
        else None
    )

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if match.group("choose") is not None:
            subjects = [
                target
                for target in game.resolve_card_targets(ability)
                if target.zone is Zone.BATTLEFIELD
            ]
        else:
            subject = _base_pt_become_object(game, ability, match.group("subject"))
            subjects = [subject] if subject is not None and subject.zone is Zone.BATTLEFIELD else []
        if not subjects:
            return
        if fixed is not None:
            power, toughness = fixed
        else:
            reference = _base_pt_become_object(game, ability, match.group("reference"))
            if reference is None:
                return
            if reference.zone is Zone.BATTLEFIELD:
                power, toughness = game.characteristics_of(reference).numeric_power_toughness
            else:
                # CR 608.2h: an object no longer where the ability expected
                # it is read by its last known information.
                power, toughness = reference.power or 0, reference.toughness or 0
        controller = game.controller_of(ability)
        if optional and not game.may(
            controller,
            f"have {subjects[0].name}'s base power and toughness become "
            f"{power}/{toughness} until end of turn",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        effects = continuous_effects(game)
        timestamp = effects.tick()
        for subject in subjects:
            effects.add(
                ContinuousEffect(
                    description=(
                        f"{ability.source_name}: {subject.name} has base power and "
                        f"toughness {power}/{toughness}"
                    ),
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.SET,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=only_this_incarnation(subject, subject.zone_change_stamp),
                    modification=set_power_toughness(power, toughness),
                ),
                game,
            )

    return effect


#: The same layer 7b set (CR 613.4b) on the ability's own source, with a
#: keyword granted for the same duration: "until end of turn, Moon Girl and
#: Devil Dinosaur's base power and toughness become 6/6 and they gain
#: trample." (the name already "this permanent", the duration leading) and
#: Shorecrasher Mimic's "this creature has base power and toughness 5/3 until
#: end of turn and gains trample until end of turn." (a "has" form, the
#: duration trailing each half).
_SELF_BASE_PT_SET_WITH_KEYWORDS_RE = re.compile(
    rf"^(?P<lead>until end of turn, )?(?:(?:{_SELF_WORDS})['’]s base power and toughness become"
    rf"|(?:{_SELF_WORDS}) (?:has|have) base power and toughness) "
    r"(?P<power>\d+)/(?P<toughness>\d+)(?P<trail> until end of turn)?"
    r" and (?:it gains|they gain|gains?) (?P<keywords>[^.]+?)(?: until end of turn)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s4")
def _parse_self_base_pt_set_with_keywords_clause(effect_text: str) -> AbilityEffect | None:
    """`_SELF_BASE_PT_SET_WITH_KEYWORDS_RE`'s shape: the source's base power
    and toughness set in layer 7b and each keyword granted in layer 6 (CR
    613.1f), both until end of turn (CR 514.2), with one shared timestamp.
    The source must still be the object that triggered (CR 400.7)."""
    match = _SELF_BASE_PT_SET_WITH_KEYWORDS_RE.fullmatch(" ".join(effect_text.strip().split()))
    if match is None or not (match.group("lead") or match.group("trail")):
        return None
    keywords = _split_and_validate_keywords(match.group("keywords"))
    if keywords is None:
        return None
    power, toughness = int(match.group("power")), int(match.group("toughness"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        subject = ability.source(game)
        if subject is None or subject.zone is not Zone.BATTLEFIELD:
            return
        if ability.source_stamp not in (None, subject.zone_change_stamp):
            return
        store = continuous_effects(game)
        timestamp = store.tick()
        selector = only_this_incarnation(subject, subject.zone_change_stamp)
        store.add(
            ContinuousEffect(
                description=(
                    f"{ability.source_name}: {subject.name} has base power and "
                    f"toughness {power}/{toughness}"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.SET,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                selector=selector,
                modification=set_power_toughness(power, toughness),
            ),
            game,
        )
        for keyword in keywords:
            store.add(
                ContinuousEffect(
                    description=f"{ability.source_name}: {subject.name} gains {keyword}",
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=selector,
                    modification=grant_ability(keyword),
                ),
                game,
            )

    return effect


def _layer_sentences_come_last(sentences: Sequence[str]) -> bool:
    """True when every genuine layer sentence of an ability follows every
    other sentence - the printed order `_compose_layer_effect_with_
    remainder_for_ability` then keeps (CR 608.2c)."""
    layer_positions = [
        index
        for index, sentence in enumerate(sentences)
        if is_genuine_resolution_layer_sentence(sentence)
    ]
    other_positions = [
        index
        for index, sentence in enumerate(sentences)
        if not is_genuine_resolution_layer_sentence(sentence)
    ]
    return bool(layer_positions and other_positions) and min(layer_positions) > max(other_positions)


@ABILITY_TEXT.rung("s43")
def _compose_layer_effect_with_remainder_for_ability(effect_text: str) -> AbilityEffect | None:
    """The ability-side twin of `_compose_layer_effect_with_remainder`, for
    `_ability_effect_or_notice`'s own `_is_layer_effect_text` fallback."""
    if not genuine_resolution_layer_text(effect_text):
        return (
            create_continuous_effect_of_ability
            if is_resolution_layer_effect_text(effect_text)
            else None
        )
    sentences = _plain_resolution_sentences(effect_text)
    remainder = [
        sentence for sentence in sentences if not is_genuine_resolution_layer_sentence(sentence)
    ]
    if not remainder:
        return create_continuous_effect_of_ability
    remainder_text = " ".join(remainder)

    instead_upgrade = _parse_layer_counter_instead_upgrade(remainder_text)
    if instead_upgrade is not None:
        condition_text, upgrade_amount, upgrade_kind = instead_upgrade

        def layer_or_counter_instead(game: "Game", ability: AbilityOnStack) -> None:
            source = ability.source(game)
            if source is None or source.zone is not Zone.BATTLEFIELD:
                return
            controller = game.controller_of(ability)
            ability_text = (
                substitute_x(ability.ability.text, ability.x_value)
                if isinstance(ability.ability, ActivatedAbility)
                and cost_announces_x(ability.ability.cost)
                else ability.ability.text
            )
            profile = profile_for_text(ability_text)
            requires_target = profile.understood and bool(profile.requirements)
            targets = game.resolve_card_targets(ability) if requires_target else [source]
            # CR 608.2h: the condition's own "it"/"that creature" is the same
            # object the pump (or the counter swap) affects - the ability's
            # own target when the printed sentence has one (Rampaging
            # Geoderm's "target attacking creature ... If it's attacking a
            # battle, ..."), the source otherwise (Desperate Futurescribe's
            # own scry/surveil condition names no object at all). Reading the
            # condition against the source alone used to answer Rampaging
            # Geoderm's own "it" as the ability's permanent rather than the
            # creature it just pumped. `ability=ability` additionally threads
            # the resolving `AbilityOnStack` itself through, for a condition
            # about the activation's own mana payment (`machines/conditions/
            # activation.py`) rather than about either object.
            condition_subject = targets[0] if targets else source
            holds = game.condition_holds(
                controller.username, condition_text, condition_subject, ability=ability
            )
            if holds is None:
                # Unreadable condition: fail closed exactly as an ordinary
                # unreadable remainder always has - run the pump and record
                # the untried swap rather than guess which branch applies.
                create_continuous_effect_of_ability(game, ability)
                game.layer_remainder_notices.append(
                    LayerRemainderNotice(
                        source_id=ability.source_id,
                        source_name=ability.source_name,
                        text=remainder_text,
                    )
                )
                return
            if not holds:
                create_continuous_effect_of_ability(game, ability)
                return
            for target in targets:
                if target.zone is Zone.BATTLEFIELD:
                    game.add_counters(target, upgrade_kind, upgrade_amount)

        from .. import conditions

        if conditions.claims(condition_text):
            return layer_or_counter_instead
        return _with_unparsed_remainder(layer_or_counter_instead, remainder_text)

    remainder_effect = _layer_remainder_or_composed(remainder_text, for_spell=False)
    if remainder_effect is not None:
        # An animation that ends in its own "It's still a land." sentence
        # carries that clause in the closure (`machines/land_animation.py`).
        animation = retained_animation_sentence(sentences)
        layer_effect = (
            retained_animation_effect(animation)
            if animation is not None
            else create_continuous_effect_of_ability
        )
        if _layer_sentences_come_last(sentences):
            # CR 608.2c: "The controller of the spell or ability follows its
            # instructions in the order written." Nissa, Who Shakes the
            # World's +1 puts its counters on "target noncreature land" and
            # untaps it *before* "It becomes a 0/0 Elemental creature": run
            # the other way round, the land is already a creature when the
            # counter instruction checks its target, gets none, and dies a
            # 0/0 (CR 704.5f).
            def remainder_then_layer_effect(game: "Game", ability: AbilityOnStack) -> None:
                remainder_effect(game, ability)
                layer_effect(game, ability)

            return remainder_then_layer_effect

        def layer_and_remainder_effect(game: "Game", ability: AbilityOnStack) -> None:
            run_layer_then_rider(game, ability, layer_effect, remainder_effect)

        return layer_and_remainder_effect

    def layer_effect_with_remainder_notice(game: "Game", ability: AbilityOnStack) -> None:
        create_continuous_effect_of_ability(game, ability)
        game.layer_remainder_notices.append(
            LayerRemainderNotice(
                source_id=ability.source_id, source_name=ability.source_name, text=remainder_text
            )
        )

    return _with_unparsed_remainder(layer_effect_with_remainder_notice, remainder_text)


def _compose_layer_effect_with_remainder_for_mode(mode_text: str) -> Effect | None:
    """One chosen mode's own text (`parse_mode_effect`), the modal-spell twin
    of `_compose_layer_effect_with_remainder` - scoped to `mode_text` alone
    through `_create_continuous_effect_for_mode_text` rather than the bare
    `create_continuous_effect` sentinel, which would read the *whole* card's
    text and wrongly also apply a different, unchosen mode's own layer
    sentence the moment that mode happened to be one too.

    Gated on a *genuine* parse (`parsed_layer_effects`), stricter than the
    whole-card composers above: a mode has no prior "route to the bare
    sentinel" behaviour to preserve for a merely apparent layer sentence -
    before this function existed, `parse_mode_effect` simply returned `None`
    for one, and `resolve_modal_spell` recorded the correct `ModeNotice`.
    Returning a scoped-but-empty continuous effect here instead would make
    that mode look like it ran when nothing on it actually did.
    """
    if not genuine_resolution_layer_text(mode_text):
        return None
    sentences = _plain_resolution_sentences(mode_text)
    remainder = [
        sentence for sentence in sentences if not is_genuine_resolution_layer_sentence(sentence)
    ]
    layer_effect = _create_continuous_effect_for_mode_text(mode_text)
    if not remainder:
        return layer_effect
    if (
        len(sentences) > 1
        and remainder == sentences[1:]
        and is_genuine_resolution_layer_sentence(sentences[0])
    ):
        # Gnashing of Teeth's first mode, "Target creature gets -5/-5 until
        # end of turn. If that creature would die this turn, exile it
        # instead." - every sentence after the pump is a rider naming the
        # pump's own object (CR 608.2c: one instruction). Read alone, the
        # rider has no antecedent and failed closed; the anaphoric series
        # reads it against the pump, the same way a non-modal Bleed Dry is.
        anaphoric = _parse_object_anaphor_clause_series(
            sentences[0], sentences[1:], for_spell=True, layer_antecedent_first=True
        )
        if anaphoric is not None:
            return anaphoric
    remainder_text = " ".join(remainder)
    remainder_effect = _layer_remainder_or_composed(remainder_text, for_spell=True)
    if remainder_effect is not None:

        def layer_and_remainder_effect(game: "Game", spell: CardState) -> None:
            run_layer_then_rider(game, spell, layer_effect, remainder_effect)

        return layer_and_remainder_effect

    def layer_effect_with_remainder_notice(game: "Game", spell: CardState) -> None:
        layer_effect(game, spell)
        game.layer_remainder_notices.append(
            LayerRemainderNotice(
                source_id=spell.id, source_name=spell.card.name, text=remainder_text
            )
        )

    return _with_unparsed_remainder(layer_effect_with_remainder_notice, remainder_text)


def _compose_layer_effect_with_remainder_for_ability_mode(mode_text: str) -> AbilityEffect | None:
    """One chosen mode's own text, for a modal *triggered* ability
    (`_resolve_modal_triggered_ability_clause`) - the ability-side twin of
    `_compose_layer_effect_with_remainder_for_mode`. Gated on a genuine parse
    the same way, and for the same reason.
    """
    if not genuine_resolution_layer_text(mode_text):
        return None
    sentences = _plain_resolution_sentences(mode_text)
    remainder = [
        sentence for sentence in sentences if not is_genuine_resolution_layer_sentence(sentence)
    ]
    layer_effect = _create_continuous_effect_of_ability_for_mode_text(mode_text)
    if not remainder:
        return layer_effect
    remainder_text = " ".join(remainder)
    remainder_effect = _layer_remainder_or_composed(remainder_text, for_spell=False)
    if remainder_effect is not None:

        def layer_and_remainder_effect(game: "Game", ability: AbilityOnStack) -> None:
            run_layer_then_rider(game, ability, layer_effect, remainder_effect)

        return layer_and_remainder_effect

    def layer_effect_with_remainder_notice(game: "Game", ability: AbilityOnStack) -> None:
        layer_effect(game, ability)
        game.layer_remainder_notices.append(
            LayerRemainderNotice(
                source_id=ability.source_id, source_name=ability.source_name, text=remainder_text
            )
        )

    return _with_unparsed_remainder(layer_effect_with_remainder_notice, remainder_text)


#: "Until end of turn, whenever you tap a Mountain for mana, add an
#: additional {R}." (Molten Tide) and "Until end of turn, whenever a player
#: taps an Island for mana, that player adds an additional {U}." (High
#: Tide, off-set - fetched as a genericity precedent, not itself in the
#: pool). CR 603.7: a resolving spell creating a delayed triggered ability
#: with a stated duration ("until end of turn"). The subject word decides
#: the recipient without a separate group to keep in sync with it: "you
#: tap" pairs with a bare "add" (CR 608.2h's default subject, the ability's
#: own controller) and restricts to the controller's own taps; "a player
#: taps" pairs with an explicit "that player adds" and is unrestricted.
_UNTIL_END_OF_TURN_TAP_LAND_ADDITIONAL_MANA_RE = re.compile(
    r"^until end of turn, whenever (?:"
    r"you taps? an? (?P<your_land>[a-z]+) for mana, add"
    r"|a player taps an? (?P<any_land>[a-z]+) for mana, that player adds"
    r") an additional (?P<mana>(?:\{[wubrgc]\})+)\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s21")
def _parse_until_end_of_turn_tap_land_additional_mana_clause(text: str) -> AbilityEffect | None:
    """`_UNTIL_END_OF_TURN_TAP_LAND_ADDITIONAL_MANA_RE`'s shape - a whole,
    single-clause spell effect (Molten Tide and High Tide each print nothing
    else), so this is tried against the full text rather than split first.
    """
    match = _UNTIL_END_OF_TURN_TAP_LAND_ADDITIONAL_MANA_RE.fullmatch(text.strip())
    if match is None:
        return None
    land = match.group("your_land") or match.group("any_land")
    mana = tuple(Color(letter.upper()) for letter in _MANA_SYMBOL_RE.findall(match.group("mana")))
    if not mana:
        return None
    only_creators_own_taps = match.group("your_land") is not None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=(
                    f"Until end of turn, whenever "
                    f"{'you tap' if only_creators_own_taps else 'a player taps'} "
                    f"{with_indefinite_article(land)} for mana, add an additional "
                    f"{''.join(f'{{{color.value}}}' for color in mana)}."
                ),
                event=TriggerEvent.TAPPED_FOR_MANA,
                controller=controller.username,
                source_id=spell.id,
                source_name=spell.name,
                remaining=None,
                expires_end_of_turn=True,
                effect=AddManaWhenLandTapped(
                    land_subtype=land,
                    mana=mana,
                    only_creators_own_taps=only_creators_own_taps,
                ),
            )
        )

    return effect


#: Wingnut, Bat on the Belfry's own Alliance effect: "Wingnut gains your
#: choice of flying, menace, or haste until end of turn." - the *self*-
#: referential twin of `_RIDER_KEYWORD_CHOICE_RE`'s targeted "`<it>` gains
#: your choice of `<keywords>` until end of turn." (Hungering Puppetbeast):
#: that rider answers an antecedent's own earlier target, where this is the
#: whole (only) sentence of its own triggered ability, self-referential by
#: CR 201.5c's own name - `trigger_effect_for`'s existing fallback already
#: rewrites "Wingnut" to CR 700.7's "this permanent" before trying this
#: parser a second time, the same way it does for every other self-named
#: sentence in the pool, so no card-name handling belongs here at all.
_SELF_KEYWORD_CHOICE_UNTIL_EOT_RE = re.compile(
    r"^this (?:creature|permanent|artifact|planeswalker|land|enchantment) gains? "
    r"your choice of (?P<keywords>[a-z]+(?: [a-z]+)?(?:,\s*[a-z]+(?: [a-z]+)?)*"
    r"(?:,?\s+or\s+[a-z]+(?: [a-z]+)?)?) until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_self_keyword_choice_until_eot_trigger(text: str) -> AbilityEffect | None:
    """`_SELF_KEYWORD_CHOICE_UNTIL_EOT_RE`'s shape - CR 608.2d's choice, asked
    once per resolution, the identical `ContinuousEffect`/`grant_ability`
    shape `_RIDER_KEYWORD_CHOICE_RE`'s own rider already builds for a target
    rather than for the source itself."""
    match = _SELF_KEYWORD_CHOICE_UNTIL_EOT_RE.fullmatch(text.strip())
    if match is None:
        return None
    keywords = _split_choice_keywords(match.group("keywords"))
    if keywords is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        chosen = keywords[0]
        if len(keywords) > 1:
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_QUALITY,
                    player=ability.controller,
                    prompt="choose a keyword",
                    source=ability.source_name,
                    options=tuple(keywords),
                    source_id=source_id_of(ability),
                )
            )
            assert isinstance(answer, str)
            chosen = answer
        effects = game.continuous_effects
        effects.add(
            ContinuousEffect(
                description=f"{ability.source_name}: {source.name} gains {chosen}",
                layer=Layer.ABILITY,
                timestamp=effects.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=only_this_incarnation(source, source.zone_change_stamp),
                modification=grant_ability(chosen),
            )
        )

    return effect


#: "target creature gains your choice of `<A>` or `<B>` until end of turn. If
#: that creature is equipped, it gains `<A>` and `<B>` until end of turn
#: instead." (Eowyn, Lady of Rohan): CR 608.2d's choice is asked at resolution,
#: and only when the target is not equipped (CR 301.5), in which case both
#: keywords are granted without a question.
_TARGET_KEYWORD_CHOICE_UNLESS_EQUIPPED_RE = re.compile(
    r"^target creature gains your choice of (?P<first>[a-z]+(?: [a-z]+)?) or "
    r"(?P<second>[a-z]+(?: [a-z]+)?) until end of turn\. If that creature is equipped, "
    r"it gains (?P<both_first>[a-z]+(?: [a-z]+)?) and (?P<both_second>[a-z]+(?: [a-z]+)?) "
    r"until end of turn instead\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_target_keyword_choice_unless_equipped_trigger(text: str) -> AbilityEffect | None:
    """`_TARGET_KEYWORD_CHOICE_UNLESS_EQUIPPED_RE`'s shape."""
    match = _TARGET_KEYWORD_CHOICE_UNLESS_EQUIPPED_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    first, second = match.group("first").lower(), match.group("second").lower()
    if (match.group("both_first").lower(), match.group("both_second").lower()) != (first, second):
        return None
    keywords = _split_choice_keywords(f"{first} or {second}")
    if keywords is None:
        return None
    from .amounts import _is_equipped

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        store = game.continuous_effects
        board = game.computed_board()
        for target in game.resolve_card_targets(ability):
            if target.zone is not Zone.BATTLEFIELD:
                continue
            granted = list(keywords)
            if not _is_equipped(game, board, target):
                answer = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_A_QUALITY,
                        player=ability.controller,
                        prompt="choose a keyword",
                        source=ability.source_name,
                        options=tuple(keywords),
                        source_id=source_id_of(ability),
                    )
                )
                assert isinstance(answer, str)
                granted = [answer]
            timestamp = store.tick()
            for keyword in granted:
                store.add(
                    ContinuousEffect(
                        description=f"{ability.source_name}: {target.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=only_this_incarnation(target, target.zone_change_stamp),
                        modification=grant_ability(keyword),
                    )
                )

    return effect


#: CR 702.91a's Battle cry effect, written out as plain, unkeyworded text:
#: "each other attacking creature gets +1/+0 until end of turn." (Wingnut,
#: Bat on the Belfry's own attack trigger). `keywords._battle_cry_effect` is
#: keyed to the keyword expansion alone (`TriggeredAbility.keyword ==
#: "battle cry"`), so a card printing the identical effect as ordinary text
#: rather than through the keyword never reached it - a general amount, not
#: hardcoded to "+1/+0", though every printing in the pool uses it, the same
#: generality `_battle_cry_effect`'s own fixed set (CR 611.2c: computed once,
#: at resolution) is built to.
_EACH_OTHER_ATTACKING_CREATURE_PUMP_RE = re.compile(
    r"^each other attacking creature gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) "
    r"until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_each_other_attacking_creature_pump_trigger(text: str) -> AbilityEffect | None:
    """`_EACH_OTHER_ATTACKING_CREATURE_PUMP_RE`'s shape."""
    match = _EACH_OTHER_ATTACKING_CREATURE_PUMP_RE.fullmatch(text.strip())
    if match is None:
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        store = game.continuous_effects
        timestamp = store.tick()
        for creature in game.attacking_creatures():
            if creature.id == source.id:
                continue
            store.add(
                ContinuousEffect(
                    description=(f"{source.name}: {creature.name} gets {power:+}/{toughness:+}"),
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=_only(creature.id),
                    modification=modify_power_toughness(power, toughness),
                )
            )

    return effect


#: "other attacking creatures gain `<keyword(s)>` until end of turn." - Cecil,
#: Redeemed Paladin's own "Protect" attack trigger, the keyword-grant twin of
#: `_EACH_OTHER_ATTACKING_CREATURE_PUMP_RE`'s +N/+N (CR 611.2c, computed once
#: at resolution, the same fixed set every mass grant here uses).
_OTHER_ATTACKING_CREATURES_GRANT_RE = re.compile(
    r"^other attacking creatures gain (?P<keywords>[a-z][a-z ,]*?) until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_other_attacking_creatures_grant_trigger(text: str) -> AbilityEffect | None:
    """`_OTHER_ATTACKING_CREATURES_GRANT_RE`'s shape."""
    match = _OTHER_ATTACKING_CREATURES_GRANT_RE.fullmatch(text.strip())
    if match is None:
        return None
    keywords = _split_and_validate_keywords(match.group("keywords"))
    if keywords is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        store = game.continuous_effects
        timestamp = store.tick()
        for creature in game.attacking_creatures():
            if creature.id == source.id:
                continue
            for keyword in keywords:
                store.add(
                    ContinuousEffect(
                        description=f"{source.name}: {creature.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=_only(creature.id),
                        modification=grant_ability(keyword),
                    )
                )

    return effect


#: "Transform this creature." / "Transform this permanent." - CR 701.27a's
#: self-referential form, the only one the werewolves and their cousins print
#: on the ability that does it. A clause naming some *other* permanent
#: ("transform target creature") needs target resolution this template does not
#: have and is deliberately not matched, the same restriction
#: `_SACRIFICE_UNLESS_PAY_ENERGY_RE` above holds itself to.
_TRANSFORM_SELF_RE = re.compile(
    r"^transform this (?:creature|permanent|artifact|enchantment|planeswalker|land|token)\.?$",
    re.IGNORECASE,
)


#: "Transform all Humans." (Moonmist) - a board sweep rather than the
#: self-reference `_TRANSFORM_SELF_RE` reads. The subtype is a CR 205.3m
#: creature type, written the way Oracle text always writes one: capitalized,
#: and plural because the sentence names a group.
_TRANSFORM_ALL_SUBTYPE_RE = re.compile(
    # Case-sensitive on purpose, unlike almost every other pattern in this
    # file: the capitalized subtype is what tells "Humans" apart from an
    # ordinary English noun, exactly as `_is_bare_subtype_word` reads it. Only
    # the leading verb is allowed either case, since a clause may arrive
    # sentence-initial or mid-paragraph.
    r"^[Tt]ransform all (?P<subtype>[A-Z][a-zA-Z]*(?:-[A-Z][a-zA-Z]*)*)\.?$"
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_transform_all_subtype_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_TRANSFORM_ALL_SUBTYPE_RE`'s shape - Moonmist's "Transform all Humans."

    CR 701.27a: "To transform a permanent, turn it over so that its other face
    is up. Only permanents represented by double-faced tokens and double-faced
    cards can transform." CR 701.27c is what makes the sweep safe to run over a
    whole battlefield: "If a spell or ability instructs a player to transform a
    permanent that isn't represented by a double-faced token or a double-faced
    card, nothing happens" - a single-faced Human is a silent no-op, not an
    error, and `CardState.transform` already enforces that itself (together
    with CR 712.10's instant-or-sorcery back face).

    The membership test is the permanent's *computed* subtypes
    (`CardState.subtypes`, CR 205.3 read off the up face per CR 712.8d), so a
    permanent showing a back face is judged by the face it is showing. Which
    matters here in particular: CR 701.27b says transforming "uses the same
    physical action as turning a permanent face up or face down" but is a
    different game action, and the set of permanents to turn over is settled
    before any of them is turned - otherwise a Human whose back face is also a
    Human would be turned over twice by one instruction.

    Every permanent on the battlefield is swept, not only the caster's: "all
    Humans" names no controller (CR 109.5's "you" is absent).
    """
    match = _TRANSFORM_ALL_SUBTYPE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    subtype = _singular_subtype_for_transform_all(match.group("subtype"))
    if subtype is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        turning = computed_permanents(
            game, game.battlefield, lambda chars: subtype in chars.subtypes
        )
        for state in turning:
            state.transform()

    return effect


@ABILITY_TEXT.rung("s25")
def _parse_transform_clause(text: str) -> AbilityEffect | None:
    """CR 701.27a: "To transform a permanent, turn it over so that its other
    face is up", read off the ability's own printed text.

    Duskwatch Recruiter's "At the beginning of each upkeep, if no spells were
    cast last turn, transform this creature." and Krallenhorde Howler's mirror
    on the back face both reach this, with no per-card row: the CR 603.4
    intervening *if* is checked by `machines/triggers.py` before the ability
    ever triggers, so all this clause has to do is the turning over.

    CR 712.9 limits transforming to a permanent represented by a double-faced
    card or token, and `CardState.transform` enforces that itself - a
    single-faced permanent told to transform does nothing (CR 701.28c's
    wording for the sibling action). The source having left the battlefield is
    the other no-op: CR 701.27a turns a *permanent* over.
    """
    if _TRANSFORM_SELF_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        transform_permanent(game, source)

    return effect


#: "[Ability word — ]As this `<noun>` transforms into `<face>`, `<effect>`"
#: (Sephiroth, One-Winged Angel's Super Nova). CR 712.20: "If a double-faced
#: card would have an 'As [this permanent] transforms . . .' ability after it
#: transforms or converts, that ability is applied while that permanent is
#: transforming or converting, not afterward."
_AS_TRANSFORMS_INTO_RE = re.compile(
    r"^(?:[^—]+—\s*)?as this [a-z]+ transforms into (?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)


#: "choose an opponent." / "choose a player." after "As this creature
#: transforms into <face>, " (Shinryu, Transcendent Rival) - CR 712.20 applies
#: it while the permanent turns over, recorded on `CardState.chosen_player`
#: for the face's "the chosen player".
_AS_TRANSFORMS_CHOOSE_PLAYER_RE = re.compile(
    r"^choose (?P<who>an opponent|a player)\.?$", re.IGNORECASE
)


def _choose_player_as_it_transforms(game: "Game", permanent: CardState, instruction: str) -> None:
    """The controller chooses an opponent (or any player) for the permanent's
    `chosen_player`; asked only when there is more than one to pick between."""
    match = _AS_TRANSFORMS_CHOOSE_PLAYER_RE.fullmatch(instruction.strip())
    if match is None:
        return
    controller = game.controller_of(permanent).username
    any_player = match.group("who").lower() == "a player"
    candidates = tuple(
        player.username
        for player in game.players_in_game
        if any_player or player.username != controller
    )
    if not candidates:
        return
    chosen = candidates[0]
    if len(candidates) > 1:
        quality = "player" if any_player else "opponent"
        answer = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=controller,
                prompt=f"choose {with_indefinite_article(quality)} as {permanent.name} transforms",
                source=permanent.name,
                source_id=source_id_of(permanent),
                options=candidates,
                quality=quality,
            )
        )
        if answer not in candidates:
            raise ValueError(f"{permanent.name}: {answer!r} is not one of {', '.join(candidates)}")
        chosen = str(answer)
    permanent.chosen_player = chosen


def transform_permanent(game: "Game", permanent: CardState, *, day_night: bool = False) -> None:
    """CR 701.27a's transform, then the new face's own "As this ...
    transforms into `<face>`, `<effect>`" (CR 712.20) for the permanent's
    controller. An "as transforms" effect this cannot read records an
    `UnmodeledTriggerEffectNotice` rather than being skipped silently.

    `day_night` is passed only by daybound/nightbound's own transform - see
    `CardState.transform`."""
    before = permanent.up_face_name
    permanent.transform(day_night=day_night)
    after = permanent.up_face_name
    if after == before:
        return  # CR 712.9: nothing happened
    controller = game.controller_of(permanent)
    for ability in parse_abilities(permanent.card):
        if ability.kind is not AbilityKind.STATIC or getattr(ability, "face", None) != after:
            continue
        match = _AS_TRANSFORMS_INTO_RE.fullmatch((ability.text or "").strip())
        # The face's own name may hold a comma ("Sephiroth, One-Winged
        # Angel"), so it is matched as the name, not up to the first comma.
        # Shinryu, Transcendent Rival's own "As this creature transforms into
        # Shinryu, ..." names the face by its shortened name (CR 201.5c).
        rest = match.group("rest") if match is not None else ""
        lead = next(
            (
                f"{name}, "
                for name in (after, after.split(",")[0])
                if rest.lower().startswith(f"{name}, ".lower())
            ),
            None,
        )
        if lead is None:
            continue
        instruction = rest[len(lead) :]
        if _AS_TRANSFORMS_CHOOSE_PLAYER_RE.fullmatch(instruction.strip()):
            _choose_player_as_it_transforms(game, permanent, instruction)
            continue
        run = _player_instruction(instruction)
        if run is None:
            game.unmodeled_trigger_effect_notices.append(
                UnmodeledTriggerEffectNotice(
                    source_id=permanent.id, source_name=permanent.name, text=ability.text
                )
            )
            continue
        run(game, controller, permanent.name, str(permanent.id))
    # CR 701.27e: "When this creature transforms into `<face>`, ..." (Avacyn,
    # the Purifier) triggers now that it has turned over.
    from ..triggers import GameEvent

    game.emit(
        GameEvent(
            event=TriggerEvent.TRANSFORMS,
            subject_id=permanent.id,
            subject_name=permanent.name,
            subject_controller=permanent.controller,
            subject_card=permanent.card,
            player=permanent.controller,
        )
    )


# --------------------------------------------------------------------------
# "You may transform <this>. If you do, <payoff>."
# --------------------------------------------------------------------------
#
# Aang, Master of Elements: "At the beginning of each upkeep, you may transform
# Aang, Master of Elements. If you do, you gain 4 life, draw four cards, put
# four +1/+1 counters on him, and he deals 4 damage to each opponent." Soul
# Seizer: "When this creature deals combat damage to a player, you may
# transform it. If you do, attach it to target creature that player controls."
#
# One instruction (CR 608.2c): the optional transform (CR 603.5's "may",
# chosen as the ability resolves) and a payoff that happens only if the
# permanent actually turned over. CR 701.27f: "If an activated or triggered
# ability of a permanent ... tries to transform it, the permanent does so only
# if it hasn't transformed or converted since the ability was put onto the
# stack" - read off `AbilityOnStack.source_times_transformed`. CR 608.2d: "The
# player can't choose an option that's illegal or impossible", so when the
# transform cannot happen (the source is gone or is a new object, CR 400.7;
# it has transformed since, CR 701.27f; it has no face to turn to, CR 701.27c
# and 701.27d) nothing is asked and nothing follows.

#: The self is "this <noun>", "it", or the source's own printed name (CR
#: 201.5, checked against the live source at resolution). The payoff is
#: anything `_optional_transform_payoff` can read.
_MAY_TRANSFORM_SELF_IF_YOU_DO_RE = re.compile(
    r"^[Yy]ou may transform (?P<self>this (?:creature|permanent|artifact|enchantment|land)|it|"
    r"[A-Z][^.]*?)\.\s*[Ii]f you do,\s*(?P<payoff>.+?)\.?$",
    re.DOTALL,
)

#: A legend's own object pronoun after a preposition - "put four +1/+1 counters
#: on him" - and its own subject pronoun opening an instruction - "he deals 4
#: damage". Oracle text uses "he"/"she"/"him"/"her" only for the legendary
#: character the card is (the same convention
#: `abilities.legendary_self_pronoun_normalized` reads), so each is CR 700.7's
#: "this permanent".
_SELF_OBJECT_PRONOUN_RE = re.compile(r"\b(?P<prep>on|to|from|with|at) (?:him|her)\b", re.IGNORECASE)
_SELF_SUBJECT_PRONOUN_RE = re.compile(r"^(?:he|she) (?=\w)", re.IGNORECASE)

#: A serial list of instructions, "A, B, C, and D" (or "then D"): the commas
#: between whole instructions, the last one carrying the conjunction.
_SERIAL_INSTRUCTION_SEPARATOR_RE = re.compile(r",\s*(?:and\s+|then\s+)?", re.IGNORECASE)

#: "attach it to target <description>" / "attach this Aura to target ..." -
#: CR 701.3a's attach of the ability's own source onto its announced target.
#: Bounded to this one sentence (`[^.]*$`, never `.+$`) - a `.` matches any
#: non-newline character, so a greedier tail used to read straight through
#: this sentence's own trailing period and swallow every sibling sentence
#: after it (Hidden Blade's own "If that creature is an Assassin, it gains
#: deathtouch until end of turn.") as though it were still part of "target
#: `<description>`", with nothing left to notice the words it never ran.
_ATTACH_SELF_TO_TARGET_RE = re.compile(
    r"^attach (?:it|this (?:aura|equipment|fortification|permanent)) "
    r"to (?:up to one )?target\b[^.]*$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s8")
def _parse_unattach_attached_clause(text: str) -> AbilityEffect | None:
    """ "Unattach enchanted Equipment." - Carry Away. Read by
    `machines/unattach.parse_unattach_attached_clause`."""
    from ..unattach import parse_unattach_attached_clause

    return parse_unattach_attached_clause(text)


@ABILITY_TEXT.rung("s8")
def _parse_then_if_subtype_unattach_clause(text: str) -> AbilityEffect | None:
    """ "Tap enchanted permanent. If it's an Equipment, unattach it." -
    Tamiyo's Compleation. Read by
    `machines/unattach.parse_then_if_subtype_unattach_clause`."""
    from ..unattach import parse_then_if_subtype_unattach_clause

    return parse_then_if_subtype_unattach_clause(text)


def attach_permanent(game: "Game", attached: CardState, host: CardState) -> bool:
    """CR 701.3a's attach, with CR 701.3b's refusals: an object that is not
    an Aura, Equipment or Fortification is not moved, nor is one onto a host
    it could not enchant (CR 702.5a), equip (CR 301.5) or fortify, nor onto a
    host with protection from it (CR 702.16c, CR 702.16d). Attaching to what
    it is already attached to does nothing. True when it moved."""
    from ..keywords import _protection_refusal_for_attachment, why_cannot_enchant

    if host.zone is not Zone.BATTLEFIELD or attached.zone is not Zone.BATTLEFIELD:
        return False
    subtypes = set(game.characteristics_of(attached).subtypes)
    host_characteristics = game.characteristics_of(host)
    if attached.attached_to == host.id:
        return False
    if "Aura" in subtypes:
        controller = game.controller_of(attached).username
        if why_cannot_enchant(attached, host, controller, game) is not None:
            return False
    elif "Equipment" in subtypes:
        if not host_characteristics.is_creature:
            return False
    elif "Fortification" in subtypes:
        if Type.LAND not in host_characteristics.types:
            return False
    else:
        return False
    if _protection_refusal_for_attachment(game, attached, host) is not None:
        return False
    attached.attach_to(host)
    return True


def _attach_self_to_announced_target(game: "Game", ability: AbilityOnStack) -> CardState | None:
    """CR 701.3a: the ability's source attached to whichever of its own
    announced targets accepts it (CR 603.3d), rechecked by `Game.
    resolve_targets` (CR 608.2b) - the primitive `_attach_self_to_target_
    effect` and its own conditional-rider sibling
    (`_parse_attach_self_then_conditional_rider_clause`) both build on, so
    the second knows exactly which object the first attached to rather than
    re-resolving (and possibly re-choosing among) the targets a second time.
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD:
        return None
    for target in game.resolve_targets(ability):
        if isinstance(target, CardState) and attach_permanent(game, source, target):
            return target
    return None


@ABILITY_TEXT.rung("s20")
def _parse_attach_may_then_rider_clause(text: str) -> AbilityEffect | None:
    """ "You may attach it to target creature you control. If you do, that
    creature gains first strike until end of turn and must be blocked this turn
    if able." (`ep02_r1_controller_recipients.attach_may_then_rider_effect`)."""
    if "if you do" not in text.lower() or "attach" not in text.lower():
        return None
    return attach_may_then_rider_effect(text)


@ABILITY_TEXT.rung("s20")
def _attach_self_to_target_effect(text: str) -> AbilityEffect | None:
    """`_ATTACH_SELF_TO_TARGET_RE`: the source attached to the target the
    ability announced (CR 603.3d), rechecked by `Game.resolve_targets` (CR
    608.2b)."""
    if _ATTACH_SELF_TO_TARGET_RE.fullmatch(" ".join(text.strip().rstrip(".").split())) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        _attach_self_to_announced_target(game, ability)

    return effect


#: "attach it to target <description>. If that `<noun>` is a/an `<quality>`,
#: it `<effect>`." - Hidden Blade's own "attach it to target creature you
#: control. If that creature is an Assassin, it gains deathtouch until end
#: of turn." CR 608.2c: two instructions in the order written - the attach,
#: then a rider whose own condition is a characteristic of the object just
#: attached to (CR 613.5's computed board), not a board-state clause about
#: the ability's own source the way every other reader of `Game.condition_
#: holds` in this file asks it. `<quality>` is any subtype, card type, or
#: other quality `_is_quality` (`machines/conditions/objects.py`) already
#: reads generically - never hand-fitted to "Assassin" - and `<effect>` is
#: read by `_parse_referent_object_clause`, the same dispatcher every other
#: "it `<verb>`..." rider in this file already goes through.
_ATTACH_SELF_THEN_CONDITIONAL_RIDER_RE = re.compile(
    r"^(?P<attach>attach (?:it|this (?:aura|equipment|fortification|permanent)) to target"
    r"[^.]*)\.\s*if (?P<subject>that (?:creature|permanent|artifact|enchantment|land"
    r"|planeswalker|vehicle)|this (?:creature|permanent|artifact|enchantment|land"
    r"|planeswalker|vehicle))\s+(?P<condition>(?:is|are|was|were)\b.+?),\s*(?P<rider>.+)$",
    re.IGNORECASE | re.DOTALL,
)


#: "Attach it to target <description>. When you do, <consequence>." - Novel
#: Nunchaku's enters trigger. CR 603.12: the second sentence is a reflexive
#: trigger, so it exists only if the attach actually happened and chooses its
#: own targets as it goes on the stack (CR 603.3d), which is why
#: `targeting.profile_for_text` already stops at "when you do".
_ATTACH_SELF_THEN_WHEN_YOU_DO_RE = re.compile(
    r"^(?P<attach>attach (?:it|this (?:aura|equipment|fortification|permanent)) to target\b[^.]*)\."
    r"\s*when you do,\s*(?P<consequence>[^.]+)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_attach_self_then_when_you_do_clause(text: str) -> AbilityEffect | None:
    """`_ATTACH_SELF_THEN_WHEN_YOU_DO_RE`'s shape, or `None`. Read only when
    the reflexive consequence is itself readable, so the pair is never half
    run."""
    match = _ATTACH_SELF_THEN_WHEN_YOU_DO_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    consequence_text = _as_capitalized_sentence(match.group("consequence"))
    if reflexive_consequence_effect(consequence_text) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if _attach_self_to_announced_target(game, ability) is None:
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=game.controller_of(ability).username,
            source_id=ability.source_id,
            source_name=ability.source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


def _parse_attach_self_then_conditional_rider_clause(text: str) -> AbilityEffect | None:
    """`_ATTACH_SELF_THEN_CONDITIONAL_RIDER_RE`'s shape, or `None`."""
    match = _ATTACH_SELF_THEN_CONDITIONAL_RIDER_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    condition_text = f"it {match.group('condition').strip()}"
    rider_text = match.group("rider").strip().rstrip(".") + "."
    inner = _parse_referent_object_clause(rider_text)
    if inner is None:
        return None
    remainder_text = (
        f"If {match.group('subject')} {match.group('condition')}, {match.group('rider')}"
    )

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        # CR 608.2b: the target is the one this ability already announced
        # (CR 603.3d), and it stays "that creature" for the rider below even
        # when the attach itself cannot happen - Hidden Blade destroyed in
        # response to its own ETB trigger, before the trigger resolves,
        # still leaves a legal target creature for "If that creature is an
        # Assassin, it gains deathtouch" to check (CR 608.2c: the attach
        # failing is not the same as the target becoming illegal). Resolving
        # the target here, rather than only through `_attach_self_to_
        # announced_target`'s own loop (which returns `None` outright once
        # `ability.source(game)` is gone), is what keeps the two questions -
        # "is there still a legal target" and "did the attach happen" -
        # separate instead of collapsing the second into the first.
        target = next((t for t in game.resolve_targets(ability) if isinstance(t, CardState)), None)
        if target is None:
            return
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            attach_permanent(game, source, target)
        controller = game.controller_of(ability).username
        holds = game.condition_holds(controller, condition_text, target)
        if holds is None:
            # Unreadable condition: fail closed exactly as an ordinary
            # unreadable remainder always has - the attach still ran, and the
            # untried rider is recorded rather than guessed at.
            game.layer_remainder_notices.append(
                LayerRemainderNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=remainder_text,
                )
            )
            return
        if holds:
            inner(game, [target], ability)

    from .. import conditions

    if conditions.claims(condition_text):
        return effect
    return _with_unparsed_remainder(effect, remainder_text)


def _optional_transform_payoff(payoff: str) -> AbilityEffect | None:
    """The "If you do" half, read three ways in turn: an attach of the source
    to its target; the payoff as one sentence `parse_mixed_effect` reads; or a
    serial list of instructions ("A, B, C, and D"), each read as its own
    sentence and run in the order written (CR 608.2c) - read only when every
    one of them is, so a list is never half-run. A legend's own pronouns are
    "this permanent" first."""
    text = _SELF_OBJECT_PRONOUN_RE.sub(lambda m: f"{m.group('prep')} this permanent", payoff)
    attach = _attach_self_to_target_effect(text)
    if attach is not None:
        return attach
    whole = parse_mixed_effect(
        _as_capitalized_sentence(_SELF_SUBJECT_PRONOUN_RE.sub("this permanent ", text))
    )
    if whole is not None:
        return whole
    pieces = [piece.strip() for piece in _SERIAL_INSTRUCTION_SEPARATOR_RE.split(text)]
    if len(pieces) < 2 or not all(pieces):
        return None
    sentences = [
        _as_capitalized_sentence(_SELF_SUBJECT_PRONOUN_RE.sub("this permanent ", p)) for p in pieces
    ]
    if any(parse_mixed_effect(sentence) is None for sentence in sentences):
        return None
    return parse_mixed_effect(" ".join(sentences))


@ABILITY_TEXT.rung("s9")
def _parse_may_transform_self_if_you_do_clause(text: str) -> AbilityEffect | None:
    """`_MAY_TRANSFORM_SELF_IF_YOU_DO_RE`'s shape - see the section note."""
    match = _MAY_TRANSFORM_SELF_IF_YOU_DO_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).strip().split())
    )
    if match is None:
        return None
    named = match.group("self").strip()
    by_name = not (named.lower() == "it" or named.lower().startswith("this "))
    payoff = _optional_transform_payoff(match.group("payoff"))
    if payoff is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if ability.source_stamp is not None and source.zone_change_stamp != ability.source_stamp:
            return  # CR 400.7: a new object, not the one this ability is about
        if by_name and named.lower() not in (source.name or "").lower():
            return  # CR 201.5: the name means this object, and this is not it
        if (
            ability.source_times_transformed is not None
            and source.times_transformed != ability.source_times_transformed
        ):
            return  # CR 701.27f
        target_face = source.face_it_would_transform_into
        if target_face is None or {Type.INSTANT, Type.SORCERY} & set(
            types_of(target_face.type_line or "")
        ):
            return  # CR 701.27c, CR 701.27d: nothing would happen
        if not game.may(
            game.controller_of(ability),
            f"transform {source.name}",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        before = source.times_transformed
        transform_permanent(game, source)
        if source.times_transformed == before:
            return
        payoff(game, ability)

    return effect


def reads_as_transforms_line(text: str) -> bool:
    """Whether `text` is an "As this ... transforms into `<face>`, `<effect>`"
    line whose effect `transform_permanent` can carry out, whatever the face's
    name (which may itself hold a comma)."""
    match = _AS_TRANSFORMS_INTO_RE.fullmatch(text.strip())
    if match is None:
        return False
    rest = match.group("rest")
    return any(
        _AS_TRANSFORMS_CHOOSE_PLAYER_RE.fullmatch(rest[index + 2 :].strip()) is not None
        or _player_instruction(rest[index + 2 :]) is not None
        for index in range(len(rest))
        if rest.startswith(", ", index)
    )


def _player_instruction(text: str) -> ClauseEffect | None:
    """One instruction for a player, read whole ("you get an emblem with
    ...", whose quoted text the clause splitter would cut) or as a plain
    player clause."""
    stripped = text.strip()
    emblem = _GET_AN_EMBLEM_RE.fullmatch(stripped)
    if emblem is not None:
        quoted = emblem.group("text")
        return lambda game, player, source, _source_id: _get_emblem(game, player, quoted, source)
    if _ATTACH_TO_A_PLAYER_RE.fullmatch(stripped) is not None:
        return _attach_permanent_to_a_player
    return parse_clause_effect(stripped)


#: "attach it to a player." - Curse of Leeches // Leeching Lurker's "As this
#: permanent transforms into Curse of Leeches, ..." (CR 712.20).
_ATTACH_TO_A_PLAYER_RE = re.compile(r"^attach (?:it|this permanent) to a player\.?$", re.IGNORECASE)


def _attach_permanent_to_a_player(
    game: "Game", player: Player, source: str, source_id: str | None
) -> None:
    """CR 303.4d: the Aura's controller chooses which player it enchants."""
    permanent = next((state for state in game.battlefield if str(state.id) == source_id), None)
    if permanent is None:
        return
    candidates = tuple(candidate.username for candidate in game.players_in_game)
    (chosen,) = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_PLAYERS,
            player=player.username,
            prompt=f"choose a player to attach {source} to",
            source=source,
            source_id=source_id,
            amount=1,
            players=candidates,
            exact=True,
        )
    )
    permanent.attach_to(chosen)


def _get_emblem(game: "Game", player: Player, text: str, source: str) -> None:
    game.create_emblem(player.username, text, source)


#: "you may `<instruction>`. If you do, `<animation>`." - Wall of
#: Resurgence's, Noyan Dar, Roil Shaper's and Cyclone Sire's "you may put three
#: +1/+1 counters on target land you control. If you do, that land becomes a
#: 0/0 Elemental creature with haste that's still a land." The consequence is
#: a continuous effect (`machines/layers.py`'s animation shape, read through
#: `is_genuine_resolution_layer_sentence`), which no player-clause "if you do"
#: merger can run; the instruction is any clause `parse_mixed_effect` reads.
_MAY_THEN_IF_YOU_DO_LAYER_RE = re.compile(
    r"^you may (?P<action>.+?)\.\s*if you do, (?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s22")
def _parse_may_then_if_you_do_layer_clause(text: str) -> AbilityEffect | None:
    """`_MAY_THEN_IF_YOU_DO_LAYER_RE`'s shape.

    CR 608.2d: the "you may" is the controller's choice as the ability
    resolves; "if you do" (CR 608.2c) runs the continuous effect only when
    that choice was yes. The consequence names the earlier instruction's
    target by anaphora ("that land"), so it applies to the ability's own
    targets (CR 608.2b rechecks them) - and, CR 113.7a, whether or not the
    ability's source is still on the battlefield.
    """
    match = _MAY_THEN_IF_YOU_DO_LAYER_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    consequence = match.group("consequence").strip()
    if not is_genuine_resolution_layer_sentence(consequence):
        return None
    action_text = match.group("action").strip()
    action = parse_mixed_effect(action_text[0].upper() + action_text[1:] + ".")
    if action is None:
        return None
    consequence_sentence = consequence[0].upper() + consequence[1:] + "."

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if not game.may(
            game.controller_of(ability),
            action_text,
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        action(game, ability)
        targets = game.resolve_card_targets(ability)
        if source is None or not targets:
            return
        continuous_effects(game).create(
            source,
            targets=targets,
            context=layer_context_for(game, game.controller_of(ability)),
            ability_text=consequence_sentence,
            game=game,
        )

    return effect


#: "You get an emblem with "`<ability>`." `<more instructions>`" - CR 114.2's
#: emblem followed by further text in the same ability: Nissa, Who Shakes the
#: World's -8 ("... Search your library for any number of Forest cards, put
#: them onto the battlefield tapped, then shuffle.") and Kiora, Master of the
#: Depths' -8 ("... Then create three 8/8 blue Octopus creature tokens."). The
#: quoted ability ends in its own full stop *inside* the closing quote, so the
#: clause splitter never sees a sentence boundary there and the whole
#: paragraph reached `_GET_AN_EMBLEM_RE` as one quote; this reads the quote
#: off the front and hands the rest to the ordinary dispatch, in printed order
#: (CR 608.2c).
_GET_AN_EMBLEM_THEN_RE = re.compile(
    r"""^(?P<who>you|they) gets? an emblem with ["“](?P<text>[^"”]+)["”]\.?\s+(?P<rest>\S.*)$""",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s22")
def _parse_get_an_emblem_then_clause(text: str) -> AbilityEffect | None:
    """`_GET_AN_EMBLEM_THEN_RE`'s shape: the emblem, then everything after it
    read by `_ability_effect_or_notice` - or `None` when that remainder does
    not read, so the paragraph is never half-run (CR 608.2c)."""
    match = _GET_AN_EMBLEM_THEN_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    quoted = match.group("text")
    rest = _LEADING_THEN_WORD_RE.sub("", match.group("rest").strip())
    rest = rest[0].upper() + rest[1:]
    remainder = _ability_effect_or_notice(rest)
    if remainder is None or getattr(remainder, "__name__", "").endswith("_notice_only"):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        _get_emblem(game, game.controller_of(ability), quoted, ability.source_name)
        remainder(game, ability)

    return effect


#: A leading "Then " on the instruction that follows an emblem (Kiora,
#: Master of the Depths) - sequencing only (CR 608.2c).
_LEADING_THEN_WORD_RE = re.compile(r"^then,?\s+", re.IGNORECASE)


@ABILITY_TEXT.rung("s22")
def _parse_get_an_emblem_clause(text: str) -> AbilityEffect | None:
    """Jaya Ballard's -8, read whole (the quoted abilities contain full stops
    the clause splitter would cut at)."""
    match = _GET_AN_EMBLEM_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    quoted = match.group("text")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        _get_emblem(game, game.controller_of(ability), quoted, ability.source_name)

    return effect


#: "Until your next turn, whenever a creature attacks you or a planeswalker
#: you control, it gets `<power>`/`<toughness>` until end of turn." - Jace,
#: Reality Sculptor's own `-3` and Tamiyo Meets the Story Circle's chapter I
#: (off-set: the identical sentence, "-2/-0" in place of "-5/-0", on a Saga
#: chapter rather than a loyalty ability - proof this is CR 603.7's delayed
#: trigger mechanism, not something specific to a planeswalker's own cost).
#: CR 508.3d/CR 306.6's compound defender ("you" the player, or a
#: planeswalker you control) is `DelayedTrigger.defending_controller_only`,
#: read off `GameEvent.defender_controller` at match time - see that field's
#: own docstring in `machines/triggers.py` for why it has to be resolved at
#: emission rather than here.
_UNTIL_YOUR_NEXT_TURN_ATTACK_PUMP_RE = re.compile(
    r"^until your next turn, whenever a creature attacks you or a planeswalker "
    r"you control, it gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s14")
def _parse_until_your_next_turn_attack_pump_clause(text: str) -> AbilityEffect | None:
    """`_UNTIL_YOUR_NEXT_TURN_ATTACK_PUMP_RE`'s shape.

    A delayed triggered ability (CR 603.7) with two independent durations at
    once: the *watch* itself lasts until the creating ability's own
    controller's next turn (CR 603.7b's own "stated duration",
    `expires_end_of_next_turn`), firing on every matching attack until then
    (`remaining=None`); each pump it grants, once fired, lasts only until the
    ordinary end of that turn (`PumpEventSubject`'s own `Duration.UNTIL_
    END_OF_TURN`) - the same two-tier duration the card's own printed text
    describes ("that turn" bounding when the ability can still trigger, not
    how long any one firing's own effect lasts).
    """
    whole = " ".join(text.strip().split())
    match = _UNTIL_YOUR_NEXT_TURN_ATTACK_PUMP_RE.fullmatch(whole)
    if match is None:
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        game.create_delayed_trigger(
            DelayedTrigger(
                text=whole,
                event=TriggerEvent.ATTACKS,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name=ability.source_name,
                remaining=None,
                expires_end_of_next_turn=True,
                defending_controller_only=True,
                effect=PumpEventSubject(power=power, toughness=toughness),
            )
        )

    return effect


#: "Whenever a creature you control attacks alone this turn, put `<n>`
#: `<kind>` counter(s) on it. It gains `<keywords>` until end of turn." - The
#: Last Ronin's own Saga chapter III (CR 714.4): a delayed trigger created as
#: that chapter's own effect, the identical "watch this turn, act on
#: whichever creature the event actually names" shape `_UNTIL_YOUR_NEXT_
#: TURN_ATTACK_PUMP_RE` already reads for Jace, Reality Sculptor's own `-3`,
#: with `attacking_alone_only` (CR 506.5) in place of `defending_controller_
#: only`, `remaining=None`/`expires_end_of_turn=True` for the shorter "this
#: turn" watch (CR 603.7b, Dalkovan Encampment's own "whenever you attack
#: this turn" already uses the identical pair), and `CountersAndKeywords
#: EventSubject`'s permanent counter plus temporary keyword grant in place
#: of `PumpEventSubject`'s own single power/toughness change.
_ATTACKS_ALONE_THIS_TURN_COUNTERS_AND_KEYWORDS_RE = re.compile(
    r"^whenever a creature you control attacks alone this turn, "
    rf"put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on it\. "
    r"it gains (?P<keywords>[^.]+) until end of turn\.?$",
    re.IGNORECASE,
)

#: "Until your next turn, whenever one or more creatures attack one of your
#: opponents, those creatures get `<power>`/`<toughness>`[ and gain
#: `<keywords>`] until end of turn." - Garruk, Curse Breaker's own `-4`. The
#: group-attack twin of `_UNTIL_YOUR_NEXT_TURN_ATTACK_PUMP_RE` just above:
#: CR 603.2c's "one or more `<description>` attack" (`machines/triggers.
#: is_batched_attack_condition`) in place of that shape's singular "a
#: creature attacks", and `DelayedTrigger.defending_opponent_only` - the
#: opposite half of `defending_controller_only`'s own compound defender -
#: in place of "you or a planeswalker you control". Built as a per-creature
#: watch (`PumpEventSubject`, one `ATTACKS` firing per attacker CR 508.3c
#: already gives), not the printed-ability `batched_attackers` count path
#: `_parse_batched_attack_group_pump_clause` reads: a delayed trigger has no
#: printed condition text of its own to hand that reader, only the fixed
#: fields `DelayedTrigger.matches` already checks.
_UNTIL_YOUR_NEXT_TURN_GROUP_ATTACK_PUMP_RE = re.compile(
    r"^until your next turn, whenever one or more creatures attack one of your opponents, "
    r"those creatures get (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)"
    r"(?:\s+and\s+gains?\s+(?P<keywords>[a-z][a-z ,]*?))?"
    r"\s+until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s14")
def _parse_attacks_alone_this_turn_counters_and_keywords_clause(
    text: str,
) -> AbilityEffect | None:
    """`_ATTACKS_ALONE_THIS_TURN_COUNTERS_AND_KEYWORDS_RE`'s shape."""
    whole = " ".join(text.strip().split())
    match = _ATTACKS_ALONE_THIS_TURN_COUNTERS_AND_KEYWORDS_RE.fullmatch(whole)
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))
    keywords = split_and_validate_keywords(match.group("keywords"))
    if keywords is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        game.create_delayed_trigger(
            DelayedTrigger(
                text=whole,
                event=TriggerEvent.ATTACKS,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name=ability.source_name,
                remaining=None,
                expires_end_of_turn=True,
                attacking_alone_only=True,
                effect=CountersAndKeywordsEventSubject(
                    counter_kind=kind, counter_amount=amount, keywords=tuple(keywords)
                ),
            )
        )

    return effect


@ABILITY_TEXT.rung("s14")
def _parse_until_your_next_turn_group_attack_pump_clause(text: str) -> AbilityEffect | None:
    """`_UNTIL_YOUR_NEXT_TURN_GROUP_ATTACK_PUMP_RE`'s shape - see the banner
    above. The same two-tier duration split (CR 603.7b's stated-duration
    delayed watch, each firing's own separate CR 611.2a "until end of turn")
    `_parse_until_your_next_turn_attack_pump_clause` already uses."""
    whole = " ".join(text.strip().split())
    match = _UNTIL_YOUR_NEXT_TURN_GROUP_ATTACK_PUMP_RE.fullmatch(whole)
    if match is None:
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))
    keyword_text = match.group("keywords")
    keywords: tuple[str, ...] = ()
    if keyword_text is not None:
        validated = _split_and_validate_keywords(keyword_text.strip())
        if validated is None:
            return None
        keywords = tuple(validated)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        game.create_delayed_trigger(
            DelayedTrigger(
                text=whole,
                event=TriggerEvent.ATTACKS,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name=ability.source_name,
                remaining=None,
                expires_end_of_next_turn=True,
                defending_opponent_only=True,
                effect=PumpEventSubject(power=power, toughness=toughness, keywords=keywords),
            )
        )

    return effect


#: "those creatures get `<P>`/`<T>`[ and gain `<keywords>`] until end of
#: turn." / "those creatures gain `<keywords>` until end of turn." - CR 400.7
#: anaphora back to whichever attackers a "one or more `<description>`
#: attack[ `<defender>`]" condition just counted
#: (`machines/triggers.batched_attackers`) - Frenzied Gorespawn's own "...
#: gain menace ..." (no P/T change at all) and The Earth King family's
#: shared "... get +N/+N ..." shape. No "target" word anywhere in the
#: sentence, so `parse_mixed_effect`'s per-clause dispatcher has nothing to
#: split it on - read off the whole, unsplit effect text instead, the same
#: tier `_parse_until_your_next_turn_attack_pump_clause` above already
#: occupies for the identical family's delayed-trigger cousin.
_BATCHED_ATTACK_GROUP_PUMP_RE = re.compile(
    r"^those creatures"
    r"(?:\s+get\s+(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+))?"
    r"(?:\s+and)?(?:\s+gains?\s+(?P<keywords>[a-z][a-z ,]*?))?"
    r"\s+until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s14")
def _parse_batched_attack_group_pump_clause(text: str) -> AbilityEffect | None:
    """`_BATCHED_ATTACK_GROUP_PUMP_RE`'s shape.

    Reads `ability.ability.condition` - the ability's own printed "one or
    more ... attack ..." condition, not this clause's own `text` - through
    `batched_attackers` at resolution time (CR 611.2c fixes membership then,
    not when the ability triggered), the same "count taken once, when the
    effect applies" discipline every other "for each"/"that many" reader in
    this file already holds to. `None` batch (an unreadable condition, or a
    condition this is not even attached to) or an empty one is not an error -
    CR 107.1a: nothing to grant.
    """
    match = _BATCHED_ATTACK_GROUP_PUMP_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    power = int(match.group("power")) if match.group("power") else 0
    toughness = int(match.group("toughness")) if match.group("toughness") else 0
    keyword_text = match.group("keywords")
    keywords: list[str] = []
    if keyword_text is not None:
        validated = _split_and_validate_keywords(keyword_text.strip())
        if validated is None:
            return None
        keywords = validated
    if power == 0 and toughness == 0 and not keywords:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if not isinstance(ability.ability, TriggeredAbility):
            return
        batch = batched_attackers(game, ability.ability.condition, ability.controller)
        if not batch:
            return
        store = continuous_effects(game)
        for creature in batch:
            selector = only_this_incarnation(creature, creature.zone_change_stamp)
            if power != 0 or toughness != 0:
                store.add(
                    ContinuousEffect(
                        description=(
                            f"{ability.source_name}: {creature.name} gets "
                            f"{power:+d}/{toughness:+d} until end of turn"
                        ),
                        layer=Layer.POWER_TOUGHNESS,
                        sublayer=Sublayer.MODIFY,
                        timestamp=store.tick(),
                        duration=Duration.UNTIL_END_OF_TURN,
                        source_id=ability.source_id,
                        selector=selector,
                        modification=modify_power_toughness(power, toughness),
                    )
                )
            for keyword in keywords:
                store.add(
                    ContinuousEffect(
                        description=(
                            f"{ability.source_name}: {creature.name} gains "
                            f"{keyword} until end of turn"
                        ),
                        layer=Layer.ABILITY,
                        timestamp=store.tick(),
                        duration=Duration.UNTIL_END_OF_TURN,
                        source_id=ability.source_id,
                        selector=selector,
                        modification=grant_ability(keyword),
                    )
                )

    return effect


#: Who an attack trigger's own bare "it" names (CR 400.7): the ability's own
#: source (CR 700.7's plain self-reference) - Eagle of the Great Shelf's
#: "Whenever this creature attacks, it gets ..." - unless the printed
#: condition instead reads "equipped creature attacks"/"enchanted creature
#: attacks" (CR 301.5a, CR 303.4b), in which case "it" is whatever the
#: Equipment or Aura is attached to, not the Equipment/Aura itself - Sigil
#: of Valor's own "Whenever equipped creature attacks alone, it gets ...".
_EQUIPPED_OR_ENCHANTED_CONDITION_RE = re.compile(
    r"\b(?:equipped|enchanted) creature\b", re.IGNORECASE
)


def _attack_trigger_pump_subject(game: "Game", ability: AbilityOnStack) -> CardState | None:
    source = ability.source(game)
    if source is None:
        return None
    condition = ability.ability.condition if isinstance(ability.ability, TriggeredAbility) else ""
    if _EQUIPPED_OR_ENCHANTED_CONDITION_RE.search(condition):
        if source.attached_to is None:
            return None
        attached = game.find_by_id(source.attached_to)
        return attached if isinstance(attached, CardState) else None
    return source


#: "Whenever this creature attacks, it gets `<P>`/`<T>` until end of turn
#: for each `<qualifier>`." - Eagle of the Great Shelf's own "it gets +1/+1
#: until end of turn for each other creature you control." CR 608.2h fixes
#: the "for each" count once, as the ability resolves - `_for_each_
#: multiplier` is the same "(other) `<qualifier>` you control" reader a mass
#: pump's own "for each" tail already reuses - and the fixed pump is a
#: one-shot continuous effect (CR 611.2) on `_attack_trigger_pump_subject`'s
#: own answer, built directly the same way `_parse_batched_attack_group_
#: pump_clause`'s own per-creature pump above is, rather than through
#: `machines/layers.py`'s printed-sentence parser, which has no "self,
#: scaled by a live for-each count, until end of turn" reader of its own to
#: hand this to.
_SELF_ATTACK_PUMP_FOR_EACH_RE = re.compile(
    r"^(?P<lead>until end of turn, )?(?:it|this [a-z]+) gets "
    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)(?P<trail> until end of turn)? "
    r"for each (?P<each>.+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s18")
def _parse_self_pump_for_each_clause(text: str) -> AbilityEffect | None:
    """`_SELF_ATTACK_PUMP_FOR_EACH_RE`'s shape; see the banner above."""
    match = _SELF_ATTACK_PUMP_FOR_EACH_RE.fullmatch(text.strip())
    if match is None or (match.group("lead") is None) == (match.group("trail") is None):
        # A pump with no stated duration ("this creature gets +1/+1 for each
        # ...") is a static ability's, read by the layer parser (CR 611.3).
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))
    multiplier = _for_each_multiplier(match.group("each"))
    if multiplier is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = _attack_trigger_pump_subject(game, ability)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        count = multiplier(game, ability.controller, str(source.id))
        if count <= 0:
            return
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=(
                    f"{source.name}: gets {power * count:+d}/{toughness * count:+d} "
                    "until end of turn"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                source_id=ability.source_id,
                selector=only_this_incarnation(source, source.zone_change_stamp),
                modification=modify_power_toughness(power * count, toughness * count),
            )
        )

    return effect


#: "Whenever this creature attacks, it gets +1/+0 until end of turn for each
#: Blood token defending player controls." (Bloodvial Purveyor) - the same
#: one-shot pump as `_SELF_ATTACK_PUMP_FOR_EACH_RE`, counting what the
#: *defending player* controls (CR 508.5: the player the attacker is attacking,
#: or the controller of the planeswalker it attacks) instead of what the pump's
#: controller does. Counted once, as the ability resolves (CR 608.2h), by
#: `permanent_description`'s own grammar so "Blood token", "creature with
#: flying" and "artifact" all mean what a target phrase means.
_SELF_ATTACK_PUMP_FOR_EACH_DEFENDING_RE = re.compile(
    r"^it gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of turn "
    r"for each (?P<each>.+?) (?:the )?defending player controls\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s18")
def _parse_self_pump_for_each_defending_clause(text: str) -> AbilityEffect | None:
    """`_SELF_ATTACK_PUMP_FOR_EACH_DEFENDING_RE`'s shape; see the banner above."""
    match = _SELF_ATTACK_PUMP_FOR_EACH_DEFENDING_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    requirement = permanent_description(match.group("each"))
    if requirement is None:
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        subject = _attack_trigger_pump_subject(game, ability)
        defending = _defending_player_of_trigger(game, ability)
        if subject is None or subject.zone is not Zone.BATTLEFIELD or defending is None:
            return
        count = sum(
            1
            for permanent in game.permanents_controlled_by(defending)
            if requirement.rejects(permanent, defending, game) is None
        )
        if count <= 0:
            return
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=(
                    f"{subject.name}: gets {power * count:+d}/{toughness * count:+d} "
                    "until end of turn"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                source_id=ability.source_id,
                selector=only_this_incarnation(subject, subject.zone_change_stamp),
                modification=modify_power_toughness(power * count, toughness * count),
            )
        )

    return effect


#: "Target creature you control that's attacking alone gets `<P>`/`<T>`
#: until end of turn. You gain `<N>` life." - Crowd of True Believers' own
#: `{T}:` ability. `machines/targeting.py`'s own `TargetRequirement.must_be_
#: attacking_alone` already recognises the "that's attacking alone" subject
#: at announcement (CR 601.2c) and rechecks it on resolution (CR 608.2b,
#: `game.resolve_targets`); this reads only the two resolution sentences,
#: building the pump directly (CR 611.2, sublayer 7c) the same way `_parse_
#: self_pump_for_each_clause` does above, rather than through `machines/
#: layers.py`'s printed-sentence grammar, whose own hand-rolled `_SUBJECT`
#: pattern has no "that's attacking alone" clause to admit - a targeting
#: restriction, not a layer-effect shape, and this file's own job to read
#: once `machines/targeting.py` already vetted it.
_TARGET_ATTACKING_ALONE_PUMP_GAIN_LIFE_RE = re.compile(
    r"^(?P<phrase>target [^.]*\battacking alone\b[^.]*) "
    r"gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of turn\.\s*"
    r"you gain (?P<life>\d+) life\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_target_attacking_alone_pump_gain_life_clause(text: str) -> AbilityEffect | None:
    """`_TARGET_ATTACKING_ALONE_PUMP_GAIN_LIFE_RE`'s shape - see the banner
    above."""
    whole = _strip_non_effect_preamble(text).strip()
    match = _TARGET_ATTACKING_ALONE_PUMP_GAIN_LIFE_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))
    life = int(match.group("life"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        store = continuous_effects(game)
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            store.add(
                ContinuousEffect(
                    description=f"{target.name}: gets {power:+d}/{toughness:+d} until end of turn",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=store.tick(),
                    duration=Duration.UNTIL_END_OF_TURN,
                    source_id=ability.source_id,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=modify_power_toughness(power, toughness),
                )
            )
        game.gain_life(game.controller_of(ability), life)

    return effect


#: "[U]ntil end of turn, this creature gets `<P>`/`<T>` and creatures you
#: control gain `<keyword(s)>`." - Wargling's own Ferocious payoff, split by
#: `_CLAUSE_SEPARATOR`'s bare "and" into two raw clauses before either ever
#: reaches `_parse_mixed_clause` - "until end of turn, this creature gets
#: `<P>`/`<T>`" and "creatures you control gain `<keyword(s)>`" - which is
#: what makes this one CR 608.2c instruction (one printed duration, shared
#: rather than repeated) a `_merge_*_clauses` pair like every other "clause A,
#: clause B carries A's own duration" case in this file, not an ordinary
#: single-clause reader: `_parse_mass_pump_clause`'s own "creatures you
#: control ..." subject grammar does not open on "this creature" either, so
#: neither half alone, nor the never-reached compound whole, is a shape it
#: (or `machines/layers.py`'s anthem readers) already reads. Two independent
#: one-shot continuous effects (CR 611.2), not one shared `ContinuousEffect`,
#: since one targets the source alone and the other the whole team, fixed
#: **now** (CR 611.2c) the same "read the group once, at resolution" way
#: `_parse_batched_attack_group_pump_clause`'s own per-creature pump above
#: already is.
#: ecl-T8: "Target creature you control gains deathtouch and lifelink until
#: end of turn. When that creature dies this turn, create a 2/2 black and
#: green Elf creature token." (Scarblade's Malice) - CR 400.7's "that
#: creature" anaphora onto the first clause's own target, watched by a
#: one-shot, this-turn-only delayed trigger (`TriggerEvent.DIES`,
#: `subject_id` the target, `expires_end_of_turn=True`) rather than a
#: replacement effect: nothing about the trigger changes what dying *means*
#: for the creature, it only reacts afterward (CR 603.2, 603.7).
_WHEN_THAT_CREATURE_DIES_THIS_TURN_RE = re.compile(
    r"^when that creature dies this turn,\s*(?P<rest>.+)$", re.IGNORECASE | re.DOTALL
)


def _parse_target_gains_then_dies_this_turn_token_whole_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_WHEN_THAT_CREATURE_DIES_THIS_TURN_RE`'s sentence pair, read whole -
    see the banner above. Read *ahead* of `_prepare_effect_clauses`'s own
    bare-"and" split: Scarblade's Malice's own first sentence, "gains
    deathtouch and lifelink until end of turn", carries exactly that bare
    "and" inside one CR 608.2c instruction, the same "power and toughness"
    problem `_DOUBLE_TARGET_POWER_AND_TOUGHNESS_RE`'s own docstring
    documents - the splitter cuts it into "gains deathtouch" and "lifelink
    until end of turn" as two fragments, neither a legal keyword-grant
    sentence on its own, and the trailing "when that creature dies this
    turn" sentence would never even be reached. The first clause is read
    exactly the way it would be alone (any ordinary single-target grant
    `_parse_targeted_clause` already reads) - this only adds the delayed
    watch on top, over whichever single object the first clause's own
    target turned out to be.
    """
    normalized = " ".join(_strip_non_effect_preamble(text).split())
    sentences = [part for part in _SIMPLE_SENTENCE_SPLIT_RE.split(normalized) if part]
    if len(sentences) < 2:
        return None
    match = _WHEN_THAT_CREATURE_DIES_THIS_TURN_RE.fullmatch(sentences[-1].strip().rstrip("."))
    if match is None:
        return None
    second = sentences[-1].strip().rstrip(".")
    first = " ".join(sentences[:-1])
    first_effect = _parse_targeted_clause(first, for_spell=for_spell)
    if first_effect is None:
        return None
    token_match = _TOKEN_CLAUSE_RE.fullmatch(match.group("rest").strip().rstrip("."))
    if token_match is None or "copy of" in match.group("rest").lower():
        return None
    count = parse_count(token_match.group("n"))
    words = token_match.group("desc").strip().split()
    tapped = bool(words) and words[0].lower() == "tapped"
    if tapped:
        words = words[1:]
    if not words or count is None:
        return None
    predefined_name = " ".join(words)
    if token_match.group("tail") is None and token_match.group("name") is None:
        definition = PREDEFINED.get(predefined_name) or _parse_generic_token_descriptor(
            words, token_match.group("tail")
        )
    else:
        definition = _parse_generic_token_descriptor(words, token_match.group("tail"))
        if definition is not None and token_match.group("name") is not None:
            definition = definition.model_copy(update={"name": token_match.group("name").strip()})
    if definition is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targets_before = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        first_effect(game, stack_object)
        if not targets_before:
            return
        target = targets_before[0]
        controller = game.controller_of(stack_object).username
        source_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=second,
                effect=CreateTokensForController(count=count, definition=definition),
                event=TriggerEvent.DIES,
                controller=controller,
                source_id=source_id,
                source_name=source_name,
                subject_id=target.id,
                expires_end_of_turn=True,
                remaining=1,
            )
        )

    return effect


#: "Choose target creature or planeswalker. You get {E}{E}{E} (three energy
#: counters), then you may pay any amount of {E}. `<name>` deals that much
#: damage to that permanent." (Galvanic Discharge) - CR 107.14/118.3's
#: variable-amount energy payment, referenced downstream by a damage clause
#: none of `_parse_targeted_clause`'s fixed-number shapes can read ("that
#: much" is not a literal number). Read whole, ahead of `parse_mixed_effect_
#: for_spell`'s per-clause split, the same way `_EACH_PLAYER_EXILE_SACRIFICE_
#: RETURN_RE` reads its own "then"-joined sentence as one CR 608.2c
#: instruction below - `split_effect_clauses` would otherwise cut this into
#: three fragments none of which reads as a known clause shape on its own.
#: The card's own name is not matched literally, so any future card sharing
#: this exact template reads for free.
_TARGET_GET_ENERGY_PAY_DAMAGE_RE = re.compile(
    r"^choose (?P<phrase>target[^.]+)\.\s*"
    r"you get (?P<e>(?:\{e\})+)\s*(?:\([^()]*\))?,\s*"
    r"then you may pay any amount of \{e\}\.\s*"
    r"[^.]+ deals that much damage to that permanent\.$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s16")
def _parse_target_get_energy_pay_damage(text: str) -> Effect | None:
    """Galvanic Discharge's own shape, see `_TARGET_GET_ENERGY_PAY_DAMAGE_RE`.

    The target was already chosen at CR 601.2c announcement (`machines/
    targeting.py` reads "target creature or planeswalker" the same whether it
    sits after "Choose" or after a verb like "destroy"), so this only has to
    grant the energy, ask CR 608.2d's variable-amount question, and deal that
    much damage to whatever `game.resolve_targets` still finds legal (CR
    608.2b) - exactly `deal_damage`'s own shape, with a paid amount standing
    in for a printed number.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _TARGET_GET_ENERGY_PAY_DAMAGE_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    energy_amount = len(re.findall(r"\{e\}", match.group("e"), re.IGNORECASE))

    def effect(game: "Game", spell: CardState) -> None:
        player = game.controller_of(spell)
        if energy_amount:
            game.add_player_counters(player, Counter.ENERGY, energy_amount)
        paid = game.pay_any_amount_of_energy(
            player, source=spell.card.name, source_id=source_id_of(spell)
        )
        if paid <= 0:
            return
        for target in game.resolve_targets(spell):
            game.deal_damage(target, paid, source=spell)

    return effect


#: "Untap all <qualifier> you control." - Emrakul, the Exigent Doom's own cast
#: trigger ("untap all lands you control"), Aggravated Assault's activated
#: ability ("untap all creatures you control"). The same "all <type
#: qualifier> you control" shape `_parse_mass_destroy_predicate`'s qualifier
#: half already reads for a mass destruction, minus that function's
#: mana-value/counter riders neither printing carries and plus an explicit
#: "you control" restriction destroy-all effects never have (Wrath of God
#: hits every player's creatures; this hits only the controller's).
#: Widened (EP01-R2-T6): "Untap all other creatures you control." (Ahn-Crop
#: Champion's and Combat Celebrant's exert consequence) - "other" leaves the
#: ability's own source tapped.
_UNTAP_ALL_YOU_CONTROL_RE = re.compile(
    r"^untap all (?P<other>other )?(?P<qualifier>.+?) you control\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s35")
def _parse_untap_all_you_control_clause(sentence: str) -> TargetedClause | None:
    """`_UNTAP_ALL_YOU_CONTROL_RE`'s shape - CR 701.26b: untapping is not
    targeted, so every matching permanent the controller has right now is
    untapped simultaneously (CR 608.2f), with no legality recheck to make."""
    match = _UNTAP_ALL_YOU_CONTROL_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    type_matches = _parse_mass_type_qualifier(match.group("qualifier"))
    if type_matches is None:
        return None
    excludes_source = match.group("other") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        for permanent in list(game.battlefield):
            if permanent.zone is not Zone.BATTLEFIELD:
                continue
            if excludes_source and source is not None and permanent.id == source.id:
                continue
            if game.controller_of(permanent).username != controller.username:
                continue
            if type_matches(game.characteristics_of(permanent)):
                permanent.untap()

    return effect


#: "That player untaps a `<quality>` they control." - Hokori, Dust Drinker's
#: "At the beginning of each player's upkeep, that player untaps a land they
#: control." "That player" is the player the triggering event names (the
#: active player whose upkeep began, CR 503.1); they choose which matching
#: permanent (CR 608.2d), a tapped one by default, and untap it (CR 701.26b).
_THAT_PLAYER_UNTAPS_RE = re.compile(
    r"^that player untaps (?:a|an|one) (?P<quality>[a-z ,-]+?) they control\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s35")
def _parse_that_player_untaps_clause(text: str) -> AbilityEffect | None:
    """`_THAT_PLAYER_UNTAPS_RE`'s shape, or `None`."""
    match = _THAT_PLAYER_UNTAPS_RE.fullmatch(text.strip())
    if match is None:
        return None
    quality = match.group("quality").strip()
    type_matches = _parse_mass_type_qualifier(quality)
    if type_matches is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = ability.event.player if ability.event is not None else None
        if player is None:
            return
        candidates = computed_permanents(game, game.permanents_controlled_by(player), type_matches)
        if not candidates:
            return
        tapped_first = sorted(candidates, key=lambda state: not state.tapped)
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player,
                prompt=f"untap a {quality} you control",
                source=ability.source_name,
                amount=1,
                cards=tuple(state.id for state in candidates),
                exact=True,
                default_cards=(tapped_first[0].id,),
                source_id=source_id_of(ability),
            )
        )
        assert isinstance(chosen, tuple)
        by_id = {state.id: state for state in candidates}
        for card_id in chosen:
            by_id[card_id].untap()

    return effect


#: "Untap all `<qualifier>`." with no controller named (Intruder Alarm's
#: "Whenever a creature enters, untap all creatures.") - CR 701.26b, every
#: player's matching permanents, untapped simultaneously (CR 608.2f). The
#: qualifier is `_parse_mass_type_qualifier`'s grammar, so "creatures you
#: control" or "attacking creatures" never reach here (each has its own rung).
_UNTAP_ALL_EVERYONES_RE = re.compile(r"^untap all (?P<qualifier>[a-z ,-]+?)\.?$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s35")
def _parse_untap_all_everyones_clause(sentence: str) -> TargetedClause | None:
    """`_UNTAP_ALL_EVERYONES_RE`'s shape."""
    match = _UNTAP_ALL_EVERYONES_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    type_matches = _parse_mass_type_qualifier(match.group("qualifier"))
    if type_matches is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for permanent in list(game.battlefield):
            if permanent.zone is Zone.BATTLEFIELD and type_matches(
                game.characteristics_of(permanent)
            ):
                permanent.untap()

    return effect


#: "Tap all `<qualifier>` `<whose>`." - Suppression Ray's own first sentence
#: and Dawnglare Invoker's whole activated ability ("tap all creatures target
#: player controls"), Cryptic Command's third mode and Subjugator Angel's
#: enters trigger ("tap all creatures your opponents control"). `<qualifier>`
#: is `_parse_mass_type_qualifier`'s grammar, the same one the untap-all and
#: mass-destroy readers use; `<whose>` names whose permanents are in the
#: group, the same controller vocabulary `_goad_group_member` already reads
#: for a mass goad. CR 115.10a: only the *player* is ever a target here - the
#: permanents are affected, never targeted.
_TAP_ALL_GROUP_RE = re.compile(
    r"^tap all (?P<attacking>attacking )?(?P<qualifier>.+?)"
    r"(?: (?P<whose>target (?:player|opponent) controls|your opponents control"
    r"|you don'?t control|an opponent controls|you control))?\.?$",
    re.IGNORECASE,
)


def _tap_all_group_members(
    clause: str,
) -> Callable[["Game", "StackObject"], list[CardState]] | None:
    """`_TAP_ALL_GROUP_RE`'s group as a selector over the board as the
    instruction is applied (CR 608.2h) - every permanent the instruction
    applies to, tapped already or not. `None` for any clause this cannot
    read, including a target phrase `machines/targeting.py` does not
    understand.

    "attacking" (Clinging Mists' "tap all attacking creatures") narrows the
    group to the creatures declared as attackers and still attacking
    (CR 506.4b: a tapped attacker stays in combat). A target player who is no
    longer legal (CR 608.2b) leaves the whole group empty.
    """
    match = _TAP_ALL_GROUP_RE.fullmatch(clause.strip())
    if match is None:
        return None
    type_matches = _parse_mass_type_qualifier(match.group("qualifier"))
    if type_matches is None:
        return None
    attacking = match.group("attacking") is not None
    whose = re.sub(r"don'?t", "don't", (match.group("whose") or "").lower())
    if whose.startswith("target") and not _targets_understood(
        whose.removesuffix(" controls"), allow_player_targets=True
    ):
        return None

    def members(game: "Game", stack_object: "StackObject") -> list[CardState]:
        controller = game.controller_of(stack_object).username
        targeted: str | None = None
        if whose.startswith("target"):
            players = [
                target
                for target in game.resolve_targets(stack_object)
                if isinstance(target, Player)
            ]
            if not players:
                return []
            targeted = players[0].username
        attackers = {attacker.id for attacker in game.attacking_creatures()} if attacking else None
        return [
            permanent
            for permanent in list(game.battlefield)
            if permanent.zone is Zone.BATTLEFIELD
            and (attackers is None or permanent.id in attackers)
            and type_matches(game.characteristics_of(permanent))
            and _goad_group_member(game, controller, whose, targeted, permanent)
        ]

    return members


def _tap_all_group_runner(
    clause: str,
) -> Callable[["Game", "StackObject"], list[CardState]] | None:
    """`_TAP_ALL_GROUP_RE`'s shape as a runner that returns the permanents it
    actually tapped - CR 701.26a: "Only untapped permanents can be tapped", so
    a permanent already tapped is left alone and is *not* one "tapped this
    way" (Suppression Ray's own ruling, 2024-06-07), which is what a later
    sentence reading back the tapped set needs. `None` for any clause
    `_tap_all_group_members` cannot read.

    The group is read once, as the instruction is applied (CR 608.2h), so a
    permanent that arrives afterwards is never tapped by it.
    """
    members = _tap_all_group_members(clause)
    if members is None:
        return None

    def run(game: "Game", stack_object: "StackObject") -> list[CardState]:
        return [
            permanent for permanent in members(game, stack_object) if game.tap_permanent(permanent)
        ]

    return run


#: "tap enchanted creature" / "tap equipped creature" - Charmed Sleep's
#: whole enters trigger, and the first half of Enchanted River's Grasp's and
#: Honest Work's "tap enchanted creature and remove all counters from it" -
#: and its "untap" twin, Volition Reins' "if enchanted permanent is tapped,
#: untap it" once `abilities._resolve_attached_object_pronoun` names the "it".
#: CR 303.4b/301.5a: the object the Aura or Equipment is attached to, never a
#: target of its own (CR 115.1b: an Aura permanent targets nothing).
_TAP_ATTACHED_RE = re.compile(
    r"^(?P<verb>tap|untap) (?:enchanted|equipped) (?:creature|permanent|artifact|land)\.?$",
    re.IGNORECASE,
)


def _attached_object(game: "Game", stack_object: "StackObject") -> CardState | None:
    """The permanent the resolving object's source is attached to (CR
    303.4b, CR 301.5a), or `None` once it has left the battlefield (CR
    608.2h). The source is read through its last known information when it
    has itself left (CR 113.7a) - the attachment it last had still names the
    enchanted object."""
    source: CardState | None = (
        stack_object.source_or_last_known(game)
        if isinstance(stack_object, AbilityOnStack)
        else stack_object
    )
    if source is None:
        return None
    attached_id = (
        source.attached_to if source.zone is Zone.BATTLEFIELD else source.last_known_attached_to
    )
    if attached_id is None:
        return None
    attached = game.find_by_id(attached_id)
    if not isinstance(attached, CardState) or attached.zone is not Zone.BATTLEFIELD:
        return None
    return attached


@MIXED_CLAUSE.rung("s35")
def _parse_tap_attached_clause(clause: str) -> TargetedClause | None:
    """`_TAP_ATTACHED_RE`'s shape - CR 701.26a's tap, silent on an
    already-tapped permanent (`CardState.tap_if_untapped`), or CR 701.26b's
    untap, silent on an untapped one."""
    match = _TAP_ATTACHED_RE.fullmatch(clause.strip())
    if match is None:
        return None
    untap = match.group("verb").lower() == "untap"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        attached = _attached_object(game, stack_object)
        if attached is None:
            return
        if untap:
            attached.untap(exert_applies=False)
        else:
            game.tap_permanent(attached)

    return effect


@MIXED_CLAUSE.rung("s35")
def _parse_tap_all_group_clause(clause: str) -> TargetedClause | None:
    """`_TAP_ALL_GROUP_RE`'s shape as an ordinary clause - see
    `_tap_all_group_runner`."""
    run = _tap_all_group_runner(clause)
    if run is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        run(game, stack_object)

    return effect


#: "Tap all `<group>`. You may pay any amount of {E}. If you do, choose up to
#: that many `<noun>` tapped this way. Put a `<kind>` counter on each of
#: them." - Suppression Ray. Four sentences carrying anaphora across all of
#: them ("that many" back to the energy paid, "tapped this way" back to the
#: first sentence's own tapped set, "each of them" back to the choice), so
#: read whole. The first sentence is `_tap_all_group_runner`'s whole grammar,
#: the chosen noun any CR 205.2a type `_parse_mass_type_qualifier` reads, the
#: counter any CR 122.1 kind. No second printing of the energy half exists
#: (Scryfall `o:"tapped this way" o:"stun counter"`, 2026-09-23: Suppression
#: Ray alone); each piece is the shared grammar, not this card's sentence.
_TAP_ALL_PAY_ENERGY_COUNTER_CHOSEN_RE = re.compile(
    r"^(?P<tap>tap all [^.]+)\.\s*"
    r"you may pay any amount of \{e\}\.\s*"
    r"if you do, choose up to that many (?P<noun>[^.]+?) tapped this way\.\s*"
    rf"put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on each of them\."
    r"(?:\s*\([^()]*\))?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_tap_all_pay_energy_counter_chosen_whole_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TAP_ALL_PAY_ENERGY_COUNTER_CHOSEN_RE`'s shape.

    CR 608.2c: in the order written - tap first, then CR 608.2d's
    variable-amount energy question (CR 107.14: paying {E} removes energy
    counters; `Game.pay_any_amount_of_energy` never pays more than the player
    has, CR 118.3, and declining is paying 0), then the choice of up to that
    many of the permanents the first sentence actually tapped and still on the
    battlefield, then the counters. Paying 0 is "if you don't": no choice is
    asked and no counter placed. Paying more than there are tapped permanents
    is legal and simply caps the choice.
    """
    whole = " ".join(_strip_non_effect_preamble(text).strip().split())
    match = _TAP_ALL_PAY_ENERGY_COUNTER_CHOSEN_RE.fullmatch(whole)
    if match is None:
        return None
    tap_all = _tap_all_group_runner(match.group("tap"))
    if tap_all is None:
        return None
    noun_matches = _parse_mass_type_qualifier(match.group("noun"))
    if noun_matches is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        tapped = tap_all(game, stack_object)
        player = game.controller_of(stack_object)
        source = (
            stack_object.source_name
            if isinstance(stack_object, AbilityOnStack)
            else stack_object.name
        )
        paid = game.pay_any_amount_of_energy(
            player, source=source, source_id=source_id_of(stack_object)
        )
        if paid <= 0:
            return
        candidates = [
            permanent
            for permanent in tapped
            if permanent.zone is Zone.BATTLEFIELD
            and noun_matches(game.characteristics_of(permanent))
        ]
        if not candidates:
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"choose up to {min(paid, len(candidates))} permanent(s) tapped this way",
                source=source,
                amount=min(paid, len(candidates)),
                cards=tuple(permanent.id for permanent in candidates),
                source_id=source_id_of(stack_object),
                exact=False,
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {permanent.id: permanent for permanent in candidates}
        for chosen_id in chosen_ids:
            game.add_counters(by_id[chosen_id], kind, amount)

    return effect


#: "Untap another target creature you control. If that creature is a `<X>`,
#: put a +1/+1 counter on it." - Little Bear's own enters trigger. Read as a
#: pair for the identical CR 400.7/608.2c reason `_parse_anaphoric_clause_
#: pair` above is: "that creature" is anaphora back to whatever the first
#: sentence's target found, not a second target of its own, and the
#: characteristic check has to run against the object the untap actually
#: reached, not the printed card. `<X>` is read by `permanent_description`,
#: the same grammar a "target `<description>`" phrase already uses, so this
#: is never pinned to "Bear" - any subtype, card type, or compound quality
#: that grammar understands reaches this the same way.
_IF_THAT_CREATURE_IS_A_COUNTER_RE = re.compile(
    r"^if that creature is an? (?P<quality>.+?), "
    r"put (?P<n>a|one|\d+) \+1/\+1 counters? on it\.?$",
    re.IGNORECASE,
)


def _parse_untap_then_if_type_counter_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_IF_THAT_CREATURE_IS_A_COUNTER_RE`'s shape; see the banner above."""
    verb_match = _TAP_UNTAP_TARGET_RE.fullmatch(first.strip())
    if verb_match is None or verb_match.group("verb").lower() != "untap":
        return None
    if not _targets_understood(
        verb_match.group("phrase"), count_agnostic=True, battlefield_only=True
    ):
        return None
    cond_match = _IF_THAT_CREATURE_IS_A_COUNTER_RE.fullmatch(second.strip())
    if cond_match is None:
        return None
    requirement = permanent_description(cond_match.group("quality"))
    if requirement is None:
        return None
    amount = parse_count(cond_match.group("n"))
    if amount is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        for target in game.resolve_targets(stack_object):
            if not (isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD):
                continue
            target.untap()
            if requirement.rejects(target, controller, game) is None:
                game.add_counters(target, Counter.PLUS_ONE, amount)

    return effect


def _block_restriction_duration(span: str) -> Duration:
    """ "this turn" (CR 611.2a, ended by CR 514.2) or "this combat" (ended
    with the combat phase, CR 500.5a/511.2)."""
    if span.lower() == "this combat":
        return Duration.UNTIL_END_OF_COMBAT
    return Duration.UNTIL_END_OF_TURN


#: "This creature can't block this combat." / "It can't block this turn." as
#: an ability's whole effect - Flummoxed Cyclops' attack trigger. CR 509.1b's
#: restriction on the ability's own source (`_SELF_ANAPHOR`), granted the
#: way `_RIDER_CANT_BLOCK_RE` grants it to a rider's referent: the self line
#: "This creature can't block." that `machines/combat.py` already reads, for
#: the printed span.
_SELF_CANT_BLOCK_RE = re.compile(
    rf"^{_SELF_ANAPHOR} can'?t block (?P<span>this turn|this combat)\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s28")
def _parse_self_cant_block_clause(text: str) -> AbilityEffect | None:
    """`_SELF_CANT_BLOCK_RE`'s shape; see the banner above."""
    match = _SELF_CANT_BLOCK_RE.fullmatch(text.strip())
    if match is None:
        return None
    span = match.group("span").lower()
    block_duration = _block_restriction_duration(span)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        effects = game.continuous_effects
        effects.add(
            ContinuousEffect(
                description=f"{source.name} can't block {span}",
                layer=Layer.ABILITY,
                timestamp=effects.tick(),
                duration=block_duration,
                selector=only_this_incarnation(source, source.zone_change_stamp),
                modification=grant_ability("This creature can't block."),
            )
        )

    return effect


#: "They can't be regenerated." / "It can't be regenerated." - Wrath of God,
#: and CR 608.2c's own worked example of a rider that *modifies its
#: antecedent* rather than running after it. Handled separately from every
#: rider above for exactly that reason: see
#: `_parse_cant_be_regenerated_clause_pair`. "A creature destroyed this way
#: can't be regenerated." (Damn) is the same rider with the antecedent spelled
#: out instead of pronouned.
_RIDER_CANT_BE_REGENERATED_RE = re.compile(
    rf"^(?:{_OBJECT_ANAPHOR}|an? {_ANAPHOR_NOUN} destroyed this way) can'?t be regenerated$",
    re.IGNORECASE,
)


#: "If it's a `<subtype>`, you may attach an Equipment you control to it."
#: - Vow to Erebor's own trailing rider ("Untap target creature you
#: control. It gets +2/+2 until end of turn. If it's a Dwarf, you may
#: attach an Equipment you control to it."), read as one of
#: `_parse_object_anaphor_clause_series`'s riders rather than through
#: `_parse_conditional_referent_clause` - that reader's own "if `<condition>`,
#: `<anaphor>` `<rider>`" shape requires the rider itself to *start* with the
#: anaphor ("it"/"that creature"), which this sentence's own "it" (at the very
#: end, "... to it") never does, and its condition ("it's a Dwarf") is about
#: the referent's own characteristics rather than a board-state
#: `condition_is_readable` phrase.
_IF_TYPE_MAY_ATTACH_EQUIPMENT_RE = re.compile(
    r"^if it'?s an? (?P<quality>[a-z][a-z '-]*?),?\s*you may attach an equipment you "
    r"control to it$",
    re.IGNORECASE,
)


def _parse_if_type_may_attach_equipment_referent_clause(rider: str) -> ReferentObjectClause | None:
    """`_IF_TYPE_MAY_ATTACH_EQUIPMENT_RE`'s shape; see the banner above.

    The Equipment is CR 608.2d's own free choice among whatever the
    controller controls, offered only when the referent still qualifies and
    only when at least one Equipment exists to offer - the identical
    `DecisionKind.MAY` shape `_parse_create_token_then_may_attach_clause`
    already asks, just with the roles of "the thing offered" (an Equipment
    the player picks) and "the thing attached to" (the referent, already
    found) swapped from that clause's own token-then-target-chooser.
    """
    match = _IF_TYPE_MAY_ATTACH_EQUIPMENT_RE.fullmatch(rider)
    if match is None:
        return None
    quality = match.group("quality").strip()

    def rider_effect(game: "Game", referents: list[CardState], stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        for referent in referents:
            if not _matches_subtype_on_battlefield(game, referent, quality):
                continue
            candidates = [
                permanent
                for permanent in game.permanents_controlled_by(controller.username)
                if "Equipment" in game.characteristics_of(permanent).subtypes
            ]
            if not candidates:
                continue
            source_name = (
                stack_object.name
                if isinstance(stack_object, CardState)
                else stack_object.source_name  # type: ignore[union-attr]
            )
            decision = game.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=controller.username,
                    prompt=f"attach an Equipment you control to {referent.name}",
                    source=source_name,
                    source_id=source_id_of(stack_object),
                    affirmative_is_legal=True,
                )
            )
            if not decision:
                continue
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt="choose an Equipment you control to attach",
                    source=source_name,
                    source_id=source_id_of(stack_object),
                    amount=1,
                    cards=tuple(permanent.id for permanent in candidates),
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {permanent.id: permanent for permanent in candidates}
            equipment = by_id.get(chosen_ids[0]) if chosen_ids else None
            if equipment is not None:
                attach_permanent(game, equipment, referent)

    return rider_effect


#: "[you may ]attach it to a creature you control" - Sidequest: Play
#: Blitzball's "transform this enchantment, then attach it to a creature you
#: control": CR 701.3a's attach of the antecedent's own object (the source,
#: an Equipment once transformed) to a permanent its controller chooses as
#: the ability resolves (CR 608.2d - "a", not "target"), of the quality the
#: sentence names.
_RIDER_ATTACH_TO_CHOSEN_RE = re.compile(
    r"^(?P<may>you may )?attach it to an? (?P<quality>[a-z -]+?) you control$",
    re.IGNORECASE,
)


def _parse_attach_referent_to_chosen_clause(rider: str) -> ReferentObjectClause | None:
    """`_RIDER_ATTACH_TO_CHOSEN_RE`'s shape. The host is chosen among the
    permanents the ability's controller controls that have the named
    quality (`models.game._permanent_quality`), never the referent itself
    (CR 301.5c: "An Equipment can't equip itself"); CR 701.3b's refusals are
    `attach_permanent`'s own. Nothing to choose, or a declined "may", leaves
    the referent where it is."""
    match = _RIDER_ATTACH_TO_CHOSEN_RE.fullmatch(rider)
    if match is None:
        return None

    from ...models.game import _permanent_quality

    quality = _permanent_quality(match.group("quality"))
    if quality is None:
        return None
    optional = match.group("may") is not None

    def rider_effect(game: "Game", referents: list[CardState], stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name  # type: ignore[union-attr]
        )
        for referent in referents:
            if referent.zone is not Zone.BATTLEFIELD:
                continue
            hosts = [
                permanent
                for permanent in game.permanents_controlled_by(controller)
                if permanent is not referent and quality(game.characteristics_of(permanent))
            ]
            if not hosts:
                continue
            if optional and not game.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=controller,
                    prompt=f"attach {referent.name} to {match.group('quality')} you control",
                    source=source_name,
                    source_id=source_id_of(stack_object),
                    affirmative_is_legal=True,
                )
            ):
                continue
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller,
                    prompt=f"choose {with_indefinite_article(match.group('quality'))} "
                    f"you control to attach {referent.name} to",
                    source=source_name,
                    source_id=source_id_of(stack_object),
                    amount=1,
                    cards=tuple(permanent.id for permanent in hosts),
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {permanent.id: permanent for permanent in hosts}
            host = by_id.get(chosen_ids[0]) if chosen_ids else None
            if host is not None:
                attach_permanent(game, referent, host)

    return rider_effect


def _layer_antecedent_clause(first: str, referent_of: ReferentReader) -> TargetedClause | None:
    """A CR 611.2 layer shape (a pump, a keyword grant, a base P/T set) used
    as an anaphoric pair's own antecedent - Tethermage's Advantage's "Target
    creature gets +2/+2 and gains reach until end of turn." (then "Untap
    it."). `_parse_mixed_clause` does not read this shape at all: only
    `effect_for`'s/`_ability_effect_or_notice`'s own whole-text
    `_is_layer_effect_text` fallback does, and that fallback sits a level
    above this pair - it is never reached once `_parse_mixed_clauses` has
    already claimed both sentences as one anaphoric pair. Built against
    `referent_of`'s own objects, read the same way the rider reads them,
    rather than a fresh `game.resolve_targets` call, so the antecedent and
    the rider can never disagree about what "it" means.
    """
    # A clause cut out of its sentence by `split_effect_clauses` has lost its
    # period, which `machines/layers.py`'s sentence reader needs.
    first = _as_sentence(first)
    if not is_resolution_layer_effect_text(first):
        return None
    builder = parsed_layer_effects(first)
    if builder is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targets = [
            target for target in referent_of(game, stack_object) if target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        if source is None:
            return
        effects = game.continuous_effects
        for built in builder(
            source,
            effects.tick(),
            targets,
            layer_context_for(game, game.controller_of(stack_object)),
        ):
            effects.add(built, game)

    return effect


#: "Each `<player|opponent>` who can't `<clause>`." - Liliana, Waker of the
#: Dead's `+1` ("Each opponent who can't loses 3 life."): the consequence
#: lands on each member who could not discard. CR 118.12's "can't" is a
#: member who never started to pay the discard - an empty hand.
_EACH_WHO_CANT_RE = re.compile(
    r"^each (?P<who>player|opponent) who can'?t (?P<clause>.+?)\.?$", re.IGNORECASE
)
#: "For each `<player|opponent>` who can't, you `<clause>`." - Cruel
#: Grimnarch's "you gain 4 life", Refurbished Familiar's and Aclazotz's "you
#: draw a card": the consequence lands on the controller, once per member who
#: could not discard.
_FOR_EACH_WHO_CANT_YOU_RE = re.compile(
    r"^for each (?P<who>player|opponent) who can'?t, (?P<clause>you .+?)\.?$", re.IGNORECASE
)
#: "loses `<n>` life" - the third-person life loss a member of the group
#: takes, which `parse_clause_effect`'s second-person grammar does not read.
_MEMBER_LOSES_LIFE_RE = re.compile(rf"^loses (?P<n>{COUNT}) life$", re.IGNORECASE)


def _who_cant_discard_consequence(
    second: str, discard_who: str, discard_count: int
) -> Callable[["Game", Player, list[Player], str, str | None], None] | None:
    """The "who can't" second sentence of a group discard, as a consequence
    `_parse_each_group_discards_then_consequence_per_failure_clause_pair`
    runs after the first sentence's discard (CR 118.12, CR 608.2c).

    The punished group must lie inside the discarding one: "each player
    discards ... each opponent who can't" judges only the opponents, and the
    controller's own empty hand costs them nothing.
    """
    text = second.strip()
    member_match = _EACH_WHO_CANT_RE.fullmatch(text)
    you_match = None if member_match is not None else _FOR_EACH_WHO_CANT_YOU_RE.fullmatch(text)
    match = member_match or you_match
    if match is None:
        return None
    who = match.group("who").lower()
    if who == "player" and discard_who != "player":
        return None
    clause_text = match.group("clause").strip()
    clause: ClauseEffect | None
    if member_match is not None and (life := _MEMBER_LOSES_LIFE_RE.fullmatch(clause_text)):
        amount = parse_count(life.group("n"))
        if amount is None:
            return None

        def lose_life(game: "Game", player: Player, source: str, source_id: str | None) -> None:
            game.lose_life(player, amount)

        clause = lose_life
    else:
        clause = parse_clause_effect(clause_text)
    if clause is None:
        return None
    on_member = member_match is not None

    def consequence(
        game: "Game",
        controller: Player,
        group: list[Player],
        source: str,
        source_id: str | None,
    ) -> None:
        failed: list[Player] = []
        for member in group:
            discarded = _discard_cards(game, member, discard_count, source, source_id=source_id)
            punished = who == "player" or member.username != controller.username
            if not discarded and punished:
                failed.append(member)
        for member in failed:
            if on_member:
                clause(game, member, source, source_id)
            else:
                clause(game, controller, source, source_id)

    return consequence


#: "Target creature you control gets +N/+N until end of turn." followed by
#: "It fights up to one target creature you don't control." - Bridgeworks
#: Battle's whole front face.
#:
#: Its own pair parser rather than a rider in `_parse_referent_object_clause`,
#: because this is the one shape in this wave where the **rider names a target
#: of its own**. `_referent_reader`'s "the antecedent targets" branch hands
#: back every legal target of the resolving object, which is right when the
#: rider adds none and wrong here: the pump would land on the opponent's
#: creature too.
#:
#: The two are told apart by controller rather than by their order in
#: `targets`, because that is what the card's own restrictions say ("you
#: control" / "you don't control") - reading `targets[0]`/`targets[1]`
#: positionally would quietly pump the wrong creature the moment CR 608.2b
#: removed one of them.
_PUMP_TARGET_YOU_CONTROL_RE = re.compile(
    r"^(?P<phrase>target (?:(?:non)?(?:white|blue|black|red|green) )?creature you control) "
    r"gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of turn$",
    re.IGNORECASE,
)
#: "Put a `<n>` `<kind>` counter[s] on target creature you control." -
#: Vigorbloom Charm's "Put a +1/+1 counter on target creature you control.
#: Then it fights target creature an opponent controls." - the counter-
#: placing twin of the pump antecedent above, sharing the same fight rider
#: and the same controller-based target split.
_COUNTER_TARGET_YOU_CONTROL_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on target creature "
    r"you control$",
    re.IGNORECASE,
)
_RIDER_FIGHTS_TARGET_RE = re.compile(
    rf"^{_OBJECT_ANAPHOR} fights (?P<phrase>(?:up to \S+ )?target .+)$", re.IGNORECASE
)


def _parse_pump_then_fight_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """Bridgeworks Battle's two sentences as one CR 608.2c instruction - "Target
    creature you control gets +N/+N until end of turn. It fights ..." - or
    Vigorbloom Charm's counter-placing twin, "Put a `<n>` `<kind>` counter[s]
    on target creature you control. Then it fights ..."

    CR 701.14a: "Each of those creatures deals damage equal to its power to
    the other creature", and CR 701.14b: "If one or both creatures instructed
    to fight are no longer on the battlefield or are no longer creatures,
    neither of them fights or deals damage" - both checked here before
    `_fight` is called, the same division of labour every other caller draws.

    CR 115.6's "up to one" is why an absent second target is not a failure:
    the pump or counter still happened, and nothing fights.

    The pump/counter is applied before the fight, in the printed order (CR
    608.2c), which is the whole point of the sequencing - a bigger creature
    deals more damage in the fight than the printed body would.
    """
    stripped_first = first.strip().rstrip(".").strip()
    stripped_second = second.strip().rstrip(".").strip()
    pump = _PUMP_TARGET_YOU_CONTROL_RE.fullmatch(stripped_first)
    counter = None if pump is not None else _COUNTER_TARGET_YOU_CONTROL_RE.fullmatch(stripped_first)
    if pump is None and counter is None:
        return None
    fight = _RIDER_FIGHTS_TARGET_RE.fullmatch(stripped_second)
    if fight is None:
        return None
    antecedent_phrase = pump.group("phrase") if pump is not None else "target creature you control"
    if not _targets_understood(antecedent_phrase, count_agnostic=True):
        return None
    if not _targets_understood(fight.group("phrase"), count_agnostic=True):
        return None
    builder = None
    counter_amount = None
    counter_kind = None
    if pump is not None:
        power, toughness = pump.group("power"), pump.group("toughness")
        builder = parsed_layer_effects(
            f"Target creature gets {power}/{toughness} until end of turn."
        )
        if builder is None:
            return None
    else:
        assert counter is not None
        counter_amount = parse_count(counter.group("n"))
        if counter_amount is None:
            return None
        counter_kind = _counter_kind(counter.group("kind"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        mine = [t for t in targets if game.controller_of(t).username == controller.username]
        theirs = [t for t in targets if game.controller_of(t).username != controller.username]
        if not mine:
            return
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        if source is None:
            return
        if builder is not None:
            effects = game.continuous_effects
            for built in builder(
                source, effects.tick(), mine[:1], layer_context_for(game, controller)
            ):
                effects.add(built, game)
        else:
            assert counter_amount is not None
            game.add_counters(mine[0], counter_kind, counter_amount)
        if not theirs:
            return  # CR 115.6: "up to one" chose none, so nothing fights.
        fighter, opponent = mine[0], theirs[0]
        if not game.characteristics_of(fighter).is_creature:
            return  # CR 701.14b
        if not game.characteristics_of(opponent).is_creature:
            return  # CR 701.14b
        _fight(game, fighter, opponent)

    return effect


#: Burrog Barrage: "Target creature you control gets +N/+N until end of turn
#: if `<condition>`. Then it deals damage equal to its power to up to one
#: target creature an opponent controls." A conditionally-pumped biter (CR
#: 608.2c's own printed "if", checked once as this instruction resolves,
#: through `Game.condition_holds` - the same reader every other printed
#: condition here goes through) whose bite rider names its own victim
#: target - the reason this needs its own pair parser rather than the
#: general object-anaphor rider, exactly `_parse_pump_then_fight_clause_
#: pair`'s own reasoning just above: the rider's own target would otherwise
#: be conflated with the antecedent's.
_CONDITIONAL_PUMP_TARGET_YOU_CONTROL_RE = re.compile(
    r"^target creature you control gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) "
    r"until end of turn if (?P<condition>.+)$",
    re.IGNORECASE,
)
#: "Then it deals damage equal to its power to up to one target creature an
#: opponent controls." - `_RIDER_DEALS_DAMAGE_EQUAL_TO_ITS_POWER_RE`'s own
#: shape with an optional leading "then" admitted (CR 608.2c's own ordering
#: word, never itself part of the instruction), since this rider always
#: follows a pump rather than a "choose" antecedent.
_CONDITIONAL_PUMP_BITE_RIDER_RE = re.compile(
    rf"^(?:then )?{_OBJECT_ANAPHOR} deals damage equal to its power to (?P<phrase>.*\btarget\b.+)$",
    re.IGNORECASE,
)


def _parse_conditional_pump_then_bite_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """Burrog Barrage's whole text as one CR 608.2c instruction pair - see
    the banner above.

    The pump applies only when the condition holds (an unreadable condition
    fails closed with a `ConditionalClauseNotice`, the same treatment
    `_parse_conditional_referent_clause` already gives an unreadable rider
    condition). The bite always runs afterwards, off whatever power the
    biter now has - `_resolve_bite_damage`, shared with `_parse_bite_damage_
    clause`/`_parse_bite_damage_clause_pair` - so a pump that never fired
    still lets a smaller creature bite for its own, unboosted power. A
    target creature gone by resolution (CR 608.2b) skips whichever half
    needed it, the same as every other bite reader.
    """
    stripped_first = first.strip().rstrip(".").strip()
    stripped_second = second.strip().rstrip(".").strip()
    pump = _CONDITIONAL_PUMP_TARGET_YOU_CONTROL_RE.fullmatch(stripped_first)
    if pump is None:
        return None
    rider = _CONDITIONAL_PUMP_BITE_RIDER_RE.fullmatch(stripped_second)
    # Savage Swipe (NW-04 T2): "... until end of turn if its power is 2. Then
    # it fights target creature you don't control." - the fight (CR 701.14a)
    # always happens, pumped or not.
    fight = (
        _RIDER_FIGHTS_TARGET_RE.fullmatch(_LEADING_THEN_WORD_RE.sub("", stripped_second))
        if rider is None
        else None
    )
    if rider is None and fight is None:
        return None
    condition_text = pump.group("condition").strip()
    # "its power is 2": "its" is the pumped target itself (CR 608.2c), read as
    # that object's own "this creature's" with the target as the condition's
    # subject - never the spell, which has no power.
    of_target = condition_text.lower().startswith("its ")
    if of_target:
        condition_text = "this creature's " + condition_text[len("its ") :]
    if not _effect_condition_is_readable(condition_text):
        return None
    if not _targets_understood("target creature you control", count_agnostic=True):
        return None
    victim_phrase = (rider if rider is not None else fight).group("phrase")  # type: ignore[union-attr]
    if not _targets_understood(victim_phrase, count_agnostic=True):
        return None
    power, toughness = pump.group("power"), pump.group("toughness")
    builder = parsed_layer_effects(f"Target creature gets {power}/{toughness} until end of turn.")
    if builder is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        mine = [t for t in targets if game.controller_of(t).username == controller.username]
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        if mine and source is not None:
            subject = mine[0] if of_target else source
            held = game.condition_holds(controller.username, condition_text, subject)
            if held is None:
                notice = ConditionalClauseNotice(
                    source_id=source_id_of(stack_object),
                    source_name=(
                        stack_object.name
                        if isinstance(stack_object, CardState)
                        else stack_object.source_name  # type: ignore[union-attr]
                    ),
                    text=first,
                )
                if notice not in game.conditional_clause_notices:
                    game.conditional_clause_notices.append(notice)
            elif held:
                effects = game.continuous_effects
                for built in builder(
                    source, effects.tick(), mine[:1], layer_context_for(game, controller)
                ):
                    effects.add(built, game)
        if fight is None:
            _resolve_bite_damage(game, stack_object, "power")
            return
        theirs = [t for t in targets if game.controller_of(t).username != controller.username]
        if not mine or not theirs:
            return  # CR 701.14b: a creature no longer there fights nobody.
        fighter, opponent = mine[0], theirs[0]
        if (
            game.characteristics_of(fighter).is_creature
            and game.characteristics_of(opponent).is_creature
        ):
            _fight(game, fighter, opponent)

    return effect


#: "This creature gets +N/+N until end of turn." followed by "If `<condition>`,
#: this creature gets +M/+M until end of turn instead." - Deluge Virtuoso's
#: own Opus rider. "Instead" (CR 608.2c) replaces the base pump outright
#: rather than adding to it (`_RIDER_ALSO_RE`'s own "also" is the additive
#: counterpart, Expressive Firedancer's shape just below) - only one of the
#: two ever actually pumps the creature.
_SELF_PUMP_EOT_RE = re.compile(
    r"^this creature gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of turn$",
    re.IGNORECASE,
)
_CONDITIONAL_SELF_PUMP_INSTEAD_RE = re.compile(
    r"^if (?P<condition>[^,]+), this creature gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) "
    r"until end of turn instead$",
    re.IGNORECASE,
)


def _parse_conditional_self_pump_instead_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """Deluge Virtuoso's whole Opus rider as one CR 608.2c instruction pair -
    see the banner above. Ability-only: "this creature" is CR 700.7's own
    self-reference, never a spell's own resolution text. The condition is
    read once, as this instruction resolves (CR 608.2h), through the same
    `Game.condition_holds` every other printed "if" here goes through, with
    the resolving ability's own event threaded in so "that spell" resolves
    to the cast trigger's own subject rather than the source
    (`_condition_holds_for_stack_object`) - an unreadable condition fails
    closed with a `ConditionalClauseNotice`, leaving the base pump as printed
    rather than guessing at the upgrade.
    """
    if for_spell:
        return None
    base = _SELF_PUMP_EOT_RE.fullmatch(first.strip().rstrip(".").strip())
    if base is None:
        return None
    upgrade = _CONDITIONAL_SELF_PUMP_INSTEAD_RE.fullmatch(second.strip().rstrip(".").strip())
    if upgrade is None:
        return None
    condition_text = upgrade.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None
    base_builder = parsed_layer_effects(
        f"This creature gets {base.group('power')}/{base.group('toughness')} until end of turn."
    )
    upgraded_builder = parsed_layer_effects(
        f"This creature gets {upgrade.group('power')}/{upgrade.group('toughness')} "
        "until end of turn."
    )
    if base_builder is None or upgraded_builder is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        controller = game.controller_of(stack_object)
        held = _condition_holds_for_stack_object(game, stack_object, condition_text, source)
        builder = base_builder
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=source_id_of(stack_object),
                source_name=stack_object.source_name,
                text=second,
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
        elif held:
            builder = upgraded_builder
        effects = game.continuous_effects
        for built in builder(source, effects.tick(), [source], layer_context_for(game, controller)):
            effects.add(built, game)

    return effect


#: "`<Target phrase>` gets +A/+B until end of turn. That creature gets +C/+D
#: instead if `<condition>`." - Festering Newt's dies
#: trigger ("target creature an opponent controls gets -1/-1 ... That creature
#: gets -4/-4 instead if you control a creature named Bogbrew Witch"). CR
#: 614.1a: "instead" replaces the base pump outright, so exactly one of the
#: two applies; the condition is read once, as the ability resolves (CR
#: 608.2h), against the ability's controller (CR 109.5), and the target is
#: the one the first sentence declared (CR 601.2c) - "that creature" adds no
#: second target.
_TARGET_PUMP_EOT_RE = re.compile(
    r"^(?P<head>target [^.]+? gets) (?P<pt>[+-]\d+/[+-]\d+) until end of turn\.?$",
    re.IGNORECASE,
)
_THAT_CREATURE_PUMP_INSTEAD_IF_RE = re.compile(
    r"^that creature gets (?P<pt>[+-]\d+/[+-]\d+)(?: until end of turn)? instead "
    r"if (?P<condition>[^.]+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_target_pump_then_that_creature_instead_if_clause(text: str) -> AbilityEffect | None:
    """`_TARGET_PUMP_EOT_RE` then `_THAT_CREATURE_PUMP_INSTEAD_IF_RE`, or `None`."""
    if " instead if " not in text:
        return None
    sentences = [part.strip() for part in re.split(r"(?<=\.)\s+", text.strip()) if part.strip()]
    if len(sentences) != 2:
        return None
    base = _TARGET_PUMP_EOT_RE.fullmatch(sentences[0])
    upgrade = _THAT_CREATURE_PUMP_INSTEAD_IF_RE.fullmatch(sentences[1])
    if base is None or upgrade is None:
        return None
    condition_text = upgrade.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None
    head = base.group("head")
    base_text = f"{head} {base.group('pt')} until end of turn."
    upgraded_text = f"{head} {upgrade.group('pt')} until end of turn."

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        targets = game.resolve_card_targets(ability)
        if not targets:
            return
        held = _condition_holds_for_stack_object(game, ability, condition_text, source)
        game.continuous_effects.create(
            source,
            targets=targets,
            context=layer_context_for(game, game.controller_of(ability)),
            ability_text=upgraded_text if held else base_text,
            game=game,
        )

    return effect


#: "This creature gets +N/+N until end of turn." followed by "If
#: `<condition>`, this creature also gains `<keyword>` until end of turn." -
#: Expressive Firedancer's own Opus rider: "also" (CR 608.2c) adds the
#: keyword grant to the base pump rather than replacing it, the additive
#: counterpart of `_parse_conditional_self_pump_instead_pair`'s "instead"
#: just above - the base pump always runs, whether or not the condition
#: holds.
_CONDITIONAL_SELF_ALSO_GAINS_RE = re.compile(
    r"^if (?P<condition>[^,]+), this creature also gains (?P<keyword>[a-z ]+) "
    r"until end of turn$",
    re.IGNORECASE,
)


def _parse_self_pump_then_conditional_also_gains_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """Expressive Firedancer's whole Opus rider - see the banner above."""
    if for_spell:
        return None
    base = _SELF_PUMP_EOT_RE.fullmatch(first.strip().rstrip(".").strip())
    if base is None:
        return None
    also = _CONDITIONAL_SELF_ALSO_GAINS_RE.fullmatch(second.strip().rstrip(".").strip())
    if also is None:
        return None
    condition_text = also.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None
    keyword_text = also.group("keyword").strip()
    base_builder = parsed_layer_effects(
        f"This creature gets {base.group('power')}/{base.group('toughness')} until end of turn."
    )
    keyword_builder = parsed_layer_effects(f"This creature gains {keyword_text} until end of turn.")
    if base_builder is None or keyword_builder is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        controller = game.controller_of(stack_object)
        effects = game.continuous_effects
        for built in base_builder(
            source, effects.tick(), [source], layer_context_for(game, controller)
        ):
            effects.add(built, game)
        held = _condition_holds_for_stack_object(game, stack_object, condition_text, source)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=source_id_of(stack_object),
                source_name=stack_object.source_name,
                text=second,
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            return
        if held:
            for built in keyword_builder(
                source, effects.tick(), [source], layer_context_for(game, controller)
            ):
                effects.add(built, game)

    return effect


def _parse_cant_be_regenerated_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "`<destroy ...>`. It/They can't be regenerated." as one instruction.

    This is CR 608.2c's own worked example, and it is the reason this rider
    cannot go through `_parse_object_anaphor_clause_pair` with the others:
    "In some cases, later text on the card may modify the meaning of earlier
    text (for example, 'Destroy target creature. It can't be regenerated'
    ...)." The rider does not run *after* the destruction - it changes how the
    destruction happens, and by the time the antecedent has finished there is
    nothing left to say it to.

    So the destruction is re-run here with the prohibition attached
    (`Game.destroy(..., regeneration_allowed=False)`) rather than by calling
    the antecedent's own parser, which has no channel for it. CR 701.19c is
    what that flag means: such effects "don't preclude such abilities from
    being activated or such spells from being cast; rather, they cause
    regeneration shields to not be applied" - the shield is skipped, not
    spent, and is still standing for the next destruction this turn.

    Only the two mass shapes and the targeted destroy are read, because those
    are the antecedents the prohibition is ever printed under. Anything else
    is refused and the card fails closed.
    """
    if _RIDER_CANT_BE_REGENERATED_RE.fullmatch(second.strip().rstrip(".").strip()) is None:
        return None
    stripped = first.strip().rstrip(".").strip()

    if _MASS_CREATURE_SUBJECT_RE.search(stripped) and stripped.lower().startswith("destroy"):

        def destroy_all(game: "Game", stack_object: "StackObject") -> None:
            for permanent in [
                candidate
                for candidate in list(game.battlefield)
                if game.characteristics_of(candidate).is_creature
            ]:
                if permanent.zone is Zone.BATTLEFIELD:
                    game.destroy(permanent, regeneration_allowed=False)

        return destroy_all

    verb_match = _DESTROY_TARGET_RE.fullmatch(stripped)
    if verb_match is None:
        return None
    if not _targets_understood(verb_match.group("phrase"), count_agnostic=True):
        return None

    def destroy_targets(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.destroy(target, regeneration_allowed=False)

    return destroy_targets


def grant_suspend(game: "Game", card: CardState, time_counters: int) -> None:
    """Put `time_counters` time counters on `card`, now in exile, and "if it
    doesn't have suspend, it gains suspend" - leaving it suspended by CR
    702.62b's own three clauses (exile, has suspend, has a time counter).

    The grant is the bare keyword line on `CardState.granted_ability_texts`,
    so `machines/keywords.granted_keyword_triggered_abilities` writes out CR
    702.62a's two exile-zone triggers from it exactly as it does for a
    printed "Suspend N-[cost]": the owner's upkeep takes a counter off, and
    the last one lets its owner cast it free, with haste for a creature. CR
    611.2a: no duration is stated, so it lasts - until CR 400.7 ends the
    object at its next zone change (`CardState.move_to` drops the line).

    A card that is not in exile (a token, which CR 704.5d removes from any
    zone but the battlefield, or a move a replacement effect sent elsewhere)
    gets nothing: "it" is no longer there to be given counters.
    """
    if card.zone is not Zone.EXILE or card not in game.exile:
        return
    game.add_counters(card, Counter.TIME, time_counters)
    if not card.has_suspend:
        card.granted_ability_texts = (*card.granted_ability_texts, "Suspend")


#: Aziza, Mage Tower Captain: "you may tap three untapped creatures you
#: control. If you do, copy that spell. You may choose new targets for the
#: copy." Raff, Weatherlight Stalwart: "you may tap two untapped creatures you
#: control. If you do, draw a card." Tidal Terror: "you may tap two other
#: untapped creatures you control. If you do, ..." - CR 118.12's shape with
#: tapping (CR 701.26a) as the optional cost: a count, an optional "other"
#: (not the ability's source), and a description of the untapped permanents.
_MAY_TAP_UNTAPPED_IF_YOU_DO_RE = re.compile(
    r"^you may tap (?P<count>[\w-]+) (?P<other>other )?untapped (?P<description>[^.]+?) "
    r"you control\.\s*if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_may_tap_untapped_if_you_do_clause(text: str) -> AbilityEffect | None:
    """`_MAY_TAP_UNTAPPED_IF_YOU_DO_RE`'s shape. The permanents are read the
    way `_sacrifice_restriction` reads a counted description ("three other
    creatures"), then narrowed to the untapped ones as the ability resolves.
    The "you may" is a `MAY` legal only while enough of them are untapped
    (CR 118.3); a yes chooses exactly that many (`CHOOSE_CARDS`), taps them,
    and runs the consequence - `pay_consequence_effect`'s, "copy that
    spell" included - on the same ability (CR 118.12)."""
    match = _MAY_TAP_UNTAPPED_IF_YOU_DO_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    other = "other " if match.group("other") else ""
    restriction = _sacrifice_restriction(
        f"{match.group('count')} {other}{match.group('description').strip()}"
    )
    if restriction is None or restriction.is_self:
        return None
    quantity = restriction.quantity
    if not quantity.exact or quantity.amount is None:
        return None
    count = quantity.amount
    consequence = pay_consequence_effect(match.group("consequence").strip())
    if consequence is None:
        return None
    prompt = (
        f"tap {match.group('count')} {other}untapped {match.group('description').strip()} "
        "you control"
    )

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        candidates = [
            permanent
            for permanent in restriction.candidates(game, player, source_id)
            if not permanent.tapped
        ]
        if not game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=player.username,
                prompt=prompt,
                source=source_name,
                affirmative_is_legal=len(candidates) >= count,
                source_id=source_id_of(ability),
            )
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"choose {count} to tap",
                source=source_name,
                amount=count,
                cards=tuple(candidate.id for candidate in candidates),
                source_id=source_id_of(ability),
            )
        )
        chosen = [candidate for candidate in candidates if candidate.id in set(chosen_ids)]
        if len(chosen) < count:
            return
        for permanent in chosen:
            game.tap_permanent(permanent)
        consequence(game, ability)

    return effect


#: "Whenever this creature attacks, you may tap another untapped Merfolk you
#: control. When you do, return target creature card with mana value 3 or
#: less from your graveyard to the battlefield." (Meanders Guide) - CR
#: 603.12's reflexive shape again, with a *chosen* permanent as the optional
#: action rather than a self-referential counter removal or a hand discard:
#: which untapped creature of the printed subtype to tap is itself a choice
#: (CR 601.2c has no bearing here - tapping a permanent as a cost or action
#: is never a target), asked the same `DecisionKind.CHOOSE_CARDS` way every
#: other "choose one of several permanents" reader in this file already is.
_TAP_ANOTHER_UNTAPPED_SUBTYPE_WHEN_YOU_DO_RE = re.compile(
    r"^(?P<may>you may )?tap another untapped (?P<subtype>[A-Z][a-zA-Z-]*) you control\.\s*"
    r"when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_tap_another_untapped_subtype_when_you_do_clause(text: str) -> AbilityEffect | None:
    """`_TAP_ANOTHER_UNTAPPED_SUBTYPE_WHEN_YOU_DO_RE`'s shape; see the banner
    above. A shape neither this reads nor `reflexive_consequence_effect`
    reads fails closed at parse time, the same guard every reflexive reader
    in this file already applies (a reflexive trigger that then resolves to
    nothing would be silence with extra steps)."""
    match = _TAP_ANOTHER_UNTAPPED_SUBTYPE_WHEN_YOU_DO_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    subtype = canonical_subtype(match.group("subtype"))
    if subtype is None:
        return None
    consequence_text = match.group("consequence").strip()
    consequence_text = consequence_text[:1].upper() + consequence_text[1:]
    if not consequence_text.endswith("."):
        consequence_text += "."
    if reflexive_consequence_effect(consequence_text) is None:
        return None
    optional = match.group("may") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        controller = game.controller_of(ability)
        source_name = ability.source_name
        board = game.computed_board()
        candidates = [
            permanent
            for permanent in game.battlefield
            if permanent.id != source.id
            and not permanent.tapped
            and board.of(permanent).controller == controller.username
            and any(word.lower() == subtype for word in board.of(permanent).subtypes)
        ]
        if not candidates:
            return
        if optional:
            decision = Decision(
                kind=DecisionKind.MAY,
                player=controller.username,
                prompt=f"tap another untapped {subtype} you control",
                source=source_name,
                affirmative_is_legal=True,
                source_id=source_id_of(ability),
            )
            if not game.ask(decision):
                return
        chosen = candidates[0]
        if len(candidates) > 1:
            pick = Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=f"choose an untapped {subtype} you control to tap",
                source=source_name,
                amount=1,
                cards=tuple(permanent.id for permanent in candidates),
                source_id=source_id_of(ability),
            )
            chosen_ids = game.ask(pick)
            by_id = {permanent.id: permanent for permanent in candidates}
            if chosen_ids:
                chosen = by_id[chosen_ids[0]]
        chosen.tap()
        # CR 603.12: created only after the action actually happened, not
        # before it, and not offered its own target until it reaches the
        # stack (`Game.put_triggers_on_stack`).
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=controller.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


#: "Tap any number of untapped creatures you control. When you do,
#: `<consequence>`, where X is the number of creatures tapped this way." -
#: Invasion of New Phyrexia // Teferi Akosa of Zhalfir's own `-3`. CR
#: 107.1c's "any number" (a non-negative count, zero included) on a plain
#: instruction rather than a "you may" cost: unlike `_parse_reflexive_
#: sacrifice_clause`'s "you may sacrifice any number of ..." (which is
#: declined entirely at zero), nothing here is optional, so the reflexive
#: ability CR 603.12 creates fires every time, X = 0 included (CR 701.24d:
#: even a set with nothing in it still gets its own library shuffled). The
#: trailing "where X is ..." clause only glosses what the ability's own text
#: already names, so it is dropped rather than parsed - `_carry_count`
#: writes the real count into every bare "X" the consequence still has.
_TAP_ANY_NUMBER_OF_UNTAPPED_CREATURES_WHEN_YOU_DO_RE = re.compile(
    r"^tap any number of untapped creatures you control\.\s*"
    r"when you do,\s*(?P<consequence>.+?)"
    r"(?:,\s*where x is the number of creatures tapped this way)?\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s22")
def _parse_tap_any_number_of_untapped_creatures_when_you_do_clause(
    text: str,
) -> AbilityEffect | None:
    """`_TAP_ANY_NUMBER_OF_UNTAPPED_CREATURES_WHEN_YOU_DO_RE`'s shape; see
    the banner above. A consequence neither `reflexive_consequence_effect`
    nor the stand-in-count probe reads fails the whole ability closed, the
    same guard every other reflexive reader in this file already applies."""
    match = _TAP_ANY_NUMBER_OF_UNTAPPED_CREATURES_WHEN_YOU_DO_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    consequence_text = match.group("consequence").strip()
    consequence_text = consequence_text[:1].upper() + consequence_text[1:]
    if not consequence_text.endswith("."):
        consequence_text += "."
    if reflexive_consequence_effect(_carry_count(consequence_text, 2, x=True)) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source_name = ability.source_name
        board = game.computed_board()
        candidates = [
            permanent
            for permanent in game.battlefield
            if not permanent.tapped
            and board.of(permanent).controller == controller.username
            and board.of(permanent).is_creature
        ]
        chosen: list[CardState] = []
        if candidates:
            pick = Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="tap any number of untapped creatures you control",
                source=source_name,
                amount=len(candidates),
                exact=False,
                cards=tuple(permanent.id for permanent in candidates),
                source_id=source_id_of(ability),
            )
            chosen_ids = game.ask(pick)
            by_id = {permanent.id: permanent for permanent in candidates}
            chosen = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
            for permanent in chosen:
                permanent.tap()
        # CR 603.12/107.1c: an instruction, not a "you may" cost - the
        # reflexive ability fires whether or not any creature was actually
        # tapped, with X written in as however many were (zero included).
        game.create_reflexive_trigger(
            text=_carry_count(consequence_text, len(chosen), x=True),
            controller=controller.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


# --------------------------------------------------------------------------
# The consequence of a paid "you may pay `<cost>`. If/When you do, ..."
# --------------------------------------------------------------------------
#
# One reader for every paid-cost family - energy (CR 107.14) and ordinary
# mana alike - since what follows "If you do"/"When you do" does not depend on
# what was paid. Three consequence shapes the ordinary clause dispatcher
# (`parse_mixed_effect`) does not read are read here:
#
# - the source anaphor, "it gets +2/+0 until end of turn." / "it gets +1/+1
#   and gains trample ...": the "it" is the object the trigger event names
#   (the attacking creature, the creature that died) - the ability's own
#   source when the event names none;
# - a one-shot continuous effect (CR 611.2) over the ability's own targets,
#   "another target creature you control gets +1/+0 and gains haste until
#   end of turn.", read by `machines/layers.py` off the consequence's own text
#   rather than the whole printed ability;
# - a modal consequence, "choose one - ...", only on the reflexive side: CR
#   603.3c/700.2b choose the mode as the reflexive ability is put on the
#   stack, which `Game.put_triggers_on_stack` already does for any modal
#   triggered ability whose own text is the bulleted list.

#: "it gets ..."/"it gains ..." - the source anaphor as the whole
#: consequence's subject.
_SOURCE_ANAPHOR_SUBJECT_RE = re.compile(r"^it (?P<predicate>(?:gets|gains)\b.+)$", re.IGNORECASE)


def _continuous_consequence(sentence: str, *, anaphor: bool) -> AbilityEffect:
    """A CR 611.2 one-shot continuous effect read off `sentence` alone.

    `anaphor` says `sentence` stands for the source anaphor - rewritten with
    a "target creature" subject so `machines/layers.py` builds it over the one
    object handed to it, `_referent_of_it`'s answer. Otherwise the sentence's
    own targets are the ability's announced ones, rechecked (CR 608.2b), or
    the ability's source when it names none (`create_continuous_effect_of_
    ability`'s own two shapes); CR 113.7a lets a targeted one apply after its
    source is gone.
    """
    requires_target = False
    if not anaphor:
        profile = profile_for_text(sentence)
        requires_target = profile.understood and bool(profile.requirements)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if anaphor:
            referent = _referent_of_it(game, ability)
            if referent is None:
                return
            targets = [referent]
            source = source or referent
        elif requires_target:
            targets = game.resolve_card_targets(ability)
        else:
            if source is None or source.zone is not Zone.BATTLEFIELD:
                return
            targets = [source]
        if source is None or not targets:
            return
        continuous_effects(game).create(
            source,
            targets=targets,
            context=layer_context_for(game, game.controller_of(ability)),
            ability_text=sentence,
            game=game,
        )

    return effect


def _layer_consequence(text: str) -> AbilityEffect | None:
    """`text` as `_continuous_consequence`'s one-shot continuous effect, the
    source anaphor first, or `None` when `machines/layers.py` reads neither."""
    anaphor = _SOURCE_ANAPHOR_SUBJECT_RE.fullmatch(text.strip())
    if anaphor is not None:
        rewritten = _as_sentence(f"target creature {anaphor.group('predicate')}")
        if is_resolution_layer_effect_text(rewritten) and parsed_layer_effects(rewritten):
            return _continuous_consequence(rewritten, anaphor=True)
        return None
    sentence = _as_sentence(text)
    if _is_layer_effect_text(sentence) and parsed_layer_effects(sentence) is not None:
        return _continuous_consequence(sentence, anaphor=False)
    return None


#: "You get `<energy>`, then you may pay one or more `<energy>`. If you do,
#: create an X/X `<desc>` token, where X is the amount of `<energy>` paid
#: this way." (Aether Refinery) - the same CR 118.12 "If you do" shape as
#: `_MAY_PAY_ENERGY_IF_YOU_DO_RE` just above, with a variable payment
#: (`Game.pay_any_amount_of_energy`, CR 608.2d) standing in for the fixed one,
#: and a token count taken from what was actually paid rather than a printed
#: number - the same "X is the amount ... paid this way" shape `_TARGET_GET_
#: ENERGY_PAY_DAMAGE_RE` already reads for damage instead of a token.
_GET_ENERGY_THEN_PAY_CREATE_X_TOKEN_RE = re.compile(
    r"^you get (?P<granted>(?:\{e\})+),?\s*then you may pay one or more (?:\{e\})\.\s*"
    r"if you do,\s*create an? x/x (?P<desc>.+?) tokens?,\s*where x is the amount of "
    r"(?:\{e\}) paid this way\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_get_energy_then_pay_create_x_token_clause(text: str) -> AbilityEffect | None:
    """`_GET_ENERGY_THEN_PAY_CREATE_X_TOKEN_RE`'s shape."""
    match = _GET_ENERGY_THEN_PAY_CREATE_X_TOKEN_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    granted = len(re.findall(r"\{e\}", match.group("granted"), re.IGNORECASE))
    words = match.group("desc").strip().split()
    if not words:
        return None
    definition = _parse_generic_token_descriptor(words, None)
    if definition is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        _source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        if granted:
            game.add_player_counters(player, Counter.ENERGY, granted)
        paid = game.pay_any_amount_of_energy(
            player, source=source_name, source_id=source_id_of(ability)
        )
        if paid <= 0:
            return
        sized = definition.model_copy(update={"power": paid, "toughness": paid})
        create_tokens(game, sized, player.username, 1)

    return effect


#: "Each equipped attacking creature gains `<keyword(s)>` until end of
#: turn." - Dain Ironfoot's own attack trigger. CR 301.5a's "equipped
#: creature" widened to a group ("each equipped ... creature", not "the
#: equipped creature" - a permanent qualifies whenever *any* Equipment is
#: attached to it, not only the ability's own source's Equipment), narrowed
#: to attackers by `Game.attacking_creatures`, the same "computed at
#: resolution, not re-targeted" set `_parse_dalkovan_attack_tokens` and
#: every other attacker-scoped grant already reads.
_EQUIPPED_ATTACKING_CREATURES_GAIN_KEYWORDS_RE = re.compile(
    r"^each equipped attacking creature gains? (?P<keywords>[a-z].+?) "
    r"until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_equipped_attacking_creatures_gain_keywords_clause(text: str) -> AbilityEffect | None:
    """`_EQUIPPED_ATTACKING_CREATURES_GAIN_KEYWORDS_RE`'s shape; see the
    banner above."""
    match = _EQUIPPED_ATTACKING_CREATURES_GAIN_KEYWORDS_RE.fullmatch(text.strip())
    if match is None:
        return None
    keywords = _split_and_validate_keywords(match.group("keywords"))
    if keywords is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        equipped_attackers = [
            creature
            for creature in game.attacking_creatures()
            if any(
                permanent.zone is Zone.BATTLEFIELD
                and permanent.attached_to == creature.id
                and "Equipment" in game.characteristics_of(permanent).subtypes
                for permanent in game.battlefield
            )
        ]
        if not equipped_attackers:
            return
        effects = game.continuous_effects
        for creature in equipped_attackers:
            for keyword in keywords:
                effects.add(
                    ContinuousEffect(
                        description=f"{ability.source_name}: {creature.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=effects.tick(),
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=only_this_incarnation(creature, creature.zone_change_stamp),
                        modification=grant_ability(keyword),
                    ),
                    game,
                )

    return effect


# --------------------------------------------------------------------------
# Suspect (CR 701.60)
# --------------------------------------------------------------------------
#
# CR 701.60a: "Certain spells and abilities instruct a player to suspect a
# creature. That creature becomes suspected until it leaves the battlefield or
# until a spell or ability causes it to no longer be suspected." The
# designation is `CardState.suspected` (CR 701.60b); its menace and "can't
# block" are `machines/layers._suspected_abilities` (CR 701.60c). Read here:
#
# - "suspect it" / "suspect this creature" (Barbed Servitor, Person of
#   Interest, Rubblebelt Braggart's "you may suspect it") - the trigger's own
#   subject, or its source when the event names none;
# - "suspect enchanted creature" (Convenient Target) - what the source is
#   attached to;
# - "suspect [up to one] [other] target creature ..." (Clandestine Meddler,
#   Absolving Lammasu) - each still-legal target (CR 608.2b);
# - "<it | this creature | that creature> is no longer suspected" and "all
#   suspected creatures are no longer suspected" (Frantic Scapegoat, Absolving
#   Lammasu).
_SUSPECT_TARGET_RE = re.compile(
    r"^suspect (?P<phrase>(?:up to \S+ |another )?(?:other )?target .+?)\.?$", re.IGNORECASE
)
_SUSPECT_OBJECT_RE = re.compile(
    r"^suspect (?P<object>it|this creature|that creature|enchanted creature|equipped creature)"
    r"\.?$",
    re.IGNORECASE,
)
_NO_LONGER_SUSPECTED_RE = re.compile(
    r"^(?:(?P<object>it|this creature|that creature|enchanted creature)(?:'s| is)"
    r"|(?P<all>all suspected creatures are|each suspected creature is)) no longer suspected\.?$",
    re.IGNORECASE,
)


def suspect(game: "Game", permanent: CardState) -> bool:
    """CR 701.60a: suspect a creature - only a creature on the battlefield can
    be (CR 701.60b: only permanents have the designation), judged on the
    computed board (CR 613.5). Returns whether it became suspected."""
    if permanent.zone is not Zone.BATTLEFIELD:
        return False
    if not game.characteristics_of(permanent).is_creature:
        return False
    permanent.suspected = True
    return True


def _named_object(game: "Game", stack_object: "StackObject", word: str) -> CardState | None:
    """The one object "it"/"this creature"/"that creature"/"enchanted
    creature" names for a resolving ability: the trigger event's subject, the
    source, or what the source is attached to."""
    word = word.lower()
    source = stack_object.source(game) if isinstance(stack_object, AbilityOnStack) else None
    if word in ("enchanted creature", "equipped creature"):
        if source is None or source.attached_to is None:
            return None
        found = game.find_by_id(source.attached_to)
        return found if isinstance(found, CardState) else None
    if word == "this creature":
        return source
    event = getattr(stack_object, "event", None)
    if event is not None and event.subject_id is not None:
        found = game.find_by_id(event.subject_id)
        if isinstance(found, CardState):
            return found
    return source


@MIXED_CLAUSE.rung("s17", for_spell=FORWARD)
def _parse_suspect_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """The suspect family - see the banner above."""
    text = clause.strip()
    if match := _SUSPECT_TARGET_RE.fullmatch(text):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None

        def suspect_targets(game: "Game", stack_object: "StackObject") -> None:
            for target in game.resolve_targets(stack_object):
                if isinstance(target, CardState):
                    suspect(game, target)

        return suspect_targets
    if for_spell:
        return None
    if match := _SUSPECT_OBJECT_RE.fullmatch(text):
        word = match.group("object")

        def suspect_object(game: "Game", stack_object: "StackObject") -> None:
            found = _named_object(game, stack_object, word)
            if found is not None:
                suspect(game, found)

        return suspect_object
    if match := _NO_LONGER_SUSPECTED_RE.fullmatch(text):
        word = match.group("object")

        def no_longer_suspected(game: "Game", stack_object: "StackObject") -> None:
            if word is None:
                for permanent in game.battlefield:
                    permanent.suspected = False
                return
            found = _named_object(game, stack_object, word)
            if found is not None:
                found.suspected = False

        return no_longer_suspected
    return None


# --------------------------------------------------------------------------
# Goad (CR 701.15)
# --------------------------------------------------------------------------
#
# CR 701.15a: "Certain spells and abilities can goad a creature. Until the
# next turn of the controller of that spell or ability, that creature is
# goaded." The goader is always the resolving object's controller, and
# `Game.goad` records it (CR 701.15d's repeat no-op included). Three printed
# subjects, each read here or in the object-anaphor riders below:
#
# - a target phrase, any count: "Goad target creature." (Glóin, Dwarf
#   Emissary), "Goad up to two target creatures." - vetted by
#   `_targets_understood`, the grammar every other targeted verb here uses;
# - a group: "Goad all creatures you don't control." (Disrupt Decorum),
#   "goad each creature target player controls." (Geode Rager), "Goad all
#   creatures your opponents control." - `_GOAD_GROUP_RE`;
# - an anaphor for an earlier sentence's object: "Tap target creature an
#   opponent controls. Goad it." (Oceanus Dragon) - `_RIDER_GOAD_RE`;
# - a trigger's player anaphor: "goad each creature that player controls."
#   (Marisi, Breaker of the Coil) - the player the trigger's event names
#   (CR 400.7), read off `ability.event` the way `_DAMAGE_THAT_PLAYER_RE` is;
# - one target per opponent: "for each opponent, goad [up to one] target
#   creature that player/opponent controls." (Frenzied Gorespawn, Havoc
#   Eater) - `_GOAD_FOR_EACH_OPPONENT_RE`, targeted through
#   `targeting._for_each_opponent_profile` (CR 601.2c).
_GOAD_FOR_EACH_OPPONENT_RE = re.compile(
    r"^for each opponent, goad (?P<up_to>up to one )?target (?P<desc>.+?) "
    r"that (?:player|opponent) controls\.?$",
    re.IGNORECASE,
)
_GOAD_TARGET_RE = re.compile(
    r"^goad (?P<phrase>(?:up to \S+ |another )?target .+?)\.?$", re.IGNORECASE
)
_GOAD_GROUP_RE = re.compile(
    r"^goad (?:each creature|all creatures)"
    r"(?: (?P<whose>you control|you don'?t control|your opponents control|an opponent controls"
    r"|target (?:player|opponent) controls|that player controls))?\.?$",
    re.IGNORECASE,
)


def _goad_group_member(
    game: "Game", goader: str, whose: str, targeted: str | None, permanent: CardState
) -> bool:
    """Whether `permanent`'s controller fits the group's controller words."""
    controller = game.controller_of(permanent).username
    if whose == "":
        return True
    if whose == "you control":
        return controller == goader
    if whose.startswith("target") or whose == "that player controls":
        return controller == targeted
    # "you don't control" / "your opponents control" / "an opponent
    # controls": in a game without teams every other player is an opponent
    # (CR 102.3), so the three read the same set.
    return controller != goader


@MIXED_CLAUSE.rung("s17", for_spell=FORWARD)
def _parse_goad_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Goad `<target phrase>`." or "Goad each creature / all creatures
    `<whose>`." - see the banner above."""
    text = clause.strip()
    if match := _GOAD_GROUP_RE.fullmatch(text):
        whose = re.sub(r"don'?t", "don't", (match.group("whose") or "").lower())
        if whose.startswith("target") and not _targets_understood(
            whose.removesuffix(" controls"), allow_player_targets=True
        ):
            return None

        if whose == "that player controls" and for_spell:
            return None

        def goad_group(game: "Game", stack_object: "StackObject") -> None:
            goader = game.controller_of(stack_object).username
            targeted: str | None = None
            if whose == "that player controls":
                event = getattr(stack_object, "event", None)
                targeted = None if event is None else event.player or event.subject_controller
                if targeted is None:
                    return
            elif whose.startswith("target"):
                players = [
                    target
                    for target in game.resolve_targets(stack_object)
                    if isinstance(target, Player)
                ]
                if not players:
                    return
                targeted = players[0].username
            board = game.computed_board()
            for permanent in list(game.battlefield):
                if board.of(permanent).is_creature and _goad_group_member(
                    game, goader, whose, targeted, permanent
                ):
                    game.goad(permanent, goader)

        return goad_group
    if match := _GOAD_FOR_EACH_OPPONENT_RE.fullmatch(text):
        if not _targets_understood(
            _for_each_opponent_target_phrase(match.group("desc")), count_agnostic=True
        ):
            return None
        return _goad_resolved_targets
    if match := _GOAD_TARGET_RE.fullmatch(text):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None

        return _goad_resolved_targets
    return None


def _goad_resolved_targets(game: "Game", stack_object: "StackObject") -> list[CardState]:
    """Goad each of the resolving object's still-legal targets (CR 608.2b),
    returning the creatures goaded."""
    goader = game.controller_of(stack_object).username
    goaded: list[CardState] = []
    for target in game.resolve_targets(stack_object):
        if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
            game.goad(target, goader)
            goaded.append(target)
    return goaded


#: `_GOAD_FOR_EACH_OPPONENT_RE`'s sentence and a rider counting what it
#: goaded: "Put X +1/+1 counters on this creature, where X is the total power
#: of creatures goaded this way." (Havoc Eater). "Goaded this way" is CR
#: 400.7 anaphora for the first sentence's own targets, so it is read whole.
_GOAD_FOR_EACH_OPPONENT_THEN_COUNTERS_RE = re.compile(
    r"^for each opponent, goad (?:up to one )?target (?P<desc>.+?) "
    r"that (?:player|opponent) controls\.\s*"
    r"put x (?P<kind>\+1/\+1|[a-z]+) counters? on this \w+, "
    r"where x is the total power of creatures goaded this way\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s29", for_spell=False)
def _parse_goad_for_each_opponent_then_counters_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_GOAD_FOR_EACH_OPPONENT_THEN_COUNTERS_RE`'s shape - see the banner."""
    match = _GOAD_FOR_EACH_OPPONENT_THEN_COUNTERS_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(
        _for_each_opponent_target_phrase(match.group("desc")), count_agnostic=True
    ):
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        goaded = _goad_resolved_targets(game, stack_object)
        board = game.computed_board()
        # CR 107.1b: negative powers count toward the total; only a negative X is 0.
        amount = max(sum(board.of(creature).power or 0 for creature in goaded), 0)
        source = stack_object.source(game) if isinstance(stack_object, AbilityOnStack) else None
        if amount > 0 and source is not None and source.zone is Zone.BATTLEFIELD:
            game.add_counters(source, kind, amount)

    return effect


#: "Whenever a `<subtype>` you control enters, you may attach this Equipment
#: to it." (Quintessential Katana's own trigger) / "Whenever a creature you
#: control with mana value 5 or greater enters, you may attach this
#: Equipment to it." (Doc Ock's Tentacles, verified Modern/Pioneer/Standard
#: legal - a mana-value filter rather than a subtype one, proving this reads
#: the mechanism, not the card). CR 701.3a's attach, offered as CR 608.2d's
#: ordinary "you may" - unlike `_CREATE_TOKEN_THEN_MAY_ATTACH_RE`'s own "it",
#: which is the token the same sentence just created, "it" here is CR 603.2's
#: own trigger subject: the permanent that entering is what triggered this
#: ability at all (`AbilityOnStack.event.subject_id`), read by *this*
#: reader alone - the filter ("a Ninja", "a creature ... with mana value 5 or
#: greater") lives entirely in the trigger's own condition, already read by
#: the ordinary `ENTERS_THE_BATTLEFIELD` machinery, and is no part of this
#: effect body at all.
_MAY_ATTACH_TO_ENTERING_CREATURE_RE = re.compile(
    r"^(?P<may>you may )?attach (?P<what>it|this (?:equipment|aura|fortification|permanent)"
    r"|target (?P<kind>equipment|aura|fortification) you control"
    r"(?: with mana value (?P<mv>\d+)(?: or (?P<mv2>\d+))?)?) "
    r"to (?P<where>it|that (?:creature|permanent)|this (?:creature|permanent)"
    r"|target creature you control)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_may_attach_to_entering_creature_clause(text: str) -> AbilityEffect | None:
    """`_MAY_ATTACH_TO_ENTERING_CREATURE_RE`'s shape, or `None`.

    The attachment is "it" (the trigger subject: Sigarda's Aid's entering
    Equipment), the source ("this Equipment"/"this Aura", Prison Term), or a
    targeted Equipment you control ("target Equipment you control with mana
    value 2 or 3", Frodo, Determined Hero; Kor Outfitter); the host is "it" /
    "that creature" (the trigger subject), the source itself ("this creature",
    Frodo's own name once normalised), or a second target. Targets are
    announced by the ordinary trigger-target machinery
    (`targeting.profile_for_text`, CR 603.3d), in the order the text names
    them, and rechecked as the ability resolves (CR 608.2b)."""
    match = _MAY_ATTACH_TO_ENTERING_CREATURE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    what = match.group("what").lower()
    where = match.group("where").lower()
    if match.group("may") is None and not (
        what.startswith("this ") and where in ("that creature", "that permanent")
    ):
        return None  # a bare "attach it to target creature you control" is the plain attach
    values = {int(value) for value in (match.group("mv"), match.group("mv2")) if value is not None}
    wanted = (match.group("kind") or "").capitalize()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        entered = (
            game.find_by_id(event.subject_id)
            if event is not None and event.subject_id is not None
            else None
        )
        source = ability.source(game)
        targets = [t for t in game.resolve_targets(ability) if isinstance(t, CardState)]
        attachment = host = None
        if what == "it":
            attachment = entered
        elif what.startswith("this "):
            attachment = source
        elif targets:
            attachment = targets.pop(0)
            if wanted not in game.characteristics_of(attachment).subtypes or (
                values and int(game.characteristics_of(attachment).mana_value) not in values
            ):
                return  # CR 608.2b: no longer what the target asked for
        if where in ("it", "that creature", "that permanent"):
            host = entered
        elif where.startswith("this "):
            host = source
        elif targets:
            host = targets.pop(0)
        for found in (attachment, host):
            if not isinstance(found, CardState) or found.zone is not Zone.BATTLEFIELD:
                return  # CR 608.2b: no longer there to attach (or to attach to)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        controller = game.controller_of(ability)
        # Illusory Gains' "Whenever a creature an opponent controls enters,
        # attach this Aura to that creature." prints no "you may": the same
        # attach, not offered.
        decision = match.group("may") is None or game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=controller.username,
                prompt=f"attach {attachment.name} to {host.name}",
                source=ability.source_name,
                source_id=source_id_of(ability),
                affirmative_is_legal=True,
            )
        )
        if decision:
            attach_permanent(game, attachment, host)

    return effect


# --------------------------------------------------------------------------
# "For each opponent, <action> up to one target X that player controls."
# --------------------------------------------------------------------------
#
# CR 601.2c/603.3d target every one of an ability's targets when it is put
# on the stack, one independent target per opponent - Age of Ultron's own
# Saga chapter ("For each opponent, destroy up to one target nonartifact
# creature that player controls.") is the real, off-set printing of the
# identical grammar Hapatra, the Desert Frost's own ETB trigger and Lich's
# Relic's reflexive consequence both read.
#
# **Scoped to the common two-player case, and said so rather than hidden.**
# A true CR 601.2c reading needs one independent `TargetRequirement` per
# opponent, sized from the game the profile is built for - `machines/
# targeting.py`'s own `TargetingProfile`/`profile_for_text` are pure text, no
# `game` in reach, and threading one through every caller (`Casting.
# targeting`, trigger-target announcement, `legal_actions`) is the "per-
# opponent target groups" subsystem this stream's own assignment names but
# does not have room to build whole. What is built instead is exactly right
# in a two-player game, where "for each opponent" and "an opponent" name the
# same single player: one ordinary "target `<X>` an opponent controls"
# requirement, applied at resolution to every opponent whose target was
# actually chosen. A three-or-more-player game would only ever see the first
# opponent's own creature offered a target at all, which is recorded as a
# gap in `docs/engine-coverage.md` rather than asserted away.


def _for_each_opponent_target_phrase(description: str) -> str:
    """ "`<description>` that player controls" rewritten to the ordinary
    "target `<description>` an opponent controls" grammar `_targets_
    understood`/`permanent_description` already read, so this shape shares
    every existing rule about qualifiers, "or", and trailing "with
    `<keyword>`" instead of re-deriving them.
    """
    return f"up to one target {description.strip()} an opponent controls"


_FOR_EACH_OPPONENT_TAP_RE = re.compile(
    r"^for each opponent, tap up to one target (?P<desc>.+?) that player controls\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s29", for_spell=False)
@MIXED_CLAUSE.rung("s21", for_spell=FORWARD)
def _parse_for_each_opponent_tap_clause(text: str, *, for_spell: bool) -> AbilityEffect | None:
    """`_FOR_EACH_OPPONENT_TAP_RE`'s shape - Hapatra, the Desert Frost's own
    antecedent sentence. The rider that follows it ("Put a stun counter on
    each of those creatures.") is `_parse_for_each_opponent_tap_then_stun_
    clause_pair`'s own shape, not this one.
    """
    match = _FOR_EACH_OPPONENT_TAP_RE.fullmatch(text.strip())
    if match is None:
        return None
    phrase = _for_each_opponent_target_phrase(match.group("desc"))
    if not _targets_understood(phrase, count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.tap_permanent(target)

    return effect


_FOR_EACH_OPPONENT_TAP_THEN_STUN_RE = re.compile(
    r"^for each opponent, tap up to one target (?P<desc>.+?) that player controls\.\s*"
    r"put a stun counter on each of those creatures\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s29", for_spell=False)
@MIXED_CLAUSE.rung("s21", for_spell=FORWARD)
def _parse_for_each_opponent_tap_then_stun_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """Hapatra, the Desert Frost's whole ETB sentence, read as one CR 608.2c
    instruction: tap each per-opponent target, then a stun counter (CR
    122.1d) on "each of those creatures" - the targets just tapped, read back
    off `game.resolve_targets` rather than re-targeted, since "those
    creatures" is CR 400.7 anaphora for the first sentence's own subject, not
    a fresh "target".
    """
    match = _FOR_EACH_OPPONENT_TAP_THEN_STUN_RE.fullmatch(text.strip())
    if match is None:
        return None
    phrase = _for_each_opponent_target_phrase(match.group("desc"))
    if not _targets_understood(phrase, count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        tapped: list[CardState] = []
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.tap_permanent(target)
                tapped.append(target)
        for permanent in tapped:
            if permanent.zone is Zone.BATTLEFIELD:
                permanent.add_counters(Counter.STUN, 1)

    return effect


_TAP_TARGETS_THEN_STUN_RE = re.compile(
    rf"^tap (?P<phrase>(?:up to )?(?:{COUNT}|x) target [a-z ]+?)\.\s*"
    r"put a stun counter on each of those [a-z]+(?P<opposing> you don'?t control)?\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s29")
def _parse_tap_targets_then_stun_clause(text: str) -> AbilityEffect | None:
    """Lost in the Maze: "tap X target creatures. Put a stun counter on each of
    those creatures you don't control." - the counted-target twin of
    `_parse_for_each_opponent_tap_then_stun_clause` (CR 608.2c: tap first,
    then the stun counter lands on "those creatures" - the ones just tapped,
    narrowed by "you don't control" to the ones the ability's controller does
    not control; CR 122.1d for the counter).
    """
    match = _TAP_TARGETS_THEN_STUN_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    phrase = match.group("phrase")
    if not _targets_understood(phrase, count_agnostic=True):
        return None
    opposing = match.group("opposing") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        tapped: list[CardState] = []
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.tap_permanent(target)
                tapped.append(target)
        for permanent in tapped:
            if permanent.zone is not Zone.BATTLEFIELD:
                continue
            if opposing and game.controller_of(permanent).username == controller:
                continue
            permanent.add_counters(Counter.STUN, 1)

    return effect


#: Kraul Harpooner's own enters trigger, read whole ahead of the per-clause
#: splitter for the same reason `_EACH_PLAYER_EXILE_SACRIFICE_RETURN_RE` is:
#: the fight clause's "that creature" is anaphoric (CR 400.7) for whatever
#: `<phrase>` names, and the pump's own magnitude is `count_expression`'s
#: "the number of creature cards in your graveyard" - both belong to one CR
#: 608.2c instruction, not three independent clauses `_CLAUSE_SEPARATOR`'s
#: "then"/"," cuts would otherwise scatter. The ability word ("Undergrowth
#: — ") is already stripped by `machines/abilities.py` before this text is
#: ever seen (CR 207.2c).
_UNDERGROWTH_PUMP_AND_FIGHT_RE = re.compile(
    r"^choose (?P<phrase>up to \S+ target [^.]+)\.\s*"
    r"this creature gets \+x/\+0 until end of turn,\s*where x is (?P<expr>[^,]+),\s*"
    r"then you may have this creature fight that creature\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s16")
def _parse_undergrowth_pump_and_fight_clause(text: str) -> AbilityEffect | None:
    """Kraul Harpooner: "choose up to one target creature you don't control
    with flying. This creature gets +X/+0 until end of turn, where X is the
    number of creature cards in your graveyard, then you may have this
    creature fight that creature."

    Printed order (CR 608.2c): the pump always happens - X is computed and
    applied whether or not a target was chosen (CR 115.6's "up to one"
    legally choosing zero, trap this file's own docstring calls out) - and
    only *then* does the optional fight ask its `MAY` question, and only if
    there is a "that creature" for it to name at all.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _UNDERGROWTH_PUMP_AND_FIGHT_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    count_fn = count_expression(match.group("expr"))
    if count_fn is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        controller = game.controller_of(ability)
        amount = count_fn(game, controller.username)
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{source.name} gets +{amount}/+0 until end of turn",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_only(source.id),
                modification=modify_power_toughness(amount, 0),
            )
        )
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        if not targets:
            # CR 115.6: "up to one" legally chose zero - nothing to fight.
            return
        opponent_creature = targets[0]
        board = game.computed_board()
        if (
            source.zone is not Zone.BATTLEFIELD
            or opponent_creature.zone is not Zone.BATTLEFIELD
            or Type.CREATURE not in board.of(source).types
            or Type.CREATURE not in board.of(opponent_creature).types
        ):
            # CR 701.14b: either is gone, or no longer a creature.
            return
        prompt = f"have {source.name} fight {opponent_creature.name}"
        if not game.may(
            controller.username, prompt, source=source.name, source_id=source_id_of(source)
        ):
            return
        _fight(game, source, opponent_creature)

    return effect


# --------------------------------------------------------------------------
# Dalkovan Encampment's own "whenever you attack this turn" delayed trigger
# --------------------------------------------------------------------------
#
# "{2}{W}, {T}: Whenever you attack this turn, create two 1/1 red Warrior
# creature tokens that are tapped and attacking. Sacrifice them at the
# beginning of the next end step." Activating this ability does not itself
# create any tokens - CR 603.7a: it creates a *delayed* triggered ability
# (`machines/delayed.py`) that watches for "you attack" (CR 508.3d, the same
# subjectless per-attacking-player event `machines/triggers.py` already reads
# for Guide of Souls) and fires **on every attack for the rest of this turn**,
# not once - CR 603.7b's "unless it has a stated duration, such as 'this
# turn'" is exactly Dalkovan's own words, so `remaining=None` plus
# `expires_end_of_turn=True` (swept by `DelayedTriggers.expire_this_turn` in
# `Game.cleanup_step`, CR 514.2) is what keeps it from also firing on the
# next turn's attack.
#
# Each firing creates its own two tokens tapped and attacking (CR 508.4,
# already proven directly in `tests/scenarios/test_tokens.py`), attacking
# whichever defender the activating player is already attacking - the
# tokens have no defender of their own printed anywhere, so this reads it
# off the controller's own currently-declared attack, CR 102.2's two-player
# default when more than one exists. Each token created this way gets its
# *own* one-shot delayed trigger reusing the existing `"sacrifice"` entry in
# `DELAYED_EFFECTS` (`_sacrifice_subject`) - the same "sacrifice this
# specific object at the next end step" idiom `return_subject_to_hand`'s
# siblings already use, not a new plural-subject field on `DelayedTrigger`.

_ATTACK_THIS_TURN_TAPPED_ATTACKING_TOKENS_RE = re.compile(
    rf"^whenever you attack this turn,\s*create (?P<n>{COUNT}) (?P<desc>.+?) tokens? "
    r"that are tapped and attacking\.\s*sacrifice them at the beginning of the "
    r"next end step\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20", before=["tokens._parse_created_trigger_ability_text"])
def _parse_attack_this_turn_create_tapped_attacking_tokens(text: str) -> AbilityEffect | None:
    match = _ATTACK_THIS_TURN_TAPPED_ATTACKING_TOKENS_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    count = parse_count(match.group("n"))
    words = match.group("desc").strip().split()
    definition = _parse_generic_token_descriptor(words, None)
    if count is None or definition is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=match.group(0),
                event=TriggerEvent.ATTACKS,
                controller=controller.username,
                source_id=source_id,
                source_name=source_name,
                # `only_when_active` only ever compares `event.player` against
                # this name (`DelayedTrigger.matches`) - CR 508.1a already
                # limits attack declaration to the active player, so reusing
                # it as "the event's own attacking player" rather than adding
                # a second, identical-in-effect field is exact, not a stretch.
                only_when_active=controller.username,
                subjectless_only=True,
                remaining=None,
                expires_end_of_turn=True,
                effect=CreateAttackingTokens(count=count, definition=definition),
            )
        )

    return effect


#: "create `<n>` `<desc>` token(s)[ with `<tail>`][ named `<name>`] that's/
#: are tapped and attacking." with **no** trailing sacrifice sentence -
#: `_ATTACK_TAPPED_ATTACKING_TOKENS_THEN_SACRIFICE_RE`'s own unconditional,
#: permanent sibling. Launch the Fleet's own granted line ("Whenever this
#: creature attacks, create a 1/1 white Soldier creature token that's
#: tapped and attacking.") is exactly this shape once the quoted ability
#: resolves as a triggered ability of its own (`machines/effects.py`'s
#: `_parse_plural_target_gain_quoted_ability_whole_text`): the token it
#: makes is a real, permanent Soldier, never sacrificed - `_MAY_COST_THEN_
#: ATTACKING_TOKEN_RE` below already makes the sacrifice *optional* for
#: Kavaron Harrier's/Gut, True-Soul Zealot's own "you may ..." wrapper
#: around this identical token shape, which is what proves the mechanism
#: (`create_tokens(..., tapped=True, attacking=...)`) already handles a
#: permanent tapped-and-attacking token correctly; this is the same call
#: with no cost-choice preamble and no forced sacrifice at all.
_TAPPED_ATTACKING_TOKENS_RE = re.compile(
    rf"^create (?P<n>{COUNT}) (?P<desc>.+?) \btokens?\b"
    r"(?:\s+with\s+(?P<tail>.+?))?"
    r"(?:\s+named (?P<name>.+?))?"
    r"\s+that(?:'s|’s| is| are) tapped and attacking\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s21", for_spell=False)
def _parse_tapped_attacking_tokens_whole_text(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_TAPPED_ATTACKING_TOKENS_RE`'s shape - see it for why no sacrifice
    trails it here. Read whole (`_strip_non_effect_preamble` first, the same
    way every other whole-text token shape in this section is) rather than
    through the ordinary per-clause dispatch, since a card carrying this
    sentence as its *only* one still reaches here with nothing before it to
    strip - the preamble strip is a no-op in that case, exactly as it is for
    `_parse_create_tapped_attacking_tokens_then_sacrifice`.
    """
    match = _TAPPED_ATTACKING_TOKENS_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None
    count = parse_count(match.group("n"))
    definition = _parse_generic_token_descriptor(
        match.group("desc").strip().split(), match.group("tail")
    )
    if definition is None:
        return None
    if name := match.group("name"):
        definition = definition.model_copy(update={"name": name.strip()})

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        create_tokens(
            game,
            definition,
            controller.username,
            count,
            tapped=True,
            attacking=_defender_of_controllers_attack(game, controller.username),
        )

    return effect


#: The Pact cycle's own shape: "At the beginning of your next upkeep, pay
#: {2}{G}{G}. If you don't, you lose the game." Two clauses `_prepare_effect_
#: clauses` cuts apart on the sentence's own period, read back together
#: because the second is the consequence CR 118.12's "unless" already gives an
#: unpaid cost, not an independent instruction.
_PAY_COST_RE = re.compile(r"^pay (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
_PAY_OR_LOSE_SECOND_RE = re.compile(r"^if you don'?t, you lose the game$", re.IGNORECASE)


def _parse_delayed_pay_or_lose_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_PAY_COST_RE`/`_PAY_OR_LOSE_SECOND_RE`'s clause pair - the Pact cycle's
    whole second paragraph, once `_prepare_effect_clauses` has cut it into two.
    """
    if index + 1 >= len(clauses):
        return None
    timing = _parse_delayed_timing_clause(clauses[index])
    if timing is None:
        return None
    step, verb = timing
    cost_match = _PAY_COST_RE.fullmatch(verb.strip())
    if cost_match is None:
        return None
    if _PAY_OR_LOSE_SECOND_RE.fullmatch(clauses[index + 1].strip().rstrip(".")) is None:
        return None
    cost = ManaCost.try_parse(cost_match.group("cost"))
    if cost is None:
        return None
    text = f"{clauses[index]}. {clauses[index + 1]}."

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=text,
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=step,
                controller=controller.username,
                source_id=source_id,
                source_name=source_name,
                # "your next upkeep" - only the player who owes the payment,
                # not whoever's upkeep happens to come first (`DelayedTrigger.
                # matches` compares this against `event.player`, the same way
                # Dalkovan Encampment's own "whenever you attack" already
                # scopes an attack-declaration event to one player).
                only_when_active=controller.username,
                effect=PayOrLoseTheGame(cost=cost),
            )
        )

    return 2, effect


#: "Attach target Equipment you control to up to one target creature you
#: control." - Iron Hills Stalwart's own ETB trigger, Blacksmith's Talent's
#: level-2 combat trigger (verified against the pool printing). CR 701.3a's
#: attach, with two independent targets (CR 601.2c/603.3d announce both):
#: the Equipment always required, the creature CR 115.6's own "up to one" -
#: choosing none simply leaves the Equipment where it is.
#:
#: CR 115.6's "up to one" sits on either half: Swordsman, Sharp Scoundrel's
#: "attach up to one target Equipment you control to target creature you
#: control" moves it to the Equipment, and Raubahn, Bull of Ala Mhigo's "...
#: to target attacking creature" names the creature by its combat status
#: instead of by controller - the same attach either way.
_ATTACH_TARGET_EQUIPMENT_UP_TO_ONE_CREATURE_RE = re.compile(
    r"^attach (?:up to one )?target equipment you control to (?:up to one )?target "
    r"(?:attacking creature|creature you control)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_attach_target_equipment_up_to_one_creature_clause(text: str) -> AbilityEffect | None:
    """`_ATTACH_TARGET_EQUIPMENT_UP_TO_ONE_CREATURE_RE`'s shape - see the
    banner above. The Equipment target is picked out of the resolved targets
    by its own subtype rather than by position, since `Game.resolve_targets`
    makes no promise about ordering two independently-typed targets in one
    sentence - the one target that carries "Equipment" is the Equipment
    half; whichever other one is left (there is at most one, CR 115.6) is
    the creature.
    """
    if _ATTACH_TARGET_EQUIPMENT_UP_TO_ONE_CREATURE_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        targets = [t for t in game.resolve_targets(ability) if isinstance(t, CardState)]
        legal = [t for t in targets if t.zone is Zone.BATTLEFIELD]
        equipment = next(
            (t for t in legal if "Equipment" in game.characteristics_of(t).subtypes), None
        )
        if equipment is None:
            return
        creature = next((t for t in legal if t.id != equipment.id), None)
        if creature is None:
            return
        attach_permanent(game, equipment, creature)

    return effect


#: "Attach any number of target Equipment you control to target creature you
#: control." - Thorin, Mountain-king's own ETB trigger. "... to it." -
#: Super-Soldier Serum's own attack/block trigger, "it" being CR 301.5a's/
#: 303.4b's "enchanted creature" (the ability's own source's attached-to
#: object, `_attached_object`), not a fresh target - CR 115.4's "any number
#: of" still only counts the Equipment half either way.
_ATTACH_ANY_NUMBER_EQUIPMENT_RE = re.compile(
    r"^attach any number of target equipment you control to "
    r"(?P<destination>target creature you control|it)\.?"
    r"(?P<reflexive> when one or more equipment become attached to (?:that|this) "
    r"creature this way, that creature deals damage equal to its power to "
    r"up to one target creature\.?)?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_attach_any_number_equipment_clause(text: str) -> AbilityEffect | None:
    """`_ATTACH_ANY_NUMBER_EQUIPMENT_RE`'s shape - see the banner above.

    The creature target is picked out the same subtype-agnostic way the
    "up to one" sibling above does (the one resolved target that is *not*
    Equipment); every other resolved target is one of the "any number of"
    Equipment (CR 115.4), each attached in turn. The optional trailing
    reflexive sentence - Thorin, Mountain-king's own - fires once, CR 603.12,
    only if at least one Equipment actually became attached this way, naming
    the creature as `ReflexiveDamageEqualToSubjectPowerConsequence`'s own
    subject.
    """
    match = _ATTACH_ANY_NUMBER_EQUIPMENT_RE.fullmatch(text.strip())
    if match is None:
        return None
    has_reflexive_damage = match.group("reflexive") is not None
    to_attached_object = match.group("destination").lower() == "it"

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        targets = [t for t in game.resolve_targets(ability) if isinstance(t, CardState)]
        equipment_pieces = [t for t in targets if t.zone is Zone.BATTLEFIELD]
        if to_attached_object:
            creature = _attached_object(game, ability)
        else:
            creature = next(
                (
                    t
                    for t in equipment_pieces
                    if "Equipment" not in game.characteristics_of(t).subtypes
                ),
                None,
            )
            equipment_pieces = [t for t in equipment_pieces if t is not creature]
        if creature is None:
            return
        attached_any = False
        for equipment in equipment_pieces:
            if attach_permanent(game, equipment, creature):
                attached_any = True
        if not attached_any or not has_reflexive_damage:
            return
        reflexive_text = (
            "When one or more Equipment become attached to that creature this way, "
            "that creature deals damage equal to its power to up to one target creature."
        )
        game.create_reflexive_trigger(
            text=reflexive_text,
            controller=ability.controller,
            source_id=ability.source_id,
            source_name=ability.source_name,
            subject_id=creature.id,
            callback=ReflexiveDamageEqualToSubjectPowerConsequence(),
        )

    return effect


#: "If this spell's <keyword> cost was paid, <consequence>." - a resolution-
#: time condition on the spell's own announcement naming the alternative-cost
#: keyword it was cast with (Morsel Theft's prowl, CR 702.76a). Read off the
#: `CastRecord`: the keyword used *and* its cost paid, the same pair CR
#: 702.185a's warp reads, since a keyword option that pays the mana cost
#: records the keyword without its cost. "Additional" is
#: `_IF_ADDITIONAL_COST_PAID_RE`'s, which names no keyword.
_IF_KEYWORD_COST_PAID_RE = re.compile(
    r"^if this spell'?s (?!additional\b)(?P<keyword>[a-z]+) cost was paid, (?P<rest>.+)$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_if_keyword_cost_paid_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_IF_KEYWORD_COST_PAID_RE`'s shape. Spell-only, like
    `_parse_if_additional_cost_paid_clause`: an ability has no `CastRecord`."""
    if not for_spell:
        return None
    match = _IF_KEYWORD_COST_PAID_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    keyword = match.group("keyword")
    rest = match.group("rest").strip()
    clause_effect = parse_clause_effect(rest) or parse_clause_effect(f"you {rest}")
    if clause_effect is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if (
            game.was_cast_with(stack_object, keyword)
            and game.cast_record(stack_object).keyword_cost_paid
        ):
            player = game.controller_of(stack_object)
            clause_effect(game, player, stack_object.name, source_id_of(stack_object))  # type: ignore[union-attr]

    return effect


#: "That land doesn't untap during its controller's next untap step."
#: (Vorinclex, Voice of Hunger's own "Whenever an opponent taps a land for
#: mana, ..."). "That `<noun>`" is CR 607.1's own anaphora back to whatever
#: the trigger's own condition just named - here `TriggerEvent.
#: TAPPED_FOR_MANA`'s own subject (`GameEvent.subject_id`, CR 106.12a) -
#: never a target: there is no "target" word in the sentence, and CR 601.2c
#: is not asked. The noun itself is not revalidated against the condition's
#: own type word; whatever `intervening_if_holds`'s `TAPPED_FOR_MANA` branch
#: already matched is what `event.subject_id` names.
_THAT_PERMANENT_NO_UNTAP_RE = re.compile(
    r"^that [a-z]+ doesn'?t untap during its controller'?s next untap step\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_that_permanent_no_untap_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_THAT_PERMANENT_NO_UNTAP_RE`'s shape. Ability-only, like `_parse_
    they_gain_or_lose_life_clause`: a spell has no `ability.event` to read
    "that `<noun>`" against.

    Reuses `CardState.exerted`/`.untap` (CR 701.43a-b), the same primitive
    `_parse_tap_target_then_no_untap_clause` already gives Tamiyo, Compleated
    Sage's targeted "It doesn't untap ..." - here imposed on the trigger's
    own anaphoric subject instead of a target.
    """
    if for_spell:
        return None
    if _THAT_PERMANENT_NO_UNTAP_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.subject_id is None:
            return
        permanent = game.find_by_id(event.subject_id)
        if permanent is not None and permanent.zone is Zone.BATTLEFIELD:
            permanent.exerted = True

    return effect


#: "It gains rebound." - Ojer Pakpatiq, Deepest Epoch's own "Whenever you
#: cast an instant spell from your hand, it gains rebound." CR 702.88a's
#: rebound is normally printed on the spell itself; here it is granted for
#: this one cast by a different card entirely, which `CardState.
#: granted_rebound` (and `machines.keywords.has_rebound_now`, read wherever
#: `has_rebound` alone used to be asked about a spell on the stack) exists
#: for. "It" is CR 607.1 anaphora back to the very spell whose casting made
#: this ability trigger - `ability.event.subject_id` - the same referent
#: `_parse_copy_that_spell_clause`/`_parse_counter_that_spell_clause` already
#: read "that spell" against.
_IT_GAINS_REBOUND_RE = re.compile(r"^it gains rebound$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_it_gains_rebound_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_IT_GAINS_REBOUND_RE`'s shape. Ability-only: a spell has no
    `ability.event` to read "it" against."""
    if for_spell:
        return None
    if not _IT_GAINS_REBOUND_RE.fullmatch(clause.strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if spell is not None and spell in game.stack:
            spell.granted_rebound = True

    return effect


#: Converge (CR 207.2c), an enters-with replacement created by a cast
#: trigger: Wildgrowth Archaic's own "Whenever you cast a creature spell,
#: that creature enters with X additional +1/+1 counters on it, where X is
#: the number of colors of mana spent to cast it." "That creature" is CR
#: 607.1's anaphora back to the very spell whose casting made this ability
#: trigger - `ability.event.subject_id`, the identical referent `_parse_it_
#: gains_rebound_clause` just above already reads "it" against - not the
#: source (Wildgrowth Archaic itself). Generalised over the printed counter
#: kind, so a future card sharing this exact template with a different
#: counter is covered for free.
_GRANT_ENTERS_WITH_COLORS_SPENT_COUNTERS_RE = re.compile(
    r"^that creature enters with x additional (?P<kind>[\w+/-]+) counters? on it,\s*"
    r"where x is the number of colors of mana spent to cast it\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_grant_enters_with_colors_spent_counters_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_GRANT_ENTERS_WITH_COLORS_SPENT_COUNTERS_RE`'s shape. Ability-only: a
    spell has no `ability.event` to read "that creature" against.

    The amount is resolved *now*, at the trigger's own resolution, off the
    still-on-stack creature spell's own `CastRecord` (`machines/converge.
    colors_of_mana_spent`) - the trigger goes on the stack above the spell
    that caused it (CR 603.3b) and so resolves first, while that spell is
    still there to read. The resolved number is then written as a plain,
    literal "This creature enters with N `<kind>` counters on it." onto the
    entering object's own `CardState.granted_ability_texts` (CR 113.10a),
    which `machines/replacement._self_enters_modifiers` reads as an
    independent `ENTERS_WITH` replacement effect once that creature spell
    itself resolves - see that function's own docstring for why the grant
    survives the stack-to-battlefield move. Written as its own counter grant
    rather than folded into any `ENTERS_WITH` line the creature already
    prints of its own: CR 616.1c lets its controller apply as many
    replacement effects, in any order, as apply, so the two simply stack.
    """
    if for_spell:
        return None
    match = _GRANT_ENTERS_WITH_COLORS_SPENT_COUNTERS_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    kind = match.group("kind")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if not isinstance(spell, CardState) or spell.zone is not Zone.STACK:
            return
        amount = colors_of_mana_spent(game, spell)
        if amount <= 0:
            return  # CR 107.1b: zero counters is nothing to grant.
        granted_text = f"This creature enters with {amount} {kind} counters on it."
        if granted_text not in spell.granted_ability_texts:
            spell.granted_ability_texts = (*spell.granted_ability_texts, granted_text)

    return effect


#: "This permanent/creature gains "`<ability>`" until end of turn." - Iron
#: Fist, Living Weapon's own "Iron Fist gains "{T}: Iron Fist deals damage
#: equal to his power to any other target" until end of turn." CR 201.5
#: self-reference, normalized to "this permanent"/"this creature" by the
#: time this is reached (`trigger_effect_for`'s own fallback). Built the same
#: way `_SELF_KEYWORD_GRANT_UNTIL_EOT_RE`'s plain keyword grant just above
#: is - a hand-built `ContinuousEffect` via `layers.grant_ability` and
#: `ContinuousEffects.add` - rather than through `create_continuous_effect_
#: of_ability`, which only ever reads a *keyword or plain static* sentence
#: off `LAYER_EFFECTS`'s own registry (`machines/layers.py`, locked to
#: another C02 task this round) and has no row for a quoted, self-granted
#: *activated* ability at all - a resolving trigger that named this shape
#: registered a `ContinuousEffect` whose own `ability_text` `effects_for`
#: never turned into anything, so the grant silently added nothing to the
#: computed board.
_SELF_GAINS_QUOTED_ABILITY_UNTIL_EOT_RE = re.compile(
    r"^this (?:permanent|creature|artifact) gains "
    r'["“](?P<ability>.+)["”] until end of turn\.?$',
    re.IGNORECASE | re.DOTALL,
)

#: Ms. Marvel, Kamala Khan's own leading-duration twin: "Until end of turn,
#: `<this>` gains "`<ability>`"." - the identical grant, with CR 611.2a's
#: duration printed before the sentence instead of after it.
_LEADING_UNTIL_EOT_SELF_GAINS_QUOTED_ABILITY_RE = re.compile(
    r"^until end of turn, this (?:permanent|creature|artifact) gains "
    r'["“](?P<ability>.+)["”]\.?$',
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s9")
def _parse_self_gains_quoted_ability_until_eot_clause(text: str) -> AbilityEffect | None:
    """`_SELF_GAINS_QUOTED_ABILITY_UNTIL_EOT_RE`'s shape, read whole - the
    quoted ability ends in a full stop of its own, which the clause splitter
    would otherwise cut at."""
    match = _SELF_GAINS_QUOTED_ABILITY_UNTIL_EOT_RE.fullmatch(
        text.strip()
    ) or _LEADING_UNTIL_EOT_SELF_GAINS_QUOTED_ABILITY_RE.fullmatch(text.strip())
    if match is None:
        return None
    granted_text = match.group("ability").strip()
    if not granted_text:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        ability = stack_object
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f'{source.name}: gains "{granted_text}" until end of turn',
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_only(source.id),
                modification=grant_ability(granted_text),
            ),
            game,
        )

    return effect


#: "This permanent/creature/artifact gets `<P>`/`<T>` until end of turn." as
#: ONE clause among several (Speedball, New Warrior's own "he gets +2/+2
#: until end of turn. You may choose new targets for that spell.") -
#: `_ability_effect_or_notice`'s own whole-text fallback to `create_
#: continuous_effect_of_ability` (Basking Rootwalla's shape) only ever runs
#: on an ability's *entire* text, so a card mixing a bare self-pump sentence
#: with another clause had no reader for this half at all; Daredevil, Man
#: Without Fear's own exile-trigger merge builds the identical continuous
#: effect inline for the same reason.
_SELF_PUMP_UNTIL_EOT_BARE_RE = re.compile(
    r"^this (?:permanent|creature|artifact) gets? "
    r"(?P<pt>[+-]\d+/[+-]\d+) until end of turn\.?$",
    re.IGNORECASE,
)


def _parse_bare_self_pump_until_eot_clause(text: str) -> AbilityEffect | None:
    """`_SELF_PUMP_UNTIL_EOT_BARE_RE`'s shape, or `None`."""
    match = _SELF_PUMP_UNTIL_EOT_BARE_RE.fullmatch(text.strip())
    if match is None:
        return None
    pump_text = f"this creature gets {match.group('pt')} until end of turn"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        ability = stack_object
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        continuous_effects(game).create(
            source,
            targets=[source],
            context=layer_context_for(game, game.controller_of(ability)),
            ability_text=_as_sentence(pump_text),
            game=game,
        )

    return effect


#: "`<put or return one object onto the battlefield>`. `<It|That permanent>`
#: gains `<keywords and "quoted abilities">`." (Terminal Velocity, Can't Stay
#: Away) - the second sentence's "it" is the permanent the first sentence put
#: onto the battlefield (CR 608.2c, CR 400.7j), and the quoted abilities are
#: whole granted lines (CR 113.10), stored verbatim like every other grant of
#: `CardState.granted_ability_texts`. The quote is cut out before sentences are
#: split because its own full stop sits inside the closing quote.
_PUT_THEN_IT_GAINS_RE = re.compile(
    r'^(?P<first>[^"]+?\.)\s+(?:it|that (?:permanent|creature|artifact|card)) gains '
    r"(?P<grants>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)
_QUOTED_GRANT_RE = re.compile(r'"([^"]+)"')


def _split_put_then_it_gains_grants(raw: str) -> list[str] | None:
    """Each grant of "haste, "quoted," and "quoted."", keywords capitalised
    (and checked against `KNOWN_KEYWORDS`), quoted lines stripped of the comma
    their list position adds inside the quote; `None` if any piece is neither."""
    grants: list[str] = []
    rest = raw
    for quoted in _QUOTED_GRANT_RE.finditer(raw):
        line = quoted.group(1).strip().rstrip(",")
        if not line:
            return None
        grants.append(line)
        rest = rest.replace(quoted.group(0), "|", 1)
    keywords: list[str] = []
    for part in re.split(r"\s*(?:,|\band\b)\s*", rest):
        part = part.strip(" |")
        if part:
            if part.lower() not in KNOWN_KEYWORDS:
                return None
            keywords.append(part.capitalize())
    return [*keywords, *grants] or None


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_put_onto_battlefield_then_it_gains_clauses(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """`_PUT_THEN_IT_GAINS_RE`'s pair: the first sentence runs through the
    ordinary reader, and whatever permanents it brought onto the battlefield
    (read off the battlefield before and after, CR 400.7: each is a new
    object) gain the listed grants. A first sentence that put nothing (the
    "may" declined, no legal card) leaves nothing to gain them (CR 608.2c)."""
    lowered = text.lower()
    if '"' not in text or " gains " not in lowered or "battlefield" not in lowered:
        return None
    match = _PUT_THEN_IT_GAINS_RE.fullmatch(" ".join(_strip_non_effect_preamble(text).split()))
    if match is None:
        return None
    grants = _split_put_then_it_gains_grants(match.group("grants"))
    if grants is None or any(is_leave_exile_line(grant) for grant in grants):
        # The leave-the-battlefield replacement is a replacement effect, not a
        # granted line: `_parse_put_then_grant_then_delayed_whole_text` owns it.
        return None
    first = _parse_mixed_clause(match.group("first"), for_spell=for_spell)
    if first is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        before = {(state.id, state.zone_change_stamp) for state in game.battlefield}
        first(game, stack_object)
        for permanent in list(game.battlefield):
            if (permanent.id, permanent.zone_change_stamp) in before:
                continue
            for granted_text in grants:
                if granted_text.lower() in KNOWN_KEYWORDS:
                    # A keyword is a layer-6 grant (CR 613.1f) scoped to this
                    # object alone (CR 400.7).
                    store = continuous_effects(game)
                    store.add(
                        ContinuousEffect(
                            description=f"{permanent.name}: gains {granted_text}",
                            layer=Layer.ABILITY,
                            timestamp=store.tick(),
                            selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                            modification=grant_ability(granted_text),
                        ),
                        game,
                    )
                elif granted_text not in permanent.granted_ability_texts:
                    permanent.granted_ability_texts = (
                        *permanent.granted_ability_texts,
                        granted_text,
                    )

    return [effect]


#: "It gains "<ability>"." - Rivaz of the Claw's "Whenever you cast a Dragon
#: creature spell from your graveyard, it gains "When this creature dies,
#: exile it."" "It" is the spell whose casting triggered this, as
#: `_IT_GAINS_REBOUND_RE` reads it; the quoted ability is written onto that
#: spell the way CR 113.10's other "gains" grants are
#: (`CardState.granted_ability_texts`), and CR 400.7a carries it onto the
#: permanent the spell becomes. No duration is printed, so it lasts (CR
#: 611.2a) until the object is gone (`CardState.move_to`, CR 400.7).
_IT_GAINS_QUOTED_ABILITY_RE = re.compile(
    r'^(?:it|that spell) gains ["\u201c](?P<ability>.+)["\u201d]\.?$', re.IGNORECASE | re.DOTALL
)


@ABILITY_TEXT.rung("s9")
def _parse_it_gains_quoted_ability_clause(text: str) -> AbilityEffect | None:
    """`_IT_GAINS_QUOTED_ABILITY_RE`'s shape, read whole - the quoted ability
    ends in a full stop of its own, which the clause splitter would cut at."""
    match = _IT_GAINS_QUOTED_ABILITY_RE.fullmatch(text.strip())
    if match is None:
        return None
    granted_text = match.group("ability").strip()
    if not granted_text:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if not isinstance(spell, CardState) or spell.zone is not Zone.STACK:
            return
        if granted_text not in spell.granted_ability_texts:
            spell.granted_ability_texts = (*spell.granted_ability_texts, granted_text)

    return effect


#: "Target creature gets +2/+0 until end of turn for each card discarded
#: this way. Whenever that creature deals combat damage to a player this
#: turn, you draw a card." - Captain Howler, Sea Scourge's whole discard
#: trigger, read as one CR 608.2c instruction: the pump's magnitude is "for
#: each card discarded this way" (CR 607.1 anaphora back to this ability's
#: own `TriggerEvent.DISCARDS_A_CARD` event, `GameEvent.amount` - see
#: `Game.discard_cards`), and the second sentence creates a CR 603.7 delayed
#: triggered ability watching "that creature" (CR 603.7c's `subject_id`) for
#: the rest of the turn (`expires_end_of_turn=True`).
_PUMP_PER_DISCARD_THEN_DELAYED_DRAW_RE = re.compile(
    r"^target creature gets \+(?P<power>\d+)/\+(?P<toughness>\d+) until end of turn "
    r"for each card discarded this way\.\s*"
    r"whenever that creature deals combat damage to a player this turn, "
    r"you draw a card\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s35")
def _parse_pump_per_discard_then_delayed_draw_clause(text: str) -> AbilityEffect | None:
    """`_PUMP_PER_DISCARD_THEN_DELAYED_DRAW_RE`'s shape - Captain Howler,
    Sea Scourge's whole trigger (CR 119.3's pump has no such rule number of
    its own beyond CR 611.2's one-shot effect; CR 603.7 for the delayed half;
    CR 120.2a for "deals combat damage to a player"; CR 121.1 for the draw).
    """
    match = _PUMP_PER_DISCARD_THEN_DELAYED_DRAW_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood("target creature"):
        return None
    per_power = int(match.group("power"))
    per_toughness = int(match.group("toughness"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        discard_count = that_many(game, ability) or 0
        if discard_count <= 0:
            return
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        if not targets:
            return
        target = targets[0]
        magnitude = discard_count * per_power
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=(
                    f"{target.name} gets +{magnitude}/+{discard_count * per_toughness} "
                    "until end of turn"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_only(target.id),
                modification=modify_power_toughness(magnitude, discard_count * per_toughness),
            )
        )
        controller = game.controller_of(ability)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=(
                    "Whenever that creature deals combat damage to a player "
                    "this turn, you draw a card."
                ),
                controller=controller.username,
                source_id=ability.source_id,
                source_name=ability.source_name,
                event=TriggerEvent.DEALS_DAMAGE,
                subject_id=target.id,
                remaining=None,
                expires_end_of_turn=True,
                effect=CombatDamageToPlayerDraw(),
            )
        )

    return effect


#: "The next red or green creature spell you cast this turn can be cast
#: without paying its mana cost." (World War Hulk's chapter I) and "Artifact
#: spells you cast this turn cost {1} less to cast." (Armor Wars' chapter II;
#: Ballad of the Black Flag's "Historic spells ... {2} less") - this-turn
#: effects on spells not yet cast, recorded on `Game` (`machines/next_spell.
#: py`). The quality is the printed phrase, read by `spell_has_quality`.
_NEXT_SPELL_FREE_CAST_RE = re.compile(
    r"^the next (?P<quality>[^.]+?) spell you cast this turn can be cast without paying"
    r" its mana cost\.?$",
    re.IGNORECASE,
)
_SPELLS_COST_LESS_THIS_TURN_RE = re.compile(
    r"^(?P<quality>[^.]+?) spells you cast this turn cost \{(?P<n>\d+)\} less to cast\.?$",
    re.IGNORECASE,
)
#: "The next noncreature spell you cast this turn has affinity for
#: artifacts." (Don & Raph, Hard Science, CR 702.41a) and "The next spell you
#: cast this turn has improvise." (Archway of Innovation, CR 702.126a) - a
#: cost keyword for the next such spell (`next_spell.NextSpellKeywordGrant`),
#: the keyword phrase read by `spell_grants`'s own reader. Trailing reminder
#: text is stripped before the match.
_NEXT_SPELL_HAS_KEYWORD_RE = re.compile(
    r"^the next (?:(?P<quality>[^.]+?) )?spell you cast this turn has (?P<keyword>[^.(]+?)\.?$",
    re.IGNORECASE,
)


def _parse_next_spell_has_keyword(text: str) -> TargetedClause | None:
    """`_NEXT_SPELL_HAS_KEYWORD_RE`, for the resolving object's controller,
    this turn - or None when the quality or the keyword is not one this
    reads (`next_spell.NEXT_SPELL_KEYWORDS`)."""
    from ..next_spell import NEXT_SPELL_KEYWORDS, NextSpellKeywordGrant, spell_quality_is_readable
    from ..spell_grants import _keyword_line

    stripped = re.sub(r"\s*\([^()]*\)\s*$", "", text).strip()
    match = _NEXT_SPELL_HAS_KEYWORD_RE.fullmatch(stripped)
    if match is None:
        return None
    quality = (match.group("quality") or "").strip()
    if quality and not spell_quality_is_readable(quality):
        return None
    read = _keyword_line(match.group("keyword"), NEXT_SPELL_KEYWORDS)
    if read is None:
        return None
    keyword, line = read

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        game.next_spell_keyword_grants = [
            *game.next_spell_keyword_grants,
            NextSpellKeywordGrant(
                controller=game.controller_of(stack_object).username,
                source_name=source_name,
                quality=quality,
                keyword=keyword,
                line=line,
                turn=game.turn.turns_taken if game.turn is not None else 0,
            ),
        ]

    return effect


@MIXED_CLAUSE.rung("s1", for_spell=FORWARD)
def _parse_this_turn_spell_grant_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_NEXT_SPELL_FREE_CAST_RE` (CR 118.9) or `_SPELLS_COST_LESS_THIS_TURN_
    RE` (CR 601.2f), for the resolving object's controller, this turn."""
    from ..next_spell import (
        NextSpellFreeCastGrant,
        SpellCostReductionGrant,
        spell_quality_is_readable,
    )

    text = " ".join(clause.strip().split())
    keyword_grant = _parse_next_spell_has_keyword(text)
    if keyword_grant is not None:
        return keyword_grant
    free = _NEXT_SPELL_FREE_CAST_RE.fullmatch(text)
    cheaper = _SPELLS_COST_LESS_THIS_TURN_RE.fullmatch(text)
    matched = free or cheaper
    if matched is None or not spell_quality_is_readable(matched.group("quality")):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        turn = game.turn.turns_taken if game.turn is not None else 0
        if free is not None:
            game.next_spell_free_cast_grants = [
                *game.next_spell_free_cast_grants,
                NextSpellFreeCastGrant(
                    controller=controller,
                    source_name=source_name,
                    quality=free.group("quality").strip(),
                    turn=turn,
                ),
            ]
        elif cheaper is not None:
            game.spell_cost_reduction_grants = [
                *game.spell_cost_reduction_grants,
                SpellCostReductionGrant(
                    controller=controller,
                    source_name=source_name,
                    quality=cheaper.group("quality").strip(),
                    amount=int(cheaper.group("n")),
                    turn=turn,
                ),
            ]

    return effect


#: Null Summoner's own second, entirely separate ability: "Threshold — As
#: long as there are seven or more cards in your graveyard, you may cast the
#: exiled card, and mana of any type can be spent to cast that spell." CR
#: 604.1: a static ability "written as a statement", true whenever its
#: condition holds - not a clause of the triggered ability that did the
#: exiling (CR 607.2h: two abilities can share one printed paragraph, or here
#: one printed card, while staying distinct). `.search` rather than
#: `.fullmatch`/an anchored `^`: an ability-word prefix ("Threshold — ") is
#: still attached to `BaseAbility.text` when the underlying line was matched
#: as a bare `StaticAbility` rather than split off by `_parse_activated`, so
#: this reads for the sentence wherever it starts in the line instead of
#: assuming any one prefix.
_CAST_EXILED_CARD_STATIC_RE = re.compile(
    r"as long as (?P<condition>.+?), you may cast the exiled cards?"
    r"(?P<any_type_mana>, and mana of any type can be spent to cast (?:it|that spell|them))?"
    r"\.?$",
    re.IGNORECASE,
)


def _grant_cast_exiled_card_permission_from_sibling_static(
    game: "Game", stack_object: "StackObject", card: CardState
) -> None:
    """Grant CR 601.3's permission to cast `card` (just exiled by
    `stack_object`'s own resolving ability) if the permanent that ability
    belongs to also prints a separate "As long as <condition>, you may cast
    the exiled card[, and mana of any type can be spent to cast that
    spell]." static ability - Null Summoner's own Threshold line.

    A no-op for every other card sharing this exiling machinery (Thoughtseize,
    Grief, Thought-Knot Seer, ...), none of which print that second sentence
    at all: the scan finds nothing and grants nothing, so nothing about their
    own behaviour changes.

    `condition`/`any_type_mana` are carried straight onto the grant
    (`PlayPermission.condition`/`.any_type_mana`) rather than resolved here,
    so the permission's usability is re-checked live every time it is asked
    about (`PlayPermission.why_not`, via `Game.condition_holds`) instead of
    being fixed at the moment of exile - a graveyard that later drops below
    Threshold makes the grant unusable again without it ever being revoked.
    """
    source_id = getattr(stack_object, "source_id", None)
    found = game.find_by_id(source_id) if source_id is not None else None
    if not isinstance(found, CardState):
        return
    controller = game.controller_of(stack_object).username
    for line in parse_abilities(found.card):
        if line.kind is not AbilityKind.STATIC:
            continue
        match = _CAST_EXILED_CARD_STATIC_RE.search((line.text or "").strip())
        if match is None:
            continue
        game.grant_play_permission(
            card,
            controller,
            action=PlayAction.CAST,
            source_name=found.name,
            rule="CR 601.3",
            zone=card.zone,
            until_end_of_turn=False,
            any_type_mana=bool(match.group("any_type_mana")),
            condition=match.group("condition").strip(),
            # CR 113.6 / CR 607.2a: the static ability functions only while its
            # own source is on the battlefield, and the card is linked to the
            # ability that exiled it - keyed by that one object, never its name.
            while_controlling=once_per_turn_key(found),
        )


#: CR 725.1 - "Target player becomes the monarch." (Denethor, Stone Seer) /
#: "target opponent becomes the monarch." (M'Baku, Jabari Chieftain, not in
#: this pool) - the same "target player"/"target opponent" phrase pair
#: `_TARGET_PLAYER_DRAWS_RE`'s own neighbours already read, one CR 725.1 verb
#: in place of theirs.
_TARGET_PLAYER_BECOMES_MONARCH_RE = re.compile(
    r"^(?P<phrase>target player|target opponent) becomes the monarch$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_target_player_becomes_monarch_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TARGET_PLAYER_BECOMES_MONARCH_RE`'s shape, or `None` if this is not
    it."""
    match = _TARGET_PLAYER_BECOMES_MONARCH_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), allow_player_targets=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, Player):
                game.become_monarch(target.username)

    return effect


def _targeted_layer_consequence(text: str) -> TargetedClause | None:
    """A one-shot continuous effect (CR 611.2) on the resolving object's
    targets - "target creature gets -3/-3 until end of turn" - as a clause of
    its own, read from `text` alone rather than from the whole printed
    ability the way `create_continuous_effect(_of_ability)` reads it, so it
    can sit behind a CR 118.12 "If you do". `None` unless `text` is a layer
    effect `machines/layers.py` reads and it names a target."""
    sentence = _as_sentence(text)
    if not _is_layer_effect_text(sentence) or parsed_layer_effects(sentence) is None:
        return None
    profile = profile_for_text(sentence)
    if not (profile.understood and profile.requirements):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        if source is None:
            return
        targets = game.resolve_card_targets(stack_object)
        if not targets:
            return
        continuous_effects(game).create(
            source,
            targets=targets,
            context=layer_context_for(game, game.controller_of(stack_object)),
            ability_text=sentence,
            game=game,
        )

    return effect


#: "Until end of turn, creatures you control gain "{1}: This creature fights
#: target creature you don't control." Exile this Saga, then return it to
#: the battlefield (front face up)." (Vorinclex // The Grand Evolution's own
#: Saga chapter III) - two CR 608.2c instructions read as one whole-text
#: match, the same reason `_CREATE_TOKEN_COPIES_EXCEPT_RE`'s own quoted
#: ability reads whole: the quoted ability ends in a full stop of its own
#: ("... you don't control.""), which `split_effect_clauses` would cut the
#: paragraph at, leaving neither half a readable clause.
#:
#: The grant is CR 613.1f's layer 6 addition to a *group* - `creatures you
#: control`, a `machines/layers.Selector` (`creatures_controlled_by`), not a
#: target or the ability's own source - built by hand the same way `_parse_
#: pump_and_becomes_chosen_color_clause`/`_parse_protection_from_chosen_
#: color_clause` already build a `ContinuousEffect` directly rather than
#: routing back through `parsed_layer_effects`'s single-subject text reader,
#: which has no group selector shape to offer this. The ability text itself
#: is read generically (whatever is quoted), not pinned to this one fight
#: ability, so a future card granting a different quoted ability the same
#: way reads here too.
#:
#: "(front face up)" never reaches this regex at all: `machines/abilities.
#: _strip_reminder` (CR 207.2a) removes every parenthetical before any
#: effect text is parsed, and confirmed by `parse_abilities` in this
#: session, so this pattern's own tail is the plain "return it to the
#: battlefield[, optionally under its owner's/your control]" every other
#: "exile self, then return" shape already reads. That is also the
#: rules-correct reading, not merely what the parser happens to see: CR
#: 712.8a - "While a double-faced card is ... in a zone other than the
#: battlefield or stack, it has only the characteristics of its front face"
#: - means an object with no "transformed" instruction already re-enters
#: front-face-up by default, exactly what the (reminder) parenthetical
#: restates. No "under its owner's control" clause is printed at all -
#: unlike `_EXILE_SELF_THEN_RETURN_RE`, which requires one - so the returned
#: permanent's controller is read off the exiled object's own `owner`, the
#: same fallback `_parse_exile_self_then_return_clause` already uses when
#: nothing overrides it.
_GRANT_QUOTED_ABILITY_THEN_RETURN_FRONT_FACE_RE = re.compile(
    r"^until end of turn, creatures you control gain "
    r"[\"“](?P<ability>.+?)[\"”]\s*"
    r"exile (?P<name>this [a-z]+|[^,]+), then return (?:it|him|her|them) "
    r"to the battlefield(?: under (?:its owner'?s|your) control)?\s*\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_grant_quoted_ability_then_return_front_face_whole_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_GRANT_QUOTED_ABILITY_THEN_RETURN_FRONT_FACE_RE`'s shape."""
    whole = _strip_non_effect_preamble(text).strip()
    match = _GRANT_QUOTED_ABILITY_THEN_RETURN_FRONT_FACE_RE.fullmatch(whole)
    if match is None:
        return None
    ability_text = match.group("ability").strip()
    if not ability_text:
        return None
    name_text = match.group("name").strip()
    named = None if name_text.lower().startswith("this ") else name_text

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if named is not None and named.lower() not in (source.name or "").lower():
            return
        controller = game.controller_of(ability).username
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{source.name}: creatures you control gain {ability_text!r}",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=creatures_controlled_by(controller),
                modification=grant_ability(ability_text),
            )
        )
        exiled = game.exile_permanent(source)
        if exiled.zone is not Zone.EXILE:
            return  # CR 111.8: a token refused the move; nothing to return.
        owner = exiled.owner or controller
        game.put_onto_battlefield(exiled, owner, transformed=False)

    return effect


@MIXED_CLAUSE.rung("s11", for_spell=FORWARD)
def _parse_mass_pump_group_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """A CR 611.2 mass pump/keyword-grant clause ("creatures you control
    gain <keyword(s)>[ and get +N/+N] until end of turn") as *one* clause of
    a multi-clause effect, not only as the whole effect text.

    `_mass_pump_ability_effect`/`_mass_pump_spell_effect` already read this
    shape, but only against the *whole*, unsplit effect text - which is why
    Ingris Stingerquill's own "Create a 2/2 ... token named Cadet. Then
    creatures you control gain haste until end of turn." used to lose the
    second sentence entirely: `split_effect_clauses` cuts the two apart
    correctly (CR 608.2c's instruction order), but nothing in `_parse_mixed_
    clause`'s per-clause dispatch below tried this shape on the resulting
    piece, so a clause that could not be read as a targeted/token/search/
    player instruction fell all the way through as unreadable. Reusing the
    same two whole-text readers here, one clause at a time, is what lets a
    mass pump compose with whatever clause precedes or follows it.
    """
    if for_spell:
        spell_effect = _mass_pump_spell_effect(clause)
        if spell_effect is None:
            return None

        def spell_clause(game: "Game", stack_object: "StackObject") -> None:
            spell_effect(game, stack_object)  # type: ignore[arg-type]

        return spell_clause
    ability_effect = _mass_pump_ability_effect(clause)
    if ability_effect is None:
        return None

    def ability_clause(game: "Game", stack_object: "StackObject") -> None:
        ability_effect(game, stack_object)  # type: ignore[arg-type]

    return ability_clause


#: "`<target phrase>` gets +N/+N [and gains `<keywords>`] until end of
#: turn." where the target phrase carries a qualifier after its noun that
#: `machines/layers.py`'s narrow `_SUBJECT` never reads - Executioner's
#: Swing's "Target creature that dealt damage this turn gets -5/-5 ...",
#: Spire Mangler's "target creature you control with flying gets +2/+0
#: ...", Slimy Dualleech's "target creature you control with power 2 or less
#: gets +1/+0 and gains deathtouch ...". Who may be targeted is
#: `machines/targeting.py`'s business (`_targets_understood`, checked at
#: announcement, CR 601.2c); this only performs the pump (sublayer 7c, CR
#: 613.4c) and each keyword (layer 6, CR 613.1f) on every target still legal
#: as it resolves (CR 608.2b), each fixed to that object (CR 611.2c).
_TARGET_PHRASE_PUMP_RE = re.compile(
    r"^(?:until end of turn, )?(?P<phrase>(?:another |up to one )?target .+?) gets "
    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)"
    r"(?: and gains (?P<keywords>[a-z][a-z0-9 ,]*?))?(?: until end of turn)?"
    # Chemister's Trick: "... gets -2/-0 until end of turn and attacks this turn
    # if able." - CR 508.1d's requirement for the span the pump lasts.
    r"(?: and (?P<attacks>attacks (?:each combat|this turn) if able))?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s11", for_spell=FORWARD)
def _parse_target_phrase_pump_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_TARGET_PHRASE_PUMP_RE`'s shape, for a target phrase the layer
    parser's own subject grammar does not read (any phrase it does read stays
    with `create_continuous_effect`)."""
    text = " ".join(clause.strip().split())
    if " gets " not in text.lower() or "until end of turn" not in text.lower():
        return None
    match = _TARGET_PHRASE_PUMP_RE.fullmatch(text)
    if match is None:
        return None
    if parsed_layer_effects(text if text.endswith(".") else f"{text}.") is not None:
        return None
    phrase = match.group("phrase")
    if not _targets_understood(phrase, count_agnostic=True, battlefield_only=True):
        return None
    keywords: list[str] = []
    if match.group("keywords") is not None:
        validated = _split_and_validate_keywords(match.group("keywords"))
        if validated is None:
            return None
        keywords = validated
    if match.group("attacks") is not None:
        keywords = [*keywords, "This creature attacks each combat if able."]
    power, toughness = int(match.group("power")), int(match.group("toughness"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        store = continuous_effects(game)
        timestamp = store.tick()
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            selector = only_this_incarnation(target, target.zone_change_stamp)
            store.add(
                ContinuousEffect(
                    description=f"{source_name}: {target.name} gets {power:+d}/{toughness:+d}",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=selector,
                    modification=modify_power_toughness(power, toughness),
                )
            )
            for keyword in keywords:
                store.add(
                    ContinuousEffect(
                        description=f"{source_name}: {target.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=selector,
                        modification=grant_ability(keyword),
                    )
                )

    return effect


@ABILITY_TEXT.rung("s41", for_spell=False)
@SPELL_TEXT.rung("s25", for_spell=True)
def _parse_target_phrase_pump_whole_text(text: str, *, for_spell: bool) -> TargetedClause | None:
    """`_parse_target_phrase_pump_clause` over the whole effect text - the
    per-clause splitter cuts "gets +1/+0 and gains deathtouch" at its "and"
    before any clause reader sees it (Slimy Dualleech)."""
    whole = _strip_non_effect_preamble(text).strip()
    if "\n" in whole:
        return None
    return _parse_target_phrase_pump_clause(whole, for_spell=for_spell)


#: "Creatures target player controls get -1/-1 until end of turn." (Gnashing
#: of Teeth's second mode), "Creatures target opponent controls get -1/-1
#: until end of turn." (Wail of War, Neutralize the Guards) and the same
#: subject with a keyword grant ("... get +2/+0 and gain haste until end of
#: turn."). CR 611.2c: the creatures are the ones that player controls as the
#: effect begins, fixed then - one sublayer 7c modification (CR 613.4c) and
#: one layer 6 grant (CR 613.1f) each, ending at cleanup (CR 514.2).
_TARGET_PLAYER_CREATURES_PUMP_RE = re.compile(
    r"^(?P<leading>until end of turn, )?creatures (?P<targeted>target (?:player|opponent)) "
    r"controls "
    # ecl-T8: Sygg's Command's own "Creatures target player controls gain
    # lifelink until end of turn." - a bare keyword grant, no "get +N/+N" at
    # all, alongside the pump[-plus-keyword] shape this already read.
    r"(?:get (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)"
    r"(?: and gain (?P<pump_keywords>[a-z][a-z ,]*?))?"
    r"|gain (?P<bare_keywords>[a-z][a-z ,]*?))"
    r"(?P<trailing> until end of turn)?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s11", for_spell=FORWARD)
def _parse_target_player_creatures_pump_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TARGET_PLAYER_CREATURES_PUMP_RE`'s shape, on a spell or an ability."""
    match = _TARGET_PLAYER_CREATURES_PUMP_RE.fullmatch(" ".join(clause.strip().split()))
    if match is None:
        return None
    if bool(match.group("leading")) == bool(match.group("trailing")):
        return None
    if not _targets_understood(match.group("targeted"), allow_player_targets=True):
        return None
    keywords: list[str] = []
    keyword_text = match.group("pump_keywords") or match.group("bare_keywords")
    if keyword_text is not None:
        validated = _split_and_validate_keywords(keyword_text)
        if validated is None:
            return None
        keywords = validated
    has_pump = match.group("power") is not None
    power = int(match.group("power")) if has_pump else 0
    toughness = int(match.group("toughness")) if has_pump else 0

    def effect(game: "Game", stack_object: "StackObject") -> None:
        players = {
            target.username
            for target in game.resolve_targets(stack_object)
            if isinstance(target, Player)
        }
        if not players:
            return
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name  # type: ignore[union-attr]
        )
        board = game.computed_board()
        group = [
            permanent
            for permanent in game.battlefield
            if board.of(permanent).is_creature and board.of(permanent).controller in players
        ]
        store = continuous_effects(game)
        timestamp = store.tick()
        for creature in group:
            selector = only_this_incarnation(creature, creature.zone_change_stamp)
            if has_pump:
                pt_description = f"{source_name}: {creature.name} gets {power:+d}/{toughness:+d}"
                store.add(
                    ContinuousEffect(
                        description=pt_description,
                        layer=Layer.POWER_TOUGHNESS,
                        sublayer=Sublayer.MODIFY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=selector,
                        modification=modify_power_toughness(power, toughness),
                    ),
                    game,
                )
            for keyword in keywords:
                store.add(
                    ContinuousEffect(
                        description=f"{source_name}: {creature.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=selector,
                        modification=grant_ability(keyword),
                    ),
                    game,
                )

    return effect


#: A mass, one-shot "lose all abilities" (CR 613.1f, layer 6), optionally
#: with a base power/toughness it sets at the same time (CR 613.4b, sublayer
#: 7b) - Final Showdown's "All creatures lose all abilities until end of
#: turn." and Sudden Spoiling's "Until end of turn, creatures target player
#: controls lose all abilities and have base power and toughness 0/2." The
#: duration may be printed first or last, never both and never neither: a
#: bare "Creatures lose all abilities." is Dress Down's own static ability
#: (CR 611.3), read by `machines/layers.py`'s battlefield sweep, not a
#: resolution effect. The group subject is any `_mass_creature_group_
#: targets` reads, plus "creatures target player/opponent controls".
#:
#: Widened (ecl T5) to Curious Colossus's "each creature target opponent
#: controls loses all abilities, becomes a Coward in addition to its other
#: types, and has base power and toughness 1/1." - the singular "each
#: creature ... controls" subject, a layer 4 rider that only *adds* creature
#: types (CR 205.1b's "in addition to its other types", CR 613.1d), and no
#: duration at all: a targeted subject can never be a permanent's own static
#: ability (CR 115.1: targets are declared as a spell or ability is put on
#: the stack, which a static ability never is), so a durationless
#: targeted sentence is a resolution effect that lasts indefinitely (CR
#: 611.2a) rather than Dress Down's CR 611.3 static.
_MASS_LOSE_ALL_ABILITIES_RE = re.compile(
    r"^(?P<leading>until end of turn, )?"
    r"(?P<subject>all creatures|(?:other )?creatures (?:you control|your opponents control)"
    r"|creatures (?P<targeted>target (?:player|opponent)) controls"
    r"|each creature (?P<each_targeted>target (?:player|opponent)) controls)"
    r" loses? all abilities"
    r"(?:,? (?:and )?becomes? an? (?P<added>[A-Z][A-Za-z'-]*(?: [A-Z][A-Za-z'-]*)*)"
    r" in addition to (?:its|their) other types)?"
    r"(?:,? and (?:have|has) base power and toughness (?P<power>\d+)/(?P<toughness>\d+))?"
    r"(?P<trailing> until end of turn)?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s11", for_spell=FORWARD)
def _parse_mass_lose_all_abilities_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_MASS_LOSE_ALL_ABILITIES_RE`'s shape, on a spell or an ability.

    CR 611.2c: the set of creatures is fixed when the effect begins - read
    once, here, from the computed board, the same fixed-set-now convention
    `_run_mass_pump` keeps - so a creature that enters later keeps its
    abilities. Each creature gets its own `only_this_incarnation` effect
    (CR 400.7), timed to CR 514.2's cleanup (`Duration.UNTIL_END_OF_TURN`).
    """
    match = _MASS_LOSE_ALL_ABILITIES_RE.fullmatch(clause.strip())
    if match is None:
        return None
    subject = match.group("subject")
    targeted = match.group("targeted") or match.group("each_targeted")
    leading, trailing = bool(match.group("leading")), bool(match.group("trailing"))
    if leading and trailing:
        return None
    if not (leading or trailing) and targeted is None:
        # Dress Down's durationless "Creatures lose all abilities." is a
        # static ability (CR 611.3), never this resolution reader's.
        return None
    if targeted is not None and not _targets_understood(targeted, allow_player_targets=True):
        return None
    duration = Duration.UNTIL_END_OF_TURN if leading or trailing else Duration.INDEFINITE
    added = tuple((match.group("added") or "").split())
    power = int(match.group("power")) if match.group("power") is not None else None
    toughness = int(match.group("toughness")) if match.group("toughness") is not None else None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source = stack_object if for_spell else stack_object.source_or_last_known(game)  # type: ignore[union-attr]
        if not isinstance(source, CardState):
            return
        if targeted is not None:
            players = {
                target.username
                for target in game.resolve_targets(stack_object)
                if isinstance(target, Player)
            }
            board = game.computed_board()
            group = [
                permanent
                for permanent in game.battlefield
                if board.of(permanent).is_creature
                and game.controller_of(permanent).username in players
            ]
        else:
            group = _mass_creature_group_targets(game, controller, source.id, subject) or []
        if not group:
            return
        store = continuous_effects(game)
        timestamp = store.tick()
        for creature in group:
            selector = only_this_incarnation(creature, creature.zone_change_stamp)
            built = [
                ContinuousEffect(
                    description=f"{source.name}: {creature.name} loses all abilities",
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    duration=duration,
                    selector=selector,
                    modification=lose_all_abilities,
                )
            ]
            for subtype in added:
                # CR 205.1b: "in addition to its other types" keeps them all.
                built.append(
                    ContinuousEffect(
                        description=f"{source.name}: {creature.name} is also a {subtype}",
                        layer=Layer.TYPE,
                        timestamp=timestamp,
                        duration=duration,
                        selector=selector,
                        modification=add_subtype(subtype),
                    )
                )
            if power is not None and toughness is not None:
                built.append(
                    ContinuousEffect(
                        description=(
                            f"{source.name}: {creature.name} has base P/T {power}/{toughness}"
                        ),
                        layer=Layer.POWER_TOUGHNESS,
                        sublayer=Sublayer.SET,
                        timestamp=timestamp,
                        duration=duration,
                        selector=selector,
                        modification=set_power_toughness(power, toughness),
                    )
                )
            for continuous in built:
                if continuous.holds(game):
                    store.add(continuous)

    return effect


#: Veil of Summer's "Spells you control can't be countered this turn." and
#: Determined's "Other spells you control can't be countered this turn." -
#: CR 611.2c's second sentence: a continuous effect from a resolving spell
#: or ability that modifies no characteristic and changes no controller
#: "modifies the rules of the game, so it can affect objects that weren't
#: affected when that continuous effect began" - a spell `controller` casts
#: *later* this turn is covered exactly as one already on the stack.
#: Recorded on `Game.casting_rule_effects` (`create_spells_cant_be_
#: countered_grant`) and read back wherever CR 113.6g's "can't be
#: countered" is already enforced, `Game.counter`
#: (`machines.casting_restrictions.spell_protected_from_countering`).
#: "Other" (Determined's own word, not a CR 205.3m subtype) excludes the
#: resolving spell itself from the protection it grants.
_SPELLS_CANT_BE_COUNTERED_THIS_TURN_RE = re.compile(
    r"^(?P<other>other )?spells you control can'?t be countered this turn\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s11", for_spell=FORWARD)
def _parse_spells_cant_be_countered_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SPELLS_CANT_BE_COUNTERED_THIS_TURN_RE`'s shape."""
    match = _SPELLS_CANT_BE_COUNTERED_THIS_TURN_RE.fullmatch(clause.strip())
    if match is None:
        return None
    excludes_self = match.group("other") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from ..casting_restrictions import create_spells_cant_be_countered_grant

        controller = game.controller_of(stack_object)
        source_name = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        excluded_source_id = (
            stack_object.id if excludes_self and isinstance(stack_object, CardState) else None
        )
        game.casting_rule_effects.append(
            create_spells_cant_be_countered_grant(
                controller.username, source_name, excluded_source_id=excluded_source_id
            )
        )

    return effect


#: "You and `<group>` you control gain `<keyword(s)>` until end of turn" -
#: Veil of Summer's own third sentence, "You and permanents you control gain
#: hexproof from blue and from black until end of turn", once `split_effect_
#: clauses`'s own guard (`_PLAYER_GROUP_SUBJECT_AND_RE`) has already kept
#: this compound subject whole as one clause instead of cutting it at its
#: own "and". `predicate` is everything after "you control" verbatim
#: ("gain hexproof from blue and from black until end of turn"), shared by
#: both halves once each is given its own subject.
_YOU_AND_GROUP_SUBJECT_RE = re.compile(
    r"^you and (?P<group>permanents|creatures) you control (?P<predicate>gain .+)$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s11", for_spell=FORWARD)
def _parse_you_and_group_gain_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_YOU_AND_GROUP_SUBJECT_RE`'s shape: a CR 608.2c compound subject read
    as two independent instructions with the same predicate (CR 205.3m has
    no bearing here - "you" and "permanents"/"creatures" are two different
    kinds of thing, not one plural noun).

    The group half ("`<group>` you control `<predicate>`") is handed
    straight to the ordinary mass-grant reader, `_parse_mass_pump_group_
    clause` - the ability grant itself, CR 611.2c's fixed-now group of
    permanents, and the layer machinery that keeps `hexproof from
    [quality]` enforced at targeting time are all exactly what that reader
    (and `machines/layers.py`'s `_MASS_PUMP_UNTIL_EOT_RE`) already give a
    plain "creatures you control gain ..." clause; `None` here fails the
    *whole* compound clause the same way an unread group clause always
    would on its own.

    The player half ("You `<predicate>`") is handed to `parse_clause_
    effect` - the same reader `_PLAYER_GAINS_HEXPROOF_RE`/`_player_gains_
    hexproof_clause` already proved reads this identical narrowed sentence
    (`tests/scenarios/test_player_hexproof_shroud.py::test_the_clause_
    parser_reads_hexproof_from_two_qualities_on_you`) - so "You gain
    hexproof from blue and from black until end of turn" is granted for
    real through `Game.grant_player_hexproof`, the same call flow 2's own
    generic mechanism makes, reusing its permanent-side quality reader
    (`hexproof_qualities_in`) rather than a second one. A predicate that
    reader cannot understand (some future "You and creatures you control
    gain flying until end of turn" - a keyword a player has no meaning for)
    still falls back to `PlayerSubjectSplitNotice`, recorded rather than
    silently applied or silently dropped, exactly as before this task -
    the fail-open notice convention this file uses throughout stays in
    force for whatever this reader does not (yet) cover.
    """
    match = _YOU_AND_GROUP_SUBJECT_RE.fullmatch(clause.strip())
    if match is None:
        return None
    group = match.group("group").lower()
    predicate = match.group("predicate").strip()
    group_effect = _parse_mass_pump_group_clause(
        f"{group} you control {predicate}", for_spell=for_spell
    )
    if group_effect is None:
        return None
    player_text = f"You {predicate}"
    player_effect = parse_clause_effect(player_text)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        group_effect(game, stack_object)
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        source_name = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        if player_effect is not None:
            controller = (
                game.controller_of(stack_object)
                if isinstance(stack_object, CardState)
                else game.player(stack_object.controller)  # type: ignore[union-attr]
            )
            player_effect(game, controller, source_name, source_id_of(stack_object))
            return
        game.player_subject_split_notices.append(
            PlayerSubjectSplitNotice(
                source_id=source.id if source is not None else None,
                source_name=source_name,
                text=player_text,
            )
        )

    return effect


#: CR 722.3b's targeted twin of `_BECOMES_PREPARED_TARGET_RE`: "Target
#: creature becomes unprepared." (Biblioplex Tomekeeper's second mode).
#: `Game.become_unprepared` is already a no-op on a permanent that was never
#: prepared, so no filter is needed here.
_BECOMES_UNPREPARED_TARGET_RE = re.compile(
    r"^(?P<phrase>target .+?) becomes unprepared\.?$", re.IGNORECASE
)


def _parse_becomes_unprepared_target_clause(clause: str) -> TargetedClause | None:
    """`_BECOMES_UNPREPARED_TARGET_RE`'s shape, or `None`."""
    match = _BECOMES_UNPREPARED_TARGET_RE.fullmatch(clause.strip())
    if match is None or not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_card_targets(stack_object):
            if target.zone is Zone.BATTLEFIELD:
                game.become_unprepared(target)

    return effect


#: "`<targeted instruction>`. If you do, this `<noun>` gains "`<ability>`"." -
#: Thief of Existence's cast trigger, once `trigger_effect_for` has
#: normalized the printed name to "this permanent": the first sentence is
#: any targeted instruction `parse_mixed_effect` reads, and CR 118.12's "If
#: you do" is whether it actually moved one of its targets.
_TARGETED_THEN_SELF_GAINS_RE = re.compile(
    r'^(?P<first>[^"]+?\.)\s*if you do, this [a-z]+ gains "(?P<ability>[^"]+)"\.?$',
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s23")
def _parse_targeted_then_self_gains_clause(text: str) -> AbilityEffect | None:
    """`_TARGETED_THEN_SELF_GAINS_RE`'s shape.

    CR 113.10: the grant is an added ability, stored verbatim on
    `CardState.granted_ability_texts` the way `_parse_gains_ability_clause`
    stores "This Saga gains ..."; CR 400.7a carries it from a permanent
    spell on the stack to the permanent that spell becomes, so a cast
    trigger's grant to its own spell is had by the creature. The source must
    still be the same object that triggered (CR 400.7) - on the stack or the
    battlefield, with the stamp the ability recorded - so a spell countered
    in response gains nothing.

    "If you do" (CR 118.12) holds only when the first instruction moved at
    least one of its targets (its `zone_change_stamp` changed) - "up to one"
    with no target chosen, or a target that resisted the move, grants
    nothing. A wholly illegal target never reaches this effect at all (CR
    608.2b).
    """
    match = _TARGETED_THEN_SELF_GAINS_RE.fullmatch(text.strip())
    if match is None:
        return None
    first = parse_mixed_effect(match.group("first").strip())
    if first is None:
        return None
    granted_text = match.group("ability").strip()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        stamps = {target.id: target.zone_change_stamp for target in targets}
        first(game, ability)
        if not any(target.zone_change_stamp != stamps[target.id] for target in targets):
            return
        source = ability.source(game)
        if (
            source is None
            or source.zone not in (Zone.STACK, Zone.BATTLEFIELD)
            or source.zone_change_stamp != ability.source_stamp
        ):
            return
        if granted_text not in source.granted_ability_texts:
            source.granted_ability_texts = (*source.granted_ability_texts, granted_text)

    return effect


#: "If the gift was promised, players can't cast spells this turn." (Bilbo's
#: Gambit) - CR 611.2c's own rule-of-the-game restriction, gated on a
#: printed condition rather than the unconditional shape a `_parse_if_
#: condition_you_win_the_game_clause`-style trailing sentence already reads
#: for a different consequence. Kept generic over the condition (any shape
#: `Game.condition_holds` can read, not only "the gift was promised"), the
#: same posture `_parse_if_condition_you_win_the_game_clause` takes - a
#: future card gating "players can't cast spells this turn" on a different
#: printed condition reads for free.
_IF_CONDITION_PLAYERS_CANT_CAST_RE = re.compile(
    r"^if (?P<condition>[^,]+),\s*players can'?t cast spells this turn\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_if_condition_players_cant_cast_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_IF_CONDITION_PLAYERS_CANT_CAST_RE`'s shape - CR 611.2c: recorded on
    `Game.casting_rule_effects` since the spell or ability that made it is
    gone by the time anyone tries to cast, read back by `casting_restrictions.
    blanket_cant_cast_restriction`."""

    match = _IF_CONDITION_PLAYERS_CANT_CAST_RE.fullmatch(clause.strip())
    if match is None:
        return None
    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from ..casting_restrictions import create_players_cant_cast_restriction

        controller = game.controller_of(stack_object)
        source = stack_object.source(game) if is_ability(stack_object) else stack_object
        source_name = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        if game.condition_holds(controller.username, condition_text, source):
            game.casting_rule_effects.append(
                create_players_cant_cast_restriction(controller.username, source_name)
            )

    return effect


def _defender_of_controllers_attack(game: "Game", username: str) -> object | None:
    """Whichever player, planeswalker or battle `username` is already
    attacking (CR 508.4), or `None` if they are attacking nothing.

    Read off `Game.combat.attacks` rather than announced anywhere, for the
    reason the section banner above gives.
    """
    for attack in game.combat.attacks:
        attacker = game.find_by_id(attack.attacker_id)
        if attacker is not None and game.controller_of(attacker).username == username:
            return attack.defender
    return None


# --------------------------------------------------------------------------
# "Double the power of target creature you control until end of turn."
# --------------------------------------------------------------------------
#
# Mightform Harmonizer's own landfall trigger. CR 701.10b: "To double a
# creature's power, that creature gets +X/+0, where X is that creature's
# power as the spell or ability that doubles its power resolves." CR 701.10a
# adds that this is a continuous effect that *modifies* rather than sets, so
# it belongs in layer 7c (CR 613.4c) alongside every other +N/+N, and
# CR 701.10c handles a negative power by giving -X/-0 instead.

_DOUBLE_POWER_TARGET_RE = re.compile(
    r"^double the power of (?P<phrase>.*target .+?) until end of turn\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s32")
def _parse_double_power_target_clause(text: str) -> AbilityEffect | None:
    """`_DOUBLE_POWER_TARGET_RE`'s shape - Mightform Harmonizer.

    X is fixed when this resolves (CR 701.10b, CR 611.2c: the effect's own
    values are locked in as it is created), so the power is read once here
    through `Game.power_of` - the computed one (CR 613.4c), not the printed
    one - and the resulting modification never recomputes.

    `_targets_understood` is passed the whole target phrase including "up
    to"/"another" prefixes, as everywhere else in this file, and this clause
    carries its own duration so it is checked before the phrase reaches the
    shared helper (whose `_TRAILING_DURATION_RE` guard would otherwise refuse
    it outright).
    """
    match = _DOUBLE_POWER_TARGET_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=False):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        power = game.power_of(target)
        if power is None:
            return
        # CR 701.10c: a negative power is doubled by getting -X/-0, where X
        # is the difference between 0 and its power - which is the same
        # arithmetic as adding the power to itself, so one expression covers
        # both directions.
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{ability.source_name}: {target.name} gets +{power}/+0",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_only(target.id),
                modification=modify_power_toughness(power, 0),
            )
        )

    return effect


#: "Choose target creature you control. Until end of turn, double its power
#: and toughness and it gains trample." (World War Hulk's chapter III) and
#: "double its power and toughness until end of turn." (Grunn, the Lonely
#: King's attack trigger, "its" the source itself) - CR 701.10b's doubling of
#: both, with an optional keyword grant for the same duration. "its" is the
#: chosen target when a "Choose target ..." sentence precedes it, and the
#: ability's own source otherwise.
_DOUBLE_POWER_AND_TOUGHNESS_RE = re.compile(
    r"^(?:choose (?P<phrase>(?:up to one |one |a )?(?:other |another )?target creature"
    r"(?: you control)?)\.\s*)?(?P<lead>until end of turn, )?double its power and toughness"
    r"(?P<trail> until end of turn)?(?: and (?:it|that creature) gains? (?P<keywords>[^.]+?))?"
    r"\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s4")
def _parse_double_power_and_toughness_clause(text: str) -> AbilityEffect | None:
    """`_DOUBLE_POWER_AND_TOUGHNESS_RE`'s shape. CR 701.10a/b: the creature
    gets +X/+Y where X and Y are its power and toughness as this resolves - a
    layer 7c modification (CR 613.4c), fixed once created (CR 611.2c) - and a
    negative value doubles to its own negative (CR 701.10c), which the same
    arithmetic gives. A creature no longer on the battlefield gets nothing."""
    match = _DOUBLE_POWER_AND_TOUGHNESS_RE.fullmatch(" ".join(text.strip().split()))
    if match is None or not (match.group("lead") or match.group("trail")):
        return None
    phrase = match.group("phrase")
    if phrase is not None and not _targets_understood(phrase, count_agnostic=False):
        return None
    keywords: list[str] = []
    if match.group("keywords"):
        read = _split_and_validate_keywords(
            re.sub(r" until end of turn$", "", match.group("keywords").strip(), flags=re.I)
        )
        if read is None:
            return None
        keywords = read

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if phrase is not None:
            subjects = [
                target
                for target in game.resolve_targets(ability)
                if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
            ]
        else:
            source = ability.source(game)
            subjects = [source] if source is not None and source.zone is Zone.BATTLEFIELD else []
            if subjects and ability.source_stamp not in (None, subjects[0].zone_change_stamp):
                subjects = []  # CR 400.7: a new object, not the one that triggered
        store = continuous_effects(game)
        for subject in subjects:
            power, toughness = game.characteristics_of(subject).numeric_power_toughness
            timestamp = store.tick()
            store.add(
                ContinuousEffect(
                    description=(
                        f"{ability.source_name}: {subject.name} gets +{power}/+{toughness}"
                    ),
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=only_this_incarnation(subject, subject.zone_change_stamp),
                    modification=modify_power_toughness(power, toughness),
                ),
                game,
            )
            for keyword in keywords:
                store.add(
                    ContinuousEffect(
                        description=f"{ability.source_name}: {subject.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=only_this_incarnation(subject, subject.zone_change_stamp),
                        modification=grant_ability(keyword),
                    ),
                    game,
                )

    return effect


_PLURAL_GRANT_ANAPHORS = frozenset({"they", "those tokens", "those creatures"})

#: A sentence end, outside any quotation - the texts this reads carry none.
_SIMPLE_SENTENCE_SPLIT_RE = re.compile(r"(?<=\.)\s+(?=[A-Za-z])")

#: The dispatcher answers a composed head must never be built on: a notice
#: stand-in (the head itself fails closed) or a sentinel that re-reads the
#: card's whole oracle text rather than the head.
_NOT_A_HEAD_NAMES = frozenset(
    {
        "create_continuous_effect",
        "create_continuous_effect_of_ability",
        "resolve_modal_spell",
        "layer_effect_with_remainder_notice",
    }
)


def _is_readable_head(effect: object) -> bool:
    if effect is None:
        return False
    name = getattr(effect, "__name__", "")
    return not (name.endswith("_notice_only") or name in _NOT_A_HEAD_NAMES)


def _entered_since(game: "Game", before: set[tuple[UUID, UUID]]) -> list[CardState]:
    """Every object on the battlefield now that was not there, as that same
    object (CR 400.7), in `before`."""
    return [
        state for state in game.battlefield if (state.id, state.zone_change_stamp) not in before
    ]


def _grant_keywords_to(
    game: "Game",
    permanent: CardState,
    keywords: Sequence[str],
    duration: str | None,
    *,
    controller: str,
    source_name: str,
) -> None:
    """CR 613.1f's layer-6 grant of `keywords` to exactly this object
    (`only_this_incarnation`, CR 400.7), for as long as CR 611.2a's printed
    duration says - none printed is indefinite."""
    store = continuous_effects(game)
    if duration == "until end of turn":
        lasting, owner = Duration.UNTIL_END_OF_TURN, None
    elif duration == "until your next turn":
        lasting, owner = Duration.UNTIL_YOUR_NEXT_TURN, controller
    else:
        lasting, owner = Duration.INDEFINITE, None
    for keyword in keywords:
        store.add(
            ContinuousEffect(
                description=f"{source_name}: {permanent.name} gains {keyword.lower()}",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=lasting,
                until_next_turn_of=owner,
                selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                modification=grant_ability(keyword),
            )
        )


#: "equipped creature|enchanted creature `<gains/gain>` `<keywords>` until
#: end of turn." - Super Speed's own "When this Aura enters, enchanted
#: creature gains first strike until end of turn." CR 303.4b/303.4m's
#: "enchanted [object]"/CR 301.5a's "equipped creature" is the attached
#: permanent (`source.attached_to`), not a target the ability's own printed
#: text never names one of (CR 115.1 has nothing to check here) - the
#: identical anaphor `_UNTAP_TRIGGER_SUBJECT_RE` and this file's other
#: attachment readers already resolve off `CardState.attached_to`, applied
#: here to a one-shot keyword grant instead of an untap or a static line.
_ATTACHED_SUBJECT_GAINS_KEYWORDS_UNTIL_RE = re.compile(
    r"^(?:equipped creature|enchanted creature) gains? (?P<keywords>[a-z][a-z, ]*?) "
    r"until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s28")
def _parse_attached_subject_gains_keywords_until_clause(text: str) -> AbilityEffect | None:
    """`_ATTACHED_SUBJECT_GAINS_KEYWORDS_UNTIL_RE`'s shape - see the banner
    above. A permanent with nothing attached to it (an Aura/Equipment that
    somehow resolves this trigger unattached, or one already unattached by
    the time it does) grants nothing - CR 303.4b: there is no "enchanted
    creature"/"equipped creature" to name."""
    match = _ATTACHED_SUBJECT_GAINS_KEYWORDS_UNTIL_RE.fullmatch(text.strip())
    if match is None:
        return None
    keywords = split_and_validate_keywords(match.group("keywords"))
    if keywords is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.attached_to is None:
            return
        attached = game.find_by_id(source.attached_to)
        if attached is None or attached.zone is not Zone.BATTLEFIELD:
            return
        controller = game.controller_of(ability).username
        _grant_keywords_to(
            game,
            attached,
            list(keywords),
            "until end of turn",
            controller=controller,
            source_name=ability.source_name,
        )

    return effect


#: "Until end of turn, it gains haste and "Whenever this creature deals combat
#: damage to a player or battle, create a Treasure token."" - Furnace Reins'
#: third sentence, after "Gain control of target creature until end of turn.
#: Untap that creature." The duration-first twin of the anaphoric grant every
#: clause reader already reads with its duration printed last ("It gains
#: haste and "..." until end of turn."): CR 611.2a's "until end of turn" is
#: the same duration wherever it is printed. Each such sentence of the whole
#: text is rewritten to the trailing-duration order and the text dispatched
#: again (quoted abilities stashed first, so their own full stops never end
#: a sentence).
_LEADING_EOT_ANAPHOR_RE = re.compile(
    r"^until end of turn, (?P<rest>(?:it|that creature|those creatures|they) "
    r"(?:gains?|gets?|has|have) .+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s1", for_spell=False)
@SPELL_TEXT.rung("s1", for_spell=True)
def _parse_leading_duration_anaphor_whole_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_LEADING_EOT_ANAPHOR_RE` over every sentence after the first, then
    the rewritten text read by the ordinary dispatcher - or `None` when no
    sentence has the shape, or the rewritten text is not genuinely read."""
    if "until end of turn, " not in text.lower():
        return None
    quoted: list[str] = []

    def stash(match: re.Match[str]) -> str:
        quoted.append(match.group(0))
        return f"\x00{len(quoted) - 1}\x00"

    normalized = " ".join(_strip_non_effect_preamble(text).split())
    normalized = _QUOTED_ABILITY_RE.sub(stash, normalized)
    if '"' in normalized:
        return None
    sentences = [part for part in _SIMPLE_SENTENCE_SPLIT_RE.split(normalized) if part]
    if len(sentences) < 2:
        return None
    rewritten = False
    for index in range(1, len(sentences)):
        match = _LEADING_EOT_ANAPHOR_RE.fullmatch(sentences[index].strip())
        if match is None:
            continue
        rest = match.group("rest")
        sentences[index] = f"{rest[0].upper()}{rest[1:]} until end of turn."
        rewritten = True
    if not rewritten:
        return None
    restored = " ".join(
        sentence if sentence.rstrip().endswith((".", "\x00")) else f"{sentence}."
        for sentence in sentences
    )
    restored = re.sub(r"\x00(\d+)\x00", lambda m: quoted[int(m.group(1))], restored)
    effect = _spell_effect_or_notice(restored) if for_spell else _ability_effect_or_notice(restored)
    if not _is_readable_head(effect):
        return None
    return effect  # type: ignore[return-value]


#: "If it would leave the battlefield, exile it instead of putting it
#: anywhere else." as a sentence of its own after the clause that put the
#: object onto the battlefield - Whip of Erebos, Kheru Lich Lord, and CR
#: 702.84a's unearth. "It"/"that creature" is the object that clause put
#: there (CR 608.2c), so the replacement is bound to that one object.
_ANAPHOR_LEAVE_EXILE_RE = re.compile(
    r"^if (?:it|that creature|that card|that permanent|that token) would leave the battlefield, "
    r"exile (?:it|that creature|that card|that permanent|that token) "
    r"instead of putting it anywhere else$",
    re.IGNORECASE,
)

#: "<pronoun> gains "<quoted ability>"" - the grant sentence whose payload is
#: a quoted ability (Geth, Thane of Contracts). The quoted text is swapped for
#: a placeholder before the paragraph is split into sentences, so a period
#: inside the quote never ends the sentence.
_ANAPHOR_GAINS_QUOTED_RE = re.compile(
    r"^(?P<anaphor>it|that creature|that card|that permanent|that token) "
    r"(?:gains|has) \x00(?P<index>\d+)\x00$",
    re.IGNORECASE,
)

_QUOTED_ABILITY_RE = re.compile(r'"([^"]+)"')


@ABILITY_TEXT.rung("s41", for_spell=False)
@SPELL_TEXT.rung("s25", for_spell=True)
def _parse_put_then_grant_then_delayed_whole_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """The whole paragraph above as one CR 608.2c instruction, or `None`.

    At least one of the trailing sentences (the grant, the delayed clause, the
    leave-the-battlefield rider) must be there - an antecedent alone is
    somebody else's shape. They read in the order printed: grant, delayed
    clause, rider. The grant is either keywords or a quoted ability, and a
    quoted ability is read only when this engine performs it as a replacement
    (`is_leave_exile_line`) - any other quoted payload fails the paragraph
    closed. The antecedent is read by the ordinary dispatcher for its side
    (`_spell_effect_or_notice` / `_ability_effect_or_notice`) and must come
    back a real effect, never a notice stand-in: an antecedent this file
    cannot run fails the whole paragraph closed (CR 608.2c).

    A delayed clause whose pronoun is the ability's own source ("return this
    card from your graveyard ...", Prized Amalgam) needs no antecedent at
    all: the source is the referent.
    """
    quoted: list[str] = []

    def stash(match: re.Match[str]) -> str:
        quoted.append(match.group(1).strip())
        return f"\x00{len(quoted) - 1}\x00"

    normalized = " ".join(_strip_non_effect_preamble(text).split())
    if "“" in normalized or "”" in normalized:
        return None
    normalized = _QUOTED_ABILITY_RE.sub(stash, normalized)
    if '"' in normalized:
        return None
    sentences = [part for part in _SIMPLE_SENTENCE_SPLIT_RE.split(normalized) if part]
    if not sentences:
        return None
    leave_exile = False
    if sentences and _ANAPHOR_LEAVE_EXILE_RE.fullmatch(sentences[-1].rstrip(".")):
        leave_exile = True
        sentences.pop()
    delayed = parse_anaphoric_delayed_clause(sentences[-1]) if sentences else None
    delayed_text: str | None = None
    if delayed is not None:
        delayed_text = sentences.pop()
    grant_keywords: list[str] | None = None
    grant_duration: str | None = None
    grant_plural = False
    if sentences:
        quoted_match = _ANAPHOR_GAINS_QUOTED_RE.fullmatch(sentences[-1].rstrip("."))
        if quoted_match is not None:
            line = quoted[int(quoted_match.group("index"))]
            if not is_leave_exile_line(line):
                return None
            grant_keywords = [line]
            sentences.pop()
        else:
            grant_match = _ANAPHOR_GAINS_KEYWORDS_RE.fullmatch(sentences[-1].rstrip("."))
            if grant_match is not None:
                keywords = split_and_validate_keywords(grant_match.group("keywords"))
                if keywords is None:
                    return None
                grant_keywords = list(keywords)
                grant_duration = (grant_match.group("duration") or "").lower() or None
                grant_plural = grant_match.group("anaphor").lower() in _PLURAL_GRANT_ANAPHORS
                sentences.pop()
    if delayed is None and grant_keywords is None and not leave_exile:
        return None
    if delayed is not None and delayed.self_referential:
        if for_spell or sentences or grant_keywords is not None or leave_exile:
            return None
        return _self_referential_delayed_effect(delayed_text or "")
    if not sentences:
        return None
    head_text = " ".join(sentences)
    if "\x00" in head_text:
        return None
    head = _spell_effect_or_notice(head_text) if for_spell else _ability_effect_or_notice(head_text)
    if not _is_readable_head(head):
        return None
    assert head is not None
    if delayed is not None and grant_keywords is not None and grant_plural != delayed.plural:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        if for_spell:
            assert isinstance(stack_object, CardState)
            source_id: UUID | None = stack_object.id
            source_name = stack_object.card.name
        else:
            assert isinstance(stack_object, AbilityOnStack)
            source_id, source_name = stack_object.source_id, stack_object.source_name
        before = {(state.id, state.zone_change_stamp) for state in game.battlefield}
        head(game, stack_object)
        entered = _entered_since(game, before)
        if not entered:
            return  # CR 101.3: nothing was produced for the pronoun to name.
        if grant_keywords is not None and (grant_plural or len(entered) == 1):
            for permanent in entered:
                _grant_keywords_to(
                    game,
                    permanent,
                    grant_keywords,
                    grant_duration,
                    controller=controller,
                    source_name=source_name,
                )
        if leave_exile and len(entered) == 1:
            permanent = entered[0]
            exile_instead_of_leaving(
                game,
                permanent,
                controller=controller,
                source_id=source_id,
                source_name=source_name,
            )
        if delayed is None:
            return
        triggers = delayed.triggers_for_all(
            entered,
            controller=controller,
            source_id=source_id,
            source_name=source_name,
            game=game,
        )
        for trigger in triggers or []:
            game.create_delayed_trigger(
                trigger.model_copy(update={"text": (delayed_text or trigger.text).strip()})
            )

    return effect


#: "<target> blocks <this object> this turn if able." - Sisters of Stone
#: Death, Tangle Angler, Matsu-Tribe Decoy, Lurking Arynx: a CR 509.1c
#: requirement on the target naming the ability's own source, lasting the
#: turn (CR 611.2a). The source's name has been read as "this creature"
#: by the time the clause gets here, like every other self-reference.
_TARGET_BLOCKS_SELF_IF_ABLE_RE = re.compile(
    r"^(?P<phrase>(?:up to one )?target (?:[a-z' ]+ )?creature(?: [a-z' ]+?)?) blocks "
    r"(?P<referent>this creature|this permanent|it) this (?:turn|combat) if able\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s11")
@SPELL_TEXT.rung("s10")
def _parse_target_blocks_self_if_able_clause(text: str) -> TargetedClause | None:
    """`_TARGET_BLOCKS_SELF_IF_ABLE_RE`'s shape, or `None`.

    The requirement is granted until end of turn as an ability line on the
    target (layer 6, CR 613.1f) - "This creature blocks <source name> each
    combat if able." - that `machines/combat.py`'s CR 509.1c reader counts,
    the block-side twin of `_parse_target_attacks_if_able_clause`. It names
    the source as it is now; a source that has already left the battlefield
    (CR 400.7) is a new object no attacker can be, so nothing is granted.
    """
    match = _TARGET_BLOCKS_SELF_IF_ABLE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if isinstance(stack_object, CardState):
            return
        source = (
            game.find_by_id(stack_object.source_id) if stack_object.source_id is not None else None
        )
        if (
            not isinstance(source, CardState)
            or source.zone is not Zone.BATTLEFIELD
            or (
                stack_object.source_stamp is not None
                and source.zone_change_stamp != stack_object.source_stamp
            )
        ):
            return
        controller = game.controller_of(stack_object).username
        # "it" is whatever the trigger event names: the creature that
        # attacked (Fighter Class: "Whenever a creature you control attacks,
        # ... blocks it this combat if able"), which is the source itself for
        # "Whenever this creature attacks" (Avalanche Tusker).
        attacker = source
        event = stack_object.event
        if match.group("referent").lower() == "it" and event is not None:
            named = game.find_by_id(event.subject_id) if event.subject_id is not None else None
            if isinstance(named, CardState):
                if named.zone is not Zone.BATTLEFIELD:
                    return
                attacker = named
        line = f"This creature blocks {attacker.name} each combat if able."
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                _grant_keywords_to(
                    game,
                    target,
                    [line],
                    "until end of turn",
                    controller=controller,
                    source_name=stack_object.source_name,
                )

    return effect


#: "[Until your next turn, ]<target> attacks [a player ](each combat|this
#: turn) if able[ this turn]." - Nahiri, the Unforgiving's +1 and Heckling
#: Fiends' activated ability: a CR 508.1d requirement put on a target by a
#: resolving ability, for CR 611.2a's printed duration.
_TARGET_ATTACKS_IF_ABLE_RE = re.compile(
    r"^(?:(?P<lead>until your next turn|until end of turn), )?"
    r"(?P<phrase>(?:up to one )?target creature(?: [a-z' ]+?)?) (?P<verb>attacks|blocks) "
    r"(?P<player>a player )?(?P<when>each combat|this turn) if able"
    r"(?: (?P<trail>this turn|until end of turn|until your next turn))?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s11")
@SPELL_TEXT.rung("s10")
def _parse_target_attacks_if_able_clause(text: str) -> TargetedClause | None:
    """`_TARGET_ATTACKS_IF_ABLE_RE`'s shape, or `None`.

    The requirement is granted as an ability line on the target (layer 6,
    CR 613.1f) that `machines/combat.py`'s CR 508.1d reader already counts -
    "This creature attacks each combat if able." or, for "attacks a player",
    "This creature attacks a player each combat if able.", which only an
    attack on a player obeys. "Attacks this turn if able" is the same
    requirement ending with the turn (CR 508.1d's last sentence reads a
    turn-long requirement at each declare-attackers step of that turn).
    """
    match = _TARGET_ATTACKS_IF_ABLE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    phrase = match.group("phrase")
    if not _targets_understood(phrase, count_agnostic=True):
        return None
    lead = (match.group("lead") or "").lower()
    trail = (match.group("trail") or "").lower()
    if lead and trail:
        return None
    this_turn = match.group("when").lower() == "this turn"
    duration_text = lead or trail or ("until end of turn" if this_turn else "")
    if duration_text == "this turn":
        duration_text = "until end of turn"
    if not duration_text:
        return None
    blocks = match.group("verb").lower() == "blocks"
    if blocks and match.group("player"):
        return None
    if blocks:
        line = "This creature blocks each combat if able."
    elif match.group("player"):
        line = "This creature attacks a player each combat if able."
    else:
        line = "This creature attacks each combat if able."

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                _grant_keywords_to(
                    game,
                    target,
                    [line],
                    duration_text,
                    controller=controller,
                    source_name=source_name,
                )

    return effect


#: "{1}{R}: Enchanted creature attacks this turn if able." - Nettling Curse:
#: `_TARGET_ATTACKS_IF_ABLE_RE`'s requirement on the permanent this Aura or
#: Equipment is attached to (CR 303.4b, CR 301.5a) instead of on a target.
_ATTACHED_ATTACKS_THIS_TURN_IF_ABLE_RE = re.compile(
    r"^(?:enchanted|equipped) creature attacks this turn if able\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s11")
def _parse_attached_attacks_this_turn_if_able_clause(text: str) -> AbilityEffect | None:
    """`_ATTACHED_ATTACKS_THIS_TURN_IF_ABLE_RE`'s shape: CR 508.1d's
    requirement granted until end of turn (CR 611.2a) as the same ability
    line `_parse_target_attacks_if_able_clause` grants. A source with nothing
    attached grants nothing (CR 303.4b names no creature)."""
    if _ATTACHED_ATTACKS_THIS_TURN_IF_ABLE_RE.fullmatch(" ".join(text.split())) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.attached_to is None:
            return
        attached = game.find_by_id(source.attached_to)
        if not isinstance(attached, CardState) or attached.zone is not Zone.BATTLEFIELD:
            return
        _grant_keywords_to(
            game,
            attached,
            ["This creature attacks each combat if able."],
            "until end of turn",
            controller=game.controller_of(ability).username,
            source_name=ability.source_name,
        )

    return effect


#: "All creatures able to block target creature this turn do so." - Shinen of
#: Life's Roar's channel ability: a CR 509.1c lure put on the target for the
#: turn (CR 611.2a), granted as the printed static's own line so
#: `machines/block_statics.py` reads it exactly like Breaker of Armies'.
_LURE_ON_TARGET_RE = re.compile(
    r"^all creatures able to block (?P<phrase>(?:up to one )?target creature(?: [a-z' ]+?)?) "
    r"this turn do so\.?$",
    re.IGNORECASE,
)

#: "This creature must be blocked this turn if able." - a mode of Glorfindel,
#: Dauntless Rescuer's trigger: the source's own CR 509.1c requirement for the
#: turn, granted as the printed "must be blocked if able" line.
_SELF_MUST_BE_BLOCKED_THIS_TURN_RE = re.compile(
    r"^(?:[\u2022*]\s*)?(?:this creature|this permanent|it) must be blocked this turn if able\.?$",
    re.IGNORECASE,
)

#: "This creature can't be blocked by more than one creature each combat this
#: turn." - Glorfindel's other mode: the source's own CR 509.1b restriction for
#: the turn, granted as the text `combat.blocked_by_at_most_one_refusal` reads.
_SELF_AT_MOST_ONE_BLOCKER_THIS_TURN_RE = re.compile(
    r"^(?:[\u2022*]\s*)?(?:this creature|this permanent|it) can't be blocked by more than one "
    r"creature(?: each combat)? this turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s11")
@SPELL_TEXT.rung("s10")
def _parse_block_requirement_grant_clause(text: str) -> TargetedClause | None:
    """`_LURE_ON_TARGET_RE`'s and `_SELF_MUST_BE_BLOCKED_THIS_TURN_RE`'s
    shapes, or `None` (CR 509.1c, CR 611.2a): the requirement is granted until
    end of turn as an ability line (layer 6, CR 613.1f) that `block_statics`
    and `combat_statics` already enforce - on the target for a lure, on the
    ability's own source (while it is still the same object, CR 400.7) for
    "must be blocked this turn"."""
    flat = " ".join(text.split())
    if match := _LURE_ON_TARGET_RE.fullmatch(flat):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None

        def lure_effect(game: "Game", stack_object: "StackObject") -> None:
            controller = game.controller_of(stack_object).username
            source_name = (
                stack_object.card.name
                if isinstance(stack_object, CardState)
                else stack_object.source_name
            )
            for target in game.resolve_targets(stack_object):
                if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                    _grant_keywords_to(
                        game,
                        target,
                        ["All creatures able to block this creature do so."],
                        "until end of turn",
                        controller=controller,
                        source_name=source_name,
                    )

        return lure_effect
    grant = (
        "This creature must be blocked if able."
        if _SELF_MUST_BE_BLOCKED_THIS_TURN_RE.fullmatch(flat) is not None
        else BLOCKED_BY_AT_MOST_ONE_GRANT_TEXT
        if _SELF_AT_MOST_ONE_BLOCKER_THIS_TURN_RE.fullmatch(flat) is not None
        else None
    )
    if grant is None:
        return None

    def self_effect(game: "Game", stack_object: "StackObject") -> None:
        if isinstance(stack_object, CardState):
            return
        source = (
            game.find_by_id(stack_object.source_id) if stack_object.source_id is not None else None
        )
        if (
            not isinstance(source, CardState)
            or source.zone is not Zone.BATTLEFIELD
            or (
                stack_object.source_stamp is not None
                and source.zone_change_stamp != stack_object.source_stamp
            )
        ):
            return
        _grant_keywords_to(
            game,
            source,
            [grant],
            "until end of turn",
            controller=game.controller_of(stack_object).username,
            source_name=stack_object.source_name,
        )

    return self_effect


_OPPONENTS_ATTACK_IF_ABLE_RE = re.compile(
    r"^until your next turn, creatures your opponents control attack each combat if able\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s11")
def _parse_opponents_creatures_attack_if_able_clause(text: str) -> AbilityEffect | None:
    """ "Until your next turn, creatures your opponents control attack each
    combat if able." (The Akroan War's chapter II): CR 508.1d's requirement
    for CR 611.2a's stated duration. It modifies the rules of the game, not
    characteristics or controller, so CR 611.2c does not fix the set: the
    selector is live and a creature that arrives under an opponent's control
    before your next turn is bound too. It is carried as the same granted
    "attacks each combat if able" line `machines/combat.py` already counts."""
    if _OPPONENTS_ATTACK_IF_ABLE_RE.fullmatch(" ".join(text.split())) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability).username
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=(
                    f"{ability.source_name}: creatures {controller}'s opponents control "
                    "attack each combat if able"
                ),
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_YOUR_NEXT_TURN,
                until_next_turn_of=controller,
                selector=creatures_controlled_by_opponents_of(controller),
                modification=grant_ability("This creature attacks each combat if able."),
            )
        )

    return effect


# ---------------------------------------------------------------------------
# C01-T3: zone play, graveyard casting and blink readers
# ---------------------------------------------------------------------------

#: "This creature gets `<layer phrase>` until end of turn and `<verb phrase>`."
#: - one sentence, two instructions sharing the one self-referencing subject
#: (CR 700.7's "this creature", or the card's own name CR 201.5 lets it use,
#: normalised to it by `trigger_effect_for`/`activated_effect_for` before
#: this sees it): Gandalf, Goblins' Bane's cast trigger and Penregon
#: Strongbull's activated ability, "... gets +1/+1 until end of turn and
#: deals 1 damage to each opponent." `_CLAUSE_SEPARATOR`'s bare " and " cut
#: strands the second half with no subject, and the layer fallback reads the
#: whole sentence as one continuous effect it cannot build - so it is read
#: whole here: the first half as its own CR 611.2a layer sentence, the
#: second as the same subject's own instruction.
_SELF_LAYER_AND_VERB_RE = re.compile(
    r"^(?P<subject>this (?:creature|permanent)) (?P<layer>gets [^.]+? until end of turn) "
    r"and (?P<rest>(?:deals|loses|gains) [^.]+)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_self_layer_and_verb_clause(effect_text: str) -> AbilityEffect | None:
    """`_SELF_LAYER_AND_VERB_RE`'s shape: the layer half through
    `_create_continuous_effect_of_ability_for_mode_text` (which does nothing
    once the source has left the battlefield - there is no object left to
    modify), then the verb half through `parse_mixed_effect`, whose damage
    reader uses the source's last known information (CR 608.2h: "it's the
    object as it exists - or as it most recently existed - that does it").
    Either half unread leaves the whole sentence unread (CR 608.2c)."""
    match = _SELF_LAYER_AND_VERB_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    subject = match.group("subject")
    layer_sentence = f"{subject[0].upper()}{subject[1:]} {match.group('layer')}."
    if not is_genuine_resolution_layer_sentence(layer_sentence):
        return None
    rest = parse_mixed_effect(f"{subject} {match.group('rest')}.")
    if rest is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            continuous_effects(game).create(
                source,
                targets=[source],
                context=layer_context_for(game, game.controller_of(ability)),
                ability_text=layer_sentence,
                game=game,
            )
        rest(game, ability)

    return effect


#: "Double target creature's power and toughness until end of turn." (Epic
#: Fight's first mode, Choose Your Weapon's "Two-Weapon Fighting", Tifa's
#: Limit Break's "Meteor Strikes") and its "Double the power and toughness of
#: target creature ..." word order. CR 701.10b: "Doubling a creature's power
#: and toughness gives it +X/+Y, where X is its power and Y is its
#: toughness" as the spell or ability resolves; CR 701.10a makes it a
#: modification, not a set - sublayer 7c (CR 613.4c). CR 701.10c's negative
#: value (-X instead of +X) is the same arithmetic: X added to itself.
_DOUBLE_TARGET_POWER_AND_TOUGHNESS_RE = re.compile(
    r"^double (?:(?P<possessive>(?:up to one )?target [a-z ]*?creature(?: you control| an opponent "
    r"controls)?)['’]s power and toughness|the power and toughness of "
    r"(?P<phrase>(?:up to one )?target [a-z ]*?creature(?: you control| an opponent controls)?))"
    r" until end of turn\.?$",
    re.IGNORECASE,
)


def _parse_double_target_power_and_toughness_clause(
    text: str,
) -> Callable[["Game", "StackObject"], None] | None:
    """`_DOUBLE_TARGET_POWER_AND_TOUGHNESS_RE`'s shape, on a spell, a mode or
    an ability alike - the values are read once, as it resolves, through the
    computed characteristics (CR 613.5), and the +X/+Y never recomputes."""
    match = _DOUBLE_TARGET_POWER_AND_TOUGHNESS_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    phrase = match.group("possessive") or match.group("phrase")
    if not _targets_understood(phrase, count_agnostic=False):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = (
            stack_object.source_name
            if isinstance(stack_object, AbilityOnStack)
            else stack_object.name
        )
        for target in game.resolve_card_targets(stack_object):
            if target.zone is Zone.BATTLEFIELD:
                _double_power_and_toughness(game, target, source_name)

    return effect


def _double_power_and_toughness(game: "Game", target: CardState, source_name: str) -> None:
    """CR 701.10b: `target` gets +X/+Y until end of turn, X and Y its power
    and toughness as this resolves (computed, CR 613.5) - a sublayer 7c
    modification (CR 613.4c), never recomputed. Nothing for a permanent that
    is not a creature or has no number to double."""
    chars = game.characteristics_of(target)
    if not chars.is_creature or chars.power is None or chars.toughness is None:
        return
    store = continuous_effects(game)
    store.add(
        ContinuousEffect(
            description=(
                f"{source_name}: {target.name} gets {chars.power:+d}/{chars.toughness:+d} (doubled)"
            ),
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.MODIFY,
            timestamp=store.tick(),
            duration=Duration.UNTIL_END_OF_TURN,
            selector=only_this_incarnation(target, target.zone_change_stamp),
            modification=modify_power_toughness(chars.power, chars.toughness),
        )
    )


# --------------------------------------------------------------------------
# Whole-text readers for source-relative combat and token effects
# --------------------------------------------------------------------------
#
# Each shape below is read off a resolving ability's (or spell's) whole,
# unsplit text, ahead of `split_effect_clauses`: every one of them is a single
# CR 608.2c instruction whose parts share a referent or an X that a clause-by-
# clause read would cut apart.

#: "X target creatures can't be blocked this turn." (Open into Wonder) / "Up
#: to two target creatures can't be blocked this turn." (Ghostform) - CR
#: 509.1b's evasion restriction on a counted plural target (CR 601.2c
#: settled how many and which at announcement; `_targets_understood` reads
#: the count), optionally followed by "Until end of turn, those creatures
#: gain [<keywords> and] "<ability>"." - "those creatures" is exactly the
#: resolved targets (CR 608.2c), each granted the quoted ability in layer 6
#: (CR 613.1f, CR 113.10) until cleanup. The single "target creature" form
#: stays with `dispatch.py`'s own `_TARGET_CANT_BE_BLOCKED_RE`.
_COUNTED_TARGETS_CANT_BE_BLOCKED_RE = re.compile(
    r"^(?P<phrase>(?:up to |one or )?(?:x|\w+) target .*?creatures(?: [a-z' ]+?)?) "
    r"can'?t be blocked this turn"
    r"(?:\.\s*until end of turn, those creatures gain "
    r"(?:(?P<keywords>[a-z][a-z0-9 ,]*?),? and )?\"(?P<granted>[^\"]+)\")?\.?$",
    re.IGNORECASE,
)


def _counted_targets_cant_be_blocked(text: str) -> TargetedClause | None:
    """`_COUNTED_TARGETS_CANT_BE_BLOCKED_RE`'s shape, or `None`."""
    whole = " ".join(text.strip().split())
    if "can't be blocked this turn" not in whole.lower() and "cant be blocked" not in whole.lower():
        return None
    match = _COUNTED_TARGETS_CANT_BE_BLOCKED_RE.fullmatch(whole)
    if match is None:
        return None
    phrase = match.group("phrase")
    if phrase.lower().startswith(("target ", "another target ")):
        return None
    if not _targets_understood(phrase, count_agnostic=True, battlefield_only=True):
        return None
    grants = ["This creature can't be blocked."]
    if match.group("keywords") is not None:
        keywords = split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        grants.extend(keywords)
    if match.group("granted") is not None:
        grants.append(match.group("granted").strip())

    def effect(game: "Game", stack_object: "StackObject") -> None:
        effects = game.continuous_effects
        timestamp = effects.tick()
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            for granted in grants:
                effects.add(
                    ContinuousEffect(
                        description=f"{target.name} gains {granted!r} this turn",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=only_this_incarnation(target, target.zone_change_stamp),
                        modification=grant_ability(granted),
                    )
                )

    return effect


@MIXED_CLAUSE.rung("s11", for_spell=FORWARD)
def _parse_counted_targets_cant_be_blocked_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_counted_targets_cant_be_blocked` as one clause (Ghostform)."""
    return _counted_targets_cant_be_blocked(clause)


@ABILITY_TEXT.rung("s41", for_spell=False)
@SPELL_TEXT.rung("s25", for_spell=True)
def _parse_counted_targets_cant_be_blocked_whole_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_counted_targets_cant_be_blocked` over the whole text - the quoted
    ability's own full stop would otherwise cut the grant sentence apart
    (Open into Wonder)."""
    whole = _strip_non_effect_preamble(text).strip()
    if '"' not in whole:
        return None
    return _counted_targets_cant_be_blocked(whole)


#: "`<target phrase>` can't be blocked this turn except by `<description>`."
#: (Departed Deckhand: "except by Spirits"): CR 509.1b's evasion restriction
#: with a creature description for the exception, granted as the self
#: sentence `combat_statics.block_evasion_refusal` reads. A keyword exception
#: ("except by creatures with haste") is `dispatch._TARGET_CANT_BE_BLOCKED_RE`'s.
_TARGET_CANT_BE_BLOCKED_EXCEPT_BY_RE = re.compile(
    r"^(?P<phrase>(?:another )?target .+?) can'?t be blocked this turn except by "
    r"(?P<desc>(?!creatures with ).+?)\.?$",
    re.IGNORECASE,
)


def _target_cant_be_blocked_except_by(text: str) -> TargetedClause | None:
    """`_TARGET_CANT_BE_BLOCKED_EXCEPT_BY_RE`'s shape, or `None`."""
    match = _TARGET_CANT_BE_BLOCKED_EXCEPT_BY_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    from ..combat_statics import parse_blocker_description

    description = match.group("desc").strip()
    if parse_blocker_description(description) is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    granted = f"This creature can't be blocked except by {description}."

    def effect(game: "Game", stack_object: "StackObject") -> None:
        effects = game.continuous_effects
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            effects.add(
                ContinuousEffect(
                    description=f"{target.name} can't be blocked except by {description} this turn",
                    layer=Layer.ABILITY,
                    timestamp=effects.tick(),
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=grant_ability(granted),
                )
            )

    return effect


@MIXED_CLAUSE.rung("s11", for_spell=FORWARD)
def _parse_target_cant_be_blocked_except_by_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_target_cant_be_blocked_except_by` as one clause."""
    return _target_cant_be_blocked_except_by(clause)


@ABILITY_TEXT.rung("s41", for_spell=False)
@SPELL_TEXT.rung("s25", for_spell=True)
def _parse_target_cant_be_blocked_except_by_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_target_cant_be_blocked_except_by` over a whole ability or spell text."""
    return _target_cant_be_blocked_except_by(_strip_non_effect_preamble(text).strip())


#: "`<target phrase>` gains `<keywords>` until end of turn and can't be
#: blocked this turn[. `<rest>`]" - Pym Particles' "Target creature gains
#: vigilance until end of turn and can't be blocked this turn. Draw a card.",
#: Break Through the Line's "Target creature with power 2 or less gains haste
#: until end of turn and can't be blocked this turn." One subject, two
#: predicates: a layer 6 keyword grant (CR 613.1f) and CR 509.1b's evasion
#: restriction granted as the self-referential sentence `machines/combat.py`
#: enforces, both ending at cleanup (CR 514.2, CR 611.2a).
_GAINS_AND_CANT_BE_BLOCKED_THIS_TURN_RE = re.compile(
    r"^(?P<phrase>target .+?) gains (?P<keywords>[a-z][a-z ,]*?) until end of turn "
    r"and can'?t be blocked this turn(?:\.\s*(?P<rest>.*))?$",
    re.IGNORECASE | re.DOTALL,
)


def _gains_and_cant_be_blocked_this_turn(
    text: str, rest_parser: Callable[[str], object]
) -> Callable[["Game", "StackObject"], None] | None:
    """`_GAINS_AND_CANT_BE_BLOCKED_THIS_TURN_RE`'s shape, with any following
    instruction read by `rest_parser` and run after it (CR 608.2c)."""
    match = _GAINS_AND_CANT_BE_BLOCKED_THIS_TURN_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    keywords = split_and_validate_keywords(match.group("keywords"))
    if keywords is None:
        return None
    rest_text = (match.group("rest") or "").strip()
    rest = rest_parser(rest_text) if rest_text else None
    if rest_text and rest is None:
        return None
    grants = [*keywords, "This creature can't be blocked."]

    def effect(game: "Game", stack_object: "StackObject") -> None:
        effects = game.continuous_effects
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            timestamp = effects.tick()
            for grant in grants:
                effects.add(
                    ContinuousEffect(
                        description=f"{target.name} has {grant} this turn",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=only_this_incarnation(target, target.zone_change_stamp),
                        modification=grant_ability(grant),
                    )
                )
        if rest is not None:
            rest(game, stack_object)  # type: ignore[operator]

    return effect


#: "each opponent loses X life and you gain X life, where X is `<expr>`." -
#: Whiplash, Vengeful Engineer's "... where X is the number of Equipment
#: attached to him." One X for both halves, read once as the ability resolves
#: (CR 608.2h) against the ability's own source (CR 113.7).
_EACH_OPPONENT_LOSES_X_YOU_GAIN_X_RE = re.compile(
    r"^each opponent loses x life and you gain x life, where x is (?P<expr>.+?)\.?$",
    re.IGNORECASE,
)


def _parse_each_opponent_loses_x_you_gain_x(text: str) -> AbilityEffect | None:
    """`_EACH_OPPONENT_LOSES_X_YOU_GAIN_X_RE`'s drain: each opponent loses X
    (CR 119.3) and the controller gains X (CR 119.4)."""
    match = _EACH_OPPONENT_LOSES_X_YOU_GAIN_X_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    reader = amount_expression(match.group("expr"))
    if reader is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        amount = reader(game, controller.username, ability.source_or_last_known(game), 0)
        if amount <= 0:
            return
        for opponent in _opponents(game, controller.username):
            game.lose_life(opponent, amount)
        game.gain_life(controller, amount)

    return effect


#: "transform it." as a triggered ability's whole effect - Avacynian
#: Missionaries' "At the beginning of your end step, if this creature is
#: equipped, transform it.", Uninvited Geist's "When this creature deals
#: combat damage to a player, transform it." The only antecedent is the
#: source the trigger condition names, so "it" is CR 701.27a's
#: self-referential transform.
_TRANSFORM_IT_RE = re.compile(r"^transform it\.?$", re.IGNORECASE)


def _parse_transform_it(text: str) -> AbilityEffect | None:
    """`_TRANSFORM_IT_RE`, as the source's own transform; an event about some
    other object leaves "it" unresolved here, so nothing transforms."""
    if _TRANSFORM_IT_RE.fullmatch(text.strip()) is None:
        return None
    transform_self = parse_mixed_effect("Transform this creature.")
    if transform_self is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        subject = None if event is None else event.subject_id
        if subject is not None and subject != ability.source_id:
            return
        transform_self(game, ability)

    return effect


#: "attach up to one target Equipment to it. Then `<rest>`" - Shagrat, Loot
#: Bearer's attack trigger, "it" being the attacking source itself (its
#: name, and so its pronoun, already the ability's own subject). CR 701.3a's
#: attach of a targeted Equipment (CR 115.6's "up to one" may choose none)
#: onto the source, then the rest of the instruction in order (CR 608.2c).
_ATTACH_TARGET_EQUIPMENT_TO_SELF_RE = re.compile(
    r"^attach (?:up to one )?target equipment(?: you control)? to "
    r"(?:it|him|her|this creature|this permanent)\.(?:\s*(?P<rest>.+))?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_attach_target_equipment_to_self(text: str) -> AbilityEffect | None:
    """`_ATTACH_TARGET_EQUIPMENT_TO_SELF_RE`'s shape, or `None`."""
    match = _ATTACH_TARGET_EQUIPMENT_TO_SELF_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    rest_text = (match.group("rest") or "").strip()
    rest = parse_mixed_effect(rest_text) if rest_text else None
    if rest_text and rest is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            for target in game.resolve_targets(ability):
                if isinstance(target, CardState):
                    attach_permanent(game, target, source)
        if rest is not None:
            rest(game, ability)

    return effect


#: "attach it to target creature you control. That creature gains
#: indestructible until end of turn." (Stolen Stark Tech), "... Untap that
#: creature." (Super Suit, Galadhrim Bow), "... That creature gains first
#: strike until end of turn." (Quick-Draw Dagger) - CR 701.3a's attach of
#: the source onto its announced target, then a rider whose "that creature"
#: is the same target (CR 608.2c: one instruction, read in order). The
#: rider is read as the targeted sentence it restates, so it acts on exactly
#: the object the attach did.
_ATTACH_SELF_THEN_THAT_CREATURE_RE = re.compile(
    r"^(?P<attach>attach (?:it|this (?:aura|equipment|fortification|permanent)) "
    r"to (?:up to one )?target [^.]+)\.\s*"
    r"(?P<rider>(?:that creature \S.*|untap that creature\.?|put [^.]*? on that creature\.?))$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_attach_self_then_that_creature(text: str) -> AbilityEffect | None:
    """`_ATTACH_SELF_THEN_THAT_CREATURE_RE`'s shape, or `None`."""
    match = _ATTACH_SELF_THEN_THAT_CREATURE_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    attach = _attach_self_to_target_effect(match.group("attach"))
    rider_text = re.sub(
        r"\bthat creature\b",
        lambda m: "Target creature" if m.start() == 0 else "target creature",
        match.group("rider").strip(),
        count=1,
        flags=re.IGNORECASE,
    )
    rider = parse_mixed_effect(rider_text)
    if attach is None or rider is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        attach(game, ability)
        rider(game, ability)

    return effect


#: "you may put an artifact card from your hand onto the battlefield. If it's
#: an Equipment, attach it to The Invincible Iron Man." (Tony Stark // The
#: Invincible Iron Man, the name already "this permanent") - CR 608.2d's
#: optional choice of a card of one type from hand put onto the battlefield,
#: then CR 701.3a's attach of that permanent onto the source when it has the
#: named subtype as it now exists (CR 613.5).
_PUT_TYPE_FROM_HAND_ATTACH_IF_SUBTYPE_RE = re.compile(
    r"^you may put an? (?P<type>[a-z]+) card from your hand onto the battlefield\. "
    r"if it's an? (?P<subtype>[A-Za-z]+), attach it to this (?:creature|permanent)\.?$",
    re.IGNORECASE,
)


def _parse_put_type_from_hand_attach_if_subtype(text: str) -> AbilityEffect | None:
    """`_PUT_TYPE_FROM_HAND_ATTACH_IF_SUBTYPE_RE`'s shape, or `None`."""
    match = _PUT_TYPE_FROM_HAND_ATTACH_IF_SUBTYPE_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    card_type = next((kind for kind in Type if kind.value == match.group("type").lower()), None)
    subtype = canonical_subtype(match.group("subtype"))
    if card_type is None or subtype is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        candidates = [state for state in player.hand if card_type in state.types]
        if not candidates or not game.may(
            player,
            f"put {with_indefinite_article(card_type.value)} card from your hand onto the "
            "battlefield",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        chosen = candidates[0]
        if len(candidates) > 1:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"choose {with_indefinite_article(card_type.value)} card to put "
                    "onto the battlefield",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    amount=1,
                    cards=tuple(state.id for state in candidates),
                    card_labels=tuple(state.name for state in candidates),
                )
            )
            assert isinstance(chosen_ids, tuple)
            chosen = {state.id: state for state in candidates}[chosen_ids[0]]
        permanent = game.put_onto_battlefield(chosen, player.username)
        if permanent is None or permanent.zone is not Zone.BATTLEFIELD:
            return
        if subtype not in {word.lower() for word in game.characteristics_of(permanent).subtypes}:
            return
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            attach_permanent(game, permanent, source)

    return effect


def _may_attach_equipment_to(game: "Game", host: CardState, stack_object: "StackObject") -> None:
    """CR 608.2d: offer the controller one Equipment they control to attach
    to `host` - nothing is asked when there is none to offer."""
    controller = game.controller_of(stack_object)
    candidates = [
        permanent
        for permanent in game.permanents_controlled_by(controller.username)
        if "Equipment" in game.characteristics_of(permanent).subtypes
    ]
    if not candidates or host.zone is not Zone.BATTLEFIELD:
        return
    source_name = (
        stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name  # type: ignore[union-attr]
    )
    if not game.may(
        controller,
        f"attach an Equipment you control to {host.name}",
        source=source_name,
        source_id=source_id_of(stack_object),
    ):
        return
    chosen = candidates[0]
    if len(candidates) > 1:
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="choose an Equipment you control to attach",
                source=source_name,
                source_id=source_id_of(stack_object),
                amount=1,
                cards=tuple(permanent.id for permanent in candidates),
                card_labels=tuple(permanent.name for permanent in candidates),
            )
        )
        assert isinstance(chosen_ids, tuple)
        chosen = {permanent.id: permanent for permanent in candidates}[chosen_ids[0]]
    attach_permanent(game, chosen, host)


#: "untap him and there is an additional combat phase after this phase." -
#: CR 701.26b's untap of the source and CR 500.8's additional combat phase.
_UNTAP_SELF_AND_ADDITIONAL_COMBAT_RE = re.compile(
    r"^untap (?:it|him|her|this creature) and there is an additional combat phase "
    r"after this phase\.?$",
    re.IGNORECASE,
)


def _untap_self_and_additional_combat(text: str) -> AbilityEffect | None:
    """`_UNTAP_SELF_AND_ADDITIONAL_COMBAT_RE`'s shape, or `None`."""
    if _UNTAP_SELF_AND_ADDITIONAL_COMBAT_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            source.untap()
        assert game.turn is not None
        game.turn.insert_extra_phase(COMBAT_PHASE_STEPS)

    return effect


#: "those creatures gain flying until end of turn." after "Whenever you cast
#: a spell that targets one or more creatures" (Storm, Windrider) - "those
#: creatures" are the triggering spell's own targets that are creatures
#: (CR 601.2c), each granted the keywords for CR 611.2a's duration. Any
#: other trigger's "those creatures" is left to the batched-attack reader.
_THOSE_CREATURES_GAIN_RE = re.compile(
    r"^those creatures gain (?P<keywords>[a-z][a-z ,]*?) until end of turn\.?$", re.IGNORECASE
)


def _parse_cast_spell_targets_gain(text: str) -> AbilityEffect | None:
    """`_THOSE_CREATURES_GAIN_RE` for a cast trigger, or `None`."""
    match = _THOSE_CREATURES_GAIN_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    keywords = split_and_validate_keywords(match.group("keywords"))
    batched = _parse_batched_attack_group_pump_clause(text)
    if keywords is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.event is not TriggerEvent.CAST_SPELL:
            if batched is not None:
                batched(game, ability)
            return
        spell = game.find_by_id(event.subject_id) if event.subject_id else None
        if spell is None:
            return
        store = game.continuous_effects
        for target_ref in spell.targets:
            if target_ref.is_player or target_ref.card_id is None:
                continue
            creature = game.find_by_id(target_ref.card_id)
            if creature is None or creature.zone is not Zone.BATTLEFIELD:
                continue
            if not game.characteristics_of(creature).is_creature:
                continue
            for keyword in keywords:
                store.add(
                    ContinuousEffect(
                        description=f"{ability.source_name}: {creature.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=store.tick(),
                        duration=Duration.UNTIL_END_OF_TURN,
                        source_id=ability.source_id,
                        selector=only_this_incarnation(creature, creature.zone_change_stamp),
                        modification=grant_ability(keyword),
                    )
                )

    return effect


# --------------------------------------------------------------------------
# NW-01 T5: group restrictions, lost keywords and per-count pumps after damage
# --------------------------------------------------------------------------


def _named_player_of(game: "Game", stack_object: "StackObject") -> str | None:
    """The player a resolving object's own words name through its target:
    the targeted player, or - for "target player or planeswalker" - the
    targeted planeswalker's controller (CR 115.1; Concussive Bolt's "that
    player or ... that planeswalker's controller", Ember Gale's "that
    player"). `None` when nothing names one (CR 608.2b: an illegal target
    names nobody)."""
    for target in game.resolve_targets(stack_object):
        if isinstance(target, Player):
            return target.username
        if (
            isinstance(target, CardState)
            and target.zone is Zone.BATTLEFIELD
            and Type.PLANESWALKER in game.characteristics_of(target).types
        ):
            return game.controller_of(target).username
    return None


#: "Creatures [`<whose>`] can't block this turn." - CR 509.1b's restriction
#: on a whole group for the rest of the turn: every creature (Barrage of
#: Boulders' Ferocious line), "your opponents control" (Cosmotronic Wave,
#: Hazardous Blast), "target player/opponent controls" (Ember Gale), or "that
#: player controls" / "controlled by that player or by that planeswalker's
#: controller" (Concussive Bolt), the player its own target names.
_GROUP_CANT_BLOCK_THIS_TURN_RE = re.compile(
    r"^creatures(?: (?:(?P<opponents>your opponents control)"
    r"|(?P<target>target (?:player|opponent)) controls"
    r"|(?P<named>that player controls"
    r"|controlled by that player(?: or by that planeswalker(?:'|’)s controller)?)))?"
    r" can(?:'|’)?t block this turn\.?$",
    re.IGNORECASE,
)


#: "<Creature type>s can't block this turn." (Pyrophobia's "Cowards can't
#: block this turn.") - CR 509.1b's restriction on every creature of a CR
#: 205.3m creature type, whoever controls it. A changeling is every creature
#: type (CR 702.73a), so it is included, read off the computed board.
_CREATURE_TYPE_CANT_BLOCK_THIS_TURN_RE = re.compile(
    r"^(?P<plural>[a-z][a-z'\u2019-]*) can(?:'|\u2019)?t block this turn\.?$", re.IGNORECASE
)


def _parse_creature_type_cant_block_this_turn_clause(clause: str) -> TargetedClause | None:
    """`_CREATURE_TYPE_CANT_BLOCK_THIS_TURN_RE`'s shape, or `None`.

    Like `_parse_group_cant_block_this_turn_clause`'s own groups it is a live
    selector, not a set fixed as the spell resolves: "can't block" changes no
    characteristic and no controller, so CR 611.2c does not lock it, and a
    creature that becomes (or enters as) a member later this turn is
    restricted too. The selector names a controller, so one effect is added
    per player in the game."""
    if "block this turn" not in clause.lower():
        return None
    match = _CREATURE_TYPE_CANT_BLOCK_THIS_TURN_RE.fullmatch(" ".join(clause.split()))
    if match is None:
        return None
    word = canonical_subtype(match.group("plural"))
    creature_type = next(
        (each for each in creature_type_vocabulary() if each.lower() == word), None
    )
    if creature_type is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        store = continuous_effects(game)
        for player in game.players:
            store.add(
                ContinuousEffect(
                    description=f"{source_name}: {creature_type}s can't block this turn",
                    layer=Layer.ABILITY,
                    timestamp=store.tick(),
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=creatures_controlled_by_with_subtype(player.username, [creature_type]),
                    modification=grant_ability("This creature can't block."),
                )
            )

    return effect


#: "Target creature with defender can attack this turn as though it didn't have
#: defender." (Assault Formation's `{G}` ability) - the one-shot, targeted twin of
#: Ghalta the Immovable's static grant: the fixed `ATTACK_WITHOUT_DEFENDER_TEXT`
#: for the rest of the turn (CR 611.2a), on the creature chosen (CR 611.2c).
_TARGET_ATTACKS_WITHOUT_DEFENDER_RE = re.compile(
    r"^(?P<phrase>target [^.]+?) can attack this turn as though it didn'?t have defender$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_target_attacks_without_defender_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TARGET_ATTACKS_WITHOUT_DEFENDER_RE`'s shape, or `None`."""
    match = _TARGET_ATTACKS_WITHOUT_DEFENDER_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None or not _targets_understood(match.group("phrase")):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        store = continuous_effects(game)
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                store.add(
                    ContinuousEffect(
                        description=f"{source_name}: can attack as though it didn't have defender",
                        layer=Layer.ABILITY,
                        timestamp=store.tick(),
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=_only(target.id),
                        modification=grant_ability(ATTACK_WITHOUT_DEFENDER_TEXT),
                    )
                )

    return effect


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_group_cant_block_this_turn_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_GROUP_CANT_BLOCK_THIS_TURN_RE`'s shape: the "This creature can't
    block." line `machines/combat.py`'s CR 509.1b reader already checks,
    granted to the group until end of turn (CR 611.2a).

    The restriction changes no characteristic and no controller, so CR
    611.2c does not fix the set as it begins: the selector stays live, and a
    creature that comes under the named player's control later in the turn
    cannot block either. A targeted player that is no longer legal names
    nobody (CR 608.2b), so nothing is restricted."""
    match = _GROUP_CANT_BLOCK_THIS_TURN_RE.fullmatch(" ".join(clause.split()))
    if match is None:
        return _parse_creature_type_cant_block_this_turn_clause(clause)
    target_phrase = match.group("target")
    if target_phrase is not None and not _targets_understood(
        target_phrase, battlefield_only=False, allow_player_targets=True
    ):
        return None
    if match.group("named") is not None and not for_spell:
        # An ability's "that player" is whoever its trigger event names (a
        # defending player, an opponent who cast a spell), not a target.
        return None
    opponents = match.group("opponents") is not None
    named = target_phrase is not None or match.group("named") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        if named:
            player = _named_player_of(game, stack_object)
            if player is None:
                return
            selector = creatures_controlled_by(player)
            whose = f"{player} controls"
        elif opponents:
            selector = creatures_controlled_by_opponents_of(controller)
            whose = f"{controller}'s opponents control"
        else:
            selector = every_creature
            whose = "anyone controls"
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{source_name}: creatures {whose} can't block this turn",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=selector,
                modification=grant_ability("This creature can't block."),
            )
        )

    return effect


#: "Those creatures don't untap during `<their controller's | that player's>`
#: next untap step." - the sentence after a mass tap (Clinging Mists' "tap all
#: attacking creatures", Sleep's "tap all creatures target player controls").
#: CR 611.2c: "those creatures" is the set the first sentence applied to,
#: fixed as it resolved - every creature of the group, including one that was
#: already tapped (CR 701.26a only stops it being tapped *again*). CR 502.3:
#: the untap step is where "effects can keep one or more of a player's
#: permanents from untapping"; `CardState.exerted` (the CR 701.43a-b
#: machinery `_parse_tap_target_then_no_untap_clause` already reuses) is
#: cleared by the creature's own controller's untap step, which is exactly
#: "their controller's next untap step".
_THOSE_DONT_UNTAP_RE = re.compile(
    r"^(?:those \w+|they) don['’]?t untap during (?:their controllers?['’]?s?|that player['’]?s?) "
    r"next untap steps?\.?$",
    re.IGNORECASE,
)
_LEADING_GATE_THEN_TAP_ALL_RE = re.compile(
    r"^if (?P<condition>.+?), (?P<tap>tap all .+)$", re.IGNORECASE
)


def _group_tap_then_no_untap_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "`[If <condition>, ]tap all <group>.` `Those creatures don't untap
    during <whose> next untap step.`" as one CR 608.2c instruction pair, or
    `None`. The optional leading condition (Clinging Mists' Fateful hour, an
    ability word with no rules meaning of its own - CR 207.2c) gates both
    sentences: with it false nothing is tapped and nothing is held down."""
    if _THOSE_DONT_UNTAP_RE.fullmatch(second.strip()) is None:
        return None
    tap_text = first.strip()
    condition: str | None = None
    gated = _LEADING_GATE_THEN_TAP_ALL_RE.fullmatch(tap_text)
    if gated is not None:
        condition = gated.group("condition").strip()
        tap_text = gated.group("tap")
        if not _effect_condition_is_readable(condition, allow_anaphor=not for_spell):
            return None
    members = _tap_all_group_members(tap_text)
    if members is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if condition is not None:
            source = (
                stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
            )
            held = _condition_holds_for_stack_object(game, stack_object, condition, source)
            if held is None:
                notice = ConditionalClauseNotice(
                    source_id=source_id_of(stack_object),
                    source_name=(
                        stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
                    ),
                    text=first.strip(),
                )
                if notice not in game.conditional_clause_notices:
                    game.conditional_clause_notices.append(notice)
                return
            if not held:
                return
        for member in members(game, stack_object):
            game.tap_permanent(member)
            member.exerted = True

    return effect


#: "Other creatures [`<whose>`] can't (attack|block) this turn." -
#: Intimidation Bolt's second sentence and Mark for Death's last. "Other" is
#: "other than the object the spell or ability just named": the creature it
#: targeted (a legal target when it resolves, CR 608.2b), else - an
#: ability's own words with no creature target - its source. CR 508.1c /
#: 509.1b make this a restriction on every creature that is not the excluded
#: one, so it is a live selector, not a fixed set (CR 611.2c fixes the set
#: only for effects that change characteristics or control): a creature that
#: enters later this turn is restricted too. "that player controls" is the
#: excluded creature's controller.
_OTHER_CREATURES_CANT_RE = re.compile(
    r"^other creatures(?: (?P<whose>that player controls|your opponents control))?"
    r" can['’]?t (?P<what>attack|block) this turn\.?$",
    re.IGNORECASE,
)


def _other_creatures_cant_clause(clause: str) -> TargetedClause | None:
    """`_OTHER_CREATURES_CANT_RE`'s shape, or `None`."""
    match = _OTHER_CREATURES_CANT_RE.fullmatch(" ".join(clause.split()))
    if match is None:
        return None
    whose = (match.group("whose") or "").lower()
    line = f"This creature can't {match.group('what').lower()}."

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        excluded: CardState | None = next(
            (
                target
                for target in game.resolve_targets(stack_object)
                if isinstance(target, CardState)
                and target.zone is Zone.BATTLEFIELD
                and game.characteristics_of(target).is_creature
            ),
            None,
        )
        if excluded is None and not isinstance(stack_object, CardState):
            excluded = stack_object.source(game)
        if excluded is None:
            return
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        if whose == "that player controls":
            selector = qualified_creatures(
                excluded.id, game.controller_of(excluded).username, other=True
            )
        elif whose == "your opponents control":
            selector = qualified_creatures(excluded.id, controller, other=True, opponents=True)
        else:
            selector = qualified_creatures(excluded.id, None, other=True)
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{source_name}: other creatures can't {match.group('what').lower()}",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=selector,
                modification=grant_ability(line),
            )
        )

    return effect


#: "[If {W}{U} was spent to cast this spell, ][until your next turn, ]
#: `<subject>` can't attack or block[ and its/their activated abilities
#: can't be activated][ until your next turn]." - Mythos of Vadrok's own
#: gated rider ("those permanents" is the targets the damage sentence chose),
#: and the same words on a "target `<permanent>`"/"it"/"that permanent"
#: subject (Edifice of Authority, Academic Probation, Linvala): CR 701.35a's
#: detain, spelled out. CR 611.2a gives the printed duration ("until your
#: next turn" ends when the spell's controller's next turn begins),
#: CR 508.1c / 509.1b the two restrictions, CR 602.5 the activation ban. No
#: mana-ability exemption is printed, so none is made (CR 605.1a keeps a
#: mana ability an *activated* ability).
#:
#: The gate is CR 601.2h's mana actually spent paying for the spell, read off
#: the cast record: a symbol is met when at least one mana of that colour was
#: spent, and every symbol must be (a spell cast for {2}{R}{R} with Plains
#: and Islands in the mix is one thing; one paid with Mountains alone is
#: another). Only a spell has a cast record.
_CANT_ATTACK_BLOCK_ACTIVATE_RE = re.compile(
    r"^(?:if (?P<gate>(?:\{[wubrgc]\})+) was spent to cast this spell, )?"
    r"(?:(?P<lead>until your next turn|until end of turn), )?"
    r"(?P<subject>those (?:permanents|creatures)|that (?:permanent|creature)|it|they"
    r"|target [a-z' ]+?)"
    r" can['’]?t attack or block"
    r"(?:,? and (?:its|their) activated abilities can['’]?t be activated)?"
    r"(?: (?P<trail>until your next turn|until end of turn))?\.?$",
    re.IGNORECASE,
)


def _cant_attack_block_activate_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_CANT_ATTACK_BLOCK_ACTIVATE_RE`'s shape, or `None`."""
    match = _CANT_ATTACK_BLOCK_ACTIVATE_RE.fullmatch(" ".join(clause.split()))
    if match is None:
        return None
    lead = (match.group("lead") or "").lower()
    trail = (match.group("trail") or "").lower()
    duration_text = lead or trail
    if not duration_text or (lead and trail):
        return None
    gate = match.group("gate")
    if gate is not None and not for_spell:
        return None
    subject = match.group("subject")
    own_phrase = subject if subject.lower().startswith("target ") else None
    if own_phrase is not None and not _targets_understood(own_phrase, count_agnostic=True):
        return None
    locks_activation = "activated abilities" in clause.lower()
    lines = ["This creature can't attack.", "This creature can't block."]
    if locks_activation:
        lines.append(CANT_ACTIVATE_ABILITIES_TEXT)
    gate_colors = [Color(letter.upper()) for letter in re.findall(r"\{(\w)\}", gate or "")]

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if gate_colors:
            if not isinstance(stack_object, CardState):
                return
            record = game.cast_record(stack_object)
            if not all(record.mana_of_color_spent(color) > 0 for color in gate_colors):
                return
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        if own_phrase is not None:
            affected = _own_phrase_targets(game, stack_object, own_phrase)
        else:
            affected = [
                target
                for target in game.resolve_targets(stack_object)
                if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
            ]
        for permanent in affected:
            _grant_keywords_to(
                game,
                permanent,
                lines,
                duration_text,
                controller=controller,
                source_name=source_name,
            )

    return effect


#: "Target creature `<...>` blocks this turn if able. Untap that creature." -
#: Mark for Death's first two sentences. CR 701.26b's untap acts on the
#: creature the first sentence's requirement was put on (CR 608.2c: in the
#: order written - untapped last, so it is untapped when it must block).
_UNTAP_THAT_CREATURE_RE = re.compile(r"^untap (?:that creature|it)\.?$", re.IGNORECASE)


def _if_able_requirement_then_untap_pair(first: str, second: str) -> TargetedClause | None:
    """`_parse_target_attacks_if_able_clause`'s requirement sentence followed
    by `_UNTAP_THAT_CREATURE_RE`'s untap, or `None`."""
    if _UNTAP_THAT_CREATURE_RE.fullmatch(second.strip()) is None:
        return None
    requirement = _parse_target_attacks_if_able_clause(first.strip())
    if requirement is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        requirement(game, stack_object)
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                target.untap()

    return effect


#: One whole-text reader for the riders that follow a spell's or ability's
#: main effect and talk about what that effect applied to or named. They are
#: read from the whole text, a sentence at a time, because each leans on the
#: sentences around it - "those creatures" is the previous sentence's group,
#: "other creatures" excludes the previous sentence's target, "those
#: permanents" is the targets the damage sentence divided among - and the
#: per-clause splitter would cut "can't attack or block and their activated
#: abilities can't be activated" at its "and". Every sentence that is not a
#: rider is read, a contiguous run at a time, by the ordinary clause reader,
#: so the main effect keeps every reading it already has (CR 608.2c: the
#: instructions are followed in the order written).
_RIDER_LITERALS = ("untap during", "other creatures", "can't attack or block", "untap that")


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_main_effect_riders(text: str, *, for_spell: bool) -> list[TargetedClause] | None:
    """The text read around its riders, or `None` when it carries none."""
    lowered = text.lower().replace("’", "'")
    if not any(literal in lowered for literal in _RIDER_LITERALS):
        return None
    sentences = _plain_resolution_sentences(_strip_non_effect_preamble(text))
    parts: list[list[str] | TargetedClause] = []
    run: list[str] = []
    found = False
    index = 0
    while index < len(sentences):
        sentence = sentences[index]
        rider: TargetedClause | None = None
        consumed = 1
        if index + 1 < len(sentences):
            rider = _group_tap_then_no_untap_pair(
                sentence, sentences[index + 1], for_spell=for_spell
            ) or _if_able_requirement_then_untap_pair(sentence, sentences[index + 1])
            consumed = 2
        if rider is None:
            consumed = 1
            rider = _other_creatures_cant_clause(sentence) or _cant_attack_block_activate_clause(
                sentence, for_spell=for_spell
            )
        if rider is None:
            run.append(sentence)
        else:
            found = True
            if run:
                parts.append(run)
                run = []
            parts.append(rider)
        index += consumed
    if not found:
        return None
    if run:
        parts.append(run)
    clauses: list[TargetedClause] = []
    for part in parts:
        if callable(part):
            clauses.append(part)
            continue
        read = _parse_mixed_clauses(" ".join(part), for_spell=for_spell)
        if read is None:
            return None
        clauses.extend(read)
    return clauses


#: The keywords a "loses `<keyword>`" removal may name: CR 702's keyword
#: abilities this engine reads off the computed board, so removing one is a
#: change something actually checks (CR 702.12b's indestructible chief among
#: them).
def _losable_keyword(word: str) -> str | None:
    lowered = word.strip().lower()
    known = {str(keyword).lower() for keyword in Keyword} | set(KEYWORDS_OUTSIDE_COMBAT)
    return lowered if lowered in known else None


def _lose_keyword_until_end_of_turn(
    game: "Game", permanent: CardState, keyword: str, source_name: str
) -> None:
    """CR 613.1f's layer 6 removal of one keyword from exactly this object
    (`only_this_incarnation`, CR 400.7) until end of turn (CR 611.2a). A
    later grant (a later timestamp, CR 613.7) gives it back."""
    store = continuous_effects(game)
    store.add(
        ContinuousEffect(
            description=f"{source_name}: {permanent.name} loses {keyword}",
            layer=Layer.ABILITY,
            timestamp=store.tick(),
            duration=Duration.UNTIL_END_OF_TURN,
            selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
            modification=lose_keyword(keyword),
        )
    )


#: "All `<group>` lose `<keyword>` until end of turn." - Hour of
#: Devastation's opening sentence. CR 613.1f's removal, which does change a
#: characteristic: CR 611.2c fixes the set as the effect begins, so a
#: creature that arrives later keeps its indestructible.
_GROUP_LOSES_KEYWORD_RE = re.compile(
    r"^all (?P<group>[a-z ]+?) lose (?P<keyword>[a-z]+(?: [a-z]+)?) until end of turn\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_group_loses_keyword_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_GROUP_LOSES_KEYWORD_RE`'s shape, the group read by
    `_parse_mass_type_qualifier` off the computed board (CR 613.5)."""
    match = _GROUP_LOSES_KEYWORD_RE.fullmatch(" ".join(clause.split()))
    if match is None:
        return None
    keyword = _losable_keyword(match.group("keyword"))
    if keyword is None:
        return None
    in_group = _parse_mass_type_qualifier(match.group("group"))
    if in_group is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        board = game.computed_board()
        for permanent in [p for p in game.battlefield if in_group(board.of(p))]:
            _lose_keyword_until_end_of_turn(game, permanent, keyword, source_name)

    return effect


#: "`<antecedent>`. `<it/that noun>` loses `<keyword>` until end of turn." -
#: Rebel Salvo's and Soul Sear's rider after their damage, read by
#: `text._parse_referent_object_clause` with this reader's own wording.
_RIDER_LOSES_KEYWORD_RE = re.compile(
    rf"^{_OBJECT_ANAPHOR} loses (?P<keyword>[a-z]+(?: [a-z]+)?) until end of turn$",
    re.IGNORECASE,
)


def _parse_loses_keyword_referent_rider(
    rider: str,
) -> Callable[["Game", list[CardState], "StackObject"], None] | None:
    """`_RIDER_LOSES_KEYWORD_RE`'s rider: each referent still on the
    battlefield loses the keyword until end of turn (CR 613.1f, CR 611.2a)."""
    match = _RIDER_LOSES_KEYWORD_RE.fullmatch(" ".join(rider.split()).rstrip("."))
    if match is None:
        return None
    keyword = _losable_keyword(match.group("keyword"))
    if keyword is None:
        return None

    def loses_keyword(
        game: "Game", referents: list[CardState], stack_object: "StackObject"
    ) -> None:
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        for referent in referents:
            if referent.zone is Zone.BATTLEFIELD:
                _lose_keyword_until_end_of_turn(game, referent, keyword, source_name)

    return loses_keyword


#: "[Until end of turn, ]`<target>` gains `<keywords>` and gets +N/+M for each
#: `<count>`[ until end of turn]." and its "gets +N/+M for each `<count>` and
#: gains `<keywords>`" word order - Fists of Flame's "Until end of turn,
#: target creature gains trample and gets +1/+0 for each card you've drawn
#: this turn.", Get a Leg Up's and Chorus of Might's "Until end of turn,
#: target creature gets +1/+1 for each creature you control and gains
#: reach/trample." One CR 608.2c instruction the "and" clause split would cut
#: in two; the count is taken once as the spell resolves (CR 608.2h), after
#: every earlier instruction of the spell (Fists of Flame's own draw).
_TARGET_GAINS_AND_PUMP_FOR_EACH_RE = re.compile(
    r"^(?:until end of turn, )?(?P<subject>(?:up to one )?target [^,.]+?) "
    r"(?:gains (?P<kw_first>[a-z ,]+?) and gets (?P<p_first>[+-]\d+)/(?P<t_first>[+-]\d+)"
    r" for each (?P<each_first>[^.]+?)"
    r"|gets (?P<p_last>[+-]\d+)/(?P<t_last>[+-]\d+) for each (?P<each_last>[^.]+?)"
    r" and gains (?P<kw_last>[a-z ,]+?))"
    r"(?: until end of turn)?\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s10")
def _parse_target_gains_and_pump_for_each_spell(text: str) -> Effect | None:
    """`_TARGET_GAINS_AND_PUMP_FOR_EACH_RE` as a spell's last sentence, the
    sentences before it read by the ordinary spell dispatcher and run first
    (CR 608.2c). The pump and the keywords are one layer effect built from
    the literal "+N/+M and gains ..." sentence with the count multiplied in
    (CR 611.2, CR 613.4c, CR 613.1f), applied to the target if still legal
    (CR 608.2b)."""
    lowered = text.lower()
    if "for each" not in " ".join(lowered.split()) or "gains" not in lowered:
        return None
    whole = " ".join(_strip_non_effect_preamble(text).split())
    sentences = _plain_resolution_sentences(whole)
    if not sentences:
        return None
    match = _TARGET_GAINS_AND_PUMP_FOR_EACH_RE.fullmatch(sentences[-1].strip())
    if match is None:
        return None
    subject = match.group("subject")
    if not _targets_understood(subject, count_agnostic=False):
        return None
    keywords = (match.group("kw_first") or match.group("kw_last")).strip()
    power = int(match.group("p_first") or match.group("p_last"))
    toughness = int(match.group("t_first") or match.group("t_last"))
    multiplier = _for_each_multiplier(match.group("each_first") or match.group("each_last"))
    if multiplier is None:
        return None

    def literal(count: int) -> str:
        return (
            f"Until end of turn, {subject} gets {power * count:+d}/{toughness * count:+d} "
            f"and gains {keywords}."
        )

    if parsed_layer_effects(literal(1)) is None:
        return None
    rest: Effect | None = None
    if len(sentences) > 1:
        rest = _spell_effect_or_notice(" ".join(sentences[:-1]))
        if rest is None or _is_notice_only(rest):
            return None

    def effect(game: "Game", spell: CardState) -> None:
        if rest is not None:
            rest(game, spell)
            game.announce_batched_events()
        controller = game.controller_of(spell)
        count = multiplier(game, controller.username, str(spell.id))
        builder = parsed_layer_effects(literal(count))
        if builder is None:
            continuous_effects(game).layer_notices.append(
                LayerNotice(source_id=spell.id, source_name=spell.card.name, text=literal(count))
            )
            return
        targets = game.resolve_card_targets(spell)
        if not targets:
            return
        store = continuous_effects(game)
        timestamp = store.tick()
        context = layer_context_for(game, controller)
        for built in builder(spell, timestamp, targets, context):
            if built.holds(game):
                store.add(built)

    return effect


#: "Double the power and toughness of target creature you control until end
#: of turn. Then it fights up to one target creature an opponent controls."
#: (Dragonclaw Strike) - CR 701.10a's doubling, then CR 701.14a's fight, one
#: CR 608.2c instruction whose "and toughness" the clause split would cut.
#: Read whole, ahead of the split, together with the pump and counter
#: antecedents `_parse_pump_then_fight_clause_pair` already reads (Chelonian
#: Tackle's "Target creature you control gets +0/+10 until end of turn. Then
#: it fights up to one target creature an opponent controls.").
_DOUBLE_TARGET_YOU_CONTROL_RE = re.compile(
    r"^double (?:the power and toughness of target creature you control"
    r"|target creature you control(?:'|’)s power and toughness) until end of turn$",
    re.IGNORECASE,
)


def _target_you_control_then_fights(text: str, *, for_spell: bool) -> TargetedClause | None:
    """The two sentences of a "creature you control is made bigger, then it
    fights" instruction. The pump and counter antecedents are handed to
    `_parse_pump_then_fight_clause_pair` unchanged; the doubling one is read
    here: the creature you control gets +X/+Y equal to its power and
    toughness as this resolves (CR 701.10b, sublayer 7c, CR 613.4c), then
    fights the opponent's creature if one was chosen (CR 115.6's "up to
    one") and both are still creatures on the battlefield (CR 701.14b)."""
    if "fights" not in text.lower():
        return None
    whole = " ".join(_strip_non_effect_preamble(text).split())
    sentences = _plain_resolution_sentences(whole)
    if len(sentences) != 2:
        return None
    first = sentences[0].strip().rstrip(".").strip()
    second = re.sub(r"^then\s+", "", sentences[1].strip(), flags=re.IGNORECASE)
    second = second.rstrip(".").strip()
    fight = _RIDER_FIGHTS_TARGET_RE.fullmatch(second)
    if fight is None:
        return None
    if _DOUBLE_TARGET_YOU_CONTROL_RE.fullmatch(first) is None:
        return _parse_pump_then_fight_clause_pair(first, second, for_spell=for_spell)
    if not _targets_understood(fight.group("phrase"), count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        mine = [t for t in targets if game.controller_of(t).username == controller]
        theirs = [t for t in targets if game.controller_of(t).username != controller]
        if not mine:
            return
        fighter = mine[0]
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        _double_power_and_toughness(game, fighter, source_name)
        if not theirs:
            return  # CR 115.6: "up to one" chose none, so nothing fights.
        opponent = theirs[0]
        if not game.characteristics_of(fighter).is_creature:
            return  # CR 701.14b
        if not game.characteristics_of(opponent).is_creature:
            return  # CR 701.14b
        _fight(game, fighter, opponent)

    return effect


@SPELL_TEXT.rung("s10")
def _parse_target_you_control_then_fights_spell(text: str) -> TargetedClause | None:
    """`_target_you_control_then_fights` on a resolving spell."""
    return _target_you_control_then_fights(text, for_spell=True)


@ABILITY_TEXT.rung("s11")
def _parse_target_you_control_then_fights_ability(text: str) -> TargetedClause | None:
    """`_target_you_control_then_fights` on a resolving ability."""
    return _target_you_control_then_fights(text, for_spell=False)


#: A counter or a pump on "target creature you control", then it fights or
#: bites (NW-03 T5): Ancient Animus' "Put a +1/+1 counter on target creature
#: you control if it's legendary. Then it fights target creature an opponent
#: controls.", Ent's Fury's "... if its power is 4 or greater. Then that
#: creature gets +1/+1 until end of turn and fights target creature you don't
#: control.", Throw from the Saddle's "Target creature you control gets +1/+1
#: until end of turn. Put a +1/+1 counter on it instead if it's a Mount. Then
#: it deals damage equal to its power to target creature you don't control."
#:
#: One CR 608.2c sequence over the same two targets `_parse_pump_then_fight_
#: clause_pair` splits by controller: the printed "if" is its own condition,
#: asked of the creature as that instruction resolves (never at announcement,
#: CR 601.2c) and answered by `Game.condition_holds` with the creature as the
#: object "it" names; "instead" replaces the pump with the counter (CR
#: 614.1a); the fight (CR 701.14a) or the bite (CR 120.3, damage with no
#: damage back) follows whatever the first instructions did, since a failed
#: condition does not stop "Then it fights".
_CHAIN_COUNTER_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    r"(?P<phrase>target (?:(?:non)?(?:white|blue|black|red|green) )?creature you control)"
    r"(?: if (?P<cond>.+))?$",
    re.IGNORECASE,
)
_CHAIN_INSTEAD_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on (?:it|that creature) "
    r"instead if (?P<cond>.+)$",
    re.IGNORECASE,
)
_CHAIN_FIGHT_RE = re.compile(
    r"^(?:it|that creature)(?: gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of turn"
    r" and)? fights (?P<phrase>(?:up to \S+ )?target .+)$",
    re.IGNORECASE,
)
_CHAIN_BITE_RE = re.compile(
    r"^(?:it|that creature) deals damage equal to its power to "
    r"(?P<phrase>(?:up to \S+ )?target .+)$",
    re.IGNORECASE,
)
_CHAIN_CONDITION_SUBJECT_RE = re.compile(r"^(?:it|its|it's|that creature)\b", re.IGNORECASE)


def _creature_condition_holds(
    game: "Game",
    stack_object: "StackObject",
    creature: CardState,
    condition: str,
    text: str,
) -> bool:
    """`condition` asked of `creature` as the object "it" names (CR 608.2c).
    One the shared reader cannot answer fails closed with a notice."""
    held = game.condition_holds(game.controller_of(stack_object).username, condition, creature)
    if held is not None:
        return held
    notice = ConditionalClauseNotice(
        source_id=source_id_of(stack_object),
        source_name=(
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        ),
        text=text,
    )
    if notice not in game.conditional_clause_notices:
        game.conditional_clause_notices.append(notice)
    return False


def _target_you_control_chain(text: str, *, for_spell: bool) -> TargetedClause | None:
    """The counter-or-pump-then-fight-or-bite sequences above, or `None`.

    Only the shapes `_parse_pump_then_fight_clause_pair` and the plain bite
    readers do not already read are claimed here: a conditional counter, an
    "instead" counter after a pump, or a fight rider that pumps as well."""
    lowered = text.lower()
    if "you control" not in lowered or not (
        "fights" in lowered or "deals damage equal to its power" in lowered
    ):
        return None
    sentences = [
        sentence.strip().rstrip(".").strip()
        for sentence in _plain_resolution_sentences(
            " ".join(_strip_non_effect_preamble(text).split())
        )
    ]
    if len(sentences) not in (2, 3):
        return None
    pump = _PUMP_TARGET_YOU_CONTROL_RE.fullmatch(sentences[0])
    counter = None if pump is not None else _CHAIN_COUNTER_RE.fullmatch(sentences[0])
    if pump is None and counter is None:
        return None
    instead = None
    if len(sentences) == 3:
        if pump is None:
            return None
        instead = _CHAIN_INSTEAD_RE.fullmatch(sentences[1])
        if instead is None:
            return None
    rider_text = re.sub(r"^then\s+", "", sentences[-1], flags=re.IGNORECASE)
    fight = _CHAIN_FIGHT_RE.fullmatch(rider_text)
    bite = None if fight is not None else _CHAIN_BITE_RE.fullmatch(rider_text)
    if fight is None and bite is None:
        return None
    gated = counter is not None and counter.group("cond") is not None
    if not (gated or instead is not None or (fight is not None and fight.group("power"))):
        return None
    antecedent = pump if pump is not None else counter
    assert antecedent is not None
    victim_phrase = (fight or bite).group("phrase")  # type: ignore[union-attr]
    if not _targets_understood(antecedent.group("phrase"), count_agnostic=True):
        return None
    if not _targets_understood(victim_phrase, count_agnostic=True):
        return None
    conditions = [
        group
        for group in (
            counter.group("cond") if counter is not None else None,
            instead.group("cond") if instead is not None else None,
        )
        if group is not None
    ]
    for condition in conditions:
        condition = condition.strip()
        if _CHAIN_CONDITION_SUBJECT_RE.match(condition) is None:
            return None
        if not _effect_condition_is_readable(condition, allow_anaphor=True):
            return None

    def pump_builder(power: str, toughness: str):
        return parsed_layer_effects(f"Target creature gets {power}/{toughness} until end of turn.")

    antecedent_builder = (
        pump_builder(pump.group("power"), pump.group("toughness")) if pump is not None else None
    )
    rider_builder = (
        pump_builder(fight.group("power"), fight.group("toughness"))
        if fight is not None and fight.group("power")
        else None
    )
    if (pump is not None and antecedent_builder is None) or (
        fight is not None and fight.group("power") and rider_builder is None
    ):
        return None
    counter_source = instead if instead is not None else counter
    amount = parse_count(counter_source.group("n")) if counter_source is not None else None
    if counter_source is not None and amount is None:
        return None
    kind = _counter_kind(counter_source.group("kind")) if counter_source is not None else None
    sentence_text = " ".join(sentences)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        mine = [t for t in targets if game.controller_of(t).username == controller.username]
        theirs = [t for t in targets if game.controller_of(t).username != controller.username]
        if not mine:
            return
        creature = mine[0]
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        if source is None:
            return
        effects = game.continuous_effects

        def pump_creature(builder) -> None:
            for built in builder(
                source, effects.tick(), [creature], layer_context_for(game, controller)
            ):
                effects.add(built, game)

        if antecedent_builder is not None:
            if instead is not None and _creature_condition_holds(
                game, stack_object, creature, instead.group("cond").strip(), sentence_text
            ):
                game.add_counters(creature, kind, amount)
            else:
                pump_creature(antecedent_builder)
        elif counter.group("cond") is None or _creature_condition_holds(  # type: ignore[union-attr]
            game,
            stack_object,
            creature,
            counter.group("cond").strip(),
            sentence_text,  # type: ignore[union-attr]
        ):
            game.add_counters(creature, kind, amount)
        if rider_builder is not None:
            pump_creature(rider_builder)
        if bite is not None:
            _resolve_bite_damage(game, stack_object, "power")
            return
        if not theirs:
            return  # CR 115.6: "up to one" chose none, so nothing fights.
        opponent = theirs[0]
        if not game.characteristics_of(creature).is_creature:
            return  # CR 701.14b
        if not game.characteristics_of(opponent).is_creature:
            return  # CR 701.14b
        _fight(game, creature, opponent)

    return effect


@SPELL_TEXT.rung("s10")
def _parse_target_you_control_chain_spell(text: str) -> TargetedClause | None:
    """`_target_you_control_chain` on a resolving spell."""
    return _target_you_control_chain(text, for_spell=True)


@ABILITY_TEXT.rung("s11")
def _parse_target_you_control_chain_ability(text: str) -> TargetedClause | None:
    """`_target_you_control_chain` on a resolving ability."""
    return _target_you_control_chain(text, for_spell=False)


#: "<Antecedent>. It gains protection from the color of your choice until end
#: of turn." (Feat of Resistance after its counter, Pristine Skywise after
#: "Untap this creature.") and "<Antecedent>. Those creatures can't block this
#: turn." (Sparkmage's Gambit, Wrap in Flames, Rowan, Fearless Sparkmage's -2):
#: a second sentence whose "it"/"those creatures" is whatever the first one
#: acted on (CR 608.2c), found by `_referent_reader` before the first runs.
#: Each referent that is still on the battlefield afterwards gets the rider;
#: one the antecedent removed, or that was no longer a legal target (CR
#: 608.2b), gets nothing, and no colour is asked for when none is left.
_ANAPHOR_PROTECTION_RE = re.compile(
    r"^(?:it|that (?:creature|permanent)) gains protection from the color of your choice "
    r"until end of turn$",
    re.IGNORECASE,
)
#: "If it's legendary, it also gains trample until end of turn." (Gimli's Fury,
#: Blessing of Belzenlok) - a conditional rider on what the antecedent acted
#: on. The condition is asked of the referent itself (CR 205.4d's supertype,
#: read off its computed characteristics as the instruction resolves, CR
#: 608.2c), not of the spell, and "also" only says the grant adds to the
#: antecedent's effect.
_CONDITIONAL_ALSO_RIDER_RE = re.compile(
    r"^if (?P<condition>(?:it|that creature)(?:'s| is| has)\b[^,]*), "
    r"(?P<rider>(?:it|that creature) also (?:gains|gets|has) .+)$",
    re.IGNORECASE,
)
_THOSE_CANT_RE = re.compile(
    r"^those (?:creatures|permanents) can['\u2019]?t (?P<what>block|attack) this turn$",
    re.IGNORECASE,
)


def _antecedent_then_referent_rider(text: str, *, for_spell: bool) -> TargetedClause | None:
    """The two sentences `_ANAPHOR_PROTECTION_RE` and `_THOSE_CANT_RE` close, or
    `None`."""
    lowered = text.lower()
    if not (
        "protection from the color of your choice" in lowered
        or "those " in lowered
        or " also gains " in lowered
    ):
        return None
    sentences = [
        sentence.strip().rstrip(".").strip()
        for sentence in _plain_resolution_sentences(
            " ".join(_strip_non_effect_preamble(text).split())
        )
    ]
    if len(sentences) != 2:
        return None
    first, second = sentences
    protection = _ANAPHOR_PROTECTION_RE.fullmatch(second)
    cant = None if protection is not None else _THOSE_CANT_RE.fullmatch(second)
    conditional = (
        None
        if protection is not None or cant is not None
        else _CONDITIONAL_ALSO_RIDER_RE.fullmatch(second)
    )
    if protection is None and cant is None and conditional is None:
        return None
    granted = None
    if conditional is not None:
        condition = conditional.group("condition").strip()
        if not _effect_condition_is_readable(condition, allow_anaphor=True):
            return None
        granted = _parse_referent_object_clause(
            re.sub(r"\balso\s+", "", conditional.group("rider"), count=1, flags=re.IGNORECASE)
        )
        if granted is None:
            return None
    referent_of = _referent_reader(first)
    if referent_of is None:
        return None
    first_sentence = f"{first}."
    antecedent = (
        parse_mixed_effect_for_spell(first_sentence)
        if for_spell
        else parse_mixed_effect(first_sentence)
    )
    if antecedent is None or _is_notice_only(antecedent):
        return None
    line = f"This creature can't {cant.group('what').lower()}." if cant is not None else ""

    def effect(game: "Game", stack_object: "StackObject") -> None:
        referents = referent_of(game, stack_object)
        antecedent(game, stack_object)
        referents = [r for r in referents if r.zone is Zone.BATTLEFIELD]
        if not referents:
            return  # CR 608.2b: nothing left for the rider to name.
        if protection is not None:
            _grant_chosen_color_protection(game, stack_object, referents[0])
            return
        if granted is not None:
            for referent in referents:
                if _creature_condition_holds(game, stack_object, referent, condition, second):
                    granted(game, [referent], stack_object)
            return
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        store = continuous_effects(game)
        for referent in referents:
            store.add(
                ContinuousEffect(
                    description=f"{source_name}: {referent.name} {line[5:-1].lower()} this turn",
                    layer=Layer.ABILITY,
                    timestamp=store.tick(),
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=only_this_incarnation(referent, referent.zone_change_stamp),
                    modification=grant_ability(line),
                )
            )

    return effect


@SPELL_TEXT.rung("s10")
def _parse_antecedent_then_referent_rider_spell(text: str) -> TargetedClause | None:
    """`_antecedent_then_referent_rider` on a resolving spell."""
    return _antecedent_then_referent_rider(text, for_spell=True)


@ABILITY_TEXT.rung("s11")
def _parse_antecedent_then_referent_rider_ability(text: str) -> TargetedClause | None:
    """`_antecedent_then_referent_rider` on a resolving ability."""
    return _antecedent_then_referent_rider(text, for_spell=False)


@ABILITY_TEXT.rung("s11")
def _parse_turn_face_up_or_exile_and_cast_clause(text: str) -> AbilityEffect | None:
    """ "Turn this creature face up. If you can't, exile it, then you may cast
    the exiled card without paying its mana cost." - read and performed by
    `machines/face_down_keywords.read_turn_up_or_exile_and_cast`."""
    from ..face_down_keywords import read_turn_up_or_exile_and_cast

    if "face up" not in text.lower():
        return None
    return read_turn_up_or_exile_and_cast(text)


from ._common import (  # noqa: E402
    _ANAPHOR_GAINS_KEYWORDS_RE,
    _COLOR_LETTERS,
    _COST_INCREASE_PER_TARGET_LINE_RE,
    _DESTROY_TARGET_RE,
    _GET_AN_EMBLEM_RE,
    _MANA_SYMBOL_RE,
    _MASS_CREATURE_SUBJECT_RE,
    _SOURCE_CHARACTERISTIC_RE,
    _TAP_UNTAP_TARGET_RE,
    _TOKEN_CLAUSE_RE,
    _TOKEN_COLOR_WORDS,
    ConditionalClauseNotice,
    LayerRemainderNotice,
    PlayerSubjectSplitNotice,
    UnmodeledTriggerEffectNotice,
    _effect_condition_is_readable,
    _opponents,
    _parse_delayed_timing_clause,
    _parse_mass_type_qualifier,
    _permanent_id_and_name,
    _targets_understood,
    computed_permanents,
    pay_consequence_effect,
)
from .amounts import (  # noqa: E402
    _carry_count,
    _for_each_multiplier,
    _that_many_or_notice,
    amount_expression,
    count_expression,
    that_many,
)
from .control_copy import _mass_control_group  # noqa: E402
from .counters import _counter_kind, _source_still_here  # noqa: E402
from .damage import (  # noqa: E402
    _defending_player_of_trigger,
    _fight,
    _resolve_bite_damage,
    damage_to_layer_target_rider,
)
from .dispatch import (  # noqa: E402
    _ability_effect_or_notice,
    _parse_mixed_clause,
    _parse_mixed_clauses,
    _parse_targeted_clause,
    _spell_effect_or_notice,
    parse_clause_effect,
    parse_mixed_effect,
    parse_mixed_effect_for_spell,
)
from .draw_discard import _discard_cards, _source_characteristic, draw_cards  # noqa: E402
from .library import _looks_like_embedded_ability_line  # noqa: E402
from .modal import (  # noqa: E402
    _choose_a_color,
    _condition_holds_for_stack_object,
    reflexive_consequence_effect,
)
from .removal import _sacrifice_restriction  # noqa: E402
from .returns import (  # noqa: E402
    _matches_subtype_on_battlefield,
    _two_battlefield_targets_understood,
)
from .text import (  # noqa: E402
    _as_capitalized_sentence,
    _as_sentence,
    _parse_object_anaphor_clause_series,
    _parse_referent_object_clause,
    _plain_resolution_sentences,
    _referent_of_it,
    _referent_reader,
    _self_referential_delayed_effect,
    _singular_subtype_for_transform_all,
    _split_choice_keywords,
    _strip_non_effect_preamble,
)
from .tokens import (  # noqa: E402
    _create_continuous_effect_for_mode_text,
    _create_continuous_effect_of_ability_for_mode_text,
    _is_notice_only,
    _parse_generic_token_descriptor,
    create_continuous_effect,
    create_continuous_effect_of_ability,
)

#: "The chosen creature gains indestructible until end of turn." (Dauntless
#: Bodyguard) - CR 613.1f's grant to the object the source's as-enters choice
#: recorded (CR 614.12a, `named_choice_rows.chosen_object`), not a target.
_CHOSEN_OBJECT_GAINS_RE = re.compile(
    r"^the chosen (?:creature|permanent) gains (?P<keywords>[a-z][a-z, ]*?)"
    r"(?P<duration> until end of turn)?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_chosen_object_gains_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_CHOSEN_OBJECT_GAINS_RE`'s shape; a chosen creature that is gone gains
    nothing (CR 608.2b)."""
    if for_spell or "the chosen" not in clause.lower():
        return None
    match = _CHOSEN_OBJECT_GAINS_RE.fullmatch(clause.strip())
    if match is None:
        return None
    keywords = _split_and_validate_keywords(match.group("keywords").strip())
    if keywords is None:
        return None
    duration = "until end of turn" if match.group("duration") else None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from ..named_choice_rows import chosen_object

        chosen = chosen_object(game, stack_object)
        if chosen is None:
            return
        _grant_keywords_to(
            game,
            chosen,
            keywords,
            duration,
            controller=game.controller_of(stack_object).username,
            source_name=getattr(stack_object, "source_name", ""),
        )

    return effect


#: "tap all lands that player controls" (War's Toll) - CR 701.26a's tap of
#: every permanent of the type the triggering event's player (CR 603.2, the
#: opponent who tapped a land for mana) controls now.
_TAP_ALL_THAT_PLAYER_CONTROLS_RE = re.compile(
    r"^tap all (?P<what>lands|creatures|artifacts|permanents) that player controls\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_tap_all_that_player_controls_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TAP_ALL_THAT_PLAYER_CONTROLS_RE`'s shape; ability-only (a spell has
    no triggering event to name "that player")."""
    if for_spell or "that player controls" not in clause.lower():
        return None
    match = _TAP_ALL_THAT_PLAYER_CONTROLS_RE.fullmatch(clause.strip())
    if match is None:
        return None
    what = match.group("what").lower()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        event = getattr(stack_object, "event", None)
        player = None if event is None else (event.player or event.subject_controller)
        if player is None or not game.is_in_game(player):
            return
        board = game.computed_board()
        for permanent in list(game.battlefield):
            if game.controller_of(permanent).username != player:
                continue
            stats = board.of(permanent)
            kind = {
                "lands": stats.is_land,
                "creatures": stats.is_creature,
                "artifacts": Type.ARTIFACT in stats.types,
                "permanents": True,
            }[what]
            if kind:
                game.tap_permanent(permanent)

    return effect


#: Zenos yae Galvus: "choose a creature an opponent controls. Until end of
#: turn, creatures other than Zenos yae Galvus and the chosen creature get
#: -2/-2." - CR 608.2d's resolution-time choice (recorded on the source for its
#: later "the chosen creature", `named_choice_rows.choose_and_record_object`),
#: then a P/T change whose affected set is fixed as it begins (CR 611.2c).
_CHOOSE_THEN_OTHERS_GET_RE = re.compile(
    r"^choose a creature(?: (?P<whose>an opponent|you) controls?)?\.\s*"
    r"(?:until end of turn, )?creatures other than (?:this creature|[^,.]+?) and the chosen "
    r"creature get (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)(?: until end of turn)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_choose_creature_then_others_get_text(text: str) -> AbilityEffect | None:
    """`_CHOOSE_THEN_OTHERS_GET_RE`'s shape; "until end of turn" is required
    in one of its two printed positions."""
    lowered = text.lower()
    if "and the chosen creature get" not in lowered or "until end of turn" not in lowered:
        return None
    match = _CHOOSE_THEN_OTHERS_GET_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))
    whose = (match.group("whose") or "").lower()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        from ..named_choice_rows import choose_and_record_object

        controller = game.controller_of(ability).username
        board = game.computed_board()
        creatures = [state for state in game.battlefield if board.of(state).is_creature]
        candidates = [
            state
            for state in creatures
            if not whose or (whose == "you") == (game.controller_of(state).username == controller)
        ]
        chosen = choose_and_record_object(
            game, ability, candidates, prompt=f"choose a creature {whose} controls".strip()
        )
        source = ability.source(game)
        excluded = {state.id for state in (source, chosen) if state is not None}
        store = game.continuous_effects
        timestamp = store.tick()
        name = ability.source_name
        for creature in creatures:
            if creature.id in excluded or creature.zone is not Zone.BATTLEFIELD:
                continue
            store.add(
                ContinuousEffect(
                    description=f"{name}: {creature.name} gets {power:+}/{toughness:+}",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=_only(creature.id),
                    modification=modify_power_toughness(power, toughness),
                )
            )

    return effect


#: Sandswirl Wanderglyph: "they can't attack you or planeswalkers you control
#: this turn." - the triggering event's player (CR 603.2: the opponent who cast
#: the spell) is barred for the rest of the turn (CR 508.1c), a rules change
#: kept by `opponent_attack_restrictions.record_cant_attack`.
_THEY_CANT_ATTACK_YOU_THIS_TURN_RE = re.compile(
    r"^(?:they|that player) can'?t attack you(?: or planeswalkers you control)? this turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_they_cant_attack_you_this_turn_text(text: str) -> AbilityEffect | None:
    """`_THEY_CANT_ATTACK_YOU_THIS_TURN_RE`'s shape."""
    if "attack you" not in text.lower():
        return None
    if _THEY_CANT_ATTACK_YOU_THIS_TURN_RE.fullmatch(" ".join(text.strip().split())) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        from ..opponent_attack_restrictions import record_cant_attack

        event = ability.event
        restricted = None if event is None else event.player
        if restricted is None or restricted == ability.controller:
            return
        record_cant_attack(game, restricted, ability.controller, ability.source_name)

    return effect


#: Elbrus, the Binding Blade: "unattach Elbrus, then transform it." - CR
#: 701.3d's unattach of the source itself (named by its own name or "this
#: Equipment"/"this Aura"), then, in order (CR 608.2c), the source's own
#: transform (CR 701.27a).
_UNATTACH_SELF_RE = re.compile(
    r"^unattach (?P<self>(?i:this (?:equipment|aura|fortification))|"
    r"(?!All |Each |Target |Any )[A-Z][^,.]*?)"
    r"(?P<transform>, then transform (?i:it|this (?:equipment|aura|permanent)))?\.?$"
)


@ABILITY_TEXT.rung("s28")
def _parse_unattach_self_then_transform_text(text: str) -> AbilityEffect | None:
    """`_UNATTACH_SELF_RE`'s shape; a source that has left the battlefield is
    a new object (CR 400.7) and nothing happens, and the transform obeys CR
    701.27f through the shared self-transform reader."""
    stripped = " ".join(text.strip().split())
    if not stripped.lower().startswith("unattach "):
        return None
    match = _UNATTACH_SELF_RE.fullmatch(stripped[0].lower() + stripped[1:])
    if match is None:
        return None
    transform_self = (
        parse_mixed_effect("Transform this permanent.") if match.group("transform") else None
    )
    if match.group("transform") and transform_self is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        source.unattach()
        if transform_self is not None:
            transform_self(game, ability)

    return effect
