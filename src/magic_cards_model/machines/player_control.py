"""The printed sentence that hands one player control of another (CR 723).

"You control target player during that player's next turn." (Mindslaver)
and "you control target opponent during their next turn." (Construct a Cosmic
Cube's reflexive payoff) are one instruction: CR 723.1's effect on the
targeted player's next turn. What that effect *does* - which turn it takes
hold on, how long it lasts, who then decides what (CR 723.1-723.9) - lives on
`TurnMachine`/`Game` (`Game.gain_control_of_player`); this module only reads
the sentence off any card that prints it, so no card is keyed by name.
"""

import re
from typing import TYPE_CHECKING

from magic_cards_model.text_norm import collapsed

from ..models.player import Player

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ..models.game import Game
    from .effects import StackObject, TargetedClause

#: "you control target player during that player's next turn" / "you control
#: target opponent during their next turn" / "you gain control of target
#: opponent during that player's next turn" - CR 723.1's two printed verbs,
#: either target word, either possessive.
_CONTROL_TARGET_PLAYER_NEXT_TURN_RE = re.compile(
    r"^you (?:gain )?control (?:of )?target (?:player|opponent) during"
    r" (?:that player's|their) next turn\.?$",
    re.IGNORECASE,
)


def parse_control_target_player_next_turn(
    clause: str, *, for_spell: bool
) -> "TargetedClause | None":
    """`_CONTROL_TARGET_PLAYER_NEXT_TURN_RE`'s instruction, on a spell or an
    ability: each targeted player still in the game (CR 608.2b) is controlled
    by the resolving object's controller during their next turn (CR 723.1).
    Control of yourself is legal and changes nothing (CR 723.9)."""
    if _CONTROL_TARGET_PLAYER_NEXT_TURN_RE.fullmatch(collapsed(clause.strip())) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        for target in game.resolve_targets(stack_object):
            if isinstance(target, Player) and game.is_in_game(target.username):
                game.gain_control_of_player(controller, target.username)

    return effect
