"""Level up (CR 702.87) and the level symbols of a leveler card (CR 711).

CR 702.87a: "Level up is an activated ability. 'Level up [cost]' means
'[Cost]: Put a level counter on this permanent. Activate only as a
sorcery.'" The keyword line prints only the cost, so the ability it means is
written out here once - the same synthetic `KeywordActivation` shape outlast
and station use (`machines/keywords.py`).

CR 711.2: "A level symbol is a keyword ability that represents a static
ability." CR 711.2a: "'{LEVEL N1-N2} [Abilities] [P/T]' means 'As long as
this creature has at least N1 level counters on it, but no more than N2 level
counters on it, it has base power and toughness [P/T] and has
[abilities].'" CR 711.2b is the same for "{LEVEL N3+}" with "N3 or more".
The striations are read by `machines/abilities.level_striations` (which tags
each striated ability with its `level_band`), and the static abilities they
stand for are built by `level_symbol_effects` below, which
`machines/layers/registry.effects_for` adds to every leveler's static
effects: a layer 7b base power/toughness (CR 613.4b) and a layer 6 grant of
every ability printed in the striation (CR 613.1f). CR 711.4/711.5/711.6 -
the unstriated lines, the uppermost box below N1 and off the battlefield -
need nothing: they are what the printed card already says.
"""

from typing import Any, NamedTuple

from ..models.card import Card
from ..models.card_state import LEVEL_COUNTER, CardState
from ..models.zone import Zone
from .abilities import KeywordAbility, keyword_abilities, level_band_holds, level_striations
from .keywords import KEYWORD_EFFECTS, KeywordActivation, _keyword_cost, _synthetic_ability

__all__ = [
    "LEVEL_COUNTER",
    "LEVEL_UP_EFFECT",
    "LEVEL_UP_RULE",
    "LevelBand",
    "active_level_band",
    "has_level_up",
    "level_bands",
    "level_symbol_effects",
    "level_up_activation",
]

#: The rule level up is read from.
LEVEL_UP_RULE = "CR 702.87a"
#: The rule a level symbol is read from.
LEVEL_SYMBOL_RULE = "CR 711.2"

#: CR 702.87a's expansion of "Level up [cost]", after the colon.
LEVEL_UP_EFFECT = "Put a level counter on this permanent."


class LevelBand(NamedTuple):
    """One leveler striation (CR 711.2): its range of level counters, its
    power/toughness box and the abilities printed in it."""

    low: int
    high: int | None
    power: int | None
    toughness: int | None
    lines: tuple[str, ...]

    def holds(self, level: int) -> bool:
        """CR 711.2a/b: whether `level` level counters are in this band."""
        return level_band_holds((self.low, self.high), level)


def level_bands(text: str) -> list[LevelBand]:
    """Every level striation of a leveler's text box, in printed order (CR
    711.2). Empty for text with no level symbol."""
    bands: list[LevelBand] = []
    current: dict[str, Any] | None = None
    for entry in level_striations(text.splitlines()):
        if entry.role == "symbol":
            if current is not None:
                bands.append(_band(current))
            assert entry.band is not None
            current = {"band": entry.band, "box": None, "lines": []}
        elif current is not None and entry.role == "box":
            current["box"] = entry.text
        elif current is not None and entry.text:
            current["lines"].append(entry.text)
    if current is not None:
        bands.append(_band(current))
    return bands


def _band(read: dict[str, Any]) -> LevelBand:
    low, high = read["band"]
    power = toughness = None
    if read["box"] is not None:
        printed_power, printed_toughness = read["box"].split("/")
        power, toughness = int(printed_power), int(printed_toughness)
    return LevelBand(low, high, power, toughness, tuple(read["lines"]))


