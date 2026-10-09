"""Per-family static-line audits of the EP-01 rounds.

One module per family, each exposing
`reads_static_line(printing, text, *, card_name, legendary) -> bool` that asks
the PRODUCTION reader of the family, never a re-derived regex.  Modules are
auto-discovered; a module whose name starts with an underscore is skipped.
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
