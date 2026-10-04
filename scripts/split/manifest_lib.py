"""Manifest format and deterministic resolver for the engine module split.

Used by the codemod, `to_registry` and the manifest drafter.  Stdlib only.

Manifest format (TOML, one file per old module)
-----------------------------------------------
Top-level keys:

``module``   dotted old module path, e.g. ``magic_cards_model.machines.effects``
``source``   old file path (resolved against the cwd, then the manifest's own
             directory and its parents)
``package``  new package directory the codemod writes into
``mode``     ``"module"``: top-level statements move to sibling modules, or
             ``"class"``: the methods of one class move to mixin modules
             (used for ``Game``)
``targets``  ordered list of target module names.  The order is meaningful: for
             effects it IS the FAMILIES order F2 uses for intra-segment order.
             ``_common`` is always a legal target even when not listed.

``[names]``  explicit ``name = "target"`` entries.

``[[rules]]``  ordered; each ``{pattern, target, kinds}``.  ``pattern`` is a
             regex that must ``fullmatch`` a name; ``kinds`` (optional, any of
             ``def``/``class``/``const``) restricts the rule.  First match wins.

``[placed]`` baked ``name = "target"`` entries.  Written by ``bake``, then
             reviewed by a human or agent; ``bake`` keeps existing values.

Class mode adds ``class`` (the class name), ``stay`` (member names that stay in
the class body in the package ``__init__``: fields, validators, named methods)
and ``records`` (the target for every other module-level class).  In class mode
fields (annotated class attributes) and every pydantic-decorated member
(``field_validator``, ``model_validator``, ``computed_field`` ...) stay
automatically; the class itself is the ``__init__`` shell.

Resolution precedence
---------------------
Every top-level statement (and, in class mode, every class-body member) gets
exactly one target and a reason.  First hit wins:

1. class mode only: ``stay`` list, pydantic-decorated, field  (target
   ``__init__``; reasons ``stay``/``decorated``/``field``; the class shell is
   ``class-shell``)
2. ``[names]``        (reason ``name``)
3. ``[[rules]]``      (reason ``rule``)
4. ``[placed]``       (reason ``placed``)
5. class mode only: a module-level class goes to ``records``  (``records``)
6. class mode only: a class-body alias of a method (``_old = new``) goes with
   that method, whatever else would place it  (``alias``)
7. constant rule: an unmatched module-level assignment goes to the target of its
   only referencing def/class (``const-single``); referenced from two or more
   targets -> ``_common`` (``const-shared``); unreferenced -> neighbour
   (``const-unreferenced``).  A constant used only by another constant follows
   that constant's users.  In class mode the class members count as users of
   module-level constants.
8. nearest preceding placed neighbour.  Imports (an ``if TYPE_CHECKING:`` block
   of imports included) get reason ``import`` and bare string statements
   (module and attribute docstrings) ``docstring``: neither is a placement, they
   are copied or travel with the member above.  Anything else gets
   ``neighbour``; statements before any placed one go to the first target.

Resolution never fails on a name it has not seen, so new code on main resolves.

``bake`` assigns, for defs still unplaced after names and rules, the majority
target among their callers; tie -> majority among callees; tie -> neighbour.
In class mode members that stay in the class shell (``__init__``) never vote:
bake places methods into mixins only.
It writes ``[placed]`` sorted and is idempotent.  Existing ``[placed]`` values
are kept, entries for names no longer in the source are pruned.  In class mode
a call is a ``self.<method>`` attribute reference.  ``[placed]`` shares one
namespace between module-level names and class members, and bake only writes
class members there.

Import graph
------------
An edge A -> B exists for every name A references that B defines (string
annotations are parsed as expressions and count; names bound by lazy in-function
imports or other locals do not).  An edge is EAGER when some reference executes
at import time (decorators, default values, class bases and class-body
statements, module-level expressions, and annotations of module-level or
class-level variables - a string annotation there is counted as eager, the
conservative reading, because pydantic resolves it at class creation) and
DEFERRED when every reference is inside a function body, a lambda body or a
function annotation.  ``ImportGraph.cycles()`` returns the strongly connected
components of the EAGER graph: deferred edges never form a cycle error, because
the codemod places their imports at the module bottom, after every definition.

CLI
---
``mise exec -- uv run python scripts/split/manifest_lib.py check <manifest.toml>``
prints per-target statement and line counts, the unplaced count, the reason
histogram and eager cycles, and exits 1 on an eager cycle or on a manifest
target that receives nothing.  ``bake <manifest.toml>`` rewrites ``[placed]``.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

COMMON = "_common"
STAY = "__init__"
KINDS = ("def", "class", "const")
MODES = ("module", "class")
PYDANTIC_DECORATORS = frozenset(
    {
        "field_validator",
        "model_validator",
        "computed_field",
        "field_serializer",
        "model_serializer",
        "validator",
        "root_validator",
    }
)
EXPLICIT_REASONS = frozenset(
    {"name", "rule", "placed", "stay", "decorated", "field", "records", "class-shell", "alias"}
)
COPIED_REASONS = frozenset({"import", "docstring"})
FALLBACK_REASONS = frozenset({"neighbour", "const-single", "const-shared", "const-unreferenced"})

_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


class ManifestError(ValueError):
    """The manifest (or the source it points at) is invalid."""


# ------------------------------------------------------------------ the manifest


@dataclass(frozen=True)
class Rule:
    pattern: str
    target: str
    kinds: tuple[str, ...] = ()

    @property
    def regex(self) -> re.Pattern[str]:
        return re.compile(self.pattern)


@dataclass
class Manifest:
    module: str
    source: str
    package: str
    mode: str
    targets: list[str]
    names: dict[str, str] = field(default_factory=dict)
    rules: list[Rule] = field(default_factory=list)
    placed: dict[str, str] = field(default_factory=dict)
    class_name: str | None = None
    stay: list[str] = field(default_factory=list)
    records: str | None = None
    path: Path | None = None


def parse_manifest(data: dict, path: Path | None = None) -> Manifest:
    """Validate a decoded manifest table and build a Manifest."""
    try:
        m = Manifest(
            module=data["module"],
            source=data["source"],
            package=data["package"],
            mode=data["mode"],
            targets=list(data["targets"]),
            names=dict(data.get("names", {})),
            rules=[
                Rule(r["pattern"], r["target"], tuple(r.get("kinds", ())))
                for r in data.get("rules", [])
            ],
            placed=dict(data.get("placed", {})),
            class_name=data.get("class"),
            stay=list(data.get("stay", [])),
            records=data.get("records"),
            path=path,
        )
    except KeyError as exc:
        raise ManifestError(f"manifest is missing key {exc.args[0]!r}") from None
    if m.mode not in MODES:
        raise ManifestError(f"mode must be one of {MODES}, got {m.mode!r}")
    if not m.targets:
        raise ManifestError("targets must not be empty")
    legal = {*m.targets, COMMON}
    for label, table in (("names", m.names), ("placed", m.placed)):
        for name, target in table.items():
            if target not in legal:
                raise ManifestError(f"[{label}] {name!r} -> unknown target {target!r}")
    for rule in m.rules:
        try:
            re.compile(rule.pattern)
        except re.error as exc:
            raise ManifestError(f"rule pattern {rule.pattern!r}: {exc}") from None
        if rule.target not in legal:
            raise ManifestError(f"rule {rule.pattern!r} -> unknown target {rule.target!r}")
        bad = set(rule.kinds) - set(KINDS)
        if bad:
            raise ManifestError(f"rule {rule.pattern!r}: unknown kinds {sorted(bad)}")
    if m.mode == "class":
        if not m.class_name:
            raise ManifestError("class mode needs `class`")
        if m.records not in legal or m.records is None:
            raise ManifestError("class mode needs `records` naming one of the targets")
    return m


def load_manifest(path: str | Path) -> Manifest:
    path = Path(path)
    with path.open("rb") as fh:
        return parse_manifest(tomllib.load(fh), path)


def read_source(manifest: Manifest) -> str:
    """Read the manifest's `source`: cwd first, then the manifest dir and its parents."""
    src = Path(manifest.source)
    candidates = [src] if src.is_absolute() else [Path.cwd() / src]
    if manifest.path is not None and not src.is_absolute():
        here = manifest.path.resolve().parent
        candidates += [d / src for d in (here, *here.parents)]
    for cand in candidates:
        if cand.is_file():
            return cand.read_text()
    raise ManifestError(f"source {manifest.source!r} not found")


