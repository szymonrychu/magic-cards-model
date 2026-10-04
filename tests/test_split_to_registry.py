"""P0-T08: the F2 codemod (`scripts/split/to_registry.py`) on a toy package.

The fixture package tests/fixtures/split/registry/pkg is a post-F1 package
(facade, two family modules, dispatch.py with the four ladders). Every test
that writes works on a copy under tmp_path; the generated package is imported
under a fresh top-level name so it never collides with the pristine fixture.
"""

from __future__ import annotations

import ast
import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest
from scripts.split import overlap as overlap_mod
from scripts.split import to_registry as tr
from scripts.split.manifest_lib import load_manifest

REG = Path(__file__).parent / "fixtures" / "split" / "registry"
PKG = REG / "pkg"
MANIFEST = REG / "registry.toml"
REVERSED = REG / "registry_reversed.toml"
TEMPLATE = Path(__file__).parent.parent / "scripts" / "split" / "templates"

CORPUS = {
    "texts": [
        "x",
        "ab",
        "a",
        "b",
        "!bang",
        "three",
        "  three  ",
        "bthree",
        "four",
        "bfour",
        "lazy",
        "q",
    ],  # fmt: skip
    "spells": ["three", "bthree", "four", "x", "  Three", "", "q"],
    "texts_and_spells": [
        "x",
        "ab",
        "a",
        "b",
        "fs",
        "bfs",
        "ft",
        "bt",
        "ff",
        "plain",
        "q",
        "x ab",
    ],  # fmt: skip
    "clauses": ["ac", "bc", "zz", "plain", "x", "q"],
}
LADDER_ENTRIES = (
    "_ability_effect_or_notice",
    "_spell_effect_or_notice",
    "_parse_mixed_clauses",
    "_parse_mixed_clause",
)

_counter = iter(range(10_000))


def defined_names(package: Path) -> set[str]:
    out: set[str] = set()
    for path in package.glob("*.py"):
        if path.name == "__init__.py":
            continue
        out |= {n.name for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef)}
    return out


def reports(package: Path = PKG):
    return tr.find_segments((package / "dispatch.py").read_text(), defined_names(package))


def rung_names(segment) -> list[str]:
    return [r.name for r in segment.rungs]


