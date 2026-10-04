#!/usr/bin/env python
"""Freeze the old-path surface that every split facade must keep.

    uv run python scripts/split/surface.py          # compare, exit 1 on drift
    uv run python scripts/split/surface.py --write  # regenerate all eight files

For each of the seven modules in `TARGETS` this writes
`scripts/split/surface/<short>.json` with sorted `defined` (every name bound
at module top level by def/class/assign/annassign, also inside top-level
if/try blocks, privates included), sorted `imported` (names bound by import
statements, `if TYPE_CHECKING:` bodies excluded), `module` (dotted old path)
and `captured_at` (engine commit sha). It also writes `game_class.json` with
`dir(Game)` and `Game.model_fields` in declaration order.

`tests/test_split_surface.py` is the gate that reads these files. Compare mode
ignores `captured_at`, so a new commit alone is not drift.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import importlib
import importlib.util
import json
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SURFACE_DIR = pathlib.Path(__file__).resolve().parent / "surface"
PKG = "magic_cards_model"

TARGETS: dict[str, str] = {
    "effects": f"{PKG}.machines.effects",
    "game": f"{PKG}.models.game",
    "layers": f"{PKG}.machines.layers",
    "replacement": f"{PKG}.machines.replacement",
    "casting": f"{PKG}.machines.casting",
    "triggers": f"{PKG}.machines.triggers",
    "cost": f"{PKG}.machines.cost",
}


def _target_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [n for elt in target.elts for n in _target_names(elt)]
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    return []


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _walk(body: list[ast.stmt], defined: set[str], imported: set[str], type_checking: bool) -> None:
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                defined.update(_target_names(target))
        elif isinstance(node, ast.AnnAssign):
            defined.update(_target_names(node.target))
        elif isinstance(node, ast.Import):
            if not type_checking:
                imported.update(a.asname or a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if not type_checking and node.module != "__future__":
                imported.update(a.asname or a.name for a in node.names if a.name != "*")
        elif isinstance(node, ast.If):
            _walk(node.body, defined, imported, type_checking or _is_type_checking(node.test))
            _walk(node.orelse, defined, imported, type_checking)
        elif isinstance(node, ast.Try):
            for part in (node.body, node.orelse, node.finalbody, *(h.body for h in node.handlers)):
                _walk(part, defined, imported, type_checking)


def _scan(tree: ast.Module) -> tuple[set[str], set[str]]:
    defined: set[str] = set()
    imported: set[str] = set()
    _walk(tree.body, defined, imported, False)
    return defined, imported


def top_level_bindings(tree: ast.Module) -> set[str]:
    """Names bound at module top level by def/class/assign/annassign,
    including inside top-level if/try blocks (the snapshot's `defined`)."""
    return _scan(tree)[0]


def top_level_imports(tree: ast.Module) -> set[str]:
    """Names bound at module top level by import statements, TYPE_CHECKING-only
    imports excluded (the snapshot's `imported`)."""
    return _scan(tree)[1]


def _module_files(dotted: str) -> list[pathlib.Path]:
    """The source file of a plain module, or every file of a package."""
    spec = importlib.util.find_spec(dotted)
    assert spec is not None and spec.origin, dotted
    origin = pathlib.Path(spec.origin)
    if spec.submodule_search_locations is None:
        return [origin]
    return sorted(origin.parent.rglob("*.py"))


def _engine_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _capture_module(dotted: str, sha: str) -> dict:
    defined: set[str] = set()
    imported: set[str] = set()
    files = _module_files(dotted)
    for path in files:
        d, i = _scan(ast.parse(path.read_text(), filename=str(path)))
        defined |= d
        # A package's own namespace only imports in its `__init__`.
        if len(files) == 1 or path == min(files, key=lambda f: len(f.parts)):
            imported |= i
    return {
        "captured_at": sha,
        "defined": sorted(defined),
        "imported": sorted(imported),
        "module": dotted,
    }


def _capture_game_class() -> dict:
    from magic_cards_model.models.game import Game

    return {"dir": sorted(set(dir(Game))), "model_fields": list(Game.model_fields)}


def capture() -> dict[str, dict]:
    sha = _engine_sha()
    snaps = {short: _capture_module(dotted, sha) for short, dotted in TARGETS.items()}
    snaps["game_class"] = _capture_game_class()
    return snaps


def render(snap: dict) -> str:
    return json.dumps(snap, sort_keys=True, indent=2) + "\n"


def _comparable(text: str) -> str:
    data = json.loads(text)
    data.pop("captured_at", None)
    return render(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="regenerate all snapshot files")
    args = parser.parse_args(argv)
    snaps = capture()
    if args.write:
        SURFACE_DIR.mkdir(parents=True, exist_ok=True)
        for short, snap in snaps.items():
            (SURFACE_DIR / f"{short}.json").write_text(render(snap))
        print(f"wrote {len(snaps)} snapshots to {SURFACE_DIR.relative_to(REPO_ROOT)}")
        return 0
    drift = False
    for short, snap in snaps.items():
        path = SURFACE_DIR / f"{short}.json"
        rel = path.relative_to(REPO_ROOT)
        if not path.exists():
            print(f"MISSING {rel}")
            drift = True
            continue
        old, new = _comparable(path.read_text()), _comparable(render(snap))
        if old != new:
            drift = True
            sys.stdout.writelines(
                difflib.unified_diff(
                    old.splitlines(True),
                    new.splitlines(True),
                    f"{rel} (committed)",
                    f"{rel} (current)",
                )
            )
    if drift:
        print("surface drift: review, then rerun with --write", file=sys.stderr)
        return 1
    print("surface unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
