"""Fixture: an eager cycle between two targets."""


def a_one() -> int:
    return 1


def b_one() -> int:
    return 2


A_TABLE = {"b": b_one}
B_TABLE = {"a": a_one}
