"""Fixture: the facade order must keep a deferred import from reaching a module early."""

D_DEFAULT = 3


def m_call() -> int:
    return n_call(1)


def n_call(x: int, base: int = D_DEFAULT) -> int:
    return d_call(x) + base


def d_call(x: int) -> int:
    return x if x < 1 else n_call(x - 1)
