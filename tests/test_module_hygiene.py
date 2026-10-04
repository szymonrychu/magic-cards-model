"""AST module hygiene checks - S0 of the engine-modularization plan.

Ruff's F811 already refuses a *redefined function or class* at module level,
but it does not see a *reassigned constant*. At the time this test was
written, HEAD carried three live instances of exactly that, each silently
overridden by a later binding of the same name with nothing reading the
first one's own value: `_BARE_SHUFFLE_RE` in `machines/effects.py`, and
`_TYPE_WORDS` / `_COLOR_WORDS` in `machines/cost.py`. (a) below closes that
gap for every module, constants included.

(b)-(d) get ahead of the two collision risks the modularization plan calls
out for the splits still to come: two family modules of a package
accidentally claiming the same public name (S2's `machines/effects/`, S4's
`models/game/`), and two `Game` mixins silently shadowing one another's
method through the MRO (S4). They are exercised today against the
`models`/`machines` packages that already exist and already curate an
`__all__` facade, so the mechanism is proven correct before there is a
mixin package for it to matter on.
"""

from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "magic_cards_model"
REPO_ROOT = SRC.parent.parent


def _iter_modules() -> list[pathlib.Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _packages() -> list[pathlib.Path]:
    """Every directory under `SRC` that is itself a package (has an
    `__init__.py`), `SRC` included."""
    return sorted({p.parent for p in SRC.rglob("__init__.py")})


#: `models/` and `machines/` predate this whole effort and were never one
#: flat namespace split apart - they are a package of loosely related,
#: independently authored modules (`casting.py`'s function `exile_warped`
#: and `delayed.py`'s unrelated `exile_warped = ExileWarped()` instance are
#: a real, harmless example already on `main`). (b) and (c) below are about
#: the opposite case: a package whose sibling modules *are* fragments of one
#: former file (`machines/effects/`, `models/game/`, once S2/S4 create
#: them), where every name really was unique by construction and a
#: collision is a fresh accident worth failing on. `main`-inherited reuse in
#: the two grouping packages is out of that scope.
#: `machines/conditions/` is a grouping package too, and by design: each
#: family module exports the same registry name, `READERS`, which the
#: package's `__init__` reads module by module (`conditions.readers()`) and
#: never imports into one namespace - the collision (b) guards against
#: cannot happen there.
_SPLIT_PACKAGE_EXEMPT = {SRC / "models", SRC / "machines", SRC / "machines" / "conditions"}


def _split_packages() -> list[pathlib.Path]:
    return [p for p in _packages() if p not in _SPLIT_PACKAGE_EXEMPT]


_PARSE_CACHE: dict[pathlib.Path, ast.Module] = {}


def _parse(path: pathlib.Path) -> ast.Module:
    cached = _PARSE_CACHE.get(path)
    if cached is None:
        cached = ast.parse(path.read_text(), filename=str(path))
        _PARSE_CACHE[path] = cached
    return cached


def _is_setter_like(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """`@x.setter`/`@x.deleter`/`@x.getter` legitimately repeat a property's
    name, as does `@overload`/`@typing.overload` - neither is the silent
    rebind this file is looking for."""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Attribute) and dec.attr in ("setter", "deleter", "getter"):
            return True
        if isinstance(dec, ast.Name) and dec.id == "overload":
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == "overload":
            return True
    return False


def _top_level_bindings(tree: ast.Module) -> dict[str, list[int]]:
    """name -> every line it is bound on, at the module's own top level.

    Deliberately does not recurse into `if`/`try` bodies (an `if
    TYPE_CHECKING:` guard only ever holds imports in this codebase, never a
    second definition of a runtime name) - only `tree.body` itself.
    """
    bindings: dict[str, list[int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_setter_like(node):
                continue
            bindings.setdefault(node.name, []).append(node.lineno)
        elif isinstance(node, ast.ClassDef):
            bindings.setdefault(node.name, []).append(node.lineno)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bindings.setdefault(target.id, []).append(node.lineno)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bindings.setdefault(node.target.id, []).append(node.lineno)
    return bindings


def _rel(path: pathlib.Path) -> str:
    return str(path.relative_to(REPO_ROOT))


# ---------------------------------------------------------------------- (a)


def test_no_duplicate_module_level_bindings():
    """No module binds one top-level name twice - functions, classes, and
    constants alike."""
    violations = []
    for path in _iter_modules():
        for name, lines in _top_level_bindings(_parse(path)).items():
            if len(lines) > 1:
                violations.append(f"{_rel(path)}: `{name}` bound at lines {lines}")
    assert not violations, "duplicate module-level binding(s):\n" + "\n".join(violations)


# -------------------------------------------------------------------- (a2)


def _class_level_bindings(class_def: ast.ClassDef) -> dict[str, list[int]]:
    """name -> every line it is bound on, directly in this class's own body -
    the class-body twin of `_top_level_bindings` right above, which only
    ever walked `tree.body` and so never saw a duplicate pydantic field: an
    `AnnAssign`/`Assign` inside a `ClassDef` is invisible to a walk that
    only reads the module's own top level. Deliberately not recursive into
    a nested `if`/`try` inside the class body, the same restriction
    `_top_level_bindings` applies at module scope.
    """
    bindings: dict[str, list[int]] = {}
    for node in class_def.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bindings.setdefault(node.target.id, []).append(node.lineno)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bindings.setdefault(target.id, []).append(node.lineno)
    return bindings


def test_no_duplicate_field_in_one_class_body():
    """No class declares the same field (or other class-body name) twice.

    `Game.attacked_this_turn` was bound at two separate lines in the same
    class body, an identical `SortedSet[UUID]` annotation and default at
    each - Pydantic silently let the second declaration win (the same
    "last binding wins" behaviour (a) already refuses at module level), with
    nothing checking that the first one's own, more detailed docstring was
    ever meant to be thrown away.
    """
    violations = []
    for path in _iter_modules():
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.ClassDef):
                continue
            for name, lines in _class_level_bindings(node).items():
                if len(lines) > 1:
                    violations.append(f"{_rel(path)}: `{node.name}.{name}` bound at lines {lines}")
    assert not violations, "duplicate class-body binding(s):\n" + "\n".join(violations)


# ---------------------------------------------------------------------- (b)


def test_no_duplicate_public_name_across_package_siblings():
    """Two sibling modules of one package never define the same public
    top-level name.

    Private (`_`-prefixed) names are exempt: every module in `machines/`
    already carries its own unrelated `_helper`-shaped names, and nothing
    combines their namespaces except an explicit, curated `__all__` import -
    which (d) checks separately. What would actually break silently is a
    *public* name a facade might import from either of two modules and get
    whichever import happened to run last.
    """
    violations = []
    for package in _split_packages():
        owners: dict[str, list[str]] = {}
        for path in sorted(package.glob("*.py")):
            if path.name == "__init__.py":
                continue
            for name in _top_level_bindings(_parse(path)):
                if name.startswith("_"):
                    continue
                owners.setdefault(name, []).append(path.name)
        for name, files in owners.items():
            if len(files) > 1:
                violations.append(f"{package.name}/: `{name}` defined in {files}")
    assert not violations, "duplicate public name across package siblings:\n" + "\n".join(
        violations
    )


# ---------------------------------------------------------------------- (c)


def _classes_by_module(modules: list[pathlib.Path]) -> dict[pathlib.Path, dict[str, ast.ClassDef]]:
    out: dict[pathlib.Path, dict[str, ast.ClassDef]] = {}
    for path in modules:
        out[path] = {n.name: n for n in _parse(path).body if isinstance(n, ast.ClassDef)}
    return out


def _local_class_map(
    package: pathlib.Path, classes_by_module: dict[pathlib.Path, dict[str, ast.ClassDef]]
) -> dict[str, tuple[pathlib.Path, ast.ClassDef]]:
    """name -> (defining module, ClassDef) for every class reachable from
    `package`: one defined directly in one of its sibling modules, or one
    imported into a sibling module from another sibling module (`from
    ._zones import ZonesMixin`) - the shape `models/game/` will use once S4
    lands its mixins."""
    siblings = sorted(p for p in package.glob("*.py"))
    local: dict[str, tuple[pathlib.Path, ast.ClassDef]] = {}
    for path in siblings:
        for name, node in classes_by_module.get(path, {}).items():
            local[name] = (path, node)
    for path in siblings:
        for node in _parse(path).body:
            if isinstance(node, ast.ImportFrom) and (node.level or 0) >= 1:
                for alias in node.names:
                    imported_as = alias.asname or alias.name
                    if imported_as in local:
                        continue
                    for other in siblings:
                        classes = classes_by_module.get(other, {})
                        if alias.name in classes:
                            local[imported_as] = (other, classes[alias.name])
                            break
    return local


def _own_method_names(class_def: ast.ClassDef) -> set[str]:
    return {
        n.name
        for n in class_def.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not _is_setter_like(n)
    }


def test_no_duplicate_method_name_across_mixin_bases():
    """No two locally-resolvable base classes of one composite class define
    the same method name.

    Nothing in this codebase does multiple inheritance from local mixins
    yet, so this runs against zero composite classes today and passes
    vacuously - it exists so the mechanism is already proven correct before
    S4 turns `Game` into one, where two mixins quietly defining the same
    method would shadow each other through the MRO with no error at all.
    """
    modules = _iter_modules()
    classes_by_module = _classes_by_module(modules)
    violations = []
    for package in _split_packages():
        local = _local_class_map(package, classes_by_module)
        for path in sorted(package.glob("*.py")):
            for class_def in classes_by_module.get(path, {}).values():
                resolved_bases = []
                for base in class_def.bases:
                    if isinstance(base, ast.Name) and base.id in local:
                        resolved_bases.append((base.id, *local[base.id]))
                if len(resolved_bases) < 2:
                    continue
                seen: dict[str, str] = {}
                for base_name, _base_path, base_node in resolved_bases:
                    for method in _own_method_names(base_node):
                        prior = seen.get(method)
                        if prior is not None and prior != base_name:
                            violations.append(
                                f"{_rel(path)}: `{class_def.name}` mixes `{prior}` and "
                                f"`{base_name}`, both defining `{method}`"
                            )
                        else:
                            seen[method] = base_name
    assert not violations, "duplicate method name across mixin bases:\n" + "\n".join(violations)


# ---------------------------------------------------------------------- (d)


def _all_names(init_tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(init_tree):
        is_all_assign = isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        )
        if is_all_assign and isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            names.update(
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            )
    return names


def test_facade_names_resolve_to_one_definition():
    """Every name a package's `__init__.py` re-exports through `__all__`
    must be defined in exactly one place reachable from that package: a
    sibling module, a module of a sibling package (`machines/effects/` once
    the split makes `effects.py` one; a name defined twice inside it counts
    twice), or (`magic_cards_model/__init__.py`'s own `__version__`) the
    `__init__.py` file itself."""
    violations = []
    for package in _packages():
        init_path = package / "__init__.py"
        exported = _all_names(_parse(init_path))
        if not exported:
            continue
        owners: dict[str, list[str]] = {}
        for path in sorted(package.glob("*.py")):
            for name in _top_level_bindings(_parse(path)):
                owners.setdefault(name, []).append(path.name)
        for sub_init in sorted(package.glob("*/__init__.py")):
            for path in sorted(sub_init.parent.rglob("*.py")):
                for name in _top_level_bindings(_parse(path)):
                    owners.setdefault(name, []).append(_rel(path))
        for name in sorted(exported):
            files = owners.get(name, [])
            if len(files) != 1:
                where = files or ["<no sibling module defines it>"]
                violations.append(f"{package.name}/__init__.py: `{name}` -> {where}")
    assert not violations, "facade name does not resolve to exactly one definition:\n" + "\n".join(
        violations
    )
