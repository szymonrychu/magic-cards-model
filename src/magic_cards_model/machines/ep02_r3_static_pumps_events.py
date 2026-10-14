"""EP-02 R3 T1: the event-driven clauses of the static-for-each-pump cards.

- "each player gains control of each land they own that you control" (Herald of
  Leshrac's leaves-the-battlefield trigger): a layer 2 control change with no
  duration (CR 613.1b, CR 611.2a) for every land on the battlefield that
  `you` control and another player owns (CR 108.3), applied to each object as
  it is now (CR 400.7).
"""

import re
from typing import TYPE_CHECKING, Any

from ..models.zone import Zone
from .effects._chains import ABILITY_TEXT

if TYPE_CHECKING:
    from ..models.game import Game

_RETURN_LANDS_RE = re.compile(
    r"^each player gains control of each (?P<noun>land|permanent|creature|artifact) they own "
    r"that you control\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_each_player_regains_what_they_own(text: str) -> Any:
    """ "Each player gains control of each `<permanent>` they own that you
    control" (CR 701.?): every such permanent goes back to its owner."""
    match = _RETURN_LANDS_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    from ..models.card import Type

    wanted = {
        "land": Type.LAND,
        "permanent": None,
        "creature": Type.CREATURE,
        "artifact": Type.ARTIFACT,
    }[match["noun"].lower()]

    def effect(game: "Game", ability: Any) -> None:
        from .layers import (
            ContinuousEffect,
            Duration,
            Layer,
            only_this_incarnation,
            set_controller,
        )

        controller = game.controller_of(ability).username
        board = game.computed_board()
        store = game.continuous_effects
        timestamp = store.tick()
        for permanent in list(game.battlefield):
            chars = board.of(permanent)
            if chars.controller != controller or permanent.owner in (None, controller):
                continue
            if wanted is not None and wanted not in chars.types:
                continue
            store.add(
                ContinuousEffect(
                    description=f"{permanent.owner} gains control of {permanent.name}",
                    layer=Layer.CONTROL,
                    timestamp=timestamp,
                    duration=Duration.INDEFINITE,
                    selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                    modification=set_controller(permanent.owner),
                ),
                game,
            )

    return effect


_EXILE_ANY_NUMBER_UNTIL_RE = re.compile(
    r"^exile any number of other (?P<desc>nontoken [a-z]+s|[a-z]+s) you control until "
    r"(?:it|this (?:creature|permanent|artifact|enchantment)) leaves the battlefield\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_exile_any_number_until_leaves(text: str) -> Any:
    """ "Exile any number of other nontoken creatures you control until this
    creature leaves the battlefield" (Lumbering Battlement): the controller
    chooses zero up to all of them as it resolves (CR 107.1c, CR 608.2d); each is
    exiled linked to the source (CR 607.2a) and returns when it leaves
    (CR 610.3). CR 610.3b: a source that already left exiles nothing."""
    match = _EXILE_ANY_NUMBER_UNTIL_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    from .ep02_r2_chosen_amounts import _permanent_matcher

    permanent = _permanent_matcher(match["desc"])
    if permanent is None:
        return None
    _untapped, _other, predicate = permanent

    def effect(game: "Game", ability: Any) -> None:
        from .ep02_r2_chosen_amounts import choose_any_number
        from .linked_exile import exile_linked_until_leaves

        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        player = game.controller_of(ability)
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(player.username)
            if permanent.id != source.id and predicate(game, player.username, permanent)
        ]
        chosen = choose_any_number(game, ability, player, candidates, text.strip().rstrip("."))
        exile_linked_until_leaves(game, source, chosen, player.username)

    return effect


_ADDITIONAL_COMBAT_AFTER_THIS_PHASE_RE = re.compile(
    r"^there(?: is|'s) an additional combat phase after this (?:main )?phase\."
    r"(?: at the beginning of that combat, (?P<rider>untap all creatures you control))?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_additional_combat_then_untap(text: str) -> Any:
    """ "There's an additional combat phase after this phase. At the beginning
    of that combat, untap all creatures you control" (Moraug, Fury of Akoum):
    CR 500.8 adds the phase directly after the one in progress, and the
    delayed trigger (CR 603.7) fires at the beginning of the next combat
    phase, which is the added one."""
    match = _ADDITIONAL_COMBAT_AFTER_THIS_PHASE_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    untaps = match["rider"] is not None

    def effect(game: "Game", ability: Any) -> None:
        from .abilities import TriggerEvent
        from .delayed import DelayedTrigger, UntapAllCreaturesForController
        from .turn import COMBAT_PHASE_STEPS, Step

        assert game.turn is not None
        game.turn.insert_extra_phase(COMBAT_PHASE_STEPS)
        if untaps:
            game.create_delayed_trigger(
                DelayedTrigger(
                    text="At the beginning of that combat, untap all creatures you control.",
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=Step.BEGINNING_OF_COMBAT,
                    controller=game.controller_of(ability).username,
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    effect=UntapAllCreaturesForController(),
                )
            )

    return effect
