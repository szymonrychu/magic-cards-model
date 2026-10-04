#!/usr/bin/env python
"""Fingerprint which parser wins each dispatch chain, per corpus input.

    uv run python scripts/dispatch_fingerprint.py          # print to stdout
    uv run python scripts/dispatch_fingerprint.py --write  # overwrite the
                                                             # committed baseline
    mise run dispatch:fingerprint                           # same as --write

`mise run dispatch:fingerprint` is the one documented way to regenerate
`tests/dispatch_fingerprint_baseline.json`. It needs re-running once this
branch is merged behind the remaining Reality Fracture branches, whose new
scenarios and cards move both the parsers and the pool this fingerprints.

The engine's coarse-to-fine dispatch chains - `effect_for`/`trigger_effect_
for`/`activated_effect_for`'s own ladders `_ability_effect_or_notice`,
`_spell_effect_or_notice`, `_parse_mixed_clauses` and `_parse_mixed_clause`
- decide correctness by *order*: the first parser in source order to return
a non-None result wins, and nothing downstream of it ever runs (see the
modularization plan, "Is the order really load-bearing?"). Splitting
`effects.py` (S2 onward) moves every one of these functions into new files;
nothing should change about which parser wins for a given input.

`_parse_targeted_clause` and `parse_clause_effect` - the plan's two
"family-internal ladders" - are deliberately *not* fingerprinted as chains
of their own: each is one function whose internal branches are almost all
inline `_SOME_RE.fullmatch(clause)` tests rather than delegation to a
sibling parser function, so there is no cross-function order inside either
of them for a split to disturb (the whole function moves as one atomic
unit). What the split genuinely puts at risk is each one's position as one
competing rung of `_parse_mixed_clause`'s own ladder - and that is exactly
what fingerprinting `_parse_mixed_clause` itself already covers, with
`_parse_targeted_clause` (and, transitively, `parse_clause_effect`)
appearing as one of its recorded winners. A trial fingerprint that treated
`parse_clause_effect`'s own internal calls as competing siblings produced
1690 "<none>" results with no relation to what the function actually
returns - the tell that this granularity is wrong for these two.

This script is the proof. It walks each chain exactly as Python resolves it
today - an AST source-order walk of the calls inside the ladder, the same
technique the split research used to measure it (see the session scratchpad
`overlap.py`/`an2.py`, both reused almost verbatim here) - runs every entry
against every real printing in the pool, and records the *name of the
parser that wins*, or `"<none>"`, for each (chain, for_spell variant, input)
triple. `tests/test_dispatch_fingerprint.py` recomputes this fresh on every
run and fails with a readable diff the moment a split (or an unrelated
change) picks a different winner.

Determinism: the pool is read in sorted file order, every corpus set is
sorted before iterating, the chain walk is ordered by `(lineno,
col_offset)`, and the JSON is dumped with `sort_keys=True` - two runs
against the same commit produce byte-identical output (checked in
`test_dispatch_fingerprint.py`).
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import inspect
import io
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.cards import pool  # noqa: E402

import magic_cards_model.machines.effects as E  # noqa: E402

BASELINE_PATH = Path(__file__).parent.parent / "tests" / "dispatch_fingerprint_baseline.json"

#: The dispatch chains this fingerprints: the two whole-text ladders and the
#: multi-clause and single-clause ladders beneath them - the four places
#: where a *sequence of separately defined sibling functions* is tried in
#: source order (see the module docstring for why the two family-internal
#: ladders are not listed here too).
#:
#: `entry`: the attribute name on `machines.effects` to walk.
#: `corpus`: which corpus set below it runs over.
#: `for_spell_variants`: the `for_spell` values to call it with. `None`
#: means "call chain entries with no `for_spell` kwarg at all" - only
#: entries whose own signature declares the parameter receive it, exactly
#: as `overlap.py`'s probe did.
CHAINS: tuple[tuple[str, str, tuple[bool | None, ...]], ...] = (
    ("_ability_effect_or_notice", "texts", (None,)),
    ("_spell_effect_or_notice", "spells", (None,)),
    ("_parse_mixed_clauses", "texts_and_spells", (False, True)),
    ("_parse_mixed_clause", "clauses", (False, True)),
)


_TREES: dict[str, ast.Module] = {}


def _source_tree(path: str) -> ast.Module:
    """The parsed AST of one source file, cached per file."""
    if path not in _TREES:
        _TREES[path] = ast.parse(Path(path).read_text())
    return _TREES[path]


def _ladder_def(module, entry: str) -> tuple[ast.FunctionDef, dict]:
    """The ladder's top-level def, found by name in the AST of the file that
    defines it (not the module's own file, which is a facade once split), and
    the globals the function resolves its names in."""
    fn = getattr(module, entry)
    tree = _source_tree(inspect.getsourcefile(fn))
    defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    return defs[entry], fn.__globals__


def _chain_calls(module, entry: str) -> list[tuple[str, Callable]]:
    """Every distinct parser the ladder `entry`'s own body calls, in source
    order, as `(name, callable)`. A name counts only when it resolves in the
    ladder function's own globals, and the callable is what those globals bind.
    `NAME.run("<segment>", ...)` where NAME binds an object with
    `segment_rungs(segment)` expands, at that call's position, into the
    segment's rungs in run order."""
    node, namespace = _ladder_def(module, entry)
    pure = _pure_rung_names(node, namespace)
    calls = [c for c in ast.walk(node) if isinstance(c, ast.Call)]
    calls.sort(key=lambda c: (c.lineno, c.col_offset))
    out: list[tuple[str, Callable]] = []
    seen: set[str] = set()

    def add(name: str, fn: Callable) -> None:
        if name not in seen:
            seen.add(name)
            out.append((name, fn))

    for c in calls:
        if isinstance(c.func, ast.Name):
            f = c.func.id
            if ("parse" in f or f.startswith("_resolve") or f in pure) and f in namespace:
                add(f, namespace[f])
        elif _is_chain_run(c, namespace):
            chain = namespace[c.func.value.id]
            for rung in chain.segment_rungs(c.args[0].value):
                add(rung.__name__, rung)
    return out


def _pure_rung_names(node: ast.FunctionDef, namespace: dict) -> set[str]:
    """Names of the ladder's pure rungs (`v = f(x)` then `if v is not None:
    return v`, the shape `scripts/split/to_registry.py` converts), so a rung
    is a chain member whatever it is called."""
    from scripts.split.to_registry import Ladder, _analyze_ladder

    defined = {k for k, v in namespace.items() if inspect.isfunction(v)}
    report = _analyze_ladder(node, Ladder(node.name, "", ""), defined)
    return {r.name for seg in report.segments for r in seg.all_rungs}


def _is_chain_run(call: ast.Call, namespace: dict) -> bool:
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "run"
        and isinstance(func.value, ast.Name)
        and callable(getattr(namespace.get(func.value.id), "segment_rungs", None))
        and bool(call.args)
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    )


