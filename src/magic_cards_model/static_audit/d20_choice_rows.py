"""Audit of the EP-01 round 3 T1 static lines: "As this creature transforms
into <face>, choose an opponent." (CR 712.20, recorded on
`CardState.chosen_player`), War's Toll's conditional all-attack requirement
(CR 508.1d) and Sandswirl Wanderglyph's ban on casting by whoever attacked
you this turn (CR 601.3). A line is credited only when its production reader
performs it: `effects.continuous.reads_as_transforms_line` (the reader
`transform_permanent` uses) and
`opponent_attack_restrictions.reads_opponent_attack_restriction_line`.
"""

from ..machines.effects.continuous import reads_as_transforms_line
from ..machines.opponent_attack_restrictions import reads_opponent_attack_restriction_line


def reads_d20_choice_rows_line(printing, text, *, card_name, legendary) -> bool:
    if reads_opponent_attack_restriction_line(text):
        return True
    return "transforms into" in text.lower() and reads_as_transforms_line(text)


#: The name the requirement gives this audit's entry point.
reads_static_line = reads_d20_choice_rows_line
