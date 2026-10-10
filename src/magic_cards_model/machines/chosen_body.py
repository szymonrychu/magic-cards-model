"""The bodies an "it becomes your choice of ..." / "this creature enters as a ..."
sentence names (Corrupted Shapeshifter, Primal Plasma, Aquamorph Entity, Molten
Sentry): a base power/toughness and the keywords it comes with (CR 614.1c,
CR 613.4b).

Pure text reading, shared by the replacement side that asks the choice
(`machines/replacement/enters_choices.py`) and the layer side that applies the
answer (`machines/layers/enters_forms.py`).
"""

import re
from typing import NamedTuple


class Body(NamedTuple):
    power: int
    toughness: int
    keywords: tuple[str, ...]


_BODY_RE = re.compile(
    r"^(?:an? )?(?P<power>\d+)/(?P<toughness>\d+)(?: creature)?"
    r"(?: with (?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:, | and |, and )[a-z]+(?: [a-z]+)?)*))?\.?$"
)
_OPTION_SPLIT_RE = re.compile(r",\s*(?:or\s+)?|\s+or\s+")


def strip_article(option: str) -> str:
    return re.sub(r"^an? ", "", option.strip())


def parse_body(option: str) -> Body | None:
    """`3/3 creature with flying` -> `Body(3, 3, ("flying",))`; None for any
    other wording."""
    match = _BODY_RE.match(option.strip())
    if match is None:
        return None
    keywords = match.group("keywords")
    return Body(
        int(match.group("power")),
        int(match.group("toughness")),
        tuple(re.split(r",\s*(?:and\s+)?|\s+and\s+", keywords)) if keywords else (),
    )


def split_body_options(text: str) -> tuple[str, ...] | None:
    """The printed options of "a 3/3 creature with flying, a 2/5 creature with
    vigilance, or a 0/12 creature with defender" (articles dropped), or None
    when any of them is not a body this module reads."""
    options = tuple(strip_article(part) for part in _OPTION_SPLIT_RE.split(text) if part.strip())
    if len(options) < 2 or any(parse_body(option) is None for option in options):
        return None
    return options
