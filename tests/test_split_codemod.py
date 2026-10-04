"""P0-T06: manifest-driven module and Game-mixin codemod (scripts/split/codemod.py).

Tooling tests on small fixture packages under tests/fixtures/split/codemod/; nothing
here runs the codemod over the real engine modules (that is the dry run's job).
"""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.split import codemod

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures" / "split" / "codemod"
MOD = FIX / "mod.toml"
SURFACE = FIX / "surface_mod.json"
OLD_MOD = (FIX / "root" / "fxtop" / "pk" / "mod.py").read_text()


@pytest.fixture(scope="module")
def mod_files() -> dict[str, str]:
    return codemod.build(MOD, surface=SURFACE).files


def defs(text: str) -> list[str]:
    return [n.name for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]


def parse_all(text: str) -> list[str]:
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "__all__":
            return list(ast.literal_eval(node.value))
    raise AssertionError("no __all__")


def run_py(root: Path, code: str) -> str:
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(root), "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        cwd=root,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


PROBE_MOD = """
import fxtop.pk.mod as m
from fxtop.pk.sibling import SibT
print(m.dispatch_run("one", "caab"), m.text_two(SibT(), m.Wide()))
skip = ("text", "dispatch", "_common")
print(sorted(n for n in dir(m) if not n.startswith("__") and n not in skip))
"""


# ------------------------------------------------------------------ module mode


def test_statements_are_byte_identical_with_decorator_and_leading_comments(mod_files):
    start = OLD_MOD.index("# leading comment line one")
    end = OLD_MOD.index("def text_two")
    sliced = OLD_MOD[start:end].rstrip("\n")
    # only the two lazy relative imports gain a dot; no other byte of the body changes
    expected = sliced.replace("from . import sibling", "from .. import sibling").replace(
        "from .sibling import lazy_sib", "from ..sibling import lazy_sib"
    )
    assert expected in mod_files["text.py"]


def test_stable_partition_keeps_source_order(mod_files):
    assert defs(mod_files["text.py"]) == ["text_one", "text_two", "stray_new_helper"]
    assert defs(mod_files["dispatch.py"]) == ["dispatch_run", "_private_dispatch_tag"]
    assert defs(mod_files["_common.py"]) == ["decorate", "Wide"]


def test_unlisted_new_name_follows_its_preceding_neighbour(mod_files):
    # stray_new_helper matches no rule or name; it sits after text_two
    assert "def stray_new_helper" in mod_files["text.py"]


def test_imports_pruned_and_relative_imports_one_level_deeper(mod_files):
    text = mod_files["text.py"]
    assert "from ...top_helper import top" in text  # was `from ..top_helper`
    assert "from ..sibling import sib" in text  # was `from .sibling`
    assert "from ..sibling import SibT" in text  # TYPE_CHECKING block rewritten too
    assert "Callable" not in text and "Callable" in mod_files["_common.py"]
    assert "import re" in text and "import re" not in mod_files["dispatch.py"]
    assert "top_helper" not in mod_files["dispatch.py"]


def test_eager_imports_on_top_deferred_at_the_bottom_with_noqa(mod_files):
    text = mod_files["text.py"]
    body = ast.parse(text).body
    first_def = next(i for i, n in enumerate(body) if isinstance(n, ast.FunctionDef))
    eager = [n for n in body[:first_def] if isinstance(n, ast.ImportFrom) and n.level == 1]
    assert [(n.module, [a.name for a in n.names]) for n in eager] == [("_common", ["decorate"])]
    tail = text.rstrip().splitlines()[-1]
    assert tail == "from ._common import Wide  # noqa: E402"
    disp = mod_files["dispatch.py"]
    assert "from .text import text_one, text_two" in disp.split("def ")[0]
    assert disp.rstrip().splitlines()[-1] == "from .text import stray_new_helper  # noqa: E402"


