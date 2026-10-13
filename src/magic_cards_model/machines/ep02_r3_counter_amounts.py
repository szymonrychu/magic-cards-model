"""EP-02 R3 T2: counter amounts and the keywords that put counters on a creature.

Fabricate (CR 702.123a): "When this permanent enters, you may put N +1/+1
counters on it. If you don't, create N 1/1 colorless Servo artifact creature
tokens." Each instance triggers separately (CR 702.123b).
"""

import re
from typing import TYPE_CHECKING

from ..models.player import Player
from ..models.zone import Zone
from .abilities import KeywordAbility, TriggeredAbility, TriggerEvent, TriggerWord
from .decisions import Decision, DecisionKind, source_id_of
from .effects._chains import FORWARD, MIXED_CLAUSE
from .effects._common import TargetedClause, _targets_understood

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers import StackObject

_WORDS = {1: "a", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def fabricate_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.123a, written out as the triggered ability it stands for."""
    from .keywords import _expansion

    count = ability.count if ability.count is not None else 1
    quantity = _WORDS.get(count, str(count))
    counters = "counter" if count == 1 else "counters"
    servos = "Servo artifact creature token" if count == 1 else "Servo artifact creature tokens"
    return _expansion(
        ability,
        keyword="fabricate",
        word=TriggerWord.WHEN,
        condition="this permanent enters",
        effect=(
            f"you may put {quantity} +1/+1 {counters} on it. "
            f"If you don't, create {quantity} 1/1 colorless {servos}"
        ),
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
    )


# -- "Exile a creature with the greatest power among creatures target opponent controls."

_GROUP_EXTREMUM_REMOVAL_RE = re.compile(
    r"^(?P<verb>exile|destroy) an? creature with the (?P<dir>greatest|least) "
    r"(?P<stat>power|toughness) among creatures "
    r"(?P<who>target opponent|target player) controls\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_remove_extremum_creature_of_target_player(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Exile a creature with the greatest power among creatures target
    opponent controls." (Fall of the Impostor III): the player is the target
    (CR 115.1), the creature is not (CR 115.10a), so hexproof on it stops
    nothing. The extremum is taken as the effect resolves (CR 608.2h); a tie
    for it is the ability controller's choice, since "a creature" is theirs to
    pick (CR 608.2d)."""
    match = _GROUP_EXTREMUM_REMOVAL_RE.fullmatch(clause.strip())
    if match is None or not _targets_understood(f"{match.group('who')}", allow_player_targets=True):
        return None
    greatest = match.group("dir").lower() == "greatest"
    stat = match.group("stat").lower()
    exiling = match.group("verb").lower() == "exile"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        players = [t for t in game.resolve_targets(stack_object) if isinstance(t, Player)]
        pool = [
            permanent
            for player in players
            for permanent in game.permanents_controlled_by(player.username)
            if game.characteristics_of(permanent).is_creature
        ]
        if not pool:
            return

        def value(permanent) -> int:
            number = game.power_of(permanent) if stat == "power" else game.toughness_of(permanent)
            return number if number is not None else 0

        bound = (max if greatest else min)(value(permanent) for permanent in pool)
        tied = [permanent for permanent in pool if value(permanent) == bound]
        pick = tied[0]
        if len(tied) > 1:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller,
                    prompt=f"choose a creature with the {match.group('dir').lower()} {stat}",
                    source=getattr(stack_object, "source_name", None) or stack_object.name,
                    amount=1,
                    exact=True,
                    cards=tuple(permanent.id for permanent in tied),
                    source_id=source_id_of(stack_object),
                )
            )
            by_id = {permanent.id: permanent for permanent in tied}
            pick = by_id.get(chosen_ids[0]) if chosen_ids else tied[0]
        if pick.zone is Zone.BATTLEFIELD:
            if exiling:
                game.exile_permanent(pick)
            else:
                game.destroy(pick)

    return effect
