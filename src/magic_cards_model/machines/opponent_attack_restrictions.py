"""Opponent attack rows: a conditional all-attack requirement, a this-turn
"can't attack you" bar, and a cast ban on whoever attacked you this turn.

- **"If a creature an opponent controls attacks, all creatures that opponent
  controls attack if able."** (War's Toll) - CR 508.1d's requirement that
  "a creature attacks if some condition is met": once the declaration holds
  any attacker of that opponent, every other creature they control that could
  attack must (`all_attack_requirement_violation`, asked by
  `combat.unobeyed_attack_requirement`). Declaring no attackers obeys it.
- **"they can't attack you or planeswalkers you control this turn"**
  (Sandswirl Wanderglyph's cast trigger) - a resolving restriction on the
  rules of the game (CR 611.2c: it is not a characteristic change, so it binds
  creatures that arrive later too), kept as a turn fact for the restricted
  player (`record_cant_attack`) and read by `cant_attack_refusal` (CR 508.1c).
- **"Each opponent who attacked you or a planeswalker you control this turn
  can't cast spells."** (Sandswirl Wanderglyph) - a static CR 601.3
  prohibition, read live (CR 611.3a) off the attack history `note_attacked`
  records as attackers are declared (CR 508.1).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ..models.card_state import CardState

if TYPE_CHECKING:
    from ..models.game import Game

_ALL_ATTACK_RE = re.compile(
    r"^if a creature (?P<who>an opponent|a player) controls attacks, all creatures that "
    r"(?:opponent|player) controls attack if able\.?$",
    re.IGNORECASE,
)
_ATTACKED_CANT_CAST_RE = re.compile(
    r"^each opponent who attacked you(?: or a planeswalker you control)? this turn "
    r"can'?t cast spells\.?$",
    re.IGNORECASE,
)
#: Turn-fact keys (`Game.turn_facts`): `<prefix>|<protected player>|<source>`.
_CANT_ATTACK_FACT = "cant_attack_you"
_ATTACKED_FACT = "attacked_player_or_planeswalker_of"


def _norm(text: str) -> str:
    return " ".join(text.split())


def reads_opponent_attack_restriction_line(text: str) -> bool:
    """Whether `text` is a static line this module enforces."""
    line = _norm(text)
    return _ALL_ATTACK_RE.fullmatch(line) is not None or (
        _ATTACKED_CANT_CAST_RE.fullmatch(line) is not None
    )


def _static_lines(game: Game, pattern: re.Pattern[str]) -> list[tuple[CardState, re.Match[str]]]:
    from .triggers.collect import _computed_ability_lines

    found = []
    for permanent in game.battlefield:
        for line in _computed_ability_lines(game, permanent):
            match = pattern.fullmatch(_norm(line))
            if match is not None:
                found.append((permanent, match))
    return found


def all_attack_requirement_violation(game: Game, declared: Mapping[UUID, Any]) -> str | None:
    """Why `declared` (attacker id -> defender) leaves home a creature an
    all-attack requirement says must attack though it could (CR 508.1d), or
    None. Only a creature that can legally attack some defender without a cost
    is held to it (CR 508.1d's restrictions and unpaid-cost clauses)."""
    from .combat import attack_costs_against, attack_refusal, attackable_defenders

    if game.turn is None or not declared:
        return None
    active = game.turn.active_player
    for source, match in _static_lines(game, _ALL_ATTACK_RE):
        controller = game.controller_of(source).username
        if match.group("who").lower() == "an opponent" and controller == active:
            continue
        board = game.computed_board()
        for creature in game.permanents_controlled_by(active):
            if creature.id in declared or not board.of(creature).is_creature:
                continue
            if any(
                attack_refusal(game, creature, defender) is None
                and not attack_costs_against(game, defender)
                for defender in attackable_defenders(game, active)
            ):
                return (
                    f"{source.name} requires every creature {active} controls to attack if "
                    f"able once one does, and {creature.name} can attack (CR 508.1d)"
                )
    return None


def record_cant_attack(game: Game, restricted: str, protected: str, source_name: str) -> None:
    """`restricted` can't attack `protected` or planeswalkers `protected`
    controls for the rest of this turn."""
    game.record_turn_fact(f"{_CANT_ATTACK_FACT}|{protected}|{source_name}", restricted)


def _defender_player(game: Game, defender: Any) -> str | None:
    """The player attacked, or the controller of the planeswalker attacked;
    None for a battle (CR 310: not "you or a planeswalker you control")."""
    if defender is None:
        return None
    if getattr(defender, "is_player", False):
        return defender.username
    card_id = getattr(defender, "card_id", None)
    found = game.find_by_id(card_id) if card_id is not None else None
    if not isinstance(found, CardState):
        return None
    from ..models.card import Type

    if Type.PLANESWALKER not in game.characteristics_of(found).types:
        return None
    return game.controller_of(found).username


def cant_attack_refusal(game: Game, creature: CardState, defender: Any) -> str | None:
    """Why `creature` can't attack `defender` under a recorded this-turn bar
    (CR 508.1c), or None."""
    protected = _defender_player(game, defender)
    if protected is None:
        return None
    attacker = game.controller_of(creature).username
    prefix = f"{_CANT_ATTACK_FACT}|{protected}|"
    for fact, players in game.turn_facts.items():
        if fact.startswith(prefix) and attacker in players:
            source = fact[len(prefix) :]
            return (
                f"{source} says {attacker} can't attack {protected} or planeswalkers "
                f"{protected} controls this turn (CR 508.1c)"
            )
    return None


def note_attacked(game: Game, attacker: str, defender: Any) -> None:
    """Record that `attacker` attacked the defender's player (the player, or
    the planeswalker's controller) this turn (CR 508.1)."""
    protected = _defender_player(game, defender)
    if protected is not None:
        game.record_turn_fact(f"{_ATTACKED_FACT}|{protected}", attacker)


def attacked_cant_cast_source(game: Game, caster: str) -> tuple[str, str] | None:
    """`(source name, its controller)` of a static that bars `caster` from
    casting because they attacked its controller (or a planeswalker that
    player controls) this turn (CR 601.3), or None."""
    for source, _match in _static_lines(game, _ATTACKED_CANT_CAST_RE):
        controller = game.controller_of(source).username
        if controller == caster:
            continue
        if game.turn_fact_holds(f"{_ATTACKED_FACT}|{controller}", caster):
            return source.name, controller
    return None
