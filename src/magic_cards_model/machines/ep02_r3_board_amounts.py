"""EP-02 R3 T4: opponent-board amounts.

- "Destroy all creatures target opponent controls. `<source>` deals damage to
  that player equal to their total power." (CR 608.2c): the damage is the total
  power of the creatures as they last existed (CR 608.2h), indestructible
  survivors counting at their current power.
- "Each opponent returns a nonland permanent they control with the greatest mana
  value among permanents they control to its owner's hand, then discards a
  card." (CR 202.3, CR 101.4): each opponent in turn order picks among the
  nonland permanents tied for the greatest mana value among *all* their
  permanents (none when that greatest is a land's), the picks are returned
  together, then each discards a card of their own choice.
"""

import re
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.player import Player
from ..models.zone import Zone
from .decisions import Decision, DecisionKind, source_id_of
from .effects._chains import ABILITY_TEXT, SPELL_TEXT
from .effects._common import _players_in_apnap_order, _targets_understood

if TYPE_CHECKING:
    from ..models.game import Game

_DESTROY_ALL_THEN_POWER_RE = re.compile(
    r"^destroy all creatures target opponent controls\. [a-z ,'~-]+ deals damage to that player "
    r"equal to their total power\.?$",
    re.IGNORECASE,
)
_RETURN_GREATEST_THEN_DISCARD_RE = re.compile(
    r"^each opponent returns a nonland permanent they control with the greatest mana value among "
    r"permanents they control to its owner's hand, then discards a card\.?$",
    re.IGNORECASE,
)


def _destroy_all_then_power_damage(text: str, *, for_spell: bool) -> Any:
    if _DESTROY_ALL_THEN_POWER_RE.fullmatch(" ".join(text.strip().split())) is None:
        return None
    if not _targets_understood("target opponent", allow_player_targets=True):
        return None

    def effect(game: "Game", obj: Any) -> None:
        target = next((t for t in game.resolve_targets(obj) if isinstance(t, Player)), None)
        if target is None:
            return
        source = obj.name if for_spell else obj.source_name
        creatures = [
            permanent
            for permanent in game.permanents_controlled_by(target.username)
            if game.characteristics_of(permanent).is_creature
        ]
        # CR 608.2h: powers are fixed before anything is destroyed.
        total = sum(game.power_of(creature) or 0 for creature in creatures)
        for creature in creatures:
            if creature.zone is Zone.BATTLEFIELD:
                game.destroy(creature)
        if total > 0:
            dealer = obj.source(game) if hasattr(obj, "source") else None
            game.deal_damage(
                target, total, source=dealer if isinstance(dealer, CardState) else None
            )
        _ = source

    return effect


def _greatest_value_candidates(game: "Game", player: Player) -> list[CardState]:
    permanents = game.permanents_controlled_by(player.username)
    greatest = max((int(p.mana_value) for p in permanents), default=0)
    return [
        permanent
        for permanent in permanents
        if not game.characteristics_of(permanent).is_land and int(permanent.mana_value) == greatest
    ]


def _return_greatest_then_discard(text: str, *, for_spell: bool) -> Any:
    if _RETURN_GREATEST_THEN_DISCARD_RE.fullmatch(" ".join(text.strip().split())) is None:
        return None

    def effect(game: "Game", obj: Any) -> None:
        controller = game.controller_of(obj)
        source = obj.name if for_spell else obj.source_name
        source_id = source_id_of(obj)
        opponents = [
            player
            for player in _players_in_apnap_order(game)
            if player.username != controller.username
        ]
        chosen: list[CardState] = []
        for player in opponents:
            candidates = _greatest_value_candidates(game, player)
            if not candidates:
                continue
            picked = candidates[0]
            if len(candidates) > 1:
                answer = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=player.username,
                        prompt="choose a nonland permanent with the greatest mana value to return",
                        source=source,
                        source_id=source_id,
                        amount=1,
                        exact=True,
                        cards=tuple(state.id for state in candidates),
                    )
                )
                assert isinstance(answer, tuple)
                picked = next(state for state in candidates if state.id == answer[0])
            chosen.append(picked)
        for permanent in chosen:  # CR 608.2c: returned together, then the discards
            game.return_to_hand(permanent)
        for player in opponents:
            if not player.hand:
                continue
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt="choose a card to discard",
                    source=source,
                    source_id=source_id,
                    amount=1,
                    exact=True,
                    cards=tuple(state.id for state in player.hand),
                )
            )
            assert isinstance(answer, tuple)
            game.discard_cards(
                player.username, [state for state in player.hand if state.id in set(answer)], source
            )

    return effect


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def _parse_board_amount_spell(text: str) -> Any:
    """Spells reading an opponent's board: Dispersal's return-then-discard."""
    if "greatest mana value among permanents they control" not in text.lower():
        return None
    return _return_greatest_then_discard(text, for_spell=True)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_board_amount_ability(text: str) -> Any:
    """Abilities reading an opponent's board: Angrath's destroy-then-power."""
    lowered = text.lower()
    if "total power" in lowered and "destroy all creatures target opponent controls" in lowered:
        return _destroy_all_then_power_damage(text, for_spell=False)
    if "greatest mana value among permanents they control" in lowered:
        return _return_greatest_then_discard(text, for_spell=False)
    return None