def _build_corpus(module=E) -> dict[str, list[str]]:
    """Real oracle text, spell text, and their split clauses, off every
    printing in the pool (`tests.cards.pool()`,
    `src/magic_cards_model/data/printings`) - the same extraction
    `overlap.py` used, against the pydantic `Card`/`CardFace` models rather
    than raw JSON."""
    texts: set[str] = set()
    spells: set[str] = set()
    for card in sorted(pool().values(), key=lambda c: c.name):
        faces = card.card_faces or [card]
        for face in faces:
            oracle_text = getattr(face, "oracle_text", None) or card.oracle_text or ""
            type_line = getattr(face, "type_line", None) or card.type_line
            for line in oracle_text.split("\n"):
                line = re.sub(r"\([^)]*\)", "", line).strip()
                if not line:
                    continue
                if re.match(r"(When|Whenever|At)\b", line) and ", " in line:
                    texts.add(line.split(", ", 1)[1])
                elif ": " in line and not line.startswith("•"):
                    texts.add(line.split(": ", 1)[1])
                elif "Instant" in type_line or "Sorcery" in type_line:
                    spells.add(line)
    clauses: set[str] = set()
    for text in texts | spells:
        with contextlib.suppress(Exception):
            clauses.update(module.split_effect_clauses(text))
    return {
        "texts": sorted(texts),
        "spells": sorted(spells),
        "texts_and_spells": sorted(texts | spells),
        "clauses": sorted(clauses),
    }


def _call(fn, value: str, for_spell: bool | None):
    kwargs = {}
    if for_spell is not None and "for_spell" in inspect.signature(fn).parameters:
        kwargs["for_spell"] = for_spell
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(value, **kwargs)


def _winner(chain: list[tuple[str, Callable]], value: str, for_spell: bool | None) -> str:
    """The first parser in `chain` to return non-`None` for `value`, or
    `"<none>"` - any exception (wrong arity, a lookup the value does not
    satisfy) counts the same as a `None` return, matching `overlap.py`."""
    for name, fn in chain:
        try:
            result = _call(fn, value, for_spell)
        except Exception:  # noqa: BLE001 - "did not match" the same as None
            continue
        if result is not None:
            return name
    return "<none>"


def _variant_key(for_spell: bool | None) -> str:
    if for_spell is None:
        return "plain"
    return "for_spell" if for_spell else "not_for_spell"


def compute_fingerprint(
    *,
    module=E,
    chains: tuple[tuple[str, str, tuple[bool | None, ...]], ...] = CHAINS,
    corpus: dict[str, list[str]] | None = None,
) -> dict:
    if corpus is None:
        corpus = _build_corpus(module)
    fingerprint: dict[str, dict] = {}
    for entry, corpus_key, for_spell_variants in chains:
        chain = _chain_calls(module, entry)
        results: dict[str, dict[str, str]] = {}
        for for_spell in for_spell_variants:
            results[_variant_key(for_spell)] = {
                value: _winner(chain, value, for_spell) for value in corpus[corpus_key]
            }
        fingerprint[entry] = {"chain": [name for name, _ in chain], "results": results}
    return fingerprint


def _dumps(fingerprint: dict) -> str:
    return json.dumps(fingerprint, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    baseline_rel = BASELINE_PATH.relative_to(BASELINE_PATH.parent.parent)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"overwrite {baseline_rel} instead of printing to stdout",
    )
    args = parser.parse_args(argv)
    text = _dumps(compute_fingerprint())
    if args.write:
        BASELINE_PATH.write_text(text)
        print(f"wrote {BASELINE_PATH}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