# ------------------------------------------------------------- reference analysis


def _bound(nodes) -> set[str]:
    """Names bound in this scope by `nodes` (not descending into nested scopes)."""
    out: set[str] = set()
    declared_global: set[str] = set()

    def visit(n: ast.AST) -> None:
        if isinstance(n, (*_FUNC, ast.ClassDef)):
            out.add(n.name)
            return
        if isinstance(n, ast.Lambda):
            return
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, ast.alias):
            out.add(n.asname or n.name.split(".")[0])
        elif isinstance(n, (ast.MatchAs, ast.MatchStar)) and n.name:
            out.add(n.name)
        elif isinstance(n, ast.MatchMapping) and n.rest:
            out.add(n.rest)
        elif isinstance(n, ast.Global):
            declared_global.update(n.names)
        for child in ast.iter_child_nodes(n):
            visit(child)

    for node in nodes:
        visit(node)
    return out - declared_global


def _params(args: ast.arguments) -> set[str]:
    names = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    names.update(a.arg for a in (args.vararg, args.kwarg) if a)
    return names


def _terminal_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        return _terminal_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _is_literal(node: ast.AST) -> bool:
    return _terminal_name(node) == "Literal"


class _Refs:
    """Collects (name, eager) references and attribute names of one statement."""

    def __init__(self) -> None:
        self.refs: list[tuple[str, bool]] = []
        self.attrs: set[str] = set()

    def visit(self, n, eager, outer, cls) -> None:
        if isinstance(n, ast.Name):
            if isinstance(n.ctx, ast.Load) and n.id not in outer and n.id not in cls:
                self.refs.append((n.id, eager))
        elif isinstance(n, ast.Attribute):
            self.attrs.add(n.attr)
            self.visit(n.value, eager, outer, cls)
        elif isinstance(n, _FUNC):
            self._function(n, eager, outer, cls)
        elif isinstance(n, ast.Lambda):
            a = n.args
            for d in (*a.defaults, *(d for d in a.kw_defaults if d)):
                self.visit(d, eager, outer, cls)
            self.visit(n.body, False, outer | _params(a), frozenset())
        elif isinstance(n, ast.ClassDef):
            for part in (*n.decorator_list, *n.bases, *(k.value for k in n.keywords)):
                self.visit(part, eager, outer, cls)
            inner = frozenset(_bound(n.body))
            for stmt in n.body:
                self.visit(stmt, eager, outer, inner)
        elif isinstance(n, ast.AnnAssign):
            self.annotation(n.annotation, eager, outer, cls)
            self.visit(n.target, eager, outer, cls)
            if n.value is not None:
                self.visit(n.value, eager, outer, cls)
        elif isinstance(n, _COMPREHENSIONS):
            targets = _bound([g.target for g in n.generators])
            for child in ast.iter_child_nodes(n):
                self.visit(child, eager, outer | targets, cls)
        elif isinstance(n, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
            return
        else:
            for child in ast.iter_child_nodes(n):
                self.visit(child, eager, outer, cls)

    def _function(self, n, eager, outer, cls) -> None:
        for d in n.decorator_list:
            self.visit(d, eager, outer, cls)
        a = n.args
        for d in (*a.defaults, *(d for d in a.kw_defaults if d)):
            self.visit(d, eager, outer, cls)
        every_arg = (*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg)
        for arg in every_arg:
            if arg is not None and arg.annotation is not None:
                self.annotation(arg.annotation, False, outer, cls)
        if n.returns is not None:
            self.annotation(n.returns, False, outer, cls)
        inner = outer | _bound(n.body) | _params(a)
        for stmt in n.body:
            self.visit(stmt, False, inner, frozenset())

    def annotation(self, n, eager, outer, cls, depth: int = 0) -> None:
        if isinstance(n, ast.Constant):
            if isinstance(n.value, str) and depth < 4:
                try:
                    parsed = ast.parse(n.value.strip(), mode="eval").body
                except SyntaxError:
                    return
                self.annotation(parsed, eager, outer, cls, depth + 1)
        elif isinstance(n, (ast.Name, ast.Attribute)):
            self.visit(n, eager, outer, cls)
        elif isinstance(n, ast.Subscript) and _is_literal(n.value):
            self.visit(n.value, eager, outer, cls)
        else:
            for child in ast.iter_child_nodes(n):
                self.annotation(child, eager, outer, cls, depth)


# ------------------------------------------------------------------ statements


@dataclass
class Item:
    key: str | None
    names: tuple[str, ...]
    kind: str  # def / class / const / import / other
    start: int
    end: int
    refs: list[tuple[str, bool]] = field(repr=False, default_factory=list)
    uses: frozenset[str] = field(repr=False, default=frozenset())
    pydantic: bool = False
    is_field: bool = False
    is_doc: bool = False
    alias_of: str | None = None
    target: str = ""
    reason: str = ""

    @property
    def lines(self) -> int:
        return self.end - self.start + 1


def _assign_names(targets) -> tuple[str, ...] | None:
    names: list[str] = []
    for t in targets:
        if isinstance(t, ast.Name):
            names.append(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            sub = _assign_names(t.elts)
            if sub is None:
                return None
            names.extend(sub)
        else:
            return None
    return tuple(names)


def _classify(node: ast.stmt) -> tuple[str, tuple[str, ...]]:
    if isinstance(node, _FUNC):
        return "def", (node.name,)
    if isinstance(node, ast.ClassDef):
        return "class", (node.name,)
    if isinstance(node, ast.Assign):
        names = _assign_names(node.targets)
        if names:
            return "const", names
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return "const", (node.target.id,)
    if isinstance(node, (ast.Import, ast.ImportFrom)) or _is_type_checking_block(node):
        return "import", ()
    return "other", tuple(sorted(_bound([node])))


def _is_type_checking_block(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.If)
        and _terminal_name(node.test) == "TYPE_CHECKING"
        and not node.orelse
        and all(isinstance(s, (ast.Import, ast.ImportFrom)) for s in node.body)
    )


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _alias_of(node: ast.stmt) -> str | None:
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Name)
    ):
        return node.value.id
    return None


