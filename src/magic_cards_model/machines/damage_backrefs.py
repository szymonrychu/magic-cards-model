"""Source-damage abilities whose later words point back at the target.

Each shape here is one instruction (or a short chain) whose second half names
its object by CR 400.7 back-reference to the first half's target - "that
creature's controller", "each other creature that shares a color with it",
"that creature deals damage ... to this creature", "<it> deals N damage
instead" - rather than announcing a target of its own. The target is fixed
as the ability is put on the stack; everything the back-reference names is
read off it as the ability resolves.

- "`<src>` deals N damage to target creature and M damage to that creature's
  controller." (Chandra, Flame's Fury's -2.)
- "`<src>` deals N damage to target creature and each other creature
  `<that shares a color with it | with the same name as that creature>`."
  (Wojek Embermage, Izzet Staticaster.)
- "`<src>` deals damage equal to its power to target creature. That creature
  deals damage equal to its power to this creature." (Karplusan Yeti, Vein
  Drinker.) Not fight: CR 701.14b stops both creatures when either is gone;
  here the two sentences are two instructions in order, so the source's
  damage still happens off its last known power (CR 608.2h) and the reply
  simply has no "this creature" to reach.
- "`<base>`. [If `<condition>`, ]`<alternative>` instead[ if `<condition>`]."
  where the alternative elides or back-references what the base announced
  (CR 614.1a): Akoum Hellkite's "this creature deals 2 damage instead",
  Scepter of Empires' "It deals 3 damage instead", Crown of Empires' "Gain
  control of that creature instead", Throne of Empires' "Create five of
  those tokens instead".

CR 608.2b covers every shape alike: one "target" each, so with that target
illegal the ability doesn't resolve and nothing the back-reference names is
touched either.

Rules looked up with `mise run rules:find` in the session that wrote this:
CR 105.2c (a colorless object has no color), CR 120.8 (0 damage is not
dealt), CR 608.2b, CR 608.2h, CR 614.1a, CR 701.14a/b.
"""

import re
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import COUNT, parse_count

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers import AbilityOnStack

_DAMAGE_TARGET_AND_CONTROLLER_RE = re.compile(
    rf"^(?P<subject>[^.]+?) deals (?P<n>{COUNT}) damage to target (?P<noun>creature|permanent"
    rf"|planeswalker|artifact|enchantment|land) and (?P<m>{COUNT}) damage to that (?P=noun)'s "
    r"controller\.?$",
    re.IGNORECASE,
)
_DAMAGE_TARGET_AND_EACH_OTHER_RE = re.compile(
    rf"^(?P<subject>[^.]+?) deals (?P<n>{COUNT}) damage to target creature and each other "
    r"creature (?:(?P<color>that shares a colou?r with it)"
    r"|(?P<name>with the same name as that creature))\.?$",
    re.IGNORECASE,
)
_MUTUAL_POWER_DAMAGE_RE = re.compile(
    r"^(?P<subject>[^.]+?) deals damage equal to its power to target creature\.\s*"
    r"that creature deals damage equal to its power to (?:this creature|it)\.?$",
    re.IGNORECASE,
)
_INSTEAD_RE = re.compile(
    r"^(?P<base>[^.]+)\.\s*(?:if (?P<condition_leading>[^,]+), (?P<alternative_leading>.+?) instead"
    r"|(?P<alternative_trailing>.+?) instead if (?P<condition_trailing>[^.]+))\.?$",
    re.IGNORECASE,
)
_BASE_DAMAGE_AMOUNT_RE = re.compile(rf"\bdeals (?P<n>{COUNT}) damage\b", re.IGNORECASE)
_ELIDED_DAMAGE_ALTERNATIVE_RE = re.compile(
    rf"^(?P<subject>[^.]+?) deals (?P<m>{COUNT}) damage$", re.IGNORECASE
)
_THOSE_TOKENS_ALTERNATIVE_RE = re.compile(
    rf"^create (?P<count>{COUNT}) of those tokens$", re.IGNORECASE
)
_BASE_TOKEN_RE = re.compile(
    rf"^create (?P<count>{COUNT}) (?P<desc>.+?) tokens?(?P<tail>\b.*)$", re.IGNORECASE
)


def _source(game: "Game", ability: "AbilityOnStack") -> CardState | None:
    return ability.source_or_last_known(game)


def _still_this_object(game: "Game", ability: "AbilityOnStack") -> CardState | None:
    """The ability's source, if it is still on the battlefield as the same
    object (CR 400.7) - what "this creature" can still be dealt damage as."""
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD:
        return None
    stamp = getattr(ability, "source_stamp", None)
    if stamp is not None and source.zone_change_stamp != stamp:
        return None
    return source


def _power(game: "Game", creature: CardState) -> int:
    """Its power now on the battlefield, or as it last existed there (CR
    608.2h)."""
    if creature.zone is Zone.BATTLEFIELD:
        return max(game.power_of(creature) or 0, 0)
    from .conditions.objects import _last_known_power_toughness

    power, _toughness = _last_known_power_toughness(creature)
    return max(power or 0, 0)


def _creature_targets(game: "Game", ability: "AbilityOnStack") -> list[CardState]:
    return [
        target
        for target in game.resolve_targets(ability)
        if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
    ]


