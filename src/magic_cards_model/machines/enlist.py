"""Enlist (CR 702.154a-d): a creature's optional attack cost to tap another
untapped creature it doesn't already control's attack, adding that
creature's power to its own until end of turn - plus the linked "enlists a
creature" trigger event (CR 702.154b, CR 607.2h).

Every CR number here was looked up with `mise run rules:find <number>` against
the 2026-09-25 Comprehensive Rules release in the session that wrote this
file.

- **CR 702.154a** - "Enlist represents a static ability and a triggered
  ability. Enlist means 'As this creature attacks, you may tap up to one
  untapped creature you control that you didn't choose to attack with and
  that either has haste or has been under your control continuously since
  this turn began. When you do, this creature gets +X/+0 until end of turn,
  where X is the tapped creature's power.'"
- **CR 702.154b** - "Enlist's static ability represents an optional cost to
  attack (see rule 508.1g). Its triggered ability is linked to that static
  ability (see rule 607.2h)."
- **CR 702.154c** - "A creature 'enlists' another creature when you pay the
  cost of the creature's enlist ability by tapping the other creature. Note
  that it isn't possible for a creature to enlist itself."
- **CR 702.154d** - multiple instances of enlist on one creature function
  independently. Not modelled: no printing in the pool carries two.
- **CR 508.1g** - "If there are any optional costs to attack with the chosen
  creatures ... the active player chooses which, if any, they will pay."

Wired additively into `Game.declare_attacker`/`declare_attackers`
(`machines/combat.py`'s own attack-declaration path), alongside - not in
place of - CR 508.1h's existing per-attacker mana cost (`total_attack_cost`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from ..models.zone import Zone
from .combat import Keyword, has_keyword
from .layers import (
    ContinuousEffect,
    Duration,
    Layer,
    Sublayer,
    modify_power_toughness,
    only_this_incarnation,
)
from .triggers import ExtraTriggerEvent, GameEvent

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game

#: CR 702.154a's own keyword name, read generically off any creature's
#: computed keywords (CR 613.5) - not gated on any one card.
ENLIST_KEYWORD = "enlist"


def has_enlist(creature: CardState, game: Game) -> bool:
    """Whether `creature` has enlist right now (CR 613.5's computed board)."""
    return has_keyword(creature, ENLIST_KEYWORD, game)


def eligible_enlist_creatures(
    game: Game, attacker: CardState, other_attacker_ids: set[UUID]
) -> list[CardState]:
    """Every creature `attacker`'s controller could enlist right now
    (CR 702.154a): another creature they control, untapped, not among the
    creatures chosen to attack this declaration, and either has haste or has
    been under their control continuously since the turn began
    (`CardState.summoning_sick`, the identical CR 302.6 test CR 508.1a's own
    attacker-eligibility check reads)."""
    controller = game.controller_of(attacker).username
    eligible: list[CardState] = []
    for creature in game.battlefield:
        if creature.id == attacker.id or creature.id in other_attacker_ids:
            continue
        if creature.tapped or creature.phased_out:
            continue
        if not game.characteristics_of(creature).is_creature:
            continue
        if game.controller_of(creature).username != controller:
            continue
        if creature.summoning_sick and not has_keyword(creature, Keyword.HASTE, game):
            continue
        eligible.append(creature)
    return eligible


def enlist_refusal(
    game: Game, attacker: CardState, enlisted: CardState, other_attacker_ids: set[UUID]
) -> str | None:
    """Why `attacker` cannot enlist `enlisted` right now, or `None`
    (CR 702.154a, 702.154c)."""
    if not has_enlist(attacker, game):
        return f"{attacker.name} has no enlist (CR 702.154a)"
    if enlisted.id == attacker.id:
        return "a creature can't enlist itself (CR 702.154c)"
    if enlisted not in eligible_enlist_creatures(game, attacker, other_attacker_ids):
        return f"{attacker.name} can't enlist {enlisted.name} (CR 702.154a)"
    return None


def enlists_event(enlister: CardState, enlisted: CardState, game: Game) -> GameEvent:
    """CR 702.154b's linked trigger event - Guardian of New Benalia's own
    "Whenever this creature enlists a creature, scry 2." `subject_id` is the
    *enlisting* creature (CR 700.7's "this creature" is the one with the
    keyword, not the one it taps); the tapped creature carries no field of
    its own here since nothing in the pool asks which one it was."""
    controller = game.controller_of(enlister).username
    return GameEvent(
        event=ExtraTriggerEvent.ENLISTS,
        subject_id=enlister.id,
        subject_name=enlister.name,
        subject_controller=controller,
        subject_card=enlister.card,
        subject_types=tuple(enlister.types),
        subject_subtypes=tuple(enlister.subtypes),
        player=controller,
    )


def apply_enlist(game: Game, attacker: CardState, enlisted: CardState) -> None:
    """CR 702.154a-c: tap `enlisted`, give `attacker` +X/+0 until end of
    turn where X is `enlisted`'s power (read live, CR 613.5 - the tapped
    creature stays on the battlefield), and raise the linked trigger event.
    """
    game.tap_permanent(enlisted)
    power = game.power_of(enlisted) or 0
    if power > 0 and attacker.zone is Zone.BATTLEFIELD and attacker.zone_change_stamp is not None:
        store = game.continuous_effects
        store.add(
            ContinuousEffect(
                description=(
                    f"{attacker.name} enlisted {enlisted.name}: "
                    f"{attacker.name} gets +{power}/+0 until end of turn"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=only_this_incarnation(attacker, attacker.zone_change_stamp),
                modification=modify_power_toughness(power, 0),
            ),
            game=game,
        )
    game.emit(enlists_event(attacker, enlisted, game))
