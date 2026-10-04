"""Segment/Chain machinery for the effects dispatch ladders (F2, registration).

At F2 `scripts/split/to_registry.py` copies this file to
`machines/effects/_chains.py` and appends the generated `Chain` declarations.
Plain module, no framework, modelled on `machines/conditions/__init__.py`
`readers()`.

A `Chain` is one ladder. It is cut into named *segments*, each a run of pure
rungs (`v = f(arg[, for_spell=...])`; `if v is not None: return v`). A family
module registers a parser into a segment with `@chain.rung("segment", ...)`.

Run order inside a segment:

1. family index: the rung's defining module (last dotted component of
   `fn.__module__`) looked up in the chain's `families` manifest; a module not
   in it raises at registration;
2. source order: `fn.__code__.co_firstlineno`;
3. explicit `before=` / `after=` edges, applied as a stable topological sort
   (walk the base order; before placing a rung, place its predecessors, in
   base order, so a rung named by an edge is pulled to just before its first
   successor and nothing else moves). An edge cycle raises.

Only `None` means "did not match"; an exception raised by a rung propagates.
Order is computed lazily, cached per segment, and invalidated by any later
registration into that segment.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


class _Mode:
    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:
        return self._name


NO_KWARG = _Mode("NO_KWARG")  # call rung(value)
FORWARD = _Mode("FORWARD")  # call rung(value, for_spell=<the run's for_spell>)

Rung = Callable[..., Any]
_RungRef = "str | Rung"


def _family_of(fn: Rung) -> str:
    return fn.__module__.rsplit(".", 1)[-1]


def _qualified(fn: Rung) -> str:
    return f"{_family_of(fn)}.{fn.__name__}"


class Chain:
    def __init__(
        self, name: str, *, segments: tuple[str, ...], arg: str, families: tuple[str, ...]
    ) -> None:
        self.name = name
        self.segments = tuple(segments)
        self.arg = arg
        self.families = tuple(families)
        # segment -> [(fn, for_spell mode)]
        self._rungs: dict[str, list[tuple[Rung, Any]]] = {s: [] for s in self.segments}
        # segment -> [(fn, ref, "before"|"after")]
        self._edges: dict[str, list[tuple[Rung, Any, str]]] = {s: [] for s in self.segments}
        self._order_cache: dict[str, tuple[tuple[Rung, Any], ...]] = {}

    def _check_segment(self, segment: str) -> None:
        if segment not in self._rungs:
            raise KeyError(f"chain {self.name!r} has no segment {segment!r}")

    def rung(
        self,
        segment: str,
        *,
        for_spell: Any = NO_KWARG,
        before: Iterable[Any] = (),
        after: Iterable[Any] = (),
    ) -> Callable[[Rung], Rung]:
        self._check_segment(segment)

        def register(fn: Rung) -> Rung:
            family = _family_of(fn)
            if family not in self.families:
                raise ValueError(
                    f"chain {self.name!r}: {fn.__name__} is defined in module {fn.__module__!r}, "
                    f"family {family!r} is not in {self.families}"
                )
            if any(f is fn for f, _ in self._rungs[segment]):
                raise ValueError(
                    f"chain {self.name!r} segment {segment!r}: {fn.__name__} registered twice"
                )
            self._rungs[segment].append((fn, for_spell))
            for ref in before:
                self._edges[segment].append((fn, ref, "before"))
            for ref in after:
                self._edges[segment].append((fn, ref, "after"))
            self._order_cache.pop(segment, None)
            return fn

        return register

    def _resolve(self, segment: str, owner: Rung, ref: Any, fns: list[Rung]) -> Rung:
        if callable(ref):
            for fn in fns:
                if fn is ref:
                    return fn
        else:
            hits = [f for f in fns if ref in (f.__name__, _qualified(f))]
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                raise ValueError(
                    f"chain {self.name!r} segment {segment!r}: edge from {owner.__name__} names "
                    f"{ref!r}, ambiguous between {[_qualified(f) for f in hits]}"
                )
        shown = ref if isinstance(ref, str) else getattr(ref, "__name__", repr(ref))
        raise ValueError(
            f"chain {self.name!r} segment {segment!r}: edge from {owner.__name__} names "
            f"{shown!r}, which is not a rung of the segment"
        )

    def _pairs(self, segment: str) -> list[tuple[Rung, Rung]]:
        fns = [f for f, _ in self._rungs[segment]]
        pairs = []
        for owner, ref, kind in self._edges[segment]:
            other = self._resolve(segment, owner, ref, fns)
            pairs.append((owner, other) if kind == "before" else (other, owner))
        return pairs

    def edges(self, segment: str) -> tuple[tuple[str, str], ...]:
        """Explicit (earlier, later) pairs as 'family.name' strings."""
        self._check_segment(segment)
        return tuple((_qualified(a), _qualified(b)) for a, b in self._pairs(segment))

    def _ordered(self, segment: str) -> tuple[tuple[Rung, Any], ...]:
        cached = self._order_cache.get(segment)
        if cached is not None:
            return cached
        entries = sorted(
            self._rungs[segment],
            key=lambda e: (self.families.index(_family_of(e[0])), e[0].__code__.co_firstlineno),
        )
        preds: dict[int, list[Rung]] = {id(f): [] for f, _ in entries}
        for earlier, later in self._pairs(segment):
            preds[id(later)].append(earlier)
        rank = {id(f): i for i, (f, _) in enumerate(entries)}
        mode = {id(f): m for f, m in entries}
        placed: list[tuple[Rung, Any]] = []
        done: set[int] = set()

        def place(fn: Rung, path: tuple[Rung, ...]) -> None:
            if id(fn) in done:
                return
            if any(p is fn for p in path):
                cycle = " -> ".join(_qualified(p) for p in (*path[path.index(fn) :], fn))
                raise ValueError(
                    f"chain {self.name!r} segment {segment!r}: before/after edge cycle: {cycle}"
                )
            for pred in sorted(preds[id(fn)], key=lambda p: rank[id(p)]):
                place(pred, (*path, fn))
            done.add(id(fn))
            placed.append((fn, mode[id(fn)]))

        for fn, _ in entries:
            place(fn, ())
        result = tuple(placed)
        self._order_cache[segment] = result
        return result

    def segment_rungs(self, segment: str) -> tuple[Rung, ...]:
        self._check_segment(segment)
        return tuple(fn for fn, _ in self._ordered(segment))

    def run(self, segment: str, value: Any, *, for_spell: Any = None) -> Any:
        self._check_segment(segment)
        for fn, mode in self._ordered(segment):
            if mode is NO_KWARG:
                result = fn(value)
            elif mode is FORWARD:
                result = fn(value, for_spell=for_spell)
            else:
                result = fn(value, for_spell=mode)
            if result is not None:
                return result
        return None
