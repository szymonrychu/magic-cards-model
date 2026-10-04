"""Fixture: a sibling the old module imports relatively."""

NAME = "N"


class SibT:
    def __str__(self) -> str:
        return "sibt"


def sib() -> str:
    return "S"


def lazy_sib() -> str:
    return "L"
