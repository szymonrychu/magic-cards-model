"""Fixture: no import order is safe (two deferred imports into a module with eager needs)."""

C_BASE = 1
D_BASE = 2


def c_run() -> int:
    return n_run()


def n_run(base: int = C_BASE, other: int = D_BASE) -> int:
    return base + other


def d_run() -> int:
    return n_run()
