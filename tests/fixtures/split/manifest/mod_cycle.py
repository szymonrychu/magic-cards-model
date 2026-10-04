"""Fixture: an eager cycle between two targets (class bases)."""


class A1:
    pass


class B1(A1):
    pass


class A2(B1):
    pass
