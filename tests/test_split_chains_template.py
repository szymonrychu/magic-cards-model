"""P0-T05: the Chain/Segment machinery template for F2 (registration).

The template lives under scripts/split/templates/ until F2 copies it to
machines/effects/_chains.py; toy family modules live in
tests/fixtures/split/chains/.
"""

from __future__ import annotations

import pytest
from scripts.split.templates._chains import FORWARD, NO_KWARG, Chain

from tests.fixtures.split.chains import alpha, beta

FAMILIES = ("alpha", "beta")


def make(segments=("s1", "s2")):
    return Chain("toy", segments=segments, arg="text", families=FAMILIES)


def names(fns):
    return [f.__name__ for f in fns]


def test_register_returns_function_unchanged_and_stacks():
    c = make()
    out = c.rung("s1")(c.rung("s2")(alpha.a_first))
    assert out is alpha.a_first
    assert c.segment_rungs("s1") == (alpha.a_first,)
    assert c.segment_rungs("s2") == (alpha.a_first,)


def test_family_then_source_order_regardless_of_registration_order():
    c = make()
    for fn in (beta.b_second, alpha.a_second, beta.b_first, alpha.a_first):
        c.rung("s1")(fn)
    assert names(c.segment_rungs("s1")) == ["a_first", "a_second", "b_first", "b_second"]


def test_family_index_beats_source_line():
    c = Chain("toy", segments=("s1",), arg="text", families=("beta", "alpha"))
    c.rung("s1")(alpha.a_first)
    c.rung("s1")(beta.b_second)
    assert names(c.segment_rungs("s1")) == ["b_second", "a_first"]


def test_unknown_family_raises_at_registration():
    c = Chain("toy", segments=("s1",), arg="text", families=("beta",))
    with pytest.raises(ValueError, match="alpha"):
        c.rung("s1")(alpha.a_first)


def test_unknown_segment_raises():
    c = make()
    with pytest.raises(KeyError, match="nope"):
        c.rung("nope")
    with pytest.raises(KeyError, match="nope"):
        c.run("nope", "x")
    with pytest.raises(KeyError, match="nope"):
        c.segment_rungs("nope")
    with pytest.raises(KeyError, match="nope"):
        c.edges("nope")


def test_run_first_non_none_wins_else_none():
    c = make()
    for fn in (alpha.a_first, alpha.a_second, beta.b_first, beta.b_second):
        c.rung("s1")(fn)
    assert c.run("s1", "both") == "a_second"
    assert c.run("s1", "b2") == "b_second"
    assert c.run("s1", "zzz") is None


def test_before_edge_reorders_stably():
    c = make()
    c.rung("s1")(alpha.a_first)
    c.rung("s1")(alpha.a_second)
    c.rung("s1", before=("a_first",))(beta.b_first)
    c.rung("s1")(beta.b_second)
    assert names(c.segment_rungs("s1")) == ["b_first", "a_first", "a_second", "b_second"]
    assert c.run("s1", "both") == "b_first"


def test_after_edge_reorders_stably():
    c = make()
    c.rung("s1", after=(beta.b_second,))(alpha.a_first)
    c.rung("s1")(alpha.a_second)
    c.rung("s1")(beta.b_first)
    c.rung("s1")(beta.b_second)
    assert names(c.segment_rungs("s1")) == ["b_second", "a_first", "a_second", "b_first"]


def test_edges_returns_explicit_pairs():
    c = make()
    c.rung("s1", before=("a_second",), after=("b_second",))(alpha.a_first)
    c.rung("s1")(alpha.a_second)
    c.rung("s1")(beta.b_second)
    assert set(c.edges("s1")) == {
        ("alpha.a_first", "alpha.a_second"),
        ("beta.b_second", "alpha.a_first"),
    }
    assert c.edges("s2") == ()


def test_cycle_raises_naming_both():
    c = make()
    c.rung("s1", before=("b_first",))(alpha.a_first)
    c.rung("s1", before=("a_first",))(beta.b_first)
    with pytest.raises(ValueError, match=r"cycle.*a_first.*b_first|cycle.*b_first.*a_first"):
        c.segment_rungs("s1")


def test_edge_naming_unknown_rung_raises_with_both_names():
    c = make()
    c.rung("s1", before=("ghost",))(alpha.a_first)
    with pytest.raises(ValueError) as e:
        c.segment_rungs("s1")
    assert "a_first" in str(e.value) and "ghost" in str(e.value)


def test_edge_names_rung_in_other_segment_only_raises():
    c = make()
    c.rung("s2")(beta.b_first)
    c.rung("s1", before=("b_first",))(alpha.a_first)
    with pytest.raises(ValueError, match="b_first"):
        c.segment_rungs("s1")


def test_for_spell_modes():
    c = make()
    c.rung("s1")(alpha.a_spell)  # NO_KWARG: called with value only
    assert c.run("s1", "spell", for_spell=True) == ("a_spell", None)
    c2 = make()
    c2.rung("s1", for_spell=True)(alpha.a_spell)
    assert c2.run("s1", "spell") == ("a_spell", True)
    c3 = make()
    c3.rung("s1", for_spell=False)(alpha.a_spell)
    assert c3.run("s1", "spell", for_spell=True) == ("a_spell", False)
    c4 = make()
    c4.rung("s1", for_spell=FORWARD)(beta.b_spell)
    assert c4.run("s1", "spell", for_spell=True) == ("b_spell", True)
    assert c4.run("s1", "spell", for_spell=False) == ("b_spell", False)
    assert NO_KWARG is not None and NO_KWARG is not FORWARD


def test_no_kwarg_rung_rejects_kwarg_free_signature_misuse():
    c = make()
    c.rung("s1")(beta.b_spell)  # requires for_spell, registered NO_KWARG
    with pytest.raises(TypeError):
        c.run("s1", "spell")


def test_one_function_in_several_segments_and_chains():
    c = make()
    other = Chain("other", segments=("x",), arg="text", families=FAMILIES)
    c.rung("s1")(c.rung("s2", for_spell=True)(alpha.a_spell))
    other.rung("x", for_spell=False)(alpha.a_spell)
    assert c.run("s1", "spell") == ("a_spell", None)
    assert c.run("s2", "spell") == ("a_spell", True)
    assert other.run("x", "spell") == ("a_spell", False)


def test_duplicate_registration_in_one_segment_raises():
    c = make()
    c.rung("s1")(alpha.a_first)
    with pytest.raises(ValueError, match="a_first"):
        c.rung("s1")(alpha.a_first)


def test_cache_invalidated_by_later_registration():
    c = make()
    c.rung("s1")(beta.b_first)
    first = c.segment_rungs("s1")
    assert c.segment_rungs("s1") == first
    c.rung("s1")(alpha.a_first)
    assert names(c.segment_rungs("s1")) == ["a_first", "b_first"]
    assert c.run("s1", "a1") == "a_first"


def test_order_is_lazy_and_cached():
    c = make()
    c.rung("s1")(alpha.a_first)
    assert c._order_cache == {}
    c.segment_rungs("s1")
    cached = c._order_cache["s1"]
    c.segment_rungs("s1")
    assert c._order_cache["s1"] is cached


def test_exceptions_propagate():
    c = make()
    c.rung("s1")(alpha.a_boom)
    c.rung("s1")(beta.b_first)
    with pytest.raises(ValueError, match="alpha exploded"):
        c.run("s1", "boom")
    assert c.run("s1", "b1") == "b_first"
