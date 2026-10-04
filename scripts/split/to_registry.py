#!/usr/bin/env python
"""F2 codemod: turn the pure rungs of the four dispatch ladders into registry chains.

    uv run python scripts/split/to_registry.py analyze <effects.py | package_dir> [--defs DIR]
    uv run python scripts/split/to_registry.py <package_dir> --manifest <effects.toml>
        [--overlap overlap.json] [--tests-dir tests]

Segment finder (shared with `overlap.py`). In each of the four ladders
(`LADDERS`), a *pure rung* is exactly

    v = f(<local>)                           or
    v = f(<local>, for_spell=<for_spell | True | False>)
    if v is not None:
        return v                              # no else

with `v` a plain name read nowhere else in the function and `f` a name bound to
a top-level def of the module/package (not a lazily imported name, not bound
anywhere in the function, not the ladder itself). A *segment* is a maximal run
of pure rungs sharing the same local and the same for_spell mode. Anything else
(guards, rebinds, lazy imports, loops, non-standard rungs) stays hand-written
and ends the segment. Segments are named `s1..sN` per ladder in source order.

`convert` rewrites a post-F1 package in place: writes `_chains.py` (the
`templates/_chains.py` machinery + FAMILIES in manifest target order + one
`Chain` per ladder), replaces each segment in `dispatch.py` with
`if (seg_hit := CHAIN.run("sN", <local>[, for_spell=for_spell])) is not None:`,
registers every rung with `@CHAIN.rung("sN"[, for_spell=...][, before=[...]])`
above its def in its family module, prunes dispatch imports it no longer uses,
and copies `templates/test_dispatch_order.py` into the tests directory. A
duplicate call of one function in one segment keeps the first and is reported.
Edges (`before=`) are written exactly for the double-matching pairs of an
`overlap.py --out` file, from the source-order winner to the loser. Nothing is
written if the set of function names any ladder calls would change.

Plain `convert` is meant for the real package once F1 has landed; the manifest
supplies FAMILIES (its `targets` order).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.split.manifest_lib import load_manifest  # noqa: E402

TEMPLATES = Path(__file__).resolve().parent / "templates"
LINE_LENGTH = 100
FRESH_BASE = "seg_hit"
MODES = ("plain", "forward", "true", "false")
#: design table at engine 325bb73a (rungs), for the analyze printout
DESIGN_RUNGS = {
    "_ability_effect_or_notice": 294,
    "_spell_effect_or_notice": 112,
    "_parse_mixed_clauses": 54,
    "_parse_mixed_clause": 172,
}


class RegistryError(ValueError):
    """The codemod refuses: the input is not what it can convert exactly."""


@dataclass(frozen=True)
class Ladder:
    entry: str
    chain_var: str
    chain_name: str


LADDERS: tuple[Ladder, ...] = (
    Ladder("_ability_effect_or_notice", "ABILITY_TEXT", "ability_text"),
    Ladder("_spell_effect_or_notice", "SPELL_TEXT", "spell_text"),
    Ladder("_parse_mixed_clauses", "MIXED_CLAUSES", "mixed_clauses"),
    Ladder("_parse_mixed_clause", "MIXED_CLAUSE", "mixed_clause"),
)


# ------------------------------------------------------------------ segment finder


@dataclass
class PureRung:
    name: str
    var: str
    local: str
    mode: str
    first_line: int  # the `v = f(...)` statement
    last_line: int  # the end of the `if v is not None` statement


@dataclass
class Segment:
    name: str
    local: str
    mode: str
    rungs: list[PureRung] = field(default_factory=list)  # kept (first call of each f)
    duplicates: list[PureRung] = field(default_factory=list)  # later calls of the same f

    @property
    def all_rungs(self) -> list[PureRung]:
        return sorted(self.rungs + self.duplicates, key=lambda r: r.first_line)

    @property
    def first_line(self) -> int:
        return self.all_rungs[0].first_line

    @property
    def last_line(self) -> int:
        return self.all_rungs[-1].last_line


@dataclass
class LadderReport:
    ladder: Ladder
    segments: list[Segment]
    rung_count: int
    other_count: int
    other_kinds: Counter
    node: ast.FunctionDef = field(repr=False)


def _fn_bound_names(fn: ast.FunctionDef) -> set[str]:
    """Names the function itself binds: parameters, stores, imports, nested defs."""
    bound = {a.arg for a in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs)}
    for extra in (fn.args.vararg, fn.args.kwarg):
        if extra is not None:
            bound.add(extra.arg)
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
    return bound


def _is_none_test(test: ast.expr, var: str) -> bool:
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == var
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.IsNot)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value is None
    )


def _mode_of(call: ast.Call) -> str | None:
    if not call.keywords:
        return "plain"
    if len(call.keywords) != 1 or call.keywords[0].arg != "for_spell":
        return None
    value = call.keywords[0].value
    if isinstance(value, ast.Name) and value.id == "for_spell":
        return "forward"
    if isinstance(value, ast.Constant) and isinstance(value.value, bool):
        return "true" if value.value else "false"
    return None


def _match_rung(
    first: ast.stmt,
    second: ast.stmt,
    *,
    defined: set[str],
    entry: str,
    bound: set[str],
    occurrences: Counter,
) -> PureRung | None:
    if not (
        isinstance(first, ast.Assign)
        and len(first.targets) == 1
        and isinstance(first.targets[0], ast.Name)
        and isinstance(first.value, ast.Call)
        and isinstance(first.value.func, ast.Name)
    ):
        return None
    var = first.targets[0].id
    call = first.value
    f = call.func.id
    if f not in defined or f == entry or f in bound:
        return None
    if len(call.args) != 1 or not isinstance(call.args[0], ast.Name):
        return None
    mode = _mode_of(call)
    if mode is None:
        return None
    if not (
        isinstance(second, ast.If)
        and not second.orelse
        and _is_none_test(second.test, var)
        and len(second.body) == 1
        and isinstance(second.body[0], ast.Return)
        and isinstance(second.body[0].value, ast.Name)
        and second.body[0].value.id == var
    ):
        return None
    if occurrences[var] != 3:  # the store, the `is not None` read, the return
        return None
    return PureRung(
        name=f,
        var=var,
        local=call.args[0].id,
        mode=mode,
        first_line=first.lineno,
        last_line=second.end_lineno or second.lineno,
    )


def _other_kind(stmt: ast.stmt) -> str:
    return "Import" if isinstance(stmt, (ast.Import, ast.ImportFrom)) else type(stmt).__name__


def _analyze_ladder(fn: ast.FunctionDef, ladder: Ladder, defined: set[str]) -> LadderReport:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # docstring
    bound = _fn_bound_names(fn)
    occurrences = Counter(n.id for n in ast.walk(fn) if isinstance(n, ast.Name))
    segments: list[Segment] = []
    current: Segment | None = None
    other: Counter = Counter()
    rungs = 0
    i = 0
    while i < len(body):
        rung = (
            _match_rung(
                body[i],
                body[i + 1],
                defined=defined,
                entry=ladder.entry,
                bound=bound,
                occurrences=occurrences,
            )
            if i + 1 < len(body)
            else None
        )
        if rung is None:
            other[_other_kind(body[i])] += 1
            current = None
            i += 1
            continue
        rungs += 1
        if current is None or (current.local, current.mode) != (rung.local, rung.mode):
            current = Segment(f"s{len(segments) + 1}", rung.local, rung.mode)
            segments.append(current)
        if any(r.name == rung.name for r in current.rungs):
            current.duplicates.append(rung)
        else:
            current.rungs.append(rung)
        i += 2
    return LadderReport(ladder, segments, rungs, sum(other.values()), other, fn)


def find_segments(
    source: str, defined: set[str], ladders: tuple[Ladder, ...] = LADDERS
) -> dict[str, LadderReport]:
    """Segment every ladder of `ladders` that `source` defines at top level."""
    tree = ast.parse(source)
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    return {
        ladder.entry: _analyze_ladder(fns[ladder.entry], ladder, defined)
        for ladder in ladders
        if ladder.entry in fns
    }


def fingerprint_hidden(report: LadderReport) -> list[str]:
    """Rung names `dispatch_fingerprint._chain_calls` cannot see (no 'parse', no '_resolve')."""
    names = {r.name for s in report.segments for r in s.rungs}
    return sorted(n for n in names if not ("parse" in n or n.startswith("_resolve")))


def top_level_defs(source: str) -> set[str]:
    return {n.name for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}


def package_modules(package: Path) -> dict[str, Path]:
    return {
        p.stem: p for p in sorted(package.glob("*.py")) if p.stem not in ("__init__", "_chains")
    }


def package_defs(package: Path) -> dict[str, list[str]]:
    """name -> modules (stems) defining it at top level, across the package."""
    out: dict[str, list[str]] = {}
    for stem, path in package_modules(package).items():
        for name in top_level_defs(path.read_text()):
            out.setdefault(name, []).append(stem)
    return out


# ------------------------------------------------------------------ rendering helpers


def _wrap(head: str, parts: list[str], tail: str, indent: str = "") -> str:
    """`head(parts)tail` on one line if it fits, else one part per line."""
    one = f"{indent}{head}({', '.join(parts)}){tail}"
    if len(one) <= LINE_LENGTH:
        return one
    inner = "".join(f"{indent}    {p},\n" for p in parts)
    return f"{indent}{head}(\n{inner}{indent}){tail}"


def _import_stmt(module: str, names: list[str]) -> str:
    one = f"from {module} import {', '.join(names)}"
    if len(one) <= LINE_LENGTH:
        return one
    return f"from {module} import (\n" + "".join(f"    {n},\n" for n in names) + ")"


def _sort_names(names: set[str]) -> list[str]:
    """ruff isort order: CONSTANTS, Classes, then everything else, each sorted."""

    def key(n: str) -> tuple[int, str]:
        if n.isupper() or (n.replace("_", "").isupper() and n.isidentifier()):
            return (0, n)
        if n[:1].isupper():
            return (1, n)
        return (2, n)

    return sorted(names, key=key)


def _fresh_name(fn: ast.FunctionDef) -> str:
    used = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)} | _fn_bound_names(fn)
    candidate, n = FRESH_BASE, 1
    while candidate in used:
        n += 1
        candidate = f"{FRESH_BASE}_{n}"
    return candidate


def _run_lines(chain_var: str, seg: Segment, fresh: str, indent: str) -> list[str]:
    args = [f'"{seg.name}"', seg.local]
    if seg.mode == "forward":
        args.append("for_spell=for_spell")
    call = f"{chain_var}.run({', '.join(args)})"
    head = f"{indent}if ({fresh} := {call}) is not None:"
    if len(head) > LINE_LENGTH:
        head = f"{indent}if (\n{indent}    {fresh} := {call}\n{indent}) is not None:"
    return [*head.split("\n"), f"{indent}    return {fresh}"]


def _span_comments(lines: list[str], seg: Segment) -> list[str]:
    """Comment-only lines inside the segment's span that no statement covers."""
    covered: set[int] = set()
    for r in seg.all_rungs:
        covered.update(range(r.first_line, r.last_line + 1))
    out = []
    for no in range(seg.first_line, seg.last_line + 1):
        text = lines[no - 1].strip()
        if no not in covered and text.startswith("#"):
            out.append(text)
    return out