def _start(node: ast.stmt) -> int:
    decos = getattr(node, "decorator_list", [])
    return min([node.lineno, *(d.lineno for d in decos)])


def _make_item(node: ast.stmt, member: bool, shell: bool = False) -> Item:
    kind, names = _classify(node)
    refs = _Refs()
    if shell:
        assert isinstance(node, ast.ClassDef)
        for part in (*node.decorator_list, *node.bases, *(k.value for k in node.keywords)):
            refs.visit(part, True, frozenset(), frozenset())
    else:
        refs.visit(node, True, frozenset(), frozenset())
    uses = {n for n, _ in refs.refs}
    if member:
        uses |= refs.attrs
    decos = getattr(node, "decorator_list", [])
    return Item(
        key=names[0] if names else None,
        names=names,
        kind=kind,
        start=_start(node),
        end=node.end_lineno or node.lineno,
        refs=refs.refs,
        uses=frozenset(uses),
        pydantic=any(_terminal_name(d) in PYDANTIC_DECORATORS for d in decos),
        is_field=isinstance(node, ast.AnnAssign),
        is_doc=_is_docstring(node),
        alias_of=_alias_of(node) if member else None,
    )


@dataclass
class Placement:
    manifest: Manifest
    items: list[Item]
    members: list[Item] = field(default_factory=list)

    def units(self) -> list[Item]:
        """Movable units: top-level statements, and in class mode the members
        instead of the class shell."""
        if self.manifest.mode != "class":
            return list(self.items)
        shell = self.manifest.class_name
        return [i for i in self.items if i.reason != "class-shell" or i.key != shell] + list(
            self.members
        )

    def target_of(self, name: str) -> str | None:
        found = None
        for item in self.items:
            if name in item.names:
                found = item.target
        return found

    def lines_by_target(self) -> Counter:
        out: Counter = Counter()
        for u in self.units():
            out[u.target] += u.lines
        return out

    def statements_by_target(self) -> Counter:
        return Counter(u.target for u in self.units())

    def reasons(self) -> Counter:
        return Counter(u.reason for u in self.units())

    def unplaced(self) -> int:
        return sum(1 for u in self.units() if u.kind in KINDS and u.reason in FALLBACK_REASONS)


