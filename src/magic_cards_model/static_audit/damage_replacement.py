"""Audit of the static damage prevention and replacement lines (EP-01 round 1,
task T5): "Prevent all damage that would be dealt to / by <group>", "If a source
would deal damage to <recipient>, it deals double / half / that much plus N
instead", "prevent N / X / all but N / half of that damage", "All damage that
would be dealt to you is dealt to <creature> instead", "If damage would be dealt
to this creature, prevent that damage and <counters, tokens, cards>",
"Damage that would be dealt by <source> can't be prevented" and the optional
attack cost "You may exert this creature as it attacks. When you do, prevent ...".

A line is credited only when the production reader - `prevention_statics` for the
`CardReplacement` (CR 615.1, CR 614.1a) and the CR 615.12 static,
`exert_on_attack` for the CR 701.43d cost - reads the whole paragraph, every
sentence of it.
"""

from magic_cards_model.machines.exert_on_attack import reads_exert_as_it_attacks_line
from magic_cards_model.machines.replacement.prevention_statics import reads_damage_static_line


def reads_static_line(printing, text, *, card_name=None, legendary=False) -> bool:
    lowered = text.lower()
    if "exert" in lowered and reads_exert_as_it_attacks_line(text):
        return True
    return "damage" in lowered and reads_damage_static_line(printing, text)
