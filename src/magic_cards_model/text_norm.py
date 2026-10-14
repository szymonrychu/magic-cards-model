"""Whitespace collapsing shared by the text readers.

Every reader on a dispatch ladder normalises the text it is handed the same
way - `" ".join(text.split())` - and a ladder hands one text to hundreds of
readers in turn, so the normalised form is memoised here once per text.
"""

import functools

__all__ = ["collapsed"]


@functools.lru_cache(maxsize=65536)
def collapsed(text: str) -> str:
    """`text` with each run of whitespace made one space and none left at
    either end: `" ".join(text.split())`."""
    return " ".join(text.split())
