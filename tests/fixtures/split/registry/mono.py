"""Fixture toy monolith: alpha, beta and dispatch in one file (pre-F1 shape)."""

from __future__ import annotations


def _tag(fn):
    return fn


def parse_a_one(text):
    return ("a_one", text) if text.startswith("a") else None


def parse_a_two(text):
    return ("a_two", text) if "x" in text else None


def parse_a_three(text):
    return ("a_three", text) if text == "three" else None


@_tag
def parse_a_four(text):
    return ("a_four", text) if text == "four" else None


def parse_a_fs(text, *, for_spell):
    return ("a_fs", text, for_spell) if text == "fs" else None


def parse_a_true(text, *, for_spell):
    return ("a_true", text, for_spell) if text == "ft" else None


def parse_a_false(text, *, for_spell):
    return ("a_false", text, for_spell) if text == "ff" else None


def parse_a_plain(text):
    return ("a_plain", text) if text == "plain" else None


def parse_a_clause(clause):
    return ("a_clause", clause) if clause == "ac" else None


def parse_b_one(text):
    return ("b_one", text) if "x" in text else None


def parse_b_two(text):
    return ("b_two", text) if "b" in text else None


def parse_b_three(text):
    return ("b_three", text) if text == "bthree" else None


def parse_b_four(text):
    return (("b_four", text),) if text == "bfour" else None


def parse_b_lazy(text):
    return ("b_lazy", text) if text == "lazy" else None


def parse_b_fs(text, *, for_spell):
    return ("b_fs", text, for_spell) if text == "bfs" else None


def parse_b_true(text, *, for_spell):
    return ("b_true", text, for_spell) if text == "bt" else None


def parse_b_clause(clause):
    return ("b_clause", clause) if clause == "bc" else None


def _ability_effect_or_notice(effect_text):
    """Toy ability ladder."""
    from .beta import parse_b_lazy  # noqa: F811

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