def test_facade_is_explicit_with_exact_all_and_reexports(mod_files):
    init = mod_files["__init__.py"]
    assert "import *" not in init
    defined = {
        "DISPATCH",
        "PATTERN",
        "TABLE_NAMES",
        "Wide",
        "_private_dispatch_tag",
        "decorate",
        "dispatch_run",
        "stray_new_helper",
        "text_one",
        "text_two",
    }
    assert parse_all(init) == sorted(defined)
    assert "from .text import" in init and "_private_dispatch_tag" in init
    # old imported names the snapshot lists, from their origin, one level deeper, not in __all__
    for line in (
        "from ..sibling import sib as sib",
        "from ...top_helper import top as top",
        "import re as re",
        "from typing import TYPE_CHECKING as TYPE_CHECKING",
        "from collections.abc import Callable as Callable",
    ):
        assert line in init
    assert not {"sib", "top", "re", "Callable", "TYPE_CHECKING"} & set(parse_all(init))
    assert init.startswith('"""Fixture: module mode')


def test_facade_imports_family_modules_in_eager_topological_order(mod_files):
    init = mod_files["__init__.py"]
    pos = {m: init.index(f"from .{m} import") for m in ("_common", "text", "dispatch")}
    assert pos["_common"] < pos["text"] < pos["dispatch"]  # manifest order is dispatch first


def test_new_package_behaves_like_the_old_module(tmp_path):
    result = codemod.build(MOD, surface=SURFACE)
    shadow = codemod.shadow_tree(result, tmp_path / "shadow")
    old = run_py(FIX / "root", PROBE_MOD)
    new = run_py(shadow, PROBE_MOD)
    assert old == new
    assert "sibt" in new


# -------------------------------------------------------------- output hygiene


