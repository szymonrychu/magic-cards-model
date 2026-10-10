"""Soulbond and pairing (CR 702.95).

CR 702.95a: soulbond is two triggered abilities - "When this creature enters,
you may pair this creature with another unpaired creature you control" and
"Whenever another creature you control enters, you may pair that creature with
this creature" - so a pair is two creatures one player controls.

CR 702.95e: a paired creature becomes unpaired when another player gains
control of it or its partner, when either stops being a creature, or when
either leaves the battlefield. `partner_of` answers "no partner" the moment
the pair stops holding, and `release_broken_pairs` (a state-based sweep, so a
pair broken and then restored between two checks stays broken) forgets the
pointers. CR 702.95d: a creature is paired with only one other creature.
"""

from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.zone import Zone
from .decisions import Decision, DecisionKind, source_id_of

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers import AbilityOnStack


def _live_creature(game: "Game", state: CardState | None) -> bool:
    return (
        state is not None
        and state.zone is Zone.BATTLEFIELD
        and game.computed_board().of(state).is_creature
    )


def partner_of(game: "Game", creature: CardState) -> CardState | None:
    """The creature `creature` is paired with now, or None (CR 702.95e)."""
    if creature.paired_with is None or not _live_creature(game, creature):
        return None
    partner = game.find_by_id(creature.paired_with)
    if (
        not _live_creature(game, partner)
        or partner.paired_with != creature.id
        or game.controller_of(partner).username != game.controller_of(creature).username
    ):
        return None
    return partner


def release_broken_pairs(game: "Game") -> None:
    """Forget every pair that no longer holds (CR 702.95e)."""
    for state in game.battlefield:
        if state.paired_with is not None and partner_of(game, state) is None:
            state.paired_with = None


def is_unpaired(game: "Game", creature: CardState) -> bool:
    return partner_of(game, creature) is None


def pair(game: "Game", first: CardState, second: CardState) -> None:
    """Pair two creatures their controller controls (CR 702.95a)."""
    first.paired_with = second.id
    second.paired_with = first.id


def paired_with_soulbond(game: "Game", creature: CardState) -> bool:
    """Whether `creature` is paired with a creature that has soulbond."""
    from .combat import has_keyword

    partner = partner_of(game, creature)
    return partner is not None and has_keyword(partner, "soulbond", game)


def _candidates(game: "Game", controller: str, others: CardState) -> list[CardState]:
    return [
        state
        for state in game.permanents_controlled_by(controller)
        if state.id != others.id and _live_creature(game, state) and is_unpaired(game, state)
    ]


def soulbond_effect(game: "Game", ability: "AbilityOnStack") -> bool | None:
    """Resolve either soulbond trigger: the controller may pair, if both
    creatures are still unpaired creatures they control (CR 702.95a, whose
    "if you control both ... and both are unpaired" is checked here, on
    resolution, and CR 702.95c: otherwise neither becomes paired)."""
    source = ability.source(game)
    if source is None or not _live_creature(game, source) or not is_unpaired(game, source):
        return None
    controller = game.controller_of(source).username
    entered = game.find_by_id(ability.event.subject_id) if ability.event else None
    own_entry = entered is None or entered.id == source.id
    if own_entry:
        options = _candidates(game, controller, source)
    elif (
        _live_creature(game, entered)
        and game.controller_of(entered).username == controller
        and is_unpaired(game, entered)
    ):
        options = [entered]
    else:
        options = []
    if not options:
        return None
    if not game.may(
        controller,
        f"pair {source.name} with another creature",
        source=ability.source_name,
        source_id=source_id_of(ability),
        cards=options,
    ):
        return False
    partner = options[0]
    if len(options) > 1:
        answer = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller,
                prompt=f"choose the creature to pair with {source.name}",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                cards=tuple(state.id for state in options),
                default_cards=(options[0].id,),
            )
        )
        chosen = {state.id: state for state in options}
        partner = next((chosen[card_id] for card_id in answer if card_id in chosen), options[0])
    pair(game, source, partner)
    return True
