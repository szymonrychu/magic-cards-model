"""Fixture package ladders: pure rungs, a guard, a rebind, non-standard rungs."""

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
    parse_b_one,
    parse_b_three,
    parse_b_true,
    parse_b_two,
)


def _ability_effect_or_notice(effect_text):
    """Toy ability ladder."""
    from .beta import parse_b_lazy

    if effect_text.startswith("!"):
        return ("guard", effect_text)
    lazy = parse_b_lazy(effect_text)
    if lazy is not None:
        return lazy
    # b_one reads "x" before a_two does
    one = parse_b_one(effect_text)
    if one is not None:
        return one
    two = parse_a_two(effect_text)
    if two is not None:
        return two
    three = parse_a_one(effect_text)
    if three is not None:
        return three
    four = parse_b_two(effect_text)
    if four is not None:
        return four
    effect_text = effect_text.strip()
    five = parse_a_three(effect_text)
    if five is not None:
        return five
    again = parse_a_three(effect_text)
    if again is not None:
        return again
    six = parse_b_three(effect_text)
    if six is not None:
        return six
    seven = parse_b_four(effect_text)
    if seven is not None:
        return seven[0]
    eight = parse_a_four(effect_text)
    if eight is not None:
        return eight
    return None


def _spell_effect_or_notice(effect_text):
    whole = effect_text.strip()
    seg_hit = whole.lower()
    if seg_hit == "":
        return None
    w1 = parse_a_three(whole)
    if w1 is not None:
        return w1
    w2 = parse_b_three(whole)
    if w2 is not None:
        return w2
    e1 = parse_a_four(effect_text)
    if e1 is not None:
        return e1
    return None


def _parse_mixed_clauses(text, *, for_spell):
    f1 = parse_a_fs(text, for_spell=for_spell)
    if f1 is not None:
        return f1
    f2 = parse_b_fs(text, for_spell=for_spell)
    if f2 is not None:
        return f2
    t1 = parse_a_true(text, for_spell=True)
    if t1 is not None:
        return t1
    t2 = parse_b_true(text, for_spell=True)
    if t2 is not None:
        return t2
    g1 = parse_a_false(text, for_spell=False)
    if g1 is not None:
        return g1
    p1 = parse_a_plain(text)
    if p1 is not None:
        return p1
    return None


def _parse_mixed_clause(clause, *, for_spell):
    c1 = parse_a_clause(clause)
    if c1 is not None:
        return c1
    seen = parse_b_clause(clause)
    if seen is not None:
        return seen
    if seen is None and clause == "zz":
        return ("seen-read", clause)
    other = parse_a_plain(clause)
    if other is not None:
        return other
    else:
        return None
