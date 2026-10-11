"""Audit of the "other statics" grab-bag (EP-01 round 2, T8): trigger
multipliers and suppression (CR 603.2d), crew/saddle/station contribution,
player-action prohibitions (CR 101.2), revealed hands/top cards and face-down
looks (CR 400.2, 701.20a), equip restrictions, block-as-though statics and
loyalty-ability statics. A line is credited only when the production reader of
its family performs it."""

from ..machines.cleanup_damage_statics import reads_damage_kept_through_cleanup_line
from ..machines.crew_saddle_statics import reads_crew_saddle_line
from ..machines.exert_on_attack import reads_exert_as_it_attacks_line
from ..machines.equip_block_statics import reads_equip_block_line
from ..machines.player_action_prohibitions import reads_player_action_prohibition_line
from ..machines.revealed_information import reads_revealed_information_line
from ..machines.transform_prohibitions import reads_cant_transform_line
from ..machines.trigger_doubling import reads_trigger_doubling_line

_FAMILIES = (
    reads_trigger_doubling_line,
    reads_crew_saddle_line,
    reads_player_action_prohibition_line,
    reads_revealed_information_line,
    reads_equip_block_line,
    reads_exert_as_it_attacks_line,
    reads_damage_kept_through_cleanup_line,
    reads_cant_transform_line,
)


def reads_other_statics_line(printing, text, *, card_name, legendary) -> bool:
    return any(family(text) for family in _FAMILIES)
