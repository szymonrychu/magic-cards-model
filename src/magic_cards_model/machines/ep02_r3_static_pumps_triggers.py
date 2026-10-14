"""EP-02 R3 T1: the non-static clauses of the static-for-each-pump cards (triggers).

Each rung reads an amount the static readers already know (`ep02_r3_static_pumps`
counts) or a plain game count, at the moment the instruction is applied
(CR 608.2h):

- "draw a card for each Aura you control that's attached to a creature" (Sage's
  Reverie): a board count, CR 303.4 / CR 301.5 attachment, read after the Aura
  entered, so it counts itself (it is attached to a creature, CR 303.4).
- "create a number of <token> tokens equal to the number of opponents you have"
  (Silverwing Squadron): CR 102.2 / CR 102.3 opponents; a player who has left
  the game is no longer an opponent (CR 800.4a).
"""

import re
from typing import TYPE_CHECKING, Any

from ..models.zone import Zone
from .effects._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game


def board_count_now(game: "Game", source: "CardState", phrase: str) -> int | None:
    """The number `phrase` ("Aura you control that's attached to a creature")
    counts on the board right now, asked from `source`'s point of view, or
    `None` when the static count reader does not know the phrase."""
    from .effects.continuous import layer_context_for
    from .ep02_r3_static_pumps import count_for

    context = layer_context_for(game, game.player(source.controller))
    count = count_for(phrase, source, context)
    if count is None:
        return None
    board = game.computed_board()
    return count(board.of(source), board.characteristics)


_DRAW_FOR_EACH_RE = re.compile(
    r"^draw a card for each "
    r"(?P<each>(?:[a-z-]+ )*aura you control that's attached to a creature)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_draw_for_each_board_count(text: str, *, for_spell: bool) -> Any:
    """ "Draw a card for each `<permanent description>`" over a board count
    the static readers know (CR 121.1: draw one card that many times)."""
    match = _DRAW_FOR_EACH_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    each = match["each"].lower()

    def effect(game: "Game", stack_object: Any) -> None:
        source = stack_object.source_or_last_known(game)
        if source is None:
            return
        amount = board_count_now(game, source, each)
        if amount:
            game.draw_cards(game.controller_of(stack_object), amount)

    return effect


_BASE_PT_COPY_RE = re.compile(
    r"^(?P<may>you may )?have the base power and toughness of (?P<target>target [^.,]+?) "
    r"become equal to this (?:creature|permanent)'s power and toughness until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_base_pt_becomes_source_pt(text: str) -> Any:
    """ "[You may] have the base power and toughness of target `<creature>`
    become equal to this creature's power and toughness until end of turn"
    (Exuberant Wolfbear): the source's power and toughness are read once as the
    instruction is applied (CR 608.2h, last known information if it has left,
    CR 603.10a) and set as the target's base (CR 613.4b, sublayer 7b), lasting
    until the cleanup step (CR 514.2)."""
    match = _BASE_PT_COPY_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    from .effects._common import _targets_understood

    if not _targets_understood(match["target"]):
        return None
    optional = match["may"] is not None

    def effect(game: "Game", stack_object: Any) -> None:
        from .effects.continuous import continuous_effects
        from .layers.model import (
            ContinuousEffect,
            Duration,
            Layer,
            Sublayer,
            only_this_incarnation,
            set_power_toughness,
        )

        source = stack_object.source_or_last_known(game)
        controller = game.controller_of(stack_object)
        if source is None:
            return
        if optional and not game.may(
            controller,
            f"Have the base power and toughness of the target become {source.name}'s?",
            source=source.name,
            source_id=str(source.id),
        ):
            return
        power, toughness = game.computed_board().of(source).power_toughness
        if power is None or toughness is None:
            return
        store = continuous_effects(game)
        timestamp = store.tick()
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, type(source)) or target.zone is not Zone.BATTLEFIELD:
                continue
            store.add(
                ContinuousEffect(
                    description=f"{source.name}: {target.name} has base power and toughness "
                    f"{power}/{toughness}",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.SET,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=set_power_toughness(power, toughness),
                )
            )

    return effect


_FUNGUS_DINOSAUR_RE = re.compile(
    r"^create an? (?P<color>[a-z]+) (?P<types>(?:[A-Z][a-z]+ )+)creature token "
    r"with base power and toughness each equal to the total power of those creatures\.?$",
    re.IGNORECASE,
)


def total_power_of_those_creatures(game: "Game", stack_object: Any) -> int:
    """The summed last-known power (CR 603.10a) of the creatures that died in
    the one event (`GameEvent.died_together`, CR 704.3) which match the
    triggered ability's own condition - "those creatures" of a "whenever one or
    more nontoken creatures you control die" trigger (CR 603.2c)."""
    from .triggers.conditions import _condition_matches

    event = stack_object.event
    source = stack_object.source_or_last_known(game)
    if event is None or source is None:
        return 0
    members = event.died_together or (event,)
    return sum(
        member.subject_power or 0
        for member in members
        if _condition_matches(game, stack_object.ability, source, stack_object.controller, member)
    )


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_token_base_pt_total_power(text: str) -> Any:
    """ "Create a `<color>` `<types>` creature token with base power and
    toughness each equal to the total power of those creatures" (The Skullspore
    Nexus, CR 111.3: the creating effect defines the token's characteristics,
    so the total is its base power and toughness)."""
    match = _FUNGUS_DINOSAUR_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    from ..models.card import Color, Type
    from ..models.token import TokenDefinition, create_tokens

    try:
        color = Color[match["color"].upper()]
    except KeyError:
        return None
    subtypes = tuple(word.capitalize() for word in match["types"].split())

    def effect(game: "Game", stack_object: Any) -> None:
        total = total_power_of_those_creatures(game, stack_object)
        create_tokens(
            game,
            TokenDefinition(
                types=(Type.CREATURE,),
                subtypes=subtypes,
                colors=(color,),
                power=total,
                toughness=total,
            ),
            game.controller_of(stack_object).username,
        )

    return effect


_DOUBLE_POWER_RE = re.compile(
    r"^double (?P<target>target [^.,']+?)(?:'s|’s) power until end of turn\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_double_target_power(text: str) -> Any:
    """ "Double target creature's power until end of turn" (The Skullspore
    Nexus): +X/+0 in sublayer 7c (CR 613.4c) where X is the target's power as
    the instruction is applied (CR 608.2h) - fixed then, so a later change to
    the power does not change the size of the pump - lasting until the
    cleanup step (CR 514.2)."""
    match = _DOUBLE_POWER_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    from .effects._common import _targets_understood

    if not _targets_understood(match["target"]):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        from .effects.continuous import continuous_effects
        from .layers.model import (
            ContinuousEffect,
            Duration,
            Layer,
            Sublayer,
            modify_power_toughness,
            only_this_incarnation,
        )

        source = stack_object.source_or_last_known(game)
        store = continuous_effects(game)
        timestamp = store.tick()
        for target in game.resolve_targets(stack_object):
            if not hasattr(target, "zone_change_stamp") or target.zone is not Zone.BATTLEFIELD:
                continue
            power = game.computed_board().of(target).power
            if not power:
                continue
            store.add(
                ContinuousEffect(
                    description=f"{source.name if source else 'Double'}: {target.name} gets "
                    f"{power:+d}/+0",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=modify_power_toughness(power, 0),
                )
            )

    return effect
