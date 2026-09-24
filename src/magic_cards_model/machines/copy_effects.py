"""Copy effects read off oracle text (CR 707): an object becoming a copy of
another, token copies, and copies of spells and abilities on the stack.

Entry points `copy_ability_effect`/`copy_spell_effect` are tried by
`machines/effects.py` ahead of its clause split, because every shape here is
an instruction chain whose later sentences refer back to the first ("copy
that spell. You may choose new targets for the copy.").
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models.card import Type
from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import parse_count
from .abilities import TriggerEvent
from .decisions import source_id_of
from .delayed import CopyNextSpellWithinManaValue, DelayedTrigger

if TYPE_CHECKING:
    from ..models.game import Game
    from .effects import AbilityEffect, Effect
    from .triggers import AbilityOnStack

#: A self-reference: "this <noun>" once `self_normalized_effect_text` has
#: rewritten the card's own name, or the printed name itself (CR 201.5).
_SELF = r"(?:this (?:creature|permanent)|[A-Z][^.,]*?)"

#: "you may choose new targets for the copy/copies." (CR 707.10c).
_NEW_TARGETS = r"(?P<new_targets>\s*you may choose new targets for the cop(?:y|ies)\.?)?"


# ---------------------------------------------------------------------------
# "When you next cast ... with mana value ... this turn, copy that spell."
# ---------------------------------------------------------------------------

#: Dual Strike's "When you next cast an instant or sorcery spell with mana
#: value 4 or less this turn, copy that spell." and Loki Laufeyson's "... with
#: mana value less than or equal to Loki's power this turn, copy that spell."
#: - a CR 603.7a delayed triggered ability (`CopyNextSpellWithinManaValue`),
#: restricted to instants and sorceries (`required_any_types`) and bounded by
#: the spell's mana value. The unbounded sentence is
#: `machines/effects._COPY_NEXT_INSTANT_OR_SORCERY_YOU_CAST_RE`'s.
_COPY_NEXT_WITHIN_MANA_VALUE_RE = re.compile(
    r"^when you next cast an instant or sorcery spell with mana value "
    rf"(?:(?P<n>\d+|[a-z]+) or less|less than or equal to (?P<self>{_SELF})['’]s power) "
    rf"this turn, copy that spell\.{_NEW_TARGETS}$",
    re.IGNORECASE,
)


def _copy_next_within_mana_value(text: str) -> tuple[bool, int | None, bool] | None:
    """`(may_retarget, at_most, at_most_source_power)` for
    `_COPY_NEXT_WITHIN_MANA_VALUE_RE`, or `None`."""
    match = _COPY_NEXT_WITHIN_MANA_VALUE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    at_most: int | None = None
    if match.group("n") is not None:
        raw = match.group("n")
        at_most = int(raw) if raw.isdigit() else parse_count(raw, article=False)
        if at_most is None:
            return None
    return match.group("new_targets") is not None, at_most, match.group("self") is not None


def _create_copy_next_trigger(
    game: Game,
    *,
    controller: str,
    source_id: object,
    source_name: str,
    spec: CopyNextSpellWithinManaValue,
) -> None:
    game.create_delayed_trigger(
        DelayedTrigger(
            text="When you next cast an instant or sorcery spell this turn, copy that spell.",
            event=TriggerEvent.CAST_SPELL,
            controller=controller,
            source_id=source_id,
            source_name=source_name,
            only_when_active=controller,
            remaining=1,
            expires_end_of_turn=True,
            required_any_types=(Type.INSTANT, Type.SORCERY),
            effect=spec,
        )
    )


def _parse_copy_next_within_mana_value_ability(text: str) -> AbilityEffect | None:
    read = _copy_next_within_mana_value(text)
    if read is None:
        return None
    may_retarget, at_most, source_power = read

    def effect(game: Game, ability: AbilityOnStack) -> None:
        _create_copy_next_trigger(
            game,
            controller=ability.controller,
            source_id=ability.source_id,
            source_name=ability.source_name,
            spec=CopyNextSpellWithinManaValue(
                may_retarget=may_retarget, at_most=at_most, at_most_source_power=source_power
            ),
        )

    return effect


def _parse_copy_next_within_mana_value_spell(text: str) -> Effect | None:
    read = _copy_next_within_mana_value(text)
    if read is None:
        return None
    may_retarget, at_most, source_power = read
    if source_power:
        return None  # a spell's own power is nothing once it has resolved

    def effect(game: Game, spell: CardState) -> None:
        _create_copy_next_trigger(
            game,
            controller=game.controller_of(spell).username,
            source_id=spell.id,
            source_name=spell.name,
            spec=CopyNextSpellWithinManaValue(may_retarget=may_retarget, at_most=at_most),
        )

    return effect


# ---------------------------------------------------------------------------
# "copy that spell. [You may choose new targets for the copy.] <rest>"
# ---------------------------------------------------------------------------

#: Fin Fang Foom's "copy that spell. You may choose new targets for the copy.
#: Put two +1/+1 counters on Fin Fang Foom." - CR 707.10's copy of the spell
#: a CAST_SPELL trigger watched (CR 607.1's "that spell", read off the
#: trigger's event), then the rest of the ability as its own instruction.
#: The bare "copy that spell[. new targets]" sentence is `machines/effects.
#: _COPY_THAT_SPELL_RE`'s.
_COPY_THAT_SPELL_THEN_RE = re.compile(
    rf"^copy that spell\.{_NEW_TARGETS}\s*(?P<rest>.+)$", re.IGNORECASE | re.DOTALL
)


def _parse_copy_that_spell_then_clause(text: str) -> AbilityEffect | None:
    from .effects import parse_mixed_effect

    match = _COPY_THAT_SPELL_THEN_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    rest = parse_mixed_effect(match.group("rest").strip())
    if rest is None:
        return None
    offer_new_targets = match.group("new_targets") is not None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        event = ability.event
        spell = (
            game.find_by_id(event.subject_id)
            if event is not None and event.subject_id is not None
            else None
        )
        if isinstance(spell, CardState) and spell in game.stack:
            copy = game.copy_spell(spell, controller=ability.controller)
            if offer_new_targets:
                game.offer_new_targets_for_copy(
                    copy,
                    ability.controller,
                    source_name=ability.source_name,
                    source_id=source_id_of(ability),
                )
        rest(game, ability)

    return effect


# ---------------------------------------------------------------------------
# "When you cast this spell, copy it <N>."
# ---------------------------------------------------------------------------

#: Photon Blast Barrage's "When you cast this spell, copy it X times. You may
#: choose new targets for the copies." and Show of Confidence's "... copy it
#: for each other instant and sorcery spell you've cast this turn." - the
#: effect of a cast trigger that functions on the stack (CR 113.6k), copying
#: the spell it is printed on (CR 707.10: the copies are not cast). X is the
#: spell's own announced X (CR 107.3a), read off its cast record.
_COPY_IT_N_TIMES_RE = re.compile(
    r"^copy it (?:(?P<n>x|\d+|[a-z]+) times|(?P<twice>twice)"
    r"|for each other (?P<types>instant and sorcery|instant or sorcery|instant|sorcery) "
    rf"spells? you['’]?ve cast this turn)\.{_NEW_TARGETS}$",
    re.IGNORECASE,
)


def _parse_copy_it_n_times_clause(text: str) -> AbilityEffect | None:
    match = _COPY_IT_N_TIMES_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    raw = (match.group("n") or "").lower()
    fixed: int | None = None
    if match.group("twice"):
        fixed = 2
    elif raw and raw != "x":
        fixed = int(raw) if raw.isdigit() else parse_count(raw, article=False)
        if fixed is None:
            return None
    types: tuple[Type, ...] = ()
    if match.group("types"):
        words = match.group("types").lower()
        types = tuple(
            card_type
            for card_type, word in ((Type.INSTANT, "instant"), (Type.SORCERY, "sorcery"))
            if word in words
        )
    offer_new_targets = match.group("new_targets") is not None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        spell = ability.source(game)
        if not isinstance(spell, CardState) or spell.zone is not Zone.STACK:
            return
        if types:
            count = sum(
                1
                for cast in game.spells_cast_this_turn.get(ability.controller, [])
                if cast.id != spell.id and any(t in cast.types for t in types)
            )
        elif fixed is not None:
            count = fixed
        else:
            count = game.cast_record(spell).x_value or 0
        for _ in range(count):
            copy = game.copy_spell(spell, controller=ability.controller)
            if offer_new_targets:
                game.offer_new_targets_for_copy(
                    copy,
                    ability.controller,
                    source_name=ability.source_name,
                    source_id=source_id_of(ability),
                )

    return effect


#: A spell's leading "When you cast this spell, ..." paragraph (CR 113.6k) is
#: its own triggered ability, not part of what the spell does as it resolves.
_LEADING_CAST_TRIGGER_RE = re.compile(
    r"^when you cast this spell, [^\n]+\n+(?P<rest>.+)$", re.I | re.S
)


def _parse_spell_after_cast_trigger(text: str) -> Effect | None:
    from .effects import _spell_effect_or_notice

    match = _LEADING_CAST_TRIGGER_RE.fullmatch(text.strip())
    if match is None:
        return None
    return _spell_effect_or_notice(match.group("rest"))


def copy_ability_effect(effect_text: str) -> AbilityEffect | None:
    """A copy instruction on an activated or triggered ability, or `None`."""
    for reader in (
        _parse_copy_next_within_mana_value_ability,
        _parse_copy_that_spell_then_clause,
        _parse_copy_it_n_times_clause,
    ):
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None


def copy_spell_effect(effect_text: str) -> Effect | None:
    """A copy instruction on a resolving spell, or `None`."""
    for reader in (_parse_copy_next_within_mana_value_spell, _parse_spell_after_cast_trigger):
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None