def _parse(text: str, manifest: Manifest) -> Placement:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ManifestError(f"source does not parse: {exc}") from None
    cls_name = manifest.class_name if manifest.mode == "class" else None
    items: list[Item] = []
    members: list[Item] = []
    found = False
    for node in tree.body:
        is_shell = cls_name is not None and isinstance(node, ast.ClassDef) and node.name == cls_name
        items.append(_make_item(node, member=False, shell=is_shell))
        if is_shell:
            found = True
            members = [_make_item(child, member=True) for child in node.body]
            methods = {m.key for m in members if m.kind == "def"}
            for member in members:
                if member.alias_of not in methods:
                    member.alias_of = None
    if cls_name is not None and not found:
        raise ManifestError(f"class {cls_name!r} not found in source")
    return Placement(manifest, items, members)


def _set(item: Item, target: str, reason: str) -> None:
    item.target, item.reason = target, reason


def _explicit(item: Item, m: Manifest, member: bool) -> None:
    """Steps 1-5 of the precedence: set target+reason or leave the item unresolved."""
    if item.kind not in KINDS:
        return
    if member:
        if item.alias_of:
            return None
        if any(n in m.stay for n in item.names):
            return _set(item, STAY, "stay")
        if item.kind == "def" and item.pydantic:
            return _set(item, STAY, "decorated")
        if item.is_field:
            return _set(item, STAY, "field")
    elif m.mode == "class" and item.kind == "class" and item.key == m.class_name:
        return _set(item, STAY, "class-shell")
    for name in item.names:
        if name in m.names:
            return _set(item, m.names[name], "name")
    for rule in m.rules:
        if rule.kinds and item.kind not in rule.kinds:
            continue
        rx = rule.regex
        if any(rx.fullmatch(n) for n in item.names):
            return _set(item, rule.target, "rule")
    for name in item.names:
        if name in m.placed:
            return _set(item, m.placed[name], "placed")
    if not member and m.mode == "class" and item.kind == "class" and m.records:
        return _set(item, m.records, "records")