def active_level_band(permanent: CardState) -> LevelBand | None:
    """The striation a leveler permanent's level counters are in, or None -
    below N1 (CR 711.5) or off the battlefield (CR 711.6)."""
    if permanent.zone is not Zone.BATTLEFIELD or not permanent.is_leveler:
        return None
    level = permanent.counter_count(LEVEL_COUNTER)
    return next(
        (band for band in level_bands(permanent.oracle_text or "") if band.holds(level)), None
    )


def level_symbol_effects(source: CardState, timestamp: int) -> list[Any]:
    """CR 711.2a/b's static ability, for the band the leveler is in now.

    A base power/toughness in layer 7b (CR 613.4b, so a +1/+1 counter still
    adds on top in 7c) and a layer 6 grant (CR 613.1f) of every ability
    printed in the striation. Rebuilt every time the board is computed (CR
    613.5), so the band changes the moment a level counter is put on or taken
    off; stamped with the permanent's own timestamp (CR 613.7a).
    """
    from .layers import ContinuousEffect, Layer, Sublayer, _only, grant_ability
    from .layers.model import SetPowerToughness

    band = active_level_band(source)
    if band is None:
        return []
    label = f"LEVEL {band.low}{'+' if band.high is None else f'-{band.high}'}"
    effects: list[Any] = []
    if band.power is not None and band.toughness is not None:
        effects.append(
            ContinuousEffect(
                description=(
                    f"{source.name}: base {band.power}/{band.toughness} at {label} (CR 711.2)"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.SET,
                timestamp=timestamp,
                source_id=source.id,
                selector=_only(source.id),
                modification=SetPowerToughness(power=band.power, toughness=band.toughness),
            )
        )
    for line in band.lines:
        effects.append(
            ContinuousEffect(
                description=f"{source.name}: {line!r} at {label} (CR 711.2)",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                selector=_only(source.id),
                modification=grant_ability(line),
            )
        )
    return effects


def _level_up_ability(card: Card) -> KeywordAbility | None:
    return next(
        (ability for ability in keyword_abilities(card) if ability.canonical.lower() == "level up"),
        None,
    )


def has_level_up(card: Card) -> bool:
    """Whether this card prints a level up ability (CR 702.87a)."""
    return _level_up_ability(card) is not None


def level_up_activation(game: Any, permanent: CardState, player: str) -> KeywordActivation:
    """Build the activation for a leveler's level up ability (CR 702.87a).

    CR 711.4: "each leveler permanent has its level up ability at all times;
    it may be activated regardless of how many level counters are on that
    permanent." No {T} in the cost, so a leveler that arrived this turn may
    level up at once (CR 602.5a never applies).
    """
    ability = _level_up_ability(permanent.card)
    if ability is None:
        raise ValueError(f"{permanent.name} has no level up ability ({LEVEL_UP_RULE})")
    cost = _keyword_cost(ability, player)
    if cost is None:
        raise ValueError(
            f"{permanent.name}'s level up cost {ability.cost!r} could not be read, "
            "so it cannot be paid"
        )
    return KeywordActivation(
        card=permanent,
        player=player,
        keyword=ability.canonical,
        rule=LEVEL_UP_RULE,
        zone=Zone.BATTLEFIELD,
        cost=cost,
        sorcery_only=True,
        ability=_synthetic_ability(ability, cost_text=ability.cost or "", effect=LEVEL_UP_EFFECT),
        game=game,
    )


def _level_up_effect(activation: KeywordActivation) -> int | None:
    """CR 702.87a: "Put a level counter on this permanent." Through
    `Game.add_counters`, CR 122.6's replaceable event. The permanent is
    re-read off the game by id, the same reason `_equip_effect` does (a
    decoded activation's `card` is a copy)."""
    game = activation.game
    permanent = game.find_by_id(activation.card.id)
    if not isinstance(permanent, CardState):
        permanent = activation.card
    if permanent.zone is not Zone.BATTLEFIELD:
        return None
    return game.add_counters(permanent, LEVEL_COUNTER, 1)


KEYWORD_EFFECTS["level up"] = _level_up_effect
