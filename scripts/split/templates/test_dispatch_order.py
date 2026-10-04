"""Guard for the dispatch ladders' registry order (the split design's 'Failure mode').

F2 turned each run of pure parser rungs in the four ladders of `machines/effects`
into a named segment of a `Chain` (`machines/effects/_chains.py`). Inside a
segment the order is (family order, source order) plus explicit `before=` /
`after=` edges, no longer "where the author put it". A parser added in an
earlier family can therefore quietly win against a later family's parser on an
input where both match.

This test runs every rung of every segment of every `Chain` over the fingerprint
corpus (`scripts/dispatch_fingerprint._build_corpus`, every `for_spell` variant
the ladder uses) and fails, listing each double-matching pair that no explicit
edge (transitively) orders. Fix a failure by adding `before=` / `after=` to one
of the two rungs' `@CHAIN.rung(...)` decorators, never by editing this test. It
runs on every later suite as the guard for that failure mode. Deterministic: the
corpus is sorted and the output is sorted.

`scripts/split/to_registry.py` copies this file to `tests/test_dispatch_order.py`
at F2. `CHAINS_MODULE` and `build_corpus` are module-level names so the template
can be exercised against a fixture package before it lands.
"""

from __future__ import annotations

import importlib

from scripts.dispatch_fingerprint import _build_corpus
from scripts.split.overlap import measure_chains

CHAINS_MODULE = "magic_cards_model.machines.effects._chains"


def build_corpus() -> dict[str, list[str]]:
    return _build_corpus()


def unordered_double_matches(chains_module: str, corpus: dict[str, list[str]]) -> list[str]:
    """One line per double-matching pair in one segment that no explicit edge orders."""
    result = measure_chains(importlib.import_module(chains_module), corpus)
    lines = []
    for entry, ladder in sorted(result["ladders"].items()):
        for segment, data in sorted(ladder["segments"].items()):
            for pair in data["pairs"]:
                if not pair["ordered"]:
                    lines.append(
                        f"{ladder['chain']}.{segment} ({entry}): {pair['a']} and {pair['b']} both "
                        f"match {pair['count']} input(s), e.g. {pair['example']!r}; add "
                        f"before=/after= to one of the two rungs"
                    )
    return sorted(lines)


def test_no_unordered_double_matches():
    found = unordered_double_matches(CHAINS_MODULE, build_corpus())
    assert not found, "unordered double matches inside registry segments:\n" + "\n".join(found)
