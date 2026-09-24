"""Cast-record conditions: how a spell was cast and which costs were paid for it
(CR 601.2b-h), read off `CastRecord`.

Each reader here is a `ConditionReader` registered through `READERS`; see
`machines/conditions/__init__.py` for the contract every reader keeps.
"""

from . import ConditionReader

READERS: tuple[ConditionReader, ...] = ()
