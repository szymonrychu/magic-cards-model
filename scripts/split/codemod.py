#!/usr/bin/env python
"""Manifest-driven, byte-preserving split of one engine module into a package.

    uv run python scripts/split/codemod.py <manifest.toml> [--out <dir>] [--check]
                                           [--surface <snapshot.json>]

The manifest (format and resolver: `scripts/split/manifest_lib.py`) says where every
top-level statement goes; nothing is edited by hand afterwards.

Module mode.  Every top-level statement is sliced by its AST line range (decorators
and the contiguous leading comment block included) and written, in original relative
order, to its target module.  Each target gets a copy of the old import block
(relative imports one level deeper, pruned with ruff F401, sorted with ruff I),
plus `from .<target> import ...` for every name it uses from another target: EAGER
references (decorators, defaults, class bodies, module-level expressions, and the
function annotations of a module without `from __future__ import annotations`) at the
top, DEFERRED ones (function bodies, quoted or future-deferred annotations) in one
block at the bottom marked `# noqa: E402`.  Lazy and TYPE_CHECKING relative imports
go one level deeper; no other byte of a statement changes.  `__init__.py` is a
generated facade: explicit `from .<target> import a, b` for every old top-level name
(privates included), `__all__` listing exactly the defined names, old imported names
the surface snapshot lists re-exported as `from <origin> import X as X`, and the
family modules imported in a topological order of the eager graph.

Class mode (`Game`).  `__init__.py` holds `class Game(<mixins in manifest order>,
<old bases>)` with the fields, validators, pydantic-decorated members and `stay`
members; every other method moves, byte for byte, into `class <Name>Mixin:` in its
target module, whose unannotated `self` becomes `self: "Game"` (with
`if TYPE_CHECKING: from . import Game`).  Module-level classes go to the manifest's
`records` target.

The codemod refuses to write anything (exit 1) when the eager graph between the new
modules has a cycle: the fix is a manifest change.  An always-on verify step re-parses
the output and asserts every moved statement equals its original slice.  `--check`
writes to a temp dir, imports the result in a subprocess and verifies, touching
nothing.  `--out` writes the package contents into <dir> and keeps the old module.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import importlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

try:
    from scripts.split import manifest_lib as ml
    from scripts.split import surface as surf
except ImportError:  # run as a script: scripts/split is sys.path[0]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    ml = importlib.import_module("manifest_lib")
    surf = importlib.import_module("surface")

REPO_ROOT = Path(__file__).resolve().parents[2]
INIT = ml.STAY
MARKER = "# __CODEMOD_REEXPORTS__"
_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)


class CodemodError(Exception):
    """The codemod cannot produce a correct split from this manifest and source."""


class CycleError(CodemodError):
    """The eager import graph between the new modules has a cycle."""


class VerifyError(CodemodError):
    """An output statement does not equal its original slice."""


# ------------------------------------------------------------------- text edits


def _apply_edits(lines: list[str], edits: list[tuple[int, int, int, str]]) -> list[str]:
    """Apply (lineno, byte col, delete length, insert) edits, right to left."""
    out = list(lines)
    for lineno, col, drop, ins in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        raw = out[lineno - 1].encode()
        out[lineno - 1] = (raw[:col] + ins.encode() + raw[col + drop :]).decode()
    return out


def _dots_col(lines: list[str], node: ast.ImportFrom) -> int:
    raw = lines[node.lineno - 1].encode()[node.col_offset :]
    found = re.match(rb"from\s+(\.+)", raw)
    if not found:
        raise CodemodError(f"line {node.lineno}: cannot locate the relative import dots")
    return node.col_offset + found.start(1)


def _relative_imports(tree: ast.AST) -> list[ast.ImportFrom]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level > 0]


# ---------------------------------------------------------------- statement slicing


@dataclass
class Geo:
    """Line geometry of a run of sibling statements."""

    lo: list[int]
    hi: list[int]
    trivia: list[list[str]]
    blank: list[int]
    tail: list[str]


def _geometry(lines: list[str], nodes: list[ast.stmt], floor: int, ceiling: int) -> Geo:
    geo = Geo([], [], [], [], [])
    for i, node in enumerate(nodes):
        lo, hi = ml._start(node), node.end_lineno or node.lineno
        prev = floor if i == 0 else geo.hi[-1]
        if i > 0 and lo <= prev:
            raise CodemodError(f"line {lo}: several statements share a line; split them first")
        raw = lines[prev : lo - 1]
        skip = 0
        while skip < len(raw) and not raw[skip].strip():
            skip += 1
        geo.lo.append(lo)
        geo.hi.append(hi)
        geo.trivia.append(raw[skip:])
        geo.blank.append(skip)
    if nodes:
        tail = lines[geo.hi[-1] : ceiling]
        while tail and not tail[-1].strip():
            tail.pop()
        geo.tail = tail
    return geo


def _chunk_text(lines: list[str], geo: Geo, i: int) -> str:
    """One statement with its leading comments, from the (edited) source lines."""
    last = i == len(geo.lo) - 1
    body = geo.trivia[i] + lines[geo.lo[i] - 1 : geo.hi[i]] + (geo.tail if last else [])
    return "\n".join(body)


def _join(chunks: list[tuple[int, str]], geo: Geo, default: str) -> str:
    """Join chunks: a gap kept as in the source for neighbours, `default` otherwise."""
    out = ""
    for k, (idx, text) in enumerate(chunks):
        if k:
            adjacent = idx == chunks[k - 1][0] + 1
            out += "\n" * (geo.blank[idx] + 1) if adjacent else default
        out += text
    return out


def _contiguous_comments(lines: list[str], lo: int, floor: int) -> list[str]:
    start = lo - 1
    while start > floor and lines[start - 1].lstrip().startswith("#"):
        start -= 1
    return lines[start : lo - 1]


def _statement_texts(lines: list[str], nodes: list[ast.stmt]) -> list[str]:
    """Each statement with its contiguous leading comment block (the verified slice)."""
    out: list[str] = []
    floor = 0
    for node in nodes:
        lo, hi = ml._start(node), node.end_lineno or node.lineno
        out.append("\n".join([*_contiguous_comments(lines, lo, floor), *lines[lo - 1 : hi]]))
        floor = hi
    return out


# --------------------------------------------------------------------- the source


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_type_checking_imports(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.If)
        and surf._is_type_checking(node.test)
        and not node.orelse
        and all(isinstance(n, (ast.Import, ast.ImportFrom)) for n in node.body)
    )


def _is_import_stmt(node: ast.stmt) -> bool:
    return isinstance(node, (ast.Import, ast.ImportFrom)) or _is_type_checking_imports(node)


def _collect_imports(body: list[ast.stmt], out: dict[str, str]) -> None:
    """name -> an `X as X` re-export line from its (one level deeper) origin."""
    for node in body:
        if isinstance(node, ast.ImportFrom) and node.module != "__future__":
            mod = ("." * (node.level + 1) if node.level else "") + (node.module or "")
            for a in node.names:
                if a.name == "*":
                    continue
                bound = a.asname or a.name
                note = "  # noqa: F401" if a.asname and a.asname != a.name else ""
                out[bound] = f"from {mod} import {a.name} as {bound}{note}"
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    note = "" if a.asname == a.name else "  # noqa: F401"
                    out[a.asname] = f"import {a.name} as {a.asname}{note}"
                elif "." in a.name:
                    out[a.name.split(".")[0]] = f"import {a.name}  # noqa: F401"
                else:
                    out[a.name] = f"import {a.name} as {a.name}"
        elif isinstance(node, ast.If) and not surf._is_type_checking(node.test):
            _collect_imports(node.body, out)
            _collect_imports(node.orelse, out)
        elif isinstance(node, ast.Try):
            for part in (node.body, node.orelse, node.finalbody, *(h.body for h in node.handlers)):
                _collect_imports(part, out)


def _runtime_loads(node: ast.AST) -> set[str]:
    """Names loaded when the statement RUNS (annotations are not run)."""
    out: set[str] = set()

    def visit(n: ast.AST) -> None:
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.add(n.id)
        for name, value in ast.iter_fields(n):
            if name in ("annotation", "returns"):
                continue
            for child in value if isinstance(value, list) else [value]:
                if isinstance(child, ast.AST):
                    visit(child)

    visit(node)
    return out


_TRANSFORMED = re.compile(r"^\s*from\s+\.|\bdef\s+\w+\(\s*self\b", re.MULTILINE)


def _comments(text: str) -> list[str]:
    reader = io.StringIO(textwrap.dedent(text)).readline
    return [t.string for t in tokenize.generate_tokens(reader) if t.type == tokenize.COMMENT]


def _head(text: str) -> str:
    code = [ln for ln in text.split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return code[0].strip() if code else ""


def mixin_name(target: str) -> str:
    return "".join(p.capitalize() for p in target.strip("_").split("_")) + "Mixin"


def _ruff(args: list[str], text: str) -> str:
    cmd = [sys.executable, "-m", "ruff", *args]
    cmd += ["--config", str(REPO_ROOT / "pyproject.toml"), "--stdin-filename", "module.py", "-"]
    res = subprocess.run(cmd, input=text, capture_output=True, text=True, cwd=REPO_ROOT)
    if res.returncode:
        raise CodemodError(f"ruff {' '.join(args)} failed:\n{res.stderr}")
    return res.stdout


def _prune(text: str) -> str:
    return _ruff(["check", "--select", "F401", "--fix", "--quiet", "--exit-zero"], text)


def _sort_imports(text: str) -> str:
    return _ruff(["check", "--select", "I", "--fix", "--quiet", "--exit-zero"], text)


def _format(text: str) -> str:
    return _ruff(["format"], text)


def _drop_empty_type_checking(text: str) -> tuple[str, bool]:
    tree = ast.parse(text)
    lines = text.split("\n")
    drop = [
        n
        for n in tree.body
        if isinstance(n, ast.If)
        and surf._is_type_checking(n.test)
        and all(isinstance(b, ast.Pass) for b in n.body)
        and not n.orelse
    ]
    for n in reversed(drop):
        del lines[n.lineno - 1 : n.end_lineno]
    return "\n".join(lines), bool(drop)


def _clean_module(text: str) -> str:
    text = _prune(text)
    text, dropped = _drop_empty_type_checking(text)
    if dropped:
        text = _prune(text)
    return _format(_sort_imports(text))


def _import_line(module: str, names: list[str], noqa: bool) -> str:
    names = sorted(names)
    one = f"from {module} import {', '.join(names)}"
    if not noqa:
        return one
    if len(one) + len("  # noqa: E402") <= 100:
        return one + "  # noqa: E402"
    body = "".join(f"    {n},\n" for n in names)
    return f"from {module} import (  # noqa: E402\n{body})"


# ------------------------------------------------------------------------- plan


@dataclass
class Result:
    files: dict[str, str]
    manifest: ml.Manifest
    source_path: Path | None
    warnings: list[str] = field(default_factory=list)


class Plan:
    def __init__(
        self,
        manifest: ml.Manifest,
        text: str,
        surface: dict | None,
    ) -> None:
        if "\r" in text:
            raise CodemodError("source has carriage returns; normalise line endings first")
        self.m = manifest
        self.text = text
        self.surface = surface
        self.warnings: list[str] = []
        self.rewrapped: list[str] = []
        self.class_mode = manifest.mode == "class"
        self.tree = ast.parse(text)
        self.nodes = self.tree.body
        self.orig = text.split("\n")
        self.placement = ml.resolve(text, manifest)
        self.items = self.placement.items
        self.members = self.placement.members
        self.cls = self._class_node()
        self.doc, self.block = self._leading()
        self._override_docstrings()
        self.graph = ml.build_graph(self.placement)
        self.skip = set(self.block) | ({self.doc} if self.doc is not None else set())
        self.defined = {
            i: surf.top_level_bindings(ast.Module([self.nodes[i]], []))
            for i in range(len(self.nodes))
            if i not in self.skip
        }
        self.last_owner: dict[str, str] = {}
        for i in sorted(self.defined):
            for name in self.defined[i]:
                self.last_owner[name] = self.items[i].target
        self.edited: set[str] = set()
        self.lines = self._edited_lines()
        self.geo = _geometry(self.lines, self.nodes, 0, len(self.lines))
        self.mgeo = self._member_geo()

    # ------------------------------------------------------------ structure

    def _class_node(self) -> ast.ClassDef | None:
        if not self.class_mode:
            return None
        for node in self.nodes:
            if isinstance(node, ast.ClassDef) and node.name == self.m.class_name:
                return node
        raise CodemodError(f"class {self.m.class_name!r} not found")

    def _leading(self) -> tuple[int | None, list[int]]:
        doc = 0 if self.nodes and _is_docstring(self.nodes[0]) else None
        k = 1 if doc is not None else 0
        block: list[int] = []
        while k < len(self.nodes) and _is_import_stmt(self.nodes[k]):
            block.append(k)
            k += 1
        return doc, block

    def _override_docstrings(self) -> None:
        if self.doc is not None:
            self.items[self.doc].target = INIT
        if self.cls is not None and self.cls.body and _is_docstring(self.cls.body[0]):
            self.members[0].target, self.members[0].reason = INIT, "stay"

    def _edited_lines(self) -> list[str]:
        edits: list[tuple[int, int, int, str]] = []
        for node in _relative_imports(self.tree):
            edits.append((node.lineno, _dots_col(self.orig, node), 0, "."))
        if self.cls is not None:
            edits += self._class_edits()
        return _apply_edits(self.orig, edits)

    def _mixin_targets(self) -> list[str]:
        used = {m.target for m in self.members if m.target != INIT}
        order = [t for t in self.m.targets if t in used]
        return order + sorted(used - set(order))

    def _class_edits(self) -> list[tuple[int, int, int, str]]:
        assert self.cls is not None
        edits: list[tuple[int, int, int, str]] = []
        bases = [*self.cls.bases, *(k.value for k in self.cls.keywords)]
        mixins = ", ".join(mixin_name(t) for t in self._mixin_targets())
        if bases and mixins:
            first = min(bases, key=lambda b: (b.lineno, b.col_offset))
            edits.append((first.lineno, first.col_offset, 0, f"{mixins}, "))
        for node, member in zip(self.cls.body, self.members, strict=True):
            if member.target == INIT or not isinstance(node, _FUNC):
                continue
            if any(ml._terminal_name(d) == "staticmethod" for d in node.decorator_list):
                continue
            args = [*node.args.posonlyargs, *node.args.args]
            if args and args[0].arg == "self" and args[0].annotation is None:
                arg = args[0]
                assert arg.end_lineno is not None and arg.end_col_offset is not None
                annotation = f': "{self.m.class_name}"'
                edits.append((arg.end_lineno, arg.end_col_offset, 0, annotation))
                self.edited.add(node.name)
        return edits

    def _member_geo(self) -> Geo | None:
        if self.cls is None:
            return None
        body = self.cls.body
        floor = ml._start(body[0]) - 1
        return _geometry(self.lines, body, floor, body[-1].end_lineno or 0)

    # -------------------------------------------------------------- graph

    def _targets(self) -> list[str]:
        """Non-init target modules that receive anything, manifest order first."""
        used = {self.items[i].target for i in self.defined} - {INIT}
        used |= {m.target for m in self.members} - {INIT}
        order = [t for t in self.m.targets if t in used]
        return order + sorted(used - set(order))

    def check_cycles(self) -> None:
        edges = dict(self.graph.edges)
        if self.class_mode:
            for t in self._targets():
                edges[(INIT, t)] = "eager"
        cycles = ml.ImportGraph(self.graph.refs, edges).cycles()
        if not cycles:
            return
        out = ["eager import cycle between new modules (fix the manifest, never the output):"]
        for comp in cycles:
            out.append(f"  {', '.join(comp)}")
            for (a, b), kind in sorted(edges.items()):
                if kind != "eager" or a not in comp or b not in comp:
                    continue
                names = sorted(
                    {r.name for r in self.graph.refs if (r.source_target, r.target) == (a, b)}
                )
                via = ", ".join(names[:8]) if names else "the facade, which imports every module"
                out.append(f"    {a} -> {b} via {via}")
        raise CycleError("\n".join(out))

    def _needs(self, target: str) -> dict[str, tuple[str, bool]]:
        """name -> (defining target, eager) for every name `target` uses from others."""
        need: dict[str, tuple[str, bool]] = {}
        for r in self.graph.refs:
            if r.source_target != target or self.last_owner.get(r.name) != r.target:
                continue
            was = need.get(r.name)
            need[r.name] = (r.target, r.eager or (was is not None and was[1]))
        return need

    def _check_init_runtime_refs(self) -> None:
        units = [(self.items[i], self.nodes[i]) for i in self.defined]
        if self.cls is not None:
            units += list(zip(self.members, self.cls.body, strict=True))
        for item, node in units:
            if item.target == INIT:
                continue
            clash = _runtime_loads(node) & {n for n, o in self.last_owner.items() if o == INIT}
            if clash:
                raise CodemodError(
                    f"{item.target}: {item.key or item.names} uses {', '.join(sorted(clash))} when "
                    f"it runs, but that name stays in __init__.py (a cycle at import time); "
                    f"move it to another target in the manifest"
                )

    def _import_plan(self) -> dict[str, tuple[list[str], list[str]]]:
        """target -> (modules it imports at the top, modules it imports at the bottom)."""
        plan: dict[str, tuple[list[str], list[str]]] = {}
        for t in self._targets():
            top: set[str] = set()
            bottom: set[str] = set()
            for dst, is_eager in self._needs(t).values():
                if dst != INIT:
                    (top if is_eager else bottom).add(dst)
            plan[t] = (sorted(top, key=str.lower), sorted(bottom, key=str.lower))
        return plan

    def _topo(self) -> list[str]:
        """Facade import order: a topological order of the eager graph (dependencies first)
        in which no import ever reaches a module that is still importing its own imports.

        A module defers an import to its bottom, so importing it can load another module
        early; that module's eager imports must then find every name they need.  The
        search simulates the real import (top imports, definitions, bottom imports) and
        picks the first order, in manifest order, that never fails.
        """
        plan = self._import_plan()
        targets = list(plan)
        eager_deps = {
            t: {b for a, b in self.graph.eager_edges() if a == t and b in plan} for t in targets
        }
        failures: list[str] = []
        dead: set[frozenset[str]] = set()

        def load(m: str, state: dict[str, str], done: list[str]) -> str | None:
            if state[m] != "unloaded":
                return None
            state[m] = "top"
            top, bottom = plan[m]
            for phase, mods in (("top", top), ("defs", bottom)):
                state[m] = phase
                for d in mods:
                    if state[d] == "unloaded":
                        err = load(d, state, done)
                        if err:
                            return err
                    if state[d] == "top":
                        return f"{m} imports names from {d} while {d} is still at its own imports"
            state[m] = "loaded"
            done.append(m)
            return None

        def search(order: list[str], state: dict[str, str]) -> list[str] | None:
            loaded = frozenset(t for t, v in state.items() if v == "loaded")
            if len(loaded) == len(targets):
                return order
            if loaded in dead:
                return None
            for cand in targets:
                if state[cand] != "unloaded" or any(state[d] != "loaded" for d in eager_deps[cand]):
                    continue
                nxt, done = dict(state), []
                err = load(cand, nxt, done)
                if err:
                    failures.append(f"importing {cand} first: {err}")
                    continue
                implicit = [d for d in done if d != cand]
                found = search([*order, cand, *implicit], nxt)
                if found:
                    return found
            dead.add(loaded)
            return None

        order = search([], dict.fromkeys(targets, "unloaded"))
        if order is None:
            raise CodemodError(
                "no import order of the new modules is safe (a deferred import would reach a "
                "module before its names exist); change the manifest:\n  "
                + "\n  ".join(failures[-6:])
            )
        return order

    # ------------------------------------------------------------- rendering

    def _block_text(self) -> str:
        if not self.block:
            return ""
        start = (self.nodes[self.doc].end_lineno or 0) if self.doc is not None else 0
        end = self.nodes[self.block[-1]].end_lineno or 0
        return "\n".join(self.lines[start:end]).strip("\n")

    def _mixin_text(self, target: str) -> str:
        assert self.cls is not None and self.mgeo is not None
        chunks: list[tuple[int, str]] = []
        for j, (node, member) in enumerate(zip(self.cls.body, self.members, strict=True)):
            if member.target != target:
                continue
            if isinstance(node, ast.AnnAssign):
                raise CodemodError(
                    f"{target}: class-level annotation {member.key!r} would move into a mixin"
                )
            chunks.append((j, _chunk_text(self.lines, self.mgeo, j)))
        return f"class {mixin_name(target)}:\n" + _join(chunks, self.mgeo, "\n\n")

    def _shell_text(self) -> str:
        assert self.cls is not None and self.mgeo is not None
        shell = self.items[self.nodes.index(self.cls)]
        header = "\n".join(self.lines[shell.start - 1 : self.mgeo.lo[0] - 1]).rstrip()
        if not self.cls.bases and not self.cls.keywords:
            mixins = ", ".join(mixin_name(t) for t in self._mixin_targets())
            name = self.cls.name
            header = re.sub(
                rf"class\s+{name}\s*(\(\s*\))?\s*:",
                f"class {name}({mixins}):" if mixins else f"class {name}:",
                header,
                count=1,
            )
        chunks = [
            (j, _chunk_text(self.lines, self.mgeo, j))
            for j, member in enumerate(self.members)
            if member.target == INIT
        ]
        body = _join(chunks, self.mgeo, "\n\n") if chunks else "    pass"
        return header + "\n" + body

    def _top_chunks(self, target: str) -> list[tuple[int, str]]:
        chunks = [
            (i, _chunk_text(self.lines, self.geo, i))
            for i in sorted(self.defined)
            if self.items[i].target == target and not self._is_shell(i)
        ]
        if self.class_mode and target == INIT:
            shell = self.nodes.index(self.cls)
            chunks.append((shell, self._shell_text()))
        elif self.class_mode and target in self._mixin_targets():
            chunks.append((self.nodes.index(self.cls), self._mixin_text(target)))
        return sorted(chunks)

    def _is_shell(self, i: int) -> bool:
        return self.cls is not None and self.nodes[i] is self.cls

    def _render_module(self, target: str) -> str:
        need = self._needs(target)
        eager: dict[str, list[str]] = {}
        deferred: dict[str, list[str]] = {}
        typing_only: list[str] = []
        for name, (dst, is_eager) in sorted(need.items()):
            if dst == INIT:
                typing_only.append(name)
            else:
                (eager if is_eager else deferred).setdefault(dst, []).append(name)
        head = [self._block_text()]
        mixin = self.class_mode and target in self._mixin_targets()
        if mixin:
            bound = surf.top_level_imports(ast.parse(self._block_text() or "pass"))
            if "TYPE_CHECKING" not in bound:
                head.append("from typing import TYPE_CHECKING")
        head += [_import_line(f".{dst}", names, False) for dst, names in sorted(eager.items())]
        if mixin:
            names = ", ".join(sorted({self.m.class_name or "", *typing_only}))
            head.append(f"if TYPE_CHECKING:\n    from . import {names}")
        chunks = self._top_chunks(target)
        body = _join(chunks, self.geo, "\n\n\n")
        tail = [_import_line(f".{dst}", names, True) for dst, names in sorted(deferred.items())]
        parts = ["\n".join(h for h in head if h), body, "\n".join(tail)]
        return _clean_module("\n\n\n".join(p for p in parts if p) + "\n")

    def _facade_lines(self, order: list[str]) -> list[str]:
        extra: dict[str, set[str]] = {}
        for name, (dst, _) in self._needs(INIT).items():
            extra.setdefault(dst, set()).add(name)
        lines: list[str] = []
        for t in order:
            names = {n for n, o in self.last_owner.items() if o == t} | extra.get(t, set())
            if self.class_mode and t in self._mixin_targets():
                names.add(mixin_name(t))
            if names:
                lines.append(_import_line(f".{t}", sorted(names), False))
        return lines

    def defined_names(self) -> list[str]:
        return sorted(self.last_owner)

    def _render_init(self, order: list[str]) -> str:
        parts: list[str] = []
        if self.doc is not None:
            parts.append(_chunk_text(self.lines, self.geo, self.doc))
        if self.class_mode and self._block_text():
            parts.append(self._block_text())
        facade = "\n".join(self._facade_lines(order))
        parts.append(f"# isort: off\n{MARKER}\n{facade}\n# isort: on")
        chunks = self._top_chunks(INIT)
        if chunks:
            parts.append(_join(chunks, self.geo, "\n\n\n"))
        names = "".join(f'    "{n}",\n' for n in self.defined_names())
        parts.append(f"__all__ = [\n{names}]")
        text = _prune("\n\n\n".join(parts) + "\n")
        text = text.replace(MARKER, "\n".join(self._reexports(text)))
        return _format(_sort_imports(text))

    def _reexports(self, pruned: str) -> list[str]:
        if not self.surface:
            return []
        origin: dict[str, str] = {}
        _collect_imports(self.nodes, origin)
        bound = surf.top_level_imports(ast.parse(pruned.replace(MARKER, "")))
        bound |= {n for n in self.last_owner}
        lines = []
        for name in sorted(self.surface.get("imported", [])):
            if name in bound:
                continue
            if name in origin:
                lines.append(origin[name])
            else:
                self.warnings.append(f"surface lists imported name {name!r}; source has no import")
        known = set(self.defined_names())
        listed = set(self.surface.get("defined", []))
        if listed and listed != known:
            diff = sorted(listed ^ known)
            self.warnings.append(f"surface `defined` differs from the source: {diff[:10]}")
        return lines

    def render(self) -> dict[str, str]:
        self.check_cycles()
        self._check_init_runtime_refs()
        order = self._topo()
        files = {"__init__.py": self._render_init(order)}
        for t in self._targets():
            files[f"{t}.py"] = self._render_module(t)
        return files

    # ---------------------------------------------------------------- verify

    def _untransform(self, text: str) -> str:
        tree = ast.parse(text)
        lines = text.split("\n")
        edits: list[tuple[int, int, int, str]] = []
        for node in _relative_imports(tree):
            if node.level >= 2:
                edits.append((node.lineno, _dots_col(lines, node), 1, ""))
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            if not cls.name.endswith("Mixin"):
                continue
            for fn in (n for n in cls.body if isinstance(n, _FUNC)):
                args = [*fn.args.posonlyargs, *fn.args.args]
                ann = args[0].annotation if args else None
                if (
                    fn.name in self.edited
                    and ann is not None
                    and isinstance(ann, ast.Constant)
                    and ann.value == self.m.class_name
                ):
                    arg = args[0]
                    assert ann.end_col_offset is not None
                    start = arg.col_offset + len("self")
                    edits.append((arg.lineno, start, ann.end_col_offset - start, ""))
        return "\n".join(_apply_edits(lines, edits))

    def _same(self, label: str, want: str, got: str) -> bool:
        """Byte-identical, or - only where a transform made `ruff format` re-wrap the
        statement - the same AST and the same comments."""
        if want == got:
            return True
        if not _TRANSFORMED.search(want):
            return False
        try:
            same = ast.dump(ast.parse(textwrap.dedent(want))) == ast.dump(
                ast.parse(textwrap.dedent(got))
            )
        except SyntaxError:
            return False
        if same and _comments(want) == _comments(got):
            self.rewrapped.append(f"{label}: {_head(want)}")
            return True
        return False

    def _expect(self, label: str, expected: list[str], got_nodes, got_lines) -> None:
        got = _statement_texts(got_lines, got_nodes)
        pos = 0
        for want in expected:
            while pos < len(got) and not self._same(label, want, got[pos]):
                pos += 1
            if pos == len(got):
                close = difflib.get_close_matches(want, got, n=1, cutoff=0.5)
                near = close[0] if close else ""
                diff = "\n".join(
                    difflib.unified_diff(want.split("\n"), near.split("\n"), "original", label, n=2)
                )
                raise VerifyError(
                    f"{label}: statement not found byte-identical, in order:\n{want}\n{diff}"
                )
            pos += 1

    def verify(self, files: dict[str, str]) -> None:
        init_expected: list[str] = []
        per_target: dict[str, list[str]] = {}
        top_texts = _statement_texts(self.orig, self.nodes)
        for i in sorted(self.defined) + ([self.doc] if self.doc is not None else []):
            if self._is_shell(i):
                continue
            target = self.items[i].target
            if i == self.doc:
                init_expected.insert(0, top_texts[i])
            elif target == INIT:
                init_expected.append(top_texts[i])
            else:
                per_target.setdefault(target, []).append(top_texts[i])
        members: dict[str, list[str]] = {}
        if self.cls is not None:
            member_texts = _statement_texts(self.orig, list(self.cls.body))
            for text, member in zip(member_texts, self.members, strict=True):
                members.setdefault(member.target, []).append(text)
        for name, text in files.items():
            target = name.removesuffix(".py")
            clean = self._untransform(text)
            tree, lines = ast.parse(clean), clean.split("\n")
            expected = init_expected if target == "__init__" else per_target.get(target, [])
            self._expect(name, expected, tree.body, lines)
            if self.cls is None:
                continue
            kind = None
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and (
                    node.name == mixin_name(target)
                    or (target == INIT and node.name == self.cls.name)
                ):
                    kind = node
            if kind is not None:
                self._expect(f"{name}:{kind.name}", members.get(target, []), kind.body, lines)
        self._verify_facade(files["__init__.py"])
        if self.rewrapped:
            self.warnings.append(
                f"{len(self.rewrapped)} statements re-wrapped by ruff format (a self annotation or "
                f"one more dot pushed a line past 100 columns; AST and comments identical), "
                f"first: {self.rewrapped[0]}"
            )

    def _verify_facade(self, init: str) -> None:
        tree = ast.parse(init)
        listed: list[str] = []
        imported: dict[str, set[str]] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "__all__":
                listed = list(ast.literal_eval(node.value))
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                imported.setdefault(node.module or "", set()).update(a.name for a in node.names)
            if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
                raise VerifyError("facade uses import *")
        if listed != self.defined_names():
            raise VerifyError("__all__ differs from the old module's defined names")
        for name, owner in self.last_owner.items():
            if owner != INIT and name not in imported.get(owner, set()):
                raise VerifyError(f"facade does not import {name} from .{owner}")


# ------------------------------------------------------------------ entry points


def source_path(manifest: ml.Manifest) -> Path:
    src = Path(manifest.source)
    candidates = [src] if src.is_absolute() else [Path.cwd() / src]
    if manifest.path is not None and not src.is_absolute():
        here = manifest.path.resolve().parent
        candidates += [d / src for d in (here, *here.parents)]
    for cand in candidates:
        if cand.is_file():
            return cand
    raise ml.ManifestError(f"source {manifest.source!r} not found")


def default_surface(manifest: ml.Manifest) -> Path | None:
    for short, dotted in surf.TARGETS.items():
        if dotted == manifest.module and manifest.mode == "module":
            path = surf.SURFACE_DIR / f"{short}.json"
            return path if path.is_file() else None
    return None


def build(manifest_path: str | Path, surface: str | Path | None = None) -> Result:
    manifest = ml.load_manifest(manifest_path)
    path = source_path(manifest)
    snap_path = Path(surface) if surface else default_surface(manifest)
    snapshot = json.loads(snap_path.read_text()) if snap_path else None
    plan = Plan(manifest, path.read_text(), snapshot)
    files = plan.render()
    plan.verify(files)
    return Result(files, manifest, path, plan.warnings)


def write_files(files: dict[str, str], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (out / name).write_text(text)


def _mirror(real: Path, dest: Path, skip: set[str]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for entry in real.iterdir():
        if entry.name not in skip and entry.name != "__pycache__":
            (dest / entry.name).symlink_to(entry.resolve())


def shadow_tree(result: Result, dest: Path) -> Path:
    """A copy of the import root where the old module is replaced by the new package.

    Everything else is symlinked, so the result can be imported without touching the tree.
    """
    assert result.source_path is not None
    parts = result.manifest.module.split(".")
    real = result.source_path.resolve().parents[len(parts) - 1]
    cur = dest
    for name in parts[:-1]:
        _mirror(real, cur, {name})
        real, cur = real / name, cur / name
    _mirror(real, cur, {parts[-1], f"{parts[-1]}.py"})
    write_files(result.files, cur / parts[-1])
    return dest


_IMPORT_SNIPPET = """
import importlib, os, sys
mod = importlib.import_module(sys.argv[1])
missing = [n for n in getattr(mod, "__all__", []) if not hasattr(mod, n)]
if missing:
    sys.exit("names in __all__ that do not resolve: " + ", ".join(missing))
