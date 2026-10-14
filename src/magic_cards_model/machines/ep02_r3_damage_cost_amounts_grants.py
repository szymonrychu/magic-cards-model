"""EP-02 R3 T8 part: a graveyard instant or sorcery gains flashback (CR 702.34a, 601.3).

Widens the established grant (`effects.continuous._parse_grant_flashback_clause`, which reads
"... gains flashback until end of turn. The flashback cost is equal to its mana cost.")
additively:

- "... equal to that card's mana cost" (Sphinx of Forgotten Lore) is the same cost phrased
  with the card named instead of "its";
- "That card gains flashback {0} until end of turn instead if this creature is saddled."
  (Archmage's Newt, CR 702.171b) replaces the cost with {0} while the source is saddled, a
  fact checked as the ability resolves (CR 608.2c: the later text modifies the earlier).
- "... gains harmonize until end of turn. Its harmonize cost is equal to its mana cost."
  (Songcrafter Mage, CR 702.180a) is the same grant as a `PlayPermission.harmonize`: the cast
  may tap a creature for its power in generic mana and exiles the card as it leaves the stack.
"""

import functools
import re
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.zone import Zone
from .effects._chains import ABILITY_TEXT

if TYPE_CHECKING:
    from ..models.game import Game

_THAT_CARDS_RE = re.compile(
    r"\bthe flashback cost is equal to that card's mana cost", re.IGNORECASE
)
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


_GRANT_HARMONIZE_RE = re.compile(
    r"^(?P<phrase>target instant or sorcery card in your graveyard) gains harmonize "
    r"until end of turn\.\s*its harmonize cost is equal to its mana cost\.?$",
    re.IGNORECASE,
)


@functools.cache
def _grant_harmonize(text: str) -> Any:
    if "gains harmonize" not in text.lower():
        return None
    match = _GRANT_HARMONIZE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    from .effects._common import _targets_understood

    if not _targets_understood(match.group("phrase"), battlefield_only=False):
        return None

    def effect(game: "Game", ability: Any) -> None:
        from .casting import PlayAction

        controller = game.controller_of(ability)
        for target in game.resolve_targets(ability):  # CR 608.2b: rechecked as it resolves
            if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD:
                game.grant_play_permission(
                    target,
                    controller.username,
                    action=PlayAction.CAST,
                    pays_mana_cost=True,  # the harmonize cost is its mana cost
                    harmonize=True,
                    source_name=ability.source_name,
                    zone=Zone.GRAVEYARD,
                    rule="CR 702.180a",
                )

    return effect


@ABILITY_TEXT.rung("s13")
def grant_harmonize(effect_text: str) -> Any:
    """`_grant_harmonize` as an ability's whole text."""
    return _grant_harmonize(effect_text.strip())
