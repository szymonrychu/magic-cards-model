"""Triggered control changes of the ability's own source, and the gain-control
steal with an Equipment attach rider.

Two shapes, both read here and registered into the ability ladder by
`machines/effects/control_copy.py` (the "gain control" family):

- "`<player>` gains control of `<this>`[, untaps it][, and puts N `<kind>`
  counters on it]. [It gains haste until end of turn.]" - Alexios, Deimos of
  Kosmos ("At the beginning of each player's upkeep, that player gains
  control of Alexios, untaps it, and puts a +1/+1 counter on it. It gains
  haste until end of turn."), and Loxodon Peacekeeper ("At the beginning of
  your upkeep, the player with the lowest life total gains control of this
  creature. If two or more players are tied for lowest life total, you choose
  one of them, and that player gains control of this creature.").
  `<player>` is "that player" (the player the trigger event names - the
  active player for an upkeep trigger, CR 102.1) or "the player with the
  lowest life total" (ties broken by the ability's controller, as printed).
- "Gain control of `<target>`. If that `<noun>` is an? `<subtype>`, attach it
  to this creature." - Thieving Skydiver's kicked ETB.

CR 613.1b: layer 2 applies control-changing effects. CR 611.2a: a resolved
ability's effect with no stated duration lasts until the end of the game, so
the change outlives the turn and is overwritten only by a later control
change (CR 613.7's timestamp order inside the layer). CR 701.26b untaps,
CR 122.6 puts the counters on, CR 702.10b haste lets the new controller attack
with it at once, and CR 701.3a attaches (with CR 701.3b's refusals).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import COUNT, parse_count
from .decisions import Decision, DecisionKind, source_id_of
from .layers import (
    ContinuousEffect,
    Duration,
    Layer,
    grant_ability,
    only_this_incarnation,
    set_controller,
)

if TYPE_CHECKING:
    from ..models.game import Game
    from .effects import AbilityEffect
    from .triggers import AbilityOnStack

#: The ability's own source: CR 201.5's printed name (any capitalised name,
#: tried unnormalised first by `trigger_effect_for`) or "this <noun>" once
#: `self_normalized_effect_text` rewrote it.
_SELF = (
    r"(?:this (?:creature|permanent|artifact|enchantment|land|planeswalker)"
    r"|[A-Z][^.,]*?)"
)

#: Who gains control - see the module docstring.
_WHO = r"(?P<who>that player|the player with the lowest life total)"

_GAINS_CONTROL_OF_SELF_RE = re.compile(
    rf"^{_WHO} gains control of {_SELF}"
    r"(?P<untap>,? (?:and )?untaps it)?"
    rf"(?:,? (?:and )?puts (?P<amount>{COUNT}) (?P<kind>[+/\w-]+) counters? on it)?\."
    r"(?P<haste>\s*it gains haste until end of turn\.)?"
    r"(?P<tie>\s*if two or more players are tied for lowest life total, you choose one of "
    rf"them, and that player gains control of {_SELF}\.)?$",
    re.IGNORECASE,
)


def _lowest_life_player(game: Game, ability: AbilityOnStack) -> str | None:
    """The player with the lowest life total; on a tie the ability's
    controller chooses among the tied players ("you choose one of them")."""
    players = list(game.players)
    lowest = min(player.life for player in players)
    tied = [player.username for player in players if player.life == lowest]
    if len(tied) == 1:
        return tied[0]
    chosen = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_PLAYERS,
            player=ability.controller,
            prompt=f"choose which tied player gains control of {ability.source_name}",
            source=ability.source_name,
            amount=1,
            players=tuple(tied),
            source_id=source_id_of(ability),
        )
    )
    assert isinstance(chosen, (list, tuple)) and chosen
    picked = chosen[0]
    return picked if isinstance(picked, str) else getattr(picked, "username", str(picked))


def parse_gains_control_of_self_clause(effect_text: str) -> AbilityEffect | None:
    """`_GAINS_CONTROL_OF_SELF_RE`'s shape, or `None`.

    "That player" needs a trigger event naming a player; the lowest-life form
    is printed with its own tie clause, and a "that player" form never is."""
    match = _GAINS_CONTROL_OF_SELF_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    lowest = match.group("who").lower().startswith("the player")
    if lowest != (match.group("tie") is not None):
        return None
    untap = match.group("untap") is not None
    haste = match.group("haste") is not None
    kind = None
    amount = 0
    if match.group("kind"):
        from .effects import _counter_kind

        kind = _counter_kind(match.group("kind"))
        amount = parse_count(match.group("amount")) or 0
        if kind is None or amount <= 0:
            return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
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
            return  # CR 400.7: a new object, or gone - nothing to give away.
        if lowest:
            player = _lowest_life_player(game, ability)
        else:
            event = ability.event
            player = event.player if event is not None else None
        if player is None:
            return
        store = game.continuous_effects
        timestamp = store.tick()
        selector = only_this_incarnation(source, source.zone_change_stamp)
        store.add(
            ContinuousEffect(
                description=f"{ability.source_name}: {player} gains control of {source.name}",
                layer=Layer.CONTROL,
                timestamp=timestamp,
                duration=Duration.INDEFINITE,
                selector=selector,
                modification=set_controller(player),
            ),
            game=game,
        )
        if untap:
            source.untap()
        if kind is not None:
            game.add_counters(source, kind, amount, putter=player)
        if haste:
            store.add(
                ContinuousEffect(
                    description=f"{ability.source_name}: {source.name} gains haste",
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=selector,
                    modification=grant_ability("Haste"),
                ),
                game=game,
            )

    return effect


#: "Gain control of `<target>`. If that `<noun>`|it is an? `<subtype>`, attach
#: it to this creature." - Thieving Skydiver.
_GAIN_CONTROL_THEN_ATTACH_RE = re.compile(
    r"^(?P<steal>(?:you )?gain control of target [^.]+?\.)\s*"
    r"if (?:that (?:artifact|permanent|creature)|it) is an? (?P<subtype>[A-Z][a-z]+), "
    r"attach it to (?:this (?:creature|permanent)|[A-Z][^.,]*?)\.?$",
    re.IGNORECASE,
)


def parse_gain_control_then_attach_clause(effect_text: str) -> AbilityEffect | None:
    """`_GAIN_CONTROL_THEN_ATTACH_RE`'s shape, or `None`: the untimed steal
    (`control_change.parse_gain_control_untimed_clause`), then CR 701.3a's
    attach of each stolen target that has the named subtype onto the source
    - which `attach_permanent` refuses (CR 701.3b) when it could not equip
    it or the source has left."""
    match = _GAIN_CONTROL_THEN_ATTACH_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    from .control_change import parse_gain_control_untimed_clause

    steal = parse_gain_control_untimed_clause(match.group("steal"))
    if steal is None:
        return None
    subtype = match.group("subtype").capitalize()

    def effect(game: Game, ability: AbilityOnStack) -> None:
        targets = [
            target
            for target in game.resolve_card_targets(ability)
            if target.zone is Zone.BATTLEFIELD
        ]
        steal(game, ability)
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if ability.source_stamp is not None and source.zone_change_stamp != ability.source_stamp:
            return
        from .effects import attach_permanent

        for target in targets:
            if (
                isinstance(target, CardState)
                and subtype in game.characteristics_of(target).subtypes
            ):
                attach_permanent(game, target, source)

    return effect
