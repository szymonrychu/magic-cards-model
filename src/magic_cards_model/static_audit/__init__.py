"""Per-family static-line audits of the EP-01 rounds.

One module per family, each exposing
`reads_static_line(printing, text, *, card_name, legendary) -> bool`, which
asks the PRODUCTION reader whether it performs the static line - never a
re-derived regex. `support._static_ability_category` calls
`reads_static_line` just before it gives up on a line as unaudited.
"""

import importlib
import pkgutil
from functools import cache


@cache
def _readers():
    return tuple(
        importlib.import_module(f"{__name__}.{m.name}").reads_static_line
        for m in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name)
        if not m.name.startswith("_")
    )


def reads_static_line(printing, text, *, card_name=None, legendary=False) -> bool:
    return any(r(printing, text, card_name=card_name, legendary=legendary) for r in _readers())
