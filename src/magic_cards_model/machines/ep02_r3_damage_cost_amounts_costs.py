"""EP-02 R3 T8 part: spell cost reductions that name a quality after the subject.

- `spells_that_are_normalised`: "Spells you cast this turn that are black and/or red cost
  {2} less to cast." (Rowan, Scion of War; Will, Scion of Peace) is the "<quality> spells you
  cast this turn cost {N} less to cast" the this-turn grant reader already prices
  (CR 601.2f); "black and/or red" is "black or red" (a spell with either colour, or both).
  The X of "{X} less ... where X is the amount of life you lost this turn" is measured once
  as the ability resolves and written in (CR 608.2h) by `ep02_r2_chosen_amounts`.
- `ActivationCostReduction.where_x` (`machines/abilities.py`): "This ability costs {X} less to
  activate, where X is the number of differently named lands you control." (Survey Mechan),
  priced by `Game.activation_cost_reduction_for` as the cost is determined (CR 601.2f).
"""

import functools
import re

_SPELLS_THAT_ARE_RE = re.compile(
    r"^spells you cast this turn that are (?P<quality>[a-z]+(?:,? (?:and/or|and|or) [a-z]+)*) "
    r"(?P<rest>cost \{\d+\} (?:less|more) to cast\.?)$",
    re.IGNORECASE,
)


@functools.cache
def spells_that_are_normalised(text: str) -> str:
    """`text` as "<quality> spells you cast this turn cost ...", or unchanged."""
    if " that are " not in text.lower() or not text.lower().startswith("spells you cast"):
        return text
    match = _SPELLS_THAT_ARE_RE.fullmatch(text)
    if match is None:
        return text
    quality = re.sub(r"\band/or\b|\band\b", "or", match.group("quality"), flags=re.IGNORECASE)
    return f"{quality} spells you cast this turn {match.group('rest')}"
