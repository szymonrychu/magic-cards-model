"""Attack requirements that name who must be attacked (CR 508.1d, CR 508.1b).

- "<group> attack <whom> each combat if able." (the group of CR 508.1d
  requirements, each creature of it obeyed only by attacking <whom>):
  <whom> is "enchanted creature's controller" (the permanent the source is
  attached to, CR 303.4) or "you" (the source's controller, CR 109.5).
- "Each opponent must attack you or a planeswalker you control with at least
  one creature each combat if able." - a requirement on the declaration as a
  whole: some creature has to attack the source's controller or one of their
  planeswalkers when one could.

Read off the computed board (CR 613.5) when asked (CR 611.3a).
"""

import re
from typing import TYPE_CHECKING

from ..models.card_state import CardState, TargetRef

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from ..models.game import Game

_FORCED_DEFENDER_RE = re.compile(
    r"^(?:all )?(?P<group>.+?) attack (?P<whom>enchanted creature's controller|you) "
    r"each combat if able\.?$",
    re.IGNORECASE,
)
_AT_LEAST_ONE_RE = re.compile(
    r"^each opponent must attack you or a planeswalker you control with at least one "
    r"creature each combat if able\.?$",
    re.IGNORECASE,
)


def _controller(game: "Game", state: CardState) -> str:
    return game.controller_of(state).username


def _required_player(game: "Game", source: CardState, whom: str) -> str | None:
    if whom.lower() == "you":
        return _controller(game, source)
    attached = source.attached_to
    if attached is None:
        return None
    creature = game.find_by_id(attached)
    return _controller(game, creature) if isinstance(creature, CardState) else None


def forced_defender_requirements(game: "Game", creature: CardState) -> list[str]:
    """The player each "<group> attack <whom> each combat if able" naming
    `creature` requires it to attack (one entry per requirement)."""
    from .group_attack_statics import _static_sentences, parse_group

    found: list[str] = []
    for source, sentence in _static_sentences(game):
        match = _FORCED_DEFENDER_RE.fullmatch(sentence)
        if match is None:
            continue
        group = parse_group(match["group"])
        if group is None or not group(game, creature, source):
            continue
        player = _required_player(game, source, match["whom"])
        if player is not None:
            found.append(player)
    return found


def _collective_sources(game: "Game"):
    from .group_attack_statics import _static_sentences

    for source, sentence in _static_sentences(game):
        if _AT_LEAST_ONE_RE.fullmatch(sentence):
            yield source


def _is_valid_defender(game: "Game", defender: TargetRef, controller: str) -> bool:
    from .combat import _is_planeswalker_controlled_by

    if defender.is_player:
        return defender.username == controller
    return _is_planeswalker_controlled_by(game, defender, controller)


def collective_requirement_violation(
    game: "Game", declared: "Mapping[UUID, TargetRef]"
) -> str | None:
    """Why `declared` (attacker id -> defender) disobeys an "at least one
    creature must attack you or your planeswalker" static though it could
    obey it (CR 508.1d), or None."""
    from .combat import attack_costs_against, attack_refusal, attackable_defenders

    if game.turn is None:
        return None
    active = game.turn.active_player
    for source in _collective_sources(game):
        controller = _controller(game, source)
        if controller == active:
            continue
        valid = [
            defender
            for defender in attackable_defenders(game, active)
            if _is_valid_defender(game, defender, controller)
            and not attack_costs_against(game, defender)
        ]
        if any(_is_valid_defender(game, defender, controller) for defender in declared.values()):
            continue
        for creature in game.permanents_controlled_by(active):
            if any(attack_refusal(game, creature, defender) is None for defender in valid):
                return (
                    f"{source.name} requires {active} to attack {controller} or a planeswalker "
                    f"{controller} controls with at least one creature, and {creature.name} "
                    "could, so a declaration without such an attack obeys fewer requirements "
                    "than it could (CR 508.1d)"
                )
    return None


def reads_defender_attack_requirement_line(text: str) -> bool:
    from .layers import layer_readable_sentences

    lowered = text.lower()
    if "each combat if able" not in lowered:
        return False
    sentences = [s.strip() for s in layer_readable_sentences(text, static_only=True)]
    from .group_attack_statics import parse_group

    def reads(sentence: str) -> bool:
        if _AT_LEAST_ONE_RE.fullmatch(sentence):
            return True
        match = _FORCED_DEFENDER_RE.fullmatch(sentence)
        return match is not None and parse_group(match["group"]) is not None

    return bool(sentences) and all(reads(sentence) for sentence in sentences)
