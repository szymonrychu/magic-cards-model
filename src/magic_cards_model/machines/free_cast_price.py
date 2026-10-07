"""What a cast "without paying its mana cost" really costs, before it is cast.

CR 118.9d: "If an alternative cost is being paid to cast a spell, any
additional costs, cost increases, and cost reductions that affect that spell
are applied to that alternative cost." CR 601.2f then applies the effects that
directly affect the total cost - Trinisphere's "each spell that would cost
less than three mana to cast costs three mana to cast" - so a free cast under
an untapped Trinisphere costs {3}. `Casting.total_cost` already charges that;
this prices it for the "you may cast it" offer, which is asked before any
`Casting` exists, so the player deciding is told the real cost.
"""

from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.mana import ManaCost
from ..models.zone import Zone
from .cost import TotalCost, apply_modifications, total_cost_for_phrase
from .spell_grants import granted_affinity_reductions

if TYPE_CHECKING:
    from ..models.game import Game


def board_priced_mana(
    game: "Game",
    spell: CardState,
    caster: str,
    base: ManaCost,
    *,
    origin_zone: Zone | None = None,
    floor_applies: bool = True,
) -> ManaCost:
    """`base` - a printed mana cost, or CR 118.9's empty alternative cost -
    with every other permanent's cost increase, reduction and floor applied
    (CR 601.2f, CR 118.9d), the same board modifiers `Casting.total_cost`
    folds in. `floor_applies=False` leaves the floor out for a cost whose X
    is not announced yet (CR 107.3a): a floored unannounced X would be a
    number nobody chose."""
    increases, reductions, floor = game.static_cost_modifiers_for(
        spell, caster, origin_zone=origin_zone
    )
    cast_from = origin_zone if origin_zone is not None else spell.zone
    reductions = reductions + granted_affinity_reductions(game, spell, caster, cast_from)
    return apply_modifications(base, increases, reductions, floor=floor if floor_applies else None)


def with_board_priced_cost(
    game: "Game",
    prompt: str,
    card: CardState,
    caster: str,
    alternative_cost: TotalCost | None = None,
    pays_mana_cost: bool = False,
) -> str:
    """`prompt` with the cast's real mana cost added when other permanents
    change it (CR 601.2f, CR 118.9d): "without paying its mana cost" under an
    untapped Trinisphere is {3}, not free, and the offer is where the player
    decides whether to take it. Unchanged when nothing on the board touches
    the cost."""
    if alternative_cost is not None:
        base = alternative_cost.mana
    elif pays_mana_cost and card.mana_cost:
        printed = total_cost_for_phrase(card.mana_cost, caster)
        base = printed.mana if printed is not None else ManaCost()
    else:
        base = ManaCost()
    priced = board_priced_mana(game, card, caster, base, floor_applies=not base.x_count)
    if priced == base:
        return prompt
    return f"{prompt} - total cost {priced} (CR 601.2f, CR 118.9d)"