@pytest.mark.parametrize("name", ["mod", "dfr", "game"])
def test_output_passes_ruff_check_and_format(name, tmp_path):
    out = tmp_path / name
    assert codemod.main([str(FIX / f"{name}.toml"), "--out", str(out)]) == 0
    assert (out / "__init__.py").is_file()
    cfg = ["--config", str(ROOT / "pyproject.toml")]
    for cmd in (["check", "--no-cache"], ["format", "--check"]):
        res = subprocess.run(
            [sys.executable, "-m", "ruff", cmd[0], *cfg, *cmd[1:], str(out)],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert res.returncode == 0, res.stdout + res.stderr


def test_out_dir_leaves_the_source_tree_alone(tmp_path):
    before = sorted(p.relative_to(FIX) for p in FIX.rglob("*") if "__pycache__" not in p.parts)
    assert codemod.main([str(MOD), "--out", str(tmp_path / "o")]) == 0
    after = sorted(p.relative_to(FIX) for p in FIX.rglob("*") if "__pycache__" not in p.parts)
    assert before == after
    assert (tmp_path / "o" / "text.py").is_file()


def test_default_run_removes_old_module_and_creates_package(tmp_path, monkeypatch):
    work = tmp_path / "work"
    shutil.copytree(FIX, work, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.chdir(work)
    assert codemod.main(["mod.toml", "--surface", "surface_mod.json"]) == 0
    pk = work / "root" / "fxtop" / "pk"
    assert not (pk / "mod.py").exists()
    assert {p.name for p in (pk / "mod").iterdir()} >= {"__init__.py", "text.py", "dispatch.py"}
    assert "stray_new_helper" in run_py(work / "root", "import fxtop.pk.mod as m; print(dir(m))")


def test_check_mode_imports_in_a_subprocess_and_touches_nothing(capsys):
    before = sorted((p, p.stat().st_mtime_ns) for p in FIX.rglob("*") if p.is_file())
    assert codemod.main([str(MOD), "--check", "--surface", str(SURFACE)]) == 0
    assert sorted((p, p.stat().st_mtime_ns) for p in FIX.rglob("*") if p.is_file()) == before
    assert "ok" in capsys.readouterr().out


def test_script_runs_standalone():
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "split" / "codemod.py"), str(MOD), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert res.returncode == 0, res.stdout + res.stderr


# ----------------------------------------------------------- cycles and verify


def test_eager_cycle_is_refused_and_nothing_is_written(tmp_path, capsys):
    out = tmp_path / "out"
    assert codemod.main([str(FIX / "cyc.toml"), "--out", str(out)]) == 1
    text = capsys.readouterr()
    shown = text.out + text.err
    assert "a, b" in shown and "b_one" in shown and "a_one" in shown
    assert not out.exists() or not any(out.iterdir())
    with pytest.raises(codemod.CycleError):
        codemod.build(FIX / "cyc.toml")


def test_deferred_mutual_reference_imports_in_either_order(tmp_path):
    result = codemod.build(FIX / "dfr.toml")
    assert result.files["a.py"].rstrip().endswith("# noqa: E402")
    assert result.files["b.py"].rstrip().endswith("# noqa: E402")
    shadow = codemod.shadow_tree(result, tmp_path / "shadow")
    expected = run_py(FIX / "root", "from fxtop.pk.dfr import a_start; print(a_start(5))")
    for first in ("a", "b"):
        got = run_py(
            shadow,
            f"import fxtop.pk.dfr.{first}\nfrom fxtop.pk.dfr import a_start; print(a_start(5))",
        )
        assert got == expected


def test_verify_catches_a_corrupted_slice(tmp_path, monkeypatch):
    real = codemod._chunk_text

    def corrupt(*args, **kwargs):
        return real(*args, **kwargs).replace("return PATTERN.sub", "return 0 + PATTERN.sub")

    monkeypatch.setattr(codemod, "_chunk_text", corrupt)
    with pytest.raises(codemod.VerifyError) as err:
        codemod.build(MOD)
    assert "text_one" in str(err.value)
    out = tmp_path / "out"
    assert codemod.main([str(MOD), "--out", str(out)]) == 1
    assert not out.exists() or not any(out.iterdir())


# -------------------------------------------------------------------- class mode


@pytest.fixture(scope="module")
def game_files() -> dict[str, str]:
    return codemod.build(FIX / "game.toml").files


def class_body(text: str, name: str) -> list[ast.stmt]:
    for node in ast.parse(text).body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node.body
    raise AssertionError(name)


def test_class_mode_init_keeps_shell_fields_validators_and_stay(game_files):
    init = game_files["__init__.py"]
    shell = next(
        n for n in ast.parse(init).body if isinstance(n, ast.ClassDef) and n.name == "Game"
    )
    assert [ast.unparse(b) for b in shell.bases] == ["CombatMixin", "LibraryMixin", "BaseModel"]
    names = [getattr(b, "name", None) for b in shell.body if isinstance(b, ast.FunctionDef)]
    assert names == ["check_life", "check_all", "settle_pregame"]
    fields = [ast.unparse(b.target) for b in shell.body if isinstance(b, ast.AnnAssign)]
    assert fields == ["CURRENT_SCHEMA_VERSION", "life", "records"]
    assert "from .helpers import ask_mulligan" in init.replace("..helpers", ".helpers")
    assert "Game.model_rebuild()" in init


def test_class_mode_mixin_has_methods_only_and_annotated_self(game_files):
    text = game_files["combat.py"]
    body = class_body(text, "CombatMixin")
    assert all(isinstance(b, ast.FunctionDef) for b in body)  # no class-level annotations
    assert [b.name for b in body] == ["combat_a", "combat_b", "static_one", "combat_c"]
    assert 'def combat_a(self: "Game") -> int:' in text
    assert 'def combat_c(self: "Game") -> int:' in text  # already annotated, left alone
    assert "def static_one() -> int:" in text
    assert "if TYPE_CHECKING:\n    from . import Game" in text
    lib = game_files["library.py"]
    assert '# leading comment for draw_one\n    def draw_one(self: "Game", n: int = 1)' in lib
    assert "def cls_one(cls) -> int:" in lib
    assert "from ..helpers import ask_mulligan as ask" in lib  # lazy import, one level deeper


def test_class_mode_records_and_reexports(game_files):
    records = game_files["records.py"]
    assert defs(records) == ["Record", "module_helper"]
    init = game_files["__init__.py"]
    assert parse_all(init) == ["Game", "Record", "module_helper"]
    assert "from .records import Record, module_helper" in init
    assert "import *" not in init
    assert (
        game_files["combat.py"]
        .rstrip()
        .endswith("from .records import module_helper  # noqa: E402")
    )


PROBE_GAME = """
import fxtop.game as gm
g = gm.Game()
print(list(gm.Game.model_fields), sorted(dir(gm.Game)))
print(g.combat_a(), g.draw_one(), g.static_one(), g.cls_one(), g.combat_c(), g.settle_pregame())
gm.ask_mulligan = lambda game: "patched"
print(g.settle_pregame())
print(gm.Game.model_validate({"life": 3}).life, gm.Game.CURRENT_SCHEMA_VERSION)
"""


def test_class_mode_behaves_like_the_old_class_and_stay_name_is_patchable(tmp_path):
    result = codemod.build(FIX / "game.toml")
    shadow = codemod.shadow_tree(result, tmp_path / "shadow")
    old = run_py(FIX / "root", PROBE_GAME)
    new = run_py(shadow, PROBE_GAME)
    # dir(Game) differs only by the mixin base classes' absence of extra public names
    assert old.splitlines()[1:] == new.splitlines()[1:]
    assert old.splitlines()[0] == new.splitlines()[0]
    assert "patched" in new


def test_class_mode_runtime_reference_into_init_is_refused(tmp_path):
    work = tmp_path / "w"
    shutil.copytree(FIX, work, ignore=shutil.ignore_patterns("__pycache__"))
    game = work / "root" / "fxtop" / "game.py"
    game.write_text(
        game.read_text().replace("return self.combat_b() + module_helper()", "return Game().life")
    )
    with pytest.raises(codemod.CodemodError, match="Game"):
        codemod.build(work / "game.toml")


def test_wrapped_signature_after_a_self_annotation_is_accepted_and_reported(tmp_path):
    work = tmp_path / "w"
    shutil.copytree(FIX, work, ignore=shutil.ignore_patterns("__pycache__"))
    long_def = (
        "    def combat_long_signature(self, first_argument: int, "
        "second_argument: int, third: int) -> int:"
    )
    assert 92 < len(long_def) <= 100 and len(long_def) + len(': "Game"') > 100
    game = work / "root" / "fxtop" / "game.py"
    game.write_text(
        game.read_text().replace(
            "    def combat_c(self",
            f"{long_def}\n        return 8\n\n    def combat_c(self",
        )
    )
    result = codemod.build(work / "game.toml")
    assert "def combat_long_signature(\n        self: " in result.files["combat.py"]
    assert any("re-wrapped" in w and "combat_long_signature" in w for w in result.warnings)


# ------------------------------------------------------------- import ordering


def test_facade_order_keeps_deferred_imports_from_reaching_a_module_early(tmp_path):
    result = codemod.build(FIX / "ord.toml")
    init = result.files["__init__.py"]
    # manifest order is m, n, d; importing m first would load n before d exists
    assert (
        init.index("from .d import") < init.index("from .n import") < init.index("from .m import")
    )
    shadow = codemod.shadow_tree(result, tmp_path / "shadow")
    call = "from fxtop.pk.ord import m_call, d_call; print(m_call(), d_call(3))"
    assert run_py(shadow, call) == run_py(FIX / "root", call)


def test_unsatisfiable_import_order_is_refused_with_the_reason(tmp_path, capsys):
    with pytest.raises(codemod.CodemodError, match="no import order"):
        codemod.build(FIX / "unsat.toml")
    out = tmp_path / "out"
    assert codemod.main([str(FIX / "unsat.toml"), "--out", str(out)]) == 1
    assert "still at its own imports" in capsys.readouterr().err
    assert not out.exists()


def test_unquoted_function_annotation_is_an_eager_reference(tmp_path):
    result = codemod.build(FIX / "ann.toml")
    top = result.files["a.py"].split("def ")[0]
    assert "from .b import Shape" in top  # a_sides(shape: Shape) runs at def time
    assert "# noqa: E402" not in result.files["a.py"]
    shadow = codemod.shadow_tree(result, tmp_path / "shadow")
    probe = "from fxtop.pk.ann import a_sides, Shape; print(a_sides(Shape()))"
    assert run_py(shadow, probe) == run_py(FIX / "root", probe)


def test_eager_annotation_reference_closes_a_cycle(tmp_path):
    work = tmp_path / "w"
    shutil.copytree(FIX, work, ignore=shutil.ignore_patterns("__pycache__"))
    src = work / "root" / "fxtop" / "pk" / "ann.py"
    src.write_text(src.read_text() + '\n\nB_TABLE = {"k": a_sides}\n')
    manifest = work / "ann.toml"
    manifest.write_text(manifest.read_text() + '\n[[rules]]\npattern = "B_.*"\ntarget = "b"\n')
    with pytest.raises(codemod.CycleError, match="a_sides|Shape"):
        codemod.build(manifest)


@pytest.mark.parametrize("name", ["ann", "cyc", "dfr", "game", "mod", "ord", "unsat"])
def test_codemod_graph_agrees_with_manifest_lib(name):
    """One eager/deferred classification: the codemod's import graph is
    manifest_lib's, unquoted function annotations of a module without the
    future import included."""
    manifest = codemod.ml.load_manifest(FIX / f"{name}.toml")
    text = codemod.source_path(manifest).read_text()
    plan = codemod.Plan(manifest, text, None)
    lib = codemod.ml.build_graph(codemod.ml.resolve(text, manifest))
    assert plan.graph.edges == lib.edges
    assert sorted(plan.graph.refs, key=repr) == sorted(lib.refs, key=repr)


def _game_with_init_helper(tmp_path: Path, extra_game: str = "") -> Path:
    """The game fixture with `module_helper` (a def before `class Game`) kept in
    the package __init__, a records class and a mixin both calling it at runtime."""
    work = tmp_path / "w"
    shutil.copytree(FIX, work, ignore=shutil.ignore_patterns("__pycache__"))
    game = work / "root" / "fxtop" / "game.py"
    text = game.read_text().replace(
        "class Record(BaseModel):\n    value: int = 0\n",
        "class Record(BaseModel):\n    value: int = 0\n\n"
        "    def helped(self) -> int:\n        return module_helper() + self.value\n",
    )
    game.write_text(text + extra_game)
    manifest = work / "game.toml"
    manifest.write_text(
        manifest.read_text().replace(
            "[[rules]]", '[names]\nmodule_helper = "__init__"\n\n[[rules]]', 1
        )
    )
    return manifest


PROBE_INIT_HELPER = """
import fxtop.game as gm
print(gm.Game().combat_a(), gm.Record(value=4).helped(), gm.module_helper())
"""


def test_class_mode_init_statement_used_at_runtime_by_a_mixin_and_records(tmp_path):
    manifest = _game_with_init_helper(tmp_path)
    result = codemod.build(manifest)
    init = result.files["__init__.py"]
    # defined in __init__ before the facade imports any family module
    assert init.index("def module_helper()") < init.index("from .combat import")
    assert init.index("def module_helper()") < init.index("from .records import")
    assert "def module_helper" not in result.files["records.py"]
    for name in ("combat.py", "records.py"):
        tail = result.files[name].rstrip().split("\n")[-1]
        assert tail == "from . import module_helper  # noqa: E402", name
    shadow = codemod.shadow_tree(result, tmp_path / "shadow")
    old_root = manifest.parent / "root"
    assert run_py(shadow, PROBE_INIT_HELPER) == run_py(old_root, PROBE_INIT_HELPER)
    assert run_py(shadow, PROBE_GAME) == run_py(old_root, PROBE_GAME)


def test_class_mode_init_statement_needing_a_family_module_at_import(tmp_path):
    """`HELPER_RECORD = Record()` needs the records module when __init__ runs, so it is
    written after the facade imports: fine on its own, refused once a mixin uses it."""
    manifest = _game_with_init_helper(tmp_path)
    game = manifest.parent / "root" / "fxtop" / "game.py"
    game.write_text(
        game.read_text().replace(
            "def module_helper() -> int:",
            "HELPER_RECORD = Record()\n\n\ndef module_helper() -> int:",
        )
    )
    manifest.write_text(
        manifest.read_text().replace("[names]\n", '[names]\nHELPER_RECORD = "__init__"\n')
    )
    result = codemod.build(manifest)
    init = result.files["__init__.py"]
    assert (
        init.index("def module_helper()")
        < init.index("from .records import")
        < init.index("HELPER_RECORD = Record()")
    )
    shadow = codemod.shadow_tree(result, tmp_path / "shadow")
    probe = PROBE_INIT_HELPER + "print(gm.HELPER_RECORD.value)\n"
    assert run_py(shadow, probe) == run_py(manifest.parent / "root", probe)

    game.write_text(
        game.read_text().replace(
            "return self.combat_b() + module_helper()",
            "return self.combat_b() + HELPER_RECORD.value",
        )
    )
    with pytest.raises(codemod.CodemodError, match="HELPER_RECORD needs Record"):
        codemod.build(manifest)


def test_init_with_early_statements_passes_ruff_check_and_format(tmp_path):
    manifest = _game_with_init_helper(tmp_path)
    out = tmp_path / "out"
    assert codemod.main([str(manifest), "--out", str(out)]) == 0
    cfg = ["--config", str(ROOT / "pyproject.toml")]
    for cmd in (["check", "--no-cache"], ["format", "--check"]):
        res = subprocess.run(
            [sys.executable, "-m", "ruff", cmd[0], *cfg, *cmd[1:], str(out)],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "warning" not in res.stderr.lower(), res.stderr


LONG_NAME = "helper_whose_name_is_long_enough_that_its_explicit_reexport_cannot_fit"


def _long_reexport(tmp_path: Path) -> tuple[Path, Path]:
    """A module whose surface re-exports an imported name too long for `X as X` to fit
    on one line, even wrapped in parentheses."""
    work = tmp_path / "w"
    shutil.copytree(FIX, work, ignore=shutil.ignore_patterns("__pycache__"))
    pk = work / "root" / "fxtop" / "pk"
    (pk / "longnames.py").write_text(f"def {LONG_NAME}() -> int:\n    return 1\n")
    (pk / "lng.py").write_text(
        '"""Fixture: a long re-exported import."""\n\n'
        f"from .longnames import (\n    {LONG_NAME},\n)\n\n\n"
        f"def lng_one() -> int:\n    return {LONG_NAME}()\n\n\n"
        "def lng_two() -> int:\n    return 2\n"
    )
    manifest = work / "lng.toml"
    manifest.write_text(
        'module = "fxtop.pk.lng"\nsource = "root/fxtop/pk/lng.py"\n'
        'package = "root/fxtop/pk/lng"\nmode = "module"\ntargets = ["one", "two"]\n\n'
        '[[rules]]\npattern = "lng_one"\ntarget = "one"\n\n'
        '[[rules]]\npattern = "lng_two"\ntarget = "two"\n'
    )
    surface = work / "surface_lng.json"
    surface.write_text(
        '{"defined": ["lng_one", "lng_two"], "imported": ["' + LONG_NAME + '"], '
        '"module": "fxtop.pk.lng"}\n'
    )
    return manifest, surface


def test_unwrappable_long_reexport_passes_ruff_with_the_repo_config(tmp_path):
    manifest, surface = _long_reexport(tmp_path)
    out = tmp_path / "out"
    assert codemod.main([str(manifest), "--surface", str(surface), "--out", str(out)]) == 0
    init = (out / "__init__.py").read_text()
    assert f"{LONG_NAME} as {LONG_NAME}" in init
    cfg = ["--config", str(ROOT / "pyproject.toml")]
    for cmd in (["check", "--no-cache"], ["format", "--check"]):
        res = subprocess.run(
            [sys.executable, "-m", "ruff", cmd[0], *cfg, *cmd[1:], str(out)],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert res.returncode == 0, res.stdout + res.stderr


def test_long_reexport_line_carries_its_own_e501_marker_and_nothing_else_does(tmp_path):
    manifest, surface = _long_reexport(tmp_path)
    files = codemod.build(manifest, surface=surface).files
    long_lines = [ln for text in files.values() for ln in text.split("\n") if len(ln) > 100]
    assert long_lines
    assert all(ln.endswith("# noqa: E501") for ln in long_lines), long_lines
    short_marked = [
        ln for text in files.values() for ln in text.split("\n")
        if "E501" in ln and len(ln) <= 100
    ]  # fmt: skip
    assert short_marked == []
    shadow = codemod.shadow_tree(codemod.build(manifest, surface=surface), tmp_path / "shadow")
    probe = f"from fxtop.pk.lng import lng_one, {LONG_NAME}; print(lng_one(), {LONG_NAME}())"
    assert run_py(shadow, probe) == run_py(manifest.parent / "root", probe)
