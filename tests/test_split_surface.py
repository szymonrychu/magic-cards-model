"""Facade gate for the engine module split (design "Back-compat").

`scripts/split/surface/*.json` freeze, at the base commit, every top-level
name of the seven big old-path modules (`machines.effects`, `models.game`,
`machines.layers`, `machines.replacement`, `machines.casting`,
`machines.triggers`, `machines.cost`) plus `dir(Game)` and
`Game.model_fields`. This test passes on today's monolith and must keep
passing once each old path becomes a facade package over family modules.

Names added on main after the capture are not in a snapshot and are not
checked. A snapshot name removed from main fails (a); that is intended - the
freeze run recaptures with `scripts/split/surface.py --write` at F1 start.

(a) every `defined` and `imported` name resolves through the old path.
(b) every `defined` name is defined (AST top-level binding, the same rules
    the snapshot used) in exactly one module of the old path, and the old
    path exposes that very object.
(c) the three registry dicts are the same objects as in the defining module.
(d) `set(dir(Game))` and `list(Game.model_fields)` (order included) match.
(e) every pydantic model among the `defined` names is fully built
    (`__pydantic_complete__ is True`), i.e. its forward references resolve.
    This is how "the surface test instantiates every moved model" is met
    without inventing constructor arguments for hundreds of models.
"""

from __future__ import annotations

import ast
import functools
import importlib
import json
import pathlib
import pkgutil

import pytest
from pydantic import BaseModel
from scripts.split.surface import SURFACE_DIR, TARGETS, top_level_bindings

REGISTRIES = ("EFFECTS", "TRIGGER_EFFECTS", "ACTIVATED_EFFECTS")


def _load(short: str) -> dict:
    return json.loads((SURFACE_DIR / f"{short}.json").read_text())


@functools.cache
def _owners(old_path: str) -> dict[str, tuple]:
    """name -> every module of the old path whose own source defines it."""
    module = importlib.import_module(old_path)
    if hasattr(module, "__path__"):
        # the package's own __init__ defines names too (Game stays in models/game/__init__)
        candidates = [module] + [
            importlib.import_module(info.name)
            for info in pkgutil.walk_packages(module.__path__, old_path + ".")
        ]
    else:
        candidates = [module]
    owners: dict[str, list] = {}
    for candidate in candidates:
        tree = ast.parse(pathlib.Path(candidate.__file__).read_text())
        for name in top_level_bindings(tree):
            owners.setdefault(name, []).append(candidate)
    return {name: tuple(mods) for name, mods in owners.items()}


def _defining_modules(old_path: str, name: str) -> tuple:
    return _owners(old_path).get(name, ())


@pytest.mark.parametrize("short", sorted(TARGETS))
def test_snapshot_names_resolve(short):
    snap = _load(short)
    module = importlib.import_module(snap["module"])
    missing = [n for n in snap["defined"] + snap["imported"] if not hasattr(module, n)]
    assert not missing, f"{snap['module']} lost {len(missing)} name(s): {missing[:20]}"


@pytest.mark.parametrize("short", sorted(TARGETS))
def test_defined_names_have_exactly_one_owner(short):
    snap = _load(short)
    module = importlib.import_module(snap["module"])
    problems = []
    for name in snap["defined"]:
        owners = _defining_modules(snap["module"], name)
        if len(owners) != 1:
            problems.append(f"{name}: defined in {[o.__name__ for o in owners]}")
        elif getattr(module, name) is not getattr(owners[0], name):
            problems.append(f"{name}: facade object is not the one in {owners[0].__name__}")
    assert not problems, "\n".join(problems[:30])


@pytest.mark.parametrize("short", sorted(TARGETS))
def test_registry_dicts_are_shared_objects(short):
    snap = _load(short)
    module = importlib.import_module(snap["module"])
    for name in REGISTRIES:
        if name not in snap["defined"]:
            continue
        (owner,) = _defining_modules(snap["module"], name)
        assert getattr(module, name) is getattr(owner, name), name


def test_game_class_surface_unchanged():
    from magic_cards_model.models.game import Game

    snap = json.loads((SURFACE_DIR / "game_class.json").read_text())
    assert sorted(set(dir(Game))) == snap["dir"]
    assert list(Game.model_fields) == snap["model_fields"]


@pytest.mark.parametrize("short", sorted(TARGETS))
def test_pydantic_models_are_complete(short):
    snap = _load(short)
    module = importlib.import_module(snap["module"])
    incomplete = []
    for name in snap["defined"]:
        obj = getattr(module, name)
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and obj.__pydantic_complete__ is not True
        ):
            incomplete.append(name)
    assert not incomplete, f"unresolved forward references: {incomplete}"
