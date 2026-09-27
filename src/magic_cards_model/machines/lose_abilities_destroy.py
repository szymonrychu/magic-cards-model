"""A group that loses all abilities and is then destroyed, as one instruction.

Day of Black Sun: "Each creature with mana value X or less loses all abilities
until end of turn. Destroy those creatures." (X already written in by the
caller's `substitute_x`, CR 107.3a).

- **CR 611.2c** - the first sentence's continuous effect fixes its set of
  objects as it begins; nothing entering later joins it.
- **CR 613.1f** - "loses all abilities" is a layer 6 effect, until the cleanup
  step (CR 514.2).
- **CR 608.2c** - the instructions are followed in order, and "those
  creatures" in the second sentence are exactly the objects the first one
  affected - not a fresh look at the board.
- **CR 701.8a / 702.12b** - each is destroyed; indestructible, already
  removed by the first sentence, no longer saves it.

The group is read with the same qualifier grammar "Destroy each ..." uses
(`machines/effects._parse_mass_destroy_predicate`: card type, "with mana
value N or less/greater", "with power/toughness N or less/greater"), so any
group that sweeper reads reads here too.

`machines/effects.py` imports this module lazily from its spell and ability
dispatchers, and this module imports its helpers from there the same lazy
way, so neither import runs at the other's module load.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.zone import Zone
from .layers import ContinuousEffect, Duration, Layer, lose_all_abilities, only_this_incarnation

if TYPE_CHECKING:
    from ..models.game import Game
    from .effects import AbilityEffect, AbilityOnStack, Effect

_EACH_LOSES_ALL_ABILITIES_THEN_DESTROY_RE = re.compile(
    r"^each (?P<group>.+?) loses all abilities until end of turn\.\s+"
    r"destroy those (?P<noun>[a-z]+)\.?$",
    re.IGNORECASE,
)

Predicate = Callable[["Game", CardState, CardState | None], bool]


def _parse(text: str) -> Predicate | None:
    match = _EACH_LOSES_ALL_ABILITIES_THEN_DESTROY_RE.fullmatch(text.strip())
    if match is None:
        return None
    from .effects import _parse_mass_destroy_predicate

    return _parse_mass_destroy_predicate(match.group("group"))


def _resolve(game: "Game", predicate: Predicate, source: CardState | None) -> None:
    """Fix the group once (CR 611.2c), take its abilities (CR 613.1f), then
    destroy exactly that group (CR 608.2c, CR 701.8a)."""
    group = [
        permanent for permanent in list(game.battlefield) if predicate(game, permanent, source)
    ]
    if not group:
        return
    store = game.continuous_effects
    timestamp = store.tick()
    name = source.name if source is not None else "effect"
    for permanent in group:
        store.add(
            ContinuousEffect(
                description=f"{name}: {permanent.name} loses all abilities",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                source_id=source.id if source is not None else None,
                selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                modification=lose_all_abilities,
            )
        )
    for permanent in group:
        if permanent.zone is Zone.BATTLEFIELD:
            game.destroy(permanent)


def lose_abilities_then_destroy_spell_effect(text: str) -> "Effect | None":
    """The spell's effect for the whole resolution text, or `None`."""
    predicate = _parse(text)
    if predicate is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        _resolve(game, predicate, spell)

    return effect


def lose_abilities_then_destroy_ability_effect(text: str) -> "AbilityEffect | None":
    """The same instruction as an ability's effect, its source the ability's own
    source (CR 113.7a, found by id wherever it is now)."""
    predicate = _parse(text)
    if predicate is None:
        return None

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        _resolve(game, predicate, ability.source(game))

    return effect
