"""Death triggers that return a double-faced card transformed - and, when its
back face is an Aura, attached to the ability's target - plus the "enchanted
permanent's controller" player referent its back faces print.

Shapes (registered into the ability ladder by `machines/effects/returns.py`
and `machines/effects/text.py`):

- "return `<it|this card>` to the battlefield[ tapped][ and][ transformed]
  under `<your|its owner's>` control attached to `<target>`." - Accursed
  Witch ("When this creature dies, return it ... attached to target
  opponent."), Radiant Grace ("When enchanted creature dies, return this card
  ... attached to target opponent."), Vengeful Strangler ("... attached to
  target creature or planeswalker an opponent controls.").
- "return this card to the battlefield[ tapped][ and][ transformed] under
  `<your|its owner's>` control." - Skin Invasion. "This card" is the
  ability's own source, now in a graveyard (CR 400.7); "it" in the attached
  form above is the dying creature itself, the source again.
- "return it to the battlefield under `<your|its owner's>` control, then
  return this card to the battlefield transformed under your control." -
  Journey to Eternity: "it" is the creature the trigger event named (the
  enchanted creature that died), "this card" the Aura itself.
- "`<enchanted|equipped> <noun>`'s controller `<instruction>`[, then that
  player `<instruction>`]." - Strangling Grasp's "At the beginning of your
  upkeep, enchanted permanent's controller sacrifices a nonland permanent of
  their choice, then that player loses 1 life.": each instruction is the
  ordinary player clause, performed by the attached permanent's controller.

CR 712.14a: a card put onto the battlefield "transformed" enters with its
back face up. CR 303.4i: an Aura put onto the battlefield attached to an
object or player it can't legally enchant stays in its current zone; CR
303.4h: a permanent that isn't an Aura enters unattached. CR 110.2a: "under
your control" is the resolving ability's controller.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from magic_cards_model.text_norm import collapsed

from ..models.card_state import CardState
from ..models.zone import Zone

if TYPE_CHECKING:
    from ..models.game import Game
    from .effects import AbilityEffect
    from .triggers import AbilityOnStack

_RETURN_SELF_RE = re.compile(
    r"^return (?P<what>it|this card) to the battlefield"
    r"(?P<tapped> tapped)?(?: and)?(?P<transformed> transformed)?"
    r" under (?P<control>its owner'?s|your) control"
    r"(?: attached to (?P<target>target [^.]+?))?\.?$",
    re.IGNORECASE,
)

_RETURN_SUBJECT_THEN_SELF_RE = re.compile(
    r"^return it to the battlefield(?P<subject_tapped> tapped)?"
    r" under (?P<subject_control>its owner'?s|your) control, then "
    r"return this card to the battlefield(?P<tapped> tapped)?(?: and)?"
    r"(?P<transformed> transformed)? under (?P<control>its owner'?s|your) control\.?$",
    re.IGNORECASE,
)

_ATTACHED_CONTROLLER_RE = re.compile(
    r"^(?:enchanted|equipped) (?:creature|permanent|artifact|land|planeswalker)'s controller "
    r"(?P<rest>.+?)\.?$",
    re.IGNORECASE,
)


def _back_face_enchant_refusal(
    game: Game, card: CardState, target: Any, controller: str, *, transformed: bool
) -> str | None:
    """Why `card`, entering with the face `transformed` names up, could not
    enchant `target` (CR 303.4i), or `None` - also `None` when that face is
    not an Aura at all (CR 303.4h: it then enters unattached)."""
    from .keywords import enchant_restrictions
    from .targeting import profile_for_text

    faces = getattr(card.card, "card_faces", None) or []
    face = faces[1] if transformed and len(faces) > 1 else (faces[0] if faces else card.card)
    if "Aura" not in (getattr(face, "type_line", "") or ""):
        return None
    for restriction in enchant_restrictions(card.card, getattr(face, "name", None)):
        profile = profile_for_text(f"target {restriction}")
        if not profile.understood or not profile.requirements:
            return f"'Enchant {restriction}' could not be read"
        refusal = profile.requirements[0].rejects(target, controller, game)
        if refusal is not None:
            return refusal
    return None


def _controller(game: Game, ability: AbilityOnStack, card: CardState, under_owner: bool) -> str:
    if under_owner and card.owner is not None:
        return card.owner
    return game.controller_of(ability).username


def parse_return_self_transformed_clause(effect_text: str) -> AbilityEffect | None:
    """`_RETURN_SELF_RE`'s shape, or `None`.

    Claims only "this card", or an "attached to <target>" tail: a bare
    "return it to the battlefield ... under ... control" with neither is
    `machines/effects/returns._parse_return_self_to_battlefield_transformed_
    clause`'s (the Ojer cycle)."""
    match = _RETURN_SELF_RE.fullmatch(collapsed(effect_text))
    if match is None:
        return None
    attached = match.group("target") is not None
    if match.group("what").lower() == "it" and not attached:
        return None
    if attached:
        from .targeting import profile_for_text

        profile = profile_for_text(match.group("target"))
        if not profile.understood or len(profile.requirements) != 1:
            return None
    tapped = match.group("tapped") is not None
    transformed = match.group("transformed") is not None
    under_owner = match.group("control").lower().startswith("its")

    def effect(game: Game, ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.GRAVEYARD:
            return  # CR 400.7: it left the graveyard, a new object.
        controller = _controller(game, ability, source, under_owner)
        host = None
        if attached:
            host = next(iter(game.resolve_targets(ability)), None)
            if host is None:
                return
            if _back_face_enchant_refusal(game, source, host, controller, transformed=transformed):
                return  # CR 303.4i: it stays in the graveyard.
        returned = game.put_onto_battlefield(
            source, controller, tapped=tapped, transformed=transformed
        )
        if (
            host is not None
            and returned.zone is Zone.BATTLEFIELD
            and "Aura" in game.characteristics_of(returned).subtypes
        ):
            returned.attach_to(host)

    return effect


def parse_return_subject_then_self_transformed_clause(effect_text: str) -> AbilityEffect | None:
    """`_RETURN_SUBJECT_THEN_SELF_RE`'s shape, or `None`: the creature the
    trigger event named returns first (if it is still in a graveyard, CR
    400.7), then the source card itself."""
    match = _RETURN_SUBJECT_THEN_SELF_RE.fullmatch(collapsed(effect_text))
    if match is None:
        return None
    subject_tapped = match.group("subject_tapped") is not None
    subject_owner = match.group("subject_control").lower().startswith("its")
    tapped = match.group("tapped") is not None
    transformed = match.group("transformed") is not None
    under_owner = match.group("control").lower().startswith("its")

    def effect(game: Game, ability: AbilityOnStack) -> None:
        event = ability.event
        subject_id = event.subject_id if event is not None else None
        subject = game.find_by_id(subject_id) if subject_id is not None else None
        if isinstance(subject, CardState) and subject.zone is Zone.GRAVEYARD:
            game.put_onto_battlefield(
                subject,
                _controller(game, ability, subject, subject_owner),
                tapped=subject_tapped,
            )
        source = ability.source(game)
        if source is None or source.zone is not Zone.GRAVEYARD:
            return
        game.put_onto_battlefield(
            source,
            _controller(game, ability, source, under_owner),
            tapped=tapped,
            transformed=transformed,
        )

    return effect


def parse_attached_controller_clause(effect_text: str) -> AbilityEffect | None:
    """`_ATTACHED_CONTROLLER_RE`'s shape, or `None`.

    The subject is the controller of the permanent the source is attached to
    (CR 303.4m; its last known host once the source has gone, CR 608.2h).
    Read as "that player <instruction>" by the ordinary readers - every
    "that player sacrifices ... / loses N life / ..." shape already reads its
    player off the trigger event (CR 603.2) - with the event's player bound
    to that controller as the ability resolves."""
    match = _ATTACHED_CONTROLLER_RE.fullmatch(collapsed(effect_text))
    if match is None:
        return None
    from .effects import parse_mixed_effect

    inner = parse_mixed_effect(f"that player {match.group('rest')}.")
    if inner is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        from .unattach import attached_host

        host = attached_host(game, ability)
        if host is None or ability.event is None:
            return
        controller = game.controller_of(host).username
        bound = ability.model_copy(
            update={"event": ability.event.model_copy(update={"player": controller})}
        )
        inner(game, bound)

    return effect
