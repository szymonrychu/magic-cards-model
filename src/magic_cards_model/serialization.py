"""Canonical-order serialization for set-typed pydantic fields.

A `set`/`frozenset` has no order, so pydantic's default JSON encoding walks it
in whatever order Python's hash table currently holds it in. For a `set[str]`
(or anything else keyed by string hashing), that order is process-dependent:
`PYTHONHASHSEED` is randomised per process by default, so the same `Game`
dumped from two different processes can produce two different, but equally
valid, JSON arrays for the same field.

That silently broke `tests/scenarios/conftest.py`'s dump/decode/re-dump
round-trip invariant, which asserts byte-identical JSON - not merely
equal-as-sets JSON - across a decode. Confirmed non-hypothetical: with
`PYTHONHASHSEED=17`,
`mise exec -- uv run pytest tests/scenarios/judge/test_judge_transform.py -p no:randomly`
failed with
`$.prevention_shields[0].excluded_source_subtypes[0]: 'Werewolf' != 'Wolf'`
- the same set, dumped twice, in two different orders. `PYTHONHASHSEED=27`
reproduces it too; seeds 1 through 6 happen not to, which is what made the
flake look rare instead of structural (roughly one process in 30 was red).

`SortedSet`/`SortedFrozenSet` fix this at the type: annotate a field with one
of these instead of a bare `set[T]`/`frozenset[T]` and it always serializes
to a list sorted by a stable string key, so the same set always dumps to the
same JSON regardless of hash order - which is also what a recorded, diffable
game log wants independent of the flake. `model_validate` reads the sorted
list straight back into a real `set`/`frozenset`, so the round trip is exact.

Sorting by `str(value)` alone would put an enum member's `repr` in the key;
`getattr(member, "value", member)` reaches through a `StrEnum` (or any enum)
to its actual value first, and falls back to the member itself - covering a
`frozenset[str]`, `frozenset[UUID]`, and `frozenset[SomeStrEnum]` alike with
one function.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from typing import Annotated, Any

from pydantic import PlainSerializer


def _canonical(value: AbstractSet[Any]) -> list[Any]:
    return sorted(value, key=lambda member: str(getattr(member, "value", member)))


type SortedSet[T] = Annotated[set[T], PlainSerializer(_canonical, when_used="always")]
type SortedFrozenSet[T] = Annotated[frozenset[T], PlainSerializer(_canonical, when_used="always")]
