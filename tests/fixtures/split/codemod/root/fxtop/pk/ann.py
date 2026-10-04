"""Fixture: an unquoted annotation runs at def time, so it is an eager reference."""


class Shape:
    sides = 4


def a_sides(shape: Shape) -> int:
    return shape.sides


def a_quoted(shape: "Shape") -> int:
    return shape.sides
