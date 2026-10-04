"""Fixture: eager vs deferred reference classification.

The future import makes function annotations (`late_ann`) deferred; without it
they run at def time and are eager.
"""

from __future__ import annotations

from math import floor


def base_dec(fn):
    return fn


class BaseThing:
    pass


def base_default():
    return 1


def base_body():
    return 2


class BaseAnn:
    pass


def base_lazy():
    return 3


def base_str():
    return 4


@base_dec
def user_decorated():
    return 0


class UserChild(BaseThing):
    attr = base_default()


def user_default(x=base_default()):  # noqa: B008
    return x


MODULE_EXPR = base_body()

TYPED: "BaseAnn" = None  # noqa: UP037 - the string annotation is the case under test


def late_body():
    return base_body()


def late_ann(x: BaseAnn) -> "BaseThing":  # noqa: UP037
    return floor(x)


def late_lazy():
    from math import ceil as base_lazy

    return base_lazy(1.5)


def late_lambda():
    return lambda: base_str()
