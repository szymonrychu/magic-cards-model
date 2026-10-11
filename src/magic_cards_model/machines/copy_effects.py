"""Copy effects read off oracle text (CR 707): an object becoming a copy of
another, token copies, and copies of spells and abilities on the stack.

Entry points `copy_ability_effect`/`copy_spell_effect` are tried by
`machines/effects.py` ahead of its clause split, because every shape here is
an instruction chain whose later sentences refer back to the first ("copy
that spell. You may choose new targets for the copy.").
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, NamedTuple

from ..models.card import Supertype, Type
from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import parse_count
from .abilities import TriggerEvent
from .decisions import Decision, DecisionKind, source_id_of
from .delayed import CopyNextSpellWithinManaValue, DelayedTrigger
from .layers import (
    BecomeACopy,
    Characteristics,
    Condition,
    ContinuousEffect,
    CopySublayer,
    Duration,
    Layer,
    RemainsOnBattlefield,
    copiable_characteristics,
    only_this_incarnation,
    printed_characteristics,
)

if TYPE_CHECKING:
    from ..models.game import Game, StackObject
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
    match = _COPY_THAT_SPELL_THEN_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None

    from .effects import parse_mixed_effect

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
#: Social Snub's own trigger reads "When you cast this spell while you
#: control a creature, you may copy this spell." - CR 603.4's intervening
#: *if* ("while you control a creature", already split out and read
#: generically by `machines/triggers.intervening_if_answer`) sits between
#: "this spell" and the comma, which the bare form above never anticipated;
#: the optional group here widens the match to admit it (and its "if ..."
#: phrasing twin) without narrowing what already matched.
#:
#: Banish into Fable's own trigger reads "When you cast this spell **from
#: your hand**, copy it if ...": CR 601.2a's origin-zone qualifier
#: (`machines/triggers._CAST_ORIGIN_ZONE_RE`'s own vocabulary - "from
#: `<your|their|his or her>` `<hand|graveyard|library|battlefield>`", or the
#: bare "from exile") in the identical position, so the optional group here
#: widens once more to admit it alongside "while"/"if" rather than narrowing
#: anything the bare and conditional forms already matched.
_LEADING_CAST_TRIGGER_RE = re.compile(
    r"^when you cast this spell(?: (?:while|if) [^,\n]+"
    r"| from (?:(?:your|their|his or her) (?:hand|graveyard|library|battlefield)|exile))?, "
    r"[^\n]+\n+(?P<rest>.+)$",
    re.I | re.S,
)


def _parse_spell_after_cast_trigger(text: str) -> Effect | None:
    match = _LEADING_CAST_TRIGGER_RE.fullmatch(text.strip())
    if match is None:
        return None

    from .effects import _spell_effect_or_notice

    return _spell_effect_or_notice(match.group("rest"))


# ---------------------------------------------------------------------------
# "Copy target activated or triggered ability you control[ from a <type> source]."
# ---------------------------------------------------------------------------

#: Echo, Perceptive Prodigy's "Copy target activated or triggered ability you
#: control from a creature source. You may choose new targets for the copy.",
#: Scientist Supreme of A.I.M.'s "... from an artifact source ...", Lithoform
#: Engine's and Peter Parker's Camera's unrestricted form - CR 707.10's copy
#: of an ability on the stack (`Game.copy_ability`); the restrictions are the
#: target's own, enforced at announcement by `machines/targeting.py` and
#: rechecked on resolution (CR 608.2b). CR 707.10c's new targets are CR
#: 115.7d's "choose new targets" (`Game.change_targets`, any number of them).
_COPY_TARGET_ABILITY_RE = re.compile(
    r"^copy target (?:activated or triggered|activated|triggered) ability"
    r"(?: you control)?(?: from an? [a-z]+ source)?\."
    rf"{_NEW_TARGETS}$",
    re.IGNORECASE,
)


def _parse_copy_target_ability_clause(text: str) -> AbilityEffect | None:
    from .targeting import RetargetScope

    match = _COPY_TARGET_ABILITY_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    offer_new_targets = match.group("new_targets") is not None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        from .triggers import AbilityOnStack as StackAbility

        for target in game.resolve_targets(ability):
            if not isinstance(target, StackAbility) or target not in game.stack:
                continue
            copy = game.copy_ability(target, controller=ability.controller)
            if offer_new_targets and copy.targets:
                game.change_targets(
                    copy,
                    ability.controller,
                    scope=RetargetScope.ANY,
                    optional=True,
                    source_name=ability.source_name,
                    source_id=source_id_of(ability),
                )

    return effect


# ---------------------------------------------------------------------------
# "<subject> becomes a copy of <object>[ <duration>][, except <exceptions>]."
# ---------------------------------------------------------------------------


class CopyExceptions(NamedTuple):
    """CR 707.9's "except ..." tail, read by `_parse_become_copy_exceptions`.

    `name` is `SELF_NAME` when the printed name was the card's own (which
    `self_normalized_effect_text` has rewritten to "this permanent").
    `set_type_line` is CR 707.9b's modified characteristic with no "in
    addition to" (Taskmaster's "he's a legendary Human Mercenary Villain
    creature"): the supertypes, card types and subtypes it names are all the
    copy has (CR 205.1a). Otherwise the named ones are added (CR 205.1b).
    """

    name: str | None = None
    power: int | None = None
    toughness: int | None = None
    add_legendary: bool = False
    remove_legendary: bool = False
    types: tuple[Type, ...] = ()
    subtypes: tuple[str, ...] = ()
    set_type_line: bool = False
    abilities: tuple[str, ...] = ()
    keeps_this_ability: bool = False


#: A name exception written with the card's own name, after normalization.
SELF_NAME = "\x00self"

_EXCEPT_NAME_RE = re.compile(r"^(?:his|her|its|their) name is (?P<name>.+)$", re.IGNORECASE)
_EXCEPT_TYPE_LINE_RE = re.compile(
    r"^(?:he|she|it|they)(?:'s|’s| is|'re| are) (?:an? )?(?P<legendary>legendary\s*)?"
    r"(?:(?P<power>\d+)/(?P<toughness>\d+)(?: |$))?"
    r"(?P<types>(?!in addition\b)[A-Za-z][\w'-]*(?: (?!in addition\b)[A-Za-z][\w'-]*)*)?"
    r"(?P<addition>\s*in addition to (?:his|her|its|their) other types)?$",
    re.IGNORECASE,
)
_EXCEPT_NOT_LEGENDARY_RE = re.compile(
    r"^(?:he|she|it|they) (?:isn'?t|is not|aren'?t|are not) legendary$", re.IGNORECASE
)
_EXCEPT_HAS_RE = re.compile(r"^(?:he|she|it|they) (?:has|have) (?P<what>.+)$", re.IGNORECASE)
_THIS_ABILITY_RE = re.compile(r"(?:,\s*|\s+and\s+|^)this ability$", re.IGNORECASE)


def _parse_become_copy_exceptions(clause: str) -> CopyExceptions | None:
    """CR 707.9's "except ..." tail, or `None` if any part is unreadable
    (CR 608.2c: never half a copy)."""
    from ..models.card import Type as CardType
    from .replacement import _granted_abilities, _split_exception_parts

    fields: dict[str, object] = {}
    parts: list[str] = []
    for whole in _split_exception_parts(clause.strip()):
        # "it's 0/0 and has this ability" (Mimeoplasm): a characteristic
        # exception and a granted ability joined by "and" are two exceptions.
        head, *rest = re.split(r"\s+and\s+(?=has\b|have\b)", whole.strip().rstrip("."))
        parts += [head, *(f"it {tail}" for tail in rest)]
    for part in parts:
        part = part.strip().rstrip(".").strip()
        if match := _EXCEPT_NAME_RE.fullmatch(part):
            name = match.group("name").strip()
            fields["name"] = SELF_NAME if name.lower() == "this permanent" else name
            continue
        if _EXCEPT_NOT_LEGENDARY_RE.fullmatch(part):
            fields["remove_legendary"] = True
            continue
        if match := _EXCEPT_HAS_RE.fullmatch(part):
            what = match.group("what").strip()
            if (this := _THIS_ABILITY_RE.search(what)) is not None:
                fields["keeps_this_ability"] = True
                what = what[: this.start()].strip()
            if what:
                granted = _granted_abilities(what)
                if granted is None:
                    return None
                fields["abilities"] = tuple(granted)
            continue
        if match := _EXCEPT_TYPE_LINE_RE.fullmatch(part):
            if match.group("power") is not None:
                fields["power"] = int(match.group("power"))
                fields["toughness"] = int(match.group("toughness"))
            types: list[Type] = []
            subtypes: list[str] = []
            for word in (match.group("types") or "").split():
                try:
                    types.append(CardType(word.lower()))
                except ValueError:
                    subtypes.append(word[0].upper() + word[1:])
            fields["types"] = tuple(types)
            fields["subtypes"] = tuple(subtypes)
            fields["add_legendary"] = match.group("legendary") is not None
            power_only = match.group("power") is not None and not (
                types or subtypes or fields["add_legendary"]
            )
            # Mimeoplasm's "except it's 0/0": a bare power/toughness changes
            # that characteristic and leaves the type line the copy's own
            # (CR 707.9b).
            fields["set_type_line"] = match.group("addition") is None and not power_only
            if fields["set_type_line"] and not types:
                return None  # "he's legendary" with nothing else is not a type line
            continue
        return None
    if not fields:
        return None
    return CopyExceptions(**fields)  # type: ignore[arg-type]


def _become_a_copy(
    game: Game,
    *,
    subject: CardState,
    copied: Characteristics,
    exceptions: CopyExceptions | None,
    source_name: str,
    own_name: str,
    this_ability: str | None,
    duration: Duration,
    until_next_turn_of: str | None = None,
    condition: Condition | None = None,
    timestamp: int | None = None,
) -> None:
    """CR 707.4: `subject`, staying on the battlefield, becomes a copy of
    `copied` (its copiable values, CR 707.2), with CR 707.9's exceptions
    written into the one layer 1a effect (CR 707.9b: they are part of the
    copy's copiable values) - never as separate later-layer effects.

    `timestamp` is shared when one instruction makes several permanents
    copies at once (`_parse_each_becomes_a_copy_clause`, CR 613.7b: one
    effect, created once)."""
    name = copied.name
    power, toughness = copied.power, copied.toughness
    supertypes = list(copied.supertypes)
    types = list(copied.types)
    subtypes = list(copied.subtypes)
    abilities = list(copied.abilities)
    if exceptions is not None:
        if exceptions.name is not None:
            name = own_name if exceptions.name == SELF_NAME else exceptions.name
        if exceptions.power is not None:
            power, toughness = exceptions.power, exceptions.toughness
        if exceptions.set_type_line:
            supertypes = [Supertype.LEGENDARY] if exceptions.add_legendary else []
            types = list(exceptions.types)
            subtypes = list(exceptions.subtypes)
        else:
            if exceptions.add_legendary and Supertype.LEGENDARY not in supertypes:
                supertypes.append(Supertype.LEGENDARY)
            types += [t for t in exceptions.types if t not in types]
            subtypes += [t for t in exceptions.subtypes if t not in subtypes]
        if exceptions.remove_legendary:
            supertypes = [t for t in supertypes if t is not Supertype.LEGENDARY]
        abilities += [a for a in exceptions.abilities if a not in abilities]
        if exceptions.keeps_this_ability and this_ability and this_ability not in abilities:
            abilities.append(this_ability)
    store = game.continuous_effects
    store.add(
        ContinuousEffect(
            description=f"{source_name}: {subject.name} becomes a copy of {copied.name}",
            layer=Layer.COPY,
            sublayer=CopySublayer.COPIABLE,
            timestamp=store.tick() if timestamp is None else timestamp,
            duration=duration,
            until_next_turn_of=until_next_turn_of,
            condition=condition,
            selector=only_this_incarnation(subject, subject.zone_change_stamp),
            modification=BecomeACopy(
                name=name,
                mana_value=copied.mana_value,
                supertypes=tuple(supertypes),
                types=tuple(types),
                subtypes=tuple(subtypes),
                colors=copied.colors,
                abilities=tuple(abilities),
                power=power,
                toughness=toughness,
                defense=copied.defense,
                loyalty=copied.loyalty,
            ),
        ),
        game,
    )


def _copiable_values_of(game: Game, obj: CardState) -> Characteristics:
    """CR 707.2's copiable values: a permanent's as modified by other copy
    effects (`copiable_characteristics`), a card elsewhere its printed ones."""
    if obj.zone is Zone.BATTLEFIELD:
        return copiable_characteristics(obj, game.continuous_effects.active(game))
    return printed_characteristics(obj)


_SELF_SUBJECT = r"this (?:land|permanent|artifact|creature|enchantment|vehicle)|he|she|it"

#: "`<subject>` becomes a copy of `<object>`[ `<duration>`][, except
#: `<exceptions>`]." with an optional leading duration - Absorbing Man's and
#: Taskmaster's "until your next turn, `<self>` becomes a copy of up to one
#: target ..., except his name is ... ", Shuri's "Target artifact you control
#: becomes a copy of a second target artifact you control until end of turn,
#: except it isn't legendary.", Saheeli's "... another target artifact or
#: creature you control until end of turn, except it's an artifact in
#: addition to its other types.", Lazav's "... becomes a copy of target
#: creature card in your graveyard with mana value X, except its name is ...,
#: it's legendary in addition to its other types, and it has this ability."
_BECOMES_A_COPY_RE = re.compile(
    r"^(?:(?P<lead>until end of turn|until your next turn), )?"
    rf"(?P<subject>{_SELF_SUBJECT}|target [^.]+?)"
    r" becomes a copy of (?P<object>(?:up to one |a second |another )?target [^.]+?"
    r"|the exiled card)"
    r"(?P<trail> until end of turn| until your next turn)?"
    r'(?:, except (?P<exception>(?:[^."]|"[^"]*")+?))?\.?$',
    re.IGNORECASE,
)


def _copy_duration(phrase: str | None) -> Duration:
    lowered = (phrase or "").strip().lower()
    if lowered == "until end of turn":
        return Duration.UNTIL_END_OF_TURN
    if lowered == "until your next turn":
        return Duration.UNTIL_YOUR_NEXT_TURN
    return Duration.INDEFINITE


def _parse_becomes_a_copy_clause(
    text: str,
) -> Callable[[Game, StackObject], None] | None:
    match = _BECOMES_A_COPY_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    exceptions = None
    if match.group("exception"):
        exceptions = _parse_become_copy_exceptions(match.group("exception"))
        if exceptions is None:
            return None
    if match.group("lead") and match.group("trail"):
        return None
    duration = _copy_duration(match.group("lead") or match.group("trail"))
    subject_is_target = match.group("subject").lower().startswith("target")
    exiled_card = match.group("object").lower() == "the exiled card"
    if exiled_card and subject_is_target:
        return None

    def effect(game: Game, stack_object: StackObject) -> None:
        from .triggers import AbilityOnStack as StackAbility

        is_ability = isinstance(stack_object, StackAbility)
        controller = (
            stack_object.controller if is_ability else game.controller_of(stack_object).username
        )
        source = stack_object.source(game) if is_ability else stack_object
        legal = {target.id: target for target in game.resolve_card_targets(stack_object)}
        announced = [
            legal.get(reference.card_id) if reference.is_card else None
            for reference in stack_object.targets
        ]
        if subject_is_target:
            if len(announced) < 2:
                return
            subject, copied_object = announced[0], announced[1]
        else:
            if (
                source is None
                or source.zone is not Zone.BATTLEFIELD
                or (
                    is_ability and stack_object.source_stamp not in (None, source.zone_change_stamp)
                )
            ):
                return
            subject = source
            if exiled_card:
                # Dermotaxi: "the exiled card" is the one exiled with this
                # permanent as it entered (CR 607.2a), not a target.
                linked = game.cards_exiled_with(source.id, None)
                copied_object = linked[0] if linked else None
            else:
                copied_object = announced[0] if announced else None
        if subject is None or copied_object is None or subject.zone is not Zone.BATTLEFIELD:
            return  # CR 115.6's "up to one" chose none, or CR 608.2b removed it
        this_ability = None
        if is_ability:
            this_ability = (stack_object.ability.raw or stack_object.ability.text or "").strip()
        _become_a_copy(
            game,
            subject=subject,
            copied=_copiable_values_of(game, copied_object),
            exceptions=exceptions,
            source_name=stack_object.source_name if is_ability else stack_object.name,
            own_name=subject.name,
            this_ability=this_ability,
            duration=duration,
            until_next_turn_of=controller if duration is Duration.UNTIL_YOUR_NEXT_TURN else None,
        )

    return effect


#: A sentence boundary outside a quoted ability: ". " followed by the next
#: sentence's capital letter.
_SENTENCE_BOUNDARY_RE = re.compile(r"\.\s+(?=[A-Z])")


def _parse_becomes_a_copy_then_rider_ability(text: str) -> AbilityEffect | None:
    """`_BECOMES_A_COPY_RE`'s sentence followed by further instructions of the
    same ability - Oko, the Trickster's "Until end of turn, Oko becomes a copy
    of target creature you control. Prevent all damage that would be dealt to
    him this turn." The copy is made first and the rest runs after it, read
    by the same remainder reader every layer sentence's rider goes through
    (`_layer_remainder_or_composed`); an unreadable rest fails the whole
    ability rather than half of it (CR 608.2c)."""
    from .effects import _layer_remainder_or_composed

    flat = " ".join(text.split())
    for boundary in _SENTENCE_BOUNDARY_RE.finditer(flat):
        head, rest = flat[: boundary.start() + 1], flat[boundary.end() :]
        if head.count('"') % 2:
            continue  # inside a quoted ability
        copy = _parse_becomes_a_copy_clause(head)
        if copy is None:
            continue
        rider = _layer_remainder_or_composed(rest, for_spell=False)
        if rider is None:
            return None
        return _copy_then_rider(copy, rider)
    return None


def _copy_then_rider(
    copy: Callable[[Game, StackObject], None], rider: Callable[[Game, StackObject], None]
) -> AbilityEffect:
    from .turn_scoped_riders import run_layer_then_rider

    def effect(game: Game, ability: AbilityOnStack) -> None:
        run_layer_then_rider(game, ability, copy, rider)

    return effect


#: "Each `<group>` becomes a copy of target `<quality>`[ until end of turn]."
#: - Mirrorform's "Each nonland permanent you control becomes a copy of
#: target non-Aura permanent." and Mirrorweave's "Each other creature becomes
#: a copy of target nonlegendary creature until end of turn." CR 707.4: each
#: permanent in the group stays on the battlefield and copies the target's
#: copiable values (CR 707.2, as modified by other copy effects), in one
#: layer 1a effect each (CR 613.1a) sharing one timestamp (CR 613.7b). The
#: group is fixed as the spell or ability resolves (CR 611.2c). "Other" is
#: other than the target (and the source, for a permanent's ability). With
#: no duration the copies last until the end of the game (CR 611.2a).
_EACH_BECOMES_A_COPY_RE = re.compile(
    r"^each (?P<other>other )?(?P<group>(?:non(?:land|creature|token|artifact) )?"
    r"(?:permanent|creature|artifact|enchantment|land|token))"
    r"(?P<whose> you control| your opponents control)?"
    r" becomes a copy of (?P<object>target [^.]+?|that creature)"
    r"(?P<trail> until end of turn| until your next turn)?\.?$",
    re.IGNORECASE,
)

_GROUP_TYPE_WORDS = {
    "permanent": None,
    "creature": Type.CREATURE,
    "artifact": Type.ARTIFACT,
    "enchantment": Type.ENCHANTMENT,
    "land": Type.LAND,
}


def _each_group_member(characteristics: Characteristics, group: str) -> bool:
    """Whether a permanent with these computed characteristics (CR 613.5) is
    one of `group`'s ("nonland permanent", "creature", "nontoken creature")."""
    words = group.lower().split()
    noun = words[-1]
    if noun == "token":
        if not characteristics.is_token:
            return False
    else:
        wanted = _GROUP_TYPE_WORDS[noun]
        if wanted is not None and wanted not in characteristics.types:
            return False
    for word in words[:-1]:
        excluded = word.removeprefix("non")
        if excluded == "token":
            if characteristics.is_token:
                return False
            continue
        excluded_type = _GROUP_TYPE_WORDS.get(excluded)
        if excluded_type is not None and excluded_type in characteristics.types:
            return False
    return True


def _parse_each_becomes_a_copy_clause(
    text: str,
) -> Callable[[Game, StackObject], None] | None:
    match = _EACH_BECOMES_A_COPY_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    group = match.group("group")
    other = match.group("other") is not None
    whose = (match.group("whose") or "").strip().lower()
    duration = _copy_duration(match.group("trail"))
    enchanted = match.group("object").lower() == "that creature"

    def effect(game: Game, stack_object: StackObject) -> None:
        from .triggers import AbilityOnStack as StackAbility

        is_ability = isinstance(stack_object, StackAbility)
        controller = game.controller_of(stack_object).username
        if enchanted:
            # Infinite Reflection: "that creature" is the creature the Aura
            # just entered attached to (CR 303.4).
            source = stack_object.source_or_last_known(game) if is_ability else None
            host = game.find_by_id(source.attached_to) if source is not None else None
            targets = (
                [host] if isinstance(host, CardState) and host.zone is Zone.BATTLEFIELD else []
            )
        else:
            targets = game.resolve_card_targets(stack_object)
        if not targets:
            return  # CR 608.2b: the only target is gone or illegal
        copied_object = targets[0]
        copied = _copiable_values_of(game, copied_object)
        source_id = stack_object.source_id if is_ability else stack_object.id
        board = game.computed_board()
        group_members = []
        for permanent in game.battlefield:
            chars = board.of(permanent)
            if other and permanent.id in (copied_object.id, source_id):
                continue
            permanent_controller = game.controller_of(permanent).username
            if whose == "you control" and permanent_controller != controller:
                continue
            if whose == "your opponents control" and permanent_controller == controller:
                continue
            if _each_group_member(chars, group):
                group_members.append(permanent)
        if not group_members:
            return
        timestamp = game.continuous_effects.tick()
        source_name = stack_object.source_name if is_ability else stack_object.name
        for member in group_members:
            _become_a_copy(
                game,
                subject=member,
                copied=copied,
                exceptions=None,
                source_name=source_name,
                own_name=member.name,
                this_ability=None,
                duration=duration,
                until_next_turn_of=controller
                if duration is Duration.UNTIL_YOUR_NEXT_TURN
                else None,
                timestamp=timestamp,
            )

    return effect


# ---------------------------------------------------------------------------
# "create a token that's a copy of one of them" / "for each of them, create a
# token that's a copy of it"
# ---------------------------------------------------------------------------

#: Twilight Diviner's "create a token that's a copy of one of them." and
#: Kambal, Profiteering Mayor's "for each of them, create a tapped token
#: that's a copy of it." - "them" is what entered in the one event that
#: triggered the ability (CR 603.6a, `GameEvent.entered_together`), narrowed
#: to the members its own condition and intervening "if" (CR 603.4) are true
#: of (`_entered_batch`). CR 707.2: each token takes the copiable values; a
#: member no longer on the battlefield is copied by its last known
#: information (CR 608.2h), which for a printed card is its printing.
_COPY_OF_ONE_OF_THEM_RE = re.compile(
    r"^create an? (?P<tapped>tapped )?token that'?s a copy of one of them\.?$",
    re.IGNORECASE,
)
_FOR_EACH_OF_THEM_COPY_RE = re.compile(
    r"^for each of them, create an? (?P<tapped>tapped )?token that'?s a copy of it\.?$",
    re.IGNORECASE,
)


def _entered_batch(game: Game, ability: AbilityOnStack) -> list[CardState]:
    """The permanents "them" names: the triggering event's subject, plus every
    other permanent that entered in the same event (CR 603.6a) that this
    ability's own trigger condition (CR 603.2) and intervening "if" (CR
    603.4) are true of - read off each one's own enters event, the same
    reading that decided the subject triggered it."""
    from .triggers import condition_matches, intervening_if_answer

    event = ability.event
    source = ability.source_or_last_known(game)
    if event is None or event.subject_id is None or source is None:
        return []
    pairs = event.entered_together or ((event.subject_id, event.origin_zone),)
    members: list[CardState] = []
    for member_id, origin in pairs:
        member = game.find_by_id(member_id)
        if not isinstance(member, CardState):
            continue
        if member_id == event.subject_id:
            members.append(member)
            continue
        if member.zone is not Zone.BATTLEFIELD:
            continue
        member_event = game._enters_event(member).model_copy(update={"origin_zone": origin})
        if not condition_matches(game, ability.ability, source, ability.controller, member_event):
            continue
        if ability.ability.intervening_if and not intervening_if_answer(
            game, ability.ability, source, member_event
        ):
            continue
        members.append(member)
    return members


def _parse_copy_of_them_clause(text: str) -> AbilityEffect | None:
    one = _COPY_OF_ONE_OF_THEM_RE.fullmatch(" ".join(text.split()))
    each = _FOR_EACH_OF_THEM_COPY_RE.fullmatch(" ".join(text.split()))
    match = one or each
    if match is None:
        return None
    tapped = match.group("tapped") is not None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        from ..models.token import token_copy_of

        members = _entered_batch(game, ability)
        if not members:
            return
        if one is not None and len(members) > 1:
            by_id = {member.id: member for member in members}
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=ability.controller,
                    prompt="choose one of them to create a token copy of",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    amount=1,
                    cards=tuple(by_id),
                    card_labels=tuple(member.name for member in members),
                )
            )
            assert isinstance(chosen_ids, tuple)
            members = [by_id[card_id] for card_id in chosen_ids if card_id in by_id][:1]
        elif one is not None:
            members = members[:1]
        for member in members:
            token_copy_of(game, member, ability.controller, tapped=tapped)

    return effect


