"""Static replacement effects that modify a damage event as it would happen
(CR 614.1a, CR 614.2), compiled from a permanent's own printed text.

`machines/replacement.py` owns the replacement machinery - parsing a
permanent's "If ... would ..., ... instead" sentences into `ReplacementEffect`
records, gathering the applicable ones off the battlefield, and CR 616.1's
ordering. This module only adds two more of its `_COMPILERS`:

- `compile_damage_plus_source_characteristic` - "If a source you control
  would deal noncombat damage to an opponent or a permanent an opponent
  controls, instead it deals that much damage plus X, where X is Hawkeye's
  power." (Hawkeye, Young Avenger). The same event shape and recipient phrases
  `replacement._compile_damage_plus_amount` reads for Torbran's fixed "plus
  2", with an addend read off the permanent carrying the effect each time
  the replacement applies.
- `compile_heal_other_damage` - "If damage would be dealt to Wolverine,
  instead that damage is dealt, but all other damage already dealt to him is
  healed." (Wolverine, Fierce Fighter): the damage is dealt unchanged, and
  the damage already marked on the permanent (CR 120.3e) is removed first.
  Combat damage is one simultaneous event (CR 510.2), so damage another
  source dealt in the same combat damage step is not "already dealt" and is
  kept (`Game.combat_damage_marked_this_step`).

The replacement-module names are imported inside each function: this module
is itself imported by `machines/replacement.py` while that module is still
loading.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal
from uuid import UUID

from pydantic import Field

from ..models.card_state import CardState
from ..models.zone import Zone
from ..snapshot import EngineModel

if TYPE_CHECKING:
    from ..models.game import Game
    from ..models.player import Player
    from .replacement import CardReplacement, ReplaceableEvent, ReplacementEffect

#: "it deals that much damage plus X, where X is `<name>`'s power" - the
#: addend a characteristic of the permanent that has the effect (CR 201.5:
#: its own name, or its short name, or "this creature").
_PLUS_SOURCE_CHARACTERISTIC_RE = re.compile(
    r"^it deals that much damage plus x, where x is (?P<who>.+?)'s "
    r"(?P<stat>power|toughness)$",
    re.IGNORECASE,
)


def _names_itself(who: str, holder: CardState) -> bool:
    """Whether `who` is how `holder`'s own text names it (CR 201.5)."""
    lowered = who.strip().lower()
    names = {
        "this creature",
        "this permanent",
        holder.name.lower(),
        holder.name.split(",")[0].strip().lower(),
    }
    return lowered in names


def compile_damage_plus_source_characteristic(
    effect: "ReplacementEffect",
) -> "CardReplacement | None":
    """Hawkeye, Young Avenger's shape - see the module docstring."""
    from .replacement import (
        _SOURCE_YOU_CONTROL_DAMAGE_EVENT_RE,
        CardReplacement,
        EventKind,
        ReplacementKind,
    )
    from .replacement.parse import damage_recipient

    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    event_match = _SOURCE_YOU_CONTROL_DAMAGE_EVENT_RE.fullmatch((effect.event or "").strip())
    if event_match is None:
        return None
    if event_match.group("subject").lower() != "source" or event_match.group("recipient") is None:
        return None
    if event_match.group("yours") is None:
        return None  # "a source you control" is what `applies` checks below.
    recipient = damage_recipient(event_match.group("recipient"))
    if recipient is None:
        return None
    match = _PLUS_SOURCE_CHARACTERISTIC_RE.fullmatch((effect.replacement or "").strip().rstrip("."))
    if match is None:
        return None
    quality = event_match.group("quality")
    noncombat = event_match.group("noncombat") is not None
    who = match.group("who")
    wants_power = match.group("stat").lower() == "power"

    def applies(game: "Game", source: CardState, event: "ReplaceableEvent") -> bool:
        if event.kind is not EventKind.DAMAGE or event.source is None:
            return False
        if noncombat and event.combat:
            return False
        if not _names_itself(who, source):
            return False
        controller = game.controller_of(source).username
        if game.controller_of(event.source).username != controller:
            return False
        if quality is not None and not game.source_has_quality(event.source, quality):
            return False
        return recipient(game, controller, event)

    def apply(game: "Game", source: CardState, event: "ReplaceableEvent") -> None:
        # The characteristic as this replacement applies, off the computed
        # board (CR 613.5).
        value = game.power_of(source) if wants_power else game.toughness_of(source)
        event.amount += max(value or 0, 0)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