def copy_pkg(tmp_path: Path, name: str = "genpkg") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    dest = tmp_path / name
    shutil.copytree(PKG, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def run_convert(tmp_path: Path, manifest: Path = MANIFEST, overlap: Path | None = None):
    dest = copy_pkg(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)
    report = tr.convert(dest, manifest, overlap_path=overlap, tests_dir=tests_dir)
    return dest, tests_dir, report


def import_generated(dest: Path):
    """Import the generated package under a unique top-level name."""
    unique = f"regpkg_{next(_counter)}"
    target = dest.parent / unique
    shutil.copytree(dest, target, ignore=shutil.ignore_patterns("__pycache__"))
    sys.path.insert(0, str(dest.parent))
    try:
        return importlib.import_module(unique)
    finally:
        sys.path.remove(str(dest.parent))


def make_overlap_json(tmp_path: Path, manifest: Path = MANIFEST) -> Path:
    mono = importlib.import_module("tests.fixtures.split.registry.mono")
    result = overlap_mod.measure_monolith(
        REG / "mono.py", load_manifest(manifest), mono, corpus=CORPUS
    )
    path = tmp_path / "overlap.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True))
    return path


# ------------------------------------------------------------------ segment finder


def test_ability_ladder_segments_and_counts():
    r = reports()["_ability_effect_or_notice"]
    assert [s.name for s in r.segments] == ["s1", "s2", "s3"]
    s1, s2, s3 = r.segments
    assert rung_names(s1) == ["parse_b_one", "parse_a_two", "parse_a_one", "parse_b_two"]
    assert (s1.local, s1.mode) == ("effect_text", "plain")
    # the rebind of effect_text ends s1 even though s2 reads the same name
    assert rung_names(s2) == ["parse_a_three", "parse_b_three"]
    assert [d.name for d in s2.duplicates] == ["parse_a_three"]
    # the non-standard rung (`return seven[0]`) ends s2
    assert rung_names(s3) == ["parse_a_four"]
    assert r.rung_count == 8
    assert len(r.segments) == 3
    # lazy import, guard if, lazy rung (2), rebind, non-standard rung (2), return
    assert r.other_count == 8


def test_lazily_imported_rung_shape_is_not_pure():
    r = reports()["_ability_effect_or_notice"]
    assert all("parse_b_lazy" not in rung_names(s) for s in r.segments)
    assert r.other_kinds["Import"] == 1


def test_lazy_name_excluded_even_when_it_is_a_top_level_def():
    assert "parse_b_lazy" in defined_names(PKG)
    names = [n for s in reports()["_ability_effect_or_notice"].segments for n in rung_names(s)]
    assert "parse_b_lazy" not in names


def test_local_change_splits_a_segment_without_any_other_statement():
    r = reports()["_spell_effect_or_notice"]
    assert [(s.name, s.local, s.mode) for s in r.segments] == [
        ("s1", "whole", "plain"),
        ("s2", "effect_text", "plain"),
    ]
    assert [rung_names(s) for s in r.segments] == [
        ["parse_a_three", "parse_b_three"],
        ["parse_a_four"],
    ]
    assert (r.rung_count, r.other_count) == (3, 4)


def test_for_spell_modes_split_segments():
    r = reports()["_parse_mixed_clauses"]
    assert [(s.name, s.mode) for s in r.segments] == [
        ("s1", "forward"),
        ("s2", "true"),
        ("s3", "false"),
        ("s4", "plain"),
    ]
    assert [rung_names(s) for s in r.segments] == [
        ["parse_a_fs", "parse_b_fs"],
        ["parse_a_true", "parse_b_true"],
        ["parse_a_false"],
        ["parse_a_plain"],
    ]
    assert (r.rung_count, r.other_count) == (6, 1)


def test_variable_read_elsewhere_and_else_branch_are_not_pure():
    r = reports()["_parse_mixed_clause"]
    assert [rung_names(s) for s in r.segments] == [["parse_a_clause"]]
    assert (r.rung_count, r.other_count) == (1, 5)


def test_ladder_itself_and_unknown_names_are_not_rungs():
    src = (
        "def _ability_effect_or_notice(effect_text):\n"
        "    a = _ability_effect_or_notice(effect_text)\n"
        "    if a is not None:\n        return a\n"
        "    b = elsewhere(effect_text)\n"
        "    if b is not None:\n        return b\n"
        "    c = real(effect_text)\n"
        "    if c is not None:\n        return c\n"
    )
    r = tr.find_segments(src, {"real", "_ability_effect_or_notice"})["_ability_effect_or_notice"]
    assert [rung_names(s) for s in r.segments] == [["real"]]


def test_two_argument_call_and_wrong_test_are_not_pure():
    src = (
        "def _ability_effect_or_notice(effect_text):\n"
        "    a = real(effect_text, 1)\n"
        "    if a is not None:\n        return a\n"
        "    b = real(effect_text)\n"
        "    if b:\n        return b\n"
        "    c = real(effect_text, for_spell=effect_text)\n"
        "    if c is not None:\n        return c\n"
    )
    r = tr.find_segments(src, {"real"})["_ability_effect_or_notice"]
    assert r.segments == []
    assert r.rung_count == 0


def test_rungs_the_fingerprint_name_filter_cannot_see_are_listed():
    src = (
        "def _spell_effect_or_notice(effect_text):\n"
        "    a = _c02_t6_spell_effect(effect_text)\n"
        "    if a is not None:\n        return a\n"
        "    b = parse_real(effect_text)\n"
        "    if b is not None:\n        return b\n"
        "    c = _resolve_thing(effect_text)\n"
        "    if c is not None:\n        return c\n"
    )
    r = tr.find_segments(src, {"_c02_t6_spell_effect", "parse_real", "_resolve_thing"})
    assert tr.fingerprint_hidden(r["_spell_effect_or_notice"]) == ["_c02_t6_spell_effect"]


def test_find_segments_skips_ladders_that_are_absent():
    assert tr.find_segments("def other():\n    return 1\n", set()) == {}


def test_analyze_prints_one_row_per_ladder(capsys):
    assert tr.main(["analyze", str(PKG / "dispatch.py"), "--defs", str(PKG)]) == 0
    out = capsys.readouterr().out
    assert "_ability_effect_or_notice" in out
    row = next(line for line in out.splitlines() if "_parse_mixed_clauses" in line)
    assert row.split()[1:4] == ["6", "4", "1"]


# ------------------------------------------------------------------ the codemod


def test_chains_file_is_template_plus_families_and_one_chain_per_ladder(tmp_path):
    dest, _, _ = run_convert(tmp_path)
    text = (dest / "_chains.py").read_text()
    template = (TEMPLATE / "_chains.py").read_text()
    assert text.startswith(template)
    assert 'FAMILIES = ("alpha", "beta", "dispatch")' in text
    ns: dict = {}
    exec(compile(text, "_chains.py", "exec"), ns)  # noqa: S102
    chains = {
        name: ns[name] for name in ("ABILITY_TEXT", "SPELL_TEXT", "MIXED_CLAUSES", "MIXED_CLAUSE")
    }
    assert chains["ABILITY_TEXT"].segments == ("s1", "s2", "s3")
    assert chains["ABILITY_TEXT"].arg == "effect_text"
    assert chains["SPELL_TEXT"].segments == ("s1", "s2")
    assert chains["MIXED_CLAUSES"].segments == ("s1", "s2", "s3", "s4")
    assert chains["MIXED_CLAUSES"].arg == "text"
    assert chains["MIXED_CLAUSE"].segments == ("s1",)
    assert chains["MIXED_CLAUSE"].arg == "clause"
    assert all(c.families == ("alpha", "beta", "dispatch") for c in chains.values())


def test_dispatch_segments_replaced_and_rest_left_hand_written(tmp_path):
    dest, _, _ = run_convert(tmp_path)
    text = (dest / "dispatch.py").read_text()
    assert "from ._chains import ABILITY_TEXT, MIXED_CLAUSE, MIXED_CLAUSES, SPELL_TEXT" in text
    ast.parse(text)
    # exact one-line-per-segment shape, fresh name, forward only where it was forward
    assert 'if (seg_hit := ABILITY_TEXT.run("s1", effect_text)) is not None:' in text
    assert 'if (seg_hit := MIXED_CLAUSES.run("s1", text, for_spell=for_spell)) is not None:' in text
    assert 'MIXED_CLAUSES.run("s2", text)' in text
    assert 'MIXED_CLAUSES.run("s3", text)' in text
    assert 'SPELL_TEXT.run("s1", whole)' in text
    assert 'SPELL_TEXT.run("s2", effect_text)' in text
    # the spell ladder already uses seg_hit; its fresh name differs
    spell = text.split("def _spell_effect_or_notice")[1].split("\ndef ")[0]
    assert "seg_hit_2 :=" in spell
    assert "seg_hit :=" not in spell
    ability = text.split("def _ability_effect_or_notice")[1].split("\ndef ")[0]
    assert "seg_hit :=" in ability
    # guards, rebind, lazy rung, non-standard rung stay exactly where they were
    assert 'return ("guard", effect_text)' in text
    assert "effect_text = effect_text.strip()" in text
    assert "lazy = parse_b_lazy(effect_text)" in text
    assert "seven = parse_b_four(effect_text)" in text
    assert "return seven[0]" in text
    assert "seen = parse_b_clause(clause)" in text
    assert "parse_a_one(effect_text)" not in text
    # comment inside a converted run is kept
    assert 'b_one reads "x" before a_two does' in text


def test_converted_names_leave_the_dispatch_imports_and_used_ones_stay(tmp_path):
    dest, _, _ = run_convert(tmp_path)
    tree = ast.parse((dest / "dispatch.py").read_text())
    imported = {
        a.name
        for n in tree.body
        if isinstance(n, ast.ImportFrom) and n.module in ("alpha", "beta")
        for a in n.names
    }
    assert imported == {"parse_b_four", "parse_b_clause", "parse_a_plain"}


def test_decorators_written_above_existing_decorators(tmp_path):
    dest, _, _ = run_convert(tmp_path)
    alpha = (dest / "alpha.py").read_text()
    assert "from ._chains import" in alpha
    assert '@ABILITY_TEXT.rung("s3")\n@SPELL_TEXT.rung("s2")\n@_tag\ndef parse_a_four' in alpha
    assert '@ABILITY_TEXT.rung("s2")\n@SPELL_TEXT.rung("s1")\ndef parse_a_three' in alpha
    assert '@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)\ndef parse_a_fs' in alpha
    assert '@MIXED_CLAUSES.rung("s2", for_spell=True)\ndef parse_a_true' in alpha
    assert '@MIXED_CLAUSES.rung("s3", for_spell=False)\ndef parse_a_false' in alpha
    assert '@MIXED_CLAUSES.rung("s4")\ndef parse_a_plain' in alpha
    assert "FORWARD" in alpha.split("from ._chains import")[1].split("\n")[0]
    beta = (dest / "beta.py").read_text()
    assert '@ABILITY_TEXT.rung("s1")\ndef parse_b_one' in beta
    assert "\n\n\ndef parse_b_lazy" in beta


def test_duplicate_call_in_one_segment_keeps_first_and_is_reported(tmp_path):
    _, _, report = run_convert(tmp_path)
    assert report.duplicates == [("_ability_effect_or_notice", "s2", "parse_a_three")]
    dest = tmp_path / "genpkg"
    alpha = (dest / "alpha.py").read_text()
    assert alpha.count('@ABILITY_TEXT.rung("s2")') == 1


def test_generated_dispatch_returns_the_same_winners(tmp_path):
    overlap = make_overlap_json(tmp_path)
    dest, _, _ = run_convert(tmp_path, overlap=overlap)
    gen = import_generated(dest)
    orig = importlib.import_module("tests.fixtures.split.registry.pkg")
    keys = {
        "_ability_effect_or_notice": "texts",
        "_spell_effect_or_notice": "spells",
        "_parse_mixed_clauses": "texts_and_spells",
        "_parse_mixed_clause": "clauses",
    }
    checked = 0
    for entry, key in keys.items():
        new_fn, old_fn = getattr(gen, entry), getattr(orig, entry)
        for value in CORPUS[key]:
            if entry in ("_parse_mixed_clauses", "_parse_mixed_clause"):
                for fs in (False, True):
                    assert new_fn(value, for_spell=fs) == old_fn(value, for_spell=fs), (
                        entry,
                        value,
                    )
                    checked += 1
            else:
                assert new_fn(value) == old_fn(value), (entry, value)
                checked += 1
    assert checked > 40


def test_without_overlap_no_edges_are_written(tmp_path):
    dest, _, report = run_convert(tmp_path)
    assert report.edges == []
    for name in ("alpha.py", "beta.py"):
        assert "before=" not in (dest / name).read_text()


def test_edges_only_for_double_matching_pairs_oriented_to_source_order(tmp_path):
    overlap = make_overlap_json(tmp_path)
    dest, _, report = run_convert(tmp_path, overlap=overlap)
    assert report.edges == [
        ("_ability_effect_or_notice", "s1", "beta.parse_b_one", "alpha.parse_a_two"),
        ("_ability_effect_or_notice", "s1", "alpha.parse_a_one", "beta.parse_b_two"),
    ]
    alpha = (dest / "alpha.py").read_text()
    beta = (dest / "beta.py").read_text()
    assert '@ABILITY_TEXT.rung("s1", before=["alpha.parse_a_two"])\ndef parse_b_one' in beta
    assert '@ABILITY_TEXT.rung("s1", before=["beta.parse_b_two"])\ndef parse_a_one' in alpha
    assert alpha.count("before=") == 1
    assert beta.count("before=") == 1
    gen = import_generated(dest)
    chains = importlib.import_module(f"{gen.__name__}._chains")
    assert set(chains.ABILITY_TEXT.edges("s1")) == {
        ("beta.parse_b_one", "alpha.parse_a_two"),
        ("alpha.parse_a_one", "beta.parse_b_two"),
    }


def test_reversed_families_still_get_edges_for_every_double_match(tmp_path):
    overlap = make_overlap_json(tmp_path, REVERSED)
    _, _, report = run_convert(tmp_path, REVERSED, overlap)
    assert len(report.edges) == 2


def test_copies_the_order_test_template_into_tests(tmp_path):
    _, tests_dir, _ = run_convert(tmp_path)
    copied = tests_dir / "test_dispatch_order.py"
    assert copied.read_text() == (TEMPLATE / "test_dispatch_order.py").read_text()


def test_refuses_to_write_when_a_ladder_name_set_would_differ(tmp_path, monkeypatch):
    dest = copy_pkg(tmp_path)
    before = {p.name: p.read_text() for p in dest.glob("*.py")}
    real = tr._render_ladder

    def lossy(*args, **kwargs):
        text, names = real(*args, **kwargs)
        return text, names - {"parse_a_four"}

    monkeypatch.setattr(tr, "_render_ladder", lossy)
    with pytest.raises(tr.RegistryError, match="name set"):
        tr.convert(dest, MANIFEST, tests_dir=tmp_path / "tests")
    assert {p.name: p.read_text() for p in dest.glob("*.py")} == before
    assert not (dest / "_chains.py").exists()
    assert not (tmp_path / "tests" / "test_dispatch_order.py").exists()


def test_name_sets_equal_on_a_normal_run(tmp_path):
    _, _, report = run_convert(tmp_path)
    assert report.name_sets_equal is True


def test_second_run_is_refused(tmp_path):
    dest, tests_dir, _ = run_convert(tmp_path)
    with pytest.raises(tr.RegistryError, match="already"):
        tr.convert(dest, MANIFEST, tests_dir=tests_dir)


def test_cli_end_to_end(tmp_path, capsys):
    dest = copy_pkg(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    rc = tr.main([str(dest), "--manifest", str(MANIFEST), "--tests-dir", str(tests_dir)])
    assert rc == 0
    assert (dest / "_chains.py").exists()
    assert "duplicate" in capsys.readouterr().out


def test_generated_package_is_ruff_clean(tmp_path):
    import subprocess

    overlap = make_overlap_json(tmp_path)
    dest, _, _ = run_convert(tmp_path, overlap=overlap)
    cfg = Path(__file__).parent.parent / "pyproject.toml"
    done = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--config", str(cfg), str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_refuses_when_a_rung_the_fingerprint_filter_cannot_see_would_join_the_chain(tmp_path):
    """dispatch_fingerprint._chain_calls only lists 'parse*'/'_resolve*' names, so a pure
    rung named otherwise is hidden today but would appear once it runs through CHAIN.run."""
    dest = copy_pkg(tmp_path)
    for path in dest.glob("*.py"):
        path.write_text(path.read_text().replace("parse_a_four", "a_four"))
    before = {p.name: p.read_text() for p in dest.glob("*.py")}
    with pytest.raises(tr.RegistryError, match="name set.*a_four"):
        tr.convert(dest, MANIFEST, tests_dir=tmp_path / "tests")
    assert {p.name: p.read_text() for p in dest.glob("*.py")} == before
    assert not (dest / "_chains.py").exists()