def _using(units: list[Item]) -> dict[str, list[int]]:
    using: dict[str, list[int]] = {}
    for i, u in enumerate(units):
        for name in u.uses:
            using.setdefault(name, []).append(i)
    return using


def _neighbour(units: list[Item], i: int, first: str) -> str:
    for k in range(i - 1, -1, -1):
        if units[k].target:
            return units[k].target
    return first


def _const_users(units, using, i, outside_from: int, seen=None) -> set[int]:
    """Indices of the defs/classes using units[i]; units from `outside_from` on
    are already resolved and count as users whatever their kind."""
    seen = seen if seen is not None else {i}
    users: set[int] = set()
    for name in units[i].names:
        for j in using.get(name, ()):
            if j in seen:
                continue
            seen.add(j)
            if units[j].kind in ("def", "class") or j >= outside_from:
                users.add(j)
            elif units[j].kind == "const":
                users |= _const_users(units, using, j, outside_from, seen)
    return users


def _finish(units: list[Item], m: Manifest, outside: list[Item] | None = None) -> None:
    """Fallback placement.  `outside` are already-resolved units (class members)
    that count as users of these units' constants."""
    first = m.targets[0]
    pool = [*units, *(outside or [])]
    using = _using(pool)
    for i, u in enumerate(units):
        if not u.target and u.kind in ("def", "class"):
            _set(u, _neighbour(units, i, first), "neighbour")
    methods = {u.key: u.target for u in units if u.kind == "def"}
    for u in units:
        if u.alias_of in methods:
            _set(u, methods[u.alias_of], "alias")
    for i, u in enumerate(units):
        if u.target:
            continue
        if u.kind == "const":
            users = _const_users(pool, using, i, len(units))
            targets = {pool[j].target for j in users}
            if len(targets) == 1:
                _set(u, targets.pop(), "const-single")
            elif targets:
                _set(u, COMMON, "const-shared")
            else:
                _set(u, _neighbour(units, i, first), "const-unreferenced")
        elif u.kind == "import":
            _set(u, _neighbour(units, i, first), "import")
        elif u.is_doc:
            _set(u, _neighbour(units, i, first), "docstring")
        else:
            _set(u, _neighbour(units, i, first), "neighbour")


def _prepare(text: str, manifest: Manifest) -> Placement:
    p = _parse(text, manifest)
    for item in p.items:
        _explicit(item, manifest, member=False)
    for item in p.members:
        _explicit(item, manifest, member=True)
    return p