#: "If damage would be dealt to `<name>`" / "... that damage is dealt, but all
#: other damage already dealt to him is healed".
_DAMAGE_DEALT_TO_SELF_EVENT_RE = re.compile(
    r"^damage would be dealt to (?P<who>.+)$", re.IGNORECASE
)
_HEAL_OTHER_DAMAGE_RE = re.compile(
    r"^that damage is dealt, but all other damage already dealt to (?:it|him|her|them) "
    r"is healed$",
    re.IGNORECASE,
)


def compile_heal_other_damage(effect: "ReplacementEffect") -> "CardReplacement | None":
    """Wolverine, Fierce Fighter's shape - see the module docstring."""
    from .replacement import CardReplacement, EventKind, ReplacementKind

    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    event_match = _DAMAGE_DEALT_TO_SELF_EVENT_RE.fullmatch((effect.event or "").strip())
    if event_match is None:
        return None
    if _HEAL_OTHER_DAMAGE_RE.fullmatch((effect.replacement or "").strip().rstrip(".")) is None:
        return None
    who = event_match.group("who")

    def applies(game: "Game", source: CardState, event: "ReplaceableEvent") -> bool:
        return (
            event.kind is EventKind.DAMAGE
            and event.card is not None
            and event.card.id == source.id
            and source.zone is Zone.BATTLEFIELD
            and _names_itself(who, source)
        )

    def apply(game: "Game", source: CardState, event: "ReplaceableEvent") -> None:
        simultaneous = game.combat_damage_marked_this_step(source) if event.combat else 0
        source.damage = min(source.damage, simultaneous)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


# --------------------------------------------------------------------------
# Turn-long damage replacement and prevention a resolving spell creates
# --------------------------------------------------------------------------
#
# CR 614.1a / CR 615.1a with CR 611.2a's stated duration: "If a source you
# control would deal damage this turn, it deals double that damage instead."
# (Insult), "Prevent all damage that would be dealt by creatures this turn.
# You gain life equal to the damage prevented this way." (Chant of
# Vitu-Ghazi, Ethereal Haze), "Damage can't be prevented this turn." beside
# one of them (Insult, CR 615.12), and the redirection effects (CR 614.9):
# "All damage that would be dealt this turn to target creature you control by
# a source of your choice is dealt to another target creature instead." (Kor
# Dirge), "All combat damage that would be dealt to you this turn is dealt to
# target attacking creature instead." (Turn the Tables), "The next N damage
# that would be dealt to target creature this turn is dealt to another target
# creature instead." (Carom, Razia, Boros Archangel).
#
# Each is a `CreatedReplacementSpec` (`machines/replacement/model.py`) held on
# `Game.created_replacements` until CR 514.2's cleanup. `machines/replacement/
# parse.read_turn_damage_spec` reads the sentence; a spec naming the creating
# spell's targets or a source of the caster's choice is completed by `bind`
# when the record is created, as the spell resolves (CR 608.2b, CR 609.7a).


def _is_damage(event: "ReplaceableEvent") -> bool:
    from .replacement import EventKind

    return event.kind is EventKind.DAMAGE and event.amount > 0


def _source_is_creature(game: "Game", source: CardState) -> bool:
    return game.source_has_quality(source, "creature")


