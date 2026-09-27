"""The monarch (CR 725): a designation at most one player holds, and the two
inherent triggered abilities CR 725.2 attaches to it.

Rules verified with `mise run rules:find` against the 2026-09-25 Comprehensive
Rules:

- **CR 725.1** - "The monarch is a designation a player can have. There is no
  monarch in a game until an effect instructs a player to become the
  monarch."
- **CR 725.2** - "There are two inherent triggered abilities associated with
  being the monarch. These triggered abilities have no source and are
  controlled by the player who was the monarch at the time the abilities
  triggered. This is an exception to rule 113.8. The full texts of these
  abilities are 'At the beginning of the monarch's end step, that player
  draws a card' and 'Whenever a creature deals combat damage to the monarch,
  its controller becomes the monarch.'"

`Game.become_monarch` (CR 725.1/725.3) and `Game._reassign_monarch_after_
departure` (CR 725.4) live on `Game` itself, next to the `monarch` field they
write. This module is only the two inherent abilities: they need a real
`AbilityOnStack` with no printed card behind them - CR 725.2's own "no source"
- so they cannot be found by `machines/effects.py`'s ordinary card-name
registries. `machines/delayed.py` already solved the identical problem for a
delayed trigger's own sourceless ability; this reuses that shape rather than
re-inventing it.
"""

from typing import TYPE_CHECKING, Literal

from .abilities import AbilityKind, TriggeredAbility, TriggerEvent, TriggerWord
from .triggers import AbilityOnStack, GameEvent
from .turn import Step

if TYPE_CHECKING:
    from ..models.game import Game

#: CR 725.2's own two ability texts, quoted whole. Neither is printed on any
#: card - the rule itself is the only place either sentence is written down -
#: so this is the closest thing either has to `Card.oracle_text`.
_END_STEP_DRAW_TEXT = "At the beginning of the monarch's end step, that player draws a card."
_COMBAT_DAMAGE_TEXT = (
    "Whenever a creature deals combat damage to the monarch, its controller becomes the monarch."
)


def _ability_on_stack(
    *,
    kind: Literal["end_step_draw", "combat_damage"],
    controller: str,
    text: str,
    word: TriggerWord,
    condition: str,
    effect: str,
    trigger_event: TriggerEvent,
    event: GameEvent,
) -> AbilityOnStack:
    ability = TriggeredAbility(
        raw=text,
        text=text,
        face="the monarch",
        word=word,
        condition=condition,
        effect=effect,
        event=trigger_event,
        monarch_inherent=kind,
    )
    return AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=ability,
        source_id=None,  # CR 725.2: "These triggered abilities have no source."
        source_name="the monarch",
        controller=controller,
        event=event,
    )


def inherent_triggers_for(game: "Game", event: GameEvent) -> list[AbilityOnStack]:
    """CR 725.2's own two abilities, triggered by `event`, or `[]`.

    Called from `Game.emit` in the same slot `Game.delayed_triggers.fire`
    already occupies - every event is offered to both, because neither is
    printed on any object `Game.emit`'s ordinary battlefield/graveyard/stack
    widening could ever ask. Unlike a delayed trigger these two are not
    *created* by any effect; they are simply live for as long as `game.
    monarch` names somebody, so there is no registry of pending watchers to
    consult - only the one live fact on `Game` itself.

    CR 725.2's own "controlled by the player who was the monarch at the time
    the abilities triggered" is `game.monarch` read *now*, as the event
    happens - exactly the moment CR 603.2 says a trigger condition is
    checked.
    """
    if game.monarch is None:
        return []
    triggered: list[AbilityOnStack] = []
    if (
        event.event is TriggerEvent.BEGINNING_OF_STEP
        and event.step is Step.END_STEP
        and event.player == game.monarch
    ):
        # CR 500.6's end step begins for the active player, and CR 725.2's
        # "the monarch's end step" is exactly that step when the active
        # player (`event.player`, per `Game`'s own `BEGINNING_OF_STEP` emit)
        # is the monarch - there is no separate "each end step" reading.
        triggered.append(
            _ability_on_stack(
                kind="end_step_draw",
                controller=game.monarch,
                text=_END_STEP_DRAW_TEXT,
                word=TriggerWord.AT,
                condition="the beginning of the monarch's end step",
                effect="that player draws a card",
                trigger_event=TriggerEvent.BEGINNING_OF_STEP,
                event=event,
            )
        )
    if (
        event.event is TriggerEvent.DEALS_DAMAGE
        and event.combat
        and event.player == game.monarch
        and event.subject_controller is not None
    ):
        # `event.player` is the damaged player (`Game.deal_damage`'s own
        # `damaged_player`), `event.combat` is CR 510's combat damage as
        # opposed to any other kind, and `event.subject_controller` is CR
        # 120.1's source's controller - the creature that dealt it, read at
        # trigger time and carried on `AbilityOnStack.event` for the
        # resolution effect below to read back (CR 113.7a: the ability
        # outlives whatever happens to that creature afterwards).
        triggered.append(
            _ability_on_stack(
                kind="combat_damage",
                controller=game.monarch,
                text=_COMBAT_DAMAGE_TEXT,
                word=TriggerWord.WHENEVER,
                condition="a creature deals combat damage to the monarch",
                effect="its controller becomes the monarch",
                trigger_event=TriggerEvent.DEALS_DAMAGE,
                event=event,
            )
        )
    return triggered


def monarch_effect_for(ability: AbilityOnStack) -> object | None:
    """The effect of one of CR 725.2's own abilities, or `None` when
    `ability` is not one of them.

    `Game._effect_of`'s first stop, ahead of the card-name registries -
    exactly where it already asks `machines/keywords.keyword_effect_for` for
    a CR 702 keyword's own unprinted ability, for the identical reason: this
    ability's effect has no card name to be keyed under.
    """
    printed = ability.ability
    if not isinstance(printed, TriggeredAbility) or printed.monarch_inherent is None:
        return None
    if printed.monarch_inherent == "end_step_draw":
        return _resolve_end_step_draw
    return _resolve_combat_damage_steal


def _resolve_end_step_draw(game: "Game", ability: AbilityOnStack) -> None:
    """ "At the beginning of the monarch's end step, that player draws a
    card" - "that player" is this ability's own controller (CR 725.2: the
    monarch as the ability triggered)."""
    game.draw_cards(ability.controller, 1)


def _resolve_combat_damage_steal(game: "Game", ability: AbilityOnStack) -> None:
    """ "Whenever a creature deals combat damage to the monarch, its
    controller becomes the monarch" - "its" is the damaging creature, read
    back off the trigger event this ability was raised from."""
    new_monarch = ability.event.subject_controller if ability.event is not None else None
    if new_monarch is not None:
        game.become_monarch(new_monarch)
