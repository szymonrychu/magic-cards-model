"""Fixture post-F1 package: facade over alpha, beta and dispatch."""

from __future__ import annotations

from .alpha import (
    parse_a_clause,
    parse_a_false,
    parse_a_four,
    parse_a_fs,
    parse_a_one,
    parse_a_plain,
    parse_a_three,
    parse_a_true,
    parse_a_two,
)
from .beta import (
    parse_b_clause,
    parse_b_four,
    parse_b_fs,
    parse_b_lazy,
    parse_b_one,
    parse_b_three,
    parse_b_true,
    parse_b_two,
)
from .dispatch import (
    _ability_effect_or_notice,
    _parse_mixed_clause,
    _parse_mixed_clauses,
    _spell_effect_or_notice,
)

__all__ = [
    "_ability_effect_or_notice",
    "_parse_mixed_clause",
    "_parse_mixed_clauses",
    "_spell_effect_or_notice",
    "parse_a_clause",
    "parse_a_false",
    "parse_a_four",
    "parse_a_fs",
    "parse_a_one",
    "parse_a_plain",
    "parse_a_three",
    "parse_a_true",
    "parse_a_two",
    "parse_b_clause",
    "parse_b_four",
    "parse_b_fs",
    "parse_b_lazy",
    "parse_b_one",
    "parse_b_three",
    "parse_b_true",
    "parse_b_two",
]