#: Secret Invasion's whole enters trigger: "exile up to one target creature
#: other than enchanted creature until this Aura leaves the battlefield.
#: Enchanted creature becomes a copy of that creature until this Aura leaves
#: the battlefield." The exile is CR 610.3's "until ... leaves the
#: battlefield" one-shot (returned by the same delayed trigger
#: `machines/effects._watch_for_departure_and_return_exiled_card` builds);
#: "that creature" is the exiled one as it last existed (CR 608.2h), its
#: copiable values taken before it moved; the copy lasts "for as long as"
#: the Aura remains (CR 611.2b).
_EXILE_THEN_BECOME_ITS_COPY_RE = re.compile(
    r"^exile (?P<phrase>(?:up to one )?target .+?) until this (?P<noun>aura|enchantment|"
    r"creature|artifact|permanent) leaves the battlefield\.\s*"
    r"(?P<subject>enchanted creature|this creature|this permanent) becomes a copy of "
    r"that (?:creature|permanent|card)(?P<duration> until this (?:aura|enchantment|creature"
    r"|artifact|permanent) leaves the battlefield)?\.?$",
    re.IGNORECASE,
)


def _parse_exile_then_become_its_copy_clause(text: str) -> AbilityEffect | None:
    match = _EXILE_THEN_BECOME_ITS_COPY_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None

    from .effects import _targets_understood, _watch_for_departure_and_return_exiled_card

    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    enchanted = match.group("subject").lower() == "enchanted creature"
    lasting = match.group("duration") is not None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return  # CR 113.7a: nothing left to watch leave
        targets = [
            target
            for target in game.resolve_card_targets(ability)
            if target.zone is Zone.BATTLEFIELD
        ]
        for target in targets:
            copied = _copiable_values_of(game, target)
            exiled = game.exile_permanent(target)
            if exiled.zone is not Zone.EXILE:
                continue
            _watch_for_departure_and_return_exiled_card(game, source, exiled, ability.controller)
            subject_id = source.attached_to if enchanted else source.id
            subject = game.find_by_id(subject_id) if subject_id is not None else None
            if not isinstance(subject, CardState) or subject.zone is not Zone.BATTLEFIELD:
                continue
            _become_a_copy(
                game,
                subject=subject,
                copied=copied,
                exceptions=None,
                source_name=ability.source_name,
                own_name=subject.name,
                this_ability=None,
                duration=Duration.FOR_AS_LONG_AS if lasting else Duration.INDEFINITE,
                condition=(
                    RemainsOnBattlefield(card_id=source.id, stamp=source.zone_change_stamp)
                    if lasting and source.zone_change_stamp is not None
                    else None
                ),
            )

    return effect


