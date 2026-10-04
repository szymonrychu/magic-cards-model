"""Fixture: bake majority, tie-breaks, propagation."""


def a_one():
    return h_major()


def a_two():
    return h_major()


def b_one():
    return h_major()


def c_one():
    return 1


def c_two():
    return 2


def a_three():
    return h_tie()


def b_three():
    return h_tie()


def h_tie():
    return c_one() + c_two()


def a_four():
    return h_tie2()


def b_four():
    return h_tie2()


def c_three():
    return 3


def h_tie2():
    return a_one() + b_one()


def h_major():
    return h_chain()


def h_chain():
    return 0


def h_orphan():
    return 1
