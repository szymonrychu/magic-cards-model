"""EP-01 round 2, task T1: group anthems, group grants and type statics.

Most of this family is read by `machines/layers/group_grants.py` through
`parsed_layer_effects`, which `support._static_ability_category` asks before
any audit module. What lands here is the part another production reader
performs: each predicate stages a throwaway permanent of the printing on a real
`Game` and asks that reader, never a regex of its own (see
`static_audit/__init__.py`).
"""

from magic_cards_model.machines.combat import may_assign_as_though_unblocked
from magic_cards_model.models.game import Game
from magic_cards_model.models.player import Player
from magic_cards_model.models.zone import Zone

#: Cheap lowercase gate: every line this module can credit carries one of these.
_GATES = ("as though it weren't blocked",)


def _staged(printing):
    from magic_cards_model.support import _synthetic_permanent

    game = Game(
        players=[Player(username="sweep_you"), Player(username="sweep_opp")],
        schema_version=Game.CURRENT_SCHEMA_VERSION,
    )
    state = _synthetic_permanent(
        printing, controller="sweep_you", token=False, tapped=False, counter_kind=None
    )
    state.bind_to_game(game)
    state.zone = Zone.BATTLEFIELD
    game.battlefield.append(state)
    return game, state


_UNBLOCKED_CACHE: dict[str, bool] = {}


def _may_assign_as_though_unblocked(printing) -> bool:
    if printing.name not in _UNBLOCKED_CACHE:
        game, state = _staged(printing)
        _UNBLOCKED_CACHE[printing.name] = may_assign_as_though_unblocked(game, state)
    return _UNBLOCKED_CACHE[printing.name]


def reads_anthems_grants_line(printing, text, *, card_name=None, legendary=False) -> bool:
    lowered = text.lower()
    if not any(gate in lowered for gate in _GATES):
        return False
    return _may_assign_as_though_unblocked(printing)
