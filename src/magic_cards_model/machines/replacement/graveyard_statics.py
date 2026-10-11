"""Replacement effects of cards that function in a graveyard (CR 113.6b).

Retriever Phoenix: "As long as this card is in your graveyard, if you would
learn, you may instead return this card to the battlefield." (CR 701.48a,
CR 614.1a). `Game`-side the effect is offered by
`model._graveyard_source_effects`, which only looks at the learner's own
graveyard; `learn` raises the `EventKind.LEARN` event and stops if it was
replaced.
"""

from typing import TYPE_CHECKING

from ...models.card_state import CardState
from ...models.zone import Zone
from .model import CardReplacement, EventKind, ReplaceableEvent, ReplacementEffect, ReplacementKind

if TYPE_CHECKING:
    from ...models.game import Game


def _compile_learn_return_from_graveyard(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD or not effect.optional:
        return None
    if (effect.event or "").strip() != "you would learn":
        return None
    if (effect.condition or "").strip() != "this card is in your graveyard":
        return None
    if (effect.replacement or "").strip().rstrip(
        "."
    ) != "you may return this card to the battlefield":
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return (
            event.kind is EventKind.LEARN
            and event.player is not None
            and source.zone is Zone.GRAVEYARD
            and any(state is source for state in event.player.graveyard)
        )

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        assert event.player is not None
        if not game.may(
            event.player,
            f"return {source.name} to the battlefield instead of learning",
            source=source.name,
            source_id=str(source.id),
        ):
            return
        event.replaced = True
        game.put_onto_battlefield(source, event.player.username)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


GRAVEYARD_COMPILERS = (_compile_learn_return_from_graveyard,)
