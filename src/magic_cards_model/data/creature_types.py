"""CR 205.3m's creature types: the legal answers to "choose a creature type".

CR 205.3m (read in full with `mise run rules:find 205.3m`): "Creatures and
kindreds share their lists of subtypes; these subtypes are called creature
types. One creature type is two words long: Time Lord. All other creature types
are one word long: Advisor, Aetherborn, ..., and Zubera."

The list is read out of the rules text by `rules_creature_types` and bundled in
`creature_types.json` by `scripts/add_creature_types.py`, because `.rules/` is
gitignored and not there at runtime. It is deliberately not `subtypes.json`'s
creature group: that is Scryfall's catalog of every creature subtype ever
printed, which is a different list from the one the rules define, and this
question is answered by the rules.

The rules print two apostrophes typographically (C'tan, Shi'ar); they are kept
as the plain apostrophe Oracle type lines use, so a chosen type compares equal
to the type line it is later matched against.
"""

import json
import re
from functools import cache
from pathlib import Path

from .. import __file__ as _package_file

CREATURE_TYPES_FILE = Path(_package_file).parent / "data" / "creature_types.json"
#: `mise run rules:pull`'s destination, relative to the repository root.
RULES_FILE = Path(_package_file).parent.parent.parent / ".rules" / "MagicCompRules.txt"

_RULE_LINE = re.compile(r"^205\.3m (?P<body>.+)$", re.MULTILINE)
#: Each "... long: A, B, and C." list in the rule - the two-word one and the
#: one-word one.
_LIST = re.compile(r"long: (?P<items>[^.]+)\.")


def rules_creature_types(rules_text: str) -> tuple[str, ...]:
    """Every creature type CR 205.3m lists, in the order the rule prints them."""
    match = _RULE_LINE.search(rules_text)
    if match is None:
        raise ValueError("CR 205.3m is not in this rules text")
    types: list[str] = []
    for listed in _LIST.finditer(match.group("body")):
        for item in listed.group("items").split(","):
            word = item.strip().removeprefix("and ").strip().replace("’", "'")
            if word:
                types.append(word)
    return tuple(types)


@cache
def creature_types() -> tuple[str, ...]:
    """The bundled CR 205.3m list."""
    return tuple(json.loads(CREATURE_TYPES_FILE.read_text())["types"])