class DamageModifierReplacement(EngineModel):
    """ "If a [`<quality>`] source/creature you control would deal [noncombat]
    damage [to `<recipients>`], it deals double/triple that damage / that much
    damage plus N instead." (CR 614.1a, CR 701.10g; CR 609.7b rechecks the
    source as the damage would be dealt). "You" is the effect's controller.
    The static twin (`replacement._compile_damage_plus_amount`) reads the same
    shape off a permanent and asks this model the same questions."""

    kind: Literal["damage_modifier"] = "damage_modifier"
    #: "source" or "creature": what the dealing object has to be.
    subject: Literal["source", "creature"] = "source"
    quality: str | None = None
    noncombat: bool = False
    #: A `replacement.parse.damage_recipient` phrase; None is any recipient.
    recipient: str | None = None
    factor: int = 1
    addend: int = 0
    #: True for a printed "a source would deal" with no "you control" (Rankle
    #: and Torbran's third mode): CR 614.1a's replacement then applies to a
    #: source whoever controls it.
    any_controller: bool = False

    prevention: ClassVar[bool] = False

    def applies(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> bool:
        from .replacement.parse import damage_recipient

        if controller is None or not _is_damage(event) or event.source is None:
            return False
        if self.noncombat and event.combat:
            return False  # "noncombat damage" (CR 510.2 marks combat damage).
        if not self.any_controller and game.controller_of(event.source).username != controller:
            return False  # "a source *you* control", checked now (CR 609.7b).
        if self.subject == "creature" and not _source_is_creature(game, event.source):
            return False
        if self.quality is not None and not game.source_has_quality(event.source, self.quality):
            return False
        if self.recipient is None:
            return True
        recipient = damage_recipient(self.recipient)
        return recipient is not None and recipient(game, controller, event)

    def apply(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> None:
        event.amount = event.amount * self.factor + self.addend


class PreventDamageByReplacement(EngineModel):
    """ "Prevent all [combat] damage that would be dealt by `<quality>`
    [sources] this turn." with, optionally, CR 615.5's "You gain life equal to
    the damage prevented this way." (CR 615.1a). CR 609.7b: the source's
    quality is rechecked each time it would deal damage, so a creature that
    stops being one deals its damage, and one animated later is covered. Each
    prevented event gains its own life (CR 615.5: "immediately afterward").
    Against damage that can't be prevented (CR 615.12) it still applies,
    prevents nothing, and so gains nothing."""

    kind: Literal["prevent_damage_by"] = "prevent_damage_by"
    source_quality: str
    combat_only: bool = False
    gains_life: bool = False

    prevention: ClassVar[bool] = True

    def applies(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> bool:
        if not _is_damage(event) or event.source is None:
            return False
        if self.combat_only and not event.combat:
            return False
        return game.source_has_quality(event.source, self.source_quality)

    def apply(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> None:
        if game.damage_cant_be_prevented(event) is not None:
            return  # CR 615.12: nothing is prevented, so nothing is gained.
        prevented = event.amount
        event.amount = 0
        if self.gains_life and prevented > 0 and controller is not None:
            game.gain_life(controller, prevented)


class DamageCantBePreventedReplacement(EngineModel):
    """ "[Combat] damage can't be prevented this turn." carried beside another
    turn-long damage effect of the same spell (Insult) - CR 615.12. It replaces
    nothing itself: `Game.damage_cant_be_prevented` asks `makes_unpreventable`
    of every created record, the same question it asks Skullcrack's recorded
    rule (`CastingRuleKind.DAMAGE_CANT_BE_PREVENTED`)."""

    kind: Literal["damage_cant_be_prevented"] = "damage_cant_be_prevented"
    combat_only: bool = False

    prevention: ClassVar[bool] = False

    def applies(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> bool:
        return False

    def apply(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> None:
        return None

    def makes_unpreventable(self, event: "ReplaceableEvent") -> bool:
        from .replacement import EventKind

        return event.kind is EventKind.DAMAGE and (event.combat or not self.combat_only)


class DamageRedirectReplacement(EngineModel):
    """A redirection effect (CR 614.9) created by a resolving spell or ability:
    damage that would be dealt to the protected creature or player is dealt to
    the redirect target instead.

    Read from the sentence (`replacement.parse.read_turn_damage_spec`) with
    the targets as indexes into the creating object's targets
    (`protected_target`, `redirect_target`); `bind` fixes them to the objects
    chosen, once they are rechecked on resolution (CR 608.2b), and asks the
    controller for "a source of your choice" when the text names one (CR
    609.7a: "The source is chosen when the effect is created").

    CR 614.9: "If one of those permanents is no longer on the battlefield when
    the damage would be redirected, or is no longer a battle, creature, or
    planeswalker when the damage would be redirected, the effect does
    nothing." - so the redirect target is rechecked as the damage would be
    dealt, and the damage then goes where it was going (Turn the Tables'
    attacker gone: the damage is dealt to you).

    `amount` is "the next N damage" (CR 615.7's twin for a redirection): N is
    what is left to redirect, spent as damage is redirected; None is "all".
    `amount_is_x` reads N as the creating spell's announced X (CR 107.3a) as
    it binds (Shining Shoal).

    `protects_yours` is "you and/or permanents [creatures] you control" (Harm's
    Way, Shining Shoal): the controller, and every permanent they control
    with `protected_types` as the damage would be dealt - one counted shield
    across all of them. The redirect target may be "any target" (CR 115.4),
    so a player as well as a permanent; a player who has left the game takes
    nothing and the damage stays where it was going (CR 614.9).
    """

    kind: Literal["damage_redirect"] = "damage_redirect"
    combat_only: bool = False
    protected_target: int | None = None
    """Which of the creating object's targets is protected; None for "you"."""
    redirect_target: int = 0
    choose_source: bool = False
    amount: int | None = None
    amount_is_x: bool = False
    protects_yours: bool = False
    protected_types: tuple[str, ...] = ()
    redirect_to_enchanted: bool = False
    """"is dealt to enchanted creature instead" (Saving Grace): the redirect
    target is what the creating object's source is attached to as the effect
    is created (CR 303.4b), fixed then - not a target."""

    bound: bool = False
    protected_id: UUID | None = None
    protected_stamp: UUID | None = None
    protected_player: str | None = None
    redirect_id: UUID | None = None
    redirect_stamp: UUID | None = None
    redirect_player: str | None = None
    source_id: UUID | None = None
    source_stamp: UUID | None = None

    prevention: ClassVar[bool] = False

    def bind(self, game: "Game", stack_object: Any) -> "DamageRedirectReplacement | None":
        targets = list(getattr(stack_object, "targets", ()) or ())

        def legal(index: int | None) -> CardState | None:
            if index is None or index >= len(targets):
                return None
            found = game.legal_target(stack_object, targets[index])
            return found if isinstance(found, CardState) else None

        from ..models.player import Player

        if self.redirect_to_enchanted:
            redirect_found = _enchanted_by_source_of(game, stack_object)
        else:
            redirect_found = (
                game.legal_target(stack_object, targets[self.redirect_target])
                if self.redirect_target < len(targets)
                else None
            )
        controller = game.controller_of(stack_object).username
        update: dict[str, Any] = {"bound": True}
        if isinstance(redirect_found, CardState):
            update["redirect_id"] = redirect_found.id
            update["redirect_stamp"] = redirect_found.zone_change_stamp
        elif isinstance(redirect_found, Player):
            update["redirect_player"] = redirect_found.username
        else:
            return None  # CR 608.2b: no legal target left to redirect to.
        if self.amount_is_x:
            x_value = (
                game.cast_record(stack_object).x_value
                if isinstance(stack_object, CardState)
                else getattr(stack_object, "x_value", None)
            )
            if not x_value:
                return None  # the next 0 damage: nothing to redirect
            update["amount"] = x_value
        if self.protects_yours or self.protected_target is None:
            update["protected_player"] = controller
        else:
            protected = legal(self.protected_target)
            if protected is None:
                return None
            update["protected_id"] = protected.id
            update["protected_stamp"] = protected.zone_change_stamp
        if self.choose_source:
            chosen = _choose_a_source(game, controller, stack_object)
            if chosen is None:
                return None
            update["source_id"] = chosen.id
            # CR 609.7a: a permanent spell chosen on the stack also covers the
            # permanent it becomes, so only a permanent is held to its stamp.
            update["source_stamp"] = (
                chosen.zone_change_stamp if chosen.zone is Zone.BATTLEFIELD else None
            )
        return self.model_copy(update=update)

    def _redirect_to(self, game: "Game") -> "CardState | Player | None":
        from ..models.card import Type

        if self.redirect_player is not None:
            if not game.is_in_game(self.redirect_player):
                return None  # CR 614.9: a player who has left the game
            return game.player(self.redirect_player)
        if self.redirect_id is None:
            return None
        found = game.find_by_id(self.redirect_id)
        if found is None or found.zone is not Zone.BATTLEFIELD:
            return None
        if found.zone_change_stamp != self.redirect_stamp:
            return None  # CR 400.7: a new object the effect never named.
        types = game.characteristics_of(found).types
        if not ({Type.CREATURE, Type.PLANESWALKER, Type.BATTLE} & set(types)):
            return None
        return found

    def applies(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> bool:
        if not self.bound or not _is_damage(event):
            return False
        if self.amount is not None and self.amount <= 0:
            return False
        if self.combat_only and not event.combat:
            return False
        if event.card is not None and event.card.id == self.redirect_id:
            return False  # already going to the new recipient: nothing to redirect
        if self.protects_yours:
            if not self._protects(game, event):
                return False
        elif self.protected_player is not None:
            if event.player is None or event.player.username != self.protected_player:
                return False
        elif (
            event.card is None
            or event.card.id != self.protected_id
            or event.card.zone_change_stamp != self.protected_stamp
        ):
            return False
        if self.source_id is not None:
            source = event.source
            if source is None or source.id != self.source_id:
                return False
            if self.source_stamp is not None and not game.damage_source_is_object(
                source, self.source_id, self.source_stamp
            ):
                return False
        return self._redirect_to(game) is not None

    def _protects(self, game: "Game", event: "ReplaceableEvent") -> bool:
        """ "you and/or permanents [creatures] you control", read as the damage
        would be dealt."""
        if event.player is not None:
            return event.player.username == self.protected_player
        card = event.card
        if card is None or card.zone is not Zone.BATTLEFIELD:
            return False
        if game.controller_of(card).username != self.protected_player:
            return False
        types = {str(kind).lower() for kind in game.characteristics_of(card).types}
        return all(kind in types for kind in self.protected_types)

    def apply(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> None:
        """The same stand-in `replacement._redirect_damage_to_the_source` uses:
        the original event loses the redirected damage (CR 614.6) and the
        redirect target is dealt it as its own event, which keeps it subject
        to that creature's own prevention and replacement effects. Deathtouch
        and lifelink key off damage dealt (CR 702.2b, 702.15b), so they are
        applied to the damage that actually reached the new recipient."""
        target = self._redirect_to(game)
        if target is None:
            return
        moved = event.amount if self.amount is None else min(self.amount, event.amount)
        if self.amount is not None:
            self.amount -= moved
        event.amount -= moved
        source = event.source
        dealt = game.deal_damage(target, moved, source=source)
        if source is not None and dealt > 0 and isinstance(target, CardState):
            game._noncombat_deathtouch_and_lifelink(source, target, dealt)
            if event.combat:
                game.combat_damage_dealt_this_turn_by.add(source.id)


def _enchanted_by_source_of(game: "Game", stack_object: Any) -> CardState | None:
    """The creature the creating ability's source is attached to (CR 303.4b),
    still on the battlefield, or None."""
    source_of = getattr(stack_object, "source_or_last_known", None)
    source = source_of(game) if callable(source_of) else None
    if source is None or source.attached_to is None:
        return None
    host = game.find_by_id(source.attached_to)
    if not isinstance(host, CardState) or host.zone is not Zone.BATTLEFIELD:
        return None
    return host


def _choose_a_source(
    game: "Game",
    controller: str,
    stack_object: Any,
    *,
    eligible: Callable[[CardState], bool] | None = None,
) -> CardState | None:
    """CR 609.7a's "a source of your choice": a permanent or a spell on the
    stack (the objects this engine can name as a damage source), chosen by
    the controller as the effect is created. `eligible` narrows the choice to
    a printed property ("a red source of your choice", CR 609.7b)."""
    from .decisions import Decision, DecisionKind, source_id_of

    candidates = [state for state in game.battlefield if isinstance(state, CardState)]
    candidates.extend(state for state in game.stack if isinstance(state, CardState))
    if eligible is not None:
        candidates = [candidate for candidate in candidates if eligible(candidate)]
    if not candidates:
        return None
    answer = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=controller,
            prompt="choose a source (CR 609.7a)",
            source=getattr(stack_object, "name", None),
            source_id=source_id_of(stack_object),
            amount=1,
            cards=tuple(candidate.id for candidate in candidates),
        )
    )
    chosen = tuple(answer) if isinstance(answer, (tuple, list)) else ()
    by_id = {candidate.id: candidate for candidate in candidates}
    return by_id.get(chosen[0]) if chosen else None


#: The turn-long specs a group can hold (one spell, several sentences).
TurnDamageSpec = Annotated[
    DamageModifierReplacement
    | PreventDamageByReplacement
    | DamageCantBePreventedReplacement
    | DamageRedirectReplacement,
    Field(discriminator="kind"),
]


class TurnDamageGroup(EngineModel):
    """Several turn-long damage effects one resolving spell creates at once,
    in printed order (CR 608.2c) - Insult's "Damage can't be prevented this
    turn. If a source you control would deal damage this turn, it deals
    double that damage instead." Each part applies as its own effect
    (`replacement._created_replacement_effects` expands the group)."""

    kind: Literal["turn_damage_group"] = "turn_damage_group"
    parts: list[TurnDamageSpec]

    prevention: ClassVar[bool] = False

    def applies(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> bool:
        return False

    def apply(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> None:
        return None

    def bind(self, game: "Game", stack_object: Any) -> "TurnDamageGroup | None":
        parts: list[Any] = []
        for part in self.parts:
            bind = getattr(part, "bind", None)
            bound = part if bind is None else bind(game, stack_object)
            if bound is not None:
                parts.append(bound)
        return self.model_copy(update={"parts": parts}) if parts else None


def created_damage_unpreventable(game: "Game", event: "ReplaceableEvent") -> str | None:
    """Why a created record makes this damage unpreventable (CR 615.12)."""
    for record in game.created_replacements:
        spec = record.spec
        parts = spec.parts if isinstance(spec, TurnDamageGroup) else [spec]
        for part in parts:
            if isinstance(part, DamageCantBePreventedReplacement) and part.makes_unpreventable(
                event
            ):
                return f"{record.source_name}: damage can't be prevented this turn (CR 615.12)"
    return None


#: A spell's own "If `<condition>`, this spell can't be countered and the
#: damage can't be prevented." (Banefire's "If X is 5 or more", Demonfire's
#: hellbent "If you have no cards in hand") - CR 113.6g's half is read by
#: `casting_restrictions.conditionally_cannot_be_countered`; this is the CR
#: 615.12 half, for damage the spell itself deals while it is on the stack.
_SPELL_OWN_UNPREVENTABLE_RE = re.compile(
    r"^(?:[A-Z][A-Za-z' -]{2,30}? — )?if (?P<condition>[^,]+), "
    r"this spell can't be countered and the damage can't be prevented\.?$",
    re.IGNORECASE,
)


def spell_damage_unpreventable(game: "Game", event: "ReplaceableEvent") -> str | None:
    """Why damage the resolving spell deals can't be prevented, from its own
    conditional static (CR 604.5: it functions while the spell is on the
    stack), or None. The condition is read now, for the spell's controller,
    by `Game.condition_holds` - an unread condition protects nothing."""
    from .abilities import AbilityKind, parse_abilities

    source = event.source
    if source is None or source.zone is not Zone.STACK:
        return None
    controller = game.controller_of(source).username
    for line in parse_abilities(source.card):
        if line.kind is not AbilityKind.STATIC:
            continue
        match = _SPELL_OWN_UNPREVENTABLE_RE.match((line.text or "").strip())
        if match is None:
            continue
        if game.condition_holds(controller, match.group("condition"), source) is True:
            return f"{source.name}: the damage can't be prevented (CR 615.12)"
    return None
