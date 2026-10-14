"""Connive, the keyword action (CR 701.50), and the one replacement effect
printed against it.

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this module:

- **CR 701.50a** - "Certain spells and abilities instruct a permanent to
  connive. To do so, that permanent's controller draws a card, then discards
  a card. If a nonland card is discarded this way, that player puts a +1/+1
  counter on the conniving permanent."
- **CR 701.50b** - "If a permanent is no longer on the battlefield as an effect
  instructs it to connive, its last known information is used to determine
  which object connived and who controlled it."
- **CR 701.50f** - a permanent "connives" after the process "is complete,
  even if some or all of those actions were impossible".
- **CR 614.1a** - an "instead" is a replacement effect; **CR 614.5** - "A
  replacement effect doesn't invoke itself repeatedly; it gets only one
  opportunity to affect an event or any modified events that may replace
  that event", which is what makes two copies of the same replacement each
  add their own draw exactly once.
- **CR 603.2h** - "Do this only once each turn": the ability "triggers only if
  its source's controller has not yet taken the indicated action that turn".

The clause template is one sentence shape with a variable subject - the
source ("it", "he", "she", "this creature", its own name), the object the
trigger's event named ("another Villain you control enters, you may have it
connive"; "an equipped creature you control attacks, it connives"), or a
target ("target creature you control", "target Villain you control", "up to
one target creature you control"). Nothing here is keyed on a card name.

Connive N (CR 701.50d) is not read: no printing legal in a target format
prints a count this engine can evaluate (Raffine, Scheming Seer's "the number
of attacking creatures" and Spymaster's Vault's "the number of creatures that
died this turn" are both outside `effects.amount_expression`), so such a
clause stays unparsed rather than half-read.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from magic_cards_model.text_norm import collapsed

from ..models.card import Type
from ..models.card_state import CardState, Counter
from ..models.zone import Zone
from ..numbers import parse_count
from .abilities import AbilityKind, parse_abilities
from .decisions import Decision, DecisionKind, source_id_of
from .triggers import AbilityOnStack

if TYPE_CHECKING:
    from ..models.game import Game, StackObject


#: "If a creature you control would connive, instead you draw a card, then
#: that creature connives." - the one replacement effect printed against the
#: connive event (Leader, Super-Genius). The quality ("a creature"/"a
#: permanent") and the draw count are read, not fixed.
_CONNIVE_REPLACEMENT_RE = re.compile(
    r"^if (?:a|an) (?P<quality>creature|permanent) you control would connive, "
    r"instead you draw (?P<count>a card|\w+ cards), then that (?:creature|permanent) "
    r"connives\.?$",
    re.IGNORECASE,
)


def is_connive_replacement_line(text: str) -> bool:
    """Whether a static line is `_CONNIVE_REPLACEMENT_RE`'s replacement."""
    return _CONNIVE_REPLACEMENT_RE.fullmatch((text or "").strip()) is not None


def _replacement_draws(game: Game, conniver: CardState, controller: str) -> list[int]:
    """How many cards each applicable connive replacement adds, one entry per
    replacement (CR 614.5: each gets one opportunity at the event).

    Read fresh off the battlefield on every connive (CR 611.3a), only from a
    permanent still showing the printed line on the computed board (CR
    613.1f: a replacement a layer-6 effect removed is gone). "A creature you
    control" is judged on the conniving object as it last existed (CR
    701.50b) - the computed board while it is on the battlefield, its own card
    otherwise - and "you" is the replacement's controller, who draws.
    """
    if conniver.zone is Zone.BATTLEFIELD:
        is_creature = game.characteristics_of(conniver).is_creature
    else:
        is_creature = Type.CREATURE in conniver.card.types
    draws: list[int] = []
    for permanent in list(game.battlefield):
        if game.controller_of(permanent).username != controller:
            continue
        shown = game.characteristics_of(permanent).abilities
        for line in parse_abilities(permanent.card):
            if line.kind is not AbilityKind.STATIC:
                continue
            match = _CONNIVE_REPLACEMENT_RE.fullmatch((line.text or "").strip())
            if match is None or line.raw not in shown:
                continue
            if match.group("quality").lower() == "creature" and not is_creature:
                continue
            count = parse_count(match.group("count").split()[0])
            draws.append(1 if count is None else count)
    return draws


def connive(
    game: Game,
    conniver: CardState | None,
    *,
    controller: str,
    source_name: str,
    source_id: str | None,
) -> None:
    """`conniver` connives (CR 701.50a).

    `conniver` may be a live permanent, a card that has already left the
    battlefield, or `None` for one that no longer exists at all (a token);
    `controller` is who controlled it as it last existed (CR 701.50b). Only a
    conniver still on the battlefield takes the counter.
    """
    from .effects import _discard_cards  # the shared CR 701.9 discard question

    player = game.player(controller)
    if conniver is not None:
        # CR 614.1a/614.5: "instead you draw a card, then that creature
        # connives" - each applicable replacement adds its own draw first.
        for extra in _replacement_draws(game, conniver, controller):
            game.draw_cards(player, extra)
    game.draw_cards(player, 1)
    discarded = _discard_cards(game, player, 1, source_name, source_id=source_id)
    nonland = any(Type.LAND not in card.card.types for card in discarded)
    if nonland and conniver is not None and conniver.zone is Zone.BATTLEFIELD:
        game.add_counters(conniver, Counter.PLUS_ONE, 1)


