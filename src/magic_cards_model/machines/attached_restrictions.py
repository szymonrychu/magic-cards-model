"""Aura/Equipment attack-block restrictions read off the attachment
(CR 508.1c, 509.1b, 508.1d, 602.5).

"Enchanted creature can't attack or block, and its activated abilities can't
be activated." (Arrest, Pacifism-likes), "Enchanted permanent can't attack or
block, and its activated abilities can't be activated unless they're mana
abilities." (Faith's Fetters), "Enchanted creature can't attack." (Forced
Worship), "Enchanted creature can't block.", "Enchanted creature attacks each
combat if able." (Lust for War) and Dog Umbra's "As long as another player
controls enchanted creature, it can't attack or block."

The source is the Aura or Equipment on the battlefield; the subject is whatever
it is attached to (`attached_to`, CR 303.4), read off the computed board when
asked (CR 613.5, CR 611.3a).
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.card import Card
    from ..models.card_state import CardState
    from ..models.game import Game

_RESTRICTION_RE = re.compile(
    r"^(?P<cond>as long as another player controls enchanted creature, )?"
    r"(?P<subject>enchanted (?:creature|permanent|artifact|land)|equipped creature|it)"
    r"(?: is an? (?P<becomes>[a-z]+) and)?"
    r" can't (?P<what>attack or block|attack|block)"
    r"(?P<tail>.*?)\.?$",
    re.IGNORECASE,
)
_DEACTIVATE_TAIL_RE = re.compile(
    r"^,? and its activated abilities can't be activated(?P<mana> unless they're mana abilities)?$",
    re.IGNORECASE,
)
_PAY_TAIL_RE = re.compile(r"^ unless its controller pays (?P<cost>.+)$", re.IGNORECASE)
_REQUIREMENT_RE = re.compile(
    r"^(?:enchanted|equipped) creature attacks each combat if able\.?$", re.IGNORECASE
)


@dataclass(frozen=True)
class AttachedRestriction:
    """One parsed attachment sentence."""

    sentence: str
    attack: bool = False
    block: bool = False
    deactivate: bool = False
    mana_exempt: bool = False
    #: "unless its controller pays <cost>" - the cost text, enforced by
    #: `attack_block_costs`.
    pay: str | None = None
    #: Dog Umbra: only while another player controls the enchanted creature.
    needs_other_controller: bool = False
    requirement: bool = False


def parse_attached(sentence: str) -> AttachedRestriction | None:
    """Read one sentence into an `AttachedRestriction`, or None."""
    text = sentence.strip()
    if _REQUIREMENT_RE.fullmatch(text):
        return AttachedRestriction(sentence=text, requirement=True)
    match = _RESTRICTION_RE.fullmatch(text)
    if match is None:
        return None
    tail = match["tail"]
    what = match["what"].lower()
    base = AttachedRestriction(
        sentence=text,
        attack="attack" in what,
        block="block" in what,
        needs_other_controller=match["cond"] is not None,
    )
    if not tail.strip():
        return base
    deactivate = _DEACTIVATE_TAIL_RE.fullmatch(tail.strip())
    if deactivate is not None:
        return AttachedRestriction(
            **{**base.__dict__, "deactivate": True, "mana_exempt": deactivate["mana"] is not None}
        )
    pay = _PAY_TAIL_RE.fullmatch(tail)
    if pay is not None:
        return AttachedRestriction(**{**base.__dict__, "pay": pay["cost"]})
    return None


def _attached_restrictions(game: "Game", subject: "CardState"):
    """(source, restriction) for every attachment on `subject` whose static
    lines state one."""
    from .layers import layer_readable_sentences

    board = game.computed_board()
    for source in game.battlefield:
        if source.attached_to != subject.id:
            continue
        for ability in board.of(source).abilities:
            lowered = ability.lower()
            if "enchanted " not in lowered and "equipped " not in lowered:
                continue
            if "can't" not in lowered and "attacks each combat" not in lowered:
                continue
            for sentence in layer_readable_sentences(ability, static_only=True):
                restriction = parse_attached(sentence)
                if restriction is None:
                    continue
                if restriction.needs_other_controller and (
                    game.controller_of(source).username == game.controller_of(subject).username
                ):
                    continue
                yield source, restriction


def _refusal(game: "Game", creature: "CardState", action: str) -> str | None:
    rule = "CR 508.1c" if action == "attack" else "CR 509.1b"
    for source, restriction in _attached_restrictions(game, creature):
        if restriction.pay is None and getattr(restriction, action):
            return (
                f'{creature.name} can\'t {action}: {source.name} says "{restriction.sentence}" '
                f"({rule})"
            )
    return None


def attached_attack_refusal(game: "Game", creature: "CardState") -> str | None:
    return _refusal(game, creature, "attack")


def attached_block_refusal(game: "Game", blocker: "CardState") -> str | None:
    return _refusal(game, blocker, "block")


def attached_attack_requirements(game: "Game", creature: "CardState") -> list[bool]:
    """One entry per "enchanted creature attacks each combat if able" on it
    (CR 508.1d); False: any attack obeys it."""
    return [
        False
        for _source, restriction in _attached_restrictions(game, creature)
        if restriction.requirement
    ]


def attached_activation_prohibition(game: "Game", obj: "CardState", *, is_mana: bool) -> str | None:
    """Why an attachment's "its activated abilities can't be activated" stops
    activating an ability of `obj`, or None (CR 602.5)."""
    for source, restriction in _attached_restrictions(game, obj):
        if restriction.deactivate and not (restriction.mana_exempt and is_mana):
            return (
                f"{obj.name}'s activated abilities can't be activated: {source.name} says "
                f'"{restriction.sentence}" (CR 602.5)'
            )
    return None


def reads_attached_restriction_line(printing: "Card", text: str, *, card_name: str) -> bool:
    """Whether every sentence of this static line is an attachment restriction
    `parse_attached` reads (the cost form is `attack_block_costs`'s)."""
    from .layers import layer_readable_sentences

    lowered = text.lower()
    if "enchanted " not in lowered and "equipped " not in lowered and "it can't" not in lowered:
        return False
    sentences = [s.strip() for s in layer_readable_sentences(text, static_only=True)]
    return bool(sentences) and all(
        (found := parse_attached(sentence)) is not None and found.pay is None
        for sentence in sentences
    )
