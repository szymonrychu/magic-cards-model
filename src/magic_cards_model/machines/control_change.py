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
    r"on the battlefield|(?P<tapped>it remains tapped))\.?$",
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
    r"on the battlefield)\.(?:\s*then (?P<rest>.+))?$",
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
    controlled = match.group("controlled") is not None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        duration_kind = "controlled" if controlled else "remains"
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


#: "Gain control of target `<object>`." with no duration - Agent of
#: Treachery's "When this creature enters, gain control of target
#: permanent.", Keiga, the Tide Star's "When Keiga dies, gain control of
#: target creature.". CR 611.2a: "If no duration is stated, it lasts until
#: the end of the game." Layer 2 (CR 613.1b), keyed to each target as it is
#: now (CR 400.7).
_GAIN_CONTROL_INDEFINITELY_RE = re.compile(
    r"^(?:you )?gain control of (?P<phrase>(?:up to (?:one|two|three|\d+) )?target [^.]+?)\.?$",
    re.IGNORECASE,
)

#: A duration or condition inside the target phrase belongs to another
#: reader, a spell (Commandeer, CR 115.1) is not a permanent to control, and
#: a rider ("and untap it", "and each Aura attached to it", ", then ...") or
#: an opponent's choice (not a target, CR 115.1) is more than this shape says.
_NOT_INDEFINITE_RE = re.compile(
    r"\b(?:until|for as long as|during|if|this turn|spells?|and|then|choice|attached)\b"
    r"|,",
    re.IGNORECASE,
)


def _parse_gain_control_indefinitely_clause(effect_text: str) -> AbilityEffect | None:
    """`_GAIN_CONTROL_INDEFINITELY_RE`'s shape, or `None`."""
    from .effects import _targets_understood

    match = _GAIN_CONTROL_INDEFINITELY_RE.fullmatch(" ".join(effect_text.split()))
    if match is None or _NOT_INDEFINITE_RE.search(match.group("phrase")):
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None

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


#: "Gain control of `<target>`.[ `<It|That creature>` becomes a[n]
#: `<creature type>` in addition to its other types.][ Put a[n] `<kind>`
#: counter on `<it|that creature>` if you control a[n] `<quality>` permanent
#: other than that creature[ or `<this>`].]" - Sorin, Ravenous Neonate's -6
#: and Captivating Vampire's activated ability. No duration is printed, so
#: CR 611.2a: "If no duration is stated, it lasts until the end of the game" -
#: the control change (layer 2, CR 613.1b) and the type change (layer 4,
#: CR 613.1d) both outlive the source. The counter rider is decided once, as
#: the ability resolves, against the board after the steal.
_GAIN_CONTROL_UNTIMED_RE = re.compile(
    r"^gain control of (?P<phrase>target [^.]+?)\."
    r"(?:\s*(?:it|that creature) becomes an? (?P<subtype>[A-Z][a-z-]+) in addition to its "
    r"other types\.)?"
    r"(?:\s*put an? (?P<kind>[a-z]+) counter on (?:it|that creature) if you control an? "
    r"(?P<quality>[a-z]+) permanent other than (?:that creature|it)"
    rf"(?: or (?P<self>{_SELF}))?\.)?$",
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


def parse_gain_control_untimed_clause(effect_text: str) -> AbilityEffect | None:
    """`_GAIN_CONTROL_UNTIMED_RE`'s shape, or `None`."""
    from .effects import _counter_kind, _targets_understood
    from .layers import _singular_subtype_word, add_subtype

    match = _GAIN_CONTROL_UNTIMED_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    phrase = match.group("phrase")
    if re.search(r"\b(?:until|for as long as|as long as)\b", phrase, re.IGNORECASE):
        return None
    if not _targets_understood(phrase):
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


def control_change_ability_effect(effect_text: str) -> AbilityEffect | None:
    """A control change or rider on an activated or triggered ability."""
    for reader in (
        _parse_tap_then_lock_clause,
        _parse_gain_control_for_as_long_clause,
        _parse_gain_control_indefinitely_clause,
    ):
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None


def control_change_spell_effect(effect_text: str) -> Effect | None:
    """A control change or rider on a resolving spell."""
    return _parse_gain_control_longer_if_clause(effect_text)
