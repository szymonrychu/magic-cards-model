"""Toy monolith: two families."""


def alpha_one(x: str) -> str:
    return "a1:" + x


def alpha_two(x: str) -> str:
    return alpha_one(x) + "|a2"


def beta_one(x: str) -> str:
    return "b1:" + alpha_two(x)


def beta_two(x: str) -> str:
    return beta_one(x) + "|b2"
