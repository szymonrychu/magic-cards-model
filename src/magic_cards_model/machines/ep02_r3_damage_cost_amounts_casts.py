"""EP-02 R3 T8 part: spells whose second sentence reads the hand of a creature's controller.

- `destroy_then_exile_hand_excess`: "Destroy target creature. If its controller has more than
  four cards in hand, they exile cards from their hand equal to the difference." (CR 701.8a
  destroy, CR 608.2c order, CR 608.2d the player chooses which cards, CR 400.7 the controller
  is the one the creature had when it was destroyed).
"""

import functools
import re
from typing import TYPE_CHECKING, Any

from ..numbers import parse_count
from .effects._chains import SPELL_TEXT

if TYPE_CHECKING:
    from ..models.game import Game

_DESTROY_THEN_EXILE_RE = re.compile(
    r"^(?P<destroy>destroy target creature)\. if its controller has more than "
    r"(?P<n>\w+) cards in hand, they exile cards from their hand equal to the difference\.?$",
    re.IGNORECASE,
)


@functools.cache
def _destroy_then_exile_hand_excess(text: str) -> Any:
    if "equal to the difference" not in text.lower():
        return None
    from .effects.text import _strip_non_effect_preamble

    match = _DESTROY_THEN_EXILE_RE.fullmatch(" ".join(_strip_non_effect_preamble(text).split()))
    limit = parse_count(match.group("n")) if match is not None else None
    if match is None or limit is None:
        return None
    from .effects.dispatch import parse_mixed_effect_for_spell

    destroy = parse_mixed_effect_for_spell(match.group("destroy") + ".")
    if destroy is None:
        return None

    def effect(game: "Game", spell: Any) -> None:
        from .decisions import Decision, DecisionKind, source_id_of

        targets = game.resolve_card_targets(spell)
        controllers = [game.controller_of(target) for target in targets]
        destroy(game, spell)
        for player in controllers[:1]:  # CR 608.2b: no legal target, nothing to read
            excess = len(player.hand) - limit
            if excess <= 0:
                continue
            ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"exile {excess} cards from your hand",
                    source=spell.name,
                    source_id=source_id_of(spell),
                    amount=excess,
                    exact=True,
                    cards=tuple(card.id for card in player.hand),
                )
            )
            chosen = [card for card in player.hand if card.id in set(ids)]
            game.exile_cards(chosen)

    return effect


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def destroy_then_exile_hand_excess(effect_text: str) -> Any:
    """`_destroy_then_exile_hand_excess` as a spell's whole text."""
    return _destroy_then_exile_hand_excess(effect_text.strip())
