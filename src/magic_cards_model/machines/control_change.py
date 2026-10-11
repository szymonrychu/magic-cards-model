"""Control-changing effects with a stated duration (CR 613.1b, layer 2), and
the "tap it; it loses all abilities / doesn't untap / can't become untapped
for as long as ..." riders that ride on the same kind of one-shot
instruction.

Entry points `control_change_ability_effect`/`control_change_spell_effect`
are tried by `machines/effects.py` ahead of its clause split: every shape
here is two sentences joined by an anaphor ("It", "That creature"), which
`_prepare_effect_clauses` would cut apart.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..models.card import Color
from ..models.card_state import CANT_BECOME_UNTAPPED_TEXT, CardState
from ..models.player import Player
from ..models.zone import Zone
from .layers import (
    CANT_ACTIVATE_ABILITIES_TEXT,
    DOESNT_UNTAP_TEXT,
    Characteristics,
    Condition,
    ContinuousEffect,
    Duration,
    Layer,
    Modification,
    RemainsOnBattlefield,
    RemainsTapped,
    YouStillControl,
    grant_ability,
    lose_all_abilities,
    only_this_incarnation,
    set_controller,
)

if TYPE_CHECKING:
    from ..models.game import Game
    from .effects import AbilityEffect, Effect
    from .triggers import AbilityOnStack

#: A self-reference: "this <noun>" once `self_normalized_effect_text` has
#: rewritten the card's own name, or the printed name itself (CR 201.5: a
#: card's name in its own text means that object) - `trigger_effect_for`
#: tries the unnormalized text first.
_SELF = (
    r"(?:this (?:creature|permanent|saga|enchantment|artifact|land|planeswalker)"
    r"|[A-Z][^.]*?)"
)

#: "Tap `<target>`. `<It|That creature|They|...>` `<rider>` for as long as
#: `<you control this|this remains on the battlefield>`." - The Wondrous Wasp
#: ("It loses all abilities for as long as The Wondrous Wasp remains on the
#: battlefield"), Spider-Woman, Secret Agent ("That creature can't become
#: untapped for as long as you control Spider-Woman"), Dungeon Geists, Ty Lee,
#: Chi Blocker, Icefall Regent, Tidebinder Mage and Time of Ice ("... doesn't
#: untap during its controller's untap step for as long as you control ...").
#:
#: CR 701.26a taps each target; the rider is a layer 6 effect (CR 613.1f)
#: with CR 611.2b's "for as long as" duration, which is the *source's*: it
#: never starts if the source is already gone (or already out of its
#: controller's hands) as the ability resolves, and the tap still happens.
_TAP_THEN_LOCK_RE = re.compile(
    r"^tap (?P<phrase>(?:up to (?:one|two|three|four|\d+) )?(?:another )?target [^.]+?)\.\s*"
    r"(?:"
    r"(?:it|that creature|that permanent|those creatures|those permanents|they) "
    r"(?P<rider>loses? all abilities"
    r"|(?:doesn'?t|don'?t) untap during (?:its controller'?s|their controllers'?) untap steps?"
    r"|can'?t become untapped)"
    r"|"
    r"(?:its|their) (?P<activation_lock>activated abilities can'?t be activated)"
    r")"
    rf" for as long as (?:you control (?P<controlled>{_SELF})|(?P<remains>{_SELF}) remains "
    r"on the battlefield|(?P<tapped>it remains tapped)"
    # Deserter's Quarters, Rust Tick, Entrancing Lyre: "... for as long as
    # this artifact remains tapped" - the *source's* tapped status.
    rf"|(?P<source_tapped>{_SELF}) remains tapped)\.?$",
    re.IGNORECASE,
)


def _lock_condition(
    game: Game,
    ability: AbilityOnStack,
    target: CardState | None = None,
    *,
    duration_kind: str,
) -> Condition | None:
    """The CR 611.2b condition this rider's duration builds, or `None` when it
    never starts.

    `duration_kind` is `"controlled"` (the source's controller), `"remains"`
    (the source staying on the battlefield) or `"tapped"` (Braided Net's own
    "for as long as it remains tapped" - the *target*'s own tapped status,
    not the source's, since `target` is what was just tapped, and CR 611.2b's
    duration is read off whatever the sentence actually names). Only
    `"tapped"` reads `target`; the other two never pass one.
    """
    if duration_kind == "source_tapped":
        source = ability.source(game)
        if (
            source is None
            or source.zone is not Zone.BATTLEFIELD
            or source.zone_change_stamp is None
            or not source.tapped
            or (
                ability.source_stamp is not None
                and source.zone_change_stamp != ability.source_stamp
            )
        ):
            return None
        return RemainsTapped(card_id=source.id, stamp=source.zone_change_stamp)
    if duration_kind == "tapped":
        assert target is not None
        if target.zone is not Zone.BATTLEFIELD or target.zone_change_stamp is None:
            return None
        return RemainsTapped(card_id=target.id, stamp=target.zone_change_stamp)
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD or source.zone_change_stamp is None:
        return None
    if ability.source_stamp is not None and source.zone_change_stamp != ability.source_stamp:
        return None
    if duration_kind == "controlled":
        if source.controller != ability.controller:
            return None
        return YouStillControl(
            card_id=source.id, stamp=source.zone_change_stamp, controller=ability.controller
        )
    return RemainsOnBattlefield(card_id=source.id, stamp=source.zone_change_stamp)


def _rider_modification(rider: str | None, *, activation_lock: bool) -> tuple[str, Modification]:
    if activation_lock:
        return "activated abilities can't be activated", grant_ability(CANT_ACTIVATE_ABILITIES_TEXT)
    assert rider is not None
    lowered = rider.lower()
    if lowered.startswith("lose"):
        return "loses all abilities", lose_all_abilities
    if lowered.startswith("can"):
        return "can't become untapped", grant_ability(CANT_BECOME_UNTAPPED_TEXT)
    return "doesn't untap during its controller's untap step", grant_ability(DOESNT_UNTAP_TEXT)


def _parse_tap_then_lock_clause(effect_text: str) -> AbilityEffect | None:
    """`_TAP_THEN_LOCK_RE`'s shape, or `None`."""
    from .effects import _targets_understood

    match = _TAP_THEN_LOCK_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    activation_lock = match.group("activation_lock") is not None
    what, modification = _rider_modification(match.group("rider"), activation_lock=activation_lock)
    if match.group("tapped") is not None:
        duration_kind = "tapped"
    elif match.group("source_tapped") is not None:
        duration_kind = "source_tapped"
    elif match.group("controlled") is not None:
        duration_kind = "controlled"
    else:
        duration_kind = "remains"

    def effect(game: Game, ability: AbilityOnStack) -> None:
        targets = [
            target
            for target in game.resolve_card_targets(ability)
            if target.zone is Zone.BATTLEFIELD
        ]
        for target in targets:
            target.tap_if_untapped()
        store = game.continuous_effects
        timestamp = store.tick()
        for target in targets:
            condition = _lock_condition(game, ability, target, duration_kind=duration_kind)
            if condition is None:
                continue
            store.add(
                ContinuousEffect(
                    description=f"{ability.source_name}: {target.name} {what}",
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    duration=Duration.FOR_AS_LONG_AS,
                    condition=condition,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=modification,
                ),
                game=game,
            )

    return effect


#: "Gain control of `<target>` for as long as `<you control this|this remains
#: on the battlefield>`.[ Then `<instruction>`.]" - The Super Hero Civil
#: War's chapter I ("Gain control of up to two target creatures with total
#: mana value 6 or less for as long as this Saga remains on the battlefield.")
#: and Rangers of Ithilien ("... gain control of up to one target creature
#: with lesser power for as long as you control this creature. Then the Ring
#: tempts you."). Layer 2 (CR 613.1b) with CR 611.2b's duration, which is the
#: source's: if it never starts, nothing is stolen, and the "Then"
#: instruction still happens.
_GAIN_CONTROL_FOR_AS_LONG_RE = re.compile(
    r"^gain control of (?P<phrase>(?:up to (?:one|two|three|\d+) )?target [^.]+?) "
    rf"for as long as (?:you control (?P<controlled>{_SELF})|(?P<remains>{_SELF}) remains "
    # Vedalken Shackles: "... for as long as this artifact remains tapped."
    rf"on the battlefield|(?P<source_tapped>{_SELF}) remains tapped)\.(?:\s*then (?P<rest>.+))?$",
    re.IGNORECASE,
)


def _parse_gain_control_for_as_long_clause(effect_text: str) -> AbilityEffect | None:
    """`_GAIN_CONTROL_FOR_AS_LONG_RE`'s shape, or `None`."""
    from .effects import _targets_understood, parse_mixed_effect

    match = _GAIN_CONTROL_FOR_AS_LONG_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    rest = None
    if match.group("rest"):
        rest = parse_mixed_effect(match.group("rest").strip())
        if rest is None:
            return None
    if match.group("controlled") is not None:
        duration_kind = "controlled"
    elif match.group("source_tapped") is not None:
        duration_kind = "source_tapped"
    else:
        duration_kind = "remains"

    def effect(game: Game, ability: AbilityOnStack) -> None:
        condition = _lock_condition(game, ability, duration_kind=duration_kind)
        targets = [
            target
            for target in game.resolve_card_targets(ability)
            if target.zone is Zone.BATTLEFIELD
        ]
        if condition is not None and targets:
            store = game.continuous_effects
            timestamp = store.tick()
            for target in targets:
                store.add(
                    ContinuousEffect(
                        description=(
                            f"{ability.source_name}: {ability.controller} gains control of "
                            f"{target.name}"
                        ),
                        layer=Layer.CONTROL,
                        timestamp=timestamp,
                        duration=Duration.FOR_AS_LONG_AS,
                        condition=condition,
                        selector=only_this_incarnation(target, target.zone_change_stamp),
                        modification=set_controller(ability.controller),
                    ),
                    game=game,
                )
        if rest is not None:
            rest(game, ability)

    return effect


#: "Gain control of all `<description>` target player/opponent controls." -
#: Emrakul, the World Anew's own cast trigger, Ashiok, Sculptor of Fears'
#: -11 ("... target opponent controls."), Gilt-Leaf Archdruid's own tap
#: ability ("... target player controls."), and the compound-description
#: form on Tezzeret, Master of Metal's -8 ("all artifacts and creatures
#: target opponent controls."). No stated duration, so CR 611.2a's default
#: applies (lasts until the end of the game - `Duration.INDEFINITE`), the
#: same as `parse_gain_control_untimed_clause` below, except the
#: object here is never itself a target: CR 115.10a's untargeted "all
#: `<description>`" among one *targeted player's* own permanents, read with
#: `machines/targeting.permanent_description` the same way `_parse_all_of_
#: target_player_then_referent_pair` (Settle the Wreckage) already reads an
#: identical "all `<description>` target player controls" grammar for a
#: destroy/exile effect instead of a control change.
_GAIN_CONTROL_OF_ALL_TARGET_PLAYERS_RE = re.compile(
    r"^gain control of all (?P<description>.+?) target (?P<who>player|opponent) controls\.?$",
    re.IGNORECASE,
)


def _parse_gain_control_of_all_target_players_clause(effect_text: str) -> AbilityEffect | None:
    """`_GAIN_CONTROL_OF_ALL_TARGET_PLAYERS_RE`'s shape, or `None`.

    The group is read off the computed board (CR 613.5) once, as the ability
    resolves - CR 611.2c: the set a control-changing continuous effect
    affects "is determined when that continuous effect begins" - so a
    permanent the target player already lost control of (or that left the
    battlefield) by then is correctly excluded, the same "fixed set now"
    reading `_parse_mass_gain_control_untap` uses for an untargeted "all
    `<description>` until end of turn" group.
    """
    from .effects import _targets_understood
    from .targeting import permanent_description

    match = _GAIN_CONTROL_OF_ALL_TARGET_PLAYERS_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    if not _targets_understood(f"target {match.group('who')}", allow_player_targets=True):
        return None
    requirement = permanent_description(match.group("description"))
    if requirement is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        players = [target for target in game.resolve_targets(ability) if isinstance(target, Player)]
        if not players:
            return
        player = players[0]
        group = [
            permanent
            for permanent in game.permanents_controlled_by(player.username)
            if requirement.rejects(permanent, player.username, game) is None
        ]
        if not group:
            return
        store = game.continuous_effects
        timestamp = store.tick()
        for target in group:
            store.add(
                ContinuousEffect(
                    description=(
                        f"{ability.source_name}: {ability.controller} gains control of "
                        f"{target.name}"
                    ),
                    layer=Layer.CONTROL,
                    timestamp=timestamp,
                    duration=Duration.INDEFINITE,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=set_controller(ability.controller),
                ),
                game=game,
            )

    return effect


#: "Gain control of target creature until end of turn. If you control a[n]
#: `<quality>` with greater mana value than that creature, gain control of
#: that creature until the end of your next turn instead.[ Untap that
#: creature.][ It gains `<keywords>` until end of turn.]" - Evil's Thrall.
#: The "instead" is decided as the spell resolves, against the computed mana
#: values (CR 202.3, CR 613.5) of the permanents its controller controls
#: then; "until the end of your next turn" is CR 611.2a's stated duration
#: (`Duration.UNTIL_END_OF_YOUR_NEXT_TURN`).
_GAIN_CONTROL_LONGER_IF_RE = re.compile(
    r"^gain control of (?P<phrase>target [^.]+?) until end of turn\.\s*"
    r"if you control an? (?P<quality>[a-z]+) with greater mana value than that creature, "
    r"gain control of that creature until the end of your next turn instead\."
    r"(?P<untap>\s*untap (?:that creature|it)\.)?"
    r"(?:\s*(?:it|that creature) gains (?P<keywords>[a-z][a-z ,]*?) until end of turn\.?)?$",
    re.IGNORECASE,
)


def _quality_matcher(word: str) -> Callable[[Characteristics], bool] | None:
    """A card type (CR 205.2a) or a subtype (CR 205.3) as a test on computed
    characteristics - `None` for a word that is neither."""
    from .layers import _card_type_word, _singular_subtype_word

    card_type = _card_type_word(word)
    if card_type is not None:
        return lambda chars: card_type in chars.types
    subtype = _singular_subtype_word(word)
    if subtype is None:
        return None
    return lambda chars: any(each.lower() == subtype.lower() for each in chars.subtypes)


def _parse_gain_control_longer_if_clause(effect_text: str) -> Effect | None:
    """`_GAIN_CONTROL_LONGER_IF_RE`'s shape, or `None`."""
    from .effects import _targets_understood
    from .layers import _split_and_validate_keywords

    match = _GAIN_CONTROL_LONGER_IF_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    has_quality = _quality_matcher(match.group("quality"))
    if has_quality is None:
        return None
    keywords: list[str] = []
    if match.group("keywords"):
        validated = _split_and_validate_keywords(match.group("keywords"))
        if validated is None:
            return None
        keywords = validated
    untap = match.group("untap") is not None

    def effect(game: Game, spell: CardState) -> None:
        caster = game.controller_of(spell).username
        store = game.continuous_effects
        for target in game.resolve_card_targets(spell):
            if target.zone is not Zone.BATTLEFIELD:
                continue
            target_value = game.characteristics_of(target).mana_value
            longer = any(
                has_quality(chars) and chars.mana_value > target_value
                for chars in (
                    game.characteristics_of(permanent)
                    for permanent in game.permanents_controlled_by(caster)
                )
            )
            timestamp = store.tick()
            selector = only_this_incarnation(target, target.zone_change_stamp)
            store.add(
                ContinuousEffect(
                    description=f"{spell.name}: {caster} gains control of {target.name}",
                    layer=Layer.CONTROL,
                    timestamp=timestamp,
                    duration=(
                        Duration.UNTIL_END_OF_YOUR_NEXT_TURN
                        if longer
                        else Duration.UNTIL_END_OF_TURN
                    ),
                    until_next_turn_of=caster if longer else None,
                    selector=selector,
                    modification=set_controller(caster),
                ),
                game=game,
            )
            if untap:
                target.untap()
            for keyword in keywords:
                store.add(
                    ContinuousEffect(
                        description=f"{spell.name}: {target.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=selector,
                        modification=grant_ability(keyword),
                    ),
                    game=game,
                )

    return effect


#: "[You ]gain control of `<target>`." with no duration, and its riders:
#: Agent of Treachery's "When this creature enters, gain control of target
#: permanent.", Keiga, the Tide Star's "When Keiga dies, gain control of
#: target creature.", and Sorin, Ravenous Neonate's -6 / Captivating
#: Vampire's "Gain control of `<target>`.[ `<It|That creature>` becomes a[n]
#: `<creature type>` in addition to its other types.][ Put a[n] `<kind>`
#: counter on `<it|that creature>` if you control a[n] `<quality>` permanent
#: other than that creature[ or `<this>`].]". CR 611.2a: "If no duration is
#: stated, it lasts until the end of the game" - the control change (layer 2,
#: CR 613.1b) and the type change (layer 4, CR 613.1d) both outlive the
#: source, keyed to each target as it is now (CR 400.7). The counter rider is
#: decided once, as the ability resolves, against the board after the steal.
_GAIN_CONTROL_UNTIMED_RE = re.compile(
    r"^(?:you )?gain control of (?P<phrase>(?:up to (?:one|two|three|\d+) )?target [^.]+?)"
    r"(?:\.(?:\s*(?:it|that creature) becomes an? (?P<subtype>[A-Z][a-z-]+) in addition to its "
    r"other types\.)?"
    r"(?:\s*put an? (?P<kind>[a-z]+) counter on (?:it|that creature) if you control an? "
    r"(?P<quality>[a-z]+) permanent other than (?:that creature|it)"
    rf"(?: or (?P<self>{_SELF}))?\.)?)?$",
    re.IGNORECASE,
)

#: A duration or condition inside the target phrase belongs to another
#: reader, a spell (Commandeer, CR 115.1) is not a permanent to control, and
#: a rider ("and untap it", "and each Aura attached to it", ", then ...") or
#: an opponent's choice (not a target, CR 115.1) is more than this shape says.
_NOT_UNTIMED_RE = re.compile(
    r"\b(?:until|for as long as|as long as|during|if|this turn|spells?|and|then|choice"
    r"|attached)\b|,",
    re.IGNORECASE,
)

#: CR 105.1's five colours, as a quality word ("a white permanent").
_COLOR_WORDS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


def _permanent_quality_matcher(word: str) -> Callable[[Characteristics], bool] | None:
    """A colour (CR 105.1), card type or subtype as a test on computed
    characteristics, or `None` for a word that is none of them."""
    color = _COLOR_WORDS.get(word.lower())
    if color is not None:
        return lambda chars: color in chars.colors
    return _quality_matcher(word)


def _phrase_has_validated_history_restriction(phrase: str) -> bool:
    """Whether `phrase`'s own "this turn" is `machines/targeting.py`'s
    validated "controlled by a player who was dealt combat damage ... this
    turn" restriction (Admiral Beckett Brass) rather than an unread duration
    or condition `_NOT_UNTIMED_RE` exists to catch.

    A narrow, provable carve-out rather than a loosening of `_NOT_UNTIMED_RE`
    itself: only a phrase that `machines/targeting.py` fully reads as
    exactly one requirement, and whose requirement is specifically this
    per-turn historical restriction (`TargetRequirement.
    controller_dealt_damage_clause`/`dealt_damage_clause`), is let through -
    every other "this turn", "until", "for as long as", etc. still fails
    closed the same way it always has.
    """
    from .targeting import profile_for_text

    profile = profile_for_text(phrase)
    if not profile.understood or len(profile.requirements) != 1:
        return False
    requirement = profile.requirements[0]
    return bool(requirement.controller_dealt_damage_clause or requirement.dealt_damage_clause)


def parse_gain_control_untimed_clause(effect_text: str) -> AbilityEffect | None:
    """`_GAIN_CONTROL_UNTIMED_RE`'s shape, or `None`."""
    from .effects import _counter_kind, _targets_understood
    from .layers import _singular_subtype_word, add_subtype

    match = _GAIN_CONTROL_UNTIMED_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    phrase = match.group("phrase")
    if _NOT_UNTIMED_RE.search(phrase) and not _phrase_has_validated_history_restriction(phrase):
        return None
    if not _targets_understood(phrase, count_agnostic=True):
        return None
    subtype: str | None = None
    if match.group("subtype"):
        singular = _singular_subtype_word(match.group("subtype"))
        if singular is None:
            return None
        subtype = singular.capitalize()
    kind = None
    has_quality = None
    if match.group("kind"):
        has_quality = _permanent_quality_matcher(match.group("quality"))
        if has_quality is None:
            return None
        kind = _counter_kind(match.group("kind"))
    excludes_source = match.group("self") is not None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        targets = [
            target
            for target in game.resolve_card_targets(ability)
            if target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        store = game.continuous_effects
        timestamp = store.tick()
        for target in targets:
            selector = only_this_incarnation(target, target.zone_change_stamp)
            store.add(
                ContinuousEffect(
                    description=(
                        f"{ability.source_name}: {ability.controller} gains control of "
                        f"{target.name}"
                    ),
                    layer=Layer.CONTROL,
                    timestamp=timestamp,
                    duration=Duration.INDEFINITE,
                    selector=selector,
                    modification=set_controller(ability.controller),
                ),
                game=game,
            )
            if subtype is not None:
                store.add(
                    ContinuousEffect(
                        description=(
                            f"{ability.source_name}: {target.name} becomes a {subtype} "
                            "in addition to its other types"
                        ),
                        layer=Layer.TYPE,
                        timestamp=timestamp,
                        duration=Duration.INDEFINITE,
                        selector=selector,
                        modification=add_subtype(subtype),
                    ),
                    game=game,
                )
        if kind is None or has_quality is None:
            return
        source = ability.source(game)
        for target in targets:
            excluded = {target.id}
            if excludes_source and source is not None:
                excluded.add(source.id)
            if any(
                has_quality(game.characteristics_of(permanent))
                for permanent in game.permanents_controlled_by(ability.controller)
                if permanent.id not in excluded
            ):
                game.add_counters(target, kind, putter=ability.controller)

    return effect


#: "Target `<creature>` has|gains `<keywords>` for as long as this `<noun>`
#: remains tapped." - Hisoka's Guard ("Target creature you control other than
#: this creature has shroud for as long as this creature remains tapped.").
#: CR 611.2b's duration is the *source's* tapped status; the keyword grant is
#: layer 6 (CR 613.1f), built by `machines/layers` from the plain "target
#: creature gains `<keywords>` until end of turn." sentence and given this
#: duration instead.
_GRANT_WHILE_SOURCE_TAPPED_RE = re.compile(
    r"^(?P<phrase>target [^.]+?) (?:has|have|gains?) (?P<keywords>[a-z][a-z, ]*?) "
    rf"for as long as (?P<source_tapped>{_SELF}) remains tapped\.?$",
    re.IGNORECASE,
)


def _parse_grant_while_source_tapped_clause(effect_text: str) -> AbilityEffect | None:
    """`_GRANT_WHILE_SOURCE_TAPPED_RE`'s shape, or `None`."""
    from .effects import _targets_understood
    from .effects.continuous import continuous_effects, layer_context_for
    from .layers import parsed_layer_effects

    match = _GRANT_WHILE_SOURCE_TAPPED_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    sentence = f"target creature gains {match.group('keywords').strip()} until end of turn."
    builder = parsed_layer_effects(sentence)
    if builder is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        condition = _lock_condition(game, ability, duration_kind="source_tapped")
        source = ability.source(game)
        targets = [
            target
            for target in game.resolve_card_targets(ability)
            if target.zone is Zone.BATTLEFIELD
        ]
        if condition is None or source is None or not targets:
            return
        store = continuous_effects(game)
        timestamp = store.tick()
        context = layer_context_for(game, game.player(ability.controller))
        for built in builder(source, timestamp, targets, context):
            store.add(
                built.model_copy(
                    update={"duration": Duration.FOR_AS_LONG_AS, "condition": condition}
                ),
                game=game,
            )

    return effect


#: Giant Oyster: "For as long as this creature remains tapped, target tapped
#: creature doesn't untap during its controller's untap step, and at the
#: beginning of each of your draw steps, put a -1/-1 counter on that creature.
#: When this creature leaves the battlefield or becomes untapped, remove all
#: -1/-1 counters from the creature." Three parts, all tied to the source:
#: the untap lock (layer 6, CR 611.2b's duration on the source being tapped),
#: a delayed trigger with that stated duration (CR 603.7b) at each of the
#: controller's chosen steps, and a CR 603.7a delayed "when" ability watching
#: the source leave (CR 603.6c) or become untapped.
_LOCK_AND_COUNTER_WHILE_TAPPED_RE = re.compile(
    rf"^for as long as (?P<src>{_SELF}) remains tapped, (?P<phrase>target [^,]+?) "
    r"doesn'?t untap during its controller'?s untap step, and at the beginning of each of "
    r"your (?P<step>upkeep|draw step|end step)s?, put an? (?P<kind>[^ ]+) counter on "
    rf"(?:that|the) creature\. when (?P<src2>{_SELF}) leaves the battlefield or becomes "
    r"untapped, remove all (?P<kind2>[^ ]+) counters from (?:that|the) creature\.?$",
    re.IGNORECASE,
)

_LOCK_STEP_WORDS = {"upkeep": "UPKEEP", "draw step": "DRAW", "end step": "END"}


def _parse_lock_and_counter_while_tapped_clause(effect_text: str) -> AbilityEffect | None:
    """`_LOCK_AND_COUNTER_WHILE_TAPPED_RE`'s shape, or `None`."""
    from .abilities import TriggerEvent
    from .delayed import (
        CounterOnSubjectWhileSourceTapped,
        DelayedTrigger,
        RemoveCountersFromLinkedCreature,
    )
    from .effects import _targets_understood
    from .turn import Step

    match = _LOCK_AND_COUNTER_WHILE_TAPPED_RE.fullmatch(" ".join(effect_text.split()))
    if match is None or match.group("kind").lower() != match.group("kind2").lower():
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    step = Step[_LOCK_STEP_WORDS[match.group("step").lower()]]
    kind = match.group("kind")

    def effect(game: Game, ability: AbilityOnStack) -> None:
        condition = _lock_condition(game, ability, duration_kind="source_tapped")
        source = ability.source(game)
        targets = [
            target
            for target in game.resolve_card_targets(ability)
            if target.zone is Zone.BATTLEFIELD and target.zone_change_stamp is not None
        ]
        if condition is None or source is None or source.zone_change_stamp is None:
            return  # CR 611.2b: already false, so none of it begins.
        store = game.continuous_effects
        timestamp = store.tick()
        for target in targets:
            assert target.zone_change_stamp is not None
            store.add(
                ContinuousEffect(
                    description=f"{ability.source_name}: {target.name} doesn't untap",
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    duration=Duration.FOR_AS_LONG_AS,
                    condition=condition,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=grant_ability(DOESNT_UNTAP_TEXT),
                ),
                game=game,
            )
            siblings = [
                game.create_delayed_trigger(
                    DelayedTrigger(
                        text=f"At the beginning of each of your {match.group('step')}s, put a "
                        f"{kind} counter on that creature.",
                        event=TriggerEvent.BEGINNING_OF_STEP,
                        step=step,
                        only_when_active=ability.controller,
                        remaining=None,
                        controller=ability.controller,
                        source_id=source.id,
                        source_name=ability.source_name,
                        subject_id=target.id,
                        expected_zone=Zone.BATTLEFIELD,
                        expected_stamp=target.zone_change_stamp,
                        effect=CounterOnSubjectWhileSourceTapped(
                            source_card_id=source.id,
                            source_stamp=source.zone_change_stamp,
                            counter_kind=kind,
                        ),
                    )
                )
            ]
            for event in (TriggerEvent.LEAVES_THE_BATTLEFIELD, TriggerEvent.BECOMES_UNTAPPED):
                siblings.append(
                    game.create_delayed_trigger(
                        DelayedTrigger(
                            text=f"When {ability.source_name} leaves the battlefield or becomes "
                            f"untapped, remove all {kind} counters from the creature.",
                            event=event,
                            controller=ability.controller,
                            source_id=source.id,
                            source_name=ability.source_name,
                            subject_id=source.id,
                            effect=RemoveCountersFromLinkedCreature(
                                creature_id=target.id,
                                creature_stamp=target.zone_change_stamp,
                                counter_kind=kind,
                            ),
                        )
                    )
                )
            for trigger in siblings:
                trigger.sibling_ids = tuple(o.id for o in siblings if o is not trigger)

    return effect


def control_change_ability_effect(effect_text: str) -> AbilityEffect | None:
    """A control change or rider on an activated or triggered ability."""
    for reader in (
        _parse_tap_then_lock_clause,
        _parse_gain_control_for_as_long_clause,
        _parse_gain_control_of_all_target_players_clause,
        _parse_grant_while_source_tapped_clause,
        _parse_lock_and_counter_while_tapped_clause,
    ):
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None


def control_change_spell_effect(effect_text: str) -> Effect | None:
    """A control change or rider on a resolving spell."""
    return _parse_gain_control_longer_if_clause(effect_text)
