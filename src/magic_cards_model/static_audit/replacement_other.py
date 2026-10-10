"""EP-01 round 1 (task 6) audit: replacement statics that are not a card's own
printed "If ... would ..., ... instead" paragraph.

The printed paragraphs are credited by `parse.performs_static_line` already
(the `OTHER_COMPILERS` of `machines/replacement/other_statics.py` are part of
`parse._COMPILERS`).  What remains is a static line whose *grant* is the
printed ability: "All Slivers have "If this permanent would be put into a
graveyard, you may put it on top of its owner's library instead."" (CR 613.1f,
CR 113.6).  It is credited only when the production layer reader takes the
grant (`_ALL_SUBTYPE_QUOTED_GRANT_RE`) and the production replacement reader
(`_granted_line_replacements`) compiles the granted line.
"""

from ..data.subtypes import subtype_vocabulary
from ..machines.layers.parse import _ALL_SUBTYPE_QUOTED_GRANT_RE
from ..machines.replacement.model import _granted_line_replacements
from ..machines.replacement.parse import strip_reminder_text


def reads_static_line(printing, text, *, card_name=None, legendary=False) -> bool:
    line = strip_reminder_text(text)[0].strip()
    if " would " not in line.lower():
        return False
    match = _ALL_SUBTYPE_QUOTED_GRANT_RE.fullmatch(line)
    if match is None or match.group("subtype").lower() not in subtype_vocabulary():
        return False
    return bool(_granted_line_replacements(printing, [match.group("ability").strip()]))