#: "<subject> connive(s)." - optionally
#: behind "then" (a spell's second sentence) or "you may have" (Baron Strucker's
#: optional trigger, where the verb is the bare infinitive "connive").
_CONNIVE_CLAUSE_RE = re.compile(
    r"^(?:then,?\s+)?(?P<may>you may have\s+)?"
    r"(?P<subject>it|he|she|this creature|this permanent|"
    r"(?:up to one )?target [^.]+?)\s+"
    r"connives?\.?$",
    re.IGNORECASE,
)


def _event_subject(game: Game, ability: AbilityOnStack) -> CardState | None | bool:
    """The object the trigger's event named, when it is a permanent (or the
    card a permanent became), or `False` when the event names no such object.

    `None` is "it existed and no longer exists at all" - a token (CR 704.5d).
    """
    event = ability.event
    if event is None or event.subject_id is None:
        return False
    if event.subject_id == ability.source_id:
        return False  # the source itself: read as the source, with its LKI
    found = game.find_by_id(event.subject_id)
    if found is None:
        return None if event.subject_controller else False
    if found.zone is Zone.STACK:
        return False  # a spell, not a permanent: "it" is the source
    return found


def parse_connive_clause(clause: str, *, for_spell: bool):  # noqa: ANN201 - TargetedClause
    """One connive instruction; see the module docstring for its shapes.

    Self-subjects on a spell are refused: CR 701.50a instructs "a permanent"
    to connive, and a resolving spell is not a permanent. A target phrase is
    trusted only when `machines/effects._targets_understood` reads it.
    """
    match = _CONNIVE_CLAUSE_RE.fullmatch(collapsed(clause))
    if match is None:
        return None
    subject = match.group("subject").lower()
    is_target = "target" in subject
    optional = match.group("may") is not None
    if match.group("may") and match.group("subject").lower() != "it" and not is_target:
        return None
    if not is_target and for_spell:
        return None
    requirement = None
    if is_target:
        from .effects import _targets_understood
        from .targeting import profile_for_text

        if not _targets_understood(match.group("subject"), count_agnostic=True):
            return None
        # The clause's own requirement picks its target out of a spell's
        # whole target list (Trickster's Stratagem names "target creature an
        # opponent controls" first) - CR 601.2c/603.3d announced each
        # "target" word's object separately.
        requirement = profile_for_text(match.group("subject")).requirements[0]

    def effect(game: Game, stack_object: StackObject) -> None:
        source_name = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        source_id = source_id_of(stack_object)
        controller = game.controller_of(stack_object)
        conniver: CardState | None
        if is_target:
            assert requirement is not None
            targets = [
                target
                for target in game.resolve_targets(stack_object)
                if isinstance(target, CardState)
                and target.zone is Zone.BATTLEFIELD
                and requirement.rejects(target, controller.username, game) is None
            ]
            if not targets:
                return
            conniver = targets[-1]
            conniver_controller = game.controller_of(conniver).username
        else:
            assert isinstance(stack_object, AbilityOnStack)
            subject_state = _event_subject(game, stack_object) if subject == "it" else False
            if subject_state is False:
                conniver = stack_object.source_or_last_known(game)
                if conniver is None:
                    return
                conniver_controller = (
                    game.controller_of(conniver).username
                    if conniver.zone is Zone.BATTLEFIELD
                    else stack_object.controller
                )
            else:
                conniver = subject_state  # type: ignore[assignment]
                if conniver is not None and conniver.zone is Zone.BATTLEFIELD:
                    conniver_controller = game.controller_of(conniver).username
                else:
                    event = stack_object.event
                    assert event is not None
                    conniver_controller = event.subject_controller or stack_object.controller
        if optional:
            asked = game.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=controller.username,
                    prompt=f"have {conniver.name if conniver else 'it'} connive",
                    source=source_name,
                    source_id=source_id,
                )
            )
            if not asked:
                _release_once_per_turn(game, stack_object)
                return
        connive(
            game,
            conniver,
            controller=conniver_controller,
            source_name=source_name,
            source_id=source_id,
        )

    return effect


def _release_once_per_turn(game: Game, stack_object: StackObject) -> None:
    """CR 603.2h: "Do this only once each turn" is spent by the action, not by
    the trigger - declining the "you may" leaves it untaken, so the next event
    this turn triggers the ability again. `machines/triggers.triggers_for`
    books the budget as the ability triggers (keyed `"<source id>:<text>"`);
    this hands it back."""
    if not isinstance(stack_object, AbilityOnStack):
        return
    ability = stack_object.ability
    if not getattr(ability, "once_per_turn", False):
        return
    key = f"{stack_object.source_id}:{ability.text}"
    fired = game.once_per_turn_triggers.get(key, 0)
    if fired > 1:
        game.once_per_turn_triggers[key] = fired - 1
    else:
        game.once_per_turn_triggers.pop(key, None)


#: Where one printed connive clause can start inside an effect text: a new
#: sentence, a quoted ability another effect grants (CR 113.10's "has"), or a
#: ", then" chaining it after another instruction (Unstable Experiment).
_CLAUSE_BREAK_RE = re.compile(r'(?<=\.)\s+|"|,\s+(?=then\b)')


def mentions_connive(texts: list[str]) -> bool:
    """Whether any of these effect texts carries a connive clause this module
    reads - `support.executed_keywords`' question, not the dispatcher's."""
    for text in texts:
        for piece in _CLAUSE_BREAK_RE.split(text.strip()):
            piece = piece.strip().rstrip('"').strip()
            if not piece:
                continue
            if any(parse_connive_clause(piece, for_spell=s) is not None for s in (False, True)):
                return True
    return False


__all__ = [
    "connive",
    "is_connive_replacement_line",
    "mentions_connive",
    "parse_connive_clause",
]
