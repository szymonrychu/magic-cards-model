"""Per-family static-line audits of the EP-01 rounds.

One module per family, each exposing
`reads_<module>_line(printing, text, *, card_name, legendary) -> bool`, which
asks the PRODUCTION reader whether it performs the static line - never a
re-derived regex. `support._static_ability_category` calls
`reads_<module>_line` just before it gives up on a line as unaudited.
"""

import importlib
import pkgutil
from functools import cache

#: Families that stage a throwaway game per line: asked last, since `any`
#: stops at the first family that reads the line and the answer is the same in
#: any order.
_STAGED_LAST = ("damage_replacement", "enters_counters", "game_rules_untap")


@cache
def _readers():
    return tuple(
        getattr(importlib.import_module(f"{__name__}.{m.name}"), f"reads_{m.name}_line")
        for m in sorted(
            pkgutil.iter_modules(__path__), key=lambda m: (m.name in _STAGED_LAST, m.name)
        )
        if not m.name.startswith("_")
    )


def reads_static_line(printing, text, *, card_name=None, legendary=False) -> bool:
    return any(r(printing, text, card_name=card_name, legendary=legendary) for r in _readers())
