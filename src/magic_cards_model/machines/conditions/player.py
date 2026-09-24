"""Player-state conditions: hands, graveyards, exile, life totals, poison and
libraries.

Each reader here is a `ConditionReader` registered through `READERS`; see
`machines/conditions/__init__.py` for the contract every reader keeps.
"""

from . import ConditionReader

READERS: tuple[ConditionReader, ...] = ()