# ---------------------------------------------------------------------------
# "<instruction>. If <it|the token> isn't a creature, it becomes an N/N ..."
# ---------------------------------------------------------------------------

#: Ultron, Artificial Malevolence's "... create a token that's a copy of it.
#: If the token isn't a creature, it becomes a 2/2 Robot Villain creature in
#: addition to its other types." and Tawnos's Tinkering's "Put two +1/+1
#: counters on target artifact, creature, or land you control. Untap that
#: permanent. If it isn't a creature, it becomes a 0/0 creature in addition
#: to its other types." The rider's condition is checked as it is reached
#: (CR 608.2c); "the token" is the one the instruction before it created,
#: "it"/"that permanent" the instruction's own target. Layer 4 adds the
#: creature type and subtypes (CR 205.1b), sublayer 7b sets the base P/T
#: (CR 613.4b), layer 6 grants any keywords (CR 613.1f).
_IF_NOT_A_CREATURE_BECOMES_RE = re.compile(
    r"^(?P<first>.+?\.)\s*if (?P<ref>it|the token|that (?:permanent|artifact|token)) isn'?t a "
    r"creature, it becomes an? (?P<power>\d+)/(?P<toughness>\d+) "
    r"(?P<subtypes>(?:[A-Z][\w'-]* )*)creature(?: with (?P<keywords>[a-z][a-z ,]*?))? "
    r"in addition to its other types(?P<until_eot> until end of turn)?\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _if_not_a_creature_rider(
    text: str, first_reader: Callable[[str], object]
) -> Callable[[Game, StackObject], None] | None:
    match = _IF_NOT_A_CREATURE_BECOMES_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None

    from .layers import (
        AddSubtype,
        _creature_type_words,
        _split_and_validate_keywords,
        add_type,
        grant_ability,
        set_power_toughness,
    )
    from .layers import Sublayer as PTSublayer

    first = first_reader(match.group("first").strip())
    if first is None or getattr(first, "__name__", "").endswith("notice_only"):
        return None
    subtypes = (
        _creature_type_words(match.group("subtypes").strip())
        if match.group("subtypes").strip()
        else []
    )
    keywords = (
        _split_and_validate_keywords(match.group("keywords")) if match.group("keywords") else []
    )
    if subtypes is None or keywords is None:
        return None
    power, toughness = int(match.group("power")), int(match.group("toughness"))
    about_the_token = match.group("ref").lower() == "the token"
    duration = Duration.UNTIL_END_OF_TURN if match.group("until_eot") else Duration.INDEFINITE

    def effect(game: Game, stack_object: StackObject) -> None:
        before = {permanent.id for permanent in game.battlefield}
        first(game, stack_object)  # type: ignore[operator]
        if about_the_token:
            referents = [
                permanent
                for permanent in game.battlefield
                if permanent.id not in before and permanent.token
            ]
        else:
            referents = [
                target
                for target in game.resolve_card_targets(stack_object)
                if target.zone is Zone.BATTLEFIELD
            ]
        store = game.continuous_effects
        for referent in referents:
            if game.characteristics_of(referent).is_creature:
                continue
            timestamp = store.tick()
            selector = only_this_incarnation(referent, referent.zone_change_stamp)
            parts: list[tuple[Layer, PTSublayer | None, object]] = [
                (Layer.TYPE, None, add_type(Type.CREATURE)),
                *((Layer.TYPE, None, AddSubtype(subtype=subtype)) for subtype in subtypes),
                *((Layer.ABILITY, None, grant_ability(keyword)) for keyword in keywords),
                (Layer.POWER_TOUGHNESS, PTSublayer.SET, set_power_toughness(power, toughness)),
            ]
            for layer, sublayer, modification in parts:
                store.add(
                    ContinuousEffect(
                        description=f"{referent.name} becomes a {power}/{toughness} creature",
                        layer=layer,
                        sublayer=sublayer,
                        timestamp=timestamp,
                        duration=duration,
                        selector=selector,
                        modification=modification,  # type: ignore[arg-type]
                    ),
                    game,
                )

    return effect


def _parse_if_not_a_creature_ability(text: str) -> AbilityEffect | None:
    from .effects import _ability_effect_or_notice

    return _if_not_a_creature_rider(text, _ability_effect_or_notice)  # type: ignore[return-value]


def _parse_if_not_a_creature_spell(text: str) -> Effect | None:
    from .effects import _spell_effect_or_notice

    return _if_not_a_creature_rider(text, _spell_effect_or_notice)  # type: ignore[return-value]


def copy_ability_effect(effect_text: str) -> AbilityEffect | None:
    """A copy instruction on an activated or triggered ability, or `None`."""
    for reader in (
        _parse_if_not_a_creature_ability,
        _parse_copy_of_them_clause,
        _parse_exile_then_become_its_copy_clause,
        _parse_each_becomes_a_copy_clause,
        _parse_becomes_a_copy_clause,
        _parse_becomes_a_copy_then_rider_ability,
        _parse_copy_target_ability_clause,
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
    for reader in (
        _parse_if_not_a_creature_spell,
        _parse_each_becomes_a_copy_clause,
        _parse_becomes_a_copy_clause,
        _parse_copy_next_within_mana_value_spell,
        _parse_spell_after_cast_trigger,
    ):
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None