def resolve(source_text: str, manifest: Manifest) -> Placement:
    """Give every top-level statement (and class member) one target and a reason."""
    p = _prepare(source_text, manifest)
    _finish(p.members, manifest)
    _finish(p.items, manifest, outside=p.members)
    return p


# -------------------------------------------------------------------------- bake


def _majority(votes: list[str]) -> str | None:
    """The unique most common vote, or None on a tie or no votes."""
    if not votes:
        return None
    ranked = Counter(votes).most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def bake(source_text: str, manifest: Manifest) -> dict[str, str]:
    """The `[placed]` table: existing entries kept, still-unplaced defs assigned by
    caller majority, then callee majority, then neighbour."""
    p = _prepare(source_text, manifest)
    units = p.members if manifest.mode == "class" else p.items
    first = manifest.targets[0]
    using = _using(units)
    by_name: dict[str, int] = {}
    for i, u in enumerate(units):
        if u.kind in KINDS:
            for n in u.names:
                by_name[n] = i
    # members staying in the class shell are not a mixin and cast no vote
    known = {i: u.target for i, u in enumerate(units) if u.target and u.target != STAY}
    pending = [i for i, u in enumerate(units) if not u.target and u.kind == "def"]

    def callers(i: int) -> list[int]:
        out: set[int] = set()
        for n in units[i].names:
            out.update(j for j in using.get(n, ()) if j != i)
        return sorted(out)

    def decide(i: int, caller_votes: list[str]) -> str:
        won = _majority(caller_votes)
        if won is None:
            callees = {by_name[n] for n in units[i].uses if n in by_name and by_name[n] != i}
            won = _majority([known[j] for j in sorted(callees) if j in known])
        if won is None:
            won = next((known[k] for k in range(i - 1, -1, -1) if k in known), first)
        return won

    while True:
        progressed = False
        for i in list(pending):
            votes = [known[j] for j in callers(i) if j in known]
            if votes:
                known[i] = decide(i, votes)
                pending.remove(i)
                progressed = True
        if not progressed:
            break
    for i in list(pending):
        known[i] = decide(i, [])

    present = {n for u in units for n in u.names}
    placed = {k: v for k, v in manifest.placed.items() if k in present}
    for i, u in enumerate(units):
        if u.kind == "def" and u.reason not in EXPLICIT_REASONS and u.key:
            placed[u.key] = known[i]
    return dict(sorted(placed.items()))


_PLACED_HEADER = re.compile(r"^\[placed\]\s*(#.*)?$")
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def _render_placed(placed: dict[str, str]) -> str:
    rows = [
        f"{k if _BARE_KEY.fullmatch(k) else json.dumps(k)} = {json.dumps(v)}\n"
        for k, v in placed.items()
    ]
    return "[placed]\n" + "".join(rows)


def _replace_placed(text: str, placed: dict[str, str]) -> str:
    block = _render_placed(placed)
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if _PLACED_HEADER.match(line.strip()):
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("["):
                j += 1
            tail = lines[j:]
            sep = "\n" if tail else ""
            return "".join(lines[:i]) + block + sep + "".join(tail)
    if text and not text.endswith("\n"):
        text += "\n"
    return text + ("\n" if text else "") + block


def bake_file(manifest_path: str | Path) -> bool:
    """Bake a manifest file in place.  Returns False when nothing changed."""
    path = Path(manifest_path)
    manifest = load_manifest(path)
    placed = bake(read_source(manifest), manifest)
    if placed == manifest.placed:
        return False
    path.write_text(_replace_placed(path.read_text(), placed))
    return True


# ------------------------------------------------------------------ import graph


@dataclass(frozen=True)
class Ref:
    source_key: str
    source_target: str
    name: str
    target: str
    eager: bool


