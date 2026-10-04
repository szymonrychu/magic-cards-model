"""Fixture: module mode with relative imports at both depths."""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..top_helper import top
from .sibling import sib

if TYPE_CHECKING:
    from .sibling import SibT

PATTERN = re.compile("a+")
TABLE_NAMES = ("one", "two")


def decorate(fn: Callable[..., str]) -> Callable[..., str]:
    return fn


class Wide:
    width = 3


# leading comment line one
# leading comment line two
@decorate
def text_one(s: str) -> str:
    from . import sibling as sibmod
    from .sibling import lazy_sib

    return PATTERN.sub("", s) + lazy_sib() + sibmod.NAME + top()


def text_two(s: "SibT", wide: "Wide") -> str:
    return text_one(str(s)) + sib() + str(wide.width)


def stray_new_helper() -> str:
    return "stray"


DISPATCH = {"one": text_one, "two": text_two}


def dispatch_run(name: str, s: str) -> str:
    return DISPATCH[name](s) + _private_dispatch_tag()


def _private_dispatch_tag() -> str:
    return stray_new_helper()
