"""Audit of the static damage prevention and replacement lines (EP-01 round 1,
task T5): "Prevent all damage that would be dealt to / by <group>", "If a source
would deal damage to <recipient>, it deals double / half / that much plus N
instead", "prevent N / X / all but N / half of that damage", "All damage that
would be dealt to you is dealt to <creature> instead", "If damage would be dealt
to this creature, prevent that damage and <counters, tokens, cards>" and
"Damage that would be dealt by <source> can't be prevented".

A line is credited only when `prevention_statics` - the reader that builds the
permanent's `CardReplacement` (CR 615.1, CR 614.1a) and the CR 615.12 static -
reads the whole paragraph, every sentence of it.
"""

from magic_cards_model.machines.replacement.prevention_statics import reads_damage_static_line


def reads_static_line(printing, text, *, card_name=None, legendary=False) -> bool:
    return "damage" in text.lower() and reads_damage_static_line(printing, text)