@dataclass
class ImportGraph:
    refs: list[Ref]
    edges: dict[tuple[str, str], str]  # (from, to) -> "eager" | "deferred"

    def eager_edges(self) -> set[tuple[str, str]]:
        return {e for e, kind in self.edges.items() if kind == "eager"}

    def cycles(self) -> list[list[str]]:
        """Strongly connected components (size > 1) of the eager graph."""
        graph: dict[str, list[str]] = {}
        for a, b in sorted(self.eager_edges()):
            graph.setdefault(a, []).append(b)
            graph.setdefault(b, [])
        index: dict[str, int] = {}
        low: dict[str, int] = {}
        stack: list[str] = []
        on: set[str] = set()
        out: list[list[str]] = []

        def strong(v: str) -> None:
            index[v] = low[v] = len(index)
            stack.append(v)
            on.add(v)
            for w in graph[v]:
                if w not in index:
                    strong(w)
                    low[v] = min(low[v], low[w])
                elif w in on:
                    low[v] = min(low[v], index[w])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    out.append(sorted(comp))

        for v in graph:
            if v not in index:
                strong(v)
        return sorted(out)


def build_graph(placement: Placement) -> ImportGraph:
    """Edges between targets from every reference to a name another target defines."""
    definers: dict[str, set[str]] = {}
    for item in placement.items:
        for name in item.names:
            definers.setdefault(name, set()).add(item.target)
    refs: list[Ref] = []
    edges: dict[tuple[str, str], str] = {}
    for item in [*placement.items, *placement.members]:
        key = item.key or f"@{item.start}"
        for name, eager in item.refs:
            owners = definers.get(name)
            if not owners or item.target in owners:
                continue
            for dst in sorted(owners):
                refs.append(Ref(key, item.target, name, dst, eager))
                edge = (item.target, dst)
                if eager:
                    edges[edge] = "eager"
                else:
                    edges.setdefault(edge, "deferred")
    return ImportGraph(refs, edges)


# --------------------------------------------------------------------------- CLI


@dataclass
class CheckReport:
    manifest: Manifest
    statements: Counter
    lines: Counter
    reasons: Counter
    unplaced: int
    graph: ImportGraph
    cycles: list[list[str]]
    empty_targets: list[str]

    @property
    def ok(self) -> bool:
        return not self.cycles and not self.empty_targets

    def render(self) -> str:
        m = self.manifest
        out = [f"manifest: {m.module} ({m.mode}, {len(m.targets)} targets)"]
        shown = [*m.targets, *sorted(set(self.statements) - set(m.targets))]
        width = max(len(t) for t in shown)
        out.append(f"{'target'.ljust(width)}  statements  lines")
        for t in shown:
            out.append(f"{t.ljust(width)}  {self.statements[t]:>10}  {self.lines[t]:>5}")
        out.append(f"unplaced: {self.unplaced}")
        hist = " ".join(f"{k}={v}" for k, v in sorted(self.reasons.items()))
        out.append(f"reasons: {hist}")
        deferred = sum(1 for k in self.graph.edges.values() if k == "deferred")
        out.append(f"edges: {len(self.graph.eager_edges())} eager, {deferred} deferred")
        if self.cycles:
            out.append("eager cycles:")
            for comp in self.cycles:
                out.append(f"  {', '.join(comp)}")
                for (a, b), kind in sorted(self.graph.edges.items()):
                    if kind == "eager" and a in comp and b in comp:
                        names = sorted(
                            {
                                r.name
                                for r in self.graph.refs
                                if (r.source_target, r.target) == (a, b) and r.eager
                            }
                        )
                        out.append(f"    {a} -> {b} via {', '.join(names[:6])}")
        else:
            out.append("eager cycles: none")
        if self.empty_targets:
            out.append(f"targets receiving nothing: {', '.join(self.empty_targets)}")
        return "\n".join(out)


def check(manifest_path: str | Path) -> CheckReport:
    manifest = load_manifest(manifest_path)
    p = resolve(read_source(manifest), manifest)
    graph = build_graph(p)
    statements = p.statements_by_target()
    return CheckReport(
        manifest=manifest,
        statements=statements,
        lines=p.lines_by_target(),
        reasons=p.reasons(),
        unplaced=p.unplaced(),
        graph=graph,
        cycles=graph.cycles(),
        empty_targets=[t for t in manifest.targets if not statements[t]],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="report placement, cycles; exit 1 on a problem").add_argument(
        "manifest"
    )
    sub.add_parser("bake", help="write the [placed] table").add_argument("manifest")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            report = check(args.manifest)
            print(report.render())
            return 0 if report.ok else 1
        changed = bake_file(args.manifest)
        print(f"{args.manifest}: {'[placed] updated' if changed else 'already baked'}")
        return 0
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
