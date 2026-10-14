"""EP-02 R3 T8 part: a graveyard instant or sorcery gains flashback (CR 702.34a, 601.3).

Widens the established grant (`effects.continuous._parse_grant_flashback_clause`, which reads
"... gains flashback until end of turn. The flashback cost is equal to its mana cost.")
additively:

- "... equal to that card's mana cost" (Sphinx of Forgotten Lore) is the same cost phrased
  with the card named instead of "its";
- "That card gains flashback {0} until end of turn instead if this creature is saddled."
  (Archmage's Newt, CR 702.171b) replaces the cost with {0} while the source is saddled, a
  fact checked as the ability resolves (CR 608.2c: the later text modifies the earlier).
"""

import functools
import re
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.zone import Zone
from .effects._chains import ABILITY_TEXT

if TYPE_CHECKING:
    from ..models.game import Game

_THAT_CARDS_RE = re.compile(r"\bthe flashback cost is equal to that card's mana cost", re.IGNORECASE)
_SADDLED_RE = re.compile(
    r"\s*that card gains flashback \{0\} until end of turn instead if this creature is saddled\.?$",
    re.IGNORECASE,
)


@functools.cache
def _grant_flashback(text: str) -> Any:
    lowered = text.lower()
    if "gains flashback" not in lowered:
        return None
    flat = " ".join(text.split())
    free_when_saddled = _SADDLED_RE.search(flat) is not None
    base = _SADDLED_RE.sub("", flat).strip()
    base = _THAT_CARDS_RE.sub("the flashback cost is equal to its mana cost", base)
    if not (free_when_saddled or base != flat):
        return None  # the established reader's text as printed
    from .effects.continuous import _parse_grant_flashback_clause

    inner = _parse_grant_flashback_clause(base)
    if inner is None:
        return None
    if not free_when_saddled:
        return inner

    from ..machines.casting import PlayAction

    def effect(game: "Game", ability: Any) -> None:
        source = ability.source_or_last_known(game)
        if source is None or not source.saddled:
            inner(game, ability)
            return
        controller = game.controller_of(ability)
        for target in game.resolve_targets(ability):
            if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD:
                game.grant_play_permission(
                    target,
                    controller.username,
                    action=PlayAction.CAST,
                    pays_mana_cost=False,  # flashback {0}
                    flashback=True,
                    source_name=ability.source_name,
                    zone=Zone.GRAVEYARD,
                    rule="CR 601.3",
                )

    return effect


@ABILITY_TEXT.rung("s13")
def grant_flashback_variants(effect_text: str) -> Any:
    """`_grant_flashback` as an ability's whole text."""
    return _grant_flashback(effect_text.strip())
