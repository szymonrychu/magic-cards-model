"""P0-T08: `scripts/split/overlap.py` (ambiguous-pair count) and the
`test_dispatch_order.py` template, on the toy package under
tests/fixtures/split/registry/.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import types
from pathlib import Path

import pytest
from scripts.split import overlap as ov
from scripts.split.manifest_lib import load_manifest

from tests.test_split_to_registry import (
    CORPUS,
    MANIFEST,
    PKG,
    REG,
    REVERSED,
    TEMPLATE,
    import_generated,
    make_overlap_json,
    run_convert,
)

MONO = "tests.fixtures.split.registry.mono"


def monolith(manifest: Path = MANIFEST) -> dict:
    return ov.measure_monolith(
        REG / "mono.py", load_manifest(manifest), importlib.import_module(MONO), corpus=CORPUS
    )


def pairs(result: dict, entry: str = "_ability_effect_or_notice", seg: str = "s1") -> list[dict]:
    return result["ladders"][entry]["segments"][seg]["pairs"]


def test_monolith_counts_every_double_match_and_the_flipping_one():
    result = monolith()
    assert result["total_ambiguous"] == 2
    assert result["flipping"] == 1
    got = {(p["a"], p["b"]): p for p in pairs(result)}
    assert set(got) == {
        ("beta.parse_b_one", "alpha.parse_a_two"),
        ("alpha.parse_a_one", "beta.parse_b_two"),
    }
    flip = got[("beta.parse_b_one", "alpha.parse_a_two")]
    assert (flip["count"], flip["example"], flip["flips"]) == (1, "x", True)
    keep = got[("alpha.parse_a_one", "beta.parse_b_two")]
    assert (keep["count"], keep["example"], keep["flips"]) == (1, "ab", False)


def test_families_order_decides_which_pair_flips():
    result = monolith(REVERSED)
    assert (result["total_ambiguous"], result["flipping"]) == (2, 1)
    flips = {(p["a"], p["b"]): p["flips"] for p in pairs(result)}
    assert flips == {
        ("beta.parse_b_one", "alpha.parse_a_two"): False,
        ("alpha.parse_a_one", "beta.parse_b_two"): True,
    }


def test_segments_without_a_double_match_have_no_pairs():
    result = monolith()
    for entry, segs in result["ladders"].items():
        for name, seg in segs["segments"].items():
            if (entry, name) != ("_ability_effect_or_notice", "s1"):
                assert seg["pairs"] == [], (entry, name)


def test_segment_metadata_and_rungs_recorded():
    seg = monolith()["ladders"]["_parse_mixed_clauses"]["segments"]["s1"]
    assert seg["mode"] == "forward"
    assert seg["local"] == "text"
    assert seg["rungs"] == ["alpha.parse_a_fs", "beta.parse_b_fs"]


def test_for_spell_variants_are_all_run_and_counted():
    # a rung that matches only under for_spell=True still meets its partner there
    src = (
        "def a(text, *, for_spell):\n    return 1 if for_spell else None\n\n\n"
        "def b(text, *, for_spell):\n    return 1\n\n\n"
        "def _parse_mixed_clauses(text, *, for_spell):\n"
        "    x = a(text, for_spell=for_spell)\n    if x is not None:\n        return x\n"
        "    y = b(text, for_spell=for_spell)\n    if y is not None:\n        return y\n"
    )
    module = types.ModuleType("inline_mono")
    exec(compile(src, "inline_mono.py", "exec"), module.__dict__)  # noqa: S102
    result = ov.measure_source(src, module, ["a", "b"], corpus={"texts_and_spells": ["t", "u"]})
    (pair,) = result["ladders"]["_parse_mixed_clauses"]["segments"]["s1"]["pairs"]
    assert (pair["a"], pair["b"], pair["count"]) == ("a", "b", 2)


def test_a_rung_that_raises_counts_as_no_match():
    src = (
        "def a(text):\n    raise ValueError(text)\n\n\n"
        "def b(text):\n    return 1\n\n\n"
        "def _ability_effect_or_notice(effect_text):\n"
        "    x = a(effect_text)\n    if x is not None:\n        return x\n"
        "    y = b(effect_text)\n    if y is not None:\n        return y\n"
    )
    module = types.ModuleType("inline_mono2")
    exec(compile(src, "inline_mono2.py", "exec"), module.__dict__)  # noqa: S102
    result = ov.measure_source(src, module, ["a", "b"], corpus={"texts": ["t"]})
    assert result["total_ambiguous"] == 0


def test_output_is_deterministic():
    assert json.dumps(monolith(), sort_keys=True) == json.dumps(monolith(), sort_keys=True)


def test_post_f2_package_reports_edges_and_ordering(tmp_path):
    dest, _, _ = run_convert(tmp_path)
    plain = ov.measure_chains(
        importlib.import_module(import_generated(dest).__name__ + "._chains"), CORPUS
    )
    assert plain["total_ambiguous"] == 2
    assert all(p["ordered"] is False for p in pairs(plain))

    dest2, _, _ = run_convert(tmp_path / "second", overlap=make_overlap_json(tmp_path))
    ordered = ov.measure_chains(
        importlib.import_module(import_generated(dest2).__name__ + "._chains"), CORPUS
    )
    assert ordered["total_ambiguous"] == 2
    assert all(p["ordered"] is True for p in pairs(ordered))
    assert ordered["unordered"] == 0
    assert plain["unordered"] == 2


def test_cli_writes_json_and_prints_totals(tmp_path, capsys):
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps(CORPUS))
    out = tmp_path / "overlap.json"
    rc = ov.main(
        [
            "--source",
            str(REG / "mono.py"),
            "--manifest",
            str(MANIFEST),
            "--module",
            MONO,
            "--corpus-json",
            str(corpus),
            "--out",
            str(out),
        ]  # fmt: skip
    )
    assert rc == 0
    text = capsys.readouterr().out
    assert "ambiguous pairs: 2" in text
    assert "flipping: 1" in text
    assert json.loads(out.read_text())["total_ambiguous"] == 2


# ------------------------------------------------------------- order-test template


def load_template(chains_module: str, corpus: dict):
    spec = importlib.util.spec_from_file_location(
        "template_dispatch_order", TEMPLATE / "test_dispatch_order.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.CHAINS_MODULE = chains_module
    mod.build_corpus = lambda: corpus
    return mod


def test_template_passes_with_the_edge(tmp_path):
    dest, _, _ = run_convert(tmp_path, overlap=make_overlap_json(tmp_path))
    gen = import_generated(dest)
    mod = load_template(f"{gen.__name__}._chains", CORPUS)
    assert mod.unordered_double_matches(mod.CHAINS_MODULE, CORPUS) == []
    mod.test_no_unordered_double_matches()


def test_template_fails_without_the_edge_and_lists_each_pair(tmp_path):
    dest, _, _ = run_convert(tmp_path)
    gen = import_generated(dest)
    mod = load_template(f"{gen.__name__}._chains", CORPUS)
    found = mod.unordered_double_matches(mod.CHAINS_MODULE, CORPUS)
    assert len(found) == 2
    assert any("alpha.parse_a_two" in line and "beta.parse_b_one" in line for line in found)
    assert any("ABILITY_TEXT.s1" in line for line in found)
    with pytest.raises(AssertionError, match="parse_b_two"):
        mod.test_no_unordered_double_matches()


def test_template_accepts_a_transitive_edge():
    from scripts.split.templates._chains import Chain

    from tests.fixtures.split.chains import alpha, beta

    chain = Chain("toy", segments=("s1",), arg="text", families=("alpha", "beta"))
    for fn in (alpha.a_first, alpha.a_second, beta.b_first):
        chain.rung("s1")(fn)
    assert ov.ordered_closure(
        [("alpha.a_first", "alpha.a_second"), ("alpha.a_second", "beta.b_first")]
    ) >= {("alpha.a_first", "beta.b_first")}


def test_template_docstring_names_the_failure_mode():
    text = (TEMPLATE / "test_dispatch_order.py").read_text()
    doc = text.split('"""')[1]
    assert "Failure mode" in doc
    assert "every later suite" in doc


def test_manifest_fixture_is_valid():
    assert load_manifest(MANIFEST).targets == ["alpha", "beta", "dispatch"]
    assert PKG.is_dir()