def _call_names(fn_node: ast.AST, namespace: set[str]) -> tuple[set[str], list[tuple[str, str]]]:
    """Names of module-level functions the ladder calls, plus its `CHAIN.run("seg")` calls."""
    names: set[str] = set()
    runs: list[tuple[str, str]] = []
    for node in ast.walk(fn_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in namespace:
            names.add(func.id)
        elif (
            isinstance(func, ast.Attribute)
            and func.attr == "run"
            and isinstance(func.value, ast.Name)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            runs.append((func.value.id, node.args[0].value))
    return names, runs


def _module_namespace(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        else:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    out.add(sub.id)
    return out


def _render_ladder(
    lines: list[str], report: LadderReport, namespace: set[str]
) -> tuple[str, set[str]]:
    """The ladder's new source text, and the set of function names the new
    ladder calls (hand-written calls plus every rung its `run` calls expand to)."""
    fn = report.node
    start = min([fn.lineno, *(d.lineno for d in fn.decorator_list)])
    end = fn.end_lineno or fn.lineno
    indent = " " * fn.body[0].col_offset
    fresh = _fresh_name(fn)
    new: list[str] = []
    cursor = start
    for seg in report.segments:
        new.extend(lines[cursor - 1 : seg.first_line - 1])
        new.extend(f"{indent}{c}" for c in _span_comments(lines, seg))
        new.extend(_run_lines(report.ladder.chain_var, seg, fresh, indent))
        cursor = seg.last_line + 1
    new.extend(lines[cursor - 1 : end])
    text = "\n".join(new)
    names, runs = _call_names(ast.parse(text), namespace)
    expansion = {
        (report.ladder.chain_var, seg.name): [r.name for r in seg.rungs] for seg in report.segments
    }
    for key in runs:
        names.update(expansion.get(key, ()))
    return text, names


# ------------------------------------------------------------------ module edits


@dataclass
class Edit:
    start: int  # 1-based first line replaced (or the line inserted before when end < start)
    end: int
    lines: list[str]


def _apply(source: str, edits: list[Edit]) -> str:
    lines = source.split("\n")
    for e in sorted(edits, key=lambda e: (e.start, e.end), reverse=True):
        lines[e.start - 1 : e.end] = e.lines
    return "\n".join(lines)


def _bind_chain_import(source: str, names: set[str]) -> str:
    """Add `from ._chains import <names>` to `source` in isort position."""
    if not names:
        return source
    tree = ast.parse(source)
    stmt = _import_stmt("._chains", _sort_names(names)).split("\n")
    relative = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.level == 1 and n.module]
    if relative:
        later = [n for n in relative if n.module > "_chains"]
        if later:
            return _apply(source, [Edit(later[0].lineno, later[0].lineno - 1, stmt)])
        last = relative[-1]
        return _apply(
            source,
            [Edit((last.end_lineno or last.lineno) + 1, (last.end_lineno or last.lineno), stmt)],
        )
    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    if imports:
        last = imports[-1]
        at = (last.end_lineno or last.lineno) + 1
        return _apply(source, [Edit(at, at - 1, ["", *stmt])])
    first = tree.body[0] if tree.body else None
    at = 1
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
        at = (first.end_lineno or first.lineno) + 1
    return _apply(source, [Edit(at, at - 1, ["", *stmt])])


def _prune_imports(source: str, candidates: set[str]) -> str:
    """Drop `candidates` from module-level relative imports when nothing reads them."""
    tree = ast.parse(source)
    loaded = {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }
    exported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            exported |= {
                c.value
                for c in ast.walk(node.value)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
            }
    edits: list[Edit] = []
    for node in tree.body:
        if not (isinstance(node, ast.ImportFrom) and node.level >= 1):
            continue
        keep = [
            a
            for a in node.names
            if not (a.name in candidates and (a.asname or a.name) not in loaded | exported)
        ]
        if len(keep) == len(node.names):
            continue
        end = node.end_lineno or node.lineno
        if not keep:
            # also swallow one following blank line so the block does not gain a gap
            lines = source.split("\n")
            if (
                end < len(lines)
                and lines[end].strip() == ""
                and (node.lineno == 1 or lines[node.lineno - 2].strip() == "")
            ):
                end += 1
            edits.append(Edit(node.lineno, end, []))
            continue
        rendered = [f"{a.name} as {a.asname}" if a.asname else a.name for a in keep]
        module = "." * node.level + (node.module or "")
        edits.append(Edit(node.lineno, end, _import_stmt(module, rendered).split("\n")))
    return _apply(source, edits) if edits else source


# ------------------------------------------------------------------ the codemod


@dataclass
class Report:
    duplicates: list[tuple[str, str, str]] = field(default_factory=list)
    edges: list[tuple[str, str, str, str]] = field(default_factory=list)
    name_sets_equal: bool = True
    hidden: dict[str, list[str]] = field(default_factory=dict)
    segments: dict[str, int] = field(default_factory=dict)
    written: list[Path] = field(default_factory=list)


def _qualified(family: str, name: str) -> str:
    return f"{family}.{name}"


def _load_edges(
    overlap_path: Path | None,
    reports: dict[str, LadderReport],
    owner_of: dict[str, str],
) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """(entry, segment) -> [(earlier qualified, later qualified)], from overlap.py's json."""
    if overlap_path is None:
        return {}
    data = json.loads(overlap_path.read_text())
    out: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for entry, ladder in data.get("ladders", {}).items():
        if entry not in reports:
            raise RegistryError(f"overlap json names ladder {entry!r} not found in dispatch.py")
        segs = {s.name: s for s in reports[entry].segments}
        for seg_name, seg in ladder.get("segments", {}).items():
            if seg_name not in segs:
                raise RegistryError(f"overlap json: {entry} has no segment {seg_name!r} here")
            mine = {_qualified(owner_of[r.name], r.name) for r in segs[seg_name].rungs}
            for pair in seg.get("pairs", []):
                if pair["a"] not in mine or pair["b"] not in mine:
                    raise RegistryError(
                        f"overlap json pair {pair['a']} / {pair['b']} is not a rung pair of "
                        f"{entry} {seg_name}: it was measured on different source"
                    )
                out.setdefault((entry, seg_name), []).append((pair["a"], pair["b"]))
    return out


def _chains_source(
    families: list[str], reports: dict[str, LadderReport], first_params: dict[str, str]
) -> str:
    template = (TEMPLATES / "_chains.py").read_text()
    out = [template.rstrip("\n"), "", "", _families_line(families)]
    for entry, report in reports.items():
        segs = [f'"{s.name}"' for s in report.segments]
        out.append("")
        out.append(_chain_decl(report.ladder, segs, first_params[entry]))
    return "\n".join(out) + "\n"


def _families_line(families: list[str]) -> str:
    items = [f'"{f}"' for f in families]
    trailing = "," if len(items) == 1 else ""
    one = f"FAMILIES = ({', '.join(items)}{trailing})"
    if len(one) <= LINE_LENGTH:
        return one
    return "FAMILIES = (\n" + "".join(f"    {i},\n" for i in items) + ")"


def _chain_decl(ladder: Ladder, segs: list[str], arg: str) -> str:
    trailing = "," if len(segs) == 1 else ""
    seg_tuple = f"({', '.join(segs)}{trailing})"
    one = (
        f'{ladder.chain_var} = Chain("{ladder.chain_name}", segments={seg_tuple}, '
        f'arg="{arg}", families=FAMILIES)'
    )
    if len(one) <= LINE_LENGTH:
        return one
    if len(f"    segments={seg_tuple},") > LINE_LENGTH:
        seg_tuple = "(\n" + "".join(f"        {s},\n" for s in segs) + "    )"
    return (
        f'{ladder.chain_var} = Chain(\n    "{ladder.chain_name}",\n    segments={seg_tuple},\n'
        f'    arg="{arg}",\n    families=FAMILIES,\n)'
    )


def _decorator(ladder: Ladder, seg: Segment, before: list[str]) -> tuple[str, bool]:
    parts = [f'"{seg.name}"']
    forward = False
    if seg.mode == "forward":
        parts.append("for_spell=FORWARD")
        forward = True
    elif seg.mode in ("true", "false"):
        parts.append(f"for_spell={seg.mode == 'true'}")
    if before:
        parts.append("before=[" + ", ".join(f'"{b}"' for b in before) + "]")
    return _wrap(f"@{ladder.chain_var}.rung", parts, ""), forward


def convert(
    package_dir: Path,
    manifest_path: Path,
    *,
    overlap_path: Path | None = None,
    tests_dir: Path | None = None,
) -> Report:
    package_dir = Path(package_dir)
    dispatch_path = package_dir / "dispatch.py"
    if not dispatch_path.is_file():
        raise RegistryError(f"{dispatch_path} not found: run F1 first")
    if (package_dir / "_chains.py").exists():
        raise RegistryError(f"{package_dir} already has _chains.py: registration already done")
    manifest = load_manifest(manifest_path)
    families = list(dict.fromkeys(manifest.targets))

    modules = package_modules(package_dir)
    sources = {stem: path.read_text() for stem, path in modules.items()}
    defs = package_defs(package_dir)
    dispatch_src = sources["dispatch"]
    reports = find_segments(dispatch_src, set(defs))
    if not reports:
        raise RegistryError("no ladder found in dispatch.py")

    owner_of: dict[str, str] = {}
    for report in reports.values():
        for seg in report.segments:
            for r in (*seg.rungs, *seg.duplicates):
                owners = defs[r.name]
                if len(owners) != 1:
                    raise RegistryError(f"rung {r.name} is defined in several modules: {owners}")
                owner_of[r.name] = owners[0]
    for stem in sorted(set(owner_of.values())):
        if stem not in families:
            families.append(stem)

    dispatch_tree = ast.parse(dispatch_src)
    namespace = _module_namespace(dispatch_tree)
    clash = {r.ladder.chain_var for r in reports.values()} & (
        set().union(*(_module_namespace(ast.parse(s)) for s in sources.values()))
    )
    if clash:
        raise RegistryError(f"chain names already bound in the package: {sorted(clash)}")

    edges = _load_edges(overlap_path, reports, owner_of)
    report_out = Report()
    dispatch_lines = dispatch_src.split("\n")

    # ladders: new text, and the name-set check before anything is written
    ladder_edits: list[Edit] = []
    for entry, rep in reports.items():
        pre, _ = _call_names(rep.node, namespace)
        text, post = _render_ladder(dispatch_lines, rep, namespace)
        report_out.segments[entry] = len(rep.segments)
        if pre != post:
            gone, new = sorted(pre - post), sorted(post - pre)
            raise RegistryError(
                f"{entry}: ladder rung name set would differ (dropped {gone}, added {new}); "
                "nothing written"
            )
        hidden = fingerprint_hidden(rep)
        if hidden:
            report_out.hidden[entry] = hidden
        start = min([rep.node.lineno, *(d.lineno for d in rep.node.decorator_list)])
        ladder_edits.append(Edit(start, rep.node.end_lineno or rep.node.lineno, text.split("\n")))
        for seg in rep.segments:
            for dup in seg.duplicates:
                report_out.duplicates.append((entry, seg.name, dup.name))

    # decorators, per family module
    decorators: dict[str, dict[str, list[tuple[int, int, str]]]] = {}
    chain_names: dict[str, set[str]] = {}
    for ladder_index, (entry, rep) in enumerate(reports.items()):
        for seg_index, seg in enumerate(rep.segments):
            pairs = edges.get((entry, seg.name), [])
            for r in seg.rungs:
                me = _qualified(owner_of[r.name], r.name)
                before = [b for a, b in pairs if a == me]
                order = {_qualified(owner_of[x.name], x.name): i for i, x in enumerate(seg.rungs)}
                before.sort(key=lambda b: order[b])
                for b in before:
                    report_out.edges.append((entry, seg.name, me, b))
                text, forward = _decorator(rep.ladder, seg, before)
                stem = owner_of[r.name]
                decorators.setdefault(stem, {}).setdefault(r.name, []).append(
                    (ladder_index, seg_index, text)
                )
                used = chain_names.setdefault(stem, set())
                used.add(rep.ladder.chain_var)
                if forward:
                    used.add("FORWARD")
    report_out.edges.sort(
        key=lambda e: (
            [x.ladder.entry for x in reports.values()].index(e[0]),
            int(e[1][1:]),
        )
    )

    new_sources: dict[str, str] = {}
    for stem, src in sources.items():
        edits: list[Edit] = []
        if stem == "dispatch":
            edits.extend(ladder_edits)
        if stem in decorators:
            tree = ast.parse(src)
            by_name = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
            for name, items in decorators[stem].items():
                node = by_name[name]
                first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
                items.sort()
                edits.append(Edit(first, first - 1, [text for _, _, text in items]))
        new = _apply(src, edits) if edits else src
        if stem == "dispatch":
            removed = {
                r.name for rep in reports.values() for s in rep.segments for r in s.all_rungs
            }
            new = _prune_imports(new, removed)
            used = {r.ladder.chain_var for r in reports.values() if r.segments}
            used |= chain_names.get("dispatch", set())
            new = _bind_chain_import(new, used)
        elif stem in chain_names:
            new = _bind_chain_import(new, chain_names[stem])
        ast.parse(new)
        new_sources[stem] = new

    params = {
        entry: rep.node.args.args[0].arg for entry, rep in reports.items() if rep.node.args.args
    }
    chains_text = _chains_source(families, reports, params)
    ast.parse(chains_text)

    # all checks passed: write
    for stem, new in new_sources.items():
        if new != sources[stem]:
            modules[stem].write_text(new)
            report_out.written.append(modules[stem])
    (package_dir / "_chains.py").write_text(chains_text)
    report_out.written.append(package_dir / "_chains.py")
    tests_dir = tests_dir if tests_dir is not None else _default_tests_dir(package_dir)
    tests_dir.mkdir(parents=True, exist_ok=True)
    order_test = tests_dir / "test_dispatch_order.py"
    order_test.write_text((TEMPLATES / "test_dispatch_order.py").read_text())
    report_out.written.append(order_test)
    return report_out


def _default_tests_dir(package_dir: Path) -> Path:
    for parent in package_dir.resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent / "tests"
    raise RegistryError("no pyproject.toml above the package: pass --tests-dir")


# ------------------------------------------------------------------ CLI


def analyze(path: Path, defs_dir: Path | None) -> str:
    if path.is_dir():
        defs_dir, path = path, path / "dispatch.py"
    source = path.read_text()
    defined = set(package_defs(defs_dir)) if defs_dir is not None else top_level_defs(source)
    out = [f"{'ladder':<28}{'rungs':>7}{'segments':>10}{'other':>7}   other statements"]
    for entry, rep in find_segments(source, defined).items():
        kinds = ", ".join(f"{n} {k}" for k, n in sorted(rep.other_kinds.items()))
        design = DESIGN_RUNGS.get(entry)
        note = f"  [design 325bb73a: {design} rungs]" if design else ""
        out.append(
            f"{entry:<28}{rep.rung_count:>7}{len(rep.segments):>10}{rep.other_count:>7}   "
            f"{kinds}{note}"
        )
        hidden = fingerprint_hidden(rep)
        if hidden:
            out.append(f"{'':<28}fingerprint name filter cannot see: {', '.join(hidden)}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "analyze":
        p = argparse.ArgumentParser(prog="to_registry analyze")
        p.add_argument("path", type=Path)
        p.add_argument("--defs", type=Path, default=None, help="package dir whose defs bind rungs")
        args = p.parse_args(argv[1:])
        print(analyze(args.path, args.defs))
        return 0
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("package_dir", type=Path)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--overlap", type=Path, default=None)
    p.add_argument("--tests-dir", type=Path, default=None)
    args = p.parse_args(argv)
    try:
        report = convert(
            args.package_dir, args.manifest, overlap_path=args.overlap, tests_dir=args.tests_dir
        )
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for entry, n in report.segments.items():
        print(f"{entry}: {n} segments")
    for entry, seg, name in report.duplicates:
        print(f"duplicate call kept first, dropped later one: {entry} {seg} {name}")
    for entry, seg, a, b in report.edges:
        print(f"edge {entry} {seg}: {a} before {b}")
    for entry, names in report.hidden.items():
        print(
            f"warning: {entry}: dispatch_fingerprint's name filter will show {names} "
            "once these are registered"
        )
    print(f"wrote {len(report.written)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
