#!/usr/bin/env python
"""Count the ambiguous rung pairs inside the segments of the four dispatch ladders.

    uv run python scripts/split/overlap.py --out overlap.json
        # monolith effects.py: segments from to_registry's finder, families from
        # manifest_lib.resolve (scripts/split/manifest/effects.toml)
    uv run python scripts/split/overlap.py --chains-module <pkg>._chains --out overlap.json
        # post-F2 package: segments from Chain.segment_rungs, edges from Chain.edges

Over the fingerprint corpus (`scripts/dispatch_fingerprint._build_corpus`, every
`for_spell` variant the ladder uses) it runs every rung of every segment on
every input and records each pair (a, b) of one segment that both return a
non-None result on some input. `a` is the rung that runs first today (source
order). Per pair: how many inputs, one example input, and `flips` - whether the
(FAMILIES order, source order) ordering F2 will use would let `b` win where `a`
wins today. An exception counts as "did not match", exactly as in
`dispatch_fingerprint._winner`. Rungs are fed the raw corpus input; ladders that
derive a local first (`whole = strip(effect_text)`) are approximated by it, the
same approximation the fingerprint makes.

Prints the total ambiguous-pair count and the flipping count (design: more than
about 20 ambiguous pairs inside segments means ship F1+F3+F4 only). `--out`
writes the json `to_registry --overlap` reads to emit before/after edges.

Post-F2 the same pairs are reported with `ordered`: whether an explicit
before/after edge (transitively) orders them. `unordered` counts the rest; that
is what `test_dispatch_order.py` fails on.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import importlib
import io
import json
import sys
from collections.abc import Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.dispatch_fingerprint import CHAINS, _build_corpus  # noqa: E402
from scripts.split.manifest_lib import Manifest, load_manifest, resolve  # noqa: E402
from scripts.split.to_registry import LADDERS, find_segments, top_level_defs  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DEFAULT_MODULE = "magic_cards_model.machines.effects"
DEFAULT_SOURCE = REPO / "src" / "magic_cards_model" / "machines" / "effects.py"
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "manifest" / "effects.toml"

_VARIANTS = {entry: (key, variants) for entry, key, variants in CHAINS}


def _invoke(fn, value: str, mode: str, variant):
    if mode == "plain":
        return fn(value)
    if mode == "forward":
        return fn(value, for_spell=variant)
    return fn(value, for_spell=mode == "true")


def _collect(rungs: list, mode: str, values: list[str], variants: tuple) -> dict:
    """(i, j) -> [count, example] for every rung pair matching the same input."""
    runs = variants if mode == "forward" else variants[:1]
    stats: dict[tuple[int, int], list] = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for variant in runs:
            for value in values:
                hits = []
                for i, fn in enumerate(rungs):
                    try:
                        result = _invoke(fn, value, mode, variant)
                    except Exception:  # noqa: BLE001 - "did not match", as in the fingerprint
                        continue
                    if result is not None:
                        hits.append(i)
                for a in range(len(hits)):
                    for b in range(a + 1, len(hits)):
                        entry = stats.setdefault((hits[a], hits[b]), [0, value])
                        entry[0] += 1
    return stats


def ordered_closure(edges: Iterable[tuple[str, str]]) -> set[tuple[str, str]]:
    """Transitive closure of (earlier, later) pairs."""
    after: dict[str, set[str]] = {}
    for a, b in edges:
        after.setdefault(a, set()).add(b)
    closure: set[tuple[str, str]] = set()
    for start in after:
        stack = list(after[start])
        seen: set[str] = set()
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            closure.add((start, node))
            stack.extend(after.get(node, ()))
    return closure


def _summary(ladders: dict) -> dict:
    pairs = [p for lad in ladders.values() for s in lad["segments"].values() for p in s["pairs"]]
    return {
        "total_ambiguous": len(pairs),
        "flipping": sum(1 for p in pairs if p["flips"]),
        "unordered": sum(1 for p in pairs if p.get("ordered") is False),
        "ladders": ladders,
    }


def measure_source(
    source_text: str,
    module,
    defined: Iterable[str],
    corpus: dict[str, list[str]],
    *,
    family_of: dict[str, str] | None = None,
    family_order: list[str] | None = None,
) -> dict:
    """Pre-F2: segments from the finder over `source_text`, rungs from `module`."""
    reports = find_segments(source_text, set(defined))
    tree = ast.parse(source_text)
    line_of = {
        n.name: min([n.lineno, *(d.lineno for d in n.decorator_list)])
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
    }
    order = list(family_order or [])

    def label(name: str) -> str:
        return f"{family_of[name]}.{name}" if family_of and name in family_of else name

    def new_key(name: str) -> tuple[int, int]:
        family = (family_of or {}).get(name)
        return (order.index(family) if family in order else len(order), line_of.get(name, 0))

    ladders: dict = {}
    for ladder in LADDERS:
        report = reports.get(ladder.entry)
        if report is None:
            continue
        key, variants = _VARIANTS[ladder.entry]
        segments: dict = {}
        for seg in report.segments:
            names = [r.name for r in seg.rungs]
            stats = _collect([getattr(module, n) for n in names], seg.mode, corpus[key], variants)
            pairs = []
            for (i, j), (count, example) in sorted(stats.items()):
                pairs.append(
                    {
                        "a": label(names[i]),
                        "b": label(names[j]),
                        "count": count,
                        "example": example,
                        "flips": bool(family_of) and new_key(names[j]) < new_key(names[i]),
                    }
                )
            segments[seg.name] = {
                "local": seg.local,
                "mode": seg.mode,
                "rungs": [label(n) for n in names],
                "pairs": pairs,
            }
        ladders[ladder.entry] = {"chain": ladder.chain_var, "segments": segments}
    return _summary(ladders)


def measure_monolith(
    source: Path, manifest: Manifest, module, corpus: dict[str, list[str]]
) -> dict:
    """Pre-F2 on the monolith: families from `manifest_lib.resolve`."""
    text = Path(source).read_text()
    placement = resolve(text, manifest)
    family_of = {}
    for item in placement.items:
        for name in item.names:
            family_of[name] = item.target
    families = list(dict.fromkeys(manifest.targets))
    return measure_source(
        text,
        module,
        top_level_defs(text),
        corpus,
        family_of=family_of,
        family_order=families,
    )


def _mode_name(mode) -> str:
    if mode is True:
        return "true"
    if mode is False:
        return "false"
    return "forward" if repr(mode) == "FORWARD" else "plain"


def _qualified(fn) -> str:
    return f"{fn.__module__.rsplit('.', 1)[-1]}.{fn.__name__}"


def measure_chains(chains_module, corpus: dict[str, list[str]]) -> dict:
    """Post-F2: segments and edges read from the `Chain` objects of `chains_module`."""
    if isinstance(chains_module, str):
        chains_module = importlib.import_module(chains_module)
    by_name = {
        c.name: c
        for c in vars(chains_module).values()
        if hasattr(c, "segment_rungs") and hasattr(c, "edges") and hasattr(c, "segments")
    }
    ladders: dict = {}
    for ladder in LADDERS:
        chain = by_name.get(ladder.chain_name)
        if chain is None:
            continue
        key, variants = _VARIANTS[ladder.entry]
        segments: dict = {}
        for seg in chain.segments:
            entries = chain._ordered(seg)
            rungs = [fn for fn, _ in entries]
            modes = {_mode_name(m) for _, m in entries}
            names = [_qualified(fn) for fn in rungs]
            closure = ordered_closure(chain.edges(seg))
            pairs = []
            stats = {}
            # a segment holds one mode; fall back to per-rung modes if it is ever mixed
            for mode in sorted(modes):
                sub = [fn for fn, m in entries if _mode_name(m) == mode]
                index = [rungs.index(fn) for fn in sub]
                for (i, j), (count, example) in _collect(sub, mode, corpus[key], variants).items():
                    cur = stats.setdefault((index[i], index[j]), [0, example])
                    cur[0] += count
            for (i, j), (count, example) in sorted(stats.items()):
                pairs.append(
                    {
                        "a": names[i],
                        "b": names[j],
                        "count": count,
                        "example": example,
                        "flips": False,
                        "ordered": (names[i], names[j]) in closure,
                    }
                )
            segments[seg] = {
                "local": chain.arg,
                "mode": next(iter(modes)) if len(modes) == 1 else "mixed",
                "rungs": names,
                "pairs": pairs,
            }
        ladders[ladder.entry] = {"chain": ladder.chain_var, "segments": segments}
    return _summary(ladders)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=None, help="write the json to this path")
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="monolith effects.py")
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--module", default=DEFAULT_MODULE, help="dotted module that defines the rungs")
    p.add_argument("--chains-module", default=None, help="post-F2: dotted path of _chains")
    p.add_argument("--corpus-json", type=Path, default=None, help="corpus override (tests)")
    args = p.parse_args(argv)

    corpus = (
        json.loads(args.corpus_json.read_text())
        if args.corpus_json
        else _build_corpus(importlib.import_module(args.module))
    )
    if args.chains_module:
        result = measure_chains(args.chains_module, corpus)
    else:
        result = measure_monolith(
            args.source, load_manifest(args.manifest), importlib.import_module(args.module), corpus
        )
    for entry, ladder in result["ladders"].items():
        for seg, data in ladder["segments"].items():
            for pair in data["pairs"]:
                flag = " FLIPS" if pair["flips"] else ""
                if "ordered" in pair:
                    flag = " ordered" if pair["ordered"] else " UNORDERED"
                print(
                    f"{entry} {seg}: {pair['a']} / {pair['b']} x{pair['count']} "
                    f"e.g. {pair['example']!r}{flag}"
                )
    print(f"ambiguous pairs: {result['total_ambiguous']}")
    print(f"flipping: {result['flipping']}")
    if args.chains_module:
        print(f"unordered: {result['unordered']}")
    if args.out:
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
