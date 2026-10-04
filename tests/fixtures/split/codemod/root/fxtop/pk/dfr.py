"""Fixture: a deferred mutual reference between two targets."""

from __future__ import annotations


def a_start(n: int) -> int:
    return n if n <= 0 else b_step(n - 1) + 1


def b_step(n: int) -> int:
    return a_start(n - 1) + 1