def _parse_damage_target_and_controller(text: str) -> Any:
    match = _DAMAGE_TARGET_AND_CONTROLLER_RE.fullmatch(text)
    if match is None:
        return None
    to_target = parse_count(match.group("n"))
    to_controller = parse_count(match.group("m"))
    if to_target is None or to_controller is None:
        return None

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        source = _source(game, ability)
        for target in _creature_targets(game, ability):
            controller = game.controller_of(target)
            game.deal_damage(target, to_target, source=source)
            game.deal_damage(controller, to_controller, source=source)

    return effect


def _parse_damage_target_and_each_other(text: str) -> Any:
    match = _DAMAGE_TARGET_AND_EACH_OTHER_RE.fullmatch(text)
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    by_color = match.group("color") is not None

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        source = _source(game, ability)
        targets = _creature_targets(game, ability)
        if not targets:
            return
        target = targets[0]
        board = game.computed_board()
        wanted = board.of(target)
        group = [target]
        for other in game.battlefield:
            if other is target:
                continue
            chars = board.of(other)
            if not chars.is_creature:
                continue
            if by_color:
                shares = bool(set(chars.colors) & set(wanted.colors))  # CR 105.2c
            else:
                shares = bool(wanted.name) and chars.name == wanted.name
            if shares:
                group.append(other)
        for creature in group:
            game.deal_damage(creature, amount, source=source)

    return effect


def _parse_mutual_power_damage(text: str) -> Any:
    if _MUTUAL_POWER_DAMAGE_RE.fullmatch(text) is None:
        return None

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        source = _source(game, ability)
        targets = _creature_targets(game, ability)
        if source is None or not targets:
            return
        target = targets[0]
        game.deal_damage(target, _power(game, source), source=source)
        game.announce_batched_events()
        this_creature = _still_this_object(game, ability)
        if this_creature is None or target.zone is not Zone.BATTLEFIELD:
            return
        game.deal_damage(this_creature, _power(game, target), source=target)

    return effect


def _alternative_text(base: str, alternative: str) -> str | None:
    """The alternative rewritten to say in full what it elides or names by
    back-reference to `base`, or None when it is none of the shapes read."""
    alternative = alternative.strip()
    if elided := _ELIDED_DAMAGE_ALTERNATIVE_RE.fullmatch(alternative):
        amounts = list(_BASE_DAMAGE_AMOUNT_RE.finditer(base))
        if len(amounts) != 1:
            return None
        found = amounts[0]
        return f"{base[: found.start('n')]}{elided.group('m')}{base[found.end('n') :]}"
    if those := _THOSE_TOKENS_ALTERNATIVE_RE.fullmatch(alternative):
        token = _BASE_TOKEN_RE.fullmatch(base.strip())
        if token is None or token.group("tail").strip():
            return None
        return f"create {those.group('count')} {token.group('desc')} tokens"
    from .effects import _anaphoric_target_substitution

    return _anaphoric_target_substitution(base, alternative)


def _branch_effect(text: str) -> Any:
    """One branch of the base-or-alternative pair as its own instruction: the
    ordinary clause reader, or the untimed control change ("Gain control of
    target creature", CR 611.2a's indefinite duration) it does not read."""
    from .control_change import parse_gain_control_untimed_clause
    from .effects import parse_mixed_effect

    return parse_mixed_effect(text) or parse_gain_control_untimed_clause(text)


def _parse_condition_instead(text: str) -> Any:
    from .conditions.objects import names_an_anaphor
    from .effects import ConditionalClauseNotice, _effect_condition_is_readable

    match = _INSTEAD_RE.fullmatch(text)
    if match is None:
        return None
    condition = (match.group("condition_leading") or match.group("condition_trailing")).strip()
    alternative_text = match.group("alternative_leading") or match.group("alternative_trailing")
    base_text = match.group("base").strip()
    if not _effect_condition_is_readable(condition, allow_anaphor=True):
        return None
    rewritten = _alternative_text(base_text, alternative_text)
    if rewritten is None:
        return None
    base = _branch_effect(base_text)
    alternative = _branch_effect(rewritten)
    if base is None or alternative is None:
        return None
    anaphoric = names_an_anaphor(condition)

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        controller = game.controller_of(ability).username
        event = getattr(ability, "event", None)
        held: bool | None
        if anaphoric and event is None:
            held = None  # an anaphor with no trigger event to name
        else:
            held = game.condition_holds(
                controller, condition, ability.source(game), ability=ability, event=event
            )
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=ability.source_id, source_name=ability.source_name, text=text
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            held = False
        (alternative if held else base)(game, ability)

    return effect


_READERS = (
    _parse_damage_target_and_controller,
    _parse_damage_target_and_each_other,
    _parse_mutual_power_damage,
    _parse_condition_instead,
)


def damage_backref_ability_effect(effect_text: str) -> Any:
    """The first shape above `effect_text` reads as, or None."""
    from .effects import _strip_non_effect_preamble

    text = " ".join(_strip_non_effect_preamble(effect_text).split())
    for reader in _READERS:
        effect = reader(text)
        if effect is not None:
            return effect
    return None