if not os.path.realpath(mod.__file__).startswith(os.path.realpath(sys.argv[2])):
    sys.exit("imported " + mod.__file__ + " instead of the generated package")
"""


def import_in_subprocess(root: Path, dotted: str) -> None:
    env = {**os.environ, "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"}
    res = subprocess.run(
        [sys.executable, "-c", _IMPORT_SNIPPET, dotted, str(root)],
        capture_output=True,
        text=True,
        env=env,
        cwd=root,
    )
    if res.returncode:
        raise CodemodError(f"importing {dotted} from the generated package failed:\n{res.stderr}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest")
    parser.add_argument("--out", help="write the package contents here and keep the old module")
    parser.add_argument("--check", action="store_true", help="temp dir, import, verify; no writes")
    parser.add_argument("--surface", help="surface snapshot json (default: scripts/split/surface)")
    args = parser.parse_args(argv)
    try:
        result = build(args.manifest, args.surface)
        for warning in result.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if args.check:
            with tempfile.TemporaryDirectory() as tmp:
                root = shadow_tree(result, Path(tmp) / "shadow")
                import_in_subprocess(root, result.manifest.module)
            print(f"ok: {len(result.files)} modules for {result.manifest.module} import cleanly")
            return 0
        package = Path(result.manifest.package)
        write_files(result.files, Path(args.out) if args.out else package)
        if not args.out and result.source_path is not None:
            result.source_path.unlink()
        print(f"wrote {len(result.files)} files to {args.out or package}")
        return 0
    except CodemodError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ml.ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
